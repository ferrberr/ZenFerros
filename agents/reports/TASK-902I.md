# TASK-902I — Evidencia: codegen C selfhost con funciones

Fecha: 2026-11-11. Noveno componente del frontend en Zen.

## Entregado
| Archivo | Contenido |
|---|---|
| `zen/selfhost/codegen_functions.zen` (1.842 líneas) | Generador C11 con funciones: parser/typechecker iterativo, emisión de `static uint64_t fn_<n>(...)`, prototipos, llamadas y recursión |
| `zen/selfhost/codegen_functions_driver.c` | Driver: C a stdout/fichero; exit 0/2/4/5/6 |
| `zen/selfhost/tests/test_selfhost_codegen_functions.py` (18 tests) | 25 programas válidos + 28 de error; codegen → `cc -std=c11 -O2 -Wall -Wextra -Werror` → ejecutar → comparar con referencia |

## Emisión
- `fn nombre(a,b){...}` a nivel superior, parámetros/retorno u64 (bool interno), `return`, llamadas como expresión y recursión; prototipos antes de `main`.
- Nombres saneados `v_<slot>`/`fn_<n>`; ámbitos léxicos y sombreado; paréntesis para precedencia; sin reutilizar el emitter Rust.
- Sin libc en el objeto Zen; C emitido usa stdio. División por cero: comportamiento C (documentado).

## Verificación
```bash
python3 -m unittest discover -s zen/selfhost/tests -p 'test_selfhost_codegen_functions.py' -v
# 18 tests OK
python3 -m unittest discover -s zen/selfhost/tests
# 127 tests OK (109 previos + 18)
```
Cobertura: factorial recursivo, fibonacci, parámetros/returns tempranos, llamadas anidadas, recursión mutua, orden libre de definición, funciones no usadas, shadowing, 64 funciones/16 params válidos, errores de sintaxis/tipos/aridad, límites y determinismo. `nm -u` vacío; C sin rastro de wrapper.

## Límites
- Funciones u64 (bool interno); sin arrays/strings/structs generados; profundidad de recursión limitada por el stack C del programa emitido; div0 sin comprobar.
- Sin optimización ni ABI externa. Decisión: ADR-023 (ampliación).
