# TASK-801: Laboratorio de benchmarks reproducible (Hito 8)

**Agente**: 00 (orquestación) / 04 (optimización)
**Estado**: COMPLETADA
**Prioridad**: ALTA
**Dependencias**: [TASK-208, TASK-701]
**Archivos**: `benchmarks/{zen,c,cpp,rust,scripts,tests,results}/`, `docs/benchmarks/results.md`, `agents/decisions/ADR-013.md`, `.gitignore`

## Objetivo
Construir un laboratorio de benchmarks reproducible y comparable que mida Zen frente a C, C++ y Rust con el mismo algoritmo, datos y verificación de corrección, y publicar una línea base honesta para la Fase 8.

## Criterios de aceptación (verificados)
- [x] Cuatro benchmarks en cuatro lenguajes: `arith`, `collatz`, `mem`, `sort`; mismo algoritmo/datos.
- [x] Checksum determinista verificado entre lenguajes antes de medir; el arnés aborta si difiere.
- [x] Métrica primaria de CPU del proceso hijo, ejecuciones intercaladas y afinidad de CPU (ADR-013).
- [x] Estadísticas: mediana, mínimo, media, desviación y muestras crudas; wall time como referencia.
- [x] JSON + Markdown versionados por ejecución, con host, toolchains, flags, tamaños y tiempos de compilación.
- [x] Tests de corrección (6 tests: paridad Zen↔C↔C++↔Rust, estadísticas y aborto por checksum) y arnés con `--reps/--warmup/--filter`.
- [x] Zig y clang declarados como no disponibles (sondeados por el arnés); sin cifras inventadas.
- [x] Recursión excluida de la comparación principal por heurísticas de inlining no controlables en Zen (documentado).
- [x] Sin regresiones: suites del compilador y Ferros siguen pasando.

## Resultado
Línea base en `docs/benchmarks/results.md` y `benchmarks/results/bench-run{1,2,3}.json`. Tres suites completas muestran **paridad aproximada** entre Zen y C/C++ dentro de la variabilidad del host: Zen/C varía 0,9385–1,0408 según carga y ejecución (una ejecución adicional puede salir fuera). No se declara superioridad y se documenta que Zen comparte backend C11 con C. Rust es consistentemente más lento en `collatz` (+8,5…12,1 %) y `sort` (+39…43 %).

## Riesgos y deuda
- Host compartido y variabilidad: los ratios cambian varios puntos entre ejecuciones; diferencias de pocos % no son señal. La métrica de CPU mitiga desalojos, no frecuencia/SMT.
- Sin `perf`: no se reportan ciclos/instrucciones/fallos de caché.
- `sort` con volátiles penaliza a Rust en este rustc; es un resultado, no un juicio de lenguaje.
- Zig, clang y KVM no están disponibles en este entorno; se declaran, no se estiman.
- Los benchmarks no cubren floats, SIMD, concurrencia ni cargas reales todavía (limitaciones del subconjunto Zen).
