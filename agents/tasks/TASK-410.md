# TASK-410: Hito 3 — primer arranque de Ferros en QEMU

**Agente**: 00 Orquestador (kernel Zen, build/QEMU, tests, evidencia); boot_engineer (entry/linker/helpers); compiler_review (revisión independiente).
**Estado**: COMPLETADA
**Prioridad**: ALTA
**Dependencias**: [TASK-310, TASK-311]
**Archivos**: [ferros/boot/, ferros/kernel/main.zen, ferros/kernel/arch/, ferros/tests/, infrastructure/qemu/, infrastructure/scripts/, docs/ferros/, README.md, ROADMAP.md, ARCHITECTURE.md, agents/decisions/ADR-009.md, agents/reports/TASK-410*]

## Objetivo medible
Compilar kernel Zen a código máquina y arrancarlo realmente en QEMU x86_64 con salida serie exacta FERROS KERNEL / Powered by Zen / Boot successful y terminación automatizada verificable.

## Propiedad y contratos
Boot engineer solo entry.S/linker.ld/io.S en Git aislado /tmp/zenferros-task410-boot, rama task410-boot; orquestador integra entrega secuencialmente y escribe kernel/scripts/tests/docs. Reviewer solo informe TASK-411. No tocar compilador salvo fallo comprobado y nueva revisión. .git del workspace vacío/protegido; no declarar merges ficticios.

## Criterios de aceptación / pruebas necesarias
- [x] ELF x86_64 kernel sin libc; imagen ELF32 contenedora Multiboot1 para loader directo QEMU, payload long-mode64. Header/entry/layout verificados.
- [x] Bootstrap asm: paginación identidad, GDT, long mode y stack ABI; solo excepciones indispensables en asm. UART init/polling/mensajes/validación boot en Zen.
- [x] QEMU TCG aislado sin red/discos físicos, RAM limitada, timeout, stdout serie/logs, isa-debug-exit con estado comprobado.
- [x] Mensaje de identificación exacto emitido por kernel generado de Zen; ejecuciones normales y optimizadas reales.
- [x] Tests negativos de validador timeout/código/salida, test de driver Zen con IO simulado y regresión compilador.
- [x] Procedencia/licencias herramientas, ratio fuente Zen/asm, comandos, versiones, métricas y fallos documentados.
- [x] Revisión cruzada de bootstrap/kernel/scripts sin bloqueantes.

## Resultado esperado
Hito 3 integrado con comando reproducible y logs reales. Sin PMM/IDT/scheduler/userspace; siguiente Hito 4 memoria/interrupciones.

## Cierre — 2026-11-11
6 boots reales QEMU33, 8 tests de boot/driver y 46 de compilador pasan; revisión independiente favorable TASK-411. Evidencia en agents/reports/TASK-410.md y subdirectorio de logs TASK-410/.
