# TASK-911: Matriz de CI local (Fase 9)

**Agente**: 17/13
**Estado**: COMPLETADA
**Resultado**: `ci_matrix.py` con modos quick/defecto/full, resumen JSON y logs; quick PASS 1m05,8 s, full PASS 1m54,3 s; `docs/ci.md` con matriz, tiempos, límites y ejemplo de CI externo.
**Dependencias**: TASK-907, TASK-908, TASK-905
**Archivos (propiedad exclusiva)**: `infrastructure/scripts/ci_matrix.py` (nuevo), `docs/ci.md` (nuevo)

## Objetivo
Un único comando reproducible de CI local que ejecute la matriz de verificación (perfiles, suites, gate, estrés y reproducibilidad) con resumen JSON y fallo temprano claro, sin CI remoto ni contenedores.

## Contrato
- `ci_matrix.py` (Python3, sin shell, cwd raíz, timeouts por paso, tempdirs; no escribe artefactos en el repo):
  - `--quick`: compilador release (cargo test release), `verify_all --quick`, `stress --quick`, `repro_build --quick`.
  - por defecto: añade compilador debug (cargo test debug), `verify_all` normal, `repro_build` completo; mantiene stress quick.
  - `--full`: añade `verify_all --full` y `stress` completo (puede tardar ~2-3 min; documentar).
  - Pasos con nombre, comando, duración, estado y log; resumen final tabla + JSON (`--json RUTA` opcional); exit ≠0 al primer fallo con resumen de lo ejecutado.
  - Verifica versiones de toolchain (cc, ld, rustc, zen) y las registra; no modifica código.
- `docs/ci.md`: matriz, comandos, tiempos observados, qué NO es (CI remoto, contenedores, otros hosts, atestación) y cómo integrarlo en un CI externo (ejemplo YAML genérico).
- No editar verify_all.py, stress.py, repro_build.py, código, tests ni otros docs.

## Aceptación
- `python3 infrastructure/scripts/ci_matrix.py --quick` PASS y `--full` PASS en este host.
- JSON válido; fallo simulado (p. ej. `--json` y ruta inválida) manejado.
- Informe: matriz, tiempos, límites y evidencias.
