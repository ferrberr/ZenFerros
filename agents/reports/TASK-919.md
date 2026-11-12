# TASK-919 — Evidencia: ZENFS01 visible en VFS/shell

Fecha: 2026-11-12.

## Entregado
| Archivo | Cambio |
|---|---|
| `storage_fs.zen` | `pfs_disk_read_ptr` y `pfs_export` (instantánea read-only 8192 B) |
| `vfs.zen` | Fallback RAMFS→PFS, fd PFS, lectura, EROFS, readdir combinado, self-test ampliado |
| `main.zen` | Reserva/publica la instantánea tras `pfs_boot()` |
| `boot_ferros.py` | Transcripción con boot.txt |
| `test_pfs_vfs.py` | 2 arranques QEMU mismo disco: `cat boot.txt` → boot=1/2, `ls` con boot.txt |
| `test_vfs.py`, `test_boot.py`, `test_shell.py` | Cobertura del nuevo contrato |
| `docs/ferros/{filesystem,shell,persistence}.md` | Integración y límites |

## Evidencia
```bash
python3 infrastructure/scripts/build_ferros.py --release   # OK
python3 infrastructure/scripts/build_ferros.py             # OK
python3 -m unittest discover -s ferros/tests
# 44 tests OK (43 previos + 1)
python3 infrastructure/scripts/boot_ferros.py --all --repeat 3
# 6/6 QEMU estado 33, writes=18, HITO 7 OK
python3 -m unittest ferros.tests.test_pfs_vfs -v
# 2 arranques: boot=1, boot=2; ls con boot.txt; OK
```
Gate completo: **8/8 PASS, 54,71 s** con **163/44/6/166**, 6/6 QEMU y reproducibilidad.

## Límites
- Instantánea read-only (8×512 B) sin refresco si el disco cambia tras el arranque; sin escritura desde usuario (−30 EROFS), sin montaje real/journaling; +8192 B de heap sin free.
- `test_vfs.py` host compila sin PFS (cache no publicada) para preservar el contrato RAMFS.
- Decisión: ADR-028.
