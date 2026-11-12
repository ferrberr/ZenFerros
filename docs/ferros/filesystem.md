# RAMFS, VFS y ZENFS02 — TASK-919 / TASK-924 / TASK-928

Ferros combina RAMFS con archivos persistentes de hasta 512 B. ZENFS02 conserva los discos ZENFS01 mediante migración automática y permite crear o reemplazar desde CPL3 con `put`. Cada archivo ocupa un sector; hay ocho entradas y un sector libre para el commit copy-on-write. `boot.txt` queda reservado al kernel. La garantía de recuperación se limita a los fallos y sectores rasgados simulados; véase [persistencia](persistence.md).

## RAMFS

- Pool supervisor de 1 MiB en BSS (`__ferros_ramfs_storage`), 256 bloques de 4 KiB.
- Bloque 0: bitmap de bloques, un byte por bloque (256 bytes usados; el resto del bloque queda sin usar).
- Bloques 1–2: tabla de 128 inodos de 64 bytes.
- Bloque 3: directorio raíz con 128 entradas de 32 B (`name[24]` NUL-padded + `u64 inode_index` en +24; nombre vacío termina).
- Bloques 4–5: datos de `hello.zen` y `notes.txt`; bloques 6–255 libres. `free_blocks=250` tras init.
- Inodo: `+0` tipo (0 libre, 1 archivo, 2 directorio), `+8` permisos, `+16` tamaño, `+24` bloque de datos.
- Estado VFS en BSS (`__ferros_vfs_state_storage`, 4 KiB): inicializado, total/libres, raíz, bitmap, inodos y tabla de descriptores (16 ranuras desde `+1032`).
- Fixtures: `hello.zen` (inodo 1, bloque 4) = `Hello`; `notes.txt` (inodo 2, bloque 5) = `Zen\n`. Ambos 0644. El directorio raíz (inodo 0, bloque 3) contiene las dos entradas;
`ramfs_lookup` recorre la tabla y la ruta vacía o `/` resuelve a la raíz.

## VFS

| Operación | Firma (kernel) | Errores |
|---|---|---|
| init | `vfs_init()->bool` | falla si ya estaba inicializado |
| open | `vfs_open_flags(path:u64,flags:u64)->i64` | flags 0 abre lo existente; flags 1 permite crear al escribir; −22 EINVAL, −2 ENOENT, −24 EMFILE |
| read | `vfs_read(fd,buf,count)->i64` | −9 EBADF, −21 EISDIR, −5 EIO si el PFS desaparece, 0 EOF |
| write (kernel) | `vfs_write(fd,buf,count)->i64` | −9 EBADF, −21 EISDIR, −28 ENOSPC, −27 EFBIG (>512 B PFS), −5 EIO, −13 EACCES (boot.txt) |
| write (CPL3) | `vfs_write_user(fd,buf,count)->i64` | además −13 EACCES si el modo no concede escritura; −27 EFBIG, −5 EIO; boot.txt devuelve −13 |
| close | `vfs_close(fd)->i64` | −9 EBADF |
| close_all | `vfs_close_all()` | libera las 16 ranuras y sus nombres PFS; se invoca al terminar o fallar la tarea |
| readdir | `vfs_readdir(buf,count)->i64` | nombres separados por NUL; −28 si no cabe (sin escritura parcial) |

`vfs_open_flags` salta una barra inicial y busca primero en RAMFS. Si no hay
archivo RAMFS, busca en la caché ZENFS02. `flags=0` conserva la apertura de
archivos existentes. `flags=1` devuelve un descriptor pendiente para un nombre
PFS válido que aún no exista. Cerrar ese descriptor sin escribir lo descarta;
leerlo devuelve EBADF. La primera escritura confirma nombre y contenido en
una sola operación. Para un archivo existente, `flags=1` permite reemplazarlo.
RAMFS mantiene la precedencia cuando los nombres coinciden.

La caché VFS guarda nombre, tamaño y datos de cada archivo PFS. `read` sirve
esa instantánea. `write` reemplaza el contenido completo desde offset cero;
0 bytes deja un archivo vacío y más de 512 devuelve EFBIG sin tocar el disco.
El commit escribe el sector de datos libre, sincroniza, escribe la tabla
alternativa, sincroniza, y publica la raíz alternativa al final. Solo entonces
se actualiza la caché. `boot.txt` devuelve EACCES. Ante un fallo de escritura
con resultado incierto, la caché se invalida y los descriptores PFS devuelven
EIO hasta remontar.

`vfs_readdir` calcula primero el tamaño total (nombres RAMFS + nombres PFS),
rechaza con −28 si no cabe y solo entonces escribe. El orden es estable y
documentado: **primero RAMFS en el orden de su directorio**
(`hello.zen`, `notes.txt`) y **después PFS por índice de inodo**
(`boot.txt`, …), todos separados por NUL. Si el disco no está disponible,
`pfs_readdir_size` contribuye 0 y la lista queda exactamente como en el Hito 7.

`read`/`write` RAMFS copian byte a byte con `memory_read8`/`memory_write8`;
`read` siempre empieza en el offset 0 (no hay posición por descriptor) y `write`
añade al final, rechazando con −28 si el bloque está lleno. El fixture es 0644:
el kernel escribe por `vfs_write`, CPL3 recibe EACCES por `vfs_write_user`. No
hay credenciales por usuario: CPL3 se modela como la clase «otros» del modo (bit
0o002), política documentada y cubierta por pruebas.

## Integración con ZENFS02 (TASK-926–928)

`pfs_boot()` monta la raíz válida de generación más reciente o migra un disco
ZENFS01 válido sin modificar LBA 16–32. Un formato reconocible pero corrupto
produce `PFS: UNAVAILABLE`. El contador `boot.txt` se actualiza por commit
copy-on-write. Después, `pfs_export` publica una caché supervisora de 8192 B;
los 512 B en +4608 se reutilizan como scratch de escritura. Sin disco, el VFS
sigue ofreciendo solo RAMFS y el kernel completa el arranque.

## Syscalls de archivos (int0x80)

Se añaden al dispatcher de usuario; los números 1–3 del Hito6 no cambian.

| Syscall | RAX | RDI | RSI | RDX | Resultado |
|---|---:|---|---|---|---|
| open |4|puntero a ruta usuario|flags: 0 existente, 1 crear al escribir|—|fd≥100 o error negativo|
| read |5|fd|buffer usuario|número≤4096|bytes leídos o error|
| write |6|fd|buffer usuario|número≤4096|bytes escritos o error|
| close |7|fd|—|—|0 o error|

`open` valida los 256 bytes de la ruta con `user_buffer_valid`, la copia a un scratch supervisor de 512 B y la termina en NUL antes de llamar al VFS; no se pasa ningún puntero de usuario al VFS. `read` valida el buffer de destino con `user_buffer_writable` (PTE presente, usuario y escribible: `PTE&7==7`) para que el kernel nunca escriba en texto de solo lectura; `write` valida la fuente con `user_buffer_valid` (`PTE&5==5`). Ambas rutas devuelven −14 EFAULT antes de tocar memoria.

## Flujo init/shell verificado

El loader admite un único ELF estático y una invocación activa. La trayectoria válida (`case 0`) de `ferros/user/main.zen` actúa como init/shell mínimo: tras comprobar CPL3, flags, GPR, BSS cero y errores de escritura, imprime `SHELL> ls`, abre `hello.zen`, imprime el nombre, imprime `SHELL> cat hello.zen`, comprueba que `read` con destino de solo lectura devuelve −14 y que `write` desde CPL3 devuelve −13, lee el archivo por VFS, escribe el contenido al puerto serie, cierra el descriptor y deja a propósito un descriptor abierto para probar el cierre de teardown. Cualquier fallo devuelve un código 15–24 y el controlador kernel aborta con `userspace test failed`.

Salida real (release), con el guion por defecto sin cambios:

```text
USER: Hello from Zen
SHELL> ls
hello.zen
SHELL> cat hello.zen
Hello
SHELL: READY
SHELL> ls
hello.zen
notes.txt
boot.txt
SHELL> cat hello.zen
Hello
SHELL> help
commands: help ls cat put exit
SHELL> exit
SHELL: DONE
USERSPACE: RING3 AND SYSCALLS OK
USERSPACE: ISOLATION AND CLEANUP OK
USERSPACE: STATS runs=7 writes=18 rejected=6 irqs=1
FS: RAMFS OK
FS: VFS OPEN/READ/CLOSE OK
Boot successful
HITO 7 OK
```

`ls` emite los tres nombres con una sola escritura, por lo que `writes` sigue
siendo 18. El camino `cat boot.txt` se ejerce con entrada propia en
`ferros/tests/test_pfs_vfs.py` (dos arranques, `boot=1`/`boot=2`), no en el
guion por defecto. TASK-928 añade `put <ruta> <texto>` para archivos PFS nuevos o
existentes: usa open4/write6/close7 y muestra `SHELL: STORED` tras éxito.
La línea del shell admite hasta 64 B, por lo que el texto máximo es
`64 − 5 − longitud(ruta)` bytes; la syscall admite 512 B. Se acepta texto
vacío (`put saved.txt `) para truncar. El menú help incluye `put`.

Después de la suite de usuario, el kernel ejecuta `vfs_self_test`: open/read/close del fixture con comprobación de contenido, EBADF tras cerrar, ENOENT con ruta desconocida, EISDIR leyendo/escribiendo la raíz, EACCES en la ruta CPL3 frente a escritura de kernel permitida, EMFILE con 16 descriptores abiertos y close_all/reutilización del 100, y ENOSPC con bloque lleno y sin bloques libres. Desde TASK-919 añade las comprobaciones PFS descritas arriba (visible, lectura, EACCES en boot.txt, cierre y RAMFS intacto). La prueba toma una instantánea del fixture antes de modificarlo y restaura tamaño, bloque, contenido y `free_blocks=250` antes de terminar; el test host comprueba que el archivo queda con tamaño 5 y contenido `Hello`. El scratch vive en la cola de la página de estado, nunca en el pool. Solo entonces imprime `FS: VFS OPEN/READ/CLOSE OK` y `HITO 7 OK`.

Pruebas: `ferros/tests/test_vfs.py` compila el código VFS real contra mocks host
con el PFS marcado como no disponible y recorre init/open/read/close, EBADF,
ENOENT, EISDIR, EACCES, EMFILE, reutilización de descriptor y ENOSPC en normal y
release. `ferros/tests/test_pfs_vfs.py` arranca QEMU dos veces con el mismo disco
y entrada `ls` + `cat boot.txt`: comprueba `boot.txt` en `ls`, `boot=1`/`boot=2`
en `cat`, estado 33, `writes=18`, sin PANIC y `HITO 7 OK`.

## Límites conocidos

- RAMFS conserva sus dos fixtures y no admite creación ni borrado desde CPL3.
- ZENFS02 admite ocho archivos de 512 B, nombres de 1–23 caracteres ASCII y
  una sola escritura de reemplazo por syscall. No hay directorios dinámicos,
  `unlink`, renombrado ni permisos por usuario persistentes.
- `read` no mantiene offset por descriptor; cada llamada empieza en cero.
- La caché de 8192 B no se libera. Cambios externos al disco durante la sesión
  no se detectan.
- El modelo supone una CPU y serialización de syscalls. La recuperación frente
  a cortes depende del orden de `ata_flush`; no implica durabilidad física.
