# TASK-910: LSP mínimo sobre `zen lint` (Fase 9)

**Agente**: 15/02
**Estado**: COMPLETADA
**Resultado**: LSP mínimo por stdio con diagnósticos; 12 e2e + 3 unit; ADR-022.
**Dependencias**: TASK-909
**Archivos (propiedad exclusiva)**: `zen/compiler/src/lsp.rs` (nuevo), `zen/compiler/src/main.rs`, `zen/compiler/src/lib.rs`, `zen/compiler/tests/lsp_cli.rs` (nuevo)

## Objetivo
Servidor LSP mínimo por stdio para editores: diagnósticos en vivo usando el linter existente, con framing correcto y ciclo de vida estándar.

## Contrato
- `zen lsp`: servidor JSON-RPC 2.0 por stdin/stdout con framing `Content-Length: N\r\n\r\n{json}`.
- Métodos:
  - `initialize` → capabilities: `textDocumentSync: 1` (full), `diagnosticProvider`? (si se implementa pull) o solo push con `publishDiagnostics`; `serverInfo`.
  - `initialized` (notificación, sin respuesta).
  - `textDocument/didOpen`, `didChange` (full), `didSave`, `didClose` → `textDocument/publishDiagnostics` (uri, version, diagnostics con `severity` 1/2, `code`, `message`, `range`) usando lint + errores del compilador; al cerrar, publicar lista vacía.
  - `shutdown` → respuesta null; `exit` → termina (código 0 si shutdown previo, 1 si no).
  - Métodos desconocidos: responder error -32601; JSON inválido: error -32700 sin matar el servidor.
- Sin dependencias nuevas si es posible (parseo JSON mínimo manual) o serde_json si ya está; el servidor no debe bloquear ni usar shell.
- Los 114 tests del compilador siguen verdes; los diagnósticos del LSP coinciden con `zen lint --json` en código/severidad/línea.

## Aceptación
- `zen/compiler/tests/lsp_cli.rs` con ≥8 tests: initialize/capabilities, didOpen con warning (unused variable) → publishDiagnostics, didChange que limpia/actualiza, didClose vacío, shutdown/exit, método desconocido (-32601), JSON inválido (-32700), framing partido en varios writes.
- Verifica manualmente con un pequeño cliente Python o `printf` una sesión completa.
- Informe: métodos, esquema, límites (sync full, sin hover/completion/fixes) y evidencia.
