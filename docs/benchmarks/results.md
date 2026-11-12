# Resultados de benchmarks — Hito 8

Ejecuciones versionadas: `benchmarks/results/bench-run{1,2,3}.json` y `.md`
Fecha UTC: 2026-11-11 · Host: AMD Ryzen 7 260 (Linux x86_64, glibc 2.44, loadavg ~2–3)
Toolchains: GCC 16.2.1 (`cc`/`g++`), rustc 1.99.1, Zen 0.1.0 (release, backend C11 vía `cc`). Zig y clang **no instalados**.
Configuración: warmup=2, reps=7 por ejecución, CPU fijada (afinidad efectiva confirmada), métrica primaria tiempo de CPU del hijo, ejecuciones intercaladas por lenguaje (ADR-013). Tres suites completas para estimar variabilidad.

## Tabla: ratio frente a C por ejecución (menor es mejor; C = 1.000)

| Bench | Zen/C (r1, r2, r3) | C++/C | Rust/C |
|---|---|---|---|
| arith | 0.969, 1.005, 1.009 | 1.002, 1.012, 1.034 | 0.981, 1.009, 0.999 |
| collatz | 1.018, 1.037, 1.027 | 1.019, 0.995, 1.029 | 1.085, 1.105, 1.121 |
| mem | 1.015, 1.017, 0.938 | 1.085, 1.057, 0.994 | 0.950, 0.966, 0.880 |
| sort | 1.023, 1.041, 1.027 | 1.048, 1.025, 1.056 | 1.392, 1.395, 1.425 |

Medianas de CPU por ejecución, calculadas de los tres JSON citados:

| Bench | Zen (ms) | C (ms) | C++ (ms) | Rust (ms) |
|---|---|---|---|---|
| arith | 42,087–42,935 | 42,422–43,414 | 42,952–44,002 | 42,478–42,797 |
| collatz | 37,710–38,332 | 36,726–37,176 | 36,761–37,900 | 40,324–41,169 |
| mem | 20,386–21,422 | 20,244–21,722 | 21,405–22,895 | 19,118–20,049 |
| sort | 26,693–27,883 | 25,984–27,265 | 27,303–28,564 | 37,038–37,947 |

Variación dentro de cada ejecución (desviación típica): 0,46–2,95 ms según lenguaje y carga.
Tamaños: Zen 16,1–16,3 KB; C/C++ ~16,0 KB; Rust ~4,5 MB (runtime estático de `std`).
Compilación: **en estas tres suites**, 0,0344–0,1030 s por implementación; una ejecución adicional bajo más carga llegó a 0,224 s, así que el dato es orientativo y no un benchmark del compilador.

> Nota de variabilidad: una ejecución adicional del revisor dio Zen/C `sort` ≈0,97, fuera del rango de estas tres suites. Los ratios cambian varios puntos con la carga del host; por eso no se interpretan diferencias de pocos puntos como señal.

## Lectura correcta

- **No hay diferencias defendibles de pocos puntos porcentuales entre Zen, C y C++.** Los ratios varían varios por ciento entre ejecuciones del mismo código en este host compartido (loadavg ~2–3, sin aislamiento); el rango observado Zen/C en estas tres suites es 0,9385–1,0408, y ejecuciones adicionales pueden salir fuera. La conclusión sostenible es **paridad aproximada** de Zen con C/C++ en estas cuatro cargas, no una ventaja ni una desventaja concretas.
- Rust es más lento de forma consistente en `collatz` (+8,5…+12,1 %) y `sort` (+39…+43 %), y algo más rápido en `mem` (−12…−3,4 %). Son observaciones de este rustc 1.99.1 y estas cargas; no se generalizan.
- **Zen usa el mismo backend C11 y el mismo GCC 16.2.1 que C** (`cc -O2`). Cualquier diferencia Zen↔C mide código generado y runtime del lenguaje, no un backend propio. No se declara superioridad.
- `sort` usa accesos volátiles para que el compilador no elimine el trabajo; Rust y C++ también los usan. No hay hints de inline específicos de un lenguaje (se retiró `#[inline(always)]` de la implementación Rust).
- Host compartido, sin `perf`: no se reportan ciclos, instrucciones ni fallos de caché. Las cifras sirven como línea base y detector de regresiones, no como ranking.

## Reproducir

```bash
CARGO_HOME="$PWD/.cargo" cargo build --release --offline --manifest-path zen/compiler/Cargo.toml
python3 benchmarks/scripts/bench.py --reps 7 --warmup 2
python3 -m unittest discover -s benchmarks/tests -v
```

El arnés aborta antes de medir si los checksums difieren (probado por `test_harness_aborts_before_timing_when_checksums_differ`).
