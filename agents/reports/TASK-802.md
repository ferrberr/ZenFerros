# TASK-802 — Evidencia: flags de optimización del backend C11

Fecha: 2026-11-11. Estudio reproducible de `-O2`, `-O3`, `-O2 -flto` y `-O3 -flto` sobre el C generado por Zen.

## Método
`benchmarks/scripts/flags.py`: por cada benchmark genera C con `zen build --emit c --release`, compila el mismo C con cada variante, **verifica checksum idéntico** antes de medir y cronometra con tiempo de CPU del hijo (getrusage), 7 reps + 2 warmups, orden rotado, CPU fijada y **dos pasadas**. Umbral preregistrado: recomendar solo si hay >3 % de mejora en todas las cargas y ambas pasadas sin regresión.

## Resultados (ratio CPU vs `-O2` de la misma pasada)

| Bench | O3 (p1/p2) | O2-LTO | O3-LTO |
|---|---|---|---|
| arith | 1.009 / 1.001 | 1.003 / 1.000 | 0.999 / 0.995 |
| collatz | **0.969 / 0.962** | 0.996 / 0.997 | **0.968 / 0.970** |
| mem | 1.006 / 1.005 | 1.001 / 1.006 | 0.995 / 1.016 |
| sort | 0.995 / 1.008 | 0.999 / 1.003 | 0.984 / 0.996 |

Checksums idénticos en las 16 combinaciones; tamaños 16,1–16,3 KB con diferencias ≤0,4 %; LTO compila 45,7–63,1 % más lento.

## Decisión
**Mantener `-O2`** (ADR-015). Solo `collatz` muestra una mejora reproducible (3,10/3,76 % con O3 en las dos pasadas); arith/mem/sort quedan en ±2 % con cambio de signo entre pasadas. Un cambio global afectaría cargas no medidas sin beneficio demostrado. No se declara superioridad y se recuerda que Zen comparte backend C11 con C.

Evidencia completa: `benchmarks/results/opt-flags.md` y `opt-flags.json`. Script: `benchmarks/scripts/flags.py`.
