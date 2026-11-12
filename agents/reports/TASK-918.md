# TASK-918 — Evidencia: workflow de CI remoto (no ejecutado en GitHub)

Fecha: 2026-11-12.

## Entregado
| Archivo | Contenido |
|---|---|
| `.github/workflows/ci.yml` | `ci-remoto`: push main / PR / manual; ubuntu-24.04, timeout 45 min, checkout, setup-python 3.12, validación del workflow, rust toolchain, GCC/QEMU, cache Cargo, `cargo fetch --locked`, `ci_matrix.py --quick` en PR y `--full` en main/manual, artefactos JSON/logs; sin secrets |
| `infrastructure/scripts/check_ci_workflow.py` | 44 comprobaciones estructurales/coherencia, parser propio o PyYAML, exit 0/1/2; pruebas negativas |
| `docs/ci-remote.md` | Requisitos, diferencias local/remoto, límites y validación |

## Verificación
```bash
python3 infrastructure/scripts/check_ci_workflow.py
# Comprobaciones: 44 (44 PASS, 0 FALLO) — PASS
```
YAML validado con `yaml`/`js-yaml` del checkout DSH; pruebas negativas (sin runs-on, sin GCC/QEMU, quick sin if, quick+full juntos, artefacto en repo, ruta inexistente, YAML mal indentado, `pull_request_target`, permissions write, token hardcodeado, doc sin atestación) → exit 1; `--backend yaml` sin PyYAML y `--root` inexistente → exit 2.

## Límites
- **No se ha ejecutado en GitHub**: sin `.git`/remoto, sin push/PR/artefactos reales; evidencia solo estructural/local.
- No es atestación; `ubuntu-24.04`, `@v4/@v5` y Rust stable son referencias móviles; `main` es una suposición.
- PyYAML no está en el host; rama PyYAML ejercitada con stub, no real. GCC/QEMU del runner diferirán del host.
- Integración con TASK-911 (`ci_matrix.py`); el workflow reproduce la matriz local, no la sustituye.
