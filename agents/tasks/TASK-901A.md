# TASK-901A: Builtins de stdlib mínima (str_eq, str_cmp, str_find) (Fase 9)

**Agente**: 01/02/03
**Estado**: COMPLETADA
**Resultado**: builtins `str_eq/str_cmp/str_find` hosted/freestanding; 12 tests; ADR-019.
**Dependencias**: TASK-208, TASK-310
**Archivos (propiedad exclusiva)**: `zen/compiler/src/mvp.rs`, `zen/compiler/tests/stdlib_cli.rs` (nuevo), `zen/examples/stdlib.zen` (nuevo)

## Objetivo
Primer bloque real de biblioteca estándar del bootstrap: utilidades de cadenas sin libc disponibles en hosted y freestanding, con semántica y límites documentados, como builtins del compilador (no hay módulos todavía).

## Contrato
- `str_eq(a: str, b: str) -> bool`: igualdad byte a byte (longitudes incluidas).
- `str_cmp(a: str, b: str) -> i32`: -1/0/1 lexicográfico por bytes sin signo.
- `str_find(haystack: str, needle: str) -> i64`: índice del primer byte donde aparece `needle` (0..len-haystack) o -1; `needle` vacío → 0.
- Semántica idéntica hosted/freestanding, sin libc; helpers C generados (`__zen_str_*`) con bucles acotados y sin UB; `str` sigue siendo vista estática (no hay asignación).
- Errores: argumentos deben ser `str` (diagnóstico de tipos); no hay pánico por límites (el recorrido está acotado).

## Aceptación
- `zen/compiler/tests/stdlib_cli.rs` con ≥10 tests: igualdad/desigualdad, prefijos/sufijos, vacío, cmp orden, find en inicio/medio/fin/ausente/vacío, hosted y freestanding (`--emit c`), y `zen/examples/stdlib.zen` ejecutable con salida verificable.
- Todos los tests existentes (94) siguen verdes.
- No tocar lexer/main/lib/fmt, ferros, benchmarks, selfhost ni docs.
