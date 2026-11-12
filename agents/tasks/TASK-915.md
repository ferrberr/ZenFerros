# TASK-915: Slices `[u64]` como parámetro + stdlib de arrays (Fase 9)

**Agente**: 01/02/03
**Estado**: COMPLETADA
**Resultado**: slices `[u64]` como parámetro + stdlib de arrays; 12 tests; ADR-026.
**Dependencias**: TASK-213, TASK-214, TASK-912
**Archivos (propiedad exclusiva)**: `zen/compiler/src/mvp.rs`, `zen/compiler/tests/slices_cli.rs` (nuevo), `zen/std/array.zen` (nuevo), `zen/examples/slices.zen` (nuevo)

## Objetivo
Desbloquear algoritmos genéricos en Zen: un tipo **slice `[u64]`** (vista a array + longitud) usable solo como parámetro, con indexación comprobada y una stdlib de arrays distribuible por `use`.

## Contrato
- Nuevo tipo en parámetros: `[u64]` (slice de u64). El argumento puede ser un array local `[u64; N]` o otro slice; se pasa por **referencia** (mutaciones visibles).
- Dentro de la función: `s[i]` lectura/escritura con **bounds check contra la longitud** (trap/comprobación como los arrays actuales); `slice_len(s)` builtin nuevo (o `len(s)` si encaja con el diseño existente) que devuelve u64; `s` no se puede copiar, comparar, retornar ni usar como valor completo (diagnóstico).
- Semántica: el callee no puede retener el slice; no hay `unsafe` adicional; la longitud viaja con el puntero; arrays locales mantienen su tipo `[u64;N]` y no se convierten en slice salvo al pasarlos.
- `zen/std/array.zen`: funciones genéricas con `[u64]` (`sum_slice`, `max_slice`, `reverse_slice`, `sort_slice` inserción, `contains_slice`), con `use`; `zen/examples/slices.zen` las usa y muestra resultados.
- Tests `slices_cli.rs` ≥10: suma/max/reverse/sort/contains, mutación visible, bounds check (trap con índice fuera), longitud 0, arrays de tamaños distintos al mismo parámetro, slice como local no permitido, retorno/copia/comparación rechazados, freestanding `--emit c`/`nm -u`, y ejemplo ejecutable. Los 151 tests actuales siguen verdes.

## Aceptación
```bash
CARGO_HOME="$PWD/.cargo" cargo build --release --offline --manifest-path zen/compiler/Cargo.toml
CARGO_HOME="$PWD/.cargo" cargo test --offline --manifest-path zen/compiler/Cargo.toml
./zen/compiler/target/release/zen run zen/examples/slices.zen
```
- ≥10 tests nuevos; ejemplo con salida verificable.
- Informe: representación (puntero+len), codegen C, semántica de mutación/bounds, tests, límites (solo u64, sin retorno/almacenamiento) y desviaciones.
