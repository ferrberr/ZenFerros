# TASK-918: Workflow de CI remoto (Fase 9)

**Agente**: 17/15
**Estado**: COMPLETADA
**Resultado**: workflow `.github/workflows/ci.yml` + validador local 44 checks PASS + `docs/ci-remote.md`; no ejecutado en GitHub y así se declara.
**Dependencias**: TASK-911
**Archivos (propiedad exclusiva)**: `.github/workflows/ci.yml` (nuevo), `infrastructure/scripts/check_ci_workflow.py` (nuevo), `docs/ci-remote.md` (nuevo)

## Objetivo
Cerrar la parte "CI remoto" de Fase 9 con un workflow reproducible que use `ci_matrix.py`, validable localmente en estructura.

## Contrato
- `.github/workflows/ci.yml`: workflow de PR/push con checkout, toolchain (Rust/GCC/QEMU), cache de Cargo, `CARGO_HOME`, ejecución `python3 infrastructure/scripts/ci_matrix.py --quick` en PR y `--full` en main/manual, publicación del JSON de resumen como artefacto (sin secretos). Debe ser coherente con `docs/ci.md` y no afirmar que se ha ejecutado en remoto.
- `infrastructure/scripts/check_ci_workflow.py`: valida localmente estructura del YAML sin depender de red: claves requeridas (`name`, `on`, `jobs`), jobs con `runs-on`/`steps`, presencia de checkout/setup-python/ci_matrix, rutas existentes, que no haya secretos hardcodeados; exit ≠0 si falla. No usa PyYAML si no está disponible (parser mínimo/líneas o `yaml` si existe).
- `docs/ci-remote.md`: qué haría el workflow, requisitos, diferencias con la matriz local, límites (no ejecutado aquí, sin `.git`, no es atestación) y cómo validarlo localmente.
- No edites código, tests, gate, scripts existentes ni otros docs.

## Aceptación
```bash
python3 infrastructure/scripts/check_ci_workflow.py   # PASS
```
- Workflow/validador/doc coherentes; informe con comandos y límites (no afirmar ejecución remota).
