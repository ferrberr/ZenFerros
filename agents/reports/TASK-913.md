# TASK-913 — Evidencia: campaña de estabilidad repetida

Fecha: 2026-11-12.

## Entregado
| Archivo | Contenido |
|---|---|
| `infrastructure/scripts/stability_campaign.py` (980 líneas) | Campaña por rondas de `stress` (quick/full) y `verify_all --full` en modo full; timeouts, logs, parada ante fallo, tabla y JSON (`schema=zenferros.stability-campaign/v1`) |
| `docs/stability-campaign.md` | Alcance, uso, tiempos, JSON, límites y relación con `stability.md`/`quality.md` |

## Evidencia del worker
```bash
python3 infrastructure/scripts/stability_campaign.py --rounds 5
# PASS 171,9 s; 5/5 rondas; stress boots 10/10, suites 10/10; parser 100, lexer 100
python3 infrastructure/scripts/stability_campaign.py --rounds 2 --mode full
# PASS 222,0 s; 2 rondas de stress+gate; stress boots 12/12, gate 12/12 estado 33; suites 4/4
```
JSON validado (quick y full); `gate.source=gate-log:05-ferros.log`, `boots_pass/total=6/6`, `warnings=[]`. Fallo simulado con `QEMU` inexistente: exit 1, una ronda FAIL, parada y JSON parcial válido.

## Verificación del Lead
```bash
python3 infrastructure/scripts/stability_campaign.py --rounds 1 --json /tmp/campaign-lead.json
# PASS 32,11 s; stress boots 2/2, suites 2/2, fuzz 20/20; JSON schema válido
```

## Límites
- No es certificación ni cambia el nivel de madurez: host compartido, tiempos variables, semilla fija del corpus, sin inyección de fallos real (solo entorno QEMU) y rondas acotadas.
- QEMU TCG `-smp 1`; sin KVM/SMP/persistencia; sin CI remoto ni `.git`.
- No sustituye a `verify_all`/`stress`; los compone.
