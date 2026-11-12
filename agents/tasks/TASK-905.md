# TASK-905: Estrés y fuzzing diferencial (Hito 10)

**Agente**: 14/13
**Estado**: COMPLETADA
**Resultado**: `stress.py --quick` 23,6 s y campaña completa 47,7 s verdes; 6/6 QEMU, fuzz parser/lexer sin discrepancias no toleradas.
**Dependencias**: TASK-703, TASK-902, TASK-907
**Archivos (propiedad exclusiva)**: `infrastructure/scripts/stress.py` (nuevo), `docs/stability.md` (nuevo)

## Objetivo
Ir más allá de la regresión funcional con evidencia de estabilidad: arranques QEMU repetidos con distintos guiones, repetición de suites y fuzzing diferencial de los componentes self-hosted.

## Contrato
- `stress.py` (sin shell, cwd raíz, timeouts, tempfiles):
  1. N arranques QEMU alternando perfiles con guiones válidos (`--boots`, por defecto 6): default, sin entrada, comandos inválidos; valida estado 33, stderr vacío, ausencia de PANIC y el marcador/serie esperada según el guion (para default usa el runner; para otros valida propiedades, no serie exacta).
  2. Repite la suite de Ferros `--rounds` (por defecto 2) y la de selfhost (2).
  3. Fuzzing diferencial: genera expresiones aleatorias (semilla fija, `--fuzz-cases`) y las pasa por el evaluador Zen (`zen/selfhost/parser.zen` + driver) comparando con la referencia Python del test existente; y fuentes mutadas para el lexer comparando contadores con `zen lex`, tolerando solo discrepancias documentadas.
  4. Resumen con PASS/FAIL, tiempos y rutas de logs; exit ≠0 al primer fallo.
- `docs/stability.md`: qué demuestra (repetición, entradas diversas, fuzz acotado) y qué NO (hardware físico, KVM, SMP, persistencia, campañas largas, sin .git/CI).
- No editar tests existentes, compilador, kernel ni otros docs.

## Aceptación
- `python3 infrastructure/scripts/stress.py --quick` verde en <60 s (2 boots, 1 ronda, pocos casos de fuzz).
- `python3 infrastructure/scripts/stress.py` verde (6 boots, 2 rondas, fuzz por defecto) y evidencia de resultados.
