# TASK-916: Mini-FS persistente real sobre ATA (Ferros)

**Agente**: 11/10
**Estado**: COMPLETADA
**Resultado**: mini-FS persistente ZENFS01 con archivos; BOOT 1/2/3; 43 tests Ferros.
**Dependencias**: TASK-914, TASK-701
**Archivos (propiedad exclusiva)**: `ferros/kernel/storage_fs.zen` (nuevo), `ferros/kernel/main.zen`, `infrastructure/scripts/build_ferros.py`, `infrastructure/scripts/boot_ferros.py`, `ferros/tests/test_pfs.py` (nuevo), `ferros/tests/test_boot.py`, `ferros/tests/test_shell.py`, `docs/ferros/persistence.md`

## Objetivo
Pasar de un contador a un **mini-FS persistente real**: archivos con nombre, metadatos y datos en disco, que sobreviven entre arranques, con evidencia QEMU de dos arranques y tests host.

## Contrato
- Layout en el disco (independiente del contador TASK-914, que usa el sector 0):
  - LBA 16: superbloque `ZENFS01` + versión + nº inodos (u32) + checksum simple (p. ej. FNV-1a32 del superbloque).
  - LBA 17–24: 8 inodos de 64 B: `name[24]` NUL, `size u64`, `start_lba u32`, `used u8`; resto reservado.
  - LBA 25+: datos; **1 bloque por archivo** (≤512 B).
- API: `pfs_boot()`, `pfs_list()->u32`, `pfs_find(name)->i64`, `pfs_create(name)->i64`, `pfs_write(name,src,len)->i64`, `pfs_read(name,dst,max)->i64`, `pfs_delete(name)->i64`; validación de nombres (1–23 ASCII, sin `/`), tamaño ≤512, sin duplicados; errores negativos (-1 args, -2 sin ATA, -3 corrupto, -4 lleno, -5 ENOENT).
- `pfs_boot()`: valida magic+checksum; si no, formatea. Luego asegura `boot.txt`: si no existe lo crea con `boot=1\n`; si existe lee el contador, lo incrementa y reescribe. Imprime **antes del shell** `PFS: BOOT <n> FILES=<n>`; cualquier fallo → `PFS: UNAVAILABLE` y sigue sin panic. Mantén la línea `PERSIST: BOOT <n>` existente.
- Integración: `main.zen` llama `storage_boot()` y `pfs_boot()`; runner/transcripción incluyen la línea PFS; `writes=18` e hitos 1–8 intactos.
- `test_pfs.py`: host con el mock ATA existente (superbloque/inodos/checksums, create/write/read/delete, nombre inválido, lleno, corrupto) + QEMU **tres arranques** con el mismo disco: `PFS: BOOT 1`, `BOOT 2`, `BOOT 3`, `FILES=1`, status 33, sin PANIC; sin disco → UNAVAILABLE.
- `docs/ferros/persistence.md`: layout del FS, API, evolución desde el contador, límites (1 bloque/archivo, 8 archivos, sin directorios/journaling), pruebas.

## Aceptación
```bash
python3 infrastructure/scripts/build_ferros.py --release
python3 infrastructure/scripts/build_ferros.py
python3 -m unittest discover -s ferros/tests
```
- Todos los tests Ferros verdes (documenta total nuevo); QEMU estado 33; tres arranques BOOT 1/2/3 con el mismo disco; `writes=18`, `HITO 7 OK`.
- No toques compilador, benchmarks, selfhost, verify_all.py ni otros docs.
- Informe: layout, API, evidencia, comandos, límites/desviaciones.
