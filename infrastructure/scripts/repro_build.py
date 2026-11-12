#!/usr/bin/env python3
"""Evidencia de builds reproducibles locales de Zen/Ferros (TASK-908).

Que hace:
  1. Usa el compilador release `zen/compiler/target/release/zen`; si no existe
     lo construye con cargo (offline) en un target temporal, sin tocar el repo.
  2. Genera dos veces el C de hello/factorial/arrays/structs con
     `zen build <src> --emit c --release` y compara los bytes.
  3. Ejecuta build_user/build_kernel (release) dos veces en directorios
     temporales distintos y compara kernel.o, ferros-x86_64.elf,
     ferros-multiboot.elf y ferros-user.elf.
  4. Escribe un manifiesto JSON en un directorio temporal y resume por stdout.
  5. Devuelve 0 solo si todos los artefactos comparados coinciden.

Modos:
  --quick   solo C generado + ELF de usuario (sin kernel).
  (defecto) C + usuario + kernel.

Nada de lo generado se escribe en el repositorio: los fuentes C, objetos, ELF,
logs y el manifiesto viven bajo un directorio temporal `zenferros-repro-*`, que
se conserva para poder inspeccionar la evidencia. Solo si falta el compilador se
invoca cargo; en ese caso el target tambien es temporal (`CARGO_TARGET_DIR`).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

# Los imports de build_ferros/build_user no deben dejar .pyc nuevos en el repo.
sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "infrastructure/scripts"
ZEN = ROOT / "zen/compiler/target/release/zen"
CARGO_MANIFEST = "zen/compiler/Cargo.toml"
CARGO_HOME = ROOT / ".cargo"

C_EXAMPLES = ("hello", "factorial", "arrays", "structs")
ALL_ARTIFACTS = (
    "kernel.o",
    "ferros-x86_64.elf",
    "ferros-multiboot.elf",
    "ferros-user.elf",
)
QUICK_ARTIFACTS = ("ferros-user.elf",)

# Secciones que pueden variar entre invocaciones sin afectar al codigo/layout
# relevante. Se eliminan solo para diagnosticar una diferencia; el PASS normal
# exige bytes identicos.
METADATA_SECTIONS = (".comment", ".note.gnu.build-id")

TIMEOUTS = {
    "version": 15.0,
    "cargo": 600.0,
    "zen_build": 120.0,
    "inspect": 60.0,
}

# Entradas de build_ferros.build_kernel; se registran como procedencia.
KERNEL_UNITS = (
    "arch/x86_64/abi.zen",
    "drivers/serial.zen",
    "memory.zen",
    "interrupts.zen",
    "scheduler.zen",
    "vfs.zen",
    "userspace.zen",
    "runtime.zen",
    "main.zen",
)

# Fuentes no-Zen y scripts de enlace que tambien entran en el build.
KERNEL_EXTRA_INPUTS = (
    "ferros/boot/entry.S",
    "ferros/boot/linker.ld",
    "ferros/kernel/arch/x86_64/io.S",
    "ferros/kernel/arch/x86_64/interrupts.S",
    "ferros/kernel/arch/x86_64/context.S",
    "ferros/kernel/arch/x86_64/userspace.S",
)


def _digests(paths) -> list[dict]:
    return [source_digest(path) for path in paths if path.is_file()]

SECTION_LINE = re.compile(
    r"^\s*\[\s*\d+\]\s+(\S+)\s+(\S+)\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)"
)


class ReproError(RuntimeError):
    """Fallo de preparacion o de un paso que impide seguir comparando."""


def log(message: str = "") -> None:
    print(message, flush=True)


def tail(text: str | None, limit: int = 1200) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else "..." + text[-limit:]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def human_bytes(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KiB"
    return f"{size / (1024 * 1024):.2f} MiB"


def format_seconds(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.2f}s"
    minutes, remainder = divmod(seconds, 60)
    return f"{int(minutes)}m {remainder:04.1f}s"


def run(command, *, timeout: float, env: dict[str, str] | None = None):
    """Ejecuta sin shell, con timeout, y devuelve (resultado, segundos)."""
    argv = [str(part) for part in command]
    environment = os.environ.copy()
    # Salida estable para versiones y readelf (el repo se usa en es_ES).
    environment["LC_ALL"] = "C"
    if env:
        environment.update(env)
    started = time.perf_counter()
    try:
        result = subprocess.run(
            argv,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=environment,
        )
    except FileNotFoundError as exc:
        raise ReproError(f"no se encontro el ejecutable {argv[0]!r}") from exc
    except subprocess.TimeoutExpired as exc:
        raise ReproError(f"timeout de {timeout:.0f}s: {' '.join(argv)}") from exc
    except OSError as exc:
        raise ReproError(f"no se pudo ejecutar {argv[0]!r}: {exc}") from exc
    return result, time.perf_counter() - started


def probe_version(
    name: str, executable, args: tuple[str, ...] = ("--version",)
) -> dict:
    """Version de una herramienta; no falla si no esta instalada."""
    record: dict = {"name": name, "command": f"{executable} {' '.join(args)}"}
    resolved = shutil.which(str(executable))
    if resolved is None and Path(str(executable)).is_file():
        resolved = str(Path(str(executable)).resolve())
    if resolved is None:
        record.update(found=False)
        return record
    record.update(found=True, path=resolved)
    try:
        result, _ = run([resolved, *args], timeout=TIMEOUTS["version"])
    except ReproError as exc:
        record.update(error=str(exc))
        return record
    text = ((result.stdout or "") + (result.stderr or "")).strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    record.update(
        exit=result.returncode,
        version=lines[0] if lines else "",
        output=text,
    )
    return record


def newest_compiler_input() -> float:
    paths = list((ROOT / "zen/compiler/src").rglob("*.rs"))
    paths.append(ROOT / "zen/compiler/Cargo.toml")
    for extra in ("Cargo.lock",):
        candidate = ROOT / "zen/compiler" / extra
        if candidate.exists():
            paths.append(candidate)
    return max(path.stat().st_mtime for path in paths)


def cargo_environment(run_dir: Path) -> dict[str, str]:
    """CARGO_HOME temporal que reutiliza el registro offline del repo.

    Cargo escribe .global-cache/.package-cache en CARGO_HOME; para no tocar
    .cargo/ del repo se enlaza solo el registro (solo lectura efectiva con
    --offline) y el resto del home vive en el directorio temporal.
    """
    env = {"CARGO_TARGET_DIR": str(run_dir / "cargo-target")}
    if CARGO_HOME.is_dir():
        home = run_dir / "cargo-home"
        home.mkdir(parents=True, exist_ok=True)
        registry = CARGO_HOME / "registry"
        linked = home / "registry"
        if registry.is_dir() and not linked.exists():
            linked.symlink_to(registry, target_is_directory=True)
        env["CARGO_HOME"] = str(home)
    return env


def resolve_compiler(rebuild: bool, no_build: bool, run_dir: Path) -> tuple[Path, dict]:
    """Devuelve el binario zen release y su registro de procedencia."""
    info: dict = {
        "expected_path": str(ZEN),
        "built": False,
        "stale": None,
        "cargo_build_seconds": None,
        "cargo_target_dir": None,
    }
    if ZEN.is_file() and not rebuild:
        newest = newest_compiler_input()
        info["stale"] = ZEN.stat().st_mtime < newest
        info["path"] = str(ZEN)
        return ZEN, info
    if no_build:
        raise ReproError(
            f"no existe el compilador release {ZEN} y se paso --no-build; "
            "omite --no-build para construirlo con cargo en un target temporal, "
            "o compilalo a mano con: CARGO_HOME=$PWD/.cargo cargo build --release "
            "--offline --manifest-path zen/compiler/Cargo.toml"
        )
    target_dir = run_dir / "cargo-target"
    env = cargo_environment(run_dir)
    command = ["cargo", "build", "--release", "--offline", "--manifest-path", CARGO_MANIFEST]
    log(f"Compilador release ausente o --rebuild: {' '.join(command)}")
    result, elapsed = run(command, timeout=TIMEOUTS["cargo"], env=env)
    if result.returncode:
        raise ReproError(
            "cargo build del compilador fallo:\n" + tail(result.stdout + result.stderr)
        )
    built = target_dir / "release" / "zen"
    if not built.is_file():
        raise ReproError(f"cargo no produjo el binario esperado en {built}")
    info.update(
        path=str(built),
        built=True,
        cargo_build_seconds=round(elapsed, 4),
        cargo_target_dir=str(target_dir),
        command=" ".join(command),
    )
    return built, info


def check_compiler_version(zen: Path, info: dict) -> dict:
    # `zen --version` (clap) solo imprime "zen X"; el subcomando `version`
    # declara el perfil de build, que es lo que hay que exigir.
    record = probe_version("zen", zen, args=("version",))
    if not record.get("found") or record.get("exit", 1) != 0:
        raise ReproError(f"no se pudo ejecutar {zen} version: {record}")
    output = record.get("output", "")
    if "Compiler build: release" not in output:
        raise ReproError(
            "el binario zen no es release; `zen version` no declara "
            f"'Compiler build: release':\n{tail(output)}"
        )
    record["binary_sha256"] = sha256_file(zen)
    record["binary_bytes"] = zen.stat().st_size
    info["version"] = record.get("version", "")
    return record


def first_diff_offset(left: bytes, right: bytes) -> int | None:
    limit = min(len(left), len(right))
    chunk = 4096
    for start in range(0, limit, chunk):
        end = min(start + chunk, limit)
        if left[start:end] != right[start:end]:
            for index in range(start, end):
                if left[index] != right[index]:
                    return index
    if len(left) != len(right):
        return limit
    return None


def read_sections(path: Path) -> dict:
    """sha256 por seccion (solo secciones con contenido en el fichero)."""
    try:
        result, _ = run(["readelf", "-SW", path], timeout=TIMEOUTS["inspect"])
    except ReproError:
        return {}
    if result.returncode:
        return {}
    data = Path(path).read_bytes()
    sections: dict = {}
    for line in result.stdout.splitlines():
        match = SECTION_LINE.match(line)
        if not match:
            continue
        name, kind, _address, offset, size = match.groups()
        offset, size = int(offset, 16), int(size, 16)
        if kind in ("NOBITS", "NULL"):
            sections[name] = {"kind": kind, "size": size, "sha256": None}
            continue
        if offset + size > len(data):
            sections[name] = {"kind": kind, "size": size, "sha256": None}
            continue
        sections[name] = {
            "kind": kind,
            "size": size,
            "sha256": sha256_bytes(data[offset:offset + size]),
        }
    return sections


def normalized_sha256(path: Path, output: Path) -> str | None:
    """sha256 tras quitar secciones de metadatos no deterministas."""
    output.parent.mkdir(parents=True, exist_ok=True)
    command = ["objcopy"]
    for section in METADATA_SECTIONS:
        command += ["--remove-section", section]
    command += [path, output]
    try:
        result, _ = run(command, timeout=TIMEOUTS["inspect"])
    except ReproError:
        return None
    if result.returncode or not output.is_file():
        return None
    return sha256_file(output)


def compare_artifact(name: str, path_a: Path, path_b: Path, run_dir: Path) -> dict:
    record = {
        "name": name,
        "path_a": str(path_a),
        "path_b": str(path_b),
    }
    if not path_a.is_file() or not path_b.is_file():
        record.update(status="FAIL", error="artefacto ausente")
        return record
    data_a = path_a.read_bytes()
    data_b = path_b.read_bytes()
    record.update(
        bytes_a=len(data_a),
        bytes_b=len(data_b),
        sha256_a=sha256_bytes(data_a),
        sha256_b=sha256_bytes(data_b),
    )
    if data_a == data_b:
        record.update(status="PASS", identical=True)
        return record

    record["identical"] = False
    record["first_diff_offset"] = first_diff_offset(data_a, data_b)
    sections_a = read_sections(path_a)
    sections_b = read_sections(path_b)
    differing = sorted(
        section
        for section in set(sections_a) | set(sections_b)
        if sections_a.get(section, {}).get("sha256")
        != sections_b.get(section, {}).get("sha256")
    )
    record["differing_sections"] = differing

    normalized_a = normalized_sha256(
        path_a, run_dir / "normalized" / f"{name}.a"
    )
    normalized_b = normalized_sha256(
        path_b, run_dir / "normalized" / f"{name}.b"
    )
    record["sha256_normalized_a"] = normalized_a
    record["sha256_normalized_b"] = normalized_b
    only_metadata = normalized_a is not None and normalized_a == normalized_b
    if only_metadata:
        record.update(
            status="PASS_METADATA",
            note=(
                "difiere solo en metadatos no relevantes "
                f"({', '.join(METADATA_SECTIONS)}); el contenido normalizado coincide"
            ),
        )
    else:
        record.update(
            status="FAIL",
            error=(
                "el contenido relevante difiere"
                + (f" en secciones: {', '.join(differing)}" if differing else "")
            ),
        )
    return record


def check_c_sources(zen: Path, run_dir: Path) -> list[dict]:
    results = []
    for name in C_EXAMPLES:
        source = ROOT / "zen/examples" / f"{name}.zen"
        work = run_dir / "c" / name
        work.mkdir(parents=True, exist_ok=True)
        record: dict = {
            "name": name,
            "source": str(source),
            "source_sha256": sha256_file(source),
        }
        try:
            first, seconds_a = run(
                [zen, "build", source, "--emit", "c", "-o", work / "a.c", "--release"],
                timeout=TIMEOUTS["zen_build"],
            )
            second, seconds_b = run(
                [zen, "build", source, "--emit", "c", "-o", work / "b.c", "--release"],
                timeout=TIMEOUTS["zen_build"],
            )
            record.update(seconds_a=round(seconds_a, 4), seconds_b=round(seconds_b, 4))
            for tag, result in (("a", first), ("b", second)):
                if result.returncode:
                    record.update(
                        status="FAIL",
                        error=(
                            f"zen build ({tag}) exit={result.returncode}: "
                            f"{tail(result.stdout + result.stderr)}"
                        ),
                    )
            if record.get("status") == "FAIL":
                results.append(record)
                continue
            path_a, path_b = work / "a.c", work / "b.c"
            if not path_a.is_file() or not path_b.is_file():
                record.update(status="FAIL", error="zen build no genero el fichero C")
                results.append(record)
                continue
            data_a = path_a.read_bytes()
            data_b = path_b.read_bytes()
            identical = data_a == data_b
            record.update(
                path_a=str(path_a),
                path_b=str(path_b),
                bytes=len(data_a),
                sha256_a=sha256_bytes(data_a),
                sha256_b=sha256_bytes(data_b),
                identical=identical,
                status="PASS" if identical else "FAIL",
            )
            if not identical:
                offset = first_diff_offset(data_a, data_b)
                record.update(
                    first_diff_offset=offset,
                    error="el C generado difiere entre las dos ejecuciones",
                )
        except ReproError as exc:
            record.update(status="FAIL", error=str(exc))
        results.append(record)
    return results


def source_digest(path: Path) -> dict:
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
    }


def check_ferros(zen: Path, run_dir: Path, quick: bool) -> dict:
    artifacts = QUICK_ARTIFACTS if quick else ALL_ARTIFACTS
    builds = []
    paths: dict[str, dict[str, Path]] = {}
    kernel_results: dict[str, dict] = {}

    for tag in ("run1", "run2"):
        base = run_dir / "ferros" / tag
        kernel_dir = base / "kernel"
        user_dir = base / "user"
        entry: dict = {
            "tag": tag,
            "kernel_dir": str(kernel_dir),
            "user_dir": str(user_dir),
        }
        try:
            started = time.perf_counter()
            user = _build_user(zen, user_dir)
            entry["user_wall_seconds"] = round(time.perf_counter() - started, 4)
            entry["user_build_seconds"] = user.get("build_seconds")
            entry["user_artifact"] = user.get("artifact_path")
        except Exception as exc:  # build_user puede lanzar RuntimeError/Timeout
            entry["user_status"] = "FAIL"
            entry["user_error"] = tail(str(exc))
        if not quick:
            try:
                started = time.perf_counter()
                kernel = _build_kernel(zen, kernel_dir)
                entry["kernel_wall_seconds"] = round(time.perf_counter() - started, 4)
                entry["kernel_build_seconds"] = kernel.get("build_seconds")
                entry["kernel_artifact"] = kernel.get("image_path")
                kernel_results[tag] = kernel
            except Exception as exc:
                entry["kernel_status"] = "FAIL"
                entry["kernel_error"] = tail(str(exc))
        builds.append(entry)
        paths[tag] = {
            "kernel.o": kernel_dir / "kernel.o",
            "ferros-x86_64.elf": kernel_dir / "ferros-x86_64.elf",
            "ferros-multiboot.elf": kernel_dir / "ferros-multiboot.elf",
            "ferros-user.elf": user_dir / "ferros-user.elf",
        }

    comparisons = [
        compare_artifact(name, paths["run1"][name], paths["run2"][name], run_dir)
        for name in artifacts
    ]

    input_checks = []
    if not quick:
        combined = [run_dir / "ferros" / tag / "kernel" / "kernel.zen" for tag in ("run1", "run2")]
        if all(path.is_file() for path in combined):
            hashes = [sha256_file(path) for path in combined]
            input_checks.append(
                {
                    "name": "kernel.zen combinado",
                    "sha256_a": hashes[0],
                    "sha256_b": hashes[1],
                    "identical": hashes[0] == hashes[1],
                }
            )
    user_main = ROOT / "ferros/user/main.zen"
    user_inputs = _digests(
        [
            user_main,
            ROOT / "ferros/user/entry.S",
            ROOT / "ferros/user/linker.ld",
        ]
    )

    kernel_inputs = _digests(
        [ROOT / "ferros/kernel" / unit for unit in KERNEL_UNITS]
        + [ROOT / path for path in KERNEL_EXTRA_INPUTS]
    )
    build_scripts = _digests(
        [
            SCRIPTS / "build_ferros.py",
            SCRIPTS / "build_user.py",
            SCRIPTS / "repro_build.py",
        ]
    )

    return {
        "builds": builds,
        "artifacts": comparisons,
        "input_checks": input_checks,
        "inputs": {
            "user": user_inputs,
            "kernel_units": kernel_inputs,
            "build_scripts": build_scripts,
        },
        "kernel_meta": {
            tag: {
                "payload": result.get("payload"),
                "image": result.get("image"),
            }
            for tag, result in kernel_results.items()
        },
    }


def _build_user(zen: Path, output: Path):
    # Import local para que --help funcione aunque falte algo del arbol.
    from build_user import build_user

    return build_user(zen, output, True)


def _build_kernel(zen: Path, output: Path):
    from build_ferros import build_kernel

    return build_kernel(zen, output, True)


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


def collect_manifest(args, zen: Path, compiler_info: dict, run_dir: Path, started: float) -> dict:
    toolchain = {
        "cc": probe_version("cc", os.environ.get("CC", "cc")),
        "ld": probe_version("ld", "ld"),
        "rustc": probe_version("rustc", "rustc"),
        "cargo": probe_version("cargo", "cargo"),
    }
    zen_version = check_compiler_version(zen, compiler_info)

    c_results = check_c_sources(zen, run_dir)
    ferros = check_ferros(zen, run_dir, args.quick)

    artifacts = ferros["artifacts"]
    failures = [item for item in c_results if item.get("status") != "PASS"]
    failures += [item for item in artifacts if not str(item.get("status", "")).startswith("PASS")]
    failures += [
        {
            "name": check["name"],
            "status": "FAIL",
            "error": "las entradas combinadas difieren entre los dos builds",
        }
        for check in ferros["input_checks"]
        if not check.get("identical")
    ]
    for build in ferros["builds"]:
        if build.get("user_status") == "FAIL":
            failures.append(
                {
                    "name": f"{build['tag']} usuario",
                    "status": "FAIL",
                    "error": build.get("user_error"),
                }
            )
        if build.get("kernel_status") == "FAIL":
            failures.append(
                {
                    "name": f"{build['tag']} kernel",
                    "status": "FAIL",
                    "error": build.get("kernel_error"),
                }
            )
    metadata_only = [
        item for item in artifacts if item.get("status") == "PASS_METADATA"
    ]
    warnings = []
    if compiler_info.get("stale"):
        warnings.append(
            "el binario release es mas antiguo que zen/compiler/src; "
            "la evidencia describe ese binario, no el fuente actual"
        )
    for item in metadata_only:
        warnings.append(f"{item['name']}: {item.get('note')}")
    missing_tools = [
        name for name, record in toolchain.items() if not record.get("found")
    ]
    if missing_tools:
        warnings.append(f"herramientas no encontradas: {', '.join(missing_tools)}")

    total_seconds = time.perf_counter() - started
    c_seconds = sum(
        item.get("seconds_a", 0.0) + item.get("seconds_b", 0.0) for item in c_results
    )
    ferros_seconds = sum(
        item.get("user_wall_seconds", 0.0) + item.get("kernel_wall_seconds", 0.0)
        for item in ferros["builds"]
    )
    result = "FAIL" if failures else "PASS"

    manifest = {
        "task": "TASK-908",
        "schema": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": "quick" if args.quick else "full",
        "result": result,
        "host": host_info(),
        "repo": {
            "root": str(ROOT),
            "git": (ROOT / ".git").exists(),
            "note": "sin .git: no hay commit ni procedencia VCS; los hashes de entrada son la referencia",
        },
        "toolchain": {
            key: {
                "found": record.get("found", False),
                "path": record.get("path"),
                "version": record.get("version"),
                "exit": record.get("exit"),
                "output": tail(record.get("output"), 800),
            }
            for key, record in toolchain.items()
        },
        "compiler": {
            **compiler_info,
            "version": zen_version.get("version"),
            "version_output": zen_version.get("output"),
            "binary_sha256": zen_version.get("binary_sha256"),
            "binary_bytes": zen_version.get("binary_bytes"),
            "release_verified": "Compiler build: release" in zen_version.get("output", ""),
            "compared_bitwise_across_runs": False,
            "note": "el binario Rust del compilador no se compara entre builds; solo se registra su hash",
        },
        "flags": {
            "c": "zen build <src> --emit c --release (target host por defecto)",
            "user": "zen build <src> --target x86_64-unknown-none --emit obj --release; cc -c -m64 -ffreestanding -fno-pie; ld -m elf_x86_64 -z max-page-size=0x1000 -z noexecstack -nostdlib -static",
            "kernel": "zen build <kernel.zen> --target x86_64-unknown-none --emit obj --release; mismos cc/ld + objcopy -O elf32-i386",
            "cargo": "cargo build --release --offline --manifest-path zen/compiler/Cargo.toml",
        },
        "checks": {
            "c": {
                "runs": 2,
                "sources": list(C_EXAMPLES),
                "seconds": round(c_seconds, 4),
                "results": c_results,
            },
            "ferros": {
                "mode": "quick" if args.quick else "full",
                "artifacts_requested": list(QUICK_ARTIFACTS if args.quick else ALL_ARTIFACTS),
                **ferros,
                "seconds": round(ferros_seconds, 4),
            },
        },
        "timings": {
            "total_seconds": round(total_seconds, 4),
            "c_seconds": round(c_seconds, 4),
            "ferros_seconds": round(ferros_seconds, 4),
            "cargo_build_seconds": compiler_info.get("cargo_build_seconds"),
        },
        "warnings": warnings,
        "failures": [
            {
                "name": item.get("name"),
                "status": item.get("status"),
                "error": item.get("error"),
            }
            for item in failures
        ],
        "limits": [
            "No se compara bit a bit el binario del compilador Rust ni su build de cargo.",
            "No se ejecuta QEMU ni se arranca el kernel: solo se comparan artefactos de build.",
            "No se compila el C generado con cc; se comparan los ficheros C emitidos.",
            "No es CI remoto ni usa un contenedor/toolchain fijado: describe este host.",
            "No hay .git: no existe commit, bisect ni atestacion de procedencia.",
            "El manifiesto contiene rutas temporales, tiempos y fecha; no es reproducible byte a byte.",
            "Un PASS no demuestra reproducibilidad en otro hardware, distro, locale o version de toolchain.",
        ],
    }
    return manifest


def print_summary(manifest: dict, manifest_path: Path) -> None:
    mode = manifest["mode"]
    log()
    log(f"TASK-908 reproducibilidad local — modo {mode}")
    log(f"Host: {manifest['host']['processor']} · {manifest['host']['platform']}")
    log(f"Repo: {manifest['repo']['root']} (git={manifest['repo']['git']})")
    compiler = manifest["compiler"]
    origin = "construido con cargo" if compiler.get("built") else "binario release existente"
    stale = "stale" if compiler.get("stale") else "al dia"
    log(f"Compilador: {compiler.get('path')} ({origin}, {stale})")
    log(f"  version: {compiler.get('version')} · sha256={compiler.get('binary_sha256')}")

    toolchain = manifest["toolchain"]
    log(
        "Toolchain: "
        + " · ".join(
            f"{name}={toolchain[name].get('version') or 'no encontrado'}"
            for name in ("cc", "ld", "rustc", "cargo")
        )
    )

    log()
    log("C generado (zen build --emit c --release, 2 ejecuciones):")
    for item in manifest["checks"]["c"]["results"]:
        status = item.get("status", "FAIL")
        if status == "PASS":
            log(
                f"  {item['name']:<10} PASS  sha256={item['sha256_a']}  "
                f"{human_bytes(item['bytes'])}  "
                f"t={item.get('seconds_a', 0):.4f}s/{item.get('seconds_b', 0):.4f}s"
            )
        else:
            log(f"  {item['name']:<10} {status}  {item.get('error', '')}")

    log()
    title = "Ferros release (2 directorios temporales)"
    if manifest["mode"] == "quick":
        title += " — solo usuario (--quick)"
    log(title + ":")
    for item in manifest["checks"]["ferros"]["artifacts"]:
        status = item.get("status", "FAIL")
        suffix = ""
        if status == "PASS_METADATA":
            suffix = "  [metadatos no relevantes]"
        if status.startswith("PASS"):
            log(
                f"  {item['name']:<22} {status}  sha256={item['sha256_a']}  "
                f"{human_bytes(item['bytes_a'])}{suffix}"
            )
        else:
            log(f"  {item['name']:<22} {status}  {item.get('error', '')}")
    builds = manifest["checks"]["ferros"]["builds"]
    log(
        "  builds: "
        + " · ".join(
            f"{build['tag']} usuario={build.get('user_wall_seconds', 0):.3f}s"
            + (
                f" kernel={build.get('kernel_wall_seconds', 0):.3f}s"
                if "kernel_wall_seconds" in build
                else ""
            )
            for build in builds
        )
    )

    if manifest["warnings"]:
        log()
        log("Avisos:")
        for warning in manifest["warnings"]:
            log(f"  - {warning}")
    if manifest["failures"]:
        log()
        log("Discrepancias/fallos:")
        for failure in manifest["failures"]:
            log(f"  - {failure['name']}: {failure.get('error') or failure.get('status')}")
    else:
        log()
        log("Discrepancias: ninguna")

    timings = manifest["timings"]
    log()
    log(
        f"Tiempo total: {format_seconds(timings['total_seconds'])} "
        f"(C {timings['c_seconds']:.2f}s, Ferros {timings['ferros_seconds']:.2f}s, "
        f"cargo {timings['cargo_build_seconds'] if timings['cargo_build_seconds'] is not None else 'n/a'})"
    )
    log(f"Manifiesto JSON: {manifest_path}")
    log(f"Resultado: {manifest['result']}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Comprueba que dos builds locales consecutivos producen los mismos "
            "artefactos y escribe un manifiesto JSON (TASK-908)."
        )
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--quick",
        action="store_true",
        help="solo C generado + ELF de usuario (omite kernel.o y los dos ELF del kernel)",
    )
    build = parser.add_mutually_exclusive_group()
    build.add_argument(
        "--rebuild",
        action="store_true",
        help="reconstruye el compilador con cargo en un target temporal, aunque exista el release",
    )
    build.add_argument(
        "--no-build",
        action="store_true",
        help="falla si no existe zen/compiler/target/release/zen; nunca invoca cargo",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help="ruta alternativa del manifiesto JSON (por defecto, dentro del directorio temporal)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    os.chdir(ROOT)
    started = time.perf_counter()
    run_dir = Path(tempfile.mkdtemp(prefix="zenferros-repro-"))
    manifest_path = (
        args.manifest.resolve()
        if args.manifest is not None
        else run_dir / "manifest.json"
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    zen: Path | None = None
    compiler_info: dict = {"expected_path": str(ZEN), "built": False}
    try:
        zen, compiler_info = resolve_compiler(args.rebuild, args.no_build, run_dir)
        manifest = collect_manifest(args, zen, compiler_info, run_dir, started)
    except ReproError as exc:
        log(f"FAIL: {exc}")
        manifest = {
            "task": "TASK-908",
            "schema": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "mode": "quick" if args.quick else "full",
            "result": "FAIL",
            "error": str(exc),
            "compiler": compiler_info,
            "timings": {"total_seconds": round(time.perf_counter() - started, 4)},
            "limits": ["Fallo de preparacion: no se compararon todos los artefactos."],
        }
    except Exception as exc:  # noqa: BLE001 - queremos manifiesto incluso ante un bug
        log(f"FAIL inesperado: {exc}")
        manifest = {
            "task": "TASK-908",
            "schema": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "mode": "quick" if args.quick else "full",
            "result": "FAIL",
            "error": f"{type(exc).__name__}: {exc}",
            "timings": {"total_seconds": round(time.perf_counter() - started, 4)},
            "limits": ["Fallo inesperado: ver el error y el arbol temporal."],
        }

    manifest.setdefault("temp_dir", str(run_dir))
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=False) + "\n")
    if "checks" in manifest:
        print_summary(manifest, manifest_path)
    else:
        log()
        log(f"Resultado: FAIL — manifiesto: {manifest_path}")
        if manifest.get("error"):
            log(f"Error: {manifest['error']}")
    return 0 if manifest["result"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
