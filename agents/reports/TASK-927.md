# TASK-927 — ZENFS02 storage and migration

Estado: REVISION. Autor: /root/storage_recovery; revisor independiente: /root.

## Cambios

- `ferros/kernel/storage_fs.zen`: sustituye la ruta v1 de escritura por ZENFS02 con dos raíces y tablas, nueve sectores de datos, checksum FNV32 de tabla/sectores/raíz, selección de generación válida y marca de activación.
- Migra ZENFS01 válido sin escribir en LBA 16–32; monta con recuperación de cortes. Un formato reconocible corrupto devuelve UNAVAILABLE.
- Commit copy-on-write: dato libre, flush, tabla alternativa, flush, raíz alternativa, flush. La caché VFS solo se publica fuera de este módulo tras éxito; fallo incierto la invalida.
- Mantiene API de lectura, exportación y operaciones de archivo de kernel. `boot.txt` se actualiza con el mismo commit COW y no admite escritura de usuario.

## Comandos y resultados

- `python3 infrastructure/scripts/build_ferros.py --release --zen /home/ferranfg/proyectos/ZenFerros/zen/compiler/target/release/zen` → `Built .../ferros-multiboot.elf` (0,96 s).
- `python3 -m unittest ferros.tests.test_zenfs02 ferros.tests.test_pfs.PfsHostTests` con pruebas TASK-929 copiadas temporalmente y symlink del compilador → 2 tests OK (1,22 s). El host test cubre creación, 0/512/513 B, reemplazo, cortes/rasgados en dato/tabla/raíz y en migración, corrupción y ATA ausente, en debug/release.
- `git diff --check` → sin errores.

## Métricas y riesgos

- 1 archivo de código modificado; formato fijo de 8 archivos × 512 B, 9 sectores de datos, scratch de 3584 B por montaje/operación de kernel. No hay durabilidad afirmada para hardware físico; depende de `ata_flush` y del modelo de fallos del mock.
- Falta integración QEMU y CI remoto, a cargo de TASK-929. El fallo de marcador en blanco antes de una raíz válida puede exigir intervención manual si el formato parcialmente escrito se reconoce como corrupto; la ruta de migración v1 sí reintenta sin alterar v1.
