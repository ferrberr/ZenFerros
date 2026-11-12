# TASK-927: Almacenamiento y migración ZENFS02

**Agente**: 11 Filesystems
**Estado**: EN_PROGRESO
**Prioridad**: ALTA
**Dependencias**: [TASK-926]
**Archivos**: [ferros/kernel/storage_fs.zen, agents/reports/TASK-927.md]

## Objetivo
Implementar montaje, migración v1→v2 y creación/reemplazo copy-on-write con confirmación por flush.

## Criterios de aceptación
- [ ] Seleccionar la generación válida más reciente y fallar cerrado ante corrupción reconocible.
- [ ] Migrar v1 sin alterar LBA 16–32 y recuperar tras cada corte.
- [ ] Escribir datos, tabla y raíz alternativa en ese orden con flush entre etapas; caché actualizada solo tras commit.
- [ ] Mantener ocho archivos de hasta 512 B y boot.txt protegido; invalidar caché ante resultado incierto.

## Pruebas necesarias y resultado esperado
Mock ATA, cortes y sectores rasgados de TASK-929; revisión independiente de un agente distinto. Informe con diff, comandos, salidas, métricas y riesgos.
