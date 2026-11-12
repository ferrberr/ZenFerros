# TASK-907: Puerta de verificación única y madurez (Fase 9)

**Agente**: 13/17
**Estado**: COMPLETADA
**Resultado**: `verify_all.py` (pasos 1–7) verde en quick y completa (30,8 s), `docs/quality.md` con madurez y límites.
**Dependencias**: TASK-801, TASK-703
**Archivos (propiedad exclusiva)**: `infrastructure/scripts/verify_all.py`, `docs/quality.md`

## Objetivo
Un comando único que ejecute todas las puertas de calidad del proyecto y un documento de madurez (Hito 10) que declare qué está verificado y qué no.

## Contrato
- `verify_all.py`: pasos secuenciales con timeout, salida clara y código de salida ≠0 al primer fallo:
  1. compilador release (`cargo build --release`) y `cargo test`;
  2. `python3 -m unittest discover -s ferros/tests`;
  3. `python3 -m unittest discover -s benchmarks/tests`;
  4. `python3 infrastructure/scripts/boot_ferros.py --all --repeat 1` (o 3 con `--full`);
  5. benchmark rápido `python3 benchmarks/scripts/bench.py --reps 3 --warmup 1 --json /tmp/... --md /tmp/...`;
  6. resumen final con tiempos y rutas de logs; `--quick` omite QEMU y bench.
- `docs/quality.md`: niveles de madurez por subsistema con evidencia (enlaces a informes), qué NO está verificado (hardware, SMP, persistencia, self-hosting completo) y cómo reproducir cada puerta.
- No editar código de compilador/kernel/tests ni otros docs.

## Aceptación
- `python3 infrastructure/scripts/verify_all.py --quick` verde y reproducible.
- `--full` verde (QEMU 6 arranques) en este host.
- Informe con comandos, tiempos y limitaciones.
