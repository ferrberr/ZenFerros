# TASK-919: ZENFS01 visible desde el VFS y el shell (Ferros)

**Agente**: 11/12
**Estado**: COMPLETADA
**Resultado**: PFS ZENFS01 visible en VFS/shell read-only; Ferros 44; boot=1/2 por cat; ADR-028.
**Dependencias**: TASK-916, TASK-701, TASK-703
**Archivos (propiedad exclusiva)**: `ferros/kernel/vfs.zen`, `ferros/kernel/storage_fs.zen`, `ferros/kernel/userspace.zen`, `ferros/kernel/main.zen`, `ferros/user/main.zen`, `infrastructure/scripts/boot_ferros.py`, `ferros/tests/test_vfs.py`, `ferros/tests/test_shell.py`, `ferros/tests/test_boot.py`, `ferros/tests/test_pfs_vfs.py` (nuevo), `docs/ferros/filesystem.md`, `docs/ferros/shell.md`, `docs/ferros/persistence.md`

## Objetivo
Hacer que los archivos persistentes de ZENFS01 sean visibles y legibles desde el VFS y el shell, sin syscalls nuevas: `ls` enumera `boot.txt` y `cat boot.txt` lo lee (read-only), preservando RAMFS y los hitos 1–8.

## Contrato
- VFS: `vfs_lookup/open` buscan primero RAMFS; si ENOENT, consultan PFS (read-only). Marca interna de fd PFS (p. ej. inodo centinela y nombre). `vfs_read` de un fd PFS copia desde `pfs_read` al buffer del usuario (validado) sin tocar RAMFS. `vfs_write` a PFS → EACCES/EROFS.
- `vfs_readdir` enumera RAMFS (hello.zen, notes.txt) **más** los nombres de PFS (boot.txt, …) separados por NUL; orden estable documentado.
- `vfs_self_test` añade comprobaciones: PFS visible, read de boot.txt, write rechazado, cierre, y que RAMFS sigue intacto.
- Shell: `ls` muestra los tres nombres; `cat boot.txt` funciona. El guion de aceptación por defecto se actualiza SOLO con la nueva salida de `ls` (sin comandos nuevos) y **`writes` debe seguir 18**; `tests/test_boot.py`/`test_shell.py` actualizados.
- `test_pfs.py`/`test_pfs_vfs.py`: QEMU con el mismo disco dos arranques y entrada `cat boot.txt` en ambos: primer arranque `boot=1`, segundo `boot=2` (la línea PFS ya lo confirma); `ls` incluye boot.txt; status 33, sin PANIC, `HITO 7 OK`.
- Si PFS no está disponible (sin disco), el VFS/shell se comportan como antes (`PFS: UNAVAILABLE`), sin panic.
- Docs: filesystem/shell/persistence reflejan la integración y límites (read-only, sin montaje real/journaling, 8 archivos).
- No toques compilador, benchmarks, selfhost, verify_all.py ni otros docs.

## Aceptación
```bash
python3 infrastructure/scripts/build_ferros.py --release
python3 infrastructure/scripts/build_ferros.py
python3 -m unittest discover -s ferros/tests
```
- Todos los tests Ferros verdes (documenta total nuevo); 6/6 QEMU estado 33 con la nueva transcripción; dos arranques mismo disco con `boot=1`/`boot=2` leídos por `cat`; writes=18.
- Informe: diseño, cambios VFS/shell, evidencia QEMU, comandos, límites/desviaciones.
