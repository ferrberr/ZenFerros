# TASK-902F — Evidencia: intérprete selfhost con funciones

Fecha: 2026-11-11. Sexto componente del frontend/ejecución en Zen.

## Entregado
| Archivo | Contenido |
|---|---|
| `zen/selfhost/interp_functions.zen` | Intérprete freestanding con definiciones `fn`, parámetros, `return`, llamadas y recursión acotada; `pub fn zen_interp_fns(source,length,out)` |
| `zen/selfhost/interp_functions_driver.c` | Driver: `status= statements= hash= bytes=` |
| `zen/selfhost/tests/test_selfhost_interp_functions.py` | 22 tests contra referencia Python independiente |

## Diseño y semántica
- Scanner → tokens en arrays; parser iterativo (sin recursión) con shunting-yard; ejecución con pilas de marcos y valores.
- `fn nombre(a,b){...}` solo a nivel superior, declaráble después de su uso; aridad validada tras parsear; función desconocida → estado 5; aridad → 6.
- Marco por invocación: parámetros mutables + `let`; sin herencia de variables; `return` desenlaza bloques de la invocación; sin `return` → 0.
- Límites: 512 nodos, profundidad de llamadas ≤16, pasos ≤1.000.000, 16 variables por marco, salida ≤256 B, 2048 tokens → estado 4.
- Sin libc ni estado global; arrays fijos locales; `nm -u` vacío. **Stack:** `objdump` mide ~177 KiB en debug y ~156 KiB en release (arrays locales), por encima de los 32 KiB de stack de tarea de Ferros: el intérprete es solo host, no ejecutable en una tarea de usuario actual.

## Verificación
```bash
python3 -m unittest discover -s zen/selfhost/tests -p 'test_selfhost_interp_functions.py' -v
# 22 tests OK
python3 -m unittest discover -s zen/selfhost/tests
# 77 tests OK (55 previos + 22)
```
Cobertura: factorial recursivo, fibonacci acotado, parámetros/return, ámbito local, aridad, función desconocida, recursión infinita (límite), div0, sintaxis, determinismo y formato del driver.

## Límites
- Lenguaje de sentencias con funciones enteras; sin strings de usuario, arrays, punteros ni I/O salvo `print`.
- Intérprete, no compilador; el driver C usa libc, el objeto Zen no.

## Relevancia
El frontend/ejecución en Zen ya cubre funciones y recursión, el último bloque básico antes de necesitar tipos compuestos y stdlib.
