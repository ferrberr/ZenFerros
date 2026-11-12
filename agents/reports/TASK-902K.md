# TASK-902K — Evidencia: codegen selfhost con structs

Fecha: 2026-11-12. Undécimo componente selfhost.

## Entregado
| Archivo | Contenido |
|---|---|
| `zen/selfhost/codegen_structs.zen` (2.733 líneas) | Generador C11 con structs nominales: declaración, literal, acceso/escritura de campo |
| `zen/selfhost/codegen_structs_driver.c` | Driver PROGRAMA.zen [SALIDA.c] |
| `zen/selfhost/tests/test_selfhost_codegen_structs.py` | 19 tests; 18 programas válidos + 26 de error |

## Emisión y semántica
- `struct Nombre { campo: u64, ... }` a nivel superior (1–8 campos, ≤16 structs); typedef `zn_<N>` antes de prototipos/funciones.
- `let p = Nombre { campo: expr, ... };` (todos los campos, orden libre, coma final opcional), `p.campo` lectura y `p.campo = expr` con `let mut`.
- Sin copia/asignación completa/parámetro/retorno/comparación/condición/print/array de structs/acceso anidado; sin métodos.
- Nombres saneados (keywords C probados); `zn_cmp` solo con comparaciones; `(void)v_n;` para `-Werror`.

## Verificación
```bash
python3 -m unittest discover -s zen/selfhost/tests -p 'test_selfhost_codegen_structs.py' -v
# 19 tests OK
python3 -m unittest discover -s zen/selfhost/tests
# 166 tests OK (147 previos + 19)
```
Cada programa: codegen → `cc -std=c11 -O2 -Wall -Wextra -Werror` → ejecutar → stdout comparado con referencia Python; límites, determinismo, driver y `nm -u` vacío.

## Límites
- 8 campos/16 structs, sin structs como parámetro/retorno/copia; solo u64; sin métodos; Decisión: ADR-023 (ampliación).
