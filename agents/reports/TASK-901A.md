# TASK-901A — Evidencia: builtins de stdlib mínima

Fecha: 2026-11-11.

## Entregado
| Archivo | Cambio |
|---|---|
| `zen/compiler/src/mvp.rs` | Builtins `str_eq`, `str_cmp`, `str_find` en firmas y emisión C (hosted y freestanding), helpers `__zen_str_*` estáticos sin libc |
| `zen/compiler/tests/stdlib_cli.rs` | 12 tests: semántica, composición, nombres reservados, shadowing local, aridad/tipos, helpers sin libc, freestanding |
| `zen/examples/stdlib.zen` | Ejemplo ejecutable con salida verificable (`stdlib ok`) |

## Semántica
- `str_eq`: igualdad byte a byte incluyendo longitud (NUL es byte normal).
- `str_cmp`: lexicográfico por bytes unsigned; prefijo menor → −1, mayor → 1, igual → 0.
- `str_find`: primer índice de byte de `needle` en `haystack`; vacío → 0; ausente o needle más largo → −1; sin lecturas fuera de rango.

## Verificación
```bash
CARGO_HOME="$PWD/.cargo" cargo build --release --offline --manifest-path zen/compiler/Cargo.toml  # OK
CARGO_HOME="$PWD/.cargo" cargo test  --offline          --manifest-path zen/compiler/Cargo.toml
# 29 unit + 9 arrays + 8 freestanding + 11 native + 12 stdlib + 15 structs = 84 passed
./zen/compiler/target/release/zen run zen/examples/stdlib.zen   # exit 0, salida esperada
```
Freestanding: C emitido sin includes de libc, `nm -u` vacío y sonda con harness produce `freestanding-ok`.

## Límites
- `str` estático: sin heap, sin asignación, sin Unicode normalizado.
- Nombres de builtin reservados como funciones; locales pueden sombrearlos.
- Es un bloque mínimo: faltan colecciones, I/O, formato, allocación y módulos. Decisión: ADR-019.
