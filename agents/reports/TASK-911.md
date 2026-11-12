# TASK-911 — Evidencia: matriz de CI local

Fecha: 2026-11-12.

## Entregado
| Archivo | Contenido |
|---|---|
| `infrastructure/scripts/ci_matrix.py` | Matriz de verificación por modos (`--quick`, defecto, `--full`): cargo test debug/release, `verify_all`, `stress`, `repro_build`; timeouts, logs por paso, fallo temprano, resumen tabla + JSON |
| `docs/ci.md` | Matriz, tiempos observados, toolchain, límites y ejemplo de integración en CI externo |

## Modos
- `--quick`: cargo test release, `verify_all --quick`, `stress --quick`, `repro_build --quick` (4 pasos).
- defecto: añade cargo test debug, `verify_all` normal, `repro_build` completo (5 pasos).
- `--full`: añade `verify_all --full` y `stress` completo (5 pasos, ~2 min).

## Verificación
```bash
python3 infrastructure/scripts/ci_matrix.py --quick --json /tmp/ci-quick.json   # PASS 1m 05,8 s
python3 infrastructure/scripts/ci_matrix.py --full  --json /tmp/ci-full.json    # PASS 1m 54,3 s
```
JSON válido con `schema`, `mode`, `result`, `toolchain`, `matrix.steps`, `logs`, `limits`, `warnings` (validado con `python3 -m json.tool` en todos los modos). Fallo temprano probado sin cargo: paso 1 FAIL, 2–4 SKIP, exit 1 y `failed_step=1`; timeout sintético → FAIL con log; `--json` inválido → exit 2 controlado. Toolchain registrada: cc 16.2.1, ld 2.47, rustc 1.99.1, zen 0.1.0 release.

## Límites
- **No es CI remoto** ni contenedor/toolchain hermético: ejecuta en este host lo que ya verifican `quality.md`, `stability.md` y `reproducibility.md`.
- Los tiempos varían con el host/caché y no son un benchmark; otro runner puede diferir en versiones y resultados.
- No publica artefactos ni atestaciones firmadas; el JSON es evidencia de ejecución.
- Decisión: TASK-911 (no requiere ADR propio; compone puertas existentes).
