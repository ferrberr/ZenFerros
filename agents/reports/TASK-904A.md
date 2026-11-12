# TASK-904A — Evidencia: formateador `zen fmt`

Fecha: 2026-11-11.

## Entregado
| Archivo | Cambio |
|---|---|
| `lexer/token.rs` | `TokenKind::Comment(String, bool)` |
| `lexer/scanner.rs` | `Scanner::with_comments` / `Lexer::with_comments`; `new` intacto |
| `src/fmt.rs` | Formateador canónico token a token con re-lexado de verificación e idempotencia |
| `src/main.rs` | `zen fmt [--check|--write] <archivo>` |
| `src/lib.rs` | `pub mod fmt` |
| `tests/fmt_cli.rs` | 10 tests |

## Comportamiento
- `zen fmt file.zen` imprime formateado; `--check` exit 0/1 sin escribir; `--write` atómico (tmp+rename), solo si cambia, conserva permisos y verifica idempotencia.
- Reglas: indentación 2 espacios, sentencia por línea, espacios canónicos, `} else {`, comentarios de línea/bloque preservados (bloques anidados), una línea en blanco entre items.
- Seguridad: re-lexa la salida y exige la misma secuencia de tokens; falla si difiere o si no es idempotente.

## Verificación
```bash
CARGO_HOME="$PWD/.cargo" cargo build --release --offline --manifest-path zen/compiler/Cargo.toml  # OK
CARGO_HOME="$PWD/.cargo" cargo test  --offline          --manifest-path zen/compiler/Cargo.toml
# 94 passed (84 previos + 10 fmt)
```
Formateados `hello/factorial/arrays/structs` pasan `zen check`; `--check` 0 sobre formateado y 1 sobre sin formatear; `--write` conserva modo 0640 y no deja temporales.

## Límites
- No preserva líneas en blanco salvo una entre items; comentarios de bloque multilínea no se reindentan; `freestanding.zen` no pasa `check` (sin `main`) y se excluye del test de ejemplos.
- `zen fmt` exige extensión `.zen`.
- Decisión: ADR-020.
