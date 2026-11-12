# Linter `zen lint` — TASK-909

```bash
zen lint archivo.zen                      # texto: archivo:linea:columna: severity[code]: mensaje
zen lint --json archivo.zen               # JSON machine-readable
zen lint --deny-warnings archivo.zen      # exit 2 si hay warnings
zen lint --target x86_64-unknown-none archivo.zen
```

JSON: lista de `{"severity","code","message","file","line","column","span_start","span_end"}`. Exit: 0 sin errores (warnings permitidos), 1 errores (lint o compilación), 2 con `--deny-warnings` y warnings (errores mandan con 1).

Reglas: `unused-variable` (let nunca leído; `_` ignorado; asignar/escribir campo o índice no cuenta; `+=` sí), `unused-parameter`, `unused-function` (privadas no llamadas; `pub`/`extern`/`main` no), `unreachable-code` (sentencias directas tras `return`). Los errores del compilador salen como `error[compile-error]` con el mismo esquema.

Límites: sin análisis de alcanzabilidad; el linter no desciende en sentencias tras `return`, así que una llamada en código muerto no mantiene viva la función, sin detección de divergencia por ramas, sin estilos/autofix/LSP; `lint` no exige `main` en host. Decisión: ADR-021. Evidencia: `agents/reports/TASK-909.md`.
