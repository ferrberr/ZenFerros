# Persistencia ATA y mini-FS ZENFS01 (TASK-914 / TASK-916 / TASK-919)

Ferros guarda estado en un disco IDE/ATA raw y lo recupera entre ejecuciones
distintas de QEMU. Hay dos capas independientes sobre el mismo disco:

1. **TASK-914 — contador de arranques** en el sector 0 (`ZENPERS1`).
2. **TASK-916 — mini-FS persistente** desde el LBA 16 (`ZENFS01`), con archivos
   con nombre, inodos y un bloque de datos por archivo.

**TASK-919** conecta el mini-FS con el VFS: `boot.txt` aparece en `ls` y `cat
boot.txt` lo lee desde CPL3, siempre en modo solo lectura.

Ninguna de las dos usa caché, journaling ni particiones. La persistencia es
opcional: si ATA falla, el arranque continúa siempre sin `kernel_panic`.

## Integración en el arranque

`kernel_entry` ejecuta ambas capas después de las estadísticas del scheduler y
antes de `userspace_self_test()` (donde corre el shell en CPL3):

```text
SCHEDULER: STATS switches=... preemptions=... yields=... completed=...
PERSIST: BOOT 1
PFS: BOOT 1 FILES=1
USER: Hello from Zen
SHELL: READY
...
HITO 7 OK
```

- `PERSIST: BOOT <n>` lo emite `storage_boot()`.
- `PFS: BOOT <n> FILES=<n>` lo emite `pfs_boot()` justo después; `FILES` cuenta
  los inodos ocupados (incluido `boot.txt`).
- El resto de la transcripción, los hitos 1–8 y `writes=18` no cambian.
- Cualquier fallo de ATA produce `PERSIST: UNAVAILABLE` y/o
  `PFS: UNAVAILABLE`; el arranque sigue y termina en estado 33.

Tras `pfs_boot()`, `kernel_entry` construye una instantánea read-only de 8192 B
con `pfs_export` (usa `pfs_disk_read_ptr`, la misma ruta que `pfs_read`) y la
publica en el VFS. `ls` muestra `hello.zen`, `notes.txt`, `boot.txt` (RAMFS
primero, PFS después) y `cat boot.txt` imprime `boot=<n>`;
`vfs_write`/`vfs_write_user` sobre ese descriptor devuelven EROFS (−30). El VFS
sirve `open`/`read`/`readdir` desde la instantánea con `pfs_find_ptr`,
`pfs_read_ptr`, `pfs_readdir_size`, `pfs_readdir_names` y `pfs_available`
(definidos en `vfs.zen` para que los tests host puedan compilarlo sin ATA).

Unidades nuevas en `build_ferros.py`:

```text
arch/x86_64/abi.zen
drivers/serial.zen
memory.zen
drivers/ata.zen
interrupts.zen
scheduler.zen
vfs.zen
userspace.zen
runtime.zen
storage.zen        <- TASK-914 (contador)
storage_fs.zen     <- TASK-916 (mini-FS)
main.zen
```

`storage.zen` y `storage_fs.zen` van después de `memory.zen`/`ata.zen` y antes
de `main.zen`.

## Driver ATA PIO (`ferros/kernel/drivers/ata.zen`)

- Canal primario: puertos `0x1F0..0x1F7`, alternate status `0x3F6`.
- Una unidad: master (`0xE0`), geometría LBA28 (máximo `0x0FFFFFFF`).
- Una transferencia = un sector de 512 bytes (256 palabras).
- Sin IRQ, sin DMA y sin caché propia: todo es polling acotado (2.000.000 de
  lecturas como máximo).
- Retardos con 4 lecturas de alternate status (≈400 ns).
- Errores negativos: `-1` argumento/LBA inválido, `-2` canal vacío o bus
  flotante (`0x00`/`0xFF`), `-3` ERR/DF, `-4` timeout.

```zen
fn ata_read_sector(lba:u64,dst:u64)->i64
fn ata_write_sector(lba:u64,src:u64)->i64
fn ata_flush()->i64
```

`dst`/`src` son direcciones supervisoras de 512 bytes. El valor de retorno es
`0` en éxito o un código negativo.

### Shims de 16 bits

`io.S` expone `ferros_in8/out8` y `ferros_out32`, pero el registro de datos IDE
es de 16 bits. En QEMU dos lecturas `inb` de `0x1F0` devuelven dos veces el byte
bajo de la misma palabra, no la palabra completa. Por eso el driver declara
`ferros_ata_in16/out16` y `build_ferros.py` genera y enlaza un artefacto
`ata_io.S` con `inw`/`outw`. No se modificó `io.S` porque pertenece a otra tarea.

## Capa 1: contador de arranques (TASK-914)

Sector 0 completo (512 bytes), little endian:

| Offset | Bytes | Contenido |
|--------|-------|-----------|
| `+0`   | 8     | magic ASCII `ZENPERS1` |
| `+8`   | 8     | contador de arranques `u64` |
| `+16`  | 496   | reservado, se escribe a cero al formatear |

`storage_boot()` reserva un buffer de 512 bytes, lee el sector 0, formatea si el
magic no coincide o el contador es `0`/`0xFFFFFFFFFFFFFFFF`, incrementa el
contador, reescribe el sector, hace `ata_flush()` y solo entonces imprime
`PERSIST: BOOT <n>`.

## Capa 2: mini-FS ZENFS01 (TASK-916)

### Layout del disco

Little endian, sectores de 512 bytes. El FS no toca el sector 0 del contador.

| LBAs | Bytes | Contenido |
|------|-------|-----------|
| 16 | 512 | superbloque |
| 17–24 | 8 sectores | un inodo de 64 B por sector: inodo `i` en LBA `17+i` |
| 25–32 | 8 sectores | un bloque de datos por inodo: archivo `i` en LBA `25+i` |

Superbloque (LBA 16):

| Offset | Bytes | Contenido |
|--------|-------|-----------|
| `+0` | 8 | magic `ZENFS01` + NUL de relleno |
| `+8` | 4 | versión `u32` = 1 |
| `+12` | 4 | número de inodos `u32` = 8 |
| `+16` | 4 | checksum FNV-1a32 de los bytes `+0..+15` |
| `+20` | 492 | reservado, cero |

Inodo (64 B; el resto del sector hasta 512 B queda a cero):

| Offset | Bytes | Contenido |
|--------|-------|-----------|
| `+0` | 24 | `name[24]`, ASCII y relleno NUL |
| `+24` | 8 | `size` `u64` (0..512) |
| `+32` | 4 | `start_lba` `u32` (= `25+i`) |
| `+36` | 1 | `used` (`1` = inodo ocupado) |
| `+37` | 27 | reservado |

`start_lba` fija el bloque de datos según el índice, de modo que no puede haber
dos archivos apuntando al mismo sector. `size` es la longitud real del archivo;
el resto del bloque de datos no se interpreta.

### FNV-1a32

El checksum se calcula en `u64` y se enmascara a 32 bits para no depender de la
aritmética de `u32` del backend, igual que los checksums del selfhost:

```text
hash = 2166136261
for byte in superblock[0..16):
    hash = ((hash ^ byte) * 16777619) & 0xFFFFFFFF
```

`pfs_boot()` considera inválido el superbloque si falla el magic, la versión
(`!=1`), el número de inodos (`!=8`) o el checksum. En ese caso formatea:
reescribe el superbloque, pone a cero los ocho sectores de inodos y hace
`ata_flush()`.

### API (`ferros/kernel/storage_fs.zen`)

```zen
fn pfs_boot()
fn pfs_list()->u32
fn pfs_find(name:str)->i64
fn pfs_create(name:str)->i64
fn pfs_write(name:str,src:u64,len:u64)->i64
fn pfs_read(name:str,dst:u64,max:u64)->i64
fn pfs_delete(name:str)->i64
// TASK-919: instantánea read-only para el VFS y lectura por puntero
fn pfs_export(cache:u64)->i64
fn pfs_disk_read_ptr(name:u64,dst:u64,max:u64)->i64
```

| Retorno | Significado |
|---------|-------------|
| `>=0` | éxito: índice de inodo (`find`/`create`), nº de archivos (`list`), bytes (`read`/`write`) o `0` (`delete`) |
| `-1` | argumento inválido: nombre fuera de 1–23 ASCII, con `/`, duplicado, `len>512`, puntero nulo, `max>0` con `dst=0` |
| `-2` | ATA no disponible, sector fuera del disco o error de E/S |
| `-3` | superbloque corrupto, sin formatear o no validado (API llamada antes de un `pfs_boot` correcto) |
| `-4` | tabla de inodos llena (8 archivos) |
| `-5` | ENOENT: no existe el nombre |

Reglas de validación:

- Nombre: 1–23 bytes ASCII imprimibles (`0x20..0x7E`) y sin `/`; el byte
  siguiente al nombre en el inodo debe ser NUL.
- Sin duplicados: `pfs_create` devuelve `-1` si el nombre ya existe.
- `pfs_write` acepta `len` de 0 a 512; nunca escribe más de un sector.
- `pfs_read` recorta `max` a 512 y a `size`; con `size=0` devuelve `0` sin leer
  el bloque de datos.
- Cada llamada de la API de disco reserva un buffer de 512 bytes con
  `heap_alloc` y lo reutiliza para todos los sectores que toca. El heap no tiene
  `free()`, así que el kernel solo llama a esta API desde `pfs_boot()` y desde
  `pfs_export()` (una lectura por archivo). TASK-919 reserva además la
  instantánea de 8192 B una sola vez. El shell y los tests quedan muy por debajo
  de 64 KiB.

### Algoritmo de `pfs_boot()`

1. Reserva un buffer de 512 bytes. Si falla: `PFS: UNAVAILABLE`.
2. Lee y valida el superbloque. Si es inválido, lo formatea.
3. Recorre los ocho inodos: cuenta ocupados, localiza el primer hueco y busca
   `boot.txt` guardando su `size`.
4. Si `boot.txt` existe, lee su bloque de datos, parsea `boot=<decimal>\n` y
   suma 1. Un contenido inválido, `0` o `0xFFFFFFFFFFFFFFFF` reinicia a 1.
5. Si no existe, ocupa el primer hueco con un inodo `boot.txt` y escribe
   `boot=1\n`. Si la tabla está llena sin `boot.txt`: `PFS: UNAVAILABLE`.
6. Escribe el bloque de datos con `boot=<n>\n`, actualiza `size` en el inodo
   (la longitud cambia con los dígitos), hace `ata_flush()` y solo entonces
   imprime `PFS: BOOT <n> FILES=<n>`.

Cualquier fallo de lectura, escritura o flush se traduce en
`PFS: UNAVAILABLE`; el FS es opcional y nunca provoca `kernel_panic`.

## Integración ZENFS01 → VFS (TASK-919)

El mini-FS no se monta ni se escribe desde el VFS. El flujo de lectura es:

```text
shell `ls`  → syscall 9 → vfs_readdir → RAMFS (hello.zen, notes.txt)
                                      → pfs_readdir_size/names (boot.txt)
shell `cat boot.txt` → syscall 4 → vfs_open → RAMFS miss
                                      → pfs_find_ptr("boot.txt") → fd etiquetado
                     → syscall 5 → vfs_read → pfs_read_ptr → buffer usuario
                     → syscall 7 → vfs_close
```

- El descriptor PFS guarda la etiqueta `0x5046534644000000` en la ranura del VFS
  y el nombre (≤23 B + NUL) en `vfs_state+1280+slot*24`; así `vfs_read` puede
  buscar el archivo en la instantánea sin volver a resolver la ruta.
- La instantánea se construye una sola vez tras `pfs_boot()`
  (`pfs_export` → `pfs_disk_read_ptr`, misma lógica que `pfs_read`) y se publica
  en `vfs_state+1160`. El VFS nunca vuelve a tocar ATA ni el disco.
- RAMFS tiene prioridad si ambos comparten nombre.
- `vfs_readdir` es determinista: RAMFS en el orden de su directorio y luego PFS
  por índice de inodo; todos los nombres van separados por NUL.
- `vfs_write` y `vfs_write_user` devuelven −30 EROFS para un fd PFS; no hay
  `pfs_write` desde el VFS ni desde CPL3.
- Sin disco (`pfs_available()==false`), `vfs_open("boot.txt")` devuelve −2 y
  `vfs_readdir` enumera solo RAMFS; el shell y `HITO 7 OK` se mantienen.

`vfs_self_test` verifica PFS visible, lectura de `boot.txt`, escritura
rechazada, cierre, EBADF posterior y que RAMFS sigue intacto. Los tests host
`test_vfs.py` (PFS no disponible) y `test_pfs_vfs.py` (dos arranques QEMU con el
mismo disco y `cat boot.txt`) cubren ambos caminos.

## Evolución desde el contador

`storage.zen` (TASK-914) demostró que un sector sobrevive entre arranques, pero
no tenía nombres, metadatos ni validación de integridad. `storage_fs.zen`
(TASK-916) añade:

- un superbloque identificable y versionado con checksum FNV-1a32;
- inodos con nombre, tamaño, bloque de datos y flag de uso;
- operaciones de archivo (crear, escribir, leer, borrar, listar, buscar);
- `boot.txt` como archivo normal: el contador ya no vive en un offset fijo,
  sino en el contenido de un archivo que el FS puede crear, leer y reescribir.

El contador TASK-914 se conserva en el sector 0 como evidencia independiente.
Ambas capas incrementan a la vez en cada arranque y comparten el mismo disco.

## Runner QEMU (`infrastructure/scripts/boot_ferros.py`)

- `boot(..., disk_image=RUTA)` y `--disk RUTA` aceptan un disco raw.
- Si no se indica disco, se crea un temporal de 1 MiB en el directorio de
  salida y se elimina al terminar. Por tanto, `--repeat N` sin `--disk`
  arranca siempre con un disco nuevo y muestra `BOOT 1` en ambas capas.
- Si `--disk` apunta a una ruta inexistente, se crea un raw de 1 MiB. La misma
  ruta se reutiliza en todas las repeticiones y en `--all`.
- QEMU recibe siempre:
  `-drive file=<ruta>,format=raw,if=ide,index=0`.
- El runner inyecta el guion del shell tras `SHELL: READY`. `PERSIST` y `PFS` se
  validan en orden (scheduler → PERSIST → PFS → `USER: Hello from Zen`) y se
  eliminan de la comparación fija, igual que las estadísticas variables.
- `result.json` incluye `persistence`, `pfs`, `disk` y `disk_temporary`.

## Cómo probarlo

Aceptación completa:

```bash
python3 infrastructure/scripts/build_ferros.py --release
python3 infrastructure/scripts/build_ferros.py
python3 -m unittest discover -s ferros/tests
```

Solo el mini-FS (host + tres arranques QEMU):

```bash
python3 ferros/tests/test_pfs.py
```

VFS + mini-FS (dos arranques QEMU con `ls` + `cat boot.txt`):

```bash
python3 ferros/tests/test_pfs_vfs.py
```

Tres arranques manuales con el mismo disco y evidencia en
`ferros/build/release/boot-01..03`:

```bash
rm -f ferros/build/pfs-demo.img
python3 infrastructure/scripts/boot_ferros.py --release --repeat 3 \
  --disk ferros/build/pfs-demo.img
grep -a "PFS:" ferros/build/release/boot-0*/serial.log
grep -a "PERSIST:" ferros/build/release/boot-0*/serial.log
xxd -s $((16*512)) -l 32 ferros/build/pfs-demo.img   # superbloque ZENFS01
xxd -s $((17*512)) -l 40 ferros/build/pfs-demo.img   # inodo boot.txt
xxd -s $((25*512)) -l 8 ferros/build/pfs-demo.img    # datos boot=3
```

Salida esperada:

```text
PFS: BOOT 1 FILES=1
PFS: BOOT 2 FILES=1
PFS: BOOT 3 FILES=1
PERSIST: BOOT 1
PERSIST: BOOT 2
PERSIST: BOOT 3
00002000: 5a45 4e46 5330 3100 0100 0000 0800 0000  ZENFS01.........
00002200: 626f 6f74 2e74 7874 0000 ...              boot.txt........
00003200: 626f 6f74 3d33 0a                            boot=3.
```

Cada arranque debe terminar con estado 33 (`isa-debug-exit` con `0x10`),
`writes=18`, `HITO 7 OK`, sin `PANIC` y con stderr de QEMU vacío.

## Pruebas

`ferros/tests/test_pfs.py` contiene:

- `PfsHostTests`: compila `storage_fs.zen`, `ata.zen`, `serial.zen` y el
  allocator reales para el host, con un mock C de 64 sectores. Verifica
  formato, magic/versión/nº de inodos/checksum, layout de inodo y datos,
  crecimiento de `boot.txt` de 1 a 10, `create/write/read/delete`, nombres
  inválidos (vacío, `/`, 24 bytes),
  duplicados, `len>512`, tabla llena (`-4`), reutilización de huecos,
  superbloque corrupto (`-3` y reformateo) y ausencia de ATA (`-2` /
  `PFS: UNAVAILABLE`). Se ejecuta en debug y release.
- `PfsGuestTests`: tres invocaciones QEMU reales con el mismo disco raw.
  Exige `PFS: BOOT 1/2/3 FILES=1`, `PERSIST: BOOT 1/2/3`, estado 33,
  `writes=18`, `HITO 7 OK`, sin `PANIC`, stderr vacío y comprueba en la imagen
  el superbloque, el inodo `boot.txt`, el dato `boot=3\n` y el contador del
  sector 0.

`ferros/tests/test_persistence.py` conserva las pruebas de TASK-914 (mock host,
discos temporales y dos arranques QEMU con el mismo disco).

TASK-919 añade `ferros/tests/test_pfs_vfs.py` (1 test, dos arranques QEMU con el
mismo disco y entrada `ls` + `cat boot.txt`): exige `boot.txt` en `ls`,
`boot=1`/`boot=2` en `cat`, estado 33, `writes=18`, sin `PANIC`, `HITO 7 OK` y
stderr vacío. El guion por defecto de TASK-703 no cambia; solo su salida de
`ls`. `test_vfs.py` compila ahora `vfs.zen` sin PFS disponible (la instantánea
no se publica), de modo que el contrato RAMFS de 20 bytes sigue cubierto en
host.

Con TASK-916 la suite Ferros pasó de 39 a **43 tests**; con TASK-919 queda en
**44 tests**:

- 2 tests nuevos de TASK-916 en `test_pfs.py` (host y tres arranques QEMU);
- 1 test nuevo de TASK-916 en `test_boot.py` (`PFS` obligatorio, orden y contadores);
- 1 test nuevo de TASK-916 en `test_shell.py` (orden `PERSIST` → `PFS` → shell);
- 1 test nuevo de TASK-919 en `test_pfs_vfs.py` (dos arranques, `cat boot.txt`).

Los arranques QEMU con estado 33 del conjunto de aceptación pasan a **11/11**
(dos de userspace, dos del shell, dos de persistencia, tres del mini-FS y dos de
PFS+VFS). El runner `--all --repeat 3` sigue produciendo **6/6** arranques con
la transcripción nueva.

## Límites y desviaciones

- Un solo bloque de datos por archivo (≤512 B); no hay archivos grandes ni
  asignación de bloques múltiple.
- Como máximo 8 archivos (8 inodos); sin directorios, enlaces, permisos,
  timestamps ni journaling.
- Sin caché de bloques ni escritura atómica: un corte entre `ata_write_sector`
  y `ata_flush` puede dejar el sector anterior o el nuevo. El checksum detecta
  un superbloque corrupto y provoca reformateo, pero no hay recuperación de
  datos de archivos. TASK-919 añade una instantánea read-only en RAM (no una
  caché de bloques): no se refresca si el disco cambia tras el arranque.
- El FS es síncrono y de un solo núcleo: no hay bloqueos porque el kernel no lo
  usa desde interrupciones ni desde varias CPU.
- El magic se guarda como `ZENFS01` + NUL (8 bytes) para que el campo quede
  alineado; el contrato lo nombra como `ZENFS01`.
- Se usa un inodo por sector (LBA `17+i`) en lugar de empaquetar los 8 inodos
  en un solo sector: encaja con el rango reservado `LBA 17–24` y con el bloque
  de datos `LBA 25+i`, a costa de 7 sectores desaprovechados.
- `pfs_create` devuelve `-1` para duplicados (no hay código EEXIST separado);
  `-4` queda reservado para la tabla llena.
- `pfs_list()` devuelve `0` ante ATA ausente o superbloque corrupto, porque su
  tipo es `u32`; el resto de la API usa los errores negativos.
- Cada llamada de disco consume 512 bytes del heap de 64 KiB sin liberarlos,
  más la instantánea de 8192 B de TASK-919. El kernel llama desde `pfs_boot()`
  y una vez desde `pfs_export()`; los tests host hacen menos de 70 llamadas y
  quedan muy por debajo del límite.
- Probado con QEMU (`-machine pc`, PIIX IDE). No se ha validado en hardware
  real ni con AHCI/SATA.
