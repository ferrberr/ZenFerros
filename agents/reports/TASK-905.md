# TASK-905 — Evidencia: estrés y fuzzing diferencial (Hito 10)

Fecha: 2026-11-11.

## Entregado
- `infrastructure/scripts/stress.py`: campañas de arranques QEMU con guiones distintos, rondas repetidas de Ferros y selfhost, y fuzz diferencial de parser y lexer contra referencias.
- `docs/stability.md`: alcance, tolerancias, límites y reproducción.

## Ejecución real
| Comando | Resultado | Tiempo |
|---|---|---:|
| `python3 infrastructure/scripts/stress.py --quick` | **PASS** | **23,6 s** |
| `python3 infrastructure/scripts/stress.py` | **PASS** | **50,5 s** |

Campaña completa: 6 arranques QEMU (debug/release alternados; default, sin entrada, comandos inválidos) **6/6 PASS status 33**, stderr vacío, sin PANIC; Ferros ×2 rondas (34 tests/ronda) OK; selfhost ×2 rondas OK (39 tests/ronda); fuzz parser 200 expresiones (100 válidas/100 error) sin discrepancias; fuzz lexer 200 mutaciones (161 comparadas, 38 omitidas por fuente inválida para `zen lex`, 1 tolerada UTF-8) sin discrepancias no toleradas.
`--quick`: 2 boots, 1 ronda, 20 casos por fuzz, PASS en 23,6 s.
Rutas de fallo verificadas: QEMU inexistente → exit 1 sin seguir; `--boots 0` → exit 2.

## Límites
- QEMU TCG, `-smp 1`, sin KVM/hardware físico, sin persistencia.
- Campaña acotada (6 boots, 2 rondas, 200 casos): no es una campaña de estabilidad prolongada ni fuzzing guiado por cobertura.
- Sin auditoría de seguridad formal, sin self-hosting completo, sin CI remoto ni `.git`.
- La tolerancia UTF-8 (char multibyte) está acotada y registrada; fuentes ASCII deben coincidir siempre.
- No declara ningún subsistema Estable u Optimizado.
