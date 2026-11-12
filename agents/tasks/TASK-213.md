# TASK-213: Arrays de tamaño fijo en Zen (Hito 9, desbloqueo de AST)

**Agente**: 01/02/03
**Estado**: COMPLETADA
**Resultado**: arrays fijos integrados; 57 tests del compilador; ejemplo ejecutable; ADR-016.
**Dependencias**: TASK-208, TASK-205
**Archivos (propiedad exclusiva)**: `zen/compiler/src/mvp.rs`, `zen/compiler/tests/arrays_cli.rs` (nuevo), `zen/examples/arrays.zen` (nuevo)

## Objetivo
Añadir arrays de tamaño fijo al subconjunto MVP para poder representar buffers y, más adelante, un AST en Zen. Es la carencia que bloquea el siguiente paso de autohosting.

## Alcance mínimo
- Tipo `[T; N]` en anotaciones (`let mut a: [u64; 4] = ...`), T escalar (`u8/u16/u32/i32/i64/u64/bool`), N literal entero >0.
- Literales `[e1,e2,...]` y repetición `[e; N]`; longitud exacta comprobada.
- Lectura `a[i]` y escritura `a[i] = expr;` (y asignación compuesta si es trivial) con comprobación de rango en ejecución; índice de tipo entero convertido a usize; el índice se evalúa una vez y de izquierda a derecha.
- Solo variables locales de función; arrays como parámetro, retorno o global se rechazan con diagnóstico claro (fuera de alcance).
- Semántica idéntica en debug y release; errores de rango terminan con el trap/mensaje habitual del backend, sin comportamiento indefinido.

## Aceptación
- Nuevo `zen/compiler/tests/arrays_cli.rs` con casos positivos (declaración, literal, repeat, lectura, escritura, bucles) y negativos (longitud incorrecta, tipos mezclados, N no constante, array como parámetro/retorno, índice OOB en ejecución).
- `cargo test --offline --manifest-path zen/compiler/Cargo.toml` debe mantener los 57 tests (46 previos + 11 nuevos) y no reducir cobertura.
- `zen/examples/arrays.zen` ejecutable con `zen run`.
- No tocar `ferros/**`, `benchmarks/**`, `zen/selfhost/**`, docs (el Lead documenta).
