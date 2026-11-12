#!/usr/bin/env python3
"""Measure GCC optimization flags on the C11 code emitted by Zen (TASK-802).

For every benchmark the pipeline is:

  1. ``zen build benchmarks/zen/<b>.zen --emit c --release -o <tmp>/<b>.c``
  2. compile that exact C with ``cc -std=c11 <flags> -o <tmp>/<b>-<variant>``
  3. run every variant once and require the same checksum as the C reference
  4. time each variant with child CPU time (getrusage RUSAGE_CHILDREN),
     interleaved round-robin inside every repetition, 2 warmup rounds + 7 reps,
     optionally pinned to one CPU
  5. repeat the whole timing suite twice (two passes) and report ratios to
     ``-O2`` from the same pass.

The script is read-only with respect to project sources. It writes the JSON and
Markdown artefacts requested by TASK-802 and keeps build products in a temporary
directory.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import resource
import shlex
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ZEN = ROOT / "zen/compiler/target/release/zen"
BUILD_C = ROOT / "benchmarks/build/c"
RESULTS = ROOT / "benchmarks/results"

BENCHMARKS = ["arith", "collatz", "mem", "sort"]

# Checksums pinned by benchmarks/tests/test_benchmarks.py. They are the
# independent expectation; the prebuilt C binary is additionally checked when
# present.
EXPECTED = {
    "arith": "385904853",
    "collatz": "62134795",
    "mem": "2139062878",
    "sort": "14559707269027860169",
}

VARIANTS = {
    "O2": ["-O2"],
    "O3": ["-O3"],
    "O2-LTO": ["-O2", "-flto"],
    "O3-LTO": ["-O3", "-flto"],
}
VARIANT_ORDER = ["O2", "O3", "O2-LTO", "O3-LTO"]
BASELINE = "O2"

# A variant is only recommended when it is at least 3 % faster than -O2 in every
# benchmark and in both passes, and never slower than -O2.
IMPROVEMENT_THRESHOLD = 0.03
MATERIAL_REGRESSION_RATIO = 1.01


def command_line() -> str:
    return " ".join(shlex.quote(part) for part in [sys.executable, *sys.argv])


def cc_command() -> list[str]:
    return shlex.split(os.environ.get("CC", "cc"))


def child_cpu_ns() -> int:
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    return int((usage.ru_utime + usage.ru_stime) * 1_000_000_000)


def run_captured(command: list[str], timeout: float) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout)


def run_quiet(binary: Path, timeout: float, cpu: int | None) -> None:
    kwargs = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "timeout": timeout,
    }
    if cpu is not None:
        kwargs["preexec_fn"] = lambda: os.sched_setaffinity(0, {cpu})
    result = subprocess.run([str(binary)], **kwargs)
    if result.returncode != 0:
        raise RuntimeError(f"{binary} exited with {result.returncode}")


def checksum(binary: Path, timeout: float) -> str:
    result = run_captured([str(binary)], timeout)
    if result.returncode != 0:
        raise RuntimeError(f"{binary} exited with {result.returncode}: {result.stderr}")
    return result.stdout.strip()


def pin_probe(cpu: int | None) -> bool:
    if cpu is None:
        return False
    try:
        result = subprocess.run(
            [sys.executable, "-c", "import os;print(sorted(os.sched_getaffinity(0)))"],
            capture_output=True,
            text=True,
            timeout=30,
            preexec_fn=lambda: os.sched_setaffinity(0, {cpu}),
        )
        return result.returncode == 0 and result.stdout.strip() == f"[{cpu}]"
    except (OSError, subprocess.SubprocessError):
        return False


def host_info() -> dict:
    cpu = "unknown"
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    try:
        affinity = sorted(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        affinity = []
    return {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "kernel": platform.release(),
        "cpu": cpu,
        "cpu_count": os.cpu_count(),
        "affinity_cpus": affinity,
        "python": platform.python_version(),
        "loadavg": list(os.getloadavg()) if hasattr(os, "getloadavg") else None,
    }


def toolchain_info() -> dict:
    cc = cc_command()
    info = {"cc": shlex.join(cc), "cc_available": bool(shutil.which(cc[0]))}
    if info["cc_available"]:
        result = run_captured([*cc, "--version"], 10)
        info["cc_version"] = result.stdout.splitlines()[0] if result.stdout else "unknown"
    zinfo = {"path": str(ZEN), "available": ZEN.exists()}
    if ZEN.exists():
        result = run_captured([str(ZEN), "version"], 10)
        zinfo["version"] = (result.stdout.strip().splitlines() or ["unknown"])[0]
    return {"compiler": info, "zen": zinfo}


def emit_c(benchmark: str, tmp: Path, timeout: float) -> dict:
    source = ROOT / f"benchmarks/zen/{benchmark}.zen"
    target = tmp / f"{benchmark}.c"
    started = time.perf_counter()
    result = run_captured(
        [str(ZEN), "build", str(source), "--emit", "c", "--release", "-o", str(target)],
        timeout,
    )
    seconds = time.perf_counter() - started
    if result.returncode != 0:
        raise RuntimeError(
            f"zen --emit c failed for {benchmark}:\n{result.stdout}{result.stderr}"
        )
    if not target.is_file():
        raise RuntimeError(f"zen reported success but {target} does not exist")
    return {
        "c_source": str(target),
        "c_bytes": target.stat().st_size,
        "emit_seconds": round(seconds, 4),
    }


def compile_variant(
    benchmark: str, c_source: Path, variant: str, tmp: Path, timeout: float
) -> dict:
    binary = tmp / f"{benchmark}-{variant}"
    command = [*cc_command(), "-std=c11", *VARIANTS[variant], "-o", str(binary), str(c_source)]
    started = time.perf_counter()
    result = run_captured(command, timeout)
    seconds = time.perf_counter() - started
    entry = {
        "flags": VARIANTS[variant],
        "command": shlex.join(command),
        "build_seconds": round(seconds, 4),
    }
    if result.returncode != 0:
        entry.update(
            {
                "available": False,
                "reason": "compile failed",
                "stderr": (result.stderr or result.stdout).strip()[:2000],
            }
        )
        return entry
    entry.update(
        {
            "available": True,
            "binary": str(binary),
            "binary_bytes": binary.stat().st_size,
            "stderr": result.stderr.strip()[:2000],
        }
    )
    return entry


def timed_pass(
    binaries: dict[str, dict[str, Path]],
    benchmarks: list[str],
    variants: list[str],
    reps: int,
    warmup: int,
    timeout: float,
    cpu: int | None,
    order_offset: int,
) -> dict:
    """Time every benchmark/variant once per repetition, round-robin.

    The starting variant rotates with the repetition (plus a per-pass offset) so
    that no variant is systematically first or last. Interleaving spreads slow
    host periods across variants.
    """
    for benchmark in benchmarks:
        available = [v for v in variants if v in binaries[benchmark]]
        for _ in range(warmup):
            for variant in available:
                run_quiet(binaries[benchmark][variant], timeout, cpu)

    samples: dict[str, dict[str, list[int]]] = {
        benchmark: {v: [] for v in variants if v in binaries[benchmark]}
        for benchmark in benchmarks
    }
    wall: dict[str, dict[str, list[int]]] = {
        benchmark: {v: [] for v in variants if v in binaries[benchmark]}
        for benchmark in benchmarks
    }
    schedule: dict[str, list[list[str]]] = {}

    for rep in range(reps):
        for benchmark in benchmarks:
            available = [v for v in variants if v in binaries[benchmark]]
            if not available:
                continue
            offset = (rep + order_offset) % len(available)
            order = available[offset:] + available[:offset]
            schedule.setdefault(benchmark, []).append(order)
            for variant in order:
                binary = binaries[benchmark][variant]
                before = child_cpu_ns()
                started = time.perf_counter_ns()
                run_quiet(binary, timeout, cpu)
                elapsed = time.perf_counter_ns() - started
                samples[benchmark][variant].append(child_cpu_ns() - before)
                wall[benchmark][variant].append(elapsed)

    return {"samples": samples, "wall": wall, "schedule": schedule}


def summarize(samples: list[int]) -> dict:
    ordered = sorted(samples)
    median = int(statistics.median(samples))
    return {
        "samples_ns": samples,
        "median_ns": median,
        "min_ns": ordered[0],
        "max_ns": ordered[-1],
        "mean_ns": int(statistics.fmean(samples)),
        "stdev_ns": int(statistics.stdev(samples)) if len(samples) > 1 else 0,
        "mad_ns": int(statistics.median([abs(x - median) for x in samples])),
    }


def relative(value: float, base: float) -> float:
    return value / base if base else float("nan")


def analyze(passes: list[dict], benchmarks: list[str], variants: list[str]) -> dict:
    analysis: dict[str, dict] = {}
    for benchmark in benchmarks:
        present = [v for v in variants if v in passes[0]["benchmarks"][benchmark]["results"]]
        if BASELINE not in present:
            continue
        entry: dict[str, dict] = {}
        for variant in present:
            ratios = []
            cvs = []
            for pass_report in passes:
                result = pass_report["benchmarks"][benchmark]["results"][variant]
                base = pass_report["benchmarks"][benchmark]["results"][BASELINE]["median_ns"]
                ratios.append(relative(result["median_ns"], base))
                cvs.append(relative(result["stdev_ns"], result["median_ns"]) * 100)
            ratio1 = ratios[0]
            ratio2 = ratios[1] if len(ratios) > 1 else None
            consistent = len(ratios) > 1 and all(
                r < 1.0 - IMPROVEMENT_THRESHOLD for r in ratios
            )
            any_slowdown = any(r > 1.0 for r in ratios)
            material_regression = len(ratios) > 1 and all(
                r > MATERIAL_REGRESSION_RATIO for r in ratios
            )
            entry[variant] = {
                "ratio_pass1": round(ratio1, 4),
                "ratio_pass2": round(ratio2, 4) if ratio2 is not None else None,
                "improvement_pct_pass1": round((1.0 - ratio1) * 100, 2),
                "improvement_pct_pass2": round((1.0 - ratio2) * 100, 2)
                if ratio2 is not None
                else None,
                "improvement_pct_mean": round((1.0 - statistics.fmean(ratios)) * 100, 2),
                "pass_spread_pct": round(
                    abs(ratio1 - ratio2) / statistics.fmean(ratios) * 100, 2
                )
                if ratio2 is not None
                else None,
                "within_pass_cv_pct_max": round(max(cvs), 2),
                "consistent_gt_threshold": consistent,
                "any_slowdown": any_slowdown,
                "material_regression": material_regression,
            }
        analysis[benchmark] = entry
    return analysis


def decide(
    analysis: dict, benchmarks: list[str], variants: list[str], available: dict
) -> dict:
    """Apply the pre-registered criterion and return a defensible decision."""
    checked = [v for v in variants if v != BASELINE]
    qualifying = []
    rejected = []
    for variant in checked:
        if not all(available.get(benchmark, {}).get(variant, False) for benchmark in benchmarks):
            rejected.append({"variant": variant, "reason": "no disponible en alguna carga"})
            continue
        stats = [analysis[b][variant] for b in benchmarks]
        if all(s["consistent_gt_threshold"] for s in stats):
            qualifying.append(
                {
                    "variant": variant,
                    "mean_improvement_pct": round(
                        statistics.fmean(s["improvement_pct_mean"] for s in stats), 2
                    ),
                }
            )
        else:
            indexed = list(zip(benchmarks, stats))
            material = [
                (benchmark, stats_item)
                for benchmark, stats_item in indexed
                if stats_item["material_regression"]
            ]
            weakest_benchmark, weakest = min(
                indexed, key=lambda pair: pair[1]["improvement_pct_mean"]
            )
            if material:
                reason = (
                    "registra una regresión material (>1 %) en "
                    + ", ".join(
                        f"{b} (p1 x{s['ratio_pass1']:.3f}, p2 "
                        + (
                            f"x{s['ratio_pass2']:.3f})"
                            if s["ratio_pass2"] is not None
                            else "n/d)"
                        )
                        for b, s in material
                    )
                )
            elif all(s["improvement_pct_mean"] > 0 for _, s in indexed):
                reason = (
                    "la mejora es uniforme pero no supera el 3 % en todas las cargas "
                    "y pasadas"
                )
            else:
                reason = "la mejora no es uniforme entre cargas"
            rejected.append(
                {
                    "variant": variant,
                    "reason": reason,
                    "weakest_benchmark": weakest_benchmark,
                    "weakest_benchmark_improvement_pct_mean": weakest[
                        "improvement_pct_mean"
                    ],
                }
            )
    if qualifying:
        best = max(qualifying, key=lambda q: q["mean_improvement_pct"])
        return {
            "change_release_flags": True,
            "recommended_variant": best["variant"],
            "recommended_flags": VARIANTS[best["variant"]],
            "criterion": (
                "mejora >3 % frente a -O2 en las cuatro cargas y en ambas pasadas, "
                "sin regresión (ratio > 1.0)"
            ),
            "qualifying": qualifying,
            "rejected": rejected,
        }
    return {
        "change_release_flags": False,
        "recommended_variant": BASELINE,
        "recommended_flags": VARIANTS[BASELINE],
        "criterion": (
            "mejora >3 % frente a -O2 en las cuatro cargas y en ambas pasadas, "
            "sin regresión (ratio > 1.0)"
        ),
        "qualifying": [],
        "rejected": rejected,
        "reason": "ninguna variante cumple el criterio completo en todas las cargas",
    }


def fmt_ms(ns: int) -> str:
    return f"{ns / 1e6:.3f}"


def fmt_load(load: list[float] | None) -> str:
    return ", ".join(f"{value:.2f}" for value in load) if load else "n/d"


def fmt_signed_pct(value: float) -> str:
    return f"{value:+.2f}"


def markdown(report: dict) -> str:
    cfg = report["config"]
    host = report["host"]
    tool = report["toolchains"]
    variants = report["variants"]
    decision = report["decision"]
    lines = [
        "# Flags de optimización del backend C11 de Zen — TASK-802",
        "",
        f"- Fecha UTC: `{report['timestamp_utc']}`",
        f"- Host: `{host['cpu']}` · `{host['platform']}` · loadavg al inicio "
        f"`{fmt_load(host['loadavg'])}` · máscara de CPU `{host['affinity_cpus']}`",
        f"- Compilador: `{tool['compiler'].get('cc_version', 'no disponible')}` "
        f"(`{tool['compiler']['cc']}`) · Zen `{tool['zen'].get('version', 'no disponible')}`",
        f"- Configuración: warmup={cfg['warmup']} rondas, reps={cfg['reps']}, "
        f"pasadas={cfg['passes']}, CPU fijada={cfg['cpu']} "
        f"(efectiva={cfg['cpu_affinity_effective']}), métrica primaria = tiempo de CPU "
        f"del hijo (`getrusage(RUSAGE_CHILDREN)`)",
        f"- Comando: `{report['command']}`",
        "",
        "## Método",
        "",
        "Para cada benchmark se generó C con "
        "`zen build benchmarks/zen/<b>.zen --emit c --release` y se compiló ese mismo "
        "fichero con `cc -std=c11 <flags>`. Antes de medir, cada binario se ejecutó y su "
        "checksum debía coincidir con el del benchmark C; una discrepancia se registra y "
        "esa variante no se mide. Las variantes se ejecutan intercaladas, rotando el orden "
        f"inicial en cada repetición, y la suite completa se repite {cfg['passes']} veces. "
        "Se compara cada variante contra `-O2` **de la misma pasada**. Se incluye el arranque "
        "del proceso y no se incluye la compilación.",
        "",
        "## Checksums",
        "",
        "| Benchmark | Esperado | C de referencia | "
        + " | ".join(variants)
        + " |",
        "|---|---|---|" + "---|" * len(variants),
    ]
    for benchmark in report["benchmarks"]:
        correctness = report["correctness"][benchmark]
        cells = []
        for variant in variants:
            info = correctness["variants"].get(variant, {})
            if info.get("checksum") is None:
                cells.append("no medido" if info.get("available") else "no disponible")
            elif info.get("match"):
                cells.append("OK")
            else:
                cells.append(f"**MISMATCH** `{info['checksum']}`")
        lines.append(
            f"| {benchmark} | `{correctness['expected']}` | "
            f"`{correctness['reference_checksum']}` "
            f"({correctness['reference_source']}) | " + " | ".join(cells) + " |"
        )

    lines += ["", "## Generación y compilación", ""]
    lines += [
        "| Benchmark | C generado (B) | `zen --emit c` (s) |",
        "|---|---:|---:|",
    ]
    for benchmark in report["benchmarks"]:
        entry = report["benchmarks"][benchmark]
        lines.append(
            f"| {benchmark} | {entry['c_bytes']} | {entry['emit_seconds']:.3f} |"
        )
    lines += [
        "",
        "| Benchmark | Variante | Flags | Binario (B) | Δ tamaño vs -O2 | Compilación (s) |",
        "|---|---|---|---:|---:|---:|",
    ]
    for benchmark in report["benchmarks"]:
        builds = report["builds"][benchmark]
        base_bytes = builds.get(BASELINE, {}).get("binary_bytes")
        for variant in variants:
            build = builds.get(variant, {})
            if not build.get("available"):
                lines.append(
                    f"| {benchmark} | {variant} | `{shlex.join(VARIANTS[variant])}` | "
                    "— | — | no disponible |"
                )
                continue
            delta = (
                f"{(build['binary_bytes'] / base_bytes - 1) * 100:+.2f} %"
                if base_bytes
                else "—"
            )
            lines.append(
                f"| {benchmark} | {variant} | `{shlex.join(VARIANTS[variant])}` | "
                f"{build['binary_bytes']} | {delta} | {build['build_seconds']:.3f} |"
            )
    lines.append("")

    lines += ["", "## Resultados por pasada", ""]
    for pass_report in report["passes"]:
        lines += [
            f"### Pasada {pass_report['pass']}",
            "",
            f"loadavg al inicio `{fmt_load(pass_report['loadavg_start'])}` · "
            f"al final `{fmt_load(pass_report['loadavg_end'])}`",
            "",
            "| Benchmark | Variante | Flags | CPU mediana (ms) | CPU mín (ms) | "
            "CPU desv (ms) | vs -O2 |",
            "|---|---|---|---:|---:|---:|---:|",
        ]
        for benchmark in report["benchmarks"]:
            results = pass_report["benchmarks"][benchmark]["results"]
            base = results.get(BASELINE, {}).get("median_ns")
            for variant in variants:
                result = results.get(variant)
                if result is None:
                    lines.append(
                        f"| {benchmark} | {variant} | `{shlex.join(VARIANTS[variant])}` | "
                        "— | — | — | no medida |"
                    )
                    continue
                ratio = relative(result["median_ns"], base) if base else float("nan")
                lines.append(
                    f"| {benchmark} | {variant} | `{shlex.join(VARIANTS[variant])}` | "
                    f"{fmt_ms(result['median_ns'])} | {fmt_ms(result['min_ns'])} | "
                    f"{fmt_ms(result['stdev_ns'])} | x{ratio:.3f} |"
                )
        lines.append("")

    lines += [
        "## Resumen entre pasadas (ratio frente a -O2, menor es mejor)",
        "",
        "| Benchmark | Variante | ratio p1 | ratio p2 | mejora media | "
        "dispersión p1↔p2 | CV intra-pasada máx. | ¿>3 % en ambas? |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for benchmark in report["benchmarks"]:
        for variant in variants:
            if variant == BASELINE:
                continue
            stats = report["analysis"][benchmark].get(variant)
            if not stats:
                lines.append(f"| {benchmark} | {variant} | — | — | — | — | — | no medida |")
                continue
            ratio2 = (
                f"{stats['ratio_pass2']:.3f}"
                if stats["ratio_pass2"] is not None
                else "—"
            )
            spread = (
                f"{stats['pass_spread_pct']:.2f} %"
                if stats["pass_spread_pct"] is not None
                else "—"
            )
            lines.append(
                f"| {benchmark} | {variant} | {stats['ratio_pass1']:.3f} | {ratio2} | "
                f"{fmt_signed_pct(stats['improvement_pct_mean'])} % | {spread} | "
                f"{stats['within_pass_cv_pct_max']:.2f} % | "
                f"{'sí' if stats['consistent_gt_threshold'] else 'no'} |"
            )
    lines.append("")

    lines += ["## Lectura de los datos", ""]
    consistent_hits = []
    for benchmark in report["benchmarks"]:
        stats_for_bench = report["analysis"].get(benchmark, {})
        hits = [
            variant
            for variant in variants
            if variant != BASELINE
            and stats_for_bench.get(variant, {}).get("consistent_gt_threshold")
        ]
        if hits:
            consistent_hits.append(f"`{benchmark}` ({', '.join(hits)})")
        candidates = [
            (variant, stats_for_bench[variant])
            for variant in variants
            if variant != BASELINE and variant in stats_for_bench
        ]
        if not candidates:
            continue
        best_variant, best_stats = max(
            candidates, key=lambda pair: pair[1]["improvement_pct_mean"]
        )
        p1 = f"x{best_stats['ratio_pass1']:.3f}"
        p2 = (
            f"x{best_stats['ratio_pass2']:.3f}"
            if best_stats["ratio_pass2"] is not None
            else "n/d"
        )
        lines.append(
            f"- `{benchmark}`: la menor mediana media es de `{best_variant}` "
            f"({fmt_signed_pct(best_stats['improvement_pct_mean'])} % de mejora media; "
            f"p1 {p1}, p2 {p2})."
        )
    lines.append("")
    if consistent_hits:
        lines.append(
            "Mejoras superiores al 3 % y reproducibles en ambas pasadas: "
            + ", ".join(consistent_hits)
            + ". Ninguna variante las presenta en las cuatro cargas a la vez."
        )
    else:
        lines.append(
            "Ninguna variante presenta una mejora superior al 3 % reproducible en "
            "ambas pasadas para ninguna carga."
        )
    lines.append("")
    lines += ["## Conclusión", ""]
    if decision["change_release_flags"]:
        lines += [
            f"**Recomendación: cambiar los flags de release a "
            f"`{shlex.join(decision['recommended_flags'])}`.**",
            "",
            f"La variante `{decision['recommended_variant']}` supera el umbral del 3 % "
            "en las cuatro cargas y en ambas pasadas, sin regresión. Criterio aplicado: "
            f"{decision['criterion']}. El cambio en `zen/compiler/src/native.rs` queda "
            "fuera de esta tarea y corresponde al Lead.",
        ]
    else:
        lines += [
            "**Recomendación: mantener `-O2`.**",
            "",
            f"Ninguna variante cumple el criterio preregistrado ({decision['criterion']}). "
            "No hay evidencia reproducible de una mejora superior al 3 % en todas las "
            "cargas; cambiar flags sin esa evidencia añadiría riesgo (LTO, compilación "
            "más lenta, binarios distintos) sin beneficio demostrado.",
        ]
        for item in decision.get("rejected", []):
            detail = ""
            if "weakest_benchmark_improvement_pct_mean" in item:
                detail = (
                    f" (peor carga: {item.get('weakest_benchmark', '?')} "
                    f"{fmt_signed_pct(item['weakest_benchmark_improvement_pct_mean'])} %)"
                )
            lines.append(f"- `{item['variant']}`: {item['reason']}{detail}.")
        if consistent_hits:
            lines.append(
                "La señal reproducible se limita a "
                + ", ".join(consistent_hits)
                + "; no se extiende al resto de cargas y no justifica cambiar el flag global."
            )
        lines.append("")
    lines += [
        "Criterio explícito: una variante solo se recomienda si su mediana de CPU es "
        f"más de un {int(IMPROVEMENT_THRESHOLD * 100)} % inferior a la de `-O2` en "
        "**todos** los benchmarks y en **ambas** pasadas, y no es más lenta que `-O2` "
        "en ninguna medición. Las diferencias por debajo de ese umbral no se consideran "
        "señal en este host.",
        "",
        "## Variabilidad y límites",
        "",
    ]
    spreads = [
        s["pass_spread_pct"]
        for b in report["analysis"].values()
        for s in b.values()
        if s.get("pass_spread_pct") is not None
    ]
    cvs = [
        s["within_pass_cv_pct_max"]
        for b in report["analysis"].values()
        for s in b.values()
        if "within_pass_cv_pct_max" in s
    ]
    unavailable_variants = sorted(
        {
            variant
            for benchmark in report["benchmarks"]
            for variant, build in report["builds"][benchmark].items()
            if not build.get("available")
        }
    )
    lines += [
        f"- Dispersión entre pasadas: {min(spreads):.2f}–{max(spreads):.2f} % "
        "según benchmark y variante." if spreads else "- Sin datos de dispersión.",
        f"- Coeficiente de variación intra-pasada máximo: {min(cvs):.2f}–{max(cvs):.2f} %."
        if cvs else "",
        "- **Zen comparte backend con C**: este estudio mide el efecto de los flags del "
        "compilador C sobre el C generado, no un backend propio de Zen. No se declara "
        "superioridad de Zen sobre C ni de una variante sobre otra fuera de estas cargas.",
        "- Host compartido, sin `perf`: la métrica es tiempo de CPU, no ciclos ni "
        "instrucciones; los cambios de frecuencia y la contención SMT no se eliminan. "
        "Las cifras no generalizan a otro hardware ni a otras cargas.",
        "- Se incluye el arranque del proceso; en cargas cortas puede pesar más que en "
        "un benchmark de larga duración.",
        f"- LTO: `-flto` se pasa también en el enlace (una sola unidad de traducción). "
        "El tiempo de compilación y el tamaño de binario se reportan, pero no son el "
        "criterio de decisión.",
        "- Solo se miden cuatro benchmarks; los resultados no justifican cambiar flags "
        "para cargas no representadas aquí.",
        "- No se modificó `zen/compiler/src/native.rs`: su build release sigue usando "
        "`-O2` (línea 77). Este informe solo recomienda; el cambio, si lo hubiera, "
        "correspondería al Lead.",
        (
            "- Los cuatro flags compilaron y verificaron checksum en este host; no hubo "
            "variantes no disponibles."
            if not unavailable_variants
            else "- Variantes no disponibles en alguna carga: "
            + ", ".join(unavailable_variants)
            + " (ver tabla de compilación)."
        ),
        "",
        "## Reproducir",
        "",
        "```bash",
        report["command"],
        "```",
        "",
        f"JSON completo: `{report['artifacts']['json']}`. "
        f"Script: `{report['artifacts']['script']}`.",
        "",
    ]
    return "\n".join(line for line in lines if line is not None) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reps", type=int, default=7, help="repeticiones medidas (default 7)")
    parser.add_argument("--warmup", type=int, default=2, help="rondas de warmup (default 2)")
    parser.add_argument("--passes", type=int, default=2, help="pasadas completas (default 2)")
    parser.add_argument("--filter", default="", help="solo benchmarks que contengan el texto")
    parser.add_argument("--timeout", type=float, default=180.0, help="timeout por comando (s)")
    parser.add_argument("--cpu", type=int, default=None, help="CPU para afinidad")
    parser.add_argument("--json", type=Path, default=RESULTS / "opt-flags.json")
    parser.add_argument("--md", type=Path, default=RESULTS / "opt-flags.md")
    parser.add_argument("--keep", action="store_true", help="conservar el directorio temporal")
    parser.add_argument(
        "--from-json",
        type=Path,
        default=None,
        help="regenerar análisis y Markdown desde un JSON ya medido (no vuelve a medir)",
    )
    args = parser.parse_args()
    if args.reps < 1 or args.warmup < 0 or args.passes < 1:
        parser.error("reps/passes deben ser >=1 y warmup >=0")
    if args.from_json is not None:
        if not args.from_json.is_file():
            print(f"error: JSON not found: {args.from_json}", file=sys.stderr)
            return 2
        report = json.loads(args.from_json.read_text())
        benchmarks = list(report["benchmarks"])
        variants = report["variants"]
        available = {
            benchmark: {
                variant: report["builds"][benchmark][variant].get("available", False)
                for variant in variants
            }
            for benchmark in benchmarks
        }
        report["analysis"] = analyze(report["passes"], benchmarks, variants)
        report["decision"] = decide(report["analysis"], benchmarks, variants, available)
        report["artifacts"] = {
            "json": str(args.json),
            "markdown": str(args.md),
            "script": str(Path(__file__).resolve()),
        }
        report["rendered_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.md.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2) + "\n")
        args.md.write_text(markdown(report))
        print(f"rendered from {args.from_json}\njson: {args.json}\nmd:   {args.md}")
        return 0
    if not ZEN.exists():
        print(f"error: build the compiler first: {ZEN} not found", file=sys.stderr)
        return 2
    if not shutil.which(cc_command()[0]):
        print(f"error: C compiler not found: {cc_command()[0]}", file=sys.stderr)
        return 2

    benchmarks = [b for b in BENCHMARKS if args.filter in b]
    if not benchmarks:
        print(f"error: no benchmark matches {args.filter!r}", file=sys.stderr)
        return 2

    if args.cpu is not None:
        try:
            if args.cpu not in os.sched_getaffinity(0):
                print(f"error: CPU {args.cpu} is not in the affinity mask", file=sys.stderr)
                return 2
        except (AttributeError, OSError):
            print("error: affinity is not supported on this platform", file=sys.stderr)
            return 2
    else:
        try:
            args.cpu = min(os.sched_getaffinity(0))
        except (AttributeError, OSError, ValueError):
            args.cpu = None
    pin_ok = pin_probe(args.cpu)
    if not pin_ok:
        args.cpu = None

    variants = VARIANT_ORDER
    tmpdir = Path(tempfile.mkdtemp(prefix="zen-flags-"))
    started = time.time()
    report = {
        "task": "TASK-802",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "command": command_line(),
        "host": host_info(),
        "toolchains": toolchain_info(),
        "config": {
            "warmup": args.warmup,
            "reps": args.reps,
            "passes": args.passes,
            "cpu": args.cpu,
            "cpu_affinity_effective": pin_ok,
            "timing": "tiempo de CPU del hijo (getrusage RUSAGE_CHILDREN), "
            "ejecuciones intercaladas; incluye arranque del proceso",
            "variants": VARIANTS,
            "threshold": IMPROVEMENT_THRESHOLD,
        },
        "benchmarks": {},
        "variants": variants,
        "correctness": {},
        "builds": {},
        "passes": [],
        "notes": [
            "Zen comparte el backend C11 con C; este estudio mide los flags del backend.",
            "No se declara superioridad; las cifras son de este host y estas cargas.",
            "Los checksums se verifican antes de medir.",
        ],
    }
    print(f"host: {report['host']['cpu']}")
    print(f"cc:   {report['toolchains']['compiler'].get('cc_version', '?')}")
    print(f"tmp:  {tmpdir} (pin={pin_ok}, cpu={args.cpu})")

    binaries: dict[str, dict[str, Path]] = {}
    available: dict[str, dict[str, bool]] = {}

    try:
        for benchmark in benchmarks:
            print(f"\n[{benchmark}] generating C and compiling variants")
            emitted = emit_c(benchmark, tmpdir, args.timeout)
            entry = {
                "desc": "",
                "c_source": emitted["c_source"],
                "c_bytes": emitted["c_bytes"],
                "emit_seconds": emitted["emit_seconds"],
            }
            report["benchmarks"][benchmark] = entry
            binaries[benchmark] = {}
            available[benchmark] = {}
            report["builds"][benchmark] = {}
            correctness = {
                "expected": EXPECTED[benchmark],
                "reference_checksum": None,
                "reference_source": "esperado del test",
                "variants": {},
            }

            reference_binary = BUILD_C / benchmark
            if reference_binary.is_file() and os.access(reference_binary, os.X_OK):
                ref_checksum = checksum(reference_binary, args.timeout)
                correctness["reference_checksum"] = ref_checksum
                correctness["reference_source"] = str(reference_binary.relative_to(ROOT))
                if ref_checksum != EXPECTED[benchmark]:
                    print(
                        f"  warning: {reference_binary} prints {ref_checksum}, "
                        f"expected {EXPECTED[benchmark]}",
                        file=sys.stderr,
                    )
            else:
                correctness["reference_checksum"] = EXPECTED[benchmark]

            for variant in variants:
                build = compile_variant(
                    benchmark, Path(emitted["c_source"]), variant, tmpdir, args.timeout
                )
                report["builds"][benchmark][variant] = build
                correctness["variants"][variant] = {
                    "available": build["available"],
                    "checksum": None,
                    "match": False,
                }
                if not build["available"]:
                    available[benchmark][variant] = False
                    print(f"  {variant:7s} UNAVAILABLE: {build['reason']}")
                    continue
                binary = Path(build["binary"])
                try:
                    got = checksum(binary, args.timeout)
                except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
                    build["available"] = False
                    build["reason"] = f"checksum run failed: {exc}"
                    available[benchmark][variant] = False
                    print(f"  {variant:7s} UNAVAILABLE: checksum run failed")
                    continue
                correctness["variants"][variant]["checksum"] = got
                match = got == EXPECTED[benchmark]
                correctness["variants"][variant]["match"] = match
                if not match:
                    build["available"] = False
                    build["reason"] = (
                        f"checksum mismatch: got {got}, expected {EXPECTED[benchmark]}"
                    )
                    available[benchmark][variant] = False
                    print(f"  {variant:7s} MISMATCH: {got} != {EXPECTED[benchmark]}")
                    continue
                available[benchmark][variant] = True
                binaries[benchmark][variant] = binary
                print(
                    f"  {variant:7s} ok: {build['binary_bytes']} B, "
                    f"{build['build_seconds']:.3f} s, checksum {got}"
                )
            report["correctness"][benchmark] = correctness
            if BASELINE not in binaries[benchmark]:
                print(
                    f"error: baseline {BASELINE} unavailable for {benchmark}; cannot compute ratios",
                    file=sys.stderr,
                )
                return 4

        usable = [b for b in benchmarks if BASELINE in binaries[b]]
        if not usable:
            print("error: no usable benchmark", file=sys.stderr)
            return 4

        for pass_index in range(args.passes):
            print(f"\n=== pass {pass_index + 1}/{args.passes} ===")
            load_start = list(os.getloadavg())
            timed = timed_pass(
                binaries,
                usable,
                variants,
                args.reps,
                args.warmup,
                args.timeout,
                args.cpu,
                order_offset=pass_index * (pass_index + 1),
            )
            pass_report = {
                "pass": pass_index + 1,
                "loadavg_start": load_start,
                "loadavg_end": list(os.getloadavg()),
                "benchmarks": {},
            }
            for benchmark in usable:
                results = {}
                for variant in variants:
                    if variant not in timed["samples"][benchmark]:
                        continue
                    stats = summarize(timed["samples"][benchmark][variant])
                    wall = summarize(timed["wall"][benchmark][variant])
                    results[variant] = {
                        **stats,
                        "wall_median_ns": wall["median_ns"],
                        "binary_bytes": report["builds"][benchmark][variant]["binary_bytes"],
                    }
                pass_report["benchmarks"][benchmark] = {
                    "results": results,
                    "schedule": timed["schedule"].get(benchmark, []),
                }
                base = results[BASELINE]["median_ns"]
                print(f"  {benchmark:8s}", end="")
                for variant in variants:
                    if variant not in results:
                        continue
                    ratio = relative(results[variant]["median_ns"], base)
                    print(
                        f"  {variant} {fmt_ms(results[variant]['median_ns'])} ms "
                        f"(x{ratio:.3f})",
                        end="",
                    )
                print()
            report["passes"].append(pass_report)

        report["analysis"] = analyze(report["passes"], usable, variants)
        report["decision"] = decide(report["analysis"], usable, variants, available)
        report["elapsed_seconds"] = round(time.time() - started, 2)
        report["artifacts"] = {
            "json": str(args.json),
            "markdown": str(args.md),
            "script": str(Path(__file__).resolve()),
        }
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.md.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2) + "\n")
        args.md.write_text(markdown(report))
        print(f"\njson: {args.json}\nmd:   {args.md}")
        print(
            "decision: "
            + (
                f"change to {report['decision']['recommended_variant']}"
                if report["decision"]["change_release_flags"]
                else "keep -O2"
            )
        )
        return 0
    finally:
        if args.keep:
            print(f"kept temporary directory: {tmpdir}")
        else:
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
