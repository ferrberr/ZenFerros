# RAMFS, VFS y ZENFS01 — TASK-919 / TASK-924

Ferros incorpora un sistema de archivos en memoria de alcance mínimo y, desde
TASK-919, expone también los archivos persistentes de ZENFS01 a través del
mismo VFS. TASK-924 permite reemplazar archivos persistentes existentes desde
CPL3 mediante la syscall 6. RAMFS mantiene su semántica de append y sus
permisos 0644; ZENFS01 ofrece reemplazo completo y síncrono de hasta 512 B.
No hay montaje real, creación desde CPL3, journaling ni atomicidad frente a
cortes de energía. `boot.txt` está reservado al kernel.

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
| open | `vfs_open(path:u64)->i64` | −2 ENOENT, −24 EMFILE, −1 sin init |
| read | `vfs_read(fd,buf,count)->i64` | −9 EBADF, −21 EISDIR, −5 EIO si el PFS desaparece, 0 EOF |
| write (kernel) | `vfs_write(fd,buf,count)->i64` | −9 EBADF, −21 EISDIR, −28 ENOSPC, −27 EFBIG (>512 B PFS), −5 EIO, −13 EACCES (boot.txt) |
| write (CPL3) | `vfs_write_user(fd,buf,count)->i64` | además −13 EACCES si el modo no concede escritura; −27 EFBIG, −5 EIO; boot.txt devuelve −13 |
| close | `vfs_close(fd)->i64` | −9 EBADF |
| close_all | `vfs_close_all()` | libera las 16 ranuras y sus nombres PFS; se invoca al terminar o fallar la tarea |
| readdir | `vfs_readdir(buf,count)->i64` | nombres separados por NUL; −28 si no cabe (sin escritura parcial) |

`vfs_open` salta una barra inicial y busca primero en el directorio RAMFS
(`hello.zen`, `notes.txt`, o la raíz con ruta vacía). Si RAMFS devuelve ENOENT y
la ruta no está vacía, consulta ZENFS01 con `pfs_find_ptr` (nombre de kernel, no
`str` de Zen). Si el archivo existe, reserva la primera ranura libre y guarda en
ella la etiqueta `0x5046534644000000` en lugar de un puntero a inodo; el nombre
de hasta 23 bytes se copia a `vfs_state+1280+slot*24`. Los descriptores siguen
siendo `100+slot` y comparten la tabla de 16 ranuras con RAMFS. Si RAMFS
contiene el mismo nombre, RAMFS gana. Cualquier error de PFS (disco ausente,
superbloque corrupto o ENOENT) conserva el resultado −2 anterior.

`vfs_read` de un descriptor PFS llama a `pfs_read_ptr`, que sirve los bytes desde
la caché de ZENFS01 publicada en el arranque y copia como máximo
`min(size,max,512)` al buffer validado por `user_buffer_writable`. Un descriptor
PFS cuya caché fue invalidada devuelve −5 EIO; `vfs_close` limpia ranura y nombre.

Para PFS, `vfs_write` y `vfs_write_user` reemplazan el contenido completo del
archivo, desde offset 0, y actualizan su tamaño exacto (incluido 0 para truncar).
No hay escrituras parciales: más de 512 B devuelve −27 EFBIG sin tocar disco.
`boot.txt` devuelve −13 EACCES, incluso al intentar truncarlo. El escritor
`pfs_commit_ptr` revalida el superbloque y busca el inodo por nombre, escribe el
sector de datos, relee/actualiza el inodo y ejecuta `ata_flush`. Devuelve el
número pedido solo tras éxito de todas las operaciones. El VFS actualiza datos
y tamaño en caché después del flush, visibles para todos los descriptores.

Un fallo de lectura/validación o ATA devuelve −5 EIO. Si ya se intentó escribir
el sector de datos, la caché entera se invalida: lecturas de fds PFS abiertos
devuelven EIO; nuevos `open` devuelven ENOENT y `readdir` solo lista RAMFS hasta
reiniciar. No se presenta una copia antigua como si describiera el disco actual.
El fallo puede haber modificado los datos o el tamaño en disco. La secuencia
**no es atómica**: un corte puede dejar datos nuevos o parciales con tamaño
antiguo, metadatos nuevos con datos incompletos o una escritura no persistida.
No hay rollback, journal ni checksum por archivo.

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

## Integración con ZENFS01 (TASK-919 / TASK-924)

ZENFS01 no se monta: `pfs_boot()` sigue siendo la única inicialización y
continúa creando/incrementando `boot.txt`. Después, `kernel_entry` reserva con
`heap_alloc` una caché de 8192 B y llama a `pfs_export`: este recorre los
inodos y copia nombre, tamaño y hasta 512 B de datos por archivo usando la ruta
de lectura `pfs_disk_read_ptr` (la misma lógica de `pfs_read`). El VFS publica
el puntero en `vfs_state+1160` y sirve `open`/`read`/`readdir` desde esa
instantánea mediante `pfs_find_ptr`, `pfs_read_ptr`, `pfs_readdir_size`,
`pfs_readdir_names` y `pfs_available`, definidos en `vfs.zen` para no acoplar
las lecturas a ATA/heap; los tests host aislados aportan un stub del escritor.
El scratch de escritura usa +4608..5119 de la misma reserva: no hay
`heap_alloc` por syscall, ni agotamiento por escrituras repetidas. `vfs_self_test`
comprueba, cuando `pfs_available()` es cierto:

- que `boot.txt` aparece en `vfs_readdir` después de los dos fixtures RAMFS;
- que `vfs_open("boot.txt")` devuelve un descriptor y `vfs_read` entrega
  `boot=<n>\n` con solo dígitos;
- que `vfs_write` y `vfs_write_user` devuelven −13 y no alteran el contenido;
- que el cierre funciona, que leer después da −9 y que el siguiente
  `vfs_open("hello.zen")` reutiliza la ranura y sigue leyendo `Hello`.

Sin disco (`pfs_available()==false`) el test exige el comportamiento previo:
`boot.txt` no existe, `readdir` mide 20 bytes y el arranque continúa sin panic.
El detalle del mini-FS está en `docs/ferros/persistence.md`.


## Syscalls de archivos (int0x80)

Se añaden al dispatcher de usuario; los números 1–3 del Hito6 no cambian.

| Syscall | RAX | RDI | RSI | RDX | Resultado |
|---|---:|---|---|---|---|
| open |4|puntero a ruta usuario|flags (reservado)|—|fd≥100 o error negativo|
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
commands: help ls cat exit
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
guion por defecto. TASK-924 añade `put <ruta> <texto>` para archivos PFS
existentes: usa open4/write6/close7 y muestra `SHELL: STORED` tras éxito.
La línea del shell admite hasta 64 B, por lo que el texto máximo es
`64 − 5 − longitud(ruta)` bytes; la syscall admite 512 B. Se acepta texto
vacío (`put saved.txt `) para truncar. El menú help conserva su salida previa.

Después de la suite de usuario, el kernel ejecuta `vfs_self_test`: open/read/close del fixture con comprobación de contenido, EBADF tras cerrar, ENOENT con ruta desconocida, EISDIR leyendo/escribiendo la raíz, EACCES en la ruta CPL3 frente a escritura de kernel permitida, EMFILE con 16 descriptores abiertos y close_all/reutilización del 100, y ENOSPC con bloque lleno y sin bloques libres. Desde TASK-919 añade las comprobaciones PFS descritas arriba (visible, lectura, EACCES en boot.txt, cierre y RAMFS intacto). La prueba toma una instantánea del fixture antes de modificarlo y restaura tamaño, bloque, contenido y `free_blocks=250` antes de terminar; el test host comprueba que el archivo queda con tamaño 5 y contenido `Hello`. El scratch vive en la cola de la página de estado, nunca en el pool. Solo entonces imprime `FS: VFS OPEN/READ/CLOSE OK` y `HITO 7 OK`.

Pruebas: `ferros/tests/test_vfs.py` compila el código VFS real contra mocks host
con el PFS marcado como no disponible y recorre init/open/read/close, EBADF,
ENOENT, EISDIR, EACCES, EMFILE, reutilización de descriptor y ENOSPC en normal y
release. `ferros/tests/test_pfs_vfs.py` arranca QEMU dos veces con el mismo disco
y entrada `ls` + `cat boot.txt`: comprueba `boot.txt` en `ls`, `boot=1`/`boot=2`
en `cat`, estado 33, `writes=18`, sin PANIC y `HITO 7 OK`.

## Límites conocidos

- Directorio raíz de una sola tabla con dos fixtures; sin creación/borrado (`unlink`), `stat`, renombrado ni permisos por usuario.
- `read` no mantiene offset por descriptor: cada llamada relee desde el inicio del archivo.
- `open` ignora `flags`; la escritura desde CPL3 se rechaza por modo (0644) en lugar de comprobar flags de apertura.
- La sonda de fuga de descriptor del programa de usuario deja un fd abierto a propósito; el teardown debe cerrarlo o el hito falla (verificado por mutación).
- ZENFS01 no tiene montaje real, creación, borrado ni permisos por usuario desde
  CPL3. Solo se reemplazan archivos existentes; `boot.txt` sigue protegido.
- La caché ocupa 8192 B del heap y no se libera. Las escrituras usan scratch
  reutilizable; cambios externos al disco durante la ejecución no se detectan.
- El nombre PFS se copia en la tabla de descriptores del VFS (máx. 23 B + NUL); rutas más largas o con `/` se rechazan en `pfs_find_ptr`.
- Sin asignación concurrente: se asume una CPU y las mutaciones del VFS ocurren en contexto de syscall o de kernel con interrupciones ya controladas por el dispatcher.


TASK-924 verifica escritura CPL3 y reinicio con el mismo disco en debug y
release (4 QEMU). La imagen se prepara con un `saved.txt` vacío; después solo
el guest modifica el disco. El test escribe 512 B binarios, comprueba EFBIG,
EFAULT y EINVAL sin cambiar el contenido, reemplaza con texto corto y compara
bytes/tamaño tanto por VFS como directamente en la imagen antes/después del
reinicio. El mock ATA prueba 150 escrituras sin reserva de heap y fallos de
datos, relectura de inodo, metadatos y flush con invalidación de caché.
