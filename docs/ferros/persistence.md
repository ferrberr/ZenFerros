# Persistencia ATA y ZENFS02 — TASK-914, TASK-916 y TASK-926–929

Ferros usa un disco raw IDE/ATA. El contador independiente `ZENPERS1` ocupa
LBA 0. El sistema de archivos conserva los sectores ZENFS01 de LBA 16–32 y
usa ZENFS02 en LBA 33–46. ATA PIO transfiere sectores de 512 B y `ata_flush`
sincroniza cada etapa antes de publicar metadatos.

## Formato ZENFS02

| LBA | Uso |
|---|---|
| 16 | Superbloque ZENFS01, solo lectura tras migración |
| 17–24 | Inodos ZENFS01, solo lectura |
| 25–32 | Datos ZENFS01, solo lectura |
| 33–34 | Raíces A/B ZENFS02 |
| 35–36 | Tablas A/B de ocho entradas |
| 37–45 | Nueve sectores de datos; al menos uno libre |
| 46 | Marca de activación |

Todos los enteros son little endian. La raíz del banco `i` contiene:

| Offset | Campo |
|---|---|
| +0 | `ZENFS02\0` (8 B) |
| +8 | versión `u32=2` |
| +12 | número de archivos `u32` (0..8) |
| +16 | generación `u64` (>0) |
| +24 | LBA de tabla `u32=35+i` |
| +28 | FNV-1a32 de los 512 B de tabla |
| +32 | FNV-1a32 de los sectores de datos usados completos, concatenados en orden de tabla |
| +36 | FNV-1a32 de bytes +0..35 de esta raíz |
| +40..511 | reservado a cero |

La tabla contiene ocho entradas de 64 B. Cada entrada tiene nombre ASCII
imprimible `name[24]` terminado en NUL (+0), tamaño `u64` ≤512 (+24), LBA de
datos `u32` en 37..45 (+32), FNV-1a32 del sector completo (+36), `used=1`
(+40) y relleno cero. Las entradas libres son cero. No se aceptan nombres
duplicados, rutas con `/` ni sectores compartidos. La marca usa `ZENACT02`
(+0), versión `u32=2` (+8), FNV-1a32 de bytes +0..11 (+12) y resto cero.
FNV-1a32 empieza en 2166136261 y para cada byte calcula
`((hash ^ byte) * 16777619) & 0xffffffff`.

## Montaje y migración

Al arrancar se validan ambas raíces, tablas y datos; se elige la generación
válida más reciente. Con una raíz válida y marca ausente o dañada, se completa
la marca antes de modificar el sistema. Con marca válida y ambas raíces
inválidas, se muestra `PFS: UNAVAILABLE`: nunca se recupera una copia v1 que
ya podría estar obsoleta.

Sin raíz ni marca válida, un ZENFS01 válido se copia a ZENFS02. Primero se
escriben los datos, después la tabla, después la raíz y por último la marca,
con `ata_flush` entre etapas. Los sectores v1 permanecen intactos; un corte
antes de publicar la raíz permite reintentar la migración. Un v1 reconocible
pero corrupto causa `PFS: UNAVAILABLE` sin formateo. Un disco vacío se inicia
directamente como ZENFS02. Tras el montaje, el kernel crea o incrementa
`boot.txt` mediante el mismo mecanismo de commit y publica la caché VFS.

## Escritura desde CPL3

`open(path, 0)` abre un archivo existente. `open(path, 1)` también permite un
nombre nuevo: devuelve un descriptor pendiente. `close` sin `write` lo
descarta. La primera escritura crea nombre y contenido en un solo commit.
`put <nombre> <texto>` usa el flag 1 tanto para crear como para reemplazar.
`boot.txt` está protegido. Se admiten como máximo ocho archivos de 512 B;
una escritura de 513 B se rechaza sin cambiar el disco, y una de 0 B crea o
trunca a vacío.

Cada commit escoge un sector de datos no referenciado por la raíz activa,
lo escribe y sincroniza, escribe y sincroniza la tabla del otro banco, y
publica y sincroniza su raíz al final. La caché VFS cambia solo tras éxito.
Ante un fallo de escritura de resultado incierto, el VFS invalida la caché y
devuelve EIO para operaciones PFS hasta el siguiente montaje. RAMFS continúa
separado.

## Pruebas y límite de la garantía

`ferros/tests/test_zenfs02.py` ejecuta el código Zen real contra ATA mock en
debug/release. Comprueba migración de v1 con archivos y contador, cortes y
sectores rasgados en datos, tabla, raíz y marca, fallos de flush, límites y
corrupción reconocible. `ferros/tests/test_pfs_vfs.py` usa QEMU debug/release
con el mismo disco entre arranques: creación, reemplazo, lectura inmediata,
lectura tras reinicio y tamaños 0/512/513 B. La puerta local añade aislamiento,
arranque sin disco, seis boots de aceptación y reproducibilidad.

La garantía de recuperación se limita al modelo probado: `ata_flush` debe
respetar el orden de escritura, y el mock cubre comandos fallidos y sectores
incompletos. QEMU confirma la integración, pero estas pruebas no demuestran
durabilidad absoluta ni comportamiento frente a cortes en hardware físico.
