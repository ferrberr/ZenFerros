# TASK-929 — Recuperación e integración ZENFS02

Estado: EN_PROGRESO (CI remoto pendiente). Responsable: /root; almacenamiento revisado por /root y syscalls revisadas por /root/storage_recovery.

## Diff y pruebas

`ferros/tests/test_zenfs02.py` ejecuta código Zen real contra mock ATA con cortes y rasgados de datos, tabla, raíz y marca; comprueba fallos de flush, migración v1 con archivos/boot.txt y LBA 16–32 intactos, corrupción reconocible, ausencia de ATA, ocho archivos y tamaños 0/512/513 B. `test_pfs_vfs.py` verifica creación/reemplazo desde CPL3, lectura inmediata y tras reinicios con mismo disco en QEMU debug y release. `test_pfs.py` comprueba boot y contador v2. `verify_all.py` exige 47 tests Ferros.

- `python3 -m unittest ferros.tests.test_zenfs02` → 1/1 OK, 0,58 s; cada subcaso compila debug y release.
- `python3 -m unittest ferros.tests.test_pfs_vfs ferros.tests.test_pfs.PfsGuestTests` → 4/4 OK, 13,1 s.
- `python3 -m unittest discover -s ferros/tests` → 47/47 OK, 40,7 s.
- `python3 infrastructure/scripts/verify_all.py --full` → 8/8 PASS en 66,9 s: 163 compilador, 47 Ferros, 6 benchmarks, 174 selfhost = 390; 6/6 arranques QEMU de aceptación, reproducibilidad PASS. Logs `/tmp/zenferros-verify-lr1oy1f4`.

Riesgos: los tests simulan cortes y sectores incompletos sobre el mock; QEMU valida integración, no cortes físicos. La recuperación depende del orden de `ata_flush`. No se afirma durabilidad en hardware real. Métricas: 8 archivos/512 B, 9 sectores de datos, scratch 3584 B por montaje.
