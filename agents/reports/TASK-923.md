# TASK-923 — Evidencia

**Resultado:** documentación preparada para revisión; no se modificó código del compilador, Ferros ni infraestructura.

**Integración y revisión:** el orquestador corrigió la descripción de `use "ruta.zen";` tras comparar con `zen/compiler/src/module.rs`. TASK-923 se integró en `main` y la puerta completa pasó 8/8. La especificación distingue inclusión textual de módulos reales.

## Cambios

- `docs/zen/spec-mvp.md`: nueva especificación descriptiva basada en el parser/typechecker activo. Detalla unidad de compilación, expresiones y precedencia real, tipos, semántica, arrays/slices/structs, unsafe/FFI, builtins, modos y formas reconocidas por lexer pero rechazadas por el compilador.
- `docs/zen/syntax-v0.ebnf`: encabezado identifica el archivo como propuesta histórica no normativa y enlaza el contrato vigente.
- `docs/zen/mvp-native.md`: aviso de precedencia normativa a `spec-mvp.md`.

## Trazabilidad revisada

- Parser, AST, tipos, límites de anidamiento, firmas y emisor: `zen/compiler/src/mvp.rs` (Parser::ty/program/struct_def/function/stmt/expr y Emitter::expr/stmt).
- Tokens disponibles y tokens que todavía no son gramática implementada: `zen/compiler/src/lexer/token.rs`, `keywords.rs`, `scanner.rs`.
- Cobertura de regresión localizada en `mvp.rs` y `zen/compiler/tests/{native_cli,freestanding_cli,arrays_cli,slices_cli,structs_cli}.rs`.

## Comandos y resultados

- `git rev-parse HEAD` → `e7737a607553eadb70624148bfafbf5c11ef70b6` (base solicitada).
- `CARGO_HOME=/home/ferranfg/proyectos/ZenFerros/.cargo CARGO_TARGET_DIR=/tmp/zenferros-task923-target cargo test --quiet --offline --manifest-path zen/compiler/Cargo.toml` → PASS, 163 pruebas; 0 fallos. La primera invocación falló al intentar crear `zen/compiler/target` en el worktree read-only; se reubicó el target en `/tmp`.
- `git diff --check` y verificación Python de espacios finales en `spec-mvp.md` → PASS, sin errores/espacios finales.
- `/tmp/zenferros-task923-target/debug/zen check` sobre `hello.zen`, `arrays.zen`, `slices.zen`, `structs.zen` y `freestanding.zen --target x86_64-unknown-none` → PASS, los cinco ejemplos aceptados.

## Riesgos / revisión pendiente

- La suite validada corresponde al commit base e7737a6 del worktree; si el compilador cambia antes de integrar, repetirla.
