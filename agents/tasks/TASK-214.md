# TASK-214: Structs mínimos en Zen (desbloqueo de Hito 9)

**Agente**: 01/02/03
**Estado**: COMPLETADA
**Resultado**: structs escalares locales; 14 tests; 71 tests compilador; ejemplo ejecutable; ADR-017.
**Dependencias**: TASK-213 (arrays), TASK-208
**Archivos (propiedad exclusiva)**: `zen/compiler/src/mvp.rs`, `zen/compiler/tests/structs_cli.rs` (nuevo), `zen/examples/structs.zen` (nuevo)

## Objetivo
Añadir structs nominales mínimos para poder representar tokens/símbolos con nombre en Zen, siguiente bloqueo del autohosting tras los arrays.

## Alcance mínimo
- Declaración de nivel superior `struct Name { field: T, ... }` con campos escalares (`u8/u16/u32/i32/i64/u64/bool`), sin genéricos, sin métodos, sin anidamiento de structs, sin arrays como campos.
- Construcción en expresión: `Name { field: expr, ... }`; todos los campos exactos, sin faltar/sobrar; tipos exactos.
- Acceso y asignación de campo sobre variable local: `p.x` lectura, `p.x = expr;` y compuestas; requiere `let mut` para escribir.
- Solo variables locales de tipo struct; struct como parámetro, retorno, global, comparación, copia/asignación completa, cast o campo de struct → diagnóstico localizado.
- Layout C natural (`typedef struct {...} __zen_Struct_Name;`) emitido antes de las funciones; semántica idéntica debug/release; nombres internos seguros.
- Diagnósticos: struct duplicado, campo duplicado, campo desconocido, campo faltante, tipo de campo incorrecto, uso antes de declarar (si el orden importa, documentarlo).

## Aceptación
- `zen/compiler/tests/structs_cli.rs` con ≥8 tests: construcción, lectura, escritura, mutabilidad, varios campos, diagnóstico de duplicados/faltantes/tipos, struct como parámetro/retorno, ejemplo ejecutable.
- `zen/examples/structs.zen` ejecutable con `zen run` (salida verificable).
- Todos los tests existentes (57) siguen verdes; total nuevo documentado.
- No tocar ferros/**, benchmarks/**, zen/selfhost/**, docs.
