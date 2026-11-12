# TASK-904A: Formatter `zen fmt` (Fase 9, tooling)

**Agente**: 15/02
**Estado**: COMPLETADA
**Resultado**: formatter `zen fmt` con comentarios, idempotencia y --check/--write; 10 tests; ADR-020.
**Dependencias**: TASK-208, TASK-212
**Archivos (propiedad exclusiva)**: `zen/compiler/src/fmt.rs` (nuevo), `zen/compiler/src/lib.rs`, `zen/compiler/src/main.rs`, `zen/compiler/src/lexer/mod.rs`, `zen/compiler/src/lexer/scanner.rs`, `zen/compiler/src/lexer/token.rs`, `zen/compiler/tests/fmt_cli.rs` (nuevo)

## Objetivo
Primera herramienta real de Fase 9: un formateador canónico `zen fmt` que **preserve comentarios**, sea idempotente y no cambie la semántica (el código formateado debe pasar `zen check`).

## Contrato
- Lexer: modo opcional con comentarios (`//...` y `/*...*/` anidados) como tokens; el modo por defecto del parser sigue **sin** comentarios (no romper semántica ni conteos actuales). Documenta la API.
- `zen fmt <archivo>`: imprime el fuente formateado a stdout (no modifica el archivo).
- `zen fmt --check <archivo>`: exit 0 si ya está formateado; exit 1 (sin escribir) si difiere; mensaje claro en stderr.
- `zen fmt --write <archivo>`: reemplaza el archivo de forma atómica (tmp + rename) solo si cambia.
- Reglas canónicas mínimas y deterministas: indentación de 2 espacios por nivel de `{}`; una sentencia por línea (`;`), `{` abre bloque al final de línea, `}` en línea propia; espacio simple alrededor de operadores binarios/asignaciones y tras `,`; sin espacio tras `(`/`[` ni antes de `)`/`]`/`,`/`; comentarios de línea en su propia línea con indentación; comentarios de bloque conservados (inline si eran inline). No reordena tokens, no elimina comentarios.
- Idempotencia: `fmt(fmt(x)) == fmt(x)` y `fmt(x)` pasa `zen check` para los ejemplos válidos (`zen/examples/*.zen` que el compilador acepte).

## Aceptación
- `zen/compiler/tests/fmt_cli.rs` con ≥8 tests: espacios, indentación, comentarios línea/bloque, idempotencia, `--check` (0 y 1), `--write` atómico, archivo inexistente, y `check` del resultado sobre hello/factorial/arrays/structs.
- Todos los tests existentes siguen verdes (94).
- No tocar ferros, benchmarks, selfhost ni docs.
