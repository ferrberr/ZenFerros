# TASK-926 — Contrato ZENFS02

Estado: COMPLETADA. Arquitectura propuesta por /root/format_926 y contrastada con /root/storage_recovery; integración documental por /root.

## Diff y resultado

`agents/decisions/ADR-029.md` define offsets, sumas FNV-1a32, dos raíces y tablas, nueve sectores de datos, marca y estados de montaje. `docs/ferros/persistence.md` detalla migración, COW y límite de la garantía. LBA 16–32 permanece intacto.

## Evidencia

- Revisión cruzada de formato con el implementador de almacenamiento: coincidencia de offsets y orden de flush.
- `python3 infrastructure/scripts/verify_all.py --full` → 8/8 PASS, 390 tests, 6/6 QEMU, reproducibilidad PASS; 66,9 s. Logs `/tmp/zenferros-verify-lr1oy1f4`.
- `git diff --check` → sin errores en el cierre de TASK-929.

Riesgo: el modelo exige orden de `ata_flush`; no demuestra durabilidad en hardware físico. Métrica: 8 archivos de 512 B con un sector libre de nueve.
