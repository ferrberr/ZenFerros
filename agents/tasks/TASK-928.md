# TASK-928: Creación desde CPL3

**Agente**: 12 Userspace
**Estado**: EN_PROGRESO
**Prioridad**: ALTA
**Dependencias**: [TASK-927 (API de commit)]
**Archivos**: [ferros/kernel/vfs.zen, ferros/kernel/userspace.zen, ferros/user/main.zen, infrastructure/scripts/boot_ferros.py, docs/ferros/shell.md, agents/reports/TASK-928.md]

## Objetivo
Añadir open flags=1 con descriptor pendiente y hacer que `put` cree o reemplace.

## Criterios de aceptación
- [ ] flags=0 conserva la semántica previa; flags=1 crea descriptor pendiente para nombre nuevo.
- [ ] write confirma nombre y bytes en un commit; close sin write descarta el pendiente.
- [ ] `put` usa flags=1; help/transcripción se actualizan; límites 0/512/513 B y boot.txt se respetan.

## Pruebas necesarias y resultado esperado
Pruebas de VFS/syscalls y QEMU de TASK-929; revisión independiente de un agente distinto. Informe con diff, comandos, salidas, métricas y riesgos.
