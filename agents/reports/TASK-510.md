# TASK-510: Hito4 completado — memoria e interrupciones básicas

**Fecha**: 2026-11-11
**Estado**: COMPLETADA / INTEGRADO MÍNIMO
**Responsables**: 00(integración/main/IDT-PIC-PIT/tests/docs), memory_engineer(PMM/VMM/heap Zen), boot_engineer(asm y linker), compiler_review(revisión TASK-511).

## Resultado real

Kernel Zen arranca en QEMU, consume mapa Multiboot real, asigna/libera páginas, instala tablas4KiB con permisos/NX/nullguard, usa arena heap, maneja breakpoint y PF esperados y recibe3ticks reales del PIT. Salida exacta y estado33 requeridos:

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

Batería final:6boots64MiB (3normales/3optimizados),2boots adicionales del mismo kernel optimizado con32/128MiB,2boots negativos conint3 no armado (normal/optimizado), estos últimos deben mostrar panic y estado35 y nunca HITO4OK. Las10ejecuciones cumplieron su resultado esperado. Logs brutos negativos mantienen passed=false para el contrato de éxito; el resumen extra registra que el rechazo era el resultado exigido, sin modificar esos logs.

## Cambios implementados

- PMMbitmap desde mapa variable Multiboot1 real, máximo256registros/64MiB. Lecturas por bytes para campos desalineados; validación de strides/longitudes/overflow y dos pasadas con prioridad de reservas. Dos bitmaps permiten alloc/free/doublefree y exclusión de páginas no gestionadas. Reserva low1MiB/kernel y hasta extremo mayor de metadata/strings admitidas.
- VMM construye35páginas de tablas dentro de buffer36páginas: identidad4KiB del primer64MiB, página0 no presente, textoRX, rodataR+NX, datos/heap/stackRW+NX, supervisor. NXE/WP/CR3 comprobados. Límites de secciones alineados y GDT accessed ya puesto para rodata protegida.
- Heapbump en arena64KiB con alineación potencia2, overflow, tamaños y agotamiento comprobados; sin free individual.
- IDT256gates, política de dispatch en Zen. Asm solo normaliza marco/error, salva15GPR, alinea llamadaABI y restaura/iretq. Int3 y PFnull/RO reales con recuperación one-shot validando sitioRIP+CR2+error exactos. Excepción ajena es fatal.
- PIC remapeado32/40, IRQ0 solamente, PITdivisor11932 nominal100Hz, contadorvolatile/EOI/espera sti-hlt-cli hasta3ticks; al terminar se vuelve a enmascarar y queda IFoff.
- Código dividido en ABI/UART/memory/interrupts/runtime/main. Build concatena lista explícita a build/kernel.zen. No se añadió ni simuló sintaxis de módulos/globals/structs del lenguaje. No se modificó el compilador.
- Pruebas host-safe de memory/IRQs y boot real negativo, mocks C solo de test; opción RAM del runner16..256MiB. Documentación/ADR010 y roadmap actualizados.

## Pruebas y comandos

```text
rtk proxy python3 infrastructure/scripts/boot_ferros.py --all --repeat 3
debug boot1 PASS33 .123s
debug boot2 PASS33 .133s
debug boot3 PASS33 .119s
release boot1 PASS33 .076s
release boot2 PASS33 .083s
release boot3 PASS33 .080s
[exact H4message above]

rtk proxy python3 -m unittest discover -s ferros/tests -v
Ran 11 tests in 1.669s
OK

rtk proxy env CARGO_HOME=/home/ferranfg/proyectos/ZenFerros/.cargo cargo test --offline --manifest-path zen/compiler/Cargo.toml
27 unitarios passed; 0 failed (0.11s)
8 freestanding CLI passed; 0 failed (0.95s)
11 hosted CLI passed; 0 failed (0.25s)
0 doc tests; 0 failed
```

Son57tests permanentes (46compilador+11Ferros), todos pasan. Tests de memoria compilan/ejecutan el código Zen real con mocks de CPU, enO0/O2 y ambos de nuevo con UBSan sin stderr; mapas sintéticos cubren registros extendidos/desalineados, reservas solapadas/reordenadas, páginas parciales, overflow/truncación, flags/módulos rechazados, strings altas/reserva, agotamiento/free/doublefree y heap/VMM. Los mocks no ejecutan CR3/IO privilegiados en host. Tests de IRQ verifican codificación gate64, divisor/EOI, contadores y fatal/recovery con CR2/frame no admitidos. El negativeboot real prueba que el IDT entra al dispatcher y una excepción no armada no regresa como éxito.

El compilador no cambió; se reejecutó regresión debug, sin repetir release ya verificado en Hito2. El kernel se compiló y ejecutó realmente en ambos niveles y con varias RAM en este hito. Revisión independiente repitió boots y tests, con dictamen favorable TASK-511.

## Fallo encontrado y corrección

La primera integración acabó con panicPMM/estado35. El harness inicial suponía strings de loader bajo1MiB, pero QEMU las sitúa tras el kernel. Diagnóstico real: info9500,flags24f,mmap9000/longituda8,commandline157000,loader157050 (hex). Se permitió string dentro del perfil64MiB/max4096bytes con NUL/límites y se reservó conservadoramente hasta todos los extremos antes de ofrecer RAM al PMM. Nueva prueba coloca strings por encima de kernel_end y verifica que sus páginas y huecos no se asignan. Native/UBSan y revisión confirman el arreglo; QEMU ya pasa. Los logs de diagnóstico fallido se conservan en TASK-510/debug-pmm/.

No quedan bloqueantes de revisión. No se ocultó el fallo ni se relajaron los marcadores/estado de aceptación para pasarlo.

## Métricas observadas

| Kernel | ELF64 bytes | ELF32 bytes | Build s | Boot medio s | Rango s |
|--------|-------------|-------------|---------|--------------|---------|
| debug | 58352 | 56364 | 0.135725 | 0.125223 | 0.119369–0.133324 |
| release | 26280 | 25036 | 0.232046 | 0.079711 | 0.075962–0.083168 |

Boot es tiempo desde lanzamiento QEMU hasta salida, no latencia exclusiva de kernel. QEMU11.1.3/TCG/qemu64/1CPU; GCC16.2.1 y entorno Linuxx86_64. Tres muestras por modo64MiB, sin afirmación estadística/competitiva. RAMguest configurada no equivale a medir picoRSS del host. Energía/cache/p95/p99/asignaciones de host no medidos.

SLOC textual reproducible: Zen490 líneas de código frente352asm de primitivas/ISR =>58.19% en kernel; incluyendo98SLOCbootstrap =>52.13%. CódigoC generado2752líneas físicas separado; linker43SLOCconfig separado. No dependencias externas enlazadas al kernel. JSON completo TASK-510-source-metrics.json. Los porcentajes no expresan seguridad o rendimiento.

Cambios de fuente física (incluye tests/comentarios/blancos, excluye docs/logs/JSON/generated): 1189 añadidas, 88 eliminadas, neto 1101. Método y archivos en TASK-510-code-changes.json contra snapshot previo.

## Artefactos, integración y límites

Logs/builds/JSON de6boots y RAMextra/negativos/diagnóstico preservados en agents/reports/TASK-510/; resúmenes TASK-510-boot-results.json y TASK-510-extra-results.json. Binarios/generated ignorados en ferros/build/. Guía actual docs/ferros/memory-interrupts.md, diseño ADR010, revisión TASK511.

Memory aislado rama task510-memory commit4d8aab0, arch rama task510-arch commit8393f37; root integra archivos de propiedad exclusiva secuencialmente. Snapshot anterior /tmp/zenferros-task510-baseline. .git workspace sigue vacío/protegido; no se simulan merges allí. Revisión por agente diferente de todos los autores.

Perfil singleCPU, PMM/heap conIFoff y ningún allocation en handlers.64MiBgestionados, metadata info/map bajo1MiB, flags24f y sin módulos. Arena sinfree general, páginas no necesariamente borradas, tablas identidad fija sin addressspaces/map-unmap arbitrario. Sin userspace/scheduler/SMP/IST/guardstack/SIMD ni recuperación robusta de doublefault. Vectores48..255 se agrupan en default255 fatal. Se inspecciona NXE/entradas pero no se afirma probe de ejecuciónNX adicional. Rawpointers siguen responsabilidad del kernel. El resultado es mínimo integrado, no estable por estrés.

## Siguiente hito

Hito5: threads/contextswitch/scheduler con contratos claros de stacks/memoria/IRQ y pruebas verificables de múltiples tareas. Ampliar tipos/módulos de Zen cuando lo exija un consumidor real.
