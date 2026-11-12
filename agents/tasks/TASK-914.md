# TASK-914: Persistencia ATA PIO entre arranques (Ferros)

**Agente**: 10/11
**Estado**: COMPLETADA
**Resultado**: persistencia ATA PIO entre arranques (BOOT 1→2) con superbloque; Ferros 39 tests; gate 8/8.
**Dependencias**: TASK-703, TASK-701
**Archivos (propiedad exclusiva)**: `ferros/kernel/drivers/ata.zen` (nuevo), `ferros/kernel/storage.zen` (nuevo), `ferros/kernel/main.zen`, `infrastructure/scripts/build_ferros.py`, `infrastructure/scripts/boot_ferros.py`, `ferros/tests/test_persistence.py` (nuevo), `ferros/tests/test_boot.py`, `ferros/tests/test_shell.py`, `docs/ferros/persistence.md` (nuevo)

## Objetivo
Persistencia real entre arranques en QEMU: driver **ATA PIO** y un almacén mínimo que incrementa un contador en disco y lo muestra, sin romper los hitos 1–8.

## Contrato
- QEMU: `boot_ferros.py` acepta un disco raw opcional (`--disk RUTA` o parámetro `disk_image=`), crea uno temporal si no se da, y lo pasa como `-drive file=...,format=raw,if=ide,index=0` (o `-hda`). Por defecto sigue funcionando sin cambios visibles salvo las líneas PERSIST.
- `drivers/ata.zen`: ATA PIO primario (0x1F0–0x1F7/0x3F6): identify opcional; `ata_read_sector(lba, dst)->i64`, `ata_write_sector(lba, src)->i64` LBA28, polling BSY/DRQ con timeout, `ata_flush`; errores negativos.
- `storage.zen`: sector 0 superbloque mágico `ZENPERS1` + contador u64; `storage_boot()` lee el sector; si no hay magic formatea (contador=1) y si existe incrementa y reescribe; imprime una línea `PERSIST: BOOT <n>` (kernel, serial). Debe tolerar disco ausente/error sin panic (emite `PERSIST: UNAVAILABLE` y sigue).
- main.zen: inicializa almacenamiento antes del shell y emite la línea; el resto del flujo (writes=18, HITO 7 OK, shell) intacto.
- Tests: `test_persistence.py` arranca QEMU dos veces con el **mismo** disco y verifica `PERSIST: BOOT 1` y `PERSIST: BOOT 2` (estado 33, sin PANIC); primer arranque formatea, segundo incrementa. Ajusta runner/transcripción (expected messages incluyen PERSIST) y test_boot/test_shell si es necesario. Actualiza `writes` solo si cambia de verdad (no debe).
- `docs/ferros/persistence.md`: layout, driver, límites (una unidad, LBA28, sin IRQ, sin caché, sin FS real, volátil en RAM), cómo probarlo.

## Aceptación
```bash
python3 infrastructure/scripts/build_ferros.py --release
python3 infrastructure/scripts/build_ferros.py
python3 -m unittest discover -s ferros/tests
```
- Todos los tests Ferros verdes (nuevo total documentado); 6/6 QEMU estado 33 con la transcripción nueva; dos arranques con el mismo disco muestran BOOT 1 y BOOT 2.
- No toques compilador, benchmarks, selfhost, verify_all.py ni docs fuera de persistence.md.
- Informe: diseño, integración, evidencia QEMU (dos arranques), comandos, límites y desviaciones.
