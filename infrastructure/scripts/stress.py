#!/usr/bin/env python3
"""TASK-905: evidencia de estabilidad acotada para Zen/Ferros.

Este script no sustituye a `verify_all.py`: repite la regresion funcional con
varios perfiles y guiones de arranque, ejecuta las suites varias veces y hace
fuzzing diferencial acotado de los componentes self-hosted.

Fases (secuenciales; nunca hay dos QEMU en paralelo):
  1. Build del kernel Ferros en debug y release, en un directorio temporal.
  2. `--boots` arranques QEMU alternando ambos perfiles y tres guiones:
     default (DEFAULT_INPUT), sin entrada (`input=None`) y comandos invalidos.
  3. Repeticion de la suite de Ferros (`--rounds`, 2 por defecto) y de la suite
     de self-hosting (2 rondas; 1 con --quick).
  4. Fuzzing diferencial del evaluador self-hosted contra la referencia Python
     de `test_selfhost_parser.py` (importada por ruta con importlib).
  5. Fuzzing diferencial del lexer self-hosted contra `zen lex`, mutando bytes
     de fixtures canonicos; las fuentes que `zen lex` rechaza se omiten.

La referencia y las fixtures se importan de los tests existentes para no
duplicar su gramatica ni sus tablas. `--quick` reduce la campana a 2 boots,
1 ronda y 20 casos por fuzz (objetivo: menos de 60 s).

Los logs y el resumen JSON se escriben solo bajo un directorio temporal
(`/tmp/zenferros-stress-*`); el script no crea artefactos en el repositorio.
Sale con codigo distinto de cero en el primer fallo.

Uso:
    python3 infrastructure/scripts/stress.py --quick
    python3 infrastructure/scripts/stress.py
    python3 infrastructure/scripts/stress.py --boots 3 --rounds 1 --fuzz-cases 50
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# No dejar __pycache__ en el arbol al importar los tests como librerias.
sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "infrastructure" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_ferros import build_kernel  # noqa: E402
from boot_ferros import (  # noqa: E402
    DEFAULT_INPUT,
    SHELL_DONE,
    SHELL_READY,
    SUCCESS_STATUS,
    boot,
    qemu_environment,
)

ZEN = ROOT / "zen/compiler/target/release/zen"
PARSER_SOURCE = ROOT / "zen/selfhost/parser.zen"
PARSER_DRIVER = ROOT / "zen/selfhost/parser_driver.c"
LEXER_SOURCE = ROOT / "zen/selfhost/lexer.zen"
LEXER_DRIVER = ROOT / "zen/selfhost/lexer_driver.c"
PARSER_TEST = ROOT / "zen/selfhost/tests/test_selfhost_parser.py"
LEXER_TEST = ROOT / "zen/selfhost/tests/test_selfhost_lexer.py"
FERROS_TESTS = "ferros/tests"
SELFHOST_TESTS = "zen/selfhost/tests"

INVALID_INPUT = b"bogus\ncat nope.zen\nexit\n"
DEFAULT_SEED = 905

BOOT_SCRIPTS = (
    ("default", DEFAULT_INPUT),
    ("sin-entrada", None),
    ("comandos-invalidos", INVALID_INPUT),
)

# Caracteres ASCII que se usan para mutar fuentes sin introducir NUL.
ASCII_MUTATION_BYTES = (
    b"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    b"_+-*/%<>=!&|^~?:;,.()[]{} \t\n\\\"'"
)
UTF8_MUTATION_CHARS = (b"\xc3\xa9", b"\xe2\x98\x95", b"\xce\xa9")  # é, ☕, Ω
# Spans lexicos donde una mutacion UTF-8 sigue siendo valida para `zen lex`.
SPAN_PATTERN = re.compile(
    rb'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
    re.DOTALL,
)
UTF8_CHAR_FIXTURE = "fn stress_utf8_char() { let c = 'é'; }\n".encode("utf-8")
UTF8_COMMENT_FIXTURE = b"// stress utf8: caf\xc3\xa9 \xe2\x98\x95\n"


class StressFailure(RuntimeError):
    """Fallo de una fase: el script para y devuelve exit != 0."""


def format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.2f}s"
    minutes, remainder = divmod(seconds, 60)
    return f"{int(minutes)}m {remainder:04.1f}s"


def run_logged(
    command: list[str],
    log_path: Path,
    timeout: float,
    *,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> tuple[subprocess.CompletedProcess[str], float]:
    """Ejecuta un comando con timeout, guarda su log y falla con contexto."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    header = f"# cwd: {cwd}\n# $ {' '.join(command)}\n# timeout: {timeout}s\n"
    started = time.perf_counter()
    result: subprocess.CompletedProcess[str] | None = None
    error: str | None = None
    try:
        result = subprocess.run(
            command,
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") + (exc.stderr or "")
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        error = f"timeout tras {format_duration(timeout)}: {' '.join(command)}"
    except OSError as exc:
        output = ""
        error = f"no se pudo ejecutar {' '.join(command)}: {exc}"
    elapsed = time.perf_counter() - started
    body = header
    if result is not None:
        body += f"# exit: {result.returncode}\n\n{result.stdout}{result.stderr}"
    else:
        body += f"# error: {error}\n\n{output}"
    log_path.write_text(body, encoding="utf-8")
    if error is not None:
        raise StressFailure(f"{error}; log: {log_path}")
    assert result is not None
    if check and result.returncode != 0:
        tail = "\n".join((result.stdout + result.stderr).splitlines()[-25:])
        raise StressFailure(
            f"`{' '.join(command)}` salio con {result.returncode}; "
            f"log: {log_path}\n{tail}"
        )
    return result, elapsed


def load_module(path: Path, name: str):
    if not path.is_file():
        raise StressFailure(f"falta {path}; no se puede importar la referencia de los tests")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise StressFailure(f"no se pudo cargar {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as error:  # noqa: BLE001 - se reporta como fallo de fase
        raise StressFailure(f"error importando {path}: {error}") from error
    return module


def load_parser_reference():
    """Importa `test_selfhost_parser.reference` sin duplicar su gramatica.

    El test expone `reference(expression) -> (status, value)` y la clase
    `ReferenceParser`. Se prefiere la funcion; si solo quedara la clase se usa
    su `parse()`. Si no quedara ninguna de las dos, el script falla en vez de
    inventar una semantica distinta.
    """
    module = load_module(PARSER_TEST, "zenferros_stress_reference_parser")
    reference = getattr(module, "reference", None)
    if callable(reference):
        return reference
    # La API preferida es reference(text). Si solo estuviera la clase, se usa
    # su metodo parse() sin copiar la gramatica en este script.
    parser_class = getattr(module, "ReferenceParser", None)
    if parser_class is not None:
        print("  aviso: test_selfhost_parser no expone reference(); uso ReferenceParser.parse()")
        return lambda text: parser_class(text).parse()
    raise StressFailure(
        f"{PARSER_TEST} no expone reference() ni ReferenceParser; actualiza el fuzzer"
    )


def load_lexer_reference():
    """Importa fixtures y utilidades de conteo de `test_selfhost_lexer.py`."""
    module = load_module(LEXER_TEST, "zenferros_stress_reference_lexer")
    for attribute in ("FIXTURES", "SYNTHETIC", "COUNTERS", "TOKEN_LINE", "categorize"):
        if not hasattr(module, attribute):
            raise StressFailure(f"{LEXER_TEST} no expone {attribute}; actualiza el fuzzer")
    return module


def build_driver(source: Path, driver_source: Path, work: Path, name: str) -> Path:
    """Compila un componente Zen a objeto y lo enlaza con su driver C."""
    work.mkdir(parents=True, exist_ok=True)
    obj = work / f"{name}.o"
    executable = work / f"{name}_driver"
    run_logged(
        [str(ZEN), "build", str(source), "--target", "x86_64-unknown-none",
         "--emit", "obj", "-o", str(obj)],
        work / f"{name}-zen-build.log",
        180,
    )
    cc = os.environ.get("CC", "cc")
    run_logged(
        [cc, "-std=c11", "-O2", "-fno-pie", "-no-pie",
         str(driver_source), str(obj), "-o", str(executable)],
        work / f"{name}-cc.log",
        180,
    )
    return executable


def phase_builds(args: argparse.Namespace, run_dir: Path, context: dict) -> str:
    if not ZEN.is_file():
        raise StressFailure(
            f"falta el compilador {ZEN}; construyelo con: "
            'CARGO_HOME="$PWD/.cargo" cargo build --release --offline '
            "--manifest-path zen/compiler/Cargo.toml"
        )
    try:
        executable, env, _ = qemu_environment(args.qemu)
        version = subprocess.check_output(
            [executable, "--version"], env=env, text=True, timeout=10
        ).splitlines()[0]
    except (OSError, subprocess.SubprocessError, IndexError, RuntimeError) as error:
        raise StressFailure(f"QEMU no disponible: {error}") from error
    print(f"  QEMU: {version}")

    builds: dict[bool, dict] = {}
    for release in (False, True):
        profile = "release" if release else "debug"
        output = run_dir / "build" / profile
        started = time.perf_counter()
        try:
            build = build_kernel(ZEN, output, release)
        except Exception as error:  # noqa: BLE001 - build_kernel lanza tipos variados
            raise StressFailure(f"build {profile} fallo: {error}") from error
        elapsed = time.perf_counter() - started
        builds[release] = build
        print(f"  build {profile}: PASS ({format_duration(elapsed)}) -> {build['image_path']}")
    context["builds"] = builds
    return "debug+release en " + str(run_dir / "build")


def check_boot(
    index: int,
    total: int,
    script_name: str,
    profile: str,
    output: Path,
    runner_error: str | None,
) -> dict:
    """Valida un arranque; el runner no acepta los guiones no-default, asi que
    se comprueban sus propiedades directamente sobre los logs guardados."""
    result_path = output / "result.json"
    serial_path = output / "serial.log"
    stderr_path = output / "qemu.stderr.log"
    if not result_path.is_file() or not serial_path.is_file():
        raise StressFailure(
            f"boot {index}/{total} ({profile} {script_name}): sin logs en {output}; "
            f"runner: {runner_error or 'sin error'}"
        )
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise StressFailure(f"boot {index}: result.json ilegible en {output}: {error}") from error
    serial = serial_path.read_bytes()
    stderr = stderr_path.read_bytes() if stderr_path.is_file() else b""

    problems: list[str] = []
    if result.get("status") != SUCCESS_STATUS:
        problems.append(f"status={result.get('status')} (esperado {SUCCESS_STATUS})")
    if result.get("timed_out"):
        problems.append("timed_out")
    if stderr:
        problems.append(f"stderr={stderr[:120]!r}")
    if b"PANIC" in serial:
        problems.append("PANIC en la serial")

    if script_name == "default":
        if runner_error is not None:
            problems.append(f"el runner rechazo el guion default: {runner_error}")
        if not result.get("passed"):
            problems.append("result.passed=false")
        userspace = result.get("userspace") or {}
        if userspace.get("writes") != 18:
            problems.append(f"writes={userspace.get('writes')} (esperado 18)")
        if SHELL_READY not in serial or SHELL_DONE not in serial:
            problems.append("faltan marcadores SHELL: READY/DONE")
    elif script_name == "sin-entrada":
        if SHELL_READY not in serial:
            problems.append("falta SHELL: READY")
        if b"SHELL: NO INPUT" not in serial:
            problems.append("falta SHELL: NO INPUT")
        if SHELL_DONE not in serial:
            problems.append("falta SHELL: DONE")
        if b"SHELL: UNKNOWN COMMAND" in serial:
            problems.append("aparece UNKNOWN COMMAND en el guion sin entrada")
    elif script_name == "comandos-invalidos":
        if SHELL_READY not in serial:
            problems.append("falta SHELL: READY")
        if b"SHELL: UNKNOWN COMMAND" not in serial:
            problems.append("falta SHELL: UNKNOWN COMMAND")
        if b"SHELL: FILE ERROR" not in serial:
            problems.append("falta SHELL: FILE ERROR")
        if SHELL_DONE not in serial:
            problems.append("falta SHELL: DONE")
        if b"SHELL: NO INPUT" in serial:
            problems.append("aparece NO INPUT en el guion de comandos invalidos")
    else:  # pragma: no cover - defensa ante una tabla futura mal editada
        problems.append(f"guion desconocido: {script_name}")

    if problems:
        tail = "\n".join(serial.decode("utf-8", errors="replace").splitlines()[-18:])
        raise StressFailure(
            f"boot {index}/{total} ({profile} {script_name}) fallo: "
            f"{'; '.join(problems)}; logs: {output}\n--- serial (cola) ---\n{tail}"
        )
    return result


def phase_boots(args: argparse.Namespace, run_dir: Path, context: dict) -> str:
    builds = context["builds"]
    boot_root = run_dir / "logs" / "boots"
    for index in range(args.boots):
        release = bool(index % 2)  # 0 -> debug, 1 -> release, ...
        profile = "release" if release else "debug"
        script_name, payload = BOOT_SCRIPTS[index % len(BOOT_SCRIPTS)]
        output = boot_root / f"boot-{index + 1:02}-{profile}-{script_name}"
        started = time.perf_counter()
        runner_error: str | None = None
        try:
            boot(
                builds[release]["image_path"],
                output,
                timeout=args.boot_timeout,
                qemu=args.qemu,
                input=payload,
            )
        except RuntimeError as error:
            # Esperado en los guiones no-default: validate_boot exige la
            # transcripcion canonica. Los logs ya estan guardados.
            runner_error = str(error)
        except Exception as error:  # noqa: BLE001 - un fallo inesperado no se enmascara
            raise StressFailure(
                f"boot {index + 1}/{args.boots} ({profile} {script_name}) "
                f"excepcion inesperada: {type(error).__name__}: {error}"
            ) from error
        elapsed = time.perf_counter() - started
        result = check_boot(index + 1, args.boots, script_name, profile, output, runner_error)
        userspace = result.get("userspace") or {}
        counters = ""
        if userspace:
            counters = (
                f", runs={userspace.get('runs')} writes={userspace.get('writes')} "
                f"rejected={userspace.get('rejected')}"
            )
        print(
            f"  [{index + 1}/{args.boots}] {profile:<7} {script_name:<18} "
            f"PASS ({format_duration(elapsed)}, status={result.get('status')}{counters})"
        )
    return (
        f"{args.boots} arranques; perfiles debug/release; guiones "
        f"default, sin-entrada y comandos-invalidos; logs: {boot_root}"
    )


def suite_environment() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.setdefault("CARGO_TERM_COLOR", "never")
    return env


def run_suite(
    name: str,
    directory: str,
    rounds: int,
    timeout: float,
    run_dir: Path,
) -> str:
    env = suite_environment()
    for round_index in range(1, rounds + 1):
        log_path = run_dir / "logs" / "suites" / f"{name}-{round_index:02}.log"
        result, elapsed = run_logged(
            [sys.executable, "-B", "-m", "unittest", "discover", "-s", directory],
            log_path,
            timeout,
            env=env,
        )
        match = re.search(r"Ran ([0-9]+) tests?", result.stdout + result.stderr)
        tests = f", {match.group(1)} tests" if match else ""
        print(
            f"  ronda {round_index}/{rounds} {name}: PASS "
            f"({format_duration(elapsed)}{tests})"
        )
    return f"{rounds} rondas de {directory}; logs: {run_dir / 'logs' / 'suites'}"


def phase_suites(args: argparse.Namespace, run_dir: Path, *, selfhost: bool) -> str:
    if selfhost:
        return run_suite(
            "selfhost",
            SELFHOST_TESTS,
            args.selfhost_rounds,
            300,
            run_dir,
        )
    return run_suite("ferros", FERROS_TESTS, args.rounds, 900, run_dir)


# ---------------------------------------------------------------------------
# Fuzzing diferencial: evaluador de expresiones
# ---------------------------------------------------------------------------

ATOMS = (
    "0", "1", "2", "3", "7", "10", "42", "255", "4096",
    "4294967296", "18446744073709551615", "18446744073709551616",
    "99999999999999999999", "12345678901234567890",
)


def generate_valid_expression(rng: random.Random, depth: int = 0) -> str:
    if depth >= 3 or rng.random() < 0.35:
        return rng.choice(ATOMS)
    operator = rng.choice(("+", "-", "*", "/", "%"))
    left = generate_valid_expression(rng, depth + 1)
    right = generate_valid_expression(rng, depth + 1)
    if operator in ("/", "%") and rng.random() < 0.30:
        right = "0"  # divisor cero: error de contrato, no crash
    text = f"{left} {operator} {right}"
    if rng.random() < 0.40:
        text = f"({text})"
    if rng.random() < 0.20:
        text = f"-{text}"
    return text


def mutate_expression(rng: random.Random, expression: str) -> str:
    """Introduce errores lexicos/sintacticos sin usar eval ni ast."""
    mode = rng.randrange(6)
    if not expression:
        return rng.choice(("(", ")", "+", "abc", "1..2", "1 2", "  "))
    if mode == 0:
        return expression[: rng.randrange(len(expression))]
    if mode == 1:
        position = rng.randrange(len(expression) + 1)
        return expression[:position] + rng.choice("()+-*/%x ") + expression[position:]
    if mode == 2:
        position = rng.randrange(len(expression))
        return expression[:position] + expression[position + 1:]
    if mode == 3:
        return expression + rng.choice((")", "(", "+", "*", "/", " x", " 1"))
    if mode == 4:
        return expression.replace("(", "", 1)
    return rng.choice(("", "   ", "()", "1/0", "5%0", "+1", "1++2", "abc", "1..2"))


def generate_parser_cases(rng: random.Random, count: int) -> list[str]:
    """Casos deterministas de borde primero; el resto pseudoaleatorios."""
    cases = [
        "",
        "   ",
        "1/0",
        "5%0",
        "-" * 64 + "7",
        "-" * 65 + "7",
        "(" * 64 + "1" + ")" * 64,
        "(" * 65 + "1" + ")" * 65,
    ][:count]
    while len(cases) < count:
        if rng.random() < 0.62:
            text = generate_valid_expression(rng)
        else:
            text = mutate_expression(rng, generate_valid_expression(rng))
        # El driver lee una expresion por linea; no se permiten saltos de linea.
        text = text.replace("\r", " ").replace("\n", " ")
        if len(text) > 240:
            text = rng.choice(ATOMS)
        cases.append(text)
    return cases


def run_parser_fuzz(
    args: argparse.Namespace,
    run_dir: Path,
    reference,
) -> tuple[int, int]:
    work = run_dir / "fuzz" / "parser"
    executable = build_driver(PARSER_SOURCE, PARSER_DRIVER, work, "parser")
    rng = random.Random(args.seed)
    expressions = generate_parser_cases(rng, args.fuzz_cases)
    fixture = work / "cases.txt"
    fixture.write_text("\n".join(expressions) + "\n", encoding="utf-8")
    result, elapsed = run_logged(
        [str(executable), str(fixture)],
        work / "driver.log",
        180,
        check=False,
    )
    if result.returncode != 0:
        tail = "\n".join((result.stdout + result.stderr).splitlines()[-20:])
        raise StressFailure(
            f"parser_driver fallo (exit {result.returncode}); log: {work / 'driver.log'}\n{tail}"
        )
    lines = result.stdout.splitlines()
    if len(lines) != len(expressions):
        raise StressFailure(
            f"parser_driver devolvio {len(lines)} lineas, se esperaban "
            f"{len(expressions)}; log: {work / 'driver.log'}"
        )
    output_line = re.compile(r"status=([0-9]+) value=([0-9]+)")
    valid = 0
    errors = 0
    for index, (expression, line) in enumerate(zip(expressions, lines)):
        match = output_line.fullmatch(line)
        if match is None:
            raise StressFailure(
                f"parser_driver linea {index + 1} con formato inesperado: {line!r}; "
                f"log: {work / 'driver.log'}"
            )
        actual = (int(match.group(1)), int(match.group(2)))
        expected = reference(expression)
        if actual != expected:
            detail = work / f"mismatch-{index + 1:03}.txt"
            detail.write_text(
                f"expression={expression!r}\n"
                f"zen={actual[0]}/{actual[1]}\n"
                f"reference={expected[0]}/{expected[1]}\n",
                encoding="utf-8",
            )
            raise StressFailure(
                f"fuzz parser: discrepancia en el caso {index + 1} "
                f"({expression!r}): zen={actual}, referencia={expected}; "
                f"detalle: {detail}; log: {work / 'driver.log'}"
            )
        if actual[0] == 0:
            valid += 1
        else:
            errors += 1
    print(
        f"  {len(expressions)} expresiones comparadas en {format_duration(elapsed)} "
        f"({valid} validas, {errors} con error)"
    )
    print(f"  driver: {executable}")
    print(f"  casos: {fixture}")
    return valid, errors


def phase_fuzz_parser(args: argparse.Namespace, run_dir: Path) -> str:
    reference = load_parser_reference()
    valid, errors = run_parser_fuzz(args, run_dir, reference)
    return (
        f"{args.fuzz_cases} expresiones contra test_selfhost_parser.reference "
        f"({valid} validas, {errors} con error); logs: {run_dir / 'fuzz' / 'parser'}"
    )


# ---------------------------------------------------------------------------
# Fuzzing diferencial: lexer
# ---------------------------------------------------------------------------

def lexer_reference_counts(module, output: str, data: bytes) -> tuple[dict[str, int], bool]:
    """Cuenta categorias del stdout de `zen lex`; detecta el token Error."""
    counts = {name: 0 for name in module.COUNTERS if name != "bytes"}
    saw_error = False
    for line in output.splitlines():
        match = module.TOKEN_LINE.match(line)
        if match is None:
            raise StressFailure(f"no se pudo interpretar la linea de zen lex: {line!r}")
        kind = match.group(1)
        if kind == "Eof":
            continue
        if kind == "Error":
            saw_error = True
        counts["tokens"] += 1
        category = module.categorize(kind)
        if category not in counts:
            raise StressFailure(f"categoria de token desconocida: {kind}")
        counts[category] += 1
    counts["bytes"] = len(data)
    return counts, saw_error


def driver_lexer_counts(stdout: str, counters) -> dict[str, int]:
    counts: dict[str, int] = {}
    for field in stdout.split():
        name, _, value = field.partition("=")
        if name in counters:
            try:
                counts[name] = int(value)
            except ValueError:
                raise StressFailure(f"contador no numerico del lexer: {field!r}") from None
    missing = [name for name in counters if name not in counts]
    if missing:
        raise StressFailure(f"la salida del lexer no incluye {missing}: {stdout!r}")
    return counts


def mutate_lexer_source(
    rng: random.Random,
    fixtures: list[bytes],
) -> tuple[bytes, str]:
    """Aplica una mutacion ASCII/UTF-8 acotada a una fixture canonica."""
    base = bytearray(rng.choice(fixtures))
    mode = rng.choices(
        ("append", "splice", "replace", "insert", "delete", "utf8"),
        weights=(3, 3, 2, 1, 1, 2),
        k=1,
    )[0]
    if mode == "append":
        snippet = rng.choice(
            (
                b"\n// stress mutation\n",
                b"\n/* stress mutation */\n",
                b"\nfn stress_extra(a:u64)->u64 { return a + 1; }\n",
            )
        )
        return bytes(base) + snippet, mode
    if mode == "splice":
        donor = rng.choice(fixtures)
        start = rng.randrange(len(donor))
        end = min(len(donor), start + rng.randrange(1, 61))
        position = rng.randrange(len(base) + 1)
        return bytes(base[:position] + donor[start:end] + base[position:]), mode
    if mode == "replace" and base:
        position = rng.randrange(len(base))
        base[position] = rng.choice(ASCII_MUTATION_BYTES)
        return bytes(base), mode
    if mode == "insert":
        position = rng.randrange(len(base) + 1)
        count = rng.randrange(1, 5)
        inserted = bytes(rng.choice(ASCII_MUTATION_BYTES) for _ in range(count))
        return bytes(base[:position] + inserted + base[position:]), mode
    if mode == "delete" and len(base) > 20:
        position = rng.randrange(len(base))
        count = rng.randrange(1, 6)
        return bytes(base[:position] + base[position + count:]), mode
    # utf8: mutar dentro de un comentario/string/char mantiene la fuente valida.
    spans = list(SPAN_PATTERN.finditer(bytes(base)))
    if not spans:
        return bytes(base) + b"\n" + UTF8_COMMENT_FIXTURE, "utf8-append"
    span = rng.choice(spans)
    start, end = span.start(), span.end()
    interior = [index for index in range(start + 1, max(start + 1, end - 1))
                if base[index] != 0x5C]  # no romper un escape
    if not interior:
        return bytes(base) + b"\n" + UTF8_COMMENT_FIXTURE, "utf8-append"
    position = rng.choice(interior)
    replacement = rng.choice(UTF8_MUTATION_CHARS)
    return bytes(base[:position] + replacement + base[position + 1:]), mode


def run_lexer_fuzz(
    args: argparse.Namespace,
    run_dir: Path,
) -> tuple[int, int, int]:
    module = load_lexer_reference()
    fixtures = []
    for path in module.FIXTURES:
        if not path.is_file():
            raise StressFailure(f"falta la fixture canonica {path}")
        fixtures.append(path.read_bytes())
    fixtures.append(module.SYNTHETIC.encode("utf-8"))
    fixtures.append(UTF8_COMMENT_FIXTURE)

    work = run_dir / "fuzz" / "lexer"
    executable = build_driver(LEXER_SOURCE, LEXER_DRIVER, work, "lexer")
    zen = str(ZEN)
    rng = random.Random(args.seed ^ 0x5EED)
    cases: list[tuple[bytes, str]] = [(UTF8_CHAR_FIXTURE, "utf8-char-fijo")]
    while len(cases) < args.fuzz_cases:
        cases.append(mutate_lexer_source(rng, fixtures))

    compared = 0
    skipped = 0
    tolerated = 0
    tolerated_log = work / "tolerated.log"
    if tolerated_log.exists():
        tolerated_log.unlink()
    for index, (data, mode) in enumerate(cases, start=1):
        path = work / f"case-{index:03}.zen"
        path.write_bytes(data)
        reference, _ = run_logged(
            [zen, "lex", str(path)],
            work / f"case-{index:03}-zen-lex.log",
            60,
            check=False,
        )
        if reference.returncode != 0:
            skipped += 1
            continue
        expected, saw_error = lexer_reference_counts(module, reference.stdout, data)
        if saw_error:
            skipped += 1  # zen lex paro en Error: no hay contadores que comparar
            continue
        actual_result, _ = run_logged(
            [str(executable), str(path)],
            work / f"case-{index:03}-driver.log",
            60,
            check=False,
        )
        if actual_result.returncode != 0:
            tail = "\n".join((actual_result.stdout + actual_result.stderr).splitlines()[-15:])
            raise StressFailure(
                f"lexer_driver fallo en el caso {index} (modo {mode}, {path}); "
                f"log: {work / f'case-{index:03}-driver.log'}\n{tail}"
            )
        actual = driver_lexer_counts(actual_result.stdout, module.COUNTERS)
        if actual == expected:
            compared += 1
            continue
        # Unica tolerancia documentada: fuentes UTF-8 validas para zen lex.
        # El lexer Zen recorre bytes, asi que un literal de caracter multibyte
        # (o cualquier byte no ASCII) puede dar contadores distintos.
        non_ascii = any(byte >= 0x80 for byte in data)
        if non_ascii:
            tolerated += 1
            difference = {
                name: {"zen": actual[name], "referencia": expected[name]}
                for name in expected
                if actual[name] != expected[name]
            }
            with tolerated_log.open("a", encoding="utf-8") as log:
                log.write(
                    f"{path.name}\tmodo={mode}\tdiff={json.dumps(difference, ensure_ascii=False)}\n"
                )
            continue
        difference = {
            name: {"zen": actual[name], "referencia": expected[name]}
            for name in expected
            if actual[name] != expected[name]
        }
        detail = work / f"mismatch-{index:03}.json"
        detail.write_text(
            json.dumps(
                {
                    "case": index,
                    "mode": mode,
                    "source": str(path),
                    "difference": difference,
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        raise StressFailure(
            f"fuzz lexer: discrepancia sin tolerancia en el caso {index} "
            f"(modo {mode}, {path}): {difference}; "
            f"detalle: {detail}; log zen lex: {work / f'case-{index:03}-zen-lex.log'}"
        )
    if tolerated:
        print(f"  toleradas por UTF-8 documentado: {tolerated} (ver {tolerated_log})")
    print(
        f"  {len(cases)} mutaciones: {compared} comparadas, "
        f"{skipped} omitidas (zen lex rechaza la fuente), {tolerated} toleradas UTF-8"
    )
    print(f"  driver: {executable}")
    print(f"  casos: {work / 'case-001.zen'} ... {work / f'case-{len(cases):03}.zen'}")
    return compared, skipped, tolerated


def phase_fuzz_lexer(args: argparse.Namespace, run_dir: Path) -> str:
    compared, skipped, tolerated = run_lexer_fuzz(args, run_dir)
    return (
        f"{args.fuzz_cases} mutaciones; {compared} comparadas, {skipped} omitidas, "
        f"{tolerated} toleradas UTF-8; logs: {run_dir / 'fuzz' / 'lexer'}"
    )


# ---------------------------------------------------------------------------
# Orquestacion y resumen
# ---------------------------------------------------------------------------

def run_phase(records: list[dict], name: str, action) -> None:
    print(f"\n== {name} ==")
    started = time.perf_counter()
    try:
        detail = action()
    except StressFailure as error:
        elapsed = time.perf_counter() - started
        records.append(
            dict(name=name, status="FAIL", seconds=elapsed, detail=str(error))
        )
        print(f"  FAIL ({format_duration(elapsed)}): {error}")
        raise
    except Exception as error:  # noqa: BLE001 - convierte bugs/errores inesperados en fase fallida
        elapsed = time.perf_counter() - started
        detail = f"{type(error).__name__}: {error}"
        records.append(dict(name=name, status="FAIL", seconds=elapsed, detail=detail))
        print(f"  FAIL ({format_duration(elapsed)}): {detail}")
        raise StressFailure(detail) from error
    elapsed = time.perf_counter() - started
    records.append(dict(name=name, status="PASS", seconds=elapsed, detail=detail or ""))
    print(f"  PASS ({format_duration(elapsed)})")


def print_summary(records: list[dict], total: float, run_dir: Path, failed: bool) -> None:
    print("\n" + "=" * 100)
    print("Resumen de estrés (TASK-905)")
    print("=" * 100)
    print(f"  {'Fase':<46} {'Estado':<7} {'Duración':>9}  Detalle")
    for record in records:
        detail = record["detail"].splitlines()[0] if record["detail"] else ""
        print(
            f"  {record['name']:<46} {record['status']:<7} "
            f"{format_duration(record['seconds']):>9}  {detail}"
        )
    print("-" * 100)
    print(f"  TOTAL: {format_duration(total)}")
    print(f"  Logs: {run_dir}")
    print(f"  Resultado: {'FALLO' if failed else 'PASS'}")


def effective_settings(args: argparse.Namespace) -> None:
    args.boots = args.boots if args.boots is not None else (2 if args.quick else 6)
    args.rounds = args.rounds if args.rounds is not None else (1 if args.quick else 2)
    args.fuzz_cases = (
        args.fuzz_cases if args.fuzz_cases is not None else (20 if args.quick else 200)
    )
    args.selfhost_rounds = 1 if args.quick else 2
    if args.boots < 1:
        raise StressFailure("--boots debe ser >= 1")
    if args.rounds < 1:
        raise StressFailure("--rounds debe ser >= 1")
    if args.fuzz_cases < 1:
        raise StressFailure("--fuzz-cases debe ser >= 1")
    if args.boot_timeout <= 0:
        raise StressFailure("--boot-timeout debe ser positivo")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Estrés acotado de Zen/Ferros: arranques QEMU repetidos, suites "
            "repetidas y fuzzing diferencial self-hosted (TASK-905)."
        ),
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="2 boots, 1 ronda por suite y 20 casos por fuzz (objetivo <60 s)",
    )
    parser.add_argument(
        "--boots",
        type=int,
        default=None,
        help="número de arranques QEMU (por defecto 6; 2 con --quick)",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=None,
        help="rondas de la suite de Ferros (por defecto 2; 1 con --quick)",
    )
    parser.add_argument(
        "--fuzz-cases",
        type=int,
        default=None,
        help="casos por cada fuzz (por defecto 200; 20 con --quick)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help="semilla fija del fuzz (reproducible; por defecto 905)",
    )
    parser.add_argument(
        "--boot-timeout",
        type=float,
        default=15.0,
        help="timeout por arranque QEMU en segundos",
    )
    parser.add_argument("--qemu", help="ruta explícita a qemu-system-x86_64")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        effective_settings(args)
    except StressFailure as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    try:
        run_dir = Path(tempfile.mkdtemp(prefix="zenferros-stress-"))
    except OSError as error:
        print(f"error: no se pudo crear el directorio temporal de logs: {error}",
              file=sys.stderr)
        return 1

    mode = "quick" if args.quick else "completo"
    print("ZenFerros — estrés acotado (TASK-905)")
    print(f"  repo: {ROOT}")
    print(
        f"  modo: {mode} ({args.boots} boots, {args.rounds} ronda(s) Ferros, "
        f"{args.selfhost_rounds} ronda(s) selfhost, {args.fuzz_cases} casos por fuzz)"
    )
    print(f"  semilla: {args.seed}")
    print(f"  logs: {run_dir}")
    print("  (artefactos solo en el directorio temporal; no se escribe en el repo)")

    context: dict = {}
    records: list[dict] = []
    started = time.perf_counter()
    failed = False
    try:
        run_phase(
            records,
            "Build del kernel Ferros (debug+release)",
            lambda: phase_builds(args, run_dir, context),
        )
        run_phase(
            records,
            f"Arranques QEMU ({args.boots}: perfiles y guiones)",
            lambda: phase_boots(args, run_dir, context),
        )
        run_phase(
            records,
            f"Suite Ferros ({args.rounds} ronda(s))",
            lambda: phase_suites(args, run_dir, selfhost=False),
        )
        run_phase(
            records,
            f"Suite selfhost ({args.selfhost_rounds} ronda(s))",
            lambda: phase_suites(args, run_dir, selfhost=True),
        )
        run_phase(
            records,
            f"Fuzz diferencial del parser ({args.fuzz_cases} casos)",
            lambda: phase_fuzz_parser(args, run_dir),
        )
        run_phase(
            records,
            f"Fuzz diferencial del lexer ({args.fuzz_cases} casos)",
            lambda: phase_fuzz_lexer(args, run_dir),
        )
    except StressFailure:
        failed = True
    except KeyboardInterrupt:
        print("\nCancelado por el usuario.")
        return 130

    total = time.perf_counter() - started
    print_summary(records, total, run_dir, failed)
    summary = {
        "task": "TASK-905",
        "mode": mode,
        "seed": args.seed,
        "boots": args.boots,
        "rounds": args.rounds,
        "selfhost_rounds": args.selfhost_rounds,
        "fuzz_cases": args.fuzz_cases,
        "boot_timeout": args.boot_timeout,
        "result": "FAIL" if failed else "PASS",
        "total_seconds": round(total, 6),
        "phases": records,
        "logs": str(run_dir),
    }
    try:
        (run_dir / "summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"  Resumen JSON: {run_dir / 'summary.json'}")
    except OSError as error:
        print(f"  aviso: no se pudo escribir summary.json: {error}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
