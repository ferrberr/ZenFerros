# TASK-610: Hito5 — threads y scheduler de kernel

**Agente**: 00 integración/tests/docs; scheduler_impl (gpt-6.1-sol/high); context_impl (gpt-6.1-sol/medium); scheduler_review (gpt-6.1-sol/high, distinto de autores).
**Estado**: COMPLETADA
**Prioridad**: ALTA
**Dependencias**: [TASK-510, TASK-511]
**Archivos**: [ferros/kernel/, ferros/tests/, infrastructure/scripts/, docs/ferros/, README.md, ROADMAP.md, ARCHITECTURE.md, agents/decisions/ADR-011.md, agents/reports/TASK-610*]

## Objetivo verificable
Ejecutar3threads de kernel Zen con stacks privados/guardas, round-robin preemptivo por PIT y yield cooperativo, salida de thread y retorno al controlador. Probar contexto GPR/stack e intercalado real (un worker no cede), detectar guards/estado inválido y preservar memoria/IRQs anteriores.

## Aislamiento/propiedad
Git aislado /tmp/zenferros-task610-scheduler rama task610-scheduler solo scheduler.zen; /tmp/zenferros-task610-arch rama task610-arch solo nuevo context.S. Root archivos restantes, integra entregas secuencialmente. Snapshot previo /tmp/zenferros-task610-baseline. .git workspace vacío/protegido: no simular merges. Reviewer solo TASK-611 report.

## Arquitectura y API compartida
UnaCPU, un addressspace, sin userspace/SMP/SIMD. Switch SystemV explícito guarda6calleeGPR+RSP, siempreIFoff; si se llama desdeIRQ el marco15GPR/IRET existente permanece en stack de thread hasta reanudar. EOI antes de elegir/cambiar thread. Nuevos threads comienzan en trampoline con ABI alineada y thread_entry(id:u64); no retorno normal.
Arch context.S: ferros_context_switch(old_slot:u64,new_rsp:u64); ferros_thread_trampoline()->u64 getter; ferros_thread_stack_guard(id:u64)->u64 /top(id)->u64 paraids1..3 (guard4KiB+stack32KiBcadauno, BSS); ferros_scheduler_state()->u64 (4096B); ferros_irq_save()->u64 (flags previos yCLI), ferros_irq_restore(flags:u64) (soloIF), ferros_context_probe()->u64 (todos15GPR+canary a través de sti/hlt/cli, dejaIFoff, retorna1siok). Primers frame64bytes: +0r15,+8r14,+16r13,+24r12(id),+32rbx,+40rbp,+48trampoline,+56dummy; savedrsp=stack_top-64. Trampoline entraRSP8mod16, llama thread_entry alineado y si retorna llama thread_returned()->void fatal.
Zen scheduler APIs internas: scheduler_init()->bool, scheduler_self_test()->bool (crea3threads y ejecuta/prueba; llamadoIFoff conPIT configurado), scheduler_on_timer() (IRQ0/IFoff), scheduler_yield(), scheduler_exit() (no debe reanudarse), scheduler_active()->bool. pub thread_entry(id:u64), thread_returned(). Root vmm_guard_page(address:u64)->bool desmapea solo páginaBSSalineada yflush; scheduler aplica3guards. Helpers irq_get(16)=ticks, irq_set(40,1)=PIT handler armado, out8/in8 existentes; scheduler_self_test puede usar `scheduler_timer_start/stop` que root implementa: PIC/PIT habilitados/deshabilitados conIFoff. panic kernel_panic(str), serial_write(str) solo controlador (workers sinIO/alloc).
EstadoBSS explícito, offsets documentados en scheduler.zen. Thread0=controlador/boot, threads1..3; estadosREADY/RUNNING/EXITED/BLOCKED. Controller bloqueado hasta que todos terminan; no resucitarEXITED. PMM/heap nunca desdeIRQ ni conIFon. Switch conserva6GPRABI, ISR preserva15 alpreemptar. No soporta bloquear en recursos ni prioridad.

## Aceptación / pruebas
- [x] Tres stacks32KiB con guard no presente, dentroBSSreservado/NX, frames iniciales ABI correctos.
- [x] Roundrobin Zen porIRQ0 real yyield, sin llamar workers enserie; worker noyield requiere progreso de otros (preemption imprescindible).
- [x] Cada worker verifica progreso/hash/localcanary/context_probe, exits y retorno alcontroller; no returns accidentales ni stack reuse.
- [x] Conteos reales de switches/preemptions/yields/completions y registros/stack preservados, sinfalsemarkers.
- [x] Guardwrite ythreadreturned/estado inválido provocanpanic35 enbootnegativo, nuncaH5OK.
- [x] Tests host de políticas (mocks sin ejecutarCLI/IO) yQEMU normales/optimizados/repetidos/memoria32/128, regresión57previas.
- [x] Evidencia/revisión independiente favorable; sin afirmar procesos/userspace/SMP/generalallocator.

## Resultado
Hito5 kernelthreads mínimo integrado, siguientehito programas deusuario/ABI/syscalls. El tamaño real de fase siguiente se definirá tras inspección.

## Recuperación tras límite de uso
La integración parcial persiste; agentes anteriores ya no están activos y /tmp no sobrevivió. Se recrean repositorios aislados. Scheduler y revisión: sol/high; ASM: sol/medium, tareas acotadas con contrato compartido. Astra dio límite de uso, no se reintenta ese modelo.

## Cierre — 2026-11-11
Hito5 mínimo integrado. 61tests pasan y17ejecuciones QEMU finales cumplen resultados esperados; revisión técnica favorable TASK-611, evidencia TASK-610. Modelos finales: sol/high scheduler+auditor, sol/medium ASM.
