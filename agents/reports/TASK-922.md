# TASK-922 — Git y CI reproducible

Fecha: 2026-11-12. Responsable: agente 00. Estado: en progreso; ejecución remota pendiente.

## Cambios

- Se inicializó Git local en `main` y se creó el commit base `e7737a6` (`Baseline ZenFerros before next milestones`), con 690 archivos fuente/documentación. No se recuperó historial anterior.
- Se actualizaron las afirmaciones operativas sobre Git en la documentación y en los límites de `ci_matrix.py`.
- El validador del workflow ahora exige que el documento explique el estado del remoto y de la ejecución, en vez de una ausencia de Git ya resuelta.

## Comandos y resultados

| Comando | Resultado |
|---|---|
| `git init -b main` | OK, repositorio local inicializado |
| `git add -A` y `git commit -m 'Baseline ZenFerros before next milestones'` | OK, `e7737a6`, 690 archivos |
| `git status --short --branch` | `## main` tras el commit |
| `git log -1 --format='%h %s'` | `e7737a6 Baseline ZenFerros before next milestones` |
| `git remote -v` | Inicialmente sin remoto; después `origin` apuntó a la URL indicada por el usuario |
| `python3 infrastructure/scripts/check_ci_workflow.py` | 44/44 PASS tras el ajuste documental |
| `git diff --check` | PASS, sin errores de espacios |
| `python3 infrastructure/scripts/ci_matrix.py --quick --json /tmp/zenferros-task922-ci.json` | 4/4 PASS, 1m 26,5 s |
| `git ls-remote https://github.com/ferrberr/ZenFerros` | Código 0, sin refs antes de publicar |
| `python3 infrastructure/scripts/verify_all.py --full` tras integrar TASK-923/924/925 | 8/8 PASS, 59,63 s; 163/45/6/174 = 388 pruebas; 6 QEMU; reproducibilidad PASS |

Logs de la matriz: `/tmp/zenferros-ci-jhkjdn67`. JSON: `/tmp/zenferros-task922-ci.json`. Logs del gate integrado: `/tmp/zenferros-verify-c9snl2ng`.

## Riesgos y pendientes

- Git identifica solo este corte y cambios posteriores, no los commits anteriores citados en informes históricos.
- El usuario indicó `https://github.com/ferrberr/ZenFerros`; `git ls-remote` no devolvió refs y se configuró como `origin`. Hasta comprobar un run de Actions no se puede demostrar el CI remoto.
- La matriz local usa este host y su toolchain; una ejecución remota debe comprobarse por separado.
