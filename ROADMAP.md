# ROADMAP.md — Plan de Desarrollo por Fases

## Estado a 2026-11-11 — Hito7 cerrado (DSH)

**Hito 1: completado y verificado** mediante TASK-210 y revisión cruzada TASK-211. La ruta implementada es Zen → frontend comprobado → C11 → cc → ELF, decisión ADR-007. **Hito 2: verificado** en TASK-310/TASK-311: objeto ELF64 freestanding sin libc, ABI C, bits/casts y punteros volatile/unsafe. **Hito 3: verificado** mediante TASK-410/TASK-411: kernel Zen y UART, bootstrap64 mínimo, 6 boots TCG con serie exacta y estado33. **Hito4: verificado** TASK-510/TASK-511, PMM/VMM/heap/excepciones/PIT con memoria/IRQs en Zen. El subconjunto nativo vigente está en `docs/zen/mvp-native.md`; la gramática completa sigue siendo propuesta.

Hito5 verificado:3threads con stacks/guardas, preemption PIT y yield/exit; revisión TASK-611. Hito6 verificado TASK-710/711: ELF Zen separado en CPL3, mapas U/S y W^X, loader, int0x80 write/exit/ticks y faults contenidos. Hito7 verificado TASK-701: RAMFS/VFS en memoria, syscalls de archivos4–7 e init/shell de CPL3 con `ls`/`cat` sobre `hello.zen`; 46 tests del compilador,20 de Ferros y6arranques estado33 con `HITO 7 OK`. Fase7 completada salvo binarios separados: TASK-703 shell interactivo COM1 verificado (34 tests Ferros, 6/6 QEMU estado 33, writes=18, sin entrada termina 33). Próximohito a decidir: VFS ampliado/persistencia, o Fase 8 con la línea base de benchmarks. Hito8 verificado TASK-801: laboratorio de benchmarks reproducible (arith/collatz/mem/sort en Zen, C, C++ y Rust) con verificación de checksum, métrica de CPU, tres suites con rangos, resultados versionados y ADR-013; Zig/clang no disponibles y declarados. Conclusión: paridad aproximada Zen/C/C++ dentro del ruido (Zen/C 0,9385–1,0408 en 3 suites); sin declaración de superioridad. QEMU11.1.3 local/TCG disponible, sin KVM; no existe `.git` en el workspace. Los informes antiguos no sustituyen evidencia actual.

## Fase 0: Reconocimiento y Preparación — BASE RECUPERADA
**Objetivo**: Inspeccionar entorno, inicializar repositorio, documentar capacidades, crear tareas iniciales.

| Tarea | ID | Estado | Agente | Evidencia |
|-------|-----|--------|--------|-----------|
| Inspeccionar herramientas y sistema | TASK-001 | ✅ COMPLETADA | 00 | `agents/reports/TASK-001.md` |
| Crear estructura repositorio | TASK-002 | ✅ COMPLETADA | 00 | Estructura en disco |
| Crear README.md | TASK-003 | ✅ COMPLETADA | 00 | `README.md` |
| Crear AGENTS.md | TASK-004 | ✅ COMPLETADA | 00 | `AGENTS.md` |
| Crear ROADMAP.md | TASK-005 | ✅ COMPLETADA | 00 | (este archivo) |
| Crear ARCHITECTURE.md | TASK-006 | ✅ COMPLETADA | 00 | Actualizada a implementación MVP |
| Preparar QEMU y dependencias | TASK-007 | ✅ COPIA LOCAL | 00/13 | TASK-410, manifest fijado, sin instalación de sistema |
| Decidir bootstrap compiler tech | TASK-008 | ✅ COMPLETADA | 00 | ADR-007 sustituye backend MVP |

---

## Fase 1: Especificación Mínima de Zen
**Objetivo**: Definir gramática inicial, tipos primitivos, funciones, control de flujo, punteros, structs, modelo memoria inicial, ABI.

| Tarea | ID | Estado | Agente | Dependencias |
|-------|-----|--------|--------|--------------|
| Diseñar gramática MVP (EBNF) | TASK-101 | BORRADOR; MVP ejecutable documentado | 01 | TASK-008 |
| Definir tipos primitivos y layout | TASK-102 | ⏳ PENDIENTE | 01/05 | TASK-101 |
| Definir modelo de memoria v1 (ownership/borrowing/regiones) | TASK-103 | ⏳ PENDIENTE | 01/05 | TASK-102 |
| Definir ABI y calling convention x86_64 | TASK-104 | ⏳ PENDIENTE | 01/03 | TASK-102 |
| Especificar modelo de errores (Result/Option/panic) | TASK-105 | ⏳ PENDIENTE | 01 | TASK-101 |
| Crear tests de aceptación sintáctica | TASK-106 | ⏳ PENDIENTE | 02 | TASK-101 |
| Documentar en `docs/zen/spec-v0.md` | TASK-107 | ⏳ PENDIENTE | 01 | TASK-101..106 |

---

## Fase 2: Compilador Zen Mínimo (Rust + backend C11 de bootstrap)
**Objetivo**: Compilador funcional que lea `.zen`, genere ejecutable nativo, CLI básica.

| Tarea | ID | Estado | Agente | Dependencias |
|-------|-----|--------|--------|--------------|
| Setup proyecto Rust (backend C11, ADR-007) | TASK-201 | ✅ MVP | 02/03 | TASK-008 |
| Implementar Lexer | TASK-202 | ✅ MVP integrado, TASK-212 | 02 | TASK-201, TASK-101 |
| Implementar Parser → AST | TASK-203 | ✅ Subconjunto nativo TASK-210 | 02 | TASK-202 |
| Implementar análisis semántico básico | TASK-204 | ✅ Subconjunto nativo TASK-210 | 02 | TASK-203, TASK-102 |
| Implementar typechecker v1 | TASK-205 | ✅ Escalares MVP; memoria pendiente | 02/05 | TASK-204, TASK-103 |
| Implementar lowering (AST comprobado → C11) | TASK-206 | ✅ MVP, ADR-007 | 03 | TASK-205, TASK-104 |
| Implementar backend: codegen + linking | TASK-207 | ✅ Hosted Linux vía cc | 03 | TASK-206 |
| CLI: `zen build`, `zen run`, `zen check` | TASK-208 | ✅ Implementada | 15 | TASK-207 |
| Tests: hello world, aritmética, funciones, structs | TASK-209 | ✅ Escalares; arrays TASK-213 y structs TASK-214 | 02/15 | TASK-208 |
| Arrays de tamaño fijo `[T; N]` (locales, bounds-check) | TASK-213 | ✅ COMPLETADA (163 tests compilador) | 02/03 | TASK-208 |
| Structs nominales escalares (locales) | TASK-214 | ✅ COMPLETADA: 15 tests; ADR-017 | 02/03 | TASK-208 |

---

## Fase 3: Zen para Sistemas (Freestanding)
**Objetivo**: Capacidades mínimas para escribir kernel: punteros raw, volatile, inline asm, sections, no-std, intrínsecos.

| Tarea | ID | Estado | Agente | Dependencias |
|-------|-----|--------|--------|--------------|
| Perfil CLI freestanding (sin atributo no_std) | TASK-301 | ✅ MVP TASK-310 | 02/03 | TASK-209 |
| Punteros raw, `volatile`, `align`, `packed` | TASK-302 | ✅ raw/volatile; align/packed PENDIENTE | 02/03/05 | TASK-301 |
| Inline assembly | TASK-303 | ⏳ PENDIENTE; helpers externos C/asm para primer boot | 03 | TASK-301 |
| Secciones de enlazado personalizadas | TASK-304 | ⏳ PENDIENTE | 03 | TASK-301 |
| Intrínsecos: memcpy, memset, CPU ops | TASK-305 | ⏳ PENDIENTE | 03/04 | TASK-302 |
| Panic handler y unwinding controlado | TASK-306 | ✅ trap sin unwind; handler configurable PENDIENTE | 02/03 | TASK-301 |
| Perfil target x86_64-unknown-none | TASK-307 | ✅ GCC anfitrión; cross general PENDIENTE | 03 | TASK-301 |
| Tests: freestanding sin libc | TASK-308 | ✅ enlace/ejecución Linux sin libc; bare-metal en Hito 3 | 02/13 | TASK-307 |

---

## Fase 4: Primer Arranque de Ferros (HITO CRÍTICO)
**Objetivo**: Kernel mínimo en Zen → imagen bootable → QEMU → "FERROS KERNEL / Powered by Zen / Boot successful"

| Tarea | ID | Estado | Agente | Dependencias |
|-------|-----|--------|--------|--------------|
| Multiboot1 directo QEMU + bootstrap original (ADR-009) | TASK-401 | ✅ MVP TASK-410 | 07 | TASK-308 |
| Linker script kernel x86_64 | TASK-402 | ✅ TASK-410 | 07/03 | TASK-308 |
| Entrada asm Multiboot32 → longmode64 → Zen | TASK-403 | ✅ TASK-410 | 07 | TASK-402 |
| Kernel main en Zen: init serial, print | TASK-404 | ✅ TASK-410 | 06/07 | TASK-308, TASK-403 |
| Build system Ferros (Python + zen/cc/ld/objcopy) | TASK-405 | ✅ MVP ADR-009 | 07/15 | TASK-401..404 |
| Script QEMU automatizado + serial capture | TASK-406 | ✅ timeout/cancelación/logs | 13 | TASK-405 |
| Test integración: boot + output verification | TASK-407 | ✅ 6 boots, 8 tests, revisión TASK-411 | 13 | TASK-406 |

---

## Fase 5: Memoria e Interrupciones
| Tarea | ID | Estado | Agente | Dependencias |
|-------|-----|--------|--------|--------------|
| Physical Memory Manager (bitmap/bump) | TASK-501 | ✅ MÍNIMO TASK-510 | 08 | TASK-407 |
| Virtual Memory Manager (paging 4-level) | TASK-502 | ✅ MÍNIMO TASK-510 | 08 | TASK-501 |
| Kernel heap (arena/linked list) | TASK-503 | ✅ MÍNIMO TASK-510 | 08 | TASK-502 |
| IDT / ISR / exception handlers | TASK-504 | ✅ MÍNIMO TASK-510 | 06/08 | TASK-407 |
| Timer (PIT/HPET/LAPIC) + tick | TASK-505 | ✅ MÍNIMO TASK-510 | 09/10 | TASK-504 |
| Tests unitarios memoria + interrupts | TASK-506 | ✅ MÍNIMO TASK-510 | 08/13 | TASK-505 |

---

## Fase 6: Procesos y Multitarea
| Tarea | ID | Estado | Agente | Dependencias |
|-------|-----|--------|--------|--------------|
| Thread/context switch (procesos aislados pendientes) | TASK-601 | ✅ KERNEL THREADS TASK-610 | 09 | TASK-506 |
| Scheduler (round-robin; prioridad/CFS futuros) | TASK-602 | ✅ RR PREEMPTIVO TASK-610 | 09 | TASK-601 |
| Syscall interface (int0x80; instrucción SYSCALL pendiente) | TASK-603 | ✅ MÍNIMA TASK-710/ADR-012 | 06/09 | TASK-601 |
| Userspace loader (ELF64 estático/CPL3) | TASK-604 | ✅ MÍNIMO TASK-710 | 12 | TASK-603 |
| IPC básico (message passing) | TASK-605 | ⏳ PENDIENTE | 09 | TASK-603 |
| Tests: context switch, scheduler, syscall | TASK-606 | ✅ MÍNIMOS TASK-610/710; IPC PENDIENTE | 09/13 | TASK-601, TASK-603, TASK-604 |

---

## Fase 7: Almacenamiento y Userspace
| Tarea | ID | Estado | Agente | Dependencias |
|-------|-----|--------|--------|--------------|
| VFS + RAMFS | TASK-701 | ✅ MÍNIMO (TASK-701); sin directorios dinámicos/unlink/persistencia | 11 | TASK-606 |
| VirtIO block driver | TASK-702 | ⏳ PENDIENTE | 10 | TASK-606 |
| Init process + shell básico | TASK-703 | ✅ COMPLETADA: shell interactivo COM1 RX (syscall 8), comandos help/ls/cat/exit, transcripción verificada en QEMU | 12 | TASK-604, TASK-701 |
| User libstd (syscall wrappers, print, alloc) | TASK-704 | WRAPPERS MÍNIMOS TASK-710; STDLIB/ALLOC PENDIENTES | 12/01 | TASK-308, TASK-603 |
| User programs en Zen (ls, cat, echo) | TASK-705 | ◐ ls/cat vía shell integrado; binarios separados/echo PENDIENTES | 12 | TASK-704 |

---

## Fase 8: Optimización Profunda
| Tarea | ID | Estado | Agente | Dependencias |
|-------|-----|--------|--------|--------------|
| Benchmarks infra + runner | TASK-801 | ✅ MÍNIMO (TASK-801, ADR-013): 4 benchmarks × 4 lenguajes, CPU-time, JSON/MD; sin perf/floats/SIMD | 04/13 | TASK-209 |
| Perf analysis: compiler, kernel, syscalls | TASK-802 | ✅ PARCIAL: flags -O2/-O3/LTO medidos; mantener -O2 (ADR-015); perf/kernel pendientes | 04 | TASK-801 ✅ |
| LLVM optimization passes tuning | TASK-803 | ⏳ PENDIENTE | 03/04 | TASK-802 |
| SIMD / vectorización en Zen | TASK-804 | ⏳ PENDIENTE | 01/03/04 | TASK-205 |
| PGO / LTO pipeline | TASK-805 | ⏳ PENDIENTE | 03/04 | TASK-803 |
| Kernel scheduler/memory optimization | TASK-806 | ⏳ PENDIENTE | 04/08/09 | TASK-606 |

---

## Fase 9: Madurez y Self-Hosting
| Tarea | ID | Estado | Agente | Dependencias |
|-------|-----|--------|--------|--------------|
| Zen stdlib completa (collections, io, sync) | TASK-901 | ◐ PARCIAL: builtins `str_eq/str_cmp/str_find` (901A) y `str_starts_with/ends_with/rfind` (901B); colecciones/IO/alloc PENDIENTES | 01/02 | TASK-209 |
| Compilador Zen en Zen (fases bootstrap) | TASK-902 | ◐ ETAPA B: lexer contador y con tokens, parser/evaluador, AST, intérpretes y typechecker y cuatro codegens C en Zen (166 tests); stdlib completa PENDIENTE | 01/02/03 | TASK-901 |
| Self-hosting verification | TASK-903 | ◐ Parcial: paridad de lexer/parser y AST/Zen; compilador completo PENDIENTE | 03/17 | TASK-902 |
| AST real en Zen con arrays fijos | TASK-902C | ✅ COMPLETADA: 14 tests; selfhost 166 | 02/03 | TASK-902 |
| Formatter, linter, LSP | TASK-904 | ✅ COMPLETADA (mínimos): TASK-904A `zen fmt`, TASK-909 `zen lint --json`, TASK-910 `zen lsp` | 15 | TASK-208 |
| Fuzzing / security audit | TASK-905 | ◐ PARCIAL: estrés QEMU + fuzz diferencial acotado (`stress.py`); campaña/auditoría PENDIENTES | 14 | TASK-606 |
| Documentation completa | TASK-906 | ⏳ PENDIENTE | 15 | TASK-901 |
| CI/CD reproducible builds | TASK-907 | ✅ PARCIAL: puerta `verify_all.py` + `docs/quality.md`; CI externa PENDIENTE | 17 | TASK-405 |
| Builds reproducibles locales + manifiesto | TASK-908 | ✅ COMPLETADA: C/kernel/usuario idénticos en 2 builds; `repro_build.py` integrado en la puerta | 17 | TASK-907 |
| Matriz de CI local (quick/defecto/full) | TASK-911 | ✅ COMPLETADA: `ci_matrix.py` + `docs/ci.md`; quick/full PASS; JSON | 17 | TASK-907/908 |
| Workflow CI remoto + validador | TASK-918 | ✅ COMPLETADA: `.github/workflows/ci.yml` (no ejecutado), 44 checks locales PASS | 17 | TASK-911 |
| Campaña de estabilidad repetida | TASK-913 | ✅ COMPLETADA: 5 rondas quick + 2 full PASS; JSON v1; `docs/stability-campaign.md` | 14/17 | TASK-905/911 |
| Campaña ampliada Hito 10 | TASK-917 | ✅ COMPLETADA: 10 quick + 3 full, 68 QEMU, gate 8/8; informe | 14 | TASK-913 |

---

## Priorización inmediata

1. Hito 1 cerrado: 23 pruebas unitarias + 10 de CLI pasan en debug y release; revisión independiente favorable (TASK-210, TASK-211, TASK-212).
2. Hito 2 cerrado (histórico): 46 tests por perfil debug/release, objeto sin libc, ABI C escalar/raw, bits/casts/volatile; enlace estático y revisión independiente TASK-311.
3. Hito 3 cerrado: arranque QEMU TCG real desde kernel Zen, imagen ELF, UART, estado y serie comprobados; revisión favorable.
4. Hito4 cerrado (histórico): mapas reales/reservas, páginas protegidas/heap, IDT/excepciones yPIT;57tests pasaban y10bootsinclnegativos verificados.
5. Hito5 cerrado:3threads kernel, guardas, preemption/yield/exits, contadores reales y negativos; revisión independiente favorable.
6. Hito6 cerrado (histórico): ELF Zen CPL3, loader con rollback, permisos U/S/W^X, write/exit/ticks, faults contenidos y pruebas negativas;65tests pasaban.
7. Hito7 cerrado (TASK-701): RAMFS1MiB/256bloques, VFS open/read/write/close, syscalls4–7 desde CPL3 y flujo init/shell con `ls`/`cat` verificado;tests verdes y 6 arranques estado33. Siguiente: decidir shell interactivo/VFS ampliado o persistencia mínima antes de ampliar lenguaje o drivers.
8. Hito8 cerrado (TASK-801): línea base reproducible en `docs/benchmarks/results.md`; paridad aproximada Zen/C/C++ dentro de la variabilidad del host (Zen/C 0,9385–1,0408 en 3 suites; ejecuciones adicionales pueden salir del rango), sin declarar superioridad (mismo backend C11). Siguiente: decidir shell interactivo/VFS ampliado o persistencia, y usar los benchmarks como detector de regresiones.
9. TASK-703 cerrada: shell interactivo COM1 RX con syscall 8; 34 tests Ferros, 163 compilador, 6 benchmarks y 6/6 QEMU estado 33.
10. Hito 9 (parcial) y Hito 10: frontend en Zen verificado (lexer contador y con tokens, parser/evaluador, AST, intérpretes de sentencias/funciones, typechecker y cuatro codegens C; 166 tests, ADR-014/016/017); arrays y structs TASK-213/214; VFS multifichero/readdir TASK-215; estrés/fuzz TASK-905; puerta `verify_all.py` y `docs/quality.md`; ADR-015 mantiene -O2. Siguiente: CI remoto, stdlib amplia, self-hosting completo o persistencia/VFS.
11. Ampliar Zen solo según necesidades verificables de Ferros; conservar tests hosted como regresión.

Los detalles de Fases 3–9 son un plan y pueden ajustarse mediante ADR; no indican implementación actual.

El cierre Hito4 es mínimo/singleCPU: arena sin free general, identidad fija64MiB sin procesos, IRQ0legacy sinSMP/IST. Las unidades se concatenan; no se declara soporte de módulos/globals/structs Zen.
