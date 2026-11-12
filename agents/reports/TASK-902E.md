# TASK-902E — Evidencia: intérprete selfhost de sentencias

Fecha: 2026-11-11. Quinto componente del frontend/ejecución en Zen.

## Entregado
| Archivo | Contenido |
|---|---|
| `zen/selfhost/interp.zen` (936 líneas) | Scanner → tokens en arrays, parser iterativo → sentencias y expresiones RPN en arrays, ejecución con pilas explícitas; `pub fn zen_interp(source,length,out)` |
| `zen/selfhost/interp_driver.c` | Driver: `status= statements= hash= bytes=` |
| `zen/selfhost/tests/test_selfhost_interp.py` (771 líneas) | 16 tests: ≥30 programas contra un intérprete de referencia propio en Python, determinismo, límites, errores, `nm -u` vacío y fuente con arrays locales |

## Verificación
```bash
python3 -m unittest discover -s zen/selfhost/tests -p 'test_selfhost_interp.py' -v
# 16 tests OK
python3 -m unittest discover -s zen/selfhost/tests
# 55 tests OK (7 lexer + 7 parser + 14 AST + 11 tokens + 16 interp)
```
Cobertura: variables, asignación, `if/else`, `while`, comparaciones encadenadas,
precedencia, unario, div0/resto0, variable desconocida, errores de sintaxis,
límites de nodos/profundidad/variables/salida y conservación de salida previa.

## Límites
- Variables globales al programa (sin ámbitos anidados); enteros u64 envolventes; sin strings, arrays ni funciones.
- Límites fijos: 256 nodos, 32 de profundidad, 16 variables, 256 bytes impresos, 1024 tokens y **1.000.000 de pasos de ejecución** (estado 4; evita cuelgues por `while 1 {}`).
- Intérprete, no compilador; no genera código máquina.
- El driver C usa libc; el objeto Zen no.

## Relevancia
Primer componente en Zen que ejecuta un **lenguaje de sentencias** (scan+parse+AST+eval) y refuerza el Hito 9: la cadena de compilación/interpretación ya es realizable en el propio lenguaje. No es un lenguaje completo (sin funciones, strings, arrays de usuario). Limitación: el stack del intérprete medido con `-fstack-usage` es ~37,5 KB, mayor que los stacks de 32 KiB de Ferros; no está pensado para ejecutarse en una tarea de usuario actual.
