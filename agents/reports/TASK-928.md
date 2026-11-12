# TASK-928 — Creación desde CPL3

Estado: COMPLETADA. Implementación integrada por /root a partir de la rama aislada revisada TASK-928; revisión cruzada independiente de /root/storage_recovery.

## Diff y resultado

`vfs_open_flags` acepta 0/1; un nombre nuevo con flag 1 reserva descriptor pendiente, que `close` descarta sin escritura. La primera `write` crea nombre y bytes por `pfs_commit_ptr`; la caché cambia solo tras éxito. Un fallo incierto enclava EIO hasta reinicio. `user_open` pasa flags y `put` usa 1. `help` y transcripción de aceptación incluyen `put`.

## Evidencia

- `python3 -m unittest ferros.tests.test_vfs ferros.tests.test_userspace` → 4/4 OK, 10,4 s.
- `python3 -m unittest ferros.tests.test_pfs_vfs ferros.tests.test_pfs.PfsGuestTests` → 4/4 OK, 13,1 s. Incluye debug/release, creación, reemplazo, dos reinicios, 0/512/513 B, flag inválido y cierre pendiente sin escritura.
- `python3 infrastructure/scripts/verify_all.py --full` → 8/8 PASS, 390 tests, 6/6 QEMU, 66,9 s.

Métrica: 16 descriptores compartidos RAMFS/PFS; 8 archivos PFS × 512 B. Riesgo: sin concurrencia entre escritores ni durabilidad física demostrada.
