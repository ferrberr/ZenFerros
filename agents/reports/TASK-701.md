# TASK-701 — Evidencia: VFS/RAMFS e init/shell mínimos (Hito 7)

Fecha de cierre: 2026-11-11. Todos los resultados de abajo se ejecutaron en este workspace tras reparar el estado roto dejado por la sesión anterior.

## Qué se implementó

| Componente | Archivo | Descripción |
|---|---|---|
| RAMFS + VFS | `ferros/kernel/vfs.zen` (nuevo, ~210 líneas) | Pool fijo 256×4 KiB; bitmap; 128 inodos de 64 B; `vfs_init`, `ramfs_alloc_block`, `ramfs_ensure_block`, `ramfs_lookup`, `vfs_open/read/write/close`, `vfs_self_test` |
| Syscalls | `ferros/kernel/userspace.zen` | dispatch 4/5/6/7 → `user_open/user_read/user_write_vfs/user_close`, con validación de buffers de usuario; `user_open` copia la ruta a un scratch del kernel |
| ABI | `ferros/kernel/arch/x86_64/abi.zen` | declaraciones `ferros_vfs_state`, `ferros_ramfs_pool`, `ferros_user_scratch` |
| Almacenamiento supervisor | `ferros/kernel/arch/x86_64/userspace.S` | BSS: estado VFS 4 KiB, pool RAMFS 1 MiB, scratch de rutas 512 B; getters vía `USER_ADDRESS_GETTER` (se eliminó el uso de `ADDRESS_GETTER`, no definido en ese fichero, y las definiciones duplicadas) |
| Secuencia del hito | `ferros/kernel/main.zen` | `vfs_init` antes de entrar en CPL3; `vfs_self_test` tras la suite de usuario; marcadores `FS: RAMFS OK`, `FS: VFS OPEN/READ/CLOSE OK`, `HITO 7 OK` |
| Init/shell verificado | `ferros/user/main.zen` | `case 0`: abre `hello.zen` (syscall 4), imprime `SHELL> ls` y el nombre, imprime `SHELL> cat hello.zen`, lee por VFS (syscall 5) y escribe el contenido (syscall 1), cierra (syscall 7). Códigos de fallo 15–21 |
| Configuración | `infrastructure/scripts/build_ferros.py` | `vfs.zen` añadido a las 9 unidades concatenadas; se restauró la lista de rutas con `/` que había quedado corrupta |
| Aceptación | `infrastructure/scripts/boot_ferros.py` | serie esperada con líneas de shell y FS; `writes` esperado 5; `HITO 7 OK` |
| Aislamiento | `ferros/kernel/userspace.zen`, `ferros/kernel/vfs.zen` | `user_buffer_writable` (PTE&7) para destinos de read; `vfs_write_user` (EACCES por modo); `vfs_close_all` en `user_space_clear`; sondas negativas en el programa de usuario (−14 read RO, −13 write CPL3, fd filtrado) |
| Pruebas | `ferros/tests/*.py`, `ferros/tests/fixtures/*` | mock host con `vfs_state`, `ramfs_pool`, `scratch`; negativos usan `HITO 7 OK`; nuevo `test_vfs.py` (fixtures `vfs_test_support.zen`, `vfs_test_api.zen`, `vfs_mock.c`) recorre init/open/read/close, EBADF, ENOENT, EISDIR, EACCES, EMFILE, reuse y ENOSPC en normal/release |

Reparaciones de regresión incluidas (el árbol no compilaba al retomar):
- `ferros/kernel/userspace.zen`: restaurado el guard de longitud en `user_elf_validate` (`image==0 || length<64 || length>131072 || ...`), eliminado el `extern "C"` local, eliminadas ramas de dispatch duplicadas.
- `infrastructure/scripts/build_ferros.py`: lista `units` corrupta.
- `zen/compiler/tests/freestanding_cli.rs`: `readelf` se ejecuta con `LC_ALL=C` para que las aserciones no dependan del idioma del host (fallo reproducible en este entorno).

## Comandos y salidas reales

### Compilador
```bash
CARGO_HOME="$PWD/.cargo" cargo build --offline --release --manifest-path zen/compiler/Cargo.toml
CARGO_HOME="$PWD/.cargo" cargo test  --offline          --manifest-path zen/compiler/Cargo.toml
```
```text
test result: ok. 27 passed; 0 failed   (unitarias lib)
test result: ok.  8 passed; 0 failed   (freestanding_cli)
test result: ok. 11 passed; 0 failed   (native_cli)
```

### Ferros (host + QEMU)
```bash
python3 -m unittest discover -s ferros/tests -v
```
```text
Ran 20 tests in 17.8s
OK
```

```bash
python3 infrastructure/scripts/boot_ferros.py --all --repeat 3
```
```text
debug boot 1: PASS (QEMU 33, 0.525s)
debug boot 2: PASS (QEMU 33, 0.526s)
debug boot 3: PASS (QEMU 33, 0.529s)
release boot 1: PASS (QEMU 33, 0.348s)
release boot 2: PASS (QEMU 33, 0.345s)
release boot 3: PASS (QEMU 33, 0.346s)
```

Serie release observada (idéntica salvo contadores de IRQ):

```text
FERROS KERNEL
Powered by Zen
MEMORY: PMM OK
MEMORY: VMM OK
MEMORY: HEAP OK
INTERRUPTS: BREAKPOINT OK
INTERRUPTS: PAGE FAULT OK
INTERRUPTS: TIMER OK
THREADS: CONTEXT OK
SCHEDULER: PREEMPTION OK
SCHEDULER: YIELD AND EXIT OK
SCHEDULER: STATS switches=45 preemptions=25 yields=16 completed=3
USER: Hello from Zen
SHELL> ls
hello.zen
SHELL> cat hello.zen
Hello
USERSPACE: RING3 AND SYSCALLS OK
USERSPACE: ISOLATION AND CLEANUP OK
USERSPACE: STATS runs=7 writes=5 rejected=6 irqs=1
FS: RAMFS OK
FS: VFS OPEN/READ/CLOSE OK
Boot successful
HITO 7 OK
```

Contadores userspace: debug `irqs=8`, release `irqs=1`; el runner exige `runs=7, writes=5, rejected>=6, irqs>=1`.

### Artefactos
| Artefacto | Debug | Release |
|---|---|---|
| payload ELF64 (`ferros-x86_64.elf`) | 151 928 B | 56 784 B |
| contenedor Multiboot ELF32 | 149 208 B | 55 184 B |
| ELF64 usuario | 24 344 B | 13 600 B |
| build del kernel | 0.330 s | 0.654 s |

Riesgo nuevo de memoria: el pool RAMFS añade 1 MiB de BSS supervisora; `ferros_kernel_end` la incluye y el PMM sigue reservándola (los 19 tests y los boots lo confirman).

## Revisión independiente y correcciones
Una revisión independiente rechazó la primera versión con tres vías reproducibles de panic desde CPL3 (read hacia texto RO, write sin permiso, fuga de fd), además de scratch dentro del pool, falta de tests VFS, contabilidad `free_blocks` y doc del bitmap. Todas se corrigieron y se añadieron pruebas:
- A1: `user_buffer_writable` (PTE&7==7) y sonda en usuario que exige −14 sin panic.
- A2: `vfs_write_user` con EACCES; el kernel conserva `vfs_write`; sonda en usuario que exige −13.
- A3: `vfs_close_all()` en `user_space_clear`; el usuario filtra un fd a propósito y el self-test reutiliza el 100.
- M1: scratch del self-test en la cola de la página de estado (2048/2560/3072), nunca en el pool.
- M3: `ferros/tests/test_vfs.py` con mocks host ejercita EBADF/ENOENT/EISDIR/EACCES/EMFILE/reuse/ENOSPC en normal y release.
- B1: `free_blocks=252`; B2: doc corregida (bitmap de 256 bytes, 1 byte/bloque); B3: bloque lleno devuelve −28.
- M2: el flujo imprime `SHELL> ls` antes del open; se documenta que no hay enumeración dinámica.
Segunda revisión independiente: **CON OBSERVACIONES** (sin panic en A1/A2/A3 y suites verdes), con dos defectos de estado/test que se corrigieron:
- Self-test no restauraba el fixture (quedaba tamaño 7, `HelloHi`): ahora toma instantánea temprana y restaura tamaño 5, contenido `Hello`, bitmap y `free_blocks=252`; el test host lo comprueba.
- La sonda de fuga del usuario era inerte (el buffer contenía la línea de shell): ahora re-etiqueta `hello.zen`, valida `100<=fd<=115` y deja el fd realmente abierto.
- Menores: `vfs_write(count=0)` devuelve 0 sin asignar bloque, comentario del bitmap corregido, política CPL3=«otros» documentada, cobertura host ampliada (self-test, ENOSPC sin bloques, contador de libres, `user_buffer_writable` vía dispatcher).

### Verificación por mutación (Lead)
Cada sonda del programa de usuario se comprobó eliminando la defensa correspondiente sobre copias en `/tmp`:

| Mutación | Resultado sin arreglo | Resultado con arreglo |
|---|---|---|
| `user_read` usa `user_buffer_valid` en vez de `user_buffer_writable` | `FERROS PANIC: unexpected interrupt or exception` (35) | PASS 33, read RO → −14 |
| syscall 6 llama a `vfs_write` en vez de `vfs_write_user` | `FERROS PANIC: userspace test failed` (35) | PASS 33, write CPL3 → −13 |
| `user_space_clear` sin `vfs_close_all()` | `FERROS PANIC: vfs test failed` (35) | PASS 33, fd reutiliza el 100 |

Re-revisión final independiente: **APROBADO** (sin hallazgos Alta/Media). Confirmó fixture prístino tras el self-test (tamaño 5, `Hello`, bloque 3, bitmap 0..3, `free_blocks=252` antes y después), las 16 ranuras fd a cero y las tres mutaciones A1/A2/A3 fallando con status 35. Observaciones menores atendidas: comentario del slot `open_count` eliminado, `vfs_write(count=0)` valida fd/tipo antes del atajo, el primer `open` del usuario acota `100..115`, y el test host comprueba los cinco bytes de `Hello`. Permanecen como limitaciones documentadas: `write` desde CPL3 solo se ejercita en rechazo (EACCES), `read` sin offset por descriptor, `open` ignora flags, `ls` sin enumeración dinámica y la ruta de éxito de `ramfs_alloc_block` no se ejercita (siempre bloque 3 o fallo).

## Revisión de integración
- Diff completo revisado por el Lead (único autor en esta sesión): compilación, suites y 6 boots reproducidos después de cada cambio.
- No se reimplementaron hitos 1–6: sus marcadores, contadores y pruebas negativas siguen vigentes, con el marcador final renombrado a `HITO 7 OK`.
- Los informes `TASK-701-filesystems.md`, `TASK-701-userspace.md` y `TASK-701-consolidated.md` de la sesión anterior quedaron **SUPERSEDED**: describían ficheros retirados (`vfs_ramfs.zen`, `init.zen`, `shell.zen`) y un estado no compilable.
