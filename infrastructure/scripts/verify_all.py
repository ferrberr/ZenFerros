#!/usr/bin/env python3
"""Puerta unica de verificacion de ZenFerros (TASK-907).

Ejecuta en secuencia las puertas de calidad del repositorio, con un timeout por
paso, y aborta en el primer fallo devolviendo un codigo distinto de cero.

Pasos:
  1. Compilador Zen: build release offline.
  2. Compilador Zen: tests release offline.
  3. Ferros: tests host + guests QEMU de la suite.
  4. Benchmarks: tests del arnes.
  5. Ferros: aceptacion QEMU (--all, 1 repeticion; 3 con --full).
  6. Benchmarks: medicion rapida (3 reps, 1 warmup, JSON/MD temporales).
  7. Self-hosting: tests de zen/selfhost/tests (obligatorio).
  8. Reproducibilidad: dos builds de C generado + usuario (completo con kernel en --full).

--quick omite los pasos 5 y 6. Los logs se guardan en un directorio temporal.
El script no escribe JSON/MD de benchmarks en el repositorio; los directorios de
build que generan las herramientas (target/, ferros/build/, benchmarks/build/)
ya estan declarados en .gitignore.
"""
from __future__ import annotations

import argparse
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CARGO_HOME = ROOT / ".cargo"
CARGO_MANIFEST = "zen/compiler/Cargo.toml"
SELFHOST_TESTS = ROOT / "zen/selfhost/tests"

# Conteos esperados: actualizar junto con las suites. La puerta falla si un paso
# pasa con menos tests de los declarados (evita que un filtro accidental reduzca
# la cobertura sin que el exit code lo delate).
EXPECTED_COUNTS = {
    2: 163,   # 34 unit + 9 arrays + 10 fmt + 8 freestanding + 10 include + 11 native + 12 stdlib + 12 stdlib_ext + 12 slices + 15 structs + 18 lint + 12 lsp
    3: 44,   # Ferros (persistencia ATA + mini-FS + PFS en VFS)
    4: 6,    # benchmarks
    7: 166,   # lexer (7) + parser (7) + AST (14) + tokens (11) + interp (16) + funciones (22) + typecheck (16) + codegen (16) + codegen_fns (18) + codegen_arrays (20) + codegen_structs (19)
}
COUNT_PATTERN = re.compile(r"Ran (\d+) tests?")
CARGO_COUNT_PATTERN = re.compile(r"test result: ok\. (\d+) passed")
CARGO_IGNORED_PATTERN = re.compile(r"test result: ok\. \d+ passed; \d+ failed; (\d+) ignored")

# Timeouts holgados por paso (segundos). Los valores observados en este host en
# 2026-11-11 estan muy por debajo; el limite solo evita que la puerta se cuelgue.
TIMEOUTS = {
    1: 600.0,
    2: 600.0,
    3: 900.0,
    4: 300.0,
    5: 900.0,
    6: 900.0,
    7: 300.0,
    8: 300.0,
}


@dataclass
class Step:
    number: int
    name: str
    command: list[str] = field(default_factory=list)
    timeout: float = 0.0
    env: dict[str, str] = field(default_factory=dict)
    skip_reason: str | None = None
    expect_tests: int | None = None
    count_mode: str = "unittest"


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


def build_steps(args: argparse.Namespace, run_dir: Path) -> list[Step]:
    python = sys.executable
    steps = [
        Step(
            1,
            "Compilador: build release (offline)",
            ["cargo", "build", "--release", "--offline", "--manifest-path", CARGO_MANIFEST],
            TIMEOUTS[1],
            {"CARGO_HOME": str(CARGO_HOME)},
        ),
        Step(
            2,
            "Compilador: tests release (offline)",
            ["cargo", "test", "--release", "--offline", "--manifest-path", CARGO_MANIFEST],
            TIMEOUTS[2],
            {"CARGO_HOME": str(CARGO_HOME)},
        ),
        Step(
            3,
            "Ferros: tests host y QEMU",
            [python, "-m", "unittest", "discover", "-s", "ferros/tests"],
            TIMEOUTS[3],
        ),
        Step(
            4,
            "Benchmarks: tests del arnes",
            [python, "-m", "unittest", "discover", "-s", "benchmarks/tests"],
            TIMEOUTS[4],
        ),
    ]

    if args.quick:
        steps.append(
            Step(
                5,
                "Ferros: aceptacion QEMU",
                skip_reason="omitido por --quick",
            )
        )
        steps.append(
            Step(
                6,
                "Benchmarks: medicion rapida",
                skip_reason="omitido por --quick",
            )
        )
    else:
        repeat = 3 if args.full else 1
        boots = 2 * repeat  # --all ejecuta debug y release
        steps.append(
            Step(
                5,
                f"Ferros: aceptacion QEMU ({boots} arranques)",
                [
                    python,
                    "infrastructure/scripts/boot_ferros.py",
                    "--all",
                    "--repeat",
                    str(repeat),
                ],
                TIMEOUTS[5],
            )
        )
        bench_dir = run_dir / "bench"
        bench_dir.mkdir(parents=True, exist_ok=True)
        steps.append(
            Step(
                6,
                "Benchmarks: medicion rapida (reps=3, warmup=1)",
                [
                    python,
                    "benchmarks/scripts/bench.py",
                    "--reps",
                    "3",
                    "--warmup",
                    "1",
                    "--json",
                    str(bench_dir / "bench.json"),
                    "--md",
                    str(bench_dir / "bench.md"),
                ],
                TIMEOUTS[6],
            )
        )

    if SELFHOST_TESTS.is_dir():
        steps.append(
            Step(
                7,
                "Self-hosting: tests de zen/selfhost/tests",
                [python, "-m", "unittest", "discover", "-s", "zen/selfhost/tests"],
                TIMEOUTS[7],
                expect_tests=EXPECTED_COUNTS.get(7),
            )
        )
    else:
        steps.append(
            Step(
                7,
                "Self-hosting: tests de zen/selfhost/tests",
                command=[python, "-c",
                         "import sys; print('zen/selfhost/tests missing: partial self-hosting is part of the repo'); sys.exit(1)"],
                timeout=5.0,
            )
        )
    repro = [python, "infrastructure/scripts/repro_build.py"]
    if not args.full:
        repro.append("--quick")
    steps.append(
        Step(
            8,
            "Reproducibilidad: C generado + Ferros" + ("" if args.full else " (rápida)"),
            repro,
            TIMEOUTS[8],
        )
    )
    for step in steps:
        if step.skip_reason is None and step.number in EXPECTED_COUNTS:
            step.expect_tests = EXPECTED_COUNTS[step.number]
            step.count_mode = "cargo" if step.number == 2 else "unittest"
    return steps


def combined_output(result: subprocess.CompletedProcess[str]) -> str:
    return result.stdout + result.stderr


def print_output(text: str, label: str) -> None:
    lines = text.splitlines()
    if not lines:
        print("  (sin salida)")
        return
    print(f"  {label} ({len(lines)} lineas):")
    for line in lines:
        print(f"  {line}")


def run_step(step: Step, run_dir: Path, total_steps: int) -> tuple[str, float, Path]:
    log_path = run_dir / f"{step.number:02d}-{step.name.split(':')[0].lower().replace(' ', '-')}.log"
    header = [
        f"# {step.number}/{total_steps} {step.name}",
        f"# cwd: {ROOT}",
    ]

    print(f"\n[{step.number}/{total_steps}] {step.name}")
    if step.skip_reason is not None:
        print(f"  SKIP: {step.skip_reason}")
        log_path.write_text("\n".join(header + [f"SKIP: {step.skip_reason}"]) + "\n", encoding="utf-8")
        return "SKIP", 0.0, log_path

    header.append(f"# $ {command_line(step)}")
    header.append(f"# timeout: {format_duration(step.timeout)}")
    print(f"  $ {command_line(step)}")

    env = os.environ.copy()
    env.update(step.env)
    env.setdefault("CARGO_TERM_COLOR", "never")
    started = time.monotonic()
    status = "FAIL"
    output = ""

    try:
        result = subprocess.run(
            step.command,
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=step.timeout,
        )
        output = combined_output(result)
        if result.returncode == 0:
            status = "PASS"
            detail = f"  PASS ({format_duration(time.perf_counter() - started)})"
        else:
            detail = (
                f"  FAIL (codigo {result.returncode}, "
                f"{format_duration(time.perf_counter() - started)})"
            )
    except subprocess.TimeoutExpired as exc:
        raw_stdout = exc.stdout or ""
        raw_stderr = exc.stderr or ""
        if isinstance(raw_stdout, bytes):
            raw_stdout = raw_stdout.decode("utf-8", errors="replace")
        if isinstance(raw_stderr, bytes):
            raw_stderr = raw_stderr.decode("utf-8", errors="replace")
        output = raw_stdout + raw_stderr
        detail = f"  FAIL (timeout tras {format_duration(step.timeout)})"
    except OSError as exc:
        output = f"{type(exc).__name__}: {exc}\n"
        detail = f"  FAIL (no se pudo ejecutar: {exc})"

    elapsed = time.monotonic() - started
    log_path.write_text("\n".join(header) + "\n\n" + output, encoding="utf-8")

    if status == "PASS" and step.expect_tests is not None:
        if step.count_mode == "cargo":
            found = sum(int(match) for match in CARGO_COUNT_PATTERN.findall(output))
            ignored = sum(int(match) for match in CARGO_IGNORED_PATTERN.findall(output))
            if ignored:
                status = "FAIL"
                output += f"\n[gate] {ignored} tests ignorados en cargo test; no se admite cobertura reducida\n"
                log_path.write_text("\n".join(header) + "\n\n" + output, encoding="utf-8")
                print_output(output, "salida completa")
                print(f"  FAIL ({ignored} tests ignorados)")
                return status, elapsed, log_path
        else:
            match = COUNT_PATTERN.search(output)
            found = int(match.group(1)) if match else -1
        if step.number in (3, 4, 7) and "skipped" in output.lower():
            status = "FAIL"
            output += "\n[gate] la suite reporta tests skipped; la cobertura verificada no admite skips\n"
            log_path.write_text("\n".join(header) + "\n\n" + output, encoding="utf-8")
            print_output(output, "salida completa")
            print(f"  log: {log_path}")
            print(f"  FAIL (tests skipped en el paso {step.number})")
            return status, elapsed, log_path
        if found != step.expect_tests:
            status = "FAIL"
            output += (
                f"\n[gate] conteo inesperado: {found} tests, esperados {step.expect_tests}. "
                "Actualiza EXPECTED_COUNTS solo si el cambio de cobertura es intencionado.\n"
            )
            log_path.write_text("\n".join(header) + "\n\n" + output, encoding="utf-8")
            detail = f"  FAIL (conteo {found} != {step.expect_tests}, {format_duration(time.perf_counter() - started)})"
            print_output(output, "salida completa")
            print(f"  log: {log_path}")
            print(detail)
            return status, elapsed, log_path

    if status == "PASS":
        print(f"  salida (ultimas 6 lineas):")
        for line in [line for line in output.splitlines() if line.strip()][-6:]:
            print(f"  {line}")
    else:
        print_output(output, "salida completa")
        print(f"  log: {log_path}")
    print(detail)
    return status, elapsed, log_path


def print_summary(
    results: list[tuple[Step, str, float, Path | None]], total: float, run_dir: Path
) -> None:
    print("\n" + "=" * 100)
    print("Resumen de la puerta de verificacion")
    print("=" * 100)
    print(f"  {'#':>2}  {'Paso':<46} {'Estado':<7} {'Duracion':>9}  Log")
    for step, status, elapsed, log_path in results:
        duration = "-" if status == "SKIP" else format_duration(elapsed)
        log_name = log_path.name if log_path is not None else "-"
        print(f"  {step.number:>2}. {step.name:<46} {status:<7} {duration:>9}  {log_name}")
    print("-" * 100)
    print(f"  TOTAL: {format_duration(total)}")
    print(f"  Logs: {run_dir}")
    failed = any(status == "FAIL" for _, status, _, _ in results)
    skipped = [step.number for step, status, _, _ in results if status == "SKIP"]
    if skipped:
        print(f"  Omitidos/no ejecutados: pasos {', '.join(str(number) for number in skipped)}")
    print(f"  Resultado: {'FALLO' if failed else 'OK'}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Puerta unica de verificacion de ZenFerros (compilador, Ferros, benchmarks y self-hosting).",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--quick",
        action="store_true",
        help="omite la aceptacion QEMU y la medicion de benchmarks (pasos 5 y 6)",
    )
    mode.add_argument(
        "--full",
        action="store_true",
        help="aceptacion QEMU con 3 repeticiones por perfil (6 arranques)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.quick:
        mode = "quick (sin QEMU ni medicion de benchmarks)"
    elif args.full:
        mode = "full (QEMU: 6 arranques)"
    else:
        mode = "normal (QEMU: 2 arranques)"

    try:
        run_dir = Path(tempfile.mkdtemp(prefix="zenferros-verify-"))
    except OSError as exc:
        print(f"error: no se pudo crear el directorio temporal de logs: {exc}", file=sys.stderr)
        return 1

    print("ZenFerros - puerta unica de verificacion (TASK-907)")
    print(f"  repo: {ROOT}")
    print(f"  modo: {mode}")
    print(f"  logs: {run_dir}")

    steps = build_steps(args, run_dir)
    results: list[tuple[Step, str, float, Path | None]] = []
    total_started = time.monotonic()
    aborted = False

    try:
        for step in steps:
            if aborted:
                print(f"\n[{step.number}/{len(steps)}] {step.name}")
                print("  SKIP: no ejecutado por el fallo anterior")
                results.append((step, "SKIP", 0.0, None))
                continue
            status, elapsed, log_path = run_step(step, run_dir, len(steps))
            results.append((step, status, elapsed, log_path))
            if status == "FAIL":
                aborted = True
    except KeyboardInterrupt:
        print("\nCancelado por el usuario.")
        return 130

    total = time.monotonic() - total_started
    print_summary(results, total, run_dir)
    return 1 if aborted else 0


if __name__ == "__main__":
    raise SystemExit(main())
