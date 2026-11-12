# Primer arranque Ferros — Hito 3

El runner actual incluye Hito5; véase `multitasking.md` para mensajes y criterios vigentes.

Este documento registra el primer boot. El runner actual incluye las pruebas del Hito4 y exige mensajes adicionales; véase `memory-interrupts.md` para estado vigente.

## Resultado

Ferros arranca realmente en una VM QEMU x86_64 y ejecuta un kernel compilado desde `ferros/kernel/main.zen`. Inicializa COM1, comprueba loopback, escribe el mensaje y termina la prueba con un puerto QEMU de depuración:

```text
FERROS KERNEL
Powered by Zen
Boot successful
```

La aceptación requiere también estado33 y stderr vacío. El mensaje por sí solo no da por aprobado el test.

## Reproducir

Desde la raíz del proyecto, se requiere Rust/Cargo, GCC, binutils, Python3 y QEMU system-x86_64. El entorno actual tiene QEMU11.1.3 local; no se necesita KVM ni privilegios de administrador.

```bash
rtk proxy env CARGO_HOME="$PWD/.cargo" cargo build --release --offline --manifest-path zen/compiler/Cargo.toml
# Solo si no existe un QEMU del sistema o la copia local (requiere red):
rtk proxy python3 infrastructure/scripts/setup_qemu.py
# Compilar y arrancar normal y optimizado, tres veces cada uno:
rtk proxy python3 infrastructure/scripts/boot_ferros.py --all --repeat 3
# Pruebas del driver Zen con IO simulado y fallos del runner:
rtk proxy python3 -m unittest discover -s ferros/tests -v
```

`boot_ferros.py` sin argumentos prueba el kernel normal una vez. `--release` selecciona optimizado; `--timeout N`, `--repeat N`, `--qemu /ruta/qemu-system-x86_64` y `--zen /ruta/zen` permiten ajustar el entorno. QEMU se elige por --qemu, variable QEMU, copia local y finalmente PATH. La copia local recibe rutas dedicadas de bibliotecas, módulos y firmware, sin alterar el entorno del resto de herramientas.

`build_ferros.py [--release]` solo compila. No ejecutar el ELF del kernel directamente en el host: contiene instrucciones privilegiadas; el script de boot lo carga únicamente en la VM. Las pruebas host enlazan únicamente el objeto Zen con funciones C simuladas, sin el asm de IO.

## Artefactos y logs

`ferros/build/debug/` y `ferros/build/release/` contienen kernel.o, entry.o, io.o, ferros-x86_64.elf, ferros-multiboot.elf, build.json y build.log. Cada boot guarda serial.log, qemu.stderr.log y result.json bajo boot-01, boot-02, etc. `ferros/build/boot-results.json` agrupa estados, comandos, versión QEMU y tiempos. Los fallos y la cancelación también guardan logs y no dejan la VM ejecutándose; Ctrl+C termina el grupo y el CLI retorna130.

Los ELF se inspeccionan antes del arranque: header Multiboot alineado en primeros8KiB, checksum, tipo/máquina/clase, LOAD dentro de identidad, sin segmentos ELF RWX, entry en segmento ejecutable, sin undefined, y payload de código/datos de solo lectura idéntico tras conversión.

## Cadena de arranque

Zen → frontend comprobado → C generado → GCC freestanding → kernel.o x86_64. El objeto se enlaza con entry.S e io.S originales y linker.ld. El ELF64 es payload64; objcopy lo encapsula en ELF32 para el loader Multiboot1 directo de QEMU (`-kernel`). No es una imagen de disco/ISO ni un sistema Linux. La única dependencia del host durante ejecución es el emulador.

La entrada Multiboot32 establece BSS, GDT, PML4/PDPT/PD y mapeo identidad de primer1GiB, activa long mode y llama a kernel_entry con magic/info y stack64KiB alineado. Toda política serie, validación del handoff y mensajes está en Zen; instrucciones de CPU/puertos son helpers asm. Las cantidades de fuente se reproducen con `measure_kernel_sources.py`, separando bootstrap, primitivas, Zen, linker y C generado. Incluyendo bootstrap no se afirma que la mayoría de líneas sea Zen; la lógica del kernel/driver está implementada en Zen.

## Aislamiento, fallos y límites

QEMU usa TCG, pc/qemu64, 1 vCPU, 64MiB, sin NIC, discos físicos, monitor ni GUI. El timeout por defecto es10s. Isa-debug-exit devuelve33 para éxito y35 para fallo; cualquier otro estado, salida alterada, stderr o timeout se rechaza. En QEMU11 no usar -no-shutdown con este test porque impediría la terminación normal del dispositivo.

UART usa sondeo acotado a un millón de lecturas por byte. Fallo de loopback, UART bloqueada o handoff inválido nunca emiten éxito. Las pruebas simuladas cubren esos caminos. Todavía no hay heap/PMM/VMM protegido/IDT/scheduler/procesos/usuarios/FS. Interrupciones siguen deshabilitadas y el mapa bootstrap es RWX e incluye página0, aunque el contenedor ELF tenga segmentos RX/R/RW. La siguiente fase debe gestionar memoria y excepciones. El éxito aquí no demuestra estabilidad de estrés ni funcionamiento en hardware físico.

## Dependencias y procedencia

QEMU/firmware y bibliotecas se descargan de paquetes oficiales Arch, con versiones y SHA256 fijados en `infrastructure/toolchains/qemu-packages.json`, caché y extracción bajo `.tools/qemu`, sin instalación de sistema. El instalador puede recurrir al archivo oficial si el mirror ya no tiene la versión fijada. Las licencias completas de paquetes se conservan en `.tools/qemu/usr/share/licenses/`; no hay dependencia externa enlazada al kernel. Protocolo y alternativas: ADR-009.
