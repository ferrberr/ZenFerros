#!/usr/bin/env python3
"""Reproducible benchmark harness for Zen vs C/C++/Rust.

Rules enforced here:
  * every implementation of a benchmark receives the same inputs;
  * the printed checksum must be identical across languages before any timing;
  * timing excludes compilation, includes process start, and is repeated;
  * results are reported as medians with variability, never as a single sample;
  * a language whose toolchain is missing is reported as unavailable, not skipped
    silently and never estimated.

Zig is not installed on this host; the harness records that explicitly.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import resource
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "benchmarks/build"
RESULTS = ROOT / "benchmarks/results"
ZEN = ROOT / "zen/compiler/target/release/zen"

BENCHMARKS = {
    "arith": {
        "desc": "50M wrapping 64-bit LCG multiply-add with 32-bit fold",
        "zen": "benchmarks/zen/arith.zen",
        "c": "benchmarks/c/arith.c",
        "cpp": "benchmarks/cpp/arith.cpp",
        "rust": "benchmarks/rust/arith.rs",
    },
    "collatz": {
        "desc": "Collatz step count over 1..=500k (branch-heavy, no recursion)",
        "zen": "benchmarks/zen/collatz.zen",
        "c": "benchmarks/c/collatz.c",
        "cpp": "benchmarks/cpp/collatz.cpp",
        "rust": "benchmarks/rust/collatz.rs",
    },
    "mem": {
        "desc": "16 MiB volatile sequential byte write + read (malloc)",
        "zen": "benchmarks/zen/mem.zen",
        "c": "benchmarks/c/mem.c",
        "cpp": "benchmarks/cpp/mem.cpp",
        "rust": "benchmarks/rust/mem.rs",
    },
    "sort": {
        "desc": "in-place heapsort of 500k u32 with volatile access",
        "zen": "benchmarks/zen/sort.zen",
        "c": "benchmarks/c/sort.c",
        "cpp": "benchmarks/cpp/sort.cpp",
        "rust": "benchmarks/rust/sort.rs",
    },
}

LANGS = ["zen", "c", "cpp", "rust"]


def toolchains() -> dict:
    found = {}
    for lang, tool in (("c", "cc"), ("cpp", "g++"), ("rust", "rustc"),
                       ("clang", "clang"), ("zig", "zig")):
        path = shutil.which(tool)
        found[lang] = {"tool": tool, "path": path, "available": bool(path)}
        if path:
            try:
                found[lang]["version"] = subprocess.run(
                    [path, "--version"], capture_output=True, text=True, timeout=10
                ).stdout.splitlines()[0]
            except (OSError, subprocess.SubprocessError):
                found[lang]["version"] = "unknown"
    zen_version = "unknown"
    if ZEN.exists():
        try:
            zen_version = subprocess.run([str(ZEN), "version"], capture_output=True, text=True,
                                         timeout=10).stdout.strip() or "unknown"
        except (OSError, subprocess.SubprocessError):
            pass
    found["zen"] = {
        "path": str(ZEN),
        "available": ZEN.exists(),
        "version": zen_version,
        "cc_env": os.environ.get("CC", "cc"),
    }
    return found


def affinity_supported(cpu: int | None) -> bool:
    """Probe pinning in the parent, restoring the original mask immediately."""
    if cpu is None:
        return False
    original = os.sched_getaffinity(0)
    try:
        os.sched_setaffinity(0, {cpu})
        return True
    except Exception:
        return False
    finally:
        try:
            os.sched_setaffinity(0, original)
        except Exception:
            pass


def host_info() -> dict:
    cpu = "unknown"
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    return {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu": cpu,
        "python": platform.python_version(),
        "loadavg": list(os.getloadavg()) if hasattr(os, "getloadavg") else None,
        "cpu_count": os.cpu_count(),
    }


def build_commands(lang: str, source: Path, output: Path) -> list[str]:
    if lang == "zen":
        return [str(ZEN), "build", str(source), "--release", "-o", str(output)]
    if lang == "c":
        return ["cc", "-std=c11", "-O2", "-o", str(output), str(source)]
    if lang == "cpp":
        return ["g++", "-std=c++17", "-O2", "-o", str(output), str(source)]
    if lang == "rust":
        return ["rustc", "-O", "-o", str(output), str(source)]
    raise ValueError(lang)


def build_one(lang: str, name: str, spec: dict, available: dict) -> dict:
    source = ROOT / spec[lang]
    output = BUILD / lang / name
    output.parent.mkdir(parents=True, exist_ok=True)
    if not available.get(lang, {}).get("available"):
        return {"built": False, "reason": f"{lang} toolchain unavailable"}
    started = time.perf_counter()
    result = subprocess.run(build_commands(lang, source, output), capture_output=True, text=True, timeout=180)
    seconds = time.perf_counter() - started
    if result.returncode != 0:
        raise RuntimeError(f"build failed for {lang}/{name}:\n{result.stdout}{result.stderr}")
    return {"built": True, "binary": str(output), "bytes": output.stat().st_size, "build_seconds": seconds}


def run_once(binary: Path, timeout: float) -> tuple[str, float]:
    started = time.perf_counter()
    result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=timeout)
    seconds = time.perf_counter() - started
    if result.returncode != 0:
        raise RuntimeError(f"{binary} exited {result.returncode}: {result.stderr}")
    return result.stdout.strip(), seconds


def timed_interleaved(binaries: dict[str, Path], reps: int, warmup: int,
                      cpu: int | None, timeout: float) -> dict[str, list[int]]:
    """Time each language once per repetition, round-robin.

    Interleaving cancels slow periods of the shared host (SMT sibling activity,
    frequency changes) that would otherwise bias whichever language ran last.
    """
    pinned = cpu is not None
    effective_pin = pinned

    def affinity():
        if not pinned:
            return None
        try:
            os.sched_setaffinity(0, {cpu})
        except Exception:
            pass
        return None

    def run(binary: Path) -> None:
        nonlocal pinned, effective_pin
        try:
            subprocess.run([str(binary)], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=timeout,
                           preexec_fn=affinity if pinned else None)
        except subprocess.SubprocessError:
            # Some sandboxes reject preexec_fn; fall back to unpinned execution.
            pinned = False
            effective_pin = False
            subprocess.run([str(binary)], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=timeout)

    def child_cpu_ns() -> int:
        usage = resource.getrusage(resource.RUSAGE_CHILDREN)
        return int((usage.ru_utime + usage.ru_stime) * 1_000_000_000)

    langs = sorted(binaries)
    for _ in range(warmup):
        for lang in langs:
            run(binaries[lang])
    cpu: dict[str, list[int]] = {lang: [] for lang in langs}
    wall: dict[str, list[int]] = {lang: [] for lang in langs}
    for _ in range(reps):
        for lang in langs:
            before = child_cpu_ns()
            started = time.perf_counter_ns()
            run(binaries[lang])
            wall[lang].append(time.perf_counter_ns() - started)
            cpu[lang].append(child_cpu_ns() - before)
    return {"cpu": cpu, "wall": wall, "pinned": effective_pin}


def summarize(samples: list[int]) -> dict:
    ordered = sorted(samples)
    return {
        "samples_ns": samples,
        "median_ns": int(statistics.median(samples)),
        "min_ns": ordered[0],
        "mean_ns": int(statistics.fmean(samples)),
        "stdev_ns": int(statistics.stdev(samples)) if len(samples) > 1 else 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reps", type=int, default=7, help="timed repetitions (default 7)")
    parser.add_argument("--warmup", type=int, default=2, help="warmup runs (default 2)")
    parser.add_argument("--filter", default="", help="only benchmarks containing this substring")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--md", type=Path)
    args = parser.parse_args()
    if args.reps < 1 or args.warmup < 0:
        parser.error("reps must be >=1 and warmup >=0")
    if not ZEN.exists():
        print(f"error: build the compiler first: {ZEN} not found", file=sys.stderr)
        return 2

    BUILD.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    available = toolchains()
    try:
        cpu = min(os.sched_getaffinity(0))
    except (AttributeError, OSError, ValueError):
        cpu = None
    affinity_ok = affinity_supported(cpu)
    if not affinity_ok:
        cpu = None

    selected = [name for name in BENCHMARKS if args.filter in name]
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "host": host_info(),
        "toolchains": available,
        "config": {"warmup": args.warmup, "reps": args.reps, "cpu_affinity": cpu,
                   "cpu_affinity_effective": affinity_ok,
                   "timing": "primary: child CPU time (getrusage RUSAGE_CHILDREN, interleaved); "
                             "secondary: wall clock per process run, includes startup"},
        "benchmarks": {},
        "notes": [
            "Compilation time and binary size are reported separately from runtime.",
            "Checksums are compared across languages before timing; a mismatch aborts.",
            "No claim of superiority is made from these numbers alone.",
        ],
    }

    print(f"host: {report['host']['cpu']}")
    for lang in LANGS:
        info = available[lang]
        print(f"toolchain {lang}: {'ok' if info['available'] else 'UNAVAILABLE'}"
              + (f" ({info.get('version')})" if info.get('version') else ""))

    for name in selected:
        spec = BENCHMARKS[name]
        print(f"\n[{name}] {spec['desc']}")
        builds = {}
        for lang in LANGS:
            builds[lang] = build_one(lang, name, spec, available)
        checksums = {}
        for lang in LANGS:
            if builds[lang]["built"]:
                checksums[lang], _ = run_once(Path(builds[lang]["binary"]), args.timeout)
        reference = checksums.get("c")
        if reference is None:
            print(f"error: C reference unavailable for {name}", file=sys.stderr)
            return 3
        mismatches = {k: v for k, v in checksums.items() if v != reference}
        if mismatches:
            print(f"error: checksum mismatch in {name}: {mismatches} != C {reference}", file=sys.stderr)
            return 4
        entry = {"desc": spec["desc"], "checksum": reference, "results": {}}
        binaries = {lang: Path(builds[lang]["binary"]) for lang in LANGS if builds[lang]["built"]}
        interleaved = timed_interleaved(binaries, args.reps, args.warmup, cpu, args.timeout)
        for lang in LANGS:
            if not builds[lang]["built"]:
                entry["results"][lang] = {"built": False, "reason": builds[lang]["reason"]}
                continue
            cpu_stats = summarize(interleaved["cpu"][lang])
            wall_stats = summarize(interleaved["wall"][lang])
            entry["results"][lang] = {
                "built": True,
                "binary_bytes": builds[lang]["bytes"],
                "build_seconds": round(builds[lang]["build_seconds"], 4),
                "cpu_samples_ns": cpu_stats.pop("samples_ns"),
                "cpu_median_ns": cpu_stats["median_ns"],
                "cpu_min_ns": cpu_stats["min_ns"],
                "cpu_mean_ns": cpu_stats["mean_ns"],
                "cpu_stdev_ns": cpu_stats["stdev_ns"],
                "wall_samples_ns": wall_stats.pop("samples_ns"),
                "wall_median_ns": wall_stats["median_ns"],
                "wall_min_ns": wall_stats["min_ns"],
                "wall_mean_ns": wall_stats["mean_ns"],
                "wall_stdev_ns": wall_stats["stdev_ns"],
            }
        c_cpu = entry["results"]["c"]["cpu_median_ns"]
        for lang in LANGS:
            result = entry["results"][lang]
            if result.get("built"):
                result["ratio_to_c_cpu"] = round(result["cpu_median_ns"] / c_cpu, 4)
                print(f"  {lang:5s} CPU median {result['cpu_median_ns']/1e6:8.3f} ms "
                      f"(min {result['cpu_min_ns']/1e6:8.3f}, stdev {result['cpu_stdev_ns']/1e6:6.3f})  "
                      f"wall {result['wall_median_ns']/1e6:8.3f} ms  "
                      f"x{result['ratio_to_c_cpu']:.3f} vs C  ({result['binary_bytes']} B)")
            else:
                print(f"  {lang:5s} unavailable: {result['reason']}")
        report["benchmarks"][name] = entry
        report["config"]["cpu_affinity_effective"] = affinity_ok and interleaved["pinned"]

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = args.json or RESULTS / f"bench-{stamp}.json"
    md_path = args.md or RESULTS / f"bench-{stamp}.md"
    report["artifacts"] = {"json": str(json_path), "markdown": str(md_path)}
    json_path.write_text(json.dumps(report, indent=2) + "\n")
    md_path.write_text(markdown(report))
    print(f"\nresults: {json_path}\nsummary: {md_path}")
    return 0


def markdown(report: dict) -> str:
    host = report["host"]
    lines = [
        "# Zen benchmark results",
        "",
        f"- Fecha UTC: `{report['timestamp_utc']}`",
        f"- Host: `{host['platform']}` / `{host['cpu']}`",
        f"- Python: `{host['python']}`; loadavg al inicio: `{host['loadavg']}`",
        f"- Configuración: warmup={report['config']['warmup']}, reps={report['config']['reps']}, "
        f"afinidad CPU={report['config']['cpu_affinity']}",
        f"- Timing: {report['config']['timing']}",
        "",
        "| Bench | Lenguaje | CPU mediana (ms) | CPU mín (ms) | CPU desv (ms) | pared mediana (ms) | vs C (CPU) | Binario (B) | Build (s) |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, entry in report["benchmarks"].items():
        for lang in LANGS:
            r = entry["results"].get(lang, {})
            if not r.get("built"):
                lines.append(f"| {name} | {lang} | — | — | — | — | — | — | no disponible |")
                continue
            lines.append(
                f"| {name} | {lang} | {r['cpu_median_ns']/1e6:.3f} | {r['cpu_min_ns']/1e6:.3f} | "
                f"{r['cpu_stdev_ns']/1e6:.3f} | {r['wall_median_ns']/1e6:.3f} | "
                f"x{r['ratio_to_c_cpu']:.3f} | {r['binary_bytes']} | {r['build_seconds']:.3f} |"
            )
    lines += [
        "",
        "## Lectura correcta de esta tabla",
        "",
        "- Todos los lenguajes ejecutan el mismo algoritmo con los mismos datos y verifican el mismo checksum.",
        "- Métrica primaria: tiempo de CPU del proceso hijo (getrusage), que no se ve afectado por "
        "desalojos del planificador del host compartido; el tiempo de pared se incluye como referencia.",
        "- Las cifras incluyen arranque de proceso y son medidas de un host compartido; "
        "no son comparaciones absolutas entre lenguajes ni predicen otro hardware.",
        "- Zen usa el backend C11 con `cc -O2`; C usa `cc -O2`; C++ `g++ -O2`; Rust `rustc -O`. "
        "Que Zen y C compartan backend es una propiedad del bootstrap actual y se declara explícitamente.",
        "- Zig no está instalado en este host: se marca como no disponible, sin estimaciones.",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
