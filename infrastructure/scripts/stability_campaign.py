#!/usr/bin/env python3
"""TASK-913: campana de estabilidad repetida para Zen/Ferros.

Coordina N rondas de `stress.py` y, en modo `full`, una puerta
`verify_all.py --full` por ronda. No reimplementa el estres ni la puerta: los
invoca como subprocesos, mide su duracion y extrae las metricas del resumen JSON
que `stress.py` ya escribe en su directorio temporal.

Por ronda:
  1. `stress.py --quick` (modo quick) o `stress.py` (modo full).
  2. Solo en full: `verify_all.py --full`, que incluye 6 arranques QEMU
     (debug/release x 3) y la puerta completa de calidad.
  3. Se comprueban el codigo de salida, el `result` del resumen y, en full, que
     los 6 arranques del gate terminan con estado 33. Se registran boots PASS,
     suites y metricas de fuzz.

La campana para en el primer fallo y guarda un resumen parcial. El resumen JSON
(`schema`, `rounds`, `results`, `totals`, `warnings`) se escribe siempre en el
directorio temporal de la campana y, si se indica, tambien en `--json RUTA`.

No escribe artefactos en el repositorio: logs y JSON viven en
`/tmp/zenferros-campaign-*`. No declara ningun subsistema Estable ni sustituye a
`verify_all.py`; es evidencia acotada de repeticion.

Uso:
    python3 infrastructure/scripts/stability_campaign.py --rounds 5
    python3 infrastructure/scripts/stability_campaign.py --rounds 2 --mode full
    python3 infrastructure/scripts/stability_campaign.py --rounds 3 --json /tmp/campana.json

Codigos de salida: 0 si todas las rondas PASS; 1 en el primer fallo (con resumen
parcial); 2 si los argumentos son invalidos; 130 si se cancela con Ctrl+C.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

# No dejar __pycache__ en el arbol al ejecutar los subprocesos.
sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
STRESS = ROOT / "infrastructure" / "scripts" / "stress.py"
VERIFY_ALL = ROOT / "infrastructure" / "scripts" / "verify_all.py"

SCHEMA = "zenferros.stability-campaign/v1"
TASK = "TASK-913"
SUCCESS_STATUS = 33

# Timeouts holgados por ronda. Los valores observados en este host estan muy por
# debajo; el limite solo evita que una campana desatendida se cuelgue.
STRESS_TIMEOUT = {"quick": 900.0, "full": 1800.0}
GATE_TIMEOUT = 1800.0
GATE_EXPECTED_BOOTS = 6

STRESS_SUMMARY_LINE = re.compile(r"^\s*Resumen JSON:\s*(\S+)\s*$", re.MULTILINE)
GATE_LOGS_LINE = re.compile(r"^\s*Logs:\s*(\S+)\s*$", re.MULTILINE)
GATE_BOOT_LINE = re.compile(
    r"^(debug|release) boot (\d+): (PASS|FAIL) \(QEMU (\d+),", re.MULTILINE
)
SUITE_ROUNDS = re.compile(r"\((\d+) ronda")
UNITTEST_COUNT = re.compile(r"Ran (\d+) tests?")

PARSER_FUZZ = re.compile(
    r"^(\d+) expresiones\b.*?\((\d+) validas,\s*(\d+) con error\)", re.MULTILINE
)
LEXER_FUZZ = re.compile(
    r"^(\d+) mutaciones;\s*(\d+) comparadas,\s*(\d+) omitidas,\s*"
    r"(\d+) toleradas UTF-8",
    re.MULTILINE,
)


def format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.2f}s"
    minutes, remainder = divmod(seconds, 60)
    return f"{int(minutes)}m {remainder:04.1f}s"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def first_line(text: str, limit: int = 240) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()[:limit]
    return ""


def tail_lines(text: str, count: int = 18) -> list[str]:
    return text.splitlines()[-count:]


def campaign_environment() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.setdefault("CARGO_TERM_COLOR", "never")
    return env


# ---------------------------------------------------------------------------
# Ejecucion de subprocesos y lectura de logs
# ---------------------------------------------------------------------------


def run_logged(
    command: list[str],
    log_path: Path,
    timeout: float,
    env: dict[str, str],
) -> dict:
    """Ejecuta un comando, guarda su salida y devuelve un registro serializable."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        f"# cwd: {ROOT}\n"
        f"# $ {' '.join(command)}\n"
        f"# timeout: {timeout}s\n"
    )
    started = time.perf_counter()
    returncode: int | None = None
    timed_out = False
    error: str | None = None
    output = ""
    try:
        result = subprocess.run(
            command,
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        returncode = result.returncode
        output = result.stdout + result.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        raw_stdout = exc.stdout or ""
        raw_stderr = exc.stderr or ""
        if isinstance(raw_stdout, bytes):
            raw_stdout = raw_stdout.decode("utf-8", errors="replace")
        if isinstance(raw_stderr, bytes):
            raw_stderr = raw_stderr.decode("utf-8", errors="replace")
        output = raw_stdout + raw_stderr
        error = f"timeout tras {format_duration(timeout)}"
    except OSError as exc:
        error = f"no se pudo ejecutar: {exc}"
    elapsed = time.perf_counter() - started

    body = header
    if returncode is not None:
        body += f"# exit: {returncode}\n"
    if error is not None:
        body += f"# error: {error}\n"
    body += "\n" + output
    try:
        log_path.write_text(body, encoding="utf-8")
    except OSError as exc:  # el log no debe enmascarar el resultado del comando
        print(f"  aviso: no se pudo escribir {log_path}: {exc}", file=sys.stderr)

    return {
        "command": command,
        "exit_code": returncode,
        "timed_out": timed_out,
        "error": error,
        "seconds": round(elapsed, 3),
        "log": str(log_path),
        "output": output,
    }


def read_json(path: Path) -> tuple[object | None, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except OSError as exc:
        return None, f"no se pudo leer {path}: {exc}"
    except ValueError as exc:
        return None, f"JSON invalido en {path}: {exc}"


def public_run(record: dict, *, output_key: str | None = "output_tail") -> dict:
    """Quita la salida completa del registro; conserva una cola para el JSON."""
    result = {key: value for key, value in record.items() if key != "output"}
    if output_key is not None and not result.get("output_tail"):
        result["output_tail"] = tail_lines(record.get("output", ""), 12)
    return result


# ---------------------------------------------------------------------------
# Metricas del resumen de stress
# ---------------------------------------------------------------------------


def count_boot_logs(run_dir: Path, warnings: list[str], label: str) -> tuple[int, int]:
    """Cuenta arranques PASS leyendo los logs que stress.py ya guardo.

    Un arranque cuenta si `result.json` declara estado 33, no hubo timeout, no
    hay `stderr` de QEMU y la serial no contiene `PANIC`. Si no hay logs, se
    devuelve (0, 0) y el llamador decide si puede inferir el dato del resumen.
    """
    boot_dir = run_dir / "logs" / "boots"
    result_paths = sorted(boot_dir.glob("*/result.json"))
    if not result_paths:
        return 0, 0

    passed = 0
    for path in result_paths:
        data, error = read_json(path)
        if error is not None or not isinstance(data, dict):
            warnings.append(f"{label}: {error or 'result.json no es un objeto'}")
            continue
        if data.get("status") != SUCCESS_STATUS:
            warnings.append(
                f"{label}: {path.parent.name} con status={data.get('status')} "
                f"(esperado {SUCCESS_STATUS})"
            )
            continue
        if data.get("timed_out") or data.get("cancelled"):
            warnings.append(f"{label}: {path.parent.name} marcado timed_out/cancelled")
            continue
        stderr_path = path.parent / "qemu.stderr.log"
        if stderr_path.is_file() and stderr_path.stat().st_size:
            warnings.append(f"{label}: {path.parent.name} con stderr no vacio")
            continue
        serial_path = path.parent / "serial.log"
        if serial_path.is_file():
            try:
                if b"PANIC" in serial_path.read_bytes():
                    warnings.append(f"{label}: {path.parent.name} con PANIC en la serial")
                    continue
            except OSError as exc:
                warnings.append(f"{label}: no se pudo leer {serial_path}: {exc}")
                continue
        passed += 1
    return passed, len(result_paths)


def suite_tests(run_dir: Path, name: str, warnings: list[str], label: str) -> int | None:
    """Ultimo recuento `Ran N tests` de la suite, si stress dejo logs."""
    lower = name.lower()
    if "ferros" in lower:
        prefix = "ferros"
    elif "selfhost" in lower:
        prefix = "selfhost"
    else:
        return None
    logs = sorted((run_dir / "logs" / "suites").glob(f"{prefix}-*.log"))
    if not logs:
        return None
    try:
        text = logs[-1].read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        warnings.append(f"{label}: no se pudo leer {logs[-1]}: {exc}")
        return None
    matches = UNITTEST_COUNT.findall(text)
    return int(matches[-1]) if matches else None


def extract_metrics(
    summary: object,
    summary_path: Path,
    warnings: list[str],
    label: str,
) -> dict:
    """Extrae boots PASS, suites y fuzz del summary JSON de stress."""
    if not isinstance(summary, dict):
        raise ValueError("el summary de stress no es un objeto JSON")
    phases = summary.get("phases")
    if not isinstance(phases, list):
        warnings.append(f"{label}: summary sin lista 'phases'")
        phases = []

    metrics: dict = {
        "result": summary.get("result"),
        "boots_pass": 0,
        "boots_total": int(summary.get("boots") or 0),
        "suites": [],
        "suites_pass": 0,
        "suites_total": 0,
        "fuzz": {"parser": None, "lexer": None},
    }

    boot_phase = next(
        (phase for phase in phases
         if str(phase.get("name", "")).startswith("Arranques QEMU")),
        None,
    )
    boot_pass, boot_count = count_boot_logs(summary_path.parent, warnings, label)
    if boot_count:
        metrics["boots_pass"] = boot_pass
        metrics["boots_total"] = metrics["boots_total"] or boot_count
        if metrics["boots_total"] != boot_count:
            warnings.append(
                f"{label}: summary declara {metrics['boots_total']} arranques "
                f"pero hay {boot_count} logs"
            )
    elif isinstance(boot_phase, dict) and boot_phase.get("status") == "PASS":
        metrics["boots_pass"] = metrics["boots_total"]
        warnings.append(
            f"{label}: sin logs de arranque; boots PASS inferidos del summary"
        )
    else:
        warnings.append(f"{label}: no se pudieron contar los arranques QEMU")

    for phase in phases:
        if not isinstance(phase, dict):
            continue
        name = str(phase.get("name", ""))
        if not name.startswith("Suite "):
            continue
        match = SUITE_ROUNDS.search(name)
        entry = {
            "name": name,
            "status": phase.get("status", "UNKNOWN"),
            "rounds": int(match.group(1)) if match else None,
            "tests": suite_tests(summary_path.parent, name, warnings, label),
        }
        metrics["suites"].append(entry)
        metrics["suites_total"] += 1
        if entry["status"] == "PASS":
            metrics["suites_pass"] += 1

    for phase in phases:
        if not isinstance(phase, dict):
            continue
        name = str(phase.get("name", ""))
        detail = str(phase.get("detail", ""))
        if name.startswith("Fuzz diferencial del parser"):
            match = PARSER_FUZZ.search(detail)
            if match:
                metrics["fuzz"]["parser"] = {
                    "status": phase.get("status", "UNKNOWN"),
                    "cases": int(match.group(1)),
                    "valid": int(match.group(2)),
                    "errors": int(match.group(3)),
                }
            else:
                metrics["fuzz"]["parser"] = {
                    "status": phase.get("status", "UNKNOWN"),
                    "cases": None,
                    "valid": None,
                    "errors": None,
                }
                warnings.append(f"{label}: no se pudieron leer las metricas del fuzz parser")
        elif name.startswith("Fuzz diferencial del lexer"):
            match = LEXER_FUZZ.search(detail)
            if match:
                metrics["fuzz"]["lexer"] = {
                    "status": phase.get("status", "UNKNOWN"),
                    "cases": int(match.group(1)),
                    "compared": int(match.group(2)),
                    "skipped": int(match.group(3)),
                    "tolerated": int(match.group(4)),
                }
            else:
                metrics["fuzz"]["lexer"] = {
                    "status": phase.get("status", "UNKNOWN"),
                    "cases": None,
                    "compared": None,
                    "skipped": None,
                    "tolerated": None,
                }
                warnings.append(f"{label}: no se pudieron leer las metricas del fuzz lexer")
    return metrics


def failed_phase_error(summary: object) -> str:
    if not isinstance(summary, dict):
        return ""
    for phase in summary.get("phases") or []:
        if isinstance(phase, dict) and phase.get("status") == "FAIL":
            return f"{phase.get('name')}: {first_line(str(phase.get('detail', '')))}"
    return ""


# ---------------------------------------------------------------------------
# Verificacion del gate full
# ---------------------------------------------------------------------------


def gate_boot_log(run_dir: Path) -> Path | None:
    """Localiza el log del paso 5 de la puerta (`05-ferros.log`)."""
    candidate = run_dir / "05-ferros.log"
    if candidate.is_file():
        return candidate
    matches = sorted(run_dir.glob("05-*.log"))
    return matches[0] if matches else None


def count_gate_boots(log_path: Path) -> tuple[int, int]:
    """Cuenta lineas `debug|release boot N: PASS (QEMU 33, ...)` del log."""
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0, 0
    seen: dict[tuple[str, int], str] = {}
    total = 0
    for profile, index, status, qemu_status in GATE_BOOT_LINE.findall(text):
        total += 1
        seen[(profile, int(index))] = status if qemu_status == str(SUCCESS_STATUS) else "FAIL"
    passed = sum(1 for status in seen.values() if status == "PASS")
    return passed, max(total, len(seen))


def verify_gate(
    gate_run: dict,
    gate_started_wall: float,
    warnings: list[str],
    label: str,
) -> dict:
    """Verifica 6/6 arranques con estado 33 a partir de la salida del gate."""
    output = gate_run.get("output", "")
    logs_match = GATE_LOGS_LINE.findall(output)
    gate_dir = Path(logs_match[-1]) if logs_match else None
    log_path = gate_boot_log(gate_dir) if gate_dir is not None else None

    passed = total = 0
    source = "sin verificar"
    if log_path is not None:
        passed, total = count_gate_boots(log_path)
        source = f"gate-log:{log_path.name}"
        if total != GATE_EXPECTED_BOOTS:
            warnings.append(
                f"{label}: el log del gate tiene {total} lineas de arranque "
                f"(esperadas {GATE_EXPECTED_BOOTS})"
            )
    else:
        warnings.append(f"{label}: no se encontro el log del paso QEMU del gate")

    # Respaldo: boot_ferros.py deja ferros/build/boot-results.json. Solo se usa
    # si es fresco (posterior al inicio del gate), para no aceptar un resultado
    # de una ejecucion anterior.
    if passed != GATE_EXPECTED_BOOTS:
        fallback = ROOT / "ferros" / "build" / "boot-results.json"
        try:
            fresh = fallback.is_file() and fallback.stat().st_mtime >= gate_started_wall - 2
        except OSError:
            fresh = False
        if fresh:
            data, error = read_json(fallback)
            if error is None and isinstance(data, list):
                fresh_passed = sum(
                    1 for item in data
                    if isinstance(item, dict)
                    and item.get("status") == SUCCESS_STATUS
                    and not item.get("timed_out")
                )
                if len(data) == GATE_EXPECTED_BOOTS and fresh_passed == GATE_EXPECTED_BOOTS:
                    passed, total = fresh_passed, len(data)
                    source = "boot-results.json"
                    warnings.append(
                        f"{label}: 6/6 verificado con boot-results.json; "
                        "no se pudo leer el log del gate"
                    )

    status = "PASS"
    error = None
    if gate_run.get("timed_out"):
        status = "FAIL"
        error = gate_run.get("error") or "gate con timeout"
    elif gate_run.get("error"):
        status = "FAIL"
        error = gate_run["error"]
    elif gate_run.get("exit_code") != 0:
        status = "FAIL"
        error = f"gate salio con {gate_run.get('exit_code')}"
    elif passed != GATE_EXPECTED_BOOTS or total != GATE_EXPECTED_BOOTS:
        status = "FAIL"
        error = (
            f"gate no verifico {GATE_EXPECTED_BOOTS}/{GATE_EXPECTED_BOOTS} "
            f"arranques con estado {SUCCESS_STATUS} (vistos {passed}/{total})"
        )
    if error is not None:
        warnings.append(f"{label}: {error}")

    record = public_run(gate_run)
    record.update(
        status=status,
        run_dir=str(gate_dir) if gate_dir is not None else None,
        boot_log=str(log_path) if log_path is not None else None,
        boots_pass=passed,
        boots_total=GATE_EXPECTED_BOOTS,
        source=source,
    )
    if error is not None:
        record["error"] = error
    return record


# ---------------------------------------------------------------------------
# Rondas
# ---------------------------------------------------------------------------


def evaluate_stress(
    stress_run: dict,
    warnings: list[str],
    label: str,
) -> tuple[dict, dict | None, list[str]]:
    """Evalua una ejecucion de stress y devuelve (registro, metricas, errores)."""
    errors: list[str] = []
    if stress_run.get("timed_out"):
        errors.append(stress_run.get("error") or "stress con timeout")
    elif stress_run.get("exit_code") != 0:
        errors.append(f"stress salio con {stress_run.get('exit_code')}")

    summary: object | None = None
    summary_path: Path | None = None
    match = STRESS_SUMMARY_LINE.findall(stress_run.get("output", ""))
    if match:
        summary_path = Path(match[-1])
        if summary_path.is_file():
            summary, error = read_json(summary_path)
            if error is not None:
                warnings.append(f"{label}: {error}")
            elif isinstance(summary, dict) and summary.get("result") != "PASS":
                errors.append("el summary de stress declara result=" + str(summary.get("result")))
        else:
            warnings.append(f"{label}: stress anuncio {summary_path} pero no existe")
    else:
        warnings.append(f"{label}: stress no anuncio la ruta de su summary JSON")

    metrics: dict | None = None
    if summary is not None and summary_path is not None:
        try:
            metrics = extract_metrics(summary, summary_path, warnings, label)
        except ValueError as exc:
            warnings.append(f"{label}: {exc}")
        else:
            if metrics["boots_total"] and metrics["boots_pass"] != metrics["boots_total"]:
                errors.append(
                    f"stress: {metrics['boots_pass']}/{metrics['boots_total']} "
                    "arranques QEMU PASS"
                )
            if metrics["suites_total"] and metrics["suites_pass"] != metrics["suites_total"]:
                errors.append(
                    f"stress: {metrics['suites_pass']}/{metrics['suites_total']} suites PASS"
                )

    if errors and failed_phase_error(summary):
        errors.append(f"fase fallida: {failed_phase_error(summary)}")
    elif errors:
        detail = first_line(stress_run.get("output", ""))
        if detail:
            errors.append(detail)

    record = public_run(stress_run)
    record.update(
        status="FAIL" if errors else "PASS",
        summary_path=str(summary_path) if summary_path is not None else None,
        metrics=metrics,
    )
    if errors:
        record["error"] = "; ".join(dict.fromkeys(errors))
    return record, metrics, errors


def run_round(
    number: int,
    total: int,
    mode: str,
    run_dir: Path,
    env: dict[str, str],
    warnings: list[str],
) -> dict:
    label = f"ronda {number}"
    print(f"\n== Ronda {number}/{total} ==", flush=True)
    started = time.perf_counter()

    stress_command = [sys.executable, "-B", str(STRESS)]
    if mode == "quick":
        stress_command.append("--quick")
    print(f"  $ {' '.join(stress_command)}", flush=True)
    stress_run = run_logged(
        stress_command,
        run_dir / "logs" / f"round-{number:02}-stress.log",
        STRESS_TIMEOUT[mode],
        env,
    )
    stress_record, metrics, errors = evaluate_stress(
        stress_run, warnings, label
    )
    status_text = "PASS" if stress_record["status"] == "PASS" else "FAIL"
    print(
        f"  stress ({mode}): {status_text} "
        f"({format_duration(stress_run['seconds'])}, exit {stress_run['exit_code']})",
        flush=True,
    )
    if metrics is not None:
        parser = metrics["fuzz"].get("parser") or {}
        lexer = metrics["fuzz"].get("lexer") or {}
        print(
            f"  metricas: boots {metrics['boots_pass']}/{metrics['boots_total']}, "
            f"suites {metrics['suites_pass']}/{metrics['suites_total']}, "
            f"fuzz parser {parser.get('cases', '-')} "
            f"({parser.get('valid', '-')}/{parser.get('errors', '-')}), "
            f"lexer {lexer.get('cases', '-')} "
            f"({lexer.get('compared', '-')} comparadas, "
            f"{lexer.get('skipped', '-')} omitidas, "
            f"{lexer.get('tolerated', '-')} toleradas)",
            flush=True,
        )

    gate_record: dict | None = None
    if mode == "full" and not errors:
        gate_command = [sys.executable, "-B", str(VERIFY_ALL), "--full"]
        print(f"  $ {' '.join(gate_command)}", flush=True)
        gate_started_wall = time.time()
        gate_run = run_logged(
            gate_command,
            run_dir / "logs" / f"round-{number:02}-gate.log",
            GATE_TIMEOUT,
            env,
        )
        gate_record = verify_gate(
            gate_run, gate_started_wall, warnings, label
        )
        gate_status = "PASS" if gate_record["status"] == "PASS" else "FAIL"
        print(
            f"  gate --full: {gate_status} "
            f"({format_duration(gate_run['seconds'])}, exit {gate_run['exit_code']}); "
            f"QEMU {gate_record['boots_pass']}/{gate_record['boots_total']} "
            f"estado {SUCCESS_STATUS} ({gate_record['source']})",
            flush=True,
        )
        if gate_record["status"] != "PASS":
            errors.append(gate_record.get("error") or "gate full fallo")
    elif mode == "full":
        print("  gate --full: SKIP (fallo previo en stress)", flush=True)

    seconds = time.perf_counter() - started
    record = {
        "round": number,
        "status": "PASS" if not errors else "FAIL",
        "seconds": round(seconds, 3),
        "stress": stress_record,
        "gate": gate_record,
        "error": None if not errors else "; ".join(dict.fromkeys(errors)),
    }

    if record["status"] == "PASS":
        print(f"  Ronda {number}: PASS ({format_duration(seconds)})", flush=True)
    else:
        print(f"  Ronda {number}: FAIL ({format_duration(seconds)})", flush=True)
        for source in (stress_record, gate_record):
            if not source:
                continue
            tail = source.get("output_tail") or []
            if tail:
                print("  cola de salida:", flush=True)
                for line in tail:
                    print(f"    {line}", flush=True)
        print(f"  detalle: {record['error']}", flush=True)
        warnings.append(
            f"{label} fallo; campana detenida en la primera ronda fallida"
        )
    return record


# ---------------------------------------------------------------------------
# Totales y resumen
# ---------------------------------------------------------------------------


def build_totals(results: list[dict], seconds: float) -> dict:
    totals = {
        "rounds_executed": len(results),
        "rounds_passed": sum(1 for item in results if item["status"] == "PASS"),
        "rounds_failed": sum(1 for item in results if item["status"] == "FAIL"),
        "seconds": round(seconds, 3),
        "stress_seconds": round(
            sum(item["stress"]["seconds"] for item in results), 3
        ),
        "gate_seconds": round(
            sum(item["gate"]["seconds"] for item in results if item.get("gate")), 3
        ),
        "stress": {
            "boots_pass": 0,
            "boots_total": 0,
            "suites_pass": 0,
            "suites_total": 0,
            "fuzz": {
                "parser_cases": 0,
                "parser_valid": 0,
                "parser_errors": 0,
                "lexer_cases": 0,
                "lexer_compared": 0,
                "lexer_skipped": 0,
                "lexer_tolerated": 0,
            },
        },
        "gate": {"boots_pass": 0, "boots_total": 0},
    }
    fuzz = totals["stress"]["fuzz"]
    for item in results:
        metrics = item["stress"].get("metrics")
        if metrics:
            totals["stress"]["boots_pass"] += metrics.get("boots_pass") or 0
            totals["stress"]["boots_total"] += metrics.get("boots_total") or 0
            totals["stress"]["suites_pass"] += metrics.get("suites_pass") or 0
            totals["stress"]["suites_total"] += metrics.get("suites_total") or 0
            parser = (metrics.get("fuzz") or {}).get("parser") or {}
            lexer = (metrics.get("fuzz") or {}).get("lexer") or {}
            fuzz["parser_cases"] += parser.get("cases") or 0
            fuzz["parser_valid"] += parser.get("valid") or 0
            fuzz["parser_errors"] += parser.get("errors") or 0
            fuzz["lexer_cases"] += lexer.get("cases") or 0
            fuzz["lexer_compared"] += lexer.get("compared") or 0
            fuzz["lexer_skipped"] += lexer.get("skipped") or 0
            fuzz["lexer_tolerated"] += lexer.get("tolerated") or 0
        gate = item.get("gate")
        if gate:
            totals["gate"]["boots_pass"] += gate.get("boots_pass") or 0
            totals["gate"]["boots_total"] += gate.get("boots_total") or 0
    return totals


def print_summary(
    results: list[dict],
    totals: dict,
    mode: str,
    run_dir: Path,
    json_path: Path | None,
    warnings: list[str],
    interrupted: bool = False,
) -> None:
    print("\n" + "=" * 112)
    print(f"Resumen de la campana de estabilidad ({TASK})")
    print("=" * 112)
    print(
        f"  {'Ronda':<6} {'Estado':<7} {'Duracion':>9} {'Stress':>9} "
        f"{'Gate':>9} {'Boots estres':>13} {'Boots gate':>11} "
        f"{'Suites':>7} {'Fuzz P/L':>10}"
    )
    for item in results:
        stress = item["stress"]
        metrics = stress.get("metrics") or {}
        gate = item.get("gate")
        parser = ((metrics.get("fuzz") or {}).get("parser") or {}).get("cases")
        lexer = ((metrics.get("fuzz") or {}).get("lexer") or {}).get("cases")
        boots = (
            f"{metrics.get('boots_pass', '-')}/{metrics.get('boots_total', '-')}"
            if metrics else "-"
        )
        suites = (
            f"{metrics.get('suites_pass', '-')}/{metrics.get('suites_total', '-')}"
            if metrics else "-"
        )
        fuzz = f"{parser if parser is not None else '-'}/{lexer if lexer is not None else '-'}"
        gate_time = format_duration(gate["seconds"]) if gate else "-"
        gate_boots = (
            f"{gate.get('boots_pass', '-')}/{gate.get('boots_total', '-')}"
            if gate else "-"
        )
        print(
            f"  {item['round']:<6} {item['status']:<7} "
            f"{format_duration(item['seconds']):>9} "
            f"{format_duration(stress['seconds']):>9} {gate_time:>9} "
            f"{boots:>13} {gate_boots:>11} {suites:>7} {fuzz:>10}"
        )
    print("-" * 112)
    print(
        f"  Rondas: {totals['rounds_passed']}/{totals['rounds_executed']} PASS "
        f"({totals['rounds_failed']} fallidas) · "
        f"total {format_duration(totals['seconds'])} "
        f"(stress {format_duration(totals['stress_seconds'])}, "
        f"gate {format_duration(totals['gate_seconds'])})"
    )
    stress_totals = totals["stress"]
    print(
        f"  QEMU: stress {stress_totals['boots_pass']}/{stress_totals['boots_total']} · "
        f"gate {totals['gate']['boots_pass']}/{totals['gate']['boots_total']} · "
        f"suites {stress_totals['suites_pass']}/{stress_totals['suites_total']}"
    )
    fuzz = stress_totals["fuzz"]
    print(
        f"  Fuzz: parser {fuzz['parser_cases']} casos "
        f"({fuzz['parser_valid']} validos, {fuzz['parser_errors']} con error) · "
        f"lexer {fuzz['lexer_cases']} casos "
        f"({fuzz['lexer_compared']} comparadas, {fuzz['lexer_skipped']} omitidas, "
        f"{fuzz['lexer_tolerated']} toleradas UTF-8)"
    )
    print(f"  Modo: {mode}")
    print(f"  Logs: {run_dir}")
    if json_path is not None:
        print(f"  JSON: {json_path}")
    if warnings:
        print(f"  Avisos ({len(warnings)}):")
        for warning in warnings:
            print(f"    - {warning}")
    if interrupted:
        outcome = "CANCELADO"
    else:
        outcome = "FALLO" if totals["rounds_failed"] else "PASS"
    print(f"  Resultado: {outcome}")


def write_json(path: Path, document: dict) -> str | None:
    """Escribe el resumen de forma atomica; devuelve un error o None."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(
            json.dumps(document, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
        return None
    except OSError as exc:
        return f"no se pudo escribir {path}: {exc}"


# ---------------------------------------------------------------------------
# Entrada
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Campana de estabilidad repetida de Zen/Ferros: N rondas de stress "
            "y, en full, la puerta completa con 6 arranques QEMU (TASK-913)."
        ),
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=5,
        help="numero de rondas (por defecto 5)",
    )
    parser.add_argument(
        "--mode",
        choices=("quick", "full"),
        default="quick",
        help=(
            "quick: stress --quick por ronda; full: stress completo + "
            "verify_all --full (6 arranques QEMU) por ronda"
        ),
    )
    parser.add_argument(
        "--json",
        type=Path,
        default=None,
        metavar="RUTA",
        help="ruta opcional donde copiar el resumen JSON",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.rounds < 1:
        print("error: --rounds debe ser >= 1", file=sys.stderr)
        return 2
    if not STRESS.is_file() or not VERIFY_ALL.is_file():
        print(
            f"error: faltan {STRESS} o {VERIFY_ALL}; ejecuta desde el repositorio",
            file=sys.stderr,
        )
        return 2

    try:
        run_dir = Path(tempfile.mkdtemp(prefix="zenferros-campaign-"))
    except OSError as exc:
        print(f"error: no se pudo crear el directorio temporal: {exc}", file=sys.stderr)
        return 1

    env = campaign_environment()
    started_at = utc_now()
    started = time.perf_counter()
    warnings: list[str] = []
    results: list[dict] = []
    interrupted = False

    print("ZenFerros - campana de estabilidad repetida (TASK-913)")
    print(f"  repo: {ROOT}")
    print(
        f"  modo: {args.mode} · rondas: {args.rounds} · "
        f"parada al primer fallo: si"
    )
    print(f"  logs: {run_dir}")
    print("  (artefactos solo en el directorio temporal; no se escribe en el repo)")
    print(
        "  limites: QEMU TCG, host compartido, semilla fija de stress, "
        "sin inyeccion de fallos"
    )

    try:
        for number in range(1, args.rounds + 1):
            record = run_round(
                number, args.rounds, args.mode, run_dir, env, warnings
            )
            results.append(record)
            if record["status"] != "PASS":
                break
    except KeyboardInterrupt:
        interrupted = True
        warnings.append("campana cancelada por el usuario; resumen parcial")

    totals = build_totals(results, time.perf_counter() - started)
    document = {
        "schema": SCHEMA,
        "task": TASK,
        "mode": args.mode,
        "rounds": args.rounds,
        "stop_on_failure": True,
        "started_at": started_at,
        "ended_at": utc_now(),
        "total_seconds": totals["seconds"],
        "interrupted": interrupted,
        "host": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "node": platform.node(),
        },
        "config": {
            "stress_timeout_seconds": STRESS_TIMEOUT[args.mode],
            "gate_timeout_seconds": GATE_TIMEOUT if args.mode == "full" else None,
            "gate_expected_boots": GATE_EXPECTED_BOOTS if args.mode == "full" else None,
            "qemu_success_status": SUCCESS_STATUS,
        },
        "results": results,
        "totals": totals,
        "warnings": warnings,
    }

    json_errors: list[str] = []
    default_json = run_dir / "summary.json"
    error = write_json(default_json, document)
    if error is not None:
        warnings.append(error)
        json_errors.append(error)
    requested_json: Path | None = args.json
    if requested_json is not None:
        requested_json = requested_json.expanduser()
        if not requested_json.is_absolute():
            requested_json = (Path.cwd() / requested_json).resolve()
        if requested_json != default_json:
            error = write_json(requested_json, document)
            if error is not None:
                print(f"error: {error}", file=sys.stderr)
                json_errors.append(error)
                requested_json = None
    else:
        requested_json = None

    print_summary(
        results,
        totals,
        args.mode,
        run_dir,
        requested_json or default_json,
        warnings,
        interrupted,
    )
    if json_errors:
        print(
            f"error: el resumen JSON no se pudo guardar: {json_errors[-1]}",
            file=sys.stderr,
        )
        return 1
    if interrupted:
        return 130
    return 1 if totals["rounds_failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
