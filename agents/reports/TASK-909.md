# TASK-909 — Evidencia: linter `zen lint` y JSON

Fecha: 2026-11-11.

## Entregado
| Archivo | Cambio |
|---|---|
| `src/lint.rs` | `Severity`, `LintDiagnostic`, `line_column` (1-based, UTF-8), `render_text`, `render_json` (escape manual), `exit_code` |
| `src/mvp.rs` | `pub fn lint`/`lint_with_mode` con scopes, spans de nombre; refactor interno sin cambiar semántica |
| `src/main.rs` | Subcomando `lint` con `--json`, `--deny-warnings`, `--target` |
| `src/lib.rs` | `pub mod lint` |
| `tests/lint_cli.rs` | 18 tests CLI con parser JSON propio |

## Reglas
- `unused-variable`: nunca leída; `_` ignorado; asignación o escritura de campo/índice no cuenta como lectura (`assigned but never read`); `+=` sí.
- `unused-parameter`: nunca leído; `_` ignorado; extern sin cuerpo fuera de análisis.
- `unused-function`: privada definida sin llamada sintáctica; `pub`/`extern`/`main` ignorados.
- `unreachable-code`: sentencias directas tras `return` en el mismo bloque, sin descender.
- Validación completa del compilador antes de lint; errores como `error[compile-error]` (exit 1).

## Verificación
```bash
CARGO_HOME="$PWD/.cargo" cargo build --release --offline --manifest-path zen/compiler/Cargo.toml  # OK
CARGO_HOME="$PWD/.cargo" cargo test  --offline          --manifest-path zen/compiler/Cargo.toml
# 114 tests, 0 fallos (94 previos + 2 unit + 18 CLI)
./zen/compiler/target/release/zen lint --json zen/examples/hello.zen   # [] exit 0
for f in zen/examples/*.zen; do zen lint --json "$f"; done             # [] en los 6
```
Comprobados exit 0/1/2, `--deny-warnings`, error de compilación, JSON válido y esquema, programa complejo con arrays/structs/unsafe/loops sin falsos positivos.

## Límites
- Sin análisis de alcanzabilidad: llamada sintáctica mantiene viva la función (recursión/código muerto → falso negativo).
- `unreachable-code` solo tras `return` directo; no infiere divergencia por ramas.
- Sin estilos/nombres, autofix ni LSP. `lint` no exige `main` en host.
- Decisión: ADR-021.
