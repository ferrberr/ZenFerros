# TASK-920: Release v0.1.1 y madurez post-corte (Fase 9/Hito 10)

**Agente**: 17/15
**Estado**: COMPLETADA
**Resultado**: release 0.1.1 (corte pre-919, 163/43/6/166) + madurez post-corte.
**Dependencias**: TASK-906, TASK-916, TASK-917, TASK-918, TASK-915, TASK-902K
**Archivos (propiedad exclusiva)**: `CHANGELOG.md`, `docs/release.md`, `docs/maturity.md`

## Objetivo
Cerrar el ciclo con una release **0.1.1** que incluya el trabajo posterior al corte 0.1.0 (slices, codegen structs, mini-FS, campaña ampliada, workflow CI remoto y —si TASK-919 termina— PFS en VFS), con hashes y conteos reales.

## Contrato
- Espera a que TASK-919 cierre o documenta el corte exacto: si TASK-919 no está integrada, 0.1.1 se corta antes de ella y se indica que PFS-en-VFS queda para 0.1.2.
- Actualiza `CHANGELOG.md`: nueva sección 0.1.1 con fecha, cambios (slices/ADR-026, TASK-902K, TASK-916/ADR-027, TASK-917 campaña, TASK-918 workflow), conteos reales, evidencia; mantén 0.1.0 como histórica.
- `docs/release.md`: corte 0.1.1, comandos, conteos (compilador/Ferros/benchmarks/selfhost), artefactos reproducibles con hashes **actuales** (`repro_build.py` completo), 6/6 QEMU, campaña, checklist; límites (CI remoto no ejecutado, FS read-only, sin self-hosting completo).
- `docs/maturity.md`: actualiza vigencia al corte 0.1.1 con evidencia real; mantén 0 Estable / 0 Optimizado salvo justificación explícita; añade filas mini-FS y (si aplica) PFS-VFS; sin sobreafirmar.
- Verifica enlaces internos de los tres documentos y que los conteos coinciden con `verify_all.py`/`cargo test`/ferros/selfhost del momento del corte.
- No edites código, tests, scripts, otros docs ni ADR.

## Aceptación
- Los tres documentos coherentes; `verify_all.py --full` PASS en el corte; informe con hashes, conteos, enlaces verificados y qué NO se demuestra.
- Si el árbol cambia durante la tarea, documenta el corte y repite lo afectado.
