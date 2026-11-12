# TASK-710: Hito 6 — ELF Zen en ring 3 y syscalls mínimas

**Agente**: 00 integración, memoria/loader/syscalls/tests; context_recovery ASM (Sol heredado); boot_engineer user/build (Sol). Perfiles nuevos rechazados por límite de agentes, detalles ADR-012.
**Estado**: COMPLETADA
**Prioridad**: ALTA
**Dependencias**: [TASK-610, TASK-611]
**Archivos**: [ferros/kernel/userspace.zen, ferros/kernel/arch/x86_64/{userspace.S,interrupts.S,abi.zen}, ferros/kernel/{interrupts.zen,main.zen}, ferros/user/, ferros/tests/, infrastructure/scripts/, docs/ferros/, agents/decisions/ADR-012.md]

## Objetivo y resultado esperado
Compilar un ELF64 estático separado desde Zen, validar y cargar PT_LOAD, ejecutarlo en CPL3 con páginas U/S y W^X, stack propio/guard y retorno controlado a kernel. ABI inicial int0x80: write, exit y ticks. Rechazar punteros y llamadas inválidas, contener faults de usuario y conservar los hitos anteriores. Sin procesos concurrentes ni filesystem en este hito.

## Propiedad e integración
Workspace .git vacío/protegido; snapshots Git en /tmp para trabajo paralelo, sin afirmar merges en el repositorio principal. user_arch posee únicamente nuevos userspace.S y cambios interrupts.S en su snapshot; user_build posee ferros/user/ y build_user.py en otro snapshot. Root integra entregas secuencialmente y posee el resto. TASK-711 audita código crítico e integración, distinto de autores.

## Contrato compartido
Una CPU; scheduler kernel ya terminado al entrar usuario. IRQs deshabilitados durante loader/syscalls. Ventana virtual [0x40000000,0x40200000), imagen debajo0x40100000; stack4páginas termina0x40200000, guard0x401fb000. Dos tablas BSS PD/PT separadas conectadas a PDPT[1], PML4[0] U=1 y hojas kernel U=0. Páginas físicas desde PMM, zero/copy antes de exponer RX/RW-NX, liberación al terminar.

ASM: ferros_user_arch_init()->u64 configura GDT/TSS64/RSP0 sin alterar selectores kernel8/16; usuario CS0x23 SS0x1b; ferros_user_enter(entry:u64,stack:u64,arg:u64)->u64 guarda contexto controlador IF0 y entra IRETQ IF1/IOPL0, RDI=arg; ferros_user_leave(result:u64) abandona stack de trap y retorna al controlador IF0. getters ferros_user_state() (4KiB), ferros_user_tables() (8KiB), ferros_user_kernel_stack_bottom/top() (32KiB). No GSbase ni SIMD; usuario sin TLS, compilado general-regs-only. Solo IDT128 DPL3, nuevo ISR128 usa wrapper15GPR común. frame del dispatcher apunta RIP, RAX guardado en frame-24, RDI en frame-64, RSI frame-56, RDX frame-48 (verificar contra ASM).

Usuario: pub fn user_entry(case_id:u64), wrappers extern C user_syscall(number:u64,a:u64,b:u64,c:u64)->u64 usando RAX/RDI/RSI/RDX en int128. Caso0 valida CPL3, write/ticks/rechazos y exit0. Casos1..6 provocan aislamiento: leer kernel0x100000, escribir texto0x40000000, CLI, ejecutar stack, leer guard0x401fb000, int0x81. ELF ET_EXEC EM_X86_64, PT_LOAD página alineada RX/R/RW separados, sin dynamic/interp/relocaciones.

## Criterios de aceptación y pruebas necesarias
- [x] ELF separado real sin símbolos indefinidos/libc; validación negativa de headers/rangos/overflow/overlap/WX/entry, BSS cero y rollback PMM.
- [x] CPL3 real, write validado página a página (null/kernel/gap/overflow/límite rechazados), exit/ticks/ENOSYS y registros ABI preservados.
- [x] PF usuario supervisor/RO/NX/guard y GP privilegiado/IDT denegado contenidos; controlador continúa, kernel no imprime éxito prematuro.
- [x] Regresión compiler/Ferros, QEMU normal/optimizado repetido y RAM32/128MiB, serie/estado/contadores reales.
- [x] Evidencia de comandos/output/métricas/riesgos y revisión TASK-711 favorable.

## Cierre — 2026-11-11

TASK-710/711 completadas:65tests,8boots finales normales, revisión cruzada favorable en TASK-711-kernel.md y TASK-711-user.md. Evidencia persistida en agents/reports/TASK-710/ y TASK-711/. Alcance mínimo/singleCPU; límites ADR-012.
