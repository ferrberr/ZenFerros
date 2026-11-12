# TASK-510: Hito 4 — memoria e interrupciones básicas

**Agente**: 00 (integración/main/IDT-PIC-PIT Zen/tests/docs), memory_engineer (PMM/VMM/arena Zen), boot_engineer (primitivas y stubs asm), compiler_review (revisión independiente).
**Estado**: COMPLETADA
**Prioridad**: ALTA
**Dependencias**: [TASK-410, TASK-411]
**Archivos**: [ferros/kernel/, ferros/boot/, ferros/tests/, infrastructure/scripts/build_ferros.py, infrastructure/scripts/boot_ferros.py, README.md, ARCHITECTURE.md, ROADMAP.md, docs/ferros/, agents/decisions/ADR-010.md, agents/reports/TASK-510*]

## Objetivo
Arrancar en QEMU un kernel Zen que usa mapa Multiboot para asignar/liberar páginas, reemplaza identidad RWX por páginas4KiB con permisos/NX y null guard, ofrece arena de heap, maneja breakpoint y page faults esperados, y recibe IRQ0 del PIT vía PIC/IDT. Probar normal/optimizado y fallos.

## Propiedad e integración
Repositorios Git aislados /tmp/zenferros-task510-memory y /tmp/zenferros-task510-arch, ramas homónimas. Memory solo memory.zen. Arch solo entry.S/linker.ld/io.S/new interrupts.S. Root archivos restantes, concatena unidades Zen en orden explícito (sin afirmar soporte módulos), copia entregas secuencialmente. Snapshot anterior /tmp/zenferros-task510-baseline. Revisor solo TASK-511 report; no componentes concurrentes. Git workspace vacío/protegido.

## Contratos de almacenamiento/ABI (todas funciones extern C unsafe)
Arch retorna direcciones u64: ferros_memory_state (4096B), ferros_pmm_bitmap (8192B), ferros_page_tables (36*4096B), ferros_heap_start/end (arena64KiB), ferros_interrupt_state (4096B), ferros_idt_address (4096B), ferros_kernel_end, ferros_text_start/end, ferros_rodata_start/end. Todo reservado en BSS/linker y alineado según uso. Bitmap:4096B libres+4096B gestionadas (cap64MiB=16384páginas). PMM state privado a memory.zen; IRQstate privado a root.
Arch: ferros_enable_nx()->u64 (1 ok), ferros_read_cr0/cr3()->u64, ferros_load_cr3(u64), ferros_invlpg(u64); ferros_isr_address(u64)->u64; ferros_load_idt(u64,u16); ferros_breakpoint(); ferros_probe_null(); ferros_probe_write_ro(); ferros_null_fault_site/resume()->u64, ferros_ro_fault_site/resume/address()->u64; ferros_wait_interrupt()=sti/hlt/cli, ferros_interrupt_disable(). ISR dispatcher Zen pub interrupt_dispatch(vector:u64,error:u64,frame:u64,cr2:u64); frame apunta a RIP para recuperación comprobada.
Memory funciones internas: pmm_init(info:u64)->bool; pmm_alloc()->u64; pmm_free(u64)->bool; pmm_free_count()->u64; pmm_self_test()->bool; vmm_init()->bool; vmm_self_test()->bool; heap_init(); heap_alloc(size:u64,alignment:u64)->u64; heap_self_test()->bool. Sin globals del lenguaje: estado explícito en zonas reservadas.

## Criterios de aceptación / pruebas necesarias
- [x] PMM bitmap desde mapa real, reservado low1MiB/kernel/bootdata, alloc/free/double-free/rango/exhaustión verificados.
- [x] Tablas4KiB primeras64MiB, NXE/WP, textoRX/rodataR+NX/dataRW+NX, null no presente; CR3 activo y fault real de null/RO verificados.
- [x] Arena heap con tamaño/alineación/límites comprobados.
- [x] IDT256, stubs de excepción y marco ABI/GPR, breakpoint/int3 y pagefault recuperable con sitio/CR2/error validados; inesperados terminan fallo.
- [x] PIC remapeado/PIT~100Hz, IRQ0 incrementa contador y EOI, 3ticks reales con espera sti/hlt/cli; timeout externo conserva logs ante bloqueo.
- [x] Kernel/algoritmos/IDT/PIC/PIT en Zen; asm solo CPU/register/entry/interrupt linkage.
- [x] Pruebas normales/optimizadas QEMU y host-safe donde proceda, regresión anterior; revisión cruzada favorable y evidencia/limitaciones.

## Resultado esperado
Hito4 mínimo integrado; sin scheduler/procesos/usuarios/SMP ni allocator general concurrente. No falsear soporte de módulos/globals/estructuras Zen que aún no existen.

## Cierre —2026-11-11
57tests pasan,6boots64MiB+2RAMextra+2negativos con resultados esperados. Revisión independiente favorable TASK511 y evidencia TASK510. Hito4mínimo integrado.
