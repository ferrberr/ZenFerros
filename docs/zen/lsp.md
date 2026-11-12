# Servidor LSP `zen lsp` — TASK-910

```bash
zen lsp    # JSON-RPC 2.0 por stdin/stdout (Content-Length framing)
```

Métodos: `initialize` (textDocumentSync full, UTF-16), `initialized`, `textDocument/didOpen|didChange|didSave|didClose` → `textDocument/publishDiagnostics`, `shutdown`, `exit`. Métodos desconocidos `-32601`; JSON inválido `-32700`; el servidor sigue vivo.

Los diagnósticos coinciden con `zen lint --json` en severity/código/línea: `range` es 0-based con carácter en UTF-16, mientras que la columna de `zen lint --json` cuenta escalares Unicode; coinciden salvo caracteres fuera del plano básico (emoji), donde el `character` UTF-16 puede ser mayor. Los errores de compilación llegan como `compile-error` severity 1.

Configuración típica de editor (ejemplo Neovim):
```lua
vim.lsp.start({ name = "zen", cmd = { "zen", "lsp" }, root_dir = vim.fn.getcwd() })
```

Límites: solo diagnóstico push con sincronización full; sin hover/completion/definition/rename/code actions/formatting, cancelación ni concurrencia. El servidor no lee archivos: el editor envía el texto. Decisión: ADR-022. Evidencia: `agents/reports/TASK-910.md`.
