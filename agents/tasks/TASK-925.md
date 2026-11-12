# TASK-925: CLI mínima de compilador Zen escrito en Zen

**Agente**: 02 Frontend Zen / 03 Backend Zen
**Estado**: COMPLETADA
**Prioridad**: ALTA
**Dependencias**: [TASK-902K]
**Archivos**: [zen/selfhost/, zen/selfhost/tests/, docs/zen/selfhost.md, agents/reports/TASK-925.md]

## Objetivo
Integrar componentes existentes en un ejecutable Zen que acepte un programa fuente de un subconjunto definido, emita C11, y valide el resultado contra el compilador Rust.

## Criterios de aceptación
- [x] Una CLI procesa al menos un archivo Zen real de extremo a extremo.
- [x] El C emitido compila y ejecuta con la salida esperada.
- [x] Comparación automatizada con el compilador Rust para casos positivos y negativos del subconjunto.
- [x] Límites claros, sin declarar autohosting completo; revisión cruzada independiente.

## Evidencia requerida
Diff, comandos, salidas, métricas, riesgos y revisión en informe.
