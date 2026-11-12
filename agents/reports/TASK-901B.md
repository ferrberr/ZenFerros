# TASK-901B — Evidencia: ampliación stdlib de strings

Fecha: 2026-11-11.

## Entregado
| Archivo | Cambio |
|---|---|
| `src/mvp.rs` | Builtins `str_starts_with`, `str_ends_with`, `str_rfind` + helpers C estáticos sin libc (prelude común hosted/freestanding) |
| `tests/stdlib_ext_cli.rs` | 12 tests hosted/freestanding |
| `examples/stdlib_ext.zen` | Ejemplo ejecutable (32 líneas, termina en `ext ok`) |

## Semántica
- `str_starts_with(s,prefix)`: prefijo exacto; vacío → true; más largo → false; NUL es byte normal.
- `str_ends_with(s,suffix)`: sufijo exacto; vacío → true; más largo → false.
- `str_rfind(s,needle)`: última aparición (con solape: `"aaaa","aa"`→2; `"ababab","abab"`→2), ausente → −1, needle vacío → `len(s)`; sin lecturas fuera de rango ni overflow.
- Firmas estrictas, nombres reservados, locales pueden sombrear; `str_eq/str_cmp/str_find` intactos.

## Verificación
```bash
CARGO_HOME="$PWD/.cargo" cargo build --release --offline --manifest-path zen/compiler/Cargo.toml  # OK
CARGO_HOME="$PWD/.cargo" cargo test  --offline          --manifest-path zen/compiler/Cargo.toml
# 141 tests PASS (129 previos + 12 nuevos)
./zen/compiler/target/release/zen run zen/examples/stdlib_ext.zen   # exit 0
```
Freestanding: `cc -ffreestanding -fno-builtin -c`, `nm -u` vacío, harness produce `freestanding-ext-ok`; bloque de helpers byte-idéntico hosted/freestanding y sin `string.h`/`mem*`/`str*`/`malloc`.

## Límites
- Byte-oriented, sin Unicode/allocation; O(n·m) en `rfind`; sin ABI nueva (helpers `static`).
