# TASK-914 — Evidencia: persistencia ATA PIO entre arranques

Fecha: 2026-11-12.

## Entregado
| Archivo | Cambio |
|---|---|
| `ferros/kernel/drivers/ata.zen` | Driver ATA PIO primario (LBA28, polling, timeout, read/write/flush) |
| `ferros/kernel/storage.zen` | Superbloque sector 0 (`ZENPERS1` + contador), formateo/incremento, `PERSIST: BOOT n` o UNAVAILABLE |
| `ferros/kernel/main.zen` | `storage_boot()` antes de userspace/shell |
| `infrastructure/scripts/build_ferros.py` | Unidades nuevas y `ata_io.S` generado (inw/outw) |
| `infrastructure/scripts/boot_ferros.py` | `disk_image=`/`--disk`, `-drive ... if=ide`, validación PERSIST |
| `ferros/tests/test_persistence.py` | 3 tests: driver/storage host, imagen temporal/explícita, dos arranques mismo disco |
| `ferros/tests/test_boot.py`, `test_shell.py` | Transcripción con PERSIST |
| `docs/ferros/persistence.md` | Diseño, layout, límites y comandos |

## Evidencia QEMU
```bash
python3 infrastructure/scripts/boot_ferros.py --release --repeat 2 --disk ferros/build/persistence-demo.img
# boot-01: status 33, PERSIST: BOOT 1, writes=18, HITO 7 OK
# boot-02: status 33, PERSIST: BOOT 2, writes=18, HITO 7 OK
xxd: 5a45 4e50 4552 5331 0200... = "ZENPERS1" + contador 2
```
Sin `-drive`: `PERSIST: UNAVAILABLE`, status 33, sin PANIC.

## Verificación
```bash
python3 infrastructure/scripts/build_ferros.py --release   # OK
python3 infrastructure/scripts/build_ferros.py             # OK
python3 -m unittest discover -s ferros/tests
# Ran 39 tests — OK (34 previos + 5)
```
Gate completo tras integración: **8/8 PASS, 47,03 s** con 151/39/6/147 y 6/6 QEMU estado 33.

## Límites
- Una unidad/canal, LBA28, 1 sector/operación, sin IRQ/DMA/caché/FS/particiones/checksum/atomicidad; validado en QEMU PIIX IDE, no hardware real/AHCI.
- `ata_io.S` es artefacto de build; no se versiona.
- Decisión: ADR-025.
