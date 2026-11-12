#!/usr/bin/env python3
"""Matriz de CI local por perfiles para ZenFerros (TASK-911).

Un unico comando reproducible ejecuta la matriz de verificacion local:

  --quick   cargo test release, verify_all --quick, stress --quick y
            repro_build --quick.
  defecto   ademas cargo test debug, verify_all normal y repro_build completo;
            el estres sigue en modo quick.
  --full    ademas verify_all --full y stress completo (~2-3 min en este host).

Cada paso se ejecuta sin shell, con cwd en la raiz del repositorio, timeout
propio y un log en un directorio temporal. Al primer fallo se omite el resto,
se imprime el resumen y se sale con codigo distinto de cero. El resumen se
puede exportar a JSON con `--json RUTA`.

Este script no es CI remoto, no usa contenedores y no fija el toolchain: solo
ordena y registra las puertas que ya existen en este host. No modifica codigo
ni escribe artefactos propios en el repositorio (logs y resumen viven bajo
`/tmp/zenferros-ci-*`); los directorios de build ya ignorados por git
(`target/`, `ferros/build/`, `benchmarks/build/`) siguen usandose como hasta
ahora.

Uso:
    python3 infrastructure/scripts/ci_matrix.py --quick
    python3 infrastructure/scripts/ci_matrix.py
    python3 infrastructure/scripts/ci_matrix.py --full --json /tmp/ci.json
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CARGO_HOME = ROOT / ".cargo"
CARGO_MANIFEST = "zen/compiler/Cargo.toml"
ZEN = ROOT / "zen/compiler/target/release/zen"
PYTHON = sys.executable
PROBE_TIMEOUT = 15.0
TAIL_LINES = 30
TASK = "TASK-911"

# Timeouts holgados por paso (segundos). Los valores observados en este host
# estan muy por debajo; el limite solo evita que la matriz se cuelgue.
TIMEOUTS = {
    "cargo_debug": 900.0,
    "cargo_release": 900.0,
    "verify_quick": 1200.0,
    "verify_normal": 1800.0,
    "verify_full": 1800.0,
    "stress_quick": 900.0,
    "stress_full": 1800.0,
    "repro_quick": 600.0,
    "repro_full": 900.0,
}

LIMITS = [
    "No es CI remoto: se ejecuta en este host, con su carga, su reloj y su toolchain.",
    "No usa contenedores ni una imagen o toolchain fijados; el PASS describe este host.",
    "No demuestra nada sobre otros hosts, distros, CPUs, versiones de GCC/ld/Rust o hardware fisico.",
    "No es una atestacion de procedencia: el commit local no aporta firma ni cadena de suministro.",
    "No fija umbrales de rendimiento: mide duracion de los pasos, no rendimiento del lenguaje.",
    "Los timeouts evitan cuelgues, no son un presupuesto de rendimiento ni un SLA.",
    "No sustituye a verify_all.py, stress.py ni repro_build.py: los compone en una matriz.",
    "Los builds escriben en target/, ferros/build/ y benchmarks/build/ (ya ignorados por git); "
    "logs y resumen van a un directorio temporal.",
]


@dataclass
class Step:
    number: int
    name: str
    command: list[str] = field(default_factory=list)
    timeout: float = 0.0
    env: dict[str, str] = field(default_factory=dict)


def format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.2f}s"
    minutes, remainder = divmod(seconds, 60)
    return f"{int(minutes)}m {remainder:04.1f}s"


def command_line(step: Step) -> str:
    command = " ".join(shlex.quote(item) for item in step.command)
    if step.env:
        prefix = " ".join(f"{key}={shlex.quote(value)}" for key, value in step.env.items())
        return f"env {prefix} {command}"
    return command


def abbreviate(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


def tail_lines(text: str, limit: int = TAIL_LINES) -> list[str]:
    lines = [line for line in text.splitlines() if line.strip()]
    return lines[-limit:]


def base_environment() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("CARGO_TERM_COLOR", "never")
    # Los scripts y las suites no deben dejar __pycache__ nuevos en el arbol.
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


# ---------------------------------------------------------------------------
# Matriz
# ---------------------------------------------------------------------------


def matrix_mode(args: argparse.Namespace) -> str:
    if args.quick:
        return "quick"
    if args.full:
        return "full"
    return "default"


def build_steps(args: argparse.Namespace) -> list[Step]:
    steps: list[Step] = []
    cargo_env = {"CARGO_HOME": str(CARGO_HOME)}
    cargo_base = ["cargo", "test", "--offline", "--manifest-path", CARGO_MANIFEST]

    if not args.quick:
        steps.append(
            Step(
                len(steps) + 1,
                "Compilador: cargo test debug (offline)",
                cargo_base,
                TIMEOUTS["cargo_debug"],
                cargo_env,
            )
        )
    steps.append(
        Step(
            len(steps) + 1,
            "Compilador: cargo test release (offline)",
            [*cargo_base, "--release"],
            TIMEOUTS["cargo_release"],
            cargo_env,
        )
    )

    verify = [PYTHON, "infrastructure/scripts/verify_all.py"]
    if args.quick:
        verify.append("--quick")
        verify_timeout = TIMEOUTS["verify_quick"]
        verify_name = "Puerta: verify_all --quick"
    elif args.full:
        verify.append("--full")
        verify_timeout = TIMEOUTS["verify_full"]
        verify_name = "Puerta: verify_all --full"
    else:
        verify_timeout = TIMEOUTS["verify_normal"]
        verify_name = "Puerta: verify_all (normal)"
    steps.append(Step(len(steps) + 1, verify_name, verify, verify_timeout))

    stress = [PYTHON, "infrastructure/scripts/stress.py"]
    if args.quick or not args.full:
        stress.append("--quick")
        stress_timeout = TIMEOUTS["stress_quick"]
        stress_name = "Estres: stress --quick"
    else:
        stress_timeout = TIMEOUTS["stress_full"]
        stress_name = "Estres: stress completo"
    steps.append(Step(len(steps) + 1, stress_name, stress, stress_timeout))

    repro = [PYTHON, "infrastructure/scripts/repro_build.py"]
    if args.quick:
        repro.append("--quick")
        repro_timeout = TIMEOUTS["repro_quick"]
        repro_name = "Reproducibilidad: repro_build --quick"
    else:
        repro_timeout = TIMEOUTS["repro_full"]
        repro_name = "Reproducibilidad: repro_build completo"
    steps.append(Step(len(steps) + 1, repro_name, repro, repro_timeout))
    return steps


# ---------------------------------------------------------------------------
# Toolchain
# ---------------------------------------------------------------------------


def probe_tool(name: str, executable: str, args: tuple[str, ...] = ("--version",)) -> dict:
    """Version de una herramienta; no falla si no esta instalada."""
    record: dict = {
        "name": name,
        "command": [executable, *args],
        "found": False,
    }
    resolved = shutil.which(str(executable))
    if resolved is None and Path(str(executable)).is_file():
        resolved = str(Path(str(executable)).resolve())
    if resolved is None:
        record["error"] = "no encontrado"
        return record
    record.update(found=True, path=resolved)
    started = time.perf_counter()
    try:
        result = subprocess.run(
            [resolved, *args],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=PROBE_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        record.update(
            seconds=round(time.perf_counter() - started, 4),
            error=f"timeout tras {format_duration(PROBE_TIMEOUT)}",
        )
        return record
    except OSError as exc:
        record.update(
            seconds=round(time.perf_counter() - started, 4),
            error=f"{type(exc).__name__}: {exc}",
        )
        return record
    output = ((result.stdout or "") + (result.stderr or "")).strip()
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    record.update(
        exit=result.returncode,
        version=lines[0] if lines else "",
        output=output[:2000],
        seconds=round(time.perf_counter() - started, 4),
    )
    if result.returncode != 0:
        record["error"] = f"exit {result.returncode}"
    return record


def probe_toolchain() -> dict:
    records = {
        "cc": probe_tool("cc", os.environ.get("CC", "cc")),
        "ld": probe_tool("ld", "ld"),
        "rustc": probe_tool("rustc", "rustc"),
        "zen": probe_tool("zen", str(ZEN), args=("version",)),
    }
    zen = records["zen"]
    zen["release"] = "Compiler build: release" in zen.get("output", "")
    return records


def toolchain_warnings(toolchain: dict) -> list[str]:
    warnings: list[str] = []
    for name in ("cc", "ld", "rustc"):
        record = toolchain[name]
        if not record.get("found"):
            warnings.append(f"{name} no encontrado; los pasos que lo usan fallaran")
        elif record.get("error"):
            warnings.append(f"{name}: {record['error']}")
    zen = toolchain["zen"]
    if not zen.get("found"):
        warnings.append(
            "zen release no existe todavia; repro_build lo construira en un target temporal si hace falta"
        )
    elif not zen.get("release"):
        warnings.append(
            "zen no declara 'Compiler build: release'; repro_build exigira el perfil release"
        )
    return warnings


def print_toolchain(toolchain: dict) -> None:
    print("\nToolchain (registrado, no es un paso de la matriz):")
    for name in ("cc", "ld", "rustc", "zen"):
        record = toolchain[name]
        if record.get("found") and not record.get("error"):
            print(f"  {name:<6} {record.get('version') or 'version desconocida'}")
        else:
            detail = record.get("error") or "no encontrado"
            print(f"  {name:<6} AUSENTE ({detail})")
    zen = toolchain["zen"]
    if zen.get("found"):
        release = "release" if zen.get("release") else "perfil NO release"
        print(f"         {zen.get('path')} ({release})")


# ---------------------------------------------------------------------------
# Ejecucion de pasos
# ---------------------------------------------------------------------------


def log_path_for(step: Step, run_dir: Path) -> Path:
    slug = (
        step.name.split(":")[-1]
        .strip()
        .lower()
        .replace(" ", "-")
        .replace("(", "")
        .replace(")", "")
        .replace("--", "")
        .replace("/", "-")
    )
    return run_dir / f"{step.number:02d}-{slug}.log"


def write_log(log_path: Path, header: list[str], output: str) -> None:
    body = "\n".join(header)
    if output:
        body += "\n\n" + output
    log_path.write_text(body + "\n", encoding="utf-8")


def skip_step(step: Step, reason: str, total: int, run_dir: Path) -> dict:
    log_path = log_path_for(step, run_dir)
    header = [
        f"# {step.number}/{total} {step.name}",
        f"# cwd: {ROOT}",
        f"# $ {command_line(step)}",
        f"# timeout: {format_duration(step.timeout)}",
        f"SKIP: {reason}",
    ]
    write_log(log_path, header, "")
    print(f"\n[{step.number}/{total}] {step.name}")
    print(f"  SKIP: {reason}")
    return {
        "number": step.number,
        "name": step.name,
        "status": "SKIP",
        "seconds": 0.0,
        "returncode": None,
        "timeout_seconds": step.timeout,
        "command": list(step.command),
        "command_line": command_line(step),
        "log": str(log_path),
        "log_name": log_path.name,
        "error": None,
        "skip_reason": reason,
    }


def run_step(step: Step, total: int, run_dir: Path) -> dict:
    log_path = log_path_for(step, run_dir)
    header = [
        f"# {step.number}/{total} {step.name}",
        f"# cwd: {ROOT}",
        f"# $ {command_line(step)}",
        f"# timeout: {format_duration(step.timeout)}",
    ]
    print(f"\n[{step.number}/{total}] {step.name}")
    print(f"  $ {command_line(step)}")

    env = base_environment()
    env.update(step.env)
    started = time.perf_counter()
    status = "FAIL"
    returncode: int | None = None
    error: str | None = None
    output = ""

    try:
        result = subprocess.run(
            step.command,
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=step.timeout,
            shell=False,
        )
        returncode = result.returncode
        output = (result.stdout or "") + (result.stderr or "")
        if returncode == 0:
            status = "PASS"
        else:
            error = f"exit {returncode}"
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") + (exc.stderr or "")
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        error = f"timeout tras {format_duration(step.timeout)}"
    except OSError as exc:
        error = f"no se pudo ejecutar {step.command[0]!r}: {exc}"

    elapsed = time.perf_counter() - started
    if returncode is not None:
        header.append(f"# exit: {returncode}")
    if error is not None:
        header.append(f"# error: {error}")
    header.append(f"# seconds: {elapsed:.4f}")
    write_log(log_path, header, output)

    if status == "PASS":
        print(f"  PASS ({format_duration(elapsed)})")
        for line in tail_lines(output, 6):
            print(f"    {line}")
    else:
        print(f"  FAIL ({error}, {format_duration(elapsed)})")
        print(f"  salida (ultimas {TAIL_LINES} lineas):")
        for line in tail_lines(output):
            print(f"    {line}")
        print(f"  log: {log_path}")

    return {
        "number": step.number,
        "name": step.name,
        "status": status,
        "seconds": round(elapsed, 4),
        "returncode": returncode,
        "timeout_seconds": step.timeout,
        "command": list(step.command),
        "command_line": command_line(step),
        "log": str(log_path),
        "log_name": log_path.name,
        "error": error,
        "skip_reason": None,
    }


# ---------------------------------------------------------------------------
# Resumen y JSON
# ---------------------------------------------------------------------------


def host_info() -> dict:
    cpu = ""
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.is_file():
        for line in cpuinfo.read_text(errors="replace").splitlines():
            if line.lower().startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    return {
        "platform": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "processor": cpu or platform.processor(),
        "python": sys.version.splitlines()[0],
        "python_executable": sys.executable,
    }


def print_summary(
    mode: str,
    results: list[dict],
    total: float,
    run_dir: Path,
    failed_step: int | None,
    warnings: list[str],
    interrupted: bool,
) -> None:
    print("\n" + "=" * 132)
    print(f"Resumen de la matriz de CI local ({TASK}) — modo {mode}")
    print("=" * 132)
    print(
        f"  {'#':>2}  {'Paso':<44} {'Estado':<7} {'Duracion':>9}  "
        f"{'Comando':<46}  Log"
    )
    for record in results:
        duration = "-" if record["status"] == "SKIP" else format_duration(record["seconds"])
        command = abbreviate(record["command_line"], 46)
        print(
            f"  {record['number']:>2}. {record['name']:<44} {record['status']:<7} "
            f"{duration:>9}  {command:<46}  {record['log_name']}"
        )
    print("-" * 132)
    print(f"  TOTAL: {format_duration(total)}")
    print(f"  Logs: {run_dir}")
    if warnings:
        print("  Avisos de toolchain:")
        for warning in warnings:
            print(f"    - {warning}")
    if failed_step is not None:
        print(f"  Primer fallo: paso {failed_step}; el resto no se ejecuto")
    result = "INTERRUMPIDO" if interrupted else ("FALLO" if failed_step is not None else "PASS")
    print(f"  Resultado: {result}")


def prepare_json_path(raw: str | None) -> tuple[Path | None, str | None]:
    """Valida y prepara el destino de --json antes de ejecutar la matriz."""
    if raw is None:
        return None, None
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    if path.exists() and path.is_dir():
        return None, f"--json apunta a un directorio, no a un fichero: {path}"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return None, f"no se pudo preparar el directorio de --json ({path.parent}): {exc}"
    if not path.parent.is_dir():
        return None, f"el directorio padre de --json no existe: {path.parent}"
    return path, None


def build_document(
    *,
    mode: str,
    toolchain: dict,
    results: list[dict],
    total: float,
    run_dir: Path,
    failed_step: int | None,
    warnings: list[str],
    interrupted: bool,
) -> dict:
    return {
        "task": TASK,
        "schema": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": mode,
        "result": "FAIL" if failed_step is not None else ("INTERRUPTED" if interrupted else "PASS"),
        "repo": {
            "root": str(ROOT),
            "git": (ROOT / ".git").exists(),
        },
        "host": host_info(),
        "toolchain": {
            name: {
                "found": record.get("found", False),
                "path": record.get("path"),
                "version": record.get("version"),
                "release": record.get("release"),
                "exit": record.get("exit"),
                "seconds": record.get("seconds"),
                "error": record.get("error"),
                "command": record.get("command"),
                "output": record.get("output"),
            }
            for name, record in toolchain.items()
        },
        "matrix": {
            "steps": [
                {
                    "number": record["number"],
                    "name": record["name"],
                    "status": record["status"],
                    "seconds": record["seconds"],
                    "timeout_seconds": record["timeout_seconds"],
                    "returncode": record["returncode"],
                    "command": record["command"],
                    "command_line": record["command_line"],
                    "log": record["log"],
                    "error": record["error"],
                    "skip_reason": record["skip_reason"],
                }
                for record in results
            ],
            "executed": sum(1 for record in results if record["status"] != "SKIP"),
            "passed": sum(1 for record in results if record["status"] == "PASS"),
            "failed": sum(1 for record in results if record["status"] == "FAIL"),
            "skipped": sum(1 for record in results if record["status"] == "SKIP"),
        },
        "failed_step": failed_step,
        "total_seconds": round(total, 4),
        "logs": str(run_dir),
        "warnings": warnings,
        "limits": LIMITS,
    }


def write_json(path: Path, document: dict) -> str | None:
    try:
        path.write_text(
            json.dumps(document, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        return f"no se pudo escribir --json ({path}): {exc}"
    return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Matriz local de CI de ZenFerros: compilador, puerta, estres y "
            "reproducibilidad con resumen JSON (TASK-911)."
        ),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--quick",
        action="store_true",
        help="cargo test release + verify_all --quick + stress --quick + repro_build --quick",
    )
    mode.add_argument(
        "--full",
        action="store_true",
        help="anade verify_all --full y stress completo (2-3 min en este host)",
    )
    parser.add_argument(
        "--json",
        metavar="RUTA",
        help="escribe el resumen de la matriz como JSON en RUTA (por defecto, solo en el temporal)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    mode = matrix_mode(args)
    json_path, json_error = prepare_json_path(args.json)
    if json_error is not None:
        print(f"error: {json_error}", file=sys.stderr)
        return 2

    try:
        run_dir = Path(tempfile.mkdtemp(prefix="zenferros-ci-"))
    except OSError as exc:
        print(f"error: no se pudo crear el directorio temporal de logs: {exc}", file=sys.stderr)
        return 1

    steps = build_steps(args)
    print(f"ZenFerros — matriz de CI local ({TASK})")
    print(f"  repo: {ROOT}")
    print(f"  modo: {mode} ({len(steps)} pasos)")
    print(f"  logs: {run_dir}")
    if json_path is not None:
        print(f"  json: {json_path}")

    toolchain_started = time.perf_counter()
    toolchain = probe_toolchain()
    print_toolchain(toolchain)
    warnings = toolchain_warnings(toolchain)
    for warning in warnings:
        print(f"  aviso: {warning}")
    print(f"  (sondas de toolchain: {format_duration(time.perf_counter() - toolchain_started)})")

    results: list[dict] = []
    failed_step: int | None = None
    interrupted = False
    total_started = time.perf_counter()
    try:
        for step in steps:
            if failed_step is not None:
                results.append(
                    skip_step(
                        step,
                        f"no ejecutado: fallo en el paso {failed_step}",
                        len(steps),
                        run_dir,
                    )
                )
                continue
            record = run_step(step, len(steps), run_dir)
            results.append(record)
            if record["status"] == "FAIL":
                failed_step = step.number
    except KeyboardInterrupt:
        interrupted = True
        print("\nCancelado por el usuario.")

    total = time.perf_counter() - total_started
    print_summary(mode, results, total, run_dir, failed_step, warnings, interrupted)

    document = build_document(
        mode=mode,
        toolchain=toolchain,
        results=results,
        total=total,
        run_dir=run_dir,
        failed_step=failed_step,
        warnings=warnings,
        interrupted=interrupted,
    )

    summary_path = run_dir / "summary.json"
    try:
        summary_path.write_text(
            json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"  Resumen JSON: {summary_path}")
    except OSError as exc:
        print(f"  aviso: no se pudo escribir {summary_path}: {exc}", file=sys.stderr)

    write_error: str | None = None
    if json_path is not None:
        write_error = write_json(json_path, document)
        if write_error is None:
            print(f"  JSON de matriz: {json_path}")
    if write_error is not None:
        print(f"error: {write_error}", file=sys.stderr)

    if interrupted:
        return 130
    if failed_step is not None or write_error is not None:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
