# TASK-511 — Revisión independiente Hito 4

**Revisor**: compiler_review, distinto de autores de memoria/arquitectura/integración
**Fecha**: 2026-11-11
**Estado**: COMPLETADA — revisión favorable del Hito 4 mínimo

## Alcance y propiedad
Se revisaron memory.zen, interrupts.zen, main/runtime/ABI, entry.S/linker.ld/io.S/interrupts.S y scripts de concatenación/build/boot, más fixtures de memoria/interrupciones. Solo este informe fue modificado para TASK-511. Los algoritmos Zen se probaron en host con mocks; las instrucciones privilegiadas se ejecutaron exclusivamente en QEMU.

## Corrección de integración verificada
La primera integración falló PMM porque la política original exigía cadenas del cargador debajo de 1 MiB. El orquestador observó en QEMU info0x9500/map0x9000 pero cmdline0x157000 y loader0x157050, después del BSS. El autor corrigió el contrato: info/map permanecen bajo1MiB; cadenas acotadas a4096bytes y64MiB, con NUL incluido; se reserva todo hasta el máximo de kernel/metadata/cadenas, redondeado a página, antes de marcar páginas disponibles. El revisor verificó fuente y regresión nueva con cadenas a32MiB/32MiB+0x2050, fuera del kernel simulado de16MiB: primera asignación32MiB+0x3000; liberar páginas de cadenas/hueco se rechaza. La cadena sin NUL al límite64MiB también se rechaza. Native O0/O2: estado0, stderr vacío. La aceptación final usa esa corrección; no se ocultó el fallo inicial.

## Revisión crítica
- **PMM**: registros Multiboot variables con payload>=20, stride dentro del buffer, suma base+length sin overflow y cap256registros. Decodificación byte a byte admite campos no alineados. Dos pasadas hacen que regiones reservadas prevalezcan ante solapes, independientemente de orden. Disponibles se redondean hacia dentro; reservas hacia fuera. Bitmap libre y bitmap gestionado distinguen reservado/no gestionado de asignado; free rechaza desalineación, rango, reserva y double-free. Autoensayo agota/restaura bitmap y contador. Metadata soportada queda reservada; flags no soportados y módulos no vacíos se rechazan.
- **VMM**: raíces PML4/PDPT/PD y32tablas hoja cubren64MiB con páginas4KiB. Página0 no presente; textoRX, rodataR+NX y data/stack/heapRW+NX; supervisor. NXE se comprueba/activa por CPUID+EFER, CR0.WP se verifica y CR3 se carga realmente. Límites text/rodata alineados a páginas y GDT con bits accessed preactivados permiten proteger rodata sin faltas del propio CPU. El layout reservado del linker mantiene tablas/estado/heap dentro del kernel excluido del PMM.
- **Heap**: arena64KiB, asignaciones con tamaño>0, alineación potencia de dos no nula, redondeo y suma comprobados antes de avanzar cursor. Se comprueban no solape y agotamiento exacto. No hay free general ni concurrencia.
- **ISR/IDT**: gate16bytes/vector, selector8 y tipo0x8E; 256descriptores. Stubs normalizan vector/error y salvan15GPR. Offsets vector+120/error+128/RIPframe+136 correctos; RBX conserva la base mientras RSP se alinea a16 para llamada SysV, restaura exactamente y retorna por iretq. cld no altera RFLAGS recuperado. No se afirma soporte user/IST/SIMD. Vectores48..255 comparten stub genérico255.
- **Recuperación**: PF requiere kind esperado de un solo uso, RIP de sonda exacto, CR2 y error0(null)/3(ROwrite); se modifica solo RIP al sitio de reanudación. Frame se comprueba por alineación y rango del kernel, bajo contrato de frame hardware confiable; esto no prueba validación de frames arbitrarios de usuario. Breakpoint solo se acepta armado; otros casos son fatales.
- **PIC/PIT**: remapeo32..47 con IF deshabilitado, todas IRQ inicialmente enmascaradas. Se programa PIT divisor11932, se arma el contador y solo se desenmascaraIRQ0. Handler incrementa porIRQ32 y manda EOI al master. sti/hlt/cli evita ventana de espera perdida y retorna con IF0. Se exigen al menos3ticks y después se vuelve a enmascarar.
- **Integración**: build concatena unidades explícitas en un archivo de entrada antes de invocar el compilador; no se presenta como soporte de módulos/globals/structs del lenguaje. Estado está en buffers de BSS reservados por arquitectura.

## Evidencia independiente ejecutada
1. Compilación desde la entrega final memory4d8aab0 con ABI+wrappers de test, objeto Zen freestanding y harness C sin instrucciones privilegiadas. Native normal/optimizado: **estado0, stderr vacío**, confirmación de mapas válidos/inválidos, reservas/solapes/exhaustión, heap y VMM. Artefactos `/tmp/zenferros-task511-review/memory-fixed`.
2. Builds nuevos de todas las fuentes integradas con `build_kernel`, salida `/tmp/zenferros-task511-review/qemu/{debug,release}`. **QEMU real TCG**:
   - Normal: imagen56.364bytes, **estado33**, 0,121759s observado.
   - Optimizado: imagen25.036bytes, **estado33**, 0,080409s observado.
   - Ambos: stderr vacío y salida exacta:

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

3. Builds independientes de `ferros/tests/unexpected_exception.zen`, ambos modos, con int3 real sin armar. QEMU termina **estado35**, guarda `FERROS PANIC: unexpected interrupt or exception`, no emite HITO4OK; el validador rechaza ambas ejecuciones. Logs bajo `{debug,release}/unexpected/boot` del directorio anterior.
4. `rtk proxy python3 -m unittest discover -s ferros/tests -v`: **11 tests pasan, 0 fallos**, 1,649s. Incluye memoria native+UBSan O0/O2, IDT/PF/PIC/PIT con mocks, negativos fatales en QEMU, UART y regresión de timeout/cancelación/logs del runner.

El código inspeccionado confirma que las sondas son instrucciones de acceso real a null/rodata después de cargar CR3, los contadores PF solo avanzan en el dispatcher, y los ticks solo avanzan desdeIRQ32. Los mocks se usan en pruebas host separadas; no sustituyen esos caminos durante los boots QEMU.

## Dictamen y límites
**Favorable para cerrar TASK-510 y Hito 4 mínimo.** La corrección de integración fue verificada y no quedan hallazgos bloqueantes de esta revisión. La evidencia prueba el subconjunto descrito en un CPU QEMU, con memoria limitada y layout fijo.

No demuestra PMM para todo firmware/Multiboot posible, grandes espacios virtuales, protección contra frames arbitrarios, stacks de excepción IST, usuarios, scheduler, SMP, allocator concurrente o estabilidad de estrés. El mapa identidad inicial de1GiB continúa durante el bootstrap antes de reemplazarse; el mapa definitivo de esta fase se limita a64MiB. El estado de fuentes anterior de Hito3 es histórico. Las duraciones son observaciones del entorno, no benchmarks competitivos.

## Revisión final de documentación y lote de evidencia
Se leyeron docs/ferros/memory-interrupts.md, ADR-010, README, ARCHITECTURE y ROADMAP: describen el subconjunto probado, el límite64MiB y contrato Multiboot, arena sin free, frame/ISR ring0 sin IST/SIMD, default255, IF/PIC/PIT y concatenación explícita. No atribuyen soporte de módulos/globals, prueba de ejecuciónNX adicional, SMP/usuarios o estabilidad no demostrada.

Se inspeccionaron los logs/JSON persistentes del lote final del orquestador: seis éxitos64MiB (tres por perfil), dos éxitos32/128MiB del mismo ELF optimizado y dos excepciones inesperadas35. Los ocho éxitos contienen salida exacta, stderr vacío y estado33; ambos negativos contienen panic sin HITO4OK. Son diez ejecuciones con resultados esperados, incluyendo dos rechazos deliberados. La reproducción independiente de esta revisión sigue siendo la descrita arriba (dos éxitos y dos negativos propios).

La nueva opción CLI memory-mib se limita a enteros16..256 y conserva64por defecto; se revisó que solo cambia -m del emulador. measure_kernel_sources.py reproduce58,19%Zen sinbootstrap y52,13%incluyéndolo, con C generado separado (2752líneas físicas); método textual documentado, sin equiparar SLOC a funcionalidad. Dictamen favorable mantenido, sin bloqueantes pendientes.
