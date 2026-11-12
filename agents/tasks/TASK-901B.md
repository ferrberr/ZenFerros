# TASK-901B: Ampliación stdlib de strings (Fase 9)

**Agente**: 01/02
**Estado**: COMPLETADA
**Resultado**: stdlib ampliada str_starts_with/ends_with/rfind; 12 tests.
**Dependencias**: TASK-901A
**Archivos (propiedad exclusiva)**: `zen/compiler/src/mvp.rs`, `zen/compiler/tests/stdlib_ext_cli.rs` (nuevo), `zen/examples/stdlib_ext.zen` (nuevo)

## Objetivo
Ampliar la stdlib mínima con utilidades de prefijo/sufijo y búsqueda inversa, hosted+freestanding y sin libc.

## Contrato
- `str_starts_with(s: str, prefix: str) -> bool`: prefijo exacto; prefijo vacío → true; prefijo más largo → false.
- `str_ends_with(s: str, suffix: str) -> bool`: sufijo exacto; sufijo vacío → true; sufijo más largo → false.
- `str_rfind(s: str, needle: str) -> i64`: índice de la **última** aparición; needle vacío → len(s); ausente → -1; sin lecturas fuera de rango.
- Builtins reconocidos como los existentes; helpers C `__zen_str_*` estáticos sin libc en hosted y freestanding; firmas estrictas y nombres de función reservados.
- No cambiar la semántica de `str_eq/str_cmp/str_find`; los 129 tests actuales siguen verdes.

## Aceptación
- `zen/compiler/tests/stdlib_ext_cli.rs` con ≥10 tests: cada función (positivo/negativo/vacío/más largo/borde), tipos/aridad, freestanding `--emit c` y `nm -u` vacío, ejemplo ejecutable `zen/examples/stdlib_ext.zen`.
- Todos los tests previos verdes.
- Informe: semántica, tests/salida, límites y desviaciones.
