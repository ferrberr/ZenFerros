# Memoria e interrupciones básicas — Hito 4

El runner actual incluye Hito5; véase `multitasking.md` para mensajes y criterios vigentes.

## Reproducir y aceptar

```bash
rtk proxy python3 infrastructure/scripts/boot_ferros.py --all --repeat 3
rtk proxy python3 -m unittest discover -s ferros/tests -v
```

El runner exige estado33, stderr vacío y salida completa exacta:

```text
FERROS KERNEL
Powered by Zen
MEMORY: PMM OK
MEMORY: VMM OK
MEMORY: HEAP OK
INTERRUPTS: BREAKPOINT OK
INTERRUPTS: PAGE FAULT OK
INTERRUPTS: TIMER OK
Boot successful
HITO 4 OK
```

Se verificaron kernels -O0 y -O2, tres veces cada uno con64MiB. También se arrancó el mismo kernel optimizado con32MiB y128MiB; el PMM usa el mapa recibido y limita su gestión a64MiB. `--memory-mib` admite16..256MiB. Es un perfil QEMU de una CPU, sin KVM/red/discos. Logs/builds permanecen en ferros/build/ y evidencia copiada al informe TASK-510.

## Unidades de fuente

ABI asm en arch/x86_64/abi.zen, driver COM1 en drivers/serial.zen, memory.zen, interrupts.zen, runtime.zen y main.zen. El build concatena una lista explícita en `ferros/build/{debug,release}/kernel.zen` y compila ese archivo. Los comentarios conservan el nombre de cada fuente; un diagnóstico del compilador se refiere al archivo combinado. No hay soporte de módulos/imports del lenguaje ni globals/structs implementados por este mecanismo.

Los datos mutables viven en buffers BSS reservados por linker y accedidos mediante funciones de dirección/offsets documentados. Esto permite probar algoritmos Zen hoy; se migrará a tipos y módulos cuando el compilador los soporte realmente.

## PMM

Páginas de4KiB, mapa Multiboot1 variable con hasta256registros, tipos disponibles y reservas. Dos pasadas hacen que una reserva gane sobre una región disponible independientemente del orden. Páginas disponibles se redondean hacia dentro; reservas parciales excluyen toda página solapada. Campos potencialmente no alineados se leen por bytes, sin cargas u64 desalineadas.

Se reserva memoria baja, imagen completa del kernel y todo el intervalo hasta el mayor extremo de los metadatos admitidos (incluidas cadenas de commandline/loader). Info y mapa deben estar bajo1MiB; cadenas pueden estar dentro de primeros64MiB y requieren NUL en un máximo de4096bytes. QEMU las coloca después del kernel, de ahí la reserva explícita. Flags admitidos0x24f, sin módulos cargados; flags/payloads adicionales se rechazan. Direcciones y tamaños se comprueban antes de usarlos según este contrato de boot.

Bitmap libre y bitmap gestionado permiten alloc, free, rechazo de doublefree, páginas reservadas, fuera de rango y direcciones sin alinear. 0 significa fallo. Selftest reserva dos páginas distintas, escribe/lee patrones, libera, prueba agotamiento y restaura estado. Las páginas asignadas no se garantizan borradas. No hay concurrencia, locks, DMAallocator o NUMA; las operaciones se ejecutan con IF deshabilitado y el IRQ no asigna memoria.

## VMM y heap

El mapa temporal bootstrap cubría1GiB con páginas2MiB/RWX. Ahora Zen construye tablas nuevas con páginas4KiB para primer64MiB: página0 ausente, textoRX, rodataR+NX, datos/stack/arenaRW+NX, supervisor. NXE se habilita y CR0.WP se exige; CR3 se cambia al árbol construido. Los límites de texto/rodata son páginas enteras del linker, e incluyen código de Zen, IO y stubs. GDT lleva bits accessed ya puestos antes de hacer rodata de solo lectura.

Se inspeccionan entradas y CR3 activo y se provocan dos fallos reales: lectura de página0 y escritura de byte en rodata. El dispatcher valida RIP exacto del probe, CR2, error esperado y estado one-shot antes de ajustar RIP al retorno del probe. Un PF ajeno al test es fatal. Los bits NX se comprueban con NXE habilitado; no se afirma una prueba adicional de ejecución desde páginaNX.

La arena64KiB ofrece bump allocation con alineación potencia de dos, overflow/límites/tamaño comprobados. Prueba alineación, escrituras, agotamiento exacto y restauración. No hay free individual ni coalescing. Tablas y arena se reservan en BSS, no se obtienen de un allocator dinámico. No hay high-half, espacios por proceso, mapeo arbitrario ni guardpage de stack. Los64MiB del mapa virtual no equivalen a afirmar que toda dirección corresponde a RAM utilizable; el PMM decide qué páginas son disponibles por E820.

## Excepciones, IDT y temporizador

Zen construye256gates IDT de16bytes (selector8, interruptgate0x8e). Asm normaliza vector/error, salva15GPR, limpia DF, alinea stack16 antes de llamar a interrupt_dispatch y retorna con iretq. Vectores0..47 tienen stubs propios;48..255 se agrupan como vector255 fatal. No hay usuarios/swapgs, stacks IST, soporte general de stackoverflow/doublefault ni estadoSIMD. Las excepciones ya pueden reportar panic si hay stack/memoria válidos; no se promete recuperación de toda corrupción de kernel.

Int3 tiene prueba esperada one-shot. PIC se remapea a32/40 y enmascara todosIRQ exceptoIRQ0 durante la prueba. PITcanal0, modo3, divisor11932 da frecuencia nominal~100Hz. Cada IRQ0 incrementa contador volatile y envía EOI al master; se esperan al menos3ticks reales mediante sti/hlt/cli y después se enmascara de nuevo. Sin calibración, prioridades, APIC/SMP ni scheduler. Si falla IRQ0, el timeout externo debe rechazar el boot, no generar éxito.

## Pruebas negativas y mocks

Los11tests de Ferros incluyen UART y runner anteriores, política IDT/PIC/PIT simulada, PMM/heap/VMM contra mapas sintéticos y builds UBSan -O0/-O2, y un boot real de int3 no armado. Este último debe salir35 y mostrar `FERROS PANIC: unexpected interrupt or exception`, nunca HITO4OK. Los mocks C implementan solo el entorno de prueba; jamás se enlazan al kernel real ni ejecutan instrucciones privilegiadas en el host.

Los casos de memoria cubren E820extendido/desalineado, prioridades invertidas, páginas parciales, tamaños truncados/overflow, strings altas/reservas, flags/módulos no admitidos, agotamiento/doublefree, heap e inspección de permisos. Los tests host de interrupción verifican gate64bits, EOI/divisor, recuperaciónone-shot y rechazo de CR2/frame/interrupts no esperados. El éxito del temporizador y los probes de protección se demuestra además en QEMU, no mediante los mocks.

## Siguiente etapa

Multitarea y scheduler (Hito5) necesitarán contexto de threads, stacks con guard, política de memoria/IRQ y probablemente tipos/módulos del lenguaje para sustituir offsets manuales. Este hito entrega subsistemas básicos integrados; no declara estabilidad de estrés ni seguridad de memoria de raw pointers. Véase ADR-010 y revisión TASK-511.
