# TASK-916 — Evidencia: mini-FS persistente ZENFS01

Fecha: 2026-11-12.

## Entregado
| Archivo | Cambio |
|---|---|
| `ferros/kernel/storage_fs.zen` | FS ZENFS01: superbloque, 8 inodos, datos, API create/read/write/delete/list/find/boot |
| `ferros/kernel/main.zen` | `pfs_boot()` tras `storage_boot()` y antes del shell |
| `infrastructure/scripts/build_ferros.py` | Unidad `storage_fs.zen` |
| `infrastructure/scripts/boot_ferros.py` | Validación de `PFS: BOOT n FILES=n` y orden |
| `ferros/tests/test_pfs.py` | Host mock + 3 arranques QEMU con el mismo disco |
| `ferros/tests/test_boot.py`, `test_shell.py` | Orden PERSIST → PFS → shell |
| `docs/ferros/persistence.md` | Layout, API, evolución, límites y pruebas |

## Evidencia QEMU (mismo disco, 3 arranques)
```
PERSIST: BOOT 1 / PFS: BOOT 1 FILES=1
PERSIST: BOOT 2 / PFS: BOOT 2 FILES=1
PERSIST: BOOT 3 / PFS: BOOT 3 FILES=1
status 33, writes=18, HITO 7 OK, sin PANIC
```
Imagen: LBA16 `ZENFS01\0` + versión/inodos/checksum; inodo LBA17 `boot.txt`, size=7, start_lba=25, used=1; LBA25 `boot=3\n`.

## Verificación
```bash
python3 infrastructure/scripts/build_ferros.py --release   # OK
python3 infrastructure/scripts/build_ferros.py             # OK
python3 -m unittest discover -s ferros/tests
# 43 tests OK (39 previos + 4)
```
Gate tras integración: **8/8 PASS, 53,92 s** con 163/43/6/166 y 6/6 QEMU. Host mock cubre formato/checksum/layout/create/write/read/delete/contador/errores/llenado/corrupción/sin ATA.

## Límites
- 8 archivos, 1 bloque de 512 B, sin directorios/journaling/caché/atomicidad; checksum solo del superbloque; heap sin free; solo QEMU PIIX IDE. Decisión: ADR-027.
