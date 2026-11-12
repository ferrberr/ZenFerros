# TASK-929: Cortes, QEMU e integración ZENFS02

**Agente**: 13 Virtualización/QA y 00 Orquestador
**Estado**: EN_PROGRESO
**Prioridad**: ALTA
**Dependencias**: [TASK-926, TASK-927, TASK-928]
**Archivos**: [ferros/tests/test_pfs.py, ferros/tests/test_pfs_vfs.py, infrastructure/scripts/verify_all.py, agents/reports/TASK-929.md, ARCHITECTURE.md, ROADMAP.md, agents/STATE.md]

## Objetivo
Demostrar recuperación ante cortes simulados, persistencia desde CPL3 y ausencia de regresiones.

## Criterios de aceptación
- [ ] Migración v1 con bytes y contador conservados durante dos reinicios y todos los cortes relevantes.
- [ ] Mock ATA cubre cortes y rasgados de datos, tabla, raíz y marca; nunca se leen bytes mezclados.
- [ ] QEMU debug/release crea y reemplaza con persistencia, y cubre 0/512/513 B.
- [ ] Pasan aislamiento, arranque sin disco, puerta local completa y CI del commit publicado.

## Pruebas necesarias y resultado esperado
Actualizar conteos de verify_all.py; registrar diff, comandos, salidas, métricas y riesgos. Revisar cruzadamente almacenamiento y syscalls antes de integrar.
