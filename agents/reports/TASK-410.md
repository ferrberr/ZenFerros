# TASK-410: Hito 3 completado — primer boot real de Ferros

**Fecha**: 2026-11-11
**Estado**: COMPLETADA / INTEGRADO
**Responsables**: 00 (kernel Zen, build/runner/tests/docs); boot_engineer (bootstrap, linker y IO asm); compiler_review (revisión independiente TASK-411).

## Evidencia de éxito

Cadena real: fuente kernel Zen → compilador Zen → C generado → GCC freestanding → código máquina x86_64 → kernel ELF64 → contenedor Multiboot ELF32 → QEMU TCG → long mode → kernel Zen → UART serie.

Se ejecutaron tres boots normales y tres optimizados. Los seis emitieron exactamente:

```text
FERROS KERNEL
Powered by Zen
Boot successful
```

Todos terminaron con estado33 del dispositivo isa-debug-exit y stderr vacío. La revisión independiente reconstruyó/arrancó ambos modos también. No es una ejecución del kernel como proceso Linux: QEMU lo carga como invitado y se ejecutan instrucciones privilegiadas en el guest. El modo de arranque es carga directa Multiboot1 con -kernel, sin imagen ISO/USB ni GRUB/UEFI.

## Cambios

- `ferros/kernel/main.zen`: kernel, validación de magic/info, UART COM1 (divisor/8N1/FIFO/modem), comprobación loopback, sondeo acotado por byte, recorrido de strings y mensajes. Fallos de UART/handoff/polling devuelven estado de fallo del test, sin afirmar éxito.
- `ferros/boot/entry.S`: header Multiboot1, BSS, GDT, tablas de identidad de primer1GiB, PAE/longmode64 y stack64KiB alineado para ABI SystemV. `linker.ld` fija 1MiB y segmentos ELF RX/R/RW; asserts de límites/alineación.
- `ferros/kernel/arch/x86_64/io.S`: cuatro primitivas mínimas in8/out8/out32/halt, única excepción de instrucciones privilegiadas junto al bootstrap. Código original; sin kernel C anfitrión.
- `build_ferros.py`: compila/enlaza, empaqueta ELF32 y comprueba header, checksum, LOAD, entry, ausencia de undefined y payload .text/.rodata idéntico en ELF64 y ELF32.
- `boot_ferros.py`: QEMU TCG/qemu64/1vCPU/64MiB, sin red/discos/GUI/monitor, captura serie/stderr, estado33 obligatorio, timeout y cancelación con grupo de procesos recolectado y logs persistentes.
- `setup_qemu.py` y manifest fijado: QEMU11.1.3 y dependencias (17 paquetes oficiales en total) extraídos localmente a .tools/qemu; URL/versiones/SHA256/licencias registrados. Sin cambios de paquetes del host ni requisito KVM. La copia usa bibliotecas/módulos/firmware dedicados solo al proceso QEMU.
- Ocho tests de driver Zen y fallos de runner; métrica reproducible de fuentes; ADR-009, guía de boot y documentación principal actualizados. El compilador no necesitó cambios en este hito.

## Comandos y resultados

```text
rtk proxy env CARGO_HOME=/home/ferranfg/proyectos/ZenFerros/.cargo cargo run --offline --manifest-path zen/compiler/Cargo.toml -- check ferros/kernel/main.zen --target x86_64-unknown-none
Checked ferros/kernel/main.zen

rtk proxy python3 infrastructure/scripts/build_ferros.py
Built .../ferros/build/debug/ferros-multiboot.elf

rtk proxy python3 infrastructure/scripts/boot_ferros.py --all --repeat 3
debug boot 1: PASS (QEMU 33, 0.056s)
debug boot 2: PASS (QEMU 33, 0.055s)
debug boot 3: PASS (QEMU 33, 0.051s)
release boot 1: PASS (QEMU 33, 0.052s)
release boot 2: PASS (QEMU 33, 0.053s)
release boot 3: PASS (QEMU 33, 0.052s)
[exact kernel message above]

rtk proxy python3 -m unittest discover -s ferros/tests -v
Ran 8 tests in 0.557s
OK

rtk proxy env CARGO_HOME=/home/ferranfg/proyectos/ZenFerros/.cargo cargo test --offline --manifest-path zen/compiler/Cargo.toml
27 unitarios passed; 0 failed (0.11s)
8 freestanding CLI passed; 0 failed (0.98s)
11 hosted CLI passed; 0 failed (0.24s)
0 doc tests; 0 failed
```

Hay 46 tests de compilador y 8 de boot/driver, todos pasan, más los seis boots reales. El compilador no cambió, por lo que se reejecutó regresión debug; release del compilador ya se verificó en Hito2. Las dos optimizaciones del kernel (-O0/-O2) se verificaron realmente en QEMU en este hito.

El test de driver ejecuta el objeto Zen enlazado con mocks C de IO, excluyendo expresamente asm privilegiado: verifica configuración UART, mensaje correcto, panic por magic/info, fallo loopback y exactamente un millón de sondeos cuando TX no está listo. Los tests de runner rechazan estado/salida/stderr/timeout, conservan logs de arranque fallido y prueban Ctrl+C con proceso hijo real. Revisión TASK-411 añade imagen inválida y timeout de QEMU real.

## Fallos encontrados y corrección

- QEMU no estaba instalado ni /dev/kvm disponible. Una consulta de red en sandbox falló por DNS; se solicitó/aprobó acceso y se descargaron paquetes oficiales a prefijo local. La URL de qemu11.1.2 del índice pacman antiguo devolvió404; el repositorio actual aportó11.1.3 y se fijó manifest con hashes. No se instaló nada en /usr ni /var.
- El primer intento manual emitió el mensaje completo pero agotó10s: -no-shutdown impedía la salida de isa-debug-exit en QEMU11. Se retiró esa opción, tras contrastar el dispositivo en fuente primaria de QEMU; el siguiente intento terminó33. La observación inicial está documentada aquí; los logs persistentes de la batería final y los fallos automatizados prueban el comportamiento corregido.
- P2 de revisión: Ctrl+C al runner podía dejar el invitado nuevo-session vivo y perder logs. Corregido con cleanup/reaping del grupo en finally y guardado de cancelación antes de propagar interrupción. Test permanente e investigación independiente confirman que el hijo desaparece y se conservan bytes parciales/result.json.

Sin bloqueantes pendientes tras revisión cruzada favorable TASK-411.

## Métricas observadas (tres boots por modo, no benchmark competitivo)

| Kernel | Payload ELF64 bytes | Imagen ELF32 bytes | Build s | Boot medio s | Rango boot s |
|--------|---------------------|--------------------|---------|--------------|--------------|
| debug | 12592 | 11640 | 0.069743 | 0.054147 | 0.050933–0.056263 |
| release | 9808 | 9416 | 0.070681 | 0.052050 | 0.051544–0.052821 |

Tiempo boot medido desde lanzamiento QEMU hasta salida; no es tiempo interno exclusivo del kernel. QEMU11.1.3, TCG pc/qemu64, 64MiB, 1vCPU; GCC16.2.1/binutils y host Linux x86_64 del entorno. Pico real de memoria host, energía, caché, latencias p95/p99 no medidos. No se afirma estabilidad de estrés ni superioridad de rendimiento.

## Porcentaje de Zen, sin ocultar bootstrap

Método de `measure_kernel_sources.py`: líneas no vacías tras excluir comentarios /* */ y // en las fuentes actuales. Archivos y resultados completos en TASK-410-source-metrics.json:

- Kernel Zen:70 líneas físicas,60 de código.
- Primitivas IO asm:44 físicas,35 de código.
- Bootstrap asm:126 físicas,98 de código.
- Linker:35 físicas,31 de configuración, separado del porcentaje.
- Zen dentro de kernel/ frente a primitivas:63.16% SLOC. Incluyendo el bootstrap asm:31.09%.
- C generado:249 líneas físicas, contado aparte; ninguna dependencia externa ni C escrito a mano enlazados al kernel. Herramientas de build, tests y paquetes QEMU no entran en el denominador.

La lógica principal de UART, mensajes, handoff y validación está en Zen; el número de líneas no sustituye esa comprobación. Las excepciones asm son inicialización de CPU/paging/stack y cuatro instrucciones de arquitectura expuestas por ABI.

## Artefactos, integración y límites

ELF/objetos compilados están en ferros/build/{debug,release}/ (ignorados por Git). Logs de seis boots, build.log/build.json copiados a agents/reports/TASK-410/{debug,release}/; resumen en TASK-410-boot-results.json. Licencias y procedencia de herramientas en infrastructure/toolchains/qemu-packages.json y .tools/qemu/usr/share/licenses/. Guía reproducible: docs/ferros/boot.md.

Bootstrap/IO implementados en Git temporal /tmp/zenferros-task410-boot, rama task410-boot, commit28989a0; integración secuencial en archivos exclusivos. .git del workspace sigue vacío/protegido; no se declara merge o commit local allí. Revisión crítica realizada por agente distinto de todos los autores.

Interrupciones deshabilitadas; sin IDT, PMM, heap, scheduler, procesos ni userspace. El mapa identidad temporal es supervisor RWX e incluye página0: permisos ELF no son protección de páginas. Hito4 deberá gestionar mapa físico, permisos virtuales, excepciones y timers. No se ha probado hardware físico, KVM, ISO/USB ni UEFI. El éxito tiene alcance mínimo QEMU documentado.

## Próximo hito

Hito4: memoria e interrupciones básicas, con contrato verificable del mapa de memoria Multiboot, capacidades Zen de layout mínimas que se requieran y tests específicos de PMM/VMM/IDT/excepciones.
