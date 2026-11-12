# TASK-902G — Evidencia: typechecker selfhost

Fecha: 2026-11-11. Séptimo componente del frontend en Zen.

## Entregado
| Archivo | Contenido |
|---|---|
| `zen/selfhost/typecheck.zen` | Typechecker freestanding u64/bool: scanner, parser iterativo, tabla de scopes y comprobación de tipos |
| `zen/selfhost/typecheck_driver.c` | Driver: `status= checked= errors= hash=` |
| `zen/selfhost/tests/test_selfhost_typecheck.py` | 16 tests contra typechecker de referencia propio en Python |

## Lenguaje y reglas
- Sentencias `let`, asignación, `print`, `if/else`, `while`; expresiones con enteros, variables, aritmética u64, comparaciones, `&& || !`, paréntesis.
- Tipos `u64`/`bool`: `let` infiere; asignación mismo tipo; condición bool; aritmética u64; comparaciones mismo tipo→bool; `print` u64/bool; no hay literales bool.
- Scopes por bloque (shadowing permitido; redeclarar en el mismo bloque es error); asignación a variable externa permitida con su tipo.
- Estados: 0 ok, 1 sintaxis, 2 tipos, 3 variable no definida, 4 límites; el primer error detiene y deja un resumen FNV-1a32 estable en `out[3]`.
- Límites: 512 nodos, profundidad 32, 32 variables, 1024 tokens; sin libc ni estado global.

## Verificación
```bash
python3 -m unittest discover -s zen/selfhost/tests -p 'test_selfhost_typecheck.py' -v
# 16 tests OK
python3 -m unittest discover -s zen/selfhost/tests
# 93 tests OK (77 previos + 16)
```
Stack: 34,2 KiB (objdump; *sub $0x88d8*), por encima de los 32 KiB de una tarea Ferros; es un componente de host hasta que se reduzca. Cobertura: inferencia u64/bool, scopes/shadowing, asignación incompatible, condición no bool, aritmética con bool, comparación de tipos distintos, variable no definida, sintaxis, límites y determinismo; objeto freestanding sin imports (`nm -u` vacío).

## Límites
- Solo u64/bool; sin funciones, arrays, strings ni genéricos; un único error reportado (no recuperación); sin flujo de tipos sofisticado (todo es comprobación local por sentencia).
- No genera código ni interpreta: solo verifica tipos.

## Relevancia
El frontend en Zen ya incluye comprobación de tipos, un paso esencial hacia un compilador autohospedado; se apoya en la misma infraestructura de arrays fijos que los intérpretes.
