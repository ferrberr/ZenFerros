# TASK-802: Análisis de flags de optimización del backend C11 (Fase 8)

**Agente**: 04
**Estado**: COMPLETADA
**Resultado**: medición -O2/-O3/LTO en 2 pasadas; recomendación mantener -O2; ADR-015.
**Dependencias**: TASK-801
**Archivos (propiedad exclusiva)**: `benchmarks/scripts/flags.py`, `benchmarks/results/opt-flags.md` (nuevo)

## Objetivo
Medir el efecto de `-O2`, `-O3` y `-O2/-O3 + LTO` sobre los C generados por Zen y decidir con datos si conviene cambiar los flags de `--release` en `native.rs` (el Lead decidirá; tú NO editas native.rs).

## Método
- Partir de `zen build --emit c --release` de los 4 benchmarks (`arith`, `collatz`, `mem`, `sort`).
- Compilar cada C con `cc -std=c11` en variantes: `-O2`, `-O3`, `-O2 -flto`, `-O3 -flto`; verificar checksum idéntico en todas.
- Medir tiempo de CPU del hijo (getrusage), 7 reps + 2 warmup, intercalado entre variantes; mediana/mín/desv; repetir la suite 2 veces.
- Reportar tabla con ratios vs `-O2`, tamaños y estabilidad; conclusión con umbral: solo recomendar cambio si la mejora es consistente (>3% y reproducible en ambas pasadas) y sin regresión en ninguna carga.

## Aceptación
- Script reproducible `python3 benchmarks/scripts/flags.py` (salida JSON/MD en `benchmarks/results/`).
- Informe `benchmarks/results/opt-flags.md` con evidencia y recomendación; sin declarar superioridad.
- No editar `zen/compiler/src/native.rs`, `ferros/**` ni `benchmarks/scripts/bench.py`.
