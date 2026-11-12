# TASK-913: Campaña de estabilidad acotada (Hito 10)

**Agente**: 14/17
**Estado**: COMPLETADA
**Resultado**: campaña por rondas (`--rounds`, quick/full), JSON schema v1, parada ante fallo; 5 rondas quick PASS (171,9 s), 2 full PASS (222,0 s); Lead: 1 ronda PASS 32,11 s.
**Dependencias**: TASK-905, TASK-911
**Archivos (propiedad exclusiva)**: `infrastructure/scripts/stability_campaign.py` (nuevo), `docs/stability-campaign.md` (nuevo)

## Objetivo
Evidencia de estabilidad **repetida** más allá de una ejecución: N rondas de estrés (y opcionalmente puerta/QEMU) con resumen JSON, parada ante el primer fallo y registro de tiempos.

## Contrato
- `stability_campaign.py` (Python3, sin shell, cwd raíz, tempdirs, timeouts):
  - `--rounds N` (por defecto 5), `--mode quick|full` (quick = stress --quick; full = stress + verify_all --full por ronda), `--json RUTA`.
  - Por ronda: ejecuta stress (y gate en full), registra estado/duración y extrae métricas (boots PASS, suites, fuzz) del summary JSON de stress si existe; para ante el primer fallo con resumen parcial.
  - Verifica que los 6 arranques QEMU de gate full terminan 33 en modo full; en quick usa stress.
  - Resumen tabla + JSON (`schema`, `rounds`, `results`, `totals`, `warnings`); exit ≠0 si falla alguna ronda.
- `docs/stability-campaign.md`: qué mide, cómo ejecutar, tiempos, qué NO demuestra (no certificación, host compartido, semilla aleatoria, sin inyección de fallos) y relación con `docs/stability.md`.
- No editar código, tests, gate, stress ni otros docs.

## Aceptación
- `python3 infrastructure/scripts/stability_campaign.py --rounds 5` PASS y `--rounds 2 --mode full` PASS en este host (documentar tiempos reales).
- JSON válido con resultados por ronda; fallo simulado (p. ej. ronda forzada) manejado.
- Informe: tiempos, métricas, límites y evidencias.
