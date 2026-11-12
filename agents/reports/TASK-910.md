# TASK-910 — Evidencia: LSP mínimo `zen lsp`

Fecha: 2026-11-11.

## Entregado
| Archivo | Cambio |
|---|---|
| `src/lsp.rs` | Servidor JSON-RPC por stdio, framing, parser JSON manual, buffers/versiones y conversión de diagnósticos (UTF-16) |
| `src/main.rs` | Subcomando `lsp` y despacho |
| `src/lib.rs` | `pub mod lsp` |
| `tests/lsp_cli.rs` | 12 tests end-to-end con el binario real |

## Protocolo
- `initialize` → `textDocumentSync: 1`, `positionEncoding: "utf-16"`, `serverInfo {zen-lsp, 0.1.0}`; `initialized` sin respuesta.
- `didOpen/didChange(full)/didSave/didClose` → `publishDiagnostics {uri, version, diagnostics[]}`; al cerrar, lista vacía.
- `shutdown` → null; `exit` → 0 con shutdown previo, 1 sin él; métodos desconocidos `-32601`; JSON inválido `-32700`; mensaje no-objeto `-32600`.
- Diagnósticos: severity 1 error / 2 warning, `code`, `source: zen`, `range` 0-based UTF-16 (la columna de `zen lint --json` cuenta escalares Unicode; coinciden salvo fuera del BMP); errores del compilador como `compile-error` severity 1.

## Verificación
```bash
CARGO_HOME="$PWD/.cargo" cargo build --release --offline --manifest-path zen/compiler/Cargo.toml  # OK
CARGO_HOME="$PWD/.cargo" cargo test  --offline          --manifest-path zen/compiler/Cargo.toml
# 129/129 = 114 previos + 12 lsp_cli + 3 unit
```
Sesión manual con cliente Python: initialize con frame partido, didOpen con warning, didChange limpio, didSave, didClose vacío, -32601, -32700, shutdown y exit 0 → OK. `cargo clippy --offline --lib` sin warnings en lsp.rs.

## Límites
- Solo push diagnostics y sincronización full; sin hover/completion/definition/rename/code actions/formatting/pull; sin cancelación ni concurrencia.
- No lee archivos; `didSave` sin `didOpen` publica lista vacía; `Content-Length` limitado a 64 MiB; EOF entre frames sin `exit` → 0; un frame truncado a mitad de cuerpo termina con error de lectura (no es un cierre limpio).
- Decisión: ADR-022.
