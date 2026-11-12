#!/usr/bin/env python3
"""Validador local del workflow de CI remoto de ZenFerros (TASK-918).

Comprueba, sin red y sin ejecutar el workflow, que
`.github/workflows/ci.yml` tiene la estructura esperada y que es coherente con
`docs/ci.md` y `docs/ci-remote.md`:

  - claves raiz `name`, `on` y `jobs`, y disparadores push/PR/manual;
  - jobs con `runs-on`, `timeout-minutes` y `steps`, y pasos con `uses` o `run`;
  - toolchain: checkout, setup-python, Rust stable, GCC y QEMU;
  - cache de Cargo sobre `.cargo`, `CARGO_HOME` en el workspace y `cargo fetch`
    para poblar el registro que usa la matriz con `--offline`;
  - `ci_matrix.py --quick` en pull request y `--full` en main/manual, con
    `--json` en `$RUNNER_TEMP` y subida del JSON como artefacto fuera del repo;
  - rutas del repositorio citadas por el workflow que existan de verdad;
  - ausencia de secretos hardcodeados, de `pull_request_target` y de permisos
    de escritura.

El YAML se lee con PyYAML si esta instalado; si no, con un parser minimo de
sangria incluido aqui (subconjunto: mapas, secuencias, escalares, secuencias de
flujo y bloques `|`/`>`). No se usa la red en ningun caso.

Uso:
    python3 infrastructure/scripts/check_ci_workflow.py
    python3 infrastructure/scripts/check_ci_workflow.py --backend mini
    python3 infrastructure/scripts/check_ci_workflow.py --workflow /tmp/ci.yml --quiet

Codigos de salida:
    0  todas las comprobaciones pasan (PASS).
    1  alguna comprobacion falla (incluye YAML ilegible o invalido).
    2  error de uso: raiz inexistente, backend pedido no disponible, etc.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WORKFLOW = Path(".github/workflows/ci.yml")
DEFAULT_DOC = Path("docs/ci-remote.md")
TASK = "TASK-918"

# Rutas que el contrato del workflow da por hechas. Ademas de esta lista se
# comprueban las rutas con extension que aparezcan dentro de los bloques `run`.
REQUIRED_PATHS = [
    "infrastructure/scripts/ci_matrix.py",
    "infrastructure/scripts/check_ci_workflow.py",
    "infrastructure/scripts/verify_all.py",
    "infrastructure/scripts/stress.py",
    "infrastructure/scripts/repro_build.py",
    "zen/compiler/Cargo.toml",
    "zen/compiler/Cargo.lock",
    "docs/ci.md",
    "docs/ci-remote.md",
]

PATH_TOKEN = re.compile(
    r"(?<![A-Za-z0-9_./${\-])"
    r"((?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\.(?:py|toml|lock|json|ya?ml|md))"
)
SECRET_PATTERNS = [
    (r"\bsecrets\s*\.", "referencia a secrets.* (el contrato no usa secretos)"),
    (r"ghp_[A-Za-z0-9]{20,}", "posible token de GitHub hardcodeado"),
    (r"github_pat_[A-Za-z0-9_]{20,}", "posible token de GitHub hardcodeado"),
    (r"AKIA[0-9A-Z]{16}", "posible clave de AWS hardcodeada"),
    (r"xox[baprs]-[A-Za-z0-9-]{10,}", "posible token de Slack hardcodeado"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "clave privada embebida"),
    (
        r"(?i)\b(password|passwd|api[_-]?key|access[_-]?token|auth[_-]?token)"
        r"\s*[:=]\s*['\"]?[^\s'\"]{6,}",
        "credencial hardcodeada",
    ),
]
# Frases que docs/ci-remote.md debe contener; cada entrada admite variantes.
DOC_REQUIRED = {
    "comando de validacion": ("check_ci_workflow.py",),
    "aviso de no ejecucion": ("no se ha ejecutado",),
    "remoto configurado": ("remoto configurado",),
    "no es atestacion": ("no es una atestación", "no es una atestacion", "no constituye una atestación"),
    "requisitos": ("requisitos",),
    "diferencias local/remoto": ("diferencia",),
    "limites": ("límites", "limites"),
    "validacion local": ("validar", "validación", "validacion"),
}


# ---------------------------------------------------------------------------
# Parser YAML minimo (sin dependencias)
# ---------------------------------------------------------------------------


class MiniYamlError(ValueError):
    """Error de sintaxis del subconjunto YAML soportado."""

    def __init__(self, message: str, line: int | None = None) -> None:
        self.line = line
        super().__init__(f"linea {line}: {message}" if line else message)


KEY_RE = re.compile(r"^([A-Za-z0-9_.\-]+):(?:[ \t]+(.*))?$")


def _indent_of(raw: str, line: int) -> int:
    prefix = raw[: len(raw) - len(raw.lstrip(" \t"))]
    if "\t" in prefix:
        raise MiniYamlError("tabulaciones en la sangria no soportadas", line)
    return len(prefix)


def _content(lines: list[str], index: int) -> int:
    while index < len(lines):
        stripped = lines[index].strip()
        if stripped and not stripped.startswith("#") and stripped not in ("---", "..."):
            return index
        index += 1
    return index


def _split_key(text: str, line: int) -> tuple[str, str]:
    match = KEY_RE.match(text)
    if match is None:
        raise MiniYamlError(f"se esperaba 'clave: valor' y hay {text!r}", line)
    return match.group(1), (match.group(2) or "").strip()


def _scalar(text: str, line: int | None = None) -> Any:
    text = text.strip()
    if text.startswith("'"):
        if len(text) < 2 or not text.endswith("'"):
            raise MiniYamlError(f"comilla simple sin cerrar: {text!r}", line)
        return text[1:-1].replace("''", "'")
    if text.startswith('"'):
        if len(text) < 2 or not text.endswith('"'):
            raise MiniYamlError(f"comilla doble sin cerrar: {text!r}", line)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text[1:-1]
    if text.startswith(("&", "*")):
        raise MiniYamlError("anclas y alias no soportados por el parser minimo", line)
    if text in ("~", "null", "Null", "NULL"):
        return None
    if text in ("true", "True", "TRUE"):
        return True
    if text in ("false", "False", "FALSE"):
        return False
    return text


def _flow_sequence(text: str, line: int) -> list[Any]:
    inner = text[1:-1].strip()
    if not inner:
        return []
    parts: list[str] = []
    current: list[str] = []
    quote: str | None = None
    for char in inner:
        if quote is not None:
            current.append(char)
            if char == quote:
                quote = None
        elif char in ("'", '"'):
            quote = char
            current.append(char)
        elif char == ",":
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    if quote is not None:
        raise MiniYamlError("comilla sin cerrar en una secuencia de flujo", line)
    parts.append("".join(current))
    return [_scalar(part.strip(), line) for part in parts if part.strip()]


def _parse_block_scalar(header: str, lines: list[str], index: int, indent: int) -> tuple[str, int]:
    modifiers = header[1:].split("#", 1)[0].strip()
    chomp = "-" if "-" in modifiers else ("+" if "+" in modifiers else "")
    index += 1
    collected: list[str] = []
    block_indent: int | None = None
    while index < len(lines):
        raw = lines[index]
        if raw.strip() == "":
            collected.append("")
            index += 1
            continue
        current = _indent_of(raw, index + 1)
        if current <= indent:
            break
        if block_indent is None:
            block_indent = current
        if current < block_indent:
            break
        collected.append(raw[block_indent:])
        index += 1
    if chomp == "-":
        while collected and collected[-1] == "":
            collected.pop()
    body = "\n".join(collected)
    if chomp != "-" and body:
        body += "\n"
    return body, index


def _parse_value(rest: str, lines: list[str], index: int, indent: int) -> tuple[Any, int]:
    rest = rest.strip()
    if rest[:1] in ("|", ">"):
        return _parse_block_scalar(rest, lines, index, indent)
    if rest.startswith("["):
        if not rest.endswith("]"):
            raise MiniYamlError("secuencia de flujo sin cerrar", index + 1)
        return _flow_sequence(rest, index + 1), index + 1
    if rest.startswith("{"):
        raise MiniYamlError("los mapas de flujo no estan soportados", index + 1)
    return _scalar(rest, index + 1), index + 1


def _parse_mapping(
    lines: list[str], index: int, indent: int, first_text: str | None = None
) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {}
    if first_text is not None:
        key, rest = _split_key(first_text, index + 1)
        index += 1
        if rest == "":
            child = _content(lines, index)
            if child < len(lines) and _indent_of(lines[child], child + 1) > indent:
                value, index = _parse_block(lines, child, _indent_of(lines[child], child + 1))
            else:
                value = None
        else:
            value, index = _parse_value(rest, lines, index - 1, indent)
        result[key] = value
    while True:
        index = _content(lines, index)
        if index >= len(lines):
            break
        raw = lines[index]
        current = _indent_of(raw, index + 1)
        if current < indent:
            break
        if current > indent:
            raise MiniYamlError("sangria inesperada dentro de un mapa", index + 1)
        text = raw.strip()
        if text.startswith("-"):
            break
        key, rest = _split_key(text, index + 1)
        if key in result:
            raise MiniYamlError(f"clave duplicada {key!r} en el mismo mapa", index + 1)
        index += 1
        if rest == "":
            child = _content(lines, index)
            if child < len(lines) and _indent_of(lines[child], child + 1) > indent:
                value, index = _parse_block(lines, child, _indent_of(lines[child], child + 1))
            else:
                value = None
        else:
            value, index = _parse_value(rest, lines, index - 1, indent)
        result[key] = value
    return result, index


def _parse_sequence(lines: list[str], index: int, indent: int) -> tuple[list[Any], int]:
    items: list[Any] = []
    while True:
        index = _content(lines, index)
        if index >= len(lines):
            break
        raw = lines[index]
        current = _indent_of(raw, index + 1)
        if current < indent:
            break
        if current > indent:
            raise MiniYamlError("sangria inesperada en una secuencia", index + 1)
        text = raw.strip()
        if not text.startswith("-"):
            break
        rest = text[1:]
        if rest.startswith((" ", "\t")):
            rest = rest.lstrip()
        if rest == "":
            child = _content(lines, index + 1)
            if child < len(lines) and _indent_of(lines[child], child + 1) > indent:
                value, index = _parse_block(lines, child, _indent_of(lines[child], child + 1))
            else:
                value, index = None, index + 1
            items.append(value)
            continue
        offset = len(text) - len(rest)
        if KEY_RE.match(rest):
            value, index = _parse_mapping(lines, index, indent + offset, first_text=rest)
        else:
            value, index = _scalar(rest, index + 1), index + 1
        items.append(value)
    return items, index


def _parse_block(lines: list[str], index: int, indent: int) -> tuple[Any, int]:
    index = _content(lines, index)
    if index >= len(lines):
        return None, index
    current = _indent_of(lines[index], index + 1)
    if current < indent:
        return None, index
    if current > indent:
        raise MiniYamlError("sangria inesperada", index + 1)
    if lines[index].strip().startswith("-"):
        return _parse_sequence(lines, index, indent)
    return _parse_mapping(lines, index, indent)


def parse_minimal(text: str) -> Any:
    """Parsea el subconjunto YAML que usa el workflow (sin red, sin PyYAML)."""
    lines = text.splitlines()
    value, index = _parse_block(lines, 0, 0)
    index = _content(lines, index)
    if index < len(lines):
        raise MiniYamlError(f"contenido inesperado: {lines[index].strip()!r}", index + 1)
    return value


# ---------------------------------------------------------------------------
# Carga del YAML
# ---------------------------------------------------------------------------


class BackendUnavailable(RuntimeError):
    """PyYAML fue pedido explicitamente pero no esta instalado."""


def import_yaml() -> Any:
    try:
        import yaml  # noqa: F401  (import local: PyYAML es opcional)
    except ImportError as exc:  # pragma: no cover - depende del entorno
        raise BackendUnavailable("PyYAML no esta instalado") from exc
    return yaml


def load_workflow(text: str, backend: str) -> tuple[Any, str]:
    if backend == "mini":
        return parse_minimal(text), "minimo (forzado)"
    if backend == "yaml":
        yaml = import_yaml()
        return yaml.safe_load(text), "PyYAML (forzado)"
    try:
        yaml = import_yaml()
    except BackendUnavailable:
        return parse_minimal(text), "minimo (PyYAML no disponible)"
    return yaml.safe_load(text), "PyYAML"


# ---------------------------------------------------------------------------
# Comprobaciones
# ---------------------------------------------------------------------------


@dataclass
class Check:
    ident: str
    title: str
    ok: bool
    detail: str = ""


def as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return str(value)


def is_true(value: Any) -> bool:
    """Interpreta un booleano YAML sin depender del backend (bool o texto)."""
    if isinstance(value, bool):
        return value
    return as_text(value).strip().lower() in ("true", "yes", "on", "1")


def flatten(value: Any) -> list[str]:
    if isinstance(value, list):
        return [as_text(item) for item in value]
    return [as_text(value)] if value is not None else []


def triggers_of(data: dict[str, Any]) -> Any:
    if "on" in data:
        return data["on"]
    # PyYAML (YAML 1.1) interpreta la clave `on` como booleano True.
    if True in data:
        return data[True]
    return None


def trigger_names(on: Any) -> list[str]:
    if isinstance(on, dict):
        return [as_text(key) for key in on]
    if isinstance(on, list):
        return [as_text(item) for item in on]
    if isinstance(on, str):
        return [on]
    return []


def steps_of(job: Any) -> list[Any]:
    if isinstance(job, dict) and isinstance(job.get("steps"), list):
        return job["steps"]
    return []


def run_text(step: Any) -> str:
    return as_text(step.get("run")) if isinstance(step, dict) else ""


def uses_text(step: Any) -> str:
    return as_text(step.get("uses")) if isinstance(step, dict) else ""


def if_text(step: Any) -> str:
    return as_text(step.get("if")) if isinstance(step, dict) else ""


def with_map(step: Any) -> dict[str, Any]:
    if isinstance(step, dict) and isinstance(step.get("with"), dict):
        return step["with"]
    return {}


def first_line(text: str, limit: int = 90) -> str:
    """Primera linea no vacia, recortada para que quepa en el informe."""
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line if len(line) <= limit else line[: limit - 1] + "…"
    return ""


def matching_line(runs: list[str], predicate: Any) -> str:
    """Primera linea de cualquier bloque `run` que cumpla el predicado."""
    for run in runs:
        for line in run.splitlines():
            line = line.strip()
            if line and predicate(line):
                return line if len(line) <= 90 else line[:89] + "…"
    return ""


def env_maps(data: dict[str, Any]) -> list[dict[str, Any]]:
    maps: list[dict[str, Any]] = []
    if isinstance(data.get("env"), dict):
        maps.append(data["env"])
    jobs = data.get("jobs")
    if isinstance(jobs, dict):
        for job in jobs.values():
            if isinstance(job, dict):
                if isinstance(job.get("env"), dict):
                    maps.append(job["env"])
                for step in steps_of(job):
                    if isinstance(step, dict) and isinstance(step.get("env"), dict):
                        maps.append(step["env"])
    return maps


def all_steps(data: dict[str, Any]) -> list[Any]:
    steps: list[Any] = []
    jobs = data.get("jobs")
    if isinstance(jobs, dict):
        for job in jobs.values():
            steps.extend(steps_of(job))
    return steps


def find_line(text: str, pattern: str) -> tuple[int, str] | None:
    regex = re.compile(pattern, re.IGNORECASE)
    for number, line in enumerate(text.splitlines(), 1):
        if regex.search(line):
            return number, line.strip()
    return None


def add(checks: list[Check], ident: str, title: str, ok: bool, detail: str = "") -> None:
    checks.append(Check(ident, title, bool(ok), detail))


def check_doc(checks: list[Check], doc_path: Path, root: Path) -> None:
    if not doc_path.is_file():
        add(checks, "doc-existe", "docs/ci-remote.md existe", False, f"falta {doc_path}")
        return
    add(checks, "doc-existe", "docs/ci-remote.md existe", True, str(doc_path))
    text = doc_path.read_text(encoding="utf-8", errors="replace")
    add(checks, "doc-contenido", "el doc cubre el contrato", bool(text.strip()), f"{len(text)} bytes")
    folded = text.casefold()
    missing = [
        label
        for label, alternatives in DOC_REQUIRED.items()
        if not any(option.casefold() in folded for option in alternatives)
    ]
    add(
        checks,
        "doc-secciones",
        "el doc declara comando, no ejecucion, estado remoto, limites y validacion",
        not missing,
        "faltan: " + ", ".join(missing) if missing else "todas las secciones presentes",
    )
    ci_doc = root / "docs/ci.md"
    if not ci_doc.is_file():
        add(checks, "doc-ci-coherente", "docs/ci.md existe y describe la matriz", False, f"falta {ci_doc}")
        return
    ci_text = ci_doc.read_text(encoding="utf-8", errors="replace").casefold()
    required = ["ci_matrix.py", "--quick", "--full", "no es ci remoto"]
    missing_ci = [token for token in required if token not in ci_text]
    add(
        checks,
        "doc-ci-coherente",
        "docs/ci.md describe la matriz y no se presenta como CI remoto",
        not missing_ci,
        "faltan: " + ", ".join(missing_ci) if missing_ci else "referencias presentes",
    )


def validate(
    root: Path,
    workflow_path: Path,
    doc_path: Path,
    backend: str,
) -> tuple[list[Check], str]:
    checks: list[Check] = []
    backend_used = backend

    if not workflow_path.is_file():
        add(checks, "archivo-workflow", "el workflow existe", False, f"falta {workflow_path}")
        check_doc(checks, doc_path, root)
        return checks, backend_used
    text = workflow_path.read_text(encoding="utf-8", errors="replace")
    add(checks, "archivo-workflow", "el workflow existe", True, f"{workflow_path} ({len(text)} bytes)")
    if not text.strip():
        add(checks, "yaml-valido", "el workflow no esta vacio y parsea", False, "fichero vacio")
        check_doc(checks, doc_path, root)
        return checks, backend_used

    try:
        data, backend_used = load_workflow(text, backend)
    except BackendUnavailable as exc:
        raise
    except Exception as exc:  # PyYAML lanza sus propias excepciones; mini, MiniYamlError
        add(checks, "yaml-valido", "el workflow no esta vacio y parsea", False, f"{type(exc).__name__}: {exc}")
        check_doc(checks, doc_path, root)
        return checks, backend_used
    add(checks, "yaml-valido", "el workflow no esta vacio y parsea", True, f"parser: {backend_used}")

    if not isinstance(data, dict):
        add(checks, "claves-raiz", "la raiz es un mapa con name/on/jobs", False, f"raiz: {type(data).__name__}")
        check_doc(checks, doc_path, root)
        return checks, backend_used

    name = data.get("name")
    on = triggers_of(data)
    jobs = data.get("jobs")
    add(checks, "clave-name", "clave raiz 'name' no vacia", isinstance(name, str) and bool(name.strip()), as_text(name))
    add(checks, "clave-on", "clave raiz 'on' presente", on is not None, ", ".join(sorted(set(trigger_names(on)))) or as_text(on))
    add(
        checks,
        "clave-jobs",
        "clave raiz 'jobs' es un mapa no vacio",
        isinstance(jobs, dict) and bool(jobs),
        f"{len(jobs)} jobs" if isinstance(jobs, dict) else type(jobs).__name__,
    )

    names = trigger_names(on)
    required_triggers = {"push", "pull_request", "workflow_dispatch"}
    missing_triggers = sorted(required_triggers - set(names))
    add(
        checks,
        "disparadores",
        "dispara en push, pull_request y workflow_dispatch",
        not missing_triggers,
        "faltan: " + ", ".join(missing_triggers) if missing_triggers else ", ".join(sorted(set(names))),
    )
    push = on.get("push") if isinstance(on, dict) else None
    if push is None:
        add(checks, "push-main", "push limitado a main", False, "push sin filtro de ramas")
    else:
        branches = push.get("branches") if isinstance(push, dict) else push
        branch_list = flatten(branches)
        add(
            checks,
            "push-main",
            "push limitado a main",
            "main" in branch_list,
            "branches: " + ", ".join(branch_list) if branch_list else "sin branches",
        )

    job_map = jobs if isinstance(jobs, dict) else {}
    for job_id, job in job_map.items():
        prefix = f"job:{as_text(job_id)}"
        if not isinstance(job, dict):
            add(checks, f"{prefix}:forma", "cada job es un mapa con runs-on y steps", False, type(job).__name__)
            continue
        runs_on = job.get("runs-on")
        runs_on_text = " ".join(flatten(runs_on)).strip()
        add(checks, f"{prefix}:runs-on", "job con runs-on no vacio", bool(runs_on_text), runs_on_text)
        linux = runs_on_text.startswith("ubuntu-") or "${{" in runs_on_text
        add(
            checks,
            f"{prefix}:runner-linux",
            "runner Linux alojado (ubuntu-*) o expresion de matriz",
            linux,
            runs_on_text or "sin runs-on",
        )
        timeout = job.get("timeout-minutes")
        try:
            timeout_ok = int(as_text(timeout)) > 0
        except (TypeError, ValueError):
            timeout_ok = False
        add(checks, f"{prefix}:timeout", "job con timeout-minutes positivo", timeout_ok, as_text(timeout) or "sin timeout")
        steps = steps_of(job)
        add(checks, f"{prefix}:steps", "job con steps no vacios", bool(steps), f"{len(steps)} pasos")
        for position, step in enumerate(steps, 1):
            is_map = isinstance(step, dict)
            has_action = bool(uses_text(step)) or bool(run_text(step))
            add(
                checks,
                f"{prefix}:paso:{position}",
                "paso con 'uses' o 'run'",
                is_map and has_action,
                (uses_text(step) or first_line(run_text(step))) if is_map else type(step).__name__,
            )

    steps = all_steps(data)
    actions = [uses_text(step) for step in steps if uses_text(step)]
    runs = [run_text(step) for step in steps]

    add(
        checks,
        "checkout",
        "usa actions/checkout",
        any(action.startswith("actions/checkout@") for action in actions),
        next((action for action in actions if action.startswith("actions/checkout@")), "no encontrado"),
    )
    setup_python = next((action for action in actions if action.startswith("actions/setup-python@")), "")
    python_steps = [step for step in steps if uses_text(step).startswith("actions/setup-python@")]
    python_version = next(
        (as_text(with_map(step).get("python-version")) for step in python_steps),
        "",
    )
    add(
        checks,
        "setup-python",
        "instala Python con version declarada",
        bool(setup_python) and bool(python_version),
        f"{setup_python or 'no encontrado'} (python-version: {python_version or 'sin declarar'})",
    )

    rust_ok = any(
        ("rust-toolchain@" in action and "stable" in action)
        or (
            action.startswith("actions-rs/toolchain@")
            and as_text(with_map(step).get("toolchain")) == "stable"
        )
        for step, action in ((step, uses_text(step)) for step in steps)
    ) or any("rustup toolchain install stable" in run for run in runs)
    add(checks, "rust-estable", "instala Rust estable", rust_ok, "rust-toolchain stable" if rust_ok else "no encontrado")

    gcc_line = matching_line(
        runs,
        lambda line: "build-essential" in line
        or (re.search(r"\bgcc\b", line) is not None and ("install" in line or "apt" in line)),
    )
    add(
        checks,
        "gcc",
        "instala GCC/build-essential",
        bool(gcc_line),
        gcc_line or "no encontrado",
    )
    qemu_line = matching_line(
        runs,
        lambda line: ("qemu-system" in line and ("install" in line or "apt" in line))
        or "setup_qemu.py" in line,
    )
    add(
        checks,
        "qemu",
        "instala QEMU",
        bool(qemu_line),
        qemu_line or "no encontrado",
    )

    cargo_home = ""
    for env in env_maps(data):
        value = as_text(env.get("CARGO_HOME"))
        if value:
            cargo_home = value
            break
    cargo_home_ok = bool(cargo_home) and ".cargo" in cargo_home and (
        "github.workspace" in cargo_home or "runner.workspace" in cargo_home
    )
    add(
        checks,
        "cargo-home",
        "CARGO_HOME en el workspace",
        cargo_home_ok,
        cargo_home or "sin CARGO_HOME",
    )

    cache_steps = [step for step in steps if uses_text(step).startswith("actions/cache@")]
    cache_path = " ".join(
        as_text(with_map(step).get("path")) for step in cache_steps
    )
    cache_key = " ".join(as_text(with_map(step).get("key")) for step in cache_steps)
    cache_ok = (
        bool(cache_steps)
        and ".cargo" in cache_path
        and "hashFiles" in cache_key
        and "Cargo.lock" in cache_key
    ) or any(action.startswith("Swatinem/rust-cache@") for action in actions)
    add(
        checks,
        "cache-cargo",
        "cache de Cargo sobre .cargo con clave por Cargo.lock",
        cache_ok,
        f"{len(cache_steps)} cache(s); path: {' '.join(cache_path.split()) or 'sin path'}",
    )

    add(
        checks,
        "cargo-fetch",
        "puebla el registro offline antes de la matriz",
        any("cargo fetch" in run and "Cargo.toml" in run for run in runs),
        next((run.strip().splitlines()[0] for run in runs if "cargo fetch" in run), "no encontrado"),
    )

    matrix_steps = [(step, run_text(step), if_text(step)) for step in steps if "ci_matrix.py" in run_text(step)]
    quick = [(step, run, cond) for step, run, cond in matrix_steps if "--quick" in run]
    full = [(step, run, cond) for step, run, cond in matrix_steps if "--full" in run]
    both = [(step, run, cond) for step, run, cond in matrix_steps if "--quick" in run and "--full" in run]
    quick_step, quick_run, quick_cond = quick[0] if quick else (None, "", "")
    full_step, full_run, full_cond = full[0] if full else (None, "", "")
    quick_masked = isinstance(quick_step, dict) and is_true(quick_step.get("continue-on-error"))
    full_masked = isinstance(full_step, dict) and is_true(full_step.get("continue-on-error"))

    quick_ok = (
        len(quick) == 1
        and not both
        and not quick_masked
        and "pull_request" in quick_cond
        and re.search(r"python3\s+infrastructure/scripts/ci_matrix\.py", quick_run) is not None
    )
    add(
        checks,
        "matriz-quick",
        "ci_matrix.py --quick solo en pull request",
        quick_ok,
        f"{len(quick)} paso(s); if: {quick_cond or 'sin condicion'}"
        + ("; continue-on-error oculta el fallo" if quick_masked else ""),
    )
    full_ok = (
        len(full) == 1
        and not both
        and not full_masked
        and any(token in full_cond for token in ("push", "workflow_dispatch", "main"))
        and re.search(r"python3\s+infrastructure/scripts/ci_matrix\.py", full_run) is not None
    )
    add(
        checks,
        "matriz-full",
        "ci_matrix.py --full en main/manual",
        full_ok,
        f"{len(full)} paso(s); if: {full_cond or 'sin condicion'}"
        + ("; continue-on-error oculta el fallo" if full_masked else ""),
    )

    json_ok = bool(quick and full) and all(
        "--json" in run and ("RUNNER_TEMP" in run or "runner.temp" in run or "/tmp/" in run)
        for _, run, _ in (quick + full)
    )
    add(
        checks,
        "matriz-json",
        "ambas matrices exportan --json a un temporal",
        bool(json_ok),
        quick_run.split("--json", 1)[-1].strip() if "--json" in quick_run else "sin --json",
    )

    upload_steps = [step for step in steps if uses_text(step).startswith("actions/upload-artifact@")]
    artifact_json_steps = [
        step for step in upload_steps if "ci-matrix.json" in as_text(with_map(step).get("path"))
    ]
    artifact_ok = bool(artifact_json_steps) and all(
        "always()" in if_text(step) for step in artifact_json_steps
    )
    artifact_path = " ".join(
        as_text(with_map(step).get("path")) for step in artifact_json_steps
    ).strip()
    add(
        checks,
        "artefacto-json",
        "sube ci-matrix.json como artefacto con if: always()",
        artifact_ok,
        artifact_path or "no encontrado",
    )

    outside: list[str] = []
    for step in upload_steps:
        for line in as_text(with_map(step).get("path")).splitlines():
            line = line.strip()
            if line and not line.startswith(("${{", "/", "~")):
                outside.append(line)
    add(
        checks,
        "artefacto-fuera-del-repo",
        "los artefactos se escriben fuera del repositorio",
        bool(upload_steps) and not outside,
        "rutas relativas: " + ", ".join(outside) if outside else "solo rutas temporales/absolutas",
    )

    secret_hits: list[str] = []
    for pattern, label in SECRET_PATTERNS:
        found = find_line(text, pattern)
        if found is not None:
            secret_hits.append(f"{label} (linea {found[0]})")
    add(
        checks,
        "sin-secretos",
        "sin secretos ni credenciales hardcodeadas",
        not secret_hits,
        "; ".join(secret_hits) or "sin coincidencias",
    )

    add(
        checks,
        "sin-pull-request-target",
        "no usa pull_request_target (evita exponer secretos a PR)",
        "pull_request_target" not in text,
        "pull_request_target presente" if "pull_request_target" in text else "no presente",
    )

    permissions = data.get("permissions")
    write_scopes = [
        f"{as_text(key)}={as_text(value)}"
        for key, value in (permissions.items() if isinstance(permissions, dict) else [])
        if "write" in as_text(value)
    ]
    permissions_ok = isinstance(permissions, dict) and not write_scopes
    add(
        checks,
        "permisos-lectura",
        "bloque permissions explicito y sin escritura",
        permissions_ok,
        ", ".join(write_scopes) if write_scopes else (as_text(permissions) or "sin bloque permissions"),
    )

    unpinned = [
        action
        for action in actions
        if "@" not in action or action.rsplit("@", 1)[-1] in ("main", "master", "HEAD")
    ]
    add(
        checks,
        "acciones-pinnadas",
        "acciones con referencia (@version) y sin ramas mutables",
        not unpinned,
        ", ".join(unpinned) if unpinned else f"{len(actions)} acciones referenciadas",
    )

    missing_paths: list[str] = []
    outside_paths: list[str] = []
    for relative in REQUIRED_PATHS:
        if not (root / relative).is_file():
            missing_paths.append(relative)
    extracted: set[str] = set()
    for run in runs:
        extracted.update(PATH_TOKEN.findall(run))
    for token in sorted(extracted):
        candidate = (root / token).resolve()
        try:
            candidate.relative_to(root.resolve())
        except ValueError:
            outside_paths.append(token)
            continue
        if not candidate.is_file():
            missing_paths.append(token)
    add(
        checks,
        "rutas-existentes",
        "las rutas citadas por el workflow existen",
        not missing_paths and not outside_paths,
        "; ".join(
            [*(f"falta {path}" for path in sorted(set(missing_paths)))]
            + [*(f"fuera del repo: {path}" for path in outside_paths)]
        )
        or f"{len(REQUIRED_PATHS)} requeridas + {len(extracted)} citadas",
    )

    check_doc(checks, doc_path, root)
    return checks, backend_used


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Valida localmente la estructura de .github/workflows/ci.yml y su "
            "coherencia con docs/ci.md y docs/ci-remote.md (TASK-918). No usa red."
        ),
    )
    parser.add_argument("--root", help=f"raiz del repositorio (por defecto: {ROOT})")
    parser.add_argument("--workflow", help="ruta del workflow (por defecto: <raiz>/.github/workflows/ci.yml)")
    parser.add_argument("--doc", help="ruta de docs/ci-remote.md (por defecto: <raiz>/docs/ci-remote.md)")
    parser.add_argument(
        "--backend",
        choices=("auto", "mini", "yaml"),
        default="auto",
        help="lector YAML: auto (PyYAML si esta, si no parser minimo), mini o yaml",
    )
    parser.add_argument("--quiet", action="store_true", help="solo muestra fallos y el resumen")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(args.root).expanduser().resolve() if args.root else ROOT
    if not root.is_dir():
        print(f"error: la raiz no existe o no es un directorio: {root}", file=sys.stderr)
        return 2
    workflow_path = Path(args.workflow).expanduser() if args.workflow else root / DEFAULT_WORKFLOW
    doc_path = Path(args.doc).expanduser() if args.doc else root / DEFAULT_DOC
    if not workflow_path.is_absolute():
        workflow_path = (root / workflow_path).resolve()
    if not doc_path.is_absolute():
        doc_path = (root / doc_path).resolve()

    print(f"Validador del workflow de CI remoto ({TASK})")
    print(f"  workflow: {workflow_path}")
    print(f"  doc:      {doc_path}")
    print(f"  raiz:     {root}")
    print("  alcance:  estructura local; no ejecuta el workflow ni usa la red")
    print()

    try:
        checks, backend_used = validate(root, workflow_path, doc_path, args.backend)
    except BackendUnavailable as exc:
        print(f"error: {exc}; use --backend auto o --backend mini", file=sys.stderr)
        return 2

    print(f"  lector YAML: {backend_used}")
    print()
    for check in checks:
        if check.ok and args.quiet:
            continue
        state = "PASS " if check.ok else "FALLO"
        detail = f" — {check.detail}" if check.detail else ""
        print(f"  {state}  {check.ident:<26} {check.title}{detail}")

    total = len(checks)
    passed = sum(1 for check in checks if check.ok)
    failed = [check for check in checks if not check.ok]
    print()
    print(f"  Comprobaciones: {total} ({passed} PASS, {len(failed)} FALLO)")
    if failed:
        print(f"  Resultado: FALLO ({len(failed)} de {total})")
        for check in failed:
            print(f"    - {check.ident}: {check.title}" + (f" ({check.detail})" if check.detail else ""))
        return 1
    print("  Resultado: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
