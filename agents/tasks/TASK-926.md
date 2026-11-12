# TASK-926: Contrato de disco ZENFS02

**Agente**: 06 Arquitecto Kernel Ferros
**Estado**: COMPLETADA
**Prioridad**: ALTA
**Dependencias**: [TASK-924]
**Archivos**: [docs/ferros/persistence.md, agents/decisions/ADR-029.md, agents/reports/TASK-926.md]

## Objetivo
Fijar el formato de dos raíces ZENFS02, la selección de generaciones y la migración recuperable de ZENFS01.

## Criterios de aceptación
- [x] Especificar bytes y checksums de raíces, tablas, datos y marca en LBA 33–46; LBA 16–32 permanece intacto.
- [x] Definir estados de arranque y comportamiento ante cortes o corrupción reconocible.
- [x] Declarar el modelo de fallos y sus límites sin atribuir durabilidad a hardware real.

## Pruebas necesarias y resultado esperado
Revisión de coherencia con TASK-927/929; ningún estado parcialmente escrito debe exponer una raíz inválida. Informe con diff, comandos, métricas y riesgos.
