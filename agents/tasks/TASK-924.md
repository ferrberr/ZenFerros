# TASK-924: Escritura persistente desde CPL3

**Agente**: 08 Kernel Memory / 11 Filesystems
**Estado**: COMPLETADA
**Prioridad**: ALTA
**Dependencias**: [TASK-916, TASK-919]
**Archivos**: [ferros/kernel/storage_fs.zen, ferros/kernel/vfs.zen, ferros/user/main.zen, ferros/tests/test_pfs_vfs.py, ferros/tests/test_pfs.py, ferros/tests/fixtures/user_mock.c, ferros/tests/fixtures/user_test_api.zen, ferros/tests/fixtures/vfs_test_support.zen, docs/ferros/filesystem.md, docs/ferros/persistence.md, agents/tasks/TASK-924.md, agents/reports/TASK-924.md]

## Objetivo
Permitir escribir un archivo ZENFS01 desde CPL3 por VFS y comprobar contenido idéntico tras reiniciar QEMU con el mismo disco.

## Criterios de aceptación
- [x] El contrato define tamaño, errores y fallo de escritura sin afirmar atomicidad inexistente.
- [x] Una prueba real escribe desde CPL3 y lee el contenido tras reinicio.
- [x] No retroceden aislamiento ni suites de Ferros.
- [x] Revisión cruzada independiente antes de cierre (orquestador /root).

## Evidencia requerida
Diff, comandos, salidas, métricas, riesgos y revisión en informe.

## Pruebas necesarias y resultado esperado

- Mock ATA real con 150 reemplazos, tamaño máximo/truncado, protección de
  boot.txt e inyección de fallos de datos, relectura de inodo, metadatos y flush.
- QEMU debug/release: CPL3 escribe 512 B, rechaza EFBIG/EFAULT/EINVAL sin
  mutación, reemplaza con texto, lee inmediatamente y tras reinicio del mismo disco.
- Suite Ferros completa mantiene aislamiento y negativos: 45 tests PASS.
- Resultado: reemplazo persistente de archivos existentes, hasta 512 B,
  con caché coherente tras éxito y sin afirmar atomicidad. Crear desde CPL3
  queda fuera del contrato aprobado por el orquestador.

## Evidencia

`agents/reports/TASK-924.md`. Código revisado independientemente por /root sin bloqueos e integrado en `main` antes de TASK-926.
