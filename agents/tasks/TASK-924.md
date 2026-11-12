# TASK-924: Escritura persistente desde CPL3

**Agente**: 08 Kernel Memory / 11 Filesystems
**Estado**: EN_PROGRESO
**Prioridad**: ALTA
**Dependencias**: [TASK-916, TASK-919]
**Archivos**: [ferros/kernel/storage_fs.zen, ferros/kernel/vfs.zen, ferros/kernel/userspace.zen, ferros/user/main.zen, ferros/tests/test_pfs_vfs.py, ferros/tests/test_pfs.py, infrastructure/scripts/boot_ferros.py, docs/ferros/filesystem.md, agents/reports/TASK-924.md]

## Objetivo
Permitir escribir un archivo ZENFS01 desde CPL3 por VFS y comprobar contenido idéntico tras reiniciar QEMU con el mismo disco.

## Criterios de aceptación
- [ ] El contrato define tamaño, errores y fallo de escritura sin afirmar atomicidad inexistente.
- [ ] Una prueba real escribe desde CPL3 y lee el contenido tras reinicio.
- [ ] No retroceden aislamiento ni suites de Ferros.
- [ ] Revisión cruzada independiente antes de cierre.

## Evidencia requerida
Diff, comandos, salidas, métricas, riesgos y revisión en informe.
