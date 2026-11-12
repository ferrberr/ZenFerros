# TASK-915 — Evidencia: slices `[u64]` y stdlib de arrays

Fecha: 2026-11-11.

## Entregado
| Archivo | Cambio |
|---|---|
| `src/mvp.rs` | `Ty::Slice`, conversión de arrays en llamada, bounds check runtime, builtin `slice_len`, diagnósticos; typedef C `__zen_slice_u64` |
| `tests/slices_cli.rs` | 12 tests hosted/freestanding |
| `zen/std/array.zen` | `sum_slice`, `max_slice`, `reverse_slice`, `sort_slice`, `contains_slice` sobre `[u64]` |
| `zen/examples/slices.zen` | Ejemplo con `use "../std/array.zen"` y mutación visible |

## Semántica
- Slice = `{uint64_t *data; uint64_t len;}` solo parámetro; array local `[u64;N]` se pasa por referencia sin copia; slices reenviables.
- Acceso `s[i]` con bounds check contra `len` en debug y release; escritura y compound assignment igual.
- `slice_len` acepta slice o array; rechazos: local/copia/comparación/retorno/cast/campo/ABI externa, elemento no u64, argumentos inválidos.
- Sin tracking de aliasing: pasar un array no-mut permite escribir sus elementos (documentado, C-like).

## Verificación
```bash
CARGO_HOME="$PWD/.cargo" cargo build --release --offline --manifest-path zen/compiler/Cargo.toml  # OK
CARGO_HOME="$PWD/.cargo" cargo test --offline          --manifest-path zen/compiler/Cargo.toml
# 163/163 (151 previos + 12 slices)
./zen/compiler/target/release/zen run zen/examples/slices.zen   # exit 0, salida esperada
```
Freestanding: `nm -u` vacío; C sin stdio/stdlib/memcpy/malloc; bounds check con índice fuera aborta; arrays de N=1,2,7 al mismo parámetro.

## Límites
- Solo `[u64]`; sin rangos/rebanados, sin slices locales/retorno/almacenamiento/ABI; sin aliasing/mutabilidad tracking; slice vacío solo desde C.
- Decisión: ADR-026.
