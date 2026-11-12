# Benchmarks de Zen

Laboratorio reproducible para medir el coste de Zen frente a C, C++ y Rust con **el mismo algoritmo, los mismos datos y la misma verificación de corrección**. Forma parte del Hito 8 (TASK-801) y es la base de la Fase 8 de optimización.

## Honestidad metodológica

- Cada benchmark imprime un checksum; **antes de medir**, el arnés compila y ejecuta todas las implementaciones y exige que el checksum sea idéntico. Si difiere, aborta sin producir cifras.
- Los tiempos excluyen compilación e incluyen arranque del proceso. Se hace warmup y se reportan mediana, mínimo, media y desviación típica de `reps` repeticiones.
- Cada ejecución se fija a un solo núcleo (`sched_setaffinity`) para reducir migraciones.
- El host es compartido; las cifras sirven para comparar **en este host** y detectar regresiones, no como ranking absoluto de lenguajes.
- **Zen usa el backend C11 del bootstrap (`cc -O2`)**. Por tanto Zen y C comparten compilador; una diferencia de rendimiento entre ellos mide el código generado y el runtime del lenguaje, no la calidad de un backend propio (que no existe todavía).
- Zig **no está instalado** en este host: el informe lo marca como no disponible; no se estiman ni inventan cifras.
- Los benchmarks recursivos se excluyeron de la comparación principal por una **hipótesis no verificada**: el inlining recursivo puede variar entre lenguaje/compilador y Zen aún no permite solicitar `noinline`, lo que haría la comparación dependiente de heurísticas del compilador. No se conservan artefactos de esa prueba exploratoria; no se citan cifras.

## Benchmarks

| Nombre | Carga | Tipo |
|---|---|---|
| `arith` | 50M iteraciones de LCG (multiply-add envolvente u64 + fold a 32 bits) | CPU entera |
| `collatz` | Conteo de pasos Collatz para 1..=500 000 | Ramas/divisiones |
| `mem` | 16 MiB: escritura y lectura secuenciales volátiles byte a byte sobre heap | Memoria |
| `sort` | Heapsort in-place de 500k `u32` con accesos volátiles | Memoria + algoritmo |

`mem` y `sort` usan `malloc`/`free` de libc en los cuatro lenguajes (Rust mediante `std::alloc` sin zero-init) para que el trabajo de asignación sea equivalente.

## Ejecutar

```bash
# compilador Zen release ya construido
CARGO_HOME="$PWD/.cargo" cargo build --release --offline --manifest-path zen/compiler/Cargo.toml

# suite completa (7 repeticiones, 2 warmup)
python3 benchmarks/scripts/bench.py

# iteración rápida durante desarrollo
python3 benchmarks/scripts/bench.py --reps 3 --warmup 1 --filter arith
```

Salidas en `benchmarks/results/bench-<UTC>.json` y `.md`. El JSON incluye host, versiones de toolchain, configuración, checksums, muestras crudas, mediana/mín/media/desviación, ratio frente a C, tamaño de binario y tiempo de compilación.

## Tests de corrección

```bash
python3 -m unittest discover -s benchmarks/tests -v
```

Comprueban la paridad de checksums Zen↔C para cada benchmark, la aritmética de estadísticas del arnés y que todas las fuentes esperadas existen.

## Añadir un benchmark

1. Crea el mismo algoritmo con entradas equivalentes en `zen/`, `c/`, `cpp/` y `rust/` (o documenta la ausencia de una implementación).
2. Asegura un checksum determinista impreso al final.
3. Añádelo a `BENCHMARKS` en `scripts/bench.py` y a `tests/test_benchmarks.py`.
4. Ejecuta la suite y actualiza los resultados versionados si procede.
