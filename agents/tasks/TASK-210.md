# TASK-210: Hito 1 — programas nativos Zen

**Agente**: 00 Orquestador (CLI, integración, lexer, pruebas y documentación); agente frontend (compilación MVP); agente revisor (revisión independiente).
**Estado**: COMPLETADA
**Prioridad**: ALTA
**Dependencias**: [TASK-101, TASK-201, TASK-202]
**Archivos**: [.gitignore, zen/compiler/Cargo.toml, zen/compiler/Cargo.lock, zen/compiler/build.rs, zen/compiler/src/lib.rs, zen/compiler/src/main.rs, zen/compiler/src/mvp.rs, zen/compiler/src/lexer/, zen/compiler/tests/, zen/examples/, docs/zen/, README.md, ROADMAP.md, ARCHITECTURE.md, agents/decisions/, agents/reports/]

## Objetivo
Compilar y ejecutar archivos Zen reales como ejecutables nativos Linux x86_64. Frontend MVP comprobado con backend C de bootstrap y enlazado mediante cc.

## Contratos y propiedad
- Frontend: trabaja en repositorio Git aislado `/tmp/zenferros-task210-frontend`, rama task210-frontend; entrega únicamente `src/mvp.rs`, API `check(&str) -> Result<(), CompileError>`, `emit_c(&str) -> Result<String, CompileError>`. Error público con `message: String`, `span: crate::lexer::Span`, Display y Error. Incluye parser, semántica y emisión C para subconjunto documentado.
- Orquestador: archivos restantes; integra el único archivo frontend secuencialmente y no lo modifica hasta la entrega.
- Revisor: inspección independiente sin modificar código de implementación; informe TASK-211.
- El `.git/` del workspace está vacío y protegido. No existe historial recuperable en esta sesión; el trabajo de frontend se aísla en un repositorio temporal y se integra sin simular merges.

## Criterios de aceptación
- [x] zen build genera ELF nativo; hello imprime Hello, Zen! y factorial(10) imprime 3628800.
- [x] zen run propaga código de salida; zen check valida sintaxis, nombres, tipos y retornos sin generar binarios.
- [x] Funciones con parámetros y recursión, let/let mut, enteros i32/i64/u64, bool, if/else y while verificados.
- [x] Entradas inválidas producen error no cero con localización, sin panic ni éxito ficticio.
- [x] Pruebas automatizadas positivas y negativas; debug y release del programa generado.
- [x] Revisión crítica por otro agente y documentación coherente con evidencia.

## Pruebas necesarias / resultado esperado
Cargo tests del lexer y aceptación CLI (ELF, stdout, estado, errores). Evidencia y métricas reales en agents/reports/TASK-210.md. Hito 1 completado; freestanding y Ferros permanecen pendientes.

## Cierre — 2026-11-11
Evidencia: `agents/reports/TASK-210.md`, métricas JSON y log de ejecución; revisión independiente favorable en `agents/reports/TASK-211.md`.
