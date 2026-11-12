# TASK-411 — Revisión independiente del primer boot Ferros

**Revisor**: compiler_review (distinto de autores de bootstrap/kernel/scripts)
**Fecha**: 2026-11-11
**Estado**: COMPLETADA — revisión favorable del Hito 3 mínimo

## Alcance
Revisión de entry.S/linker.ld, helpers IO, kernel Zen, build/inspección de imagen, runner QEMU, instalación local y pruebas host-safe. Solo este informe fue modificado por el revisor. Las instrucciones privilegiadas únicamente se ejecutaron dentro de QEMU.

## Hallazgo reproducido
- **P2: Ctrl+C puede dejar QEMU huérfano**. `run_process` crea sesión propia del hijo y solo maneja timeout/OSError. Al enviar SIGINT al proceso Python del runner, termina con -2 pero el hijo en sesión separada sigue vivo, sin result.json ni logs parciales persistidos. Reproducción segura con proceso Python que duerme, nunca con asm privilegiado: `/tmp/zenferros-task411-review/interrupt`. El revisor terminó inmediatamente el grupo restante. Notificado al orquestador y **corregido**: cleanup con terminación/recolección del grupo en finally, SIGINT repetido ignorado durante cleanup, evidencia persistida y cancelación propagada. Reproducción independiente tras arreglo: wrapper termina por SIGINT, hijo ya no existe, cancelled=true/passed=false y serial parcial guardado. La CLI traduce Ctrl+C a estado 130.

## Evidencia independiente
1. Builds nuevos desde fuentes actuales, usando `build_kernel` y `boot` con salida en `/tmp/zenferros-task411-review/{debug,release}`. **Dos boots QEMU reales**:
   - Normal: imagen 11.640 bytes, estado QEMU **33**, tiempo observado 0,052197 s.
   - Optimizado: imagen 9.416 bytes, estado QEMU **33**, tiempo observado 0,052643 s.
   - Ambos: stderr vacío y bytes exactos `FERROS KERNEL\nPowered by Zen\nBoot successful\n`.
2. `rtk proxy python3 -m unittest discover -s ferros/tests -v`: **8 tests pasan, 0 fallos**, 0,558 s, tras incorporar la regresión de cancelación. Incluye UART compilado desde Zen con IO C simulado, handoff inválido, loopback fallido, polling acotado, salida/estado/stderr/timeout/start failure y logs.
3. QEMU real con imagen inválida: estado 1, passed=false, stderr guardado; QEMU real con timeout forzado 0,000001 s: estado -15, timed_out=true, passed=false, logs y JSON guardados. Artefactos en `/tmp/zenferros-task411-review/{invalid,forced-timeout}`.

4. Con runner final corregido, otros dos boots QEMU reales de las imágenes recién compiladas: **debug/release PASS, estado33**, cancelled=false, stderr vacío y mensaje exacto; tiempos observados 0,053310 s / 0,051665 s. Logs independientes en `/tmp/zenferros-task411-review/{debug,release}/boot-final`.
5. Se verificaron SHA256 de **17 archivos de paquetes** locales contra el manifiesto fijado `infrastructure/toolchains/qemu-packages.json`: todos coinciden. Setup local revisado: usa esas versiones/hashes, verifica antes de extraer y recurre al archivo oficial si el mirror devuelve 404. No se descargó ni instaló nada adicional durante esta revisión.

## Observaciones críticas confirmadas
- Header Multiboot v1 alineado/checksum, payload ELF64 y contenedor ELF32. Build valida entrada/PT_LOAD/rango y comprueba que text/rodata no cambian tras objcopy, además de símbolos sin resolver.
- Bootstrap preserva magic/info, carga GDT propia antes de selectores, limpia BSS sin usar la pila, construye PML4/PDPT/512 páginas de 2 MiB, activa PAE/long mode y salta a CS de 64 bits. RSP está alineada a 16 antes de call; argumentos cero-extendidos usan registros System V AMD64.
- Mapping inicial identidad [0,1 GiB) deliberadamente RWX y con página cero; no representa todavía un VMM protegido. Interrupciones siguen desactivadas y no hay IDT.
- Helpers IO solo implementan primitivas in/out/halt. UART, validación y mensajes están en Zen. Código de éxito 0x10 produce status33 del dispositivo de test, distinto de 0 del host; el runner exige ese estado y stdout exacto.
- VM TCG qemu64: 64 MiB, un CPU, sin discos/red/display/monitor, timeout y proceso aparte. No se usó KVM ni hardware real.
- Procedencia local QEMU registrada con URL oficial Arch, versiones, SHA256 y licencias en .tools/qemu/provenance.json. Setup extrae herramientas en prefijo local y no ejecuta instaladores de paquetes en el anfitrión.

## Dictamen
**Favorable para cerrar TASK-410 y Hito 3 mínimo**. El único hallazgo P2 reproducido se corrigió y verificó independientemente; no quedan bloqueantes de esta revisión. El kernel compilado desde Zen y ambos boots QEMU han sido observados directamente, con validación exacta de salida y estado.

El resultado no demuestra PMM/VMM protegido, IDT/interrupciones, scheduler, usuarios ni hardware físico. Las mediciones de ~0,05 s son observaciones de este boot y entorno, sin comparación competitiva de rendimiento.

## Revisión final de documentación del Hito 3
Se leyeron docs/ferros/boot.md y ADR-009 tras su publicación: los contratos de Multiboot/ELF, estado33, TCG, kernel Zen, límites de RWX inicial y ausencia de PMM/IDT/boot físico coinciden con la implementación y las observaciones de esta revisión. Se ejecutó measure_kernel_sources.py: 60 líneas Zen / 35 asm de primitivas / 98 asm bootstrap; 63,16% Zen sin bootstrap y 31,09% incluyéndolo; 249 líneas físicas C generado separadas. Es una métrica textual documentada del estado del Hito3, sin equipararla a proporción de funcionalidad.
