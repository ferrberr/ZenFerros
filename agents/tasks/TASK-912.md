# TASK-912: `use`/includes textuales y stdlib distribuible (Fase 9)

**Agente**: 01/15
**Estado**: COMPLETADA
**Resultado**: includes textuales + stdlib distribuible; 10 tests; ADR-024.
**Dependencias**: TASK-208, TASK-901
**Archivos (propiedad exclusiva)**: `zen/compiler/src/module.rs` (nuevo), `zen/compiler/src/main.rs`, `zen/compiler/src/lib.rs`, `zen/compiler/tests/include_cli.rs` (nuevo), `zen/std/core.zen` (nuevo), `zen/examples/use_std.zen` (nuevo)

## Objetivo
Primer mecanismo real de composición multi-archivo: `use "ruta.zen";` resuelto en compilación, que permite distribuir una stdlib en Zen y escribir programas en varios ficheros.

## Contrato
- `use "ruta.zen";` al inicio de un fichero (antes de items) incluye **textualmente** el fuente referenciado; rutas relativas al fichero que incluye; soporta includes anidados.
- Detección de ciclos (error claro con cadena), límite de profundidad (p. ej. 16) y fichero inexistente → error de compilación con ruta; no se incluye dos veces el mismo fichero canónico (incluir una vez; documentar).
- `zen build/run/check` aceptan includes; `zen fmt/lint/lsp` documentan que trabajan sobre el fuente tal cual (sin resolver includes) o los resuelven si es viable; no romper tests.
- `zen/std/core.zen`: funciones puras útiles (`min_u64`, `max_u64`, `clamp_u64`, `is_even`?) con tests; `zen/examples/use_std.zen` usa `use` y ejecuta.
- Tests `include_cli.rs` ≥8: include simple, anidado, relativo, ciclo, ausente, profundidad, include duplicado (regla), check/run del ejemplo, y que los 141 tests siguen verdes.

## Aceptación
```bash
CARGO_HOME="$PWD/.cargo" cargo build --release --offline --manifest-path zen/compiler/Cargo.toml
CARGO_HOME="$PWD/.cargo" cargo test --offline --manifest-path zen/compiler/Cargo.toml
./zen/compiler/target/release/zen run zen/examples/use_std.zen
```
- ≥8 tests nuevos; ejemplo ejecutable con salida verificable.
- Informe: resolución, reglas (orden/duplicados/ciclos/límites), tests, límites (textual, sin namespaces) y desviaciones.
