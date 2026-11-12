# Documentación de Zen + Ferros

Índice de la documentación **vigente** del proyecto y de la evidencia que la
sostiene. Corte de este índice: **2026-11-12 (09:28 CET)**, versión local **0.1.1**; estado posterior 163/44/6/166.

> Regla de lectura: un documento de `agents/reports/` describe una ejecución
> concreta y puede quedar desfasado; la puerta
> [`verify_all.py`](../infrastructure/scripts/verify_all.py) y los documentos de
> estado ([`ARCHITECTURE.md`](../ARCHITECTURE.md), [`ROADMAP.md`](../ROADMAP.md),
> [`agents/STATE.md`](../agents/STATE.md)) mandan sobre el estado actual. Los
> documentos de `docs/agent-handoff/` son **históricos** (transferencia
> Codex→DSH) y no describen el presente.

## Punto de entrada

| Documento | Para qué sirve |
|---|---|
| [`README.md`](../README.md) | Presentación, arranque rápido, comandos y validación. |
| [`ARCHITECTURE.md`](../ARCHITECTURE.md) | Cadena implementada, contratos del lenguaje, composición del kernel y límites. |
| [`ROADMAP.md`](../ROADMAP.md) | Hitos, fases, tareas y pendientes. Puede contener filas históricas sin actualizar. |
| [`AGENTS.md`](../AGENTS.md) | Reglas de colaboración, roles y niveles de madurez. |
| [`agents/STATE.md`](../agents/STATE.md) | Resumen operativo de la ronda en curso. |
| [`CHANGELOG.md`](../CHANGELOG.md) | Qué entró en 0.1.0 y 0.1.1, por hito y fase. |
| [`release.md`](release.md) | Qué significa una release local, artefactos, matriz CI y checklist. |
| [`maturity.md`](maturity.md) | Revisión de madurez por subsistema con evidencia fechada y reglas de promoción. |

## Zen — lenguaje y compilador

| Documento | Contenido |
|---|---|
| [`zen/mvp-native.md`](zen/mvp-native.md) | Subconjunto ejecutable: tipos, funciones, flujo, arrays y structs. |
| [`zen/freestanding.md`](zen/freestanding.md) | Objetos sin libc, ABI C, punteros raw, `volatile`, `unsafe` y límites. |
| [`zen/selfhost.md`](zen/selfhost.md) | Los once componentes del frontend/ejecución escritos en Zen. |
| [`zen/modules.md`](zen/modules.md) | `use` / includes textuales y `zen/std/core.zen`. |
| [`zen/formatter.md`](zen/formatter.md) | `zen fmt`, formato canónico e idempotencia. |
| [`zen/linter.md`](zen/linter.md) | `zen lint`, reglas, JSON y códigos de salida. |
| [`zen/lsp.md`](zen/lsp.md) | `zen lsp`, framing JSON-RPC y diagnósticos. |
| [`zen/syntax-decisions.md`](zen/syntax-decisions.md) | Decisiones de sintaxis del borrador v0 (no es el parser activo). |
| [`zen/syntax-v0.ebnf`](zen/syntax-v0.ebnf) | Gramática propuesta, más amplia que el subconjunto implementado. |

## Ferros — kernel y sistema

| Documento | Contenido |
|---|---|
| [`ferros/boot.md`](ferros/boot.md) | Primer arranque, Multiboot1, UART y logs QEMU (Hito 3). |
| [`ferros/memory-interrupts.md`](ferros/memory-interrupts.md) | PMM, VMM, heap, IDT/PIC/PIT (Hito 4). |
| [`ferros/multitasking.md`](ferros/multitasking.md) | Threads de kernel, guardas y scheduler round-robin (Hito 5). |
| [`ferros/userspace.md`](ferros/userspace.md) | ELF Zen en CPL3, loader, `int0x80` y faults (Hito 6). |
| [`ferros/filesystem.md`](ferros/filesystem.md) | RAMFS/VFS, syscalls de archivos y `readdir` (Hito 7). |
| [`ferros/shell.md`](ferros/shell.md) | Shell interactivo por COM1 y contrato de transcripción (`writes=18`). |
| [`ferros/persistence.md`](ferros/persistence.md) | Persistencia ATA PIO (TASK-914, contador), mini-FS ZENFS01 (TASK-916) y PFS visible en VFS read-only (TASK-919, posterior a 0.1.1). |

Los documentos de `ferros/` describen el **mínimo integrado** de cada hito y sus
límites; no son una garantía de estabilidad ni cubren hardware físico o SMP.
El corte 0.1.1 incluía 43 tests de Ferros; el árbol actual tiene 44 (PFS en VFS) y 166 selfhost.

## Calidad, release y evidencia

| Documento | Contenido |
|---|---|
| [`quality.md`](quality.md) | Puerta única de 8 pasos, conteos esperados y límites de lo verificado. |
| [`maturity.md`](maturity.md) | Auditoría de niveles por subsistema y regla de promoción. |
| [`release.md`](release.md) | Release local 0.1.1: artefactos, matriz, campaña, checklist y límites. |
| [`reproducibility.md`](reproducibility.md) | Builds reproducibles locales y manifiesto de `repro_build.py`. |
| [`stability.md`](stability.md) | Campaña acotada de `stress.py`: guiones, fuzz y tolerancias. |
| [`stability-campaign.md`](stability-campaign.md) | Repetición de la campaña (`stability_campaign.py`) y JSON. |
| [`ci.md`](ci.md) | Matriz local `ci_matrix.py` (quick/defecto/full). |
| [`benchmarks/results.md`](benchmarks/results.md) | Línea base Hito 8 y lectura correcta de los ratios. |
| [`../benchmarks/README.md`](../benchmarks/README.md) | Arnés, cargas y cómo ejecutar los benchmarks. |
| [`../CHANGELOG.md`](../CHANGELOG.md) | Resumen de cambios de la versión local. |

## Decisiones (ADR)

Los ADR presentes en el árbol son **001 y 007–028**. No existen ADR-002 a
ADR-006; la numeración no es continua. Los estados se leen en cada fichero.

| ADR | Decisión |
|---|---|
| [`ADR-001`](../agents/decisions/ADR-001.md) | Lenguaje de bootstrap del compilador (histórica; sustituida por ADR-007 para el MVP). |
| [`ADR-007`](../agents/decisions/ADR-007.md) | Backend C11 de bootstrap: Zen → C11 → `cc`. |
| [`ADR-008`](../agents/decisions/ADR-008.md) | Freestanding x86_64, ABI C explícita y `unsafe`. |
| [`ADR-009`](../agents/decisions/ADR-009.md) | Primer boot con Multiboot1 y QEMU TCG. |
| [`ADR-010`](../agents/decisions/ADR-010.md) | Memoria e interrupciones mínimas verificables. |
| [`ADR-011`](../agents/decisions/ADR-011.md) | Threads de kernel con preemption por PIT. |
| [`ADR-012`](../agents/decisions/ADR-012.md) | ELF estático Zen en CPL3 y ABI `int0x80`. |
| [`ADR-013`](../agents/decisions/ADR-013.md) | Metodología de benchmarks comparables. |
| [`ADR-014`](../agents/decisions/ADR-014.md) | Etapa B de autohosting: componentes del compilador en Zen. |
| [`ADR-015`](../agents/decisions/ADR-015.md) | Mantener `-O2` tras medir `-O3`/LTO (no se declara optimización). |
| [`ADR-016`](../agents/decisions/ADR-016.md) | Arrays de tamaño fijo `[T; N]`. |
| [`ADR-017`](../agents/decisions/ADR-017.md) | Structs nominales escalares locales. |
| [`ADR-018`](../agents/decisions/ADR-018.md) | Directorio raíz real, segundo fixture y syscall `readdir`. |
| [`ADR-019`](../agents/decisions/ADR-019.md) | Stdlib mínima como builtins del bootstrap. |
| [`ADR-020`](../agents/decisions/ADR-020.md) | Formateador `zen fmt` token a token. |
| [`ADR-021`](../agents/decisions/ADR-021.md) | Linter `zen lint` con diagnósticos JSON. |
| [`ADR-022`](../agents/decisions/ADR-022.md) | Servidor LSP mínimo por stdio. |
| [`ADR-023`](../agents/decisions/ADR-023.md) | Codegen C escrito en Zen (selfhost). |
| [`ADR-024`](../agents/decisions/ADR-024.md) | `use` / includes textuales para composición multi-archivo. |
| [`ADR-025`](../agents/decisions/ADR-025.md) | Persistencia ATA PIO y superbloque. |
| [`ADR-026`](../agents/decisions/ADR-026.md) | Slices `[u64]` como parámetro. |
| [`ADR-027`](../agents/decisions/ADR-027.md) | Mini-FS persistente ZENFS01. |
| [`ADR-028`](../agents/decisions/ADR-028.md) | PFS visible en VFS mediante instantánea read-only. |

## Tareas, informes y evidencia

| Ruta | Contenido |
|---|---|
| [`agents/tasks/`](../agents/tasks/) | Contratos de tarea (objetivo, archivos, aceptación). |
| [`agents/reports/`](../agents/reports/) | Resultados ejecutados, JSON y métricas por tarea. |
| [`agents/decisions/`](../agents/decisions/) | ADR. |

Informes de referencia por hito:

| Hito | Evidencia principal |
|---|---|
| 1 | [`TASK-210`](../agents/reports/TASK-210.md), [`TASK-211`](../agents/reports/TASK-211.md) |
| 2 | [`TASK-310`](../agents/reports/TASK-310.md), [`TASK-311`](../agents/reports/TASK-311.md) |
| 3 | [`TASK-410`](../agents/reports/TASK-410.md), [`TASK-411`](../agents/reports/TASK-411.md) |
| 4 | [`TASK-510`](../agents/reports/TASK-510.md), [`TASK-511`](../agents/reports/TASK-511.md) |
| 5 | [`TASK-610`](../agents/reports/TASK-610.md), [`TASK-611`](../agents/reports/TASK-611.md) |
| 6 | [`TASK-710`](../agents/reports/TASK-710.md), [`TASK-711`](../agents/reports/TASK-711.md) |
| 7 | [`TASK-701`](../agents/reports/TASK-701.md), [`TASK-703`](../agents/reports/TASK-703.md) |
| 8 | [`TASK-801`](../agents/reports/TASK-801.md), [`TASK-802`](../agents/reports/TASK-802.md) |
| 9 | [`TASK-902`](../agents/reports/TASK-902.md), [`TASK-902J`](../agents/reports/TASK-902J.md), [`TASK-912`](../agents/reports/TASK-912.md) |
| 10 | [`TASK-905`](../agents/reports/TASK-905.md), [`TASK-907`](../agents/reports/TASK-907.md), [`TASK-908`](../agents/reports/TASK-908.md), [`TASK-911`](../agents/reports/TASK-911.md), [`TASK-913`](../agents/reports/TASK-913.md) |

## Histórico

Los siguientes documentos se conservan para trazabilidad, pero **no** son estado
vigente:

- [`agent-handoff/CODEX_WORK.md`](agent-handoff/CODEX_WORK.md)
- [`agent-handoff/CONTEXT.md`](agent-handoff/CONTEXT.md)
- [`agent-handoff/CURRENT_STATE.md`](agent-handoff/CURRENT_STATE.md)
- [`agent-handoff/DSH_RESUME.md`](agent-handoff/DSH_RESUME.md)

## Cómo se mantiene este índice

- Un documento nuevo entra aquí con una frase de alcance y su ruta relativa.
- Un documento histórico se marca como tal; no se borra la evidencia.
- Las cifras de tests y los hashes se citan con fecha y comando; no se copian sin
  volver a ejecutar la puerta. Los conteos del corte 0.1.1 son **163** (compilador), **43** (Ferros), **6**
  (benchmarks) y **166** (self-hosting); el árbol posterior exige 163/44/6/166.
- Los enlaces relativos se revisan antes de cerrar una tarea documental; un
  enlace roto es deuda documental, no un detalle estético.
