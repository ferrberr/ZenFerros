# TASK-909: Linter y diagnósticos machine-readable (Fase 9)

**Agente**: 15/02
**Estado**: COMPLETADA
**Resultado**: linter `zen lint` con JSON, 4 reglas y exit codes; 18 CLI + 2 unit; ADR-021.
**Dependencias**: TASK-904A, TASK-208
**Archivos (propiedad exclusiva)**: `zen/compiler/src/lint.rs` (nuevo), `zen/compiler/src/mvp.rs`, `zen/compiler/src/main.rs`, `zen/compiler/src/lib.rs`, `zen/compiler/tests/lint_cli.rs` (nuevo)

## Objetivo
Primera herramienta de análisis estático real: `zen lint` con diagnósticos **machine-readable** (`--json`) y reglas sin falsos positivos, usable por editores/CI.

## Contrato
- `zen lint <archivo>`: diagnósticos legibles por stdout (o stderr) con archivo/línea/columna/severidad/código; exit 0 si no hay errores (warnings permitidos), 1 si hay errores, 2 si `--deny-warnings` y hay warnings.
- `zen lint --json <archivo>`: JSON válido (una lista de objetos con `severity`, `code`, `message`, `file`, `line`, `column`, `span_start`, `span_end`) por stdout; mismo exit code.
- Reglas mínimas:
  - `unused-variable`: local `let` nunca leído (ignorar nombres que empiezan por `_`; no marcar si se asigna? decidir y documentar).
  - `unused-parameter`: parámetro de función definida nunca leído (ignorar `_`).
  - `unused-function`: función no `pub`/`extern`/`main` nunca llamada.
  - `unreachable-code`: sentencias tras un `return` en el mismo bloque.
- Debe funcionar sobre el subconjunto MVP completo (arrays/structs/unsafe/loops) sin falsos positivos en los ejemplos válidos; los errores de compilación se reportan como error del linter con el diagnóstico existente.
- No cambia la semántica del compilador; los 94 tests siguen verdes.

## Aceptación
- `zen/compiler/tests/lint_cli.rs` con ≥10 tests: cada regla (positivo/negativo), `_` ignorado, JSON parseable y campos, exit codes 0/1/2, archivo con error de compilación, ejemplo válido sin warnings.
- `zen lint --json zen/examples/hello.zen` JSON válido; `zen lint` sobre examples sin errores (warnings documentados si los hay).
- Informe: reglas, decisiones (asignación sin lectura), límites y evidencia.
