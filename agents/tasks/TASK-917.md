# TASK-917: Campaña de estabilidad ampliada (Hito 10)

**Agente**: 14/17
**Estado**: COMPLETADA
**Resultado**: 10 rondas quick + 3 full + gate full + stress completo, todo PASS sobre corte estable; 68 arranques QEMU estado 33, sin flakes; informe `agents/reports/TASK-917.md`.
**Dependencias**: TASK-913
**Archivos (propiedad exclusiva)**: `agents/reports/TASK-917.md` (nuevo)

## Objetivo
Evidencia repetida para Hito 10: campaña ampliada (10 rondas quick + 3 full) sobre el árbol actual, con resultados reales, sin cambiar código ni scripts.

## Contrato
- Ejecuta, con timestamps:
  1. `python3 infrastructure/scripts/stability_campaign.py --rounds 10 --json /tmp/campaign-10.json`
  2. `python3 infrastructure/scripts/stability_campaign.py --rounds 3 --mode full --json /tmp/campaign-full-3.json`
  3. `python3 infrastructure/scripts/verify_all.py --full` (estado final del árbol).
  4. `python3 infrastructure/scripts/stress.py` completo.
- Registra en `agents/reports/TASK-917.md`: comandos exactos, resultados PASS/FAIL, tiempos, rondas, boots, suites, fuzz, estado 33, enlaces a logs si quedan en /tmp; conclusión honesta sobre estabilidad (qué respalda y qué no; no promover a Estable automáticamente).
- Si el árbol cambia durante la campaña (otra tarea en curso), documenta el corte y repite las partes afectadas si es viable.
- No edites código, tests, scripts, gate, docs de calidad ni STATE.

## Aceptación
- Informe con las ejecuciones reales (no inventadas) y un veredicto explícito de estabilidad acotada.
- Si alguna campaña falla, se documenta con el log y no se afirma PASS.
