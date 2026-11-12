> **Informe histórico de TASK-907** (ejecución de la ronda anterior; la puerta actual tiene 8 pasos y conteos 94/34/6/77). Estado vigente: `docs/quality.md`, `agents/STATE.md` y `infrastructure/scripts/verify_all.py`.

# TASK-907 — Evidencia: puerta de verificación y madurez (Hito 10)

Fecha: 2026-11-11.

## Entregado
- `infrastructure/scripts/verify_all.py`: 7 pasos secuenciales con timeout, aborta al primer fallo, `--quick` (sin QEMU ni benchmark) y `--full` (6 arranques QEMU).
- `docs/quality.md`: niveles de madurez por subsistema, evidencia enlazada, puertas, modos y límites explícitos; declara que **ningún subsistema es Estable ni Optimizado**.

## Ejecución real
```bash
python3 infrastructure/scripts/verify_all.py --quick
# 1–4 y 7 PASS; omitidos 5 y 6; TOTAL 23,99 s; Resultado OK

python3 infrastructure/scripts/verify_all.py
# 1–7 PASS; QEMU 2 arranques; benchmark rápido; TOTAL 30,84 s; Resultado OK

python3 infrastructure/scripts/verify_all.py --full
# 1–7 PASS; QEMU 6 arranques (3 debug + 3 release, estado 33, writes=18); TOTAL 32,45 s; Resultado OK
```
| # | Paso | Estado | Duración |
|---|---|---|---|
| 1 | Compilador build release | PASS | 0,03 s |
| 2 | Compilador tests (57) | PASS | 1,37 s |
| 3 | Ferros tests (34) | PASS | 20,32 s |
| 4 | Benchmarks tests (6) | PASS | 2,07 s |
| 5 | QEMU (2 por defecto; `--full` 6) | PASS | 2,08 s / 3,99 s |
| 6 | Benchmark rápido | PASS | 4,71 s |
| 7 | Selfhost (28) | PASS | 0,43 s |

La puerta valida además los conteos esperados (71/34/6/39) y el paso 7 es obligatorio; últimas ejecuciones: `--full` 7/7 en 33,11–33,46 s y `stress.py --quick` PASS en 23,83–23,86 s.

## Límites
- La puerta mide regresión funcional, no estrés ni estabilidad prolongada.
- QEMU TCG, sin hardware físico/KVM/UEFI; sin SMP, persistencia, IPC ni SYSCALL.
- Sin `perf`; benchmarks de 4 cargas enteras.
- No es CI externa: es una puerta local reproducible; el pipeline remoto queda pendiente.
