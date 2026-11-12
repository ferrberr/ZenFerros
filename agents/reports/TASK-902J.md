# TASK-902J — Evidencia: codegen selfhost con arrays

Fecha: 2026-11-11. Décimo componente del frontend/ejecución en Zen.

## Entregado
| Archivo | Contenido |
|---|---|
| `zen/selfhost/codegen_arrays.zen` (2.216 líneas) | Generador C11 con arrays fijos de u64: inicialización, lectura/escritura por índice, ámbitos y funciones |
| `zen/selfhost/codegen_arrays_driver.c` | Driver PROGRAMA.zen [SALIDA.c]; exit 0/2/4/5/6 |
| `zen/selfhost/tests/test_selfhost_codegen_arrays.py` | 20 tests: 39 programas válidos (27 arrays + 12 regresión) y 53 de error |

## Emisión
- `let a=[e0..eN-1];` (N≥1, u64, inferido), lectura `a[expr]`, asignación `a[expr]=expr;`; sin arrays como parámetro/retorno, sin multidimensionales ni `len`.
- C: `uint64_t v_n[N] = {...};`, índices `v_n[(size_t)(EXPR)]`, `#include <stddef.h>`, paréntesis de precedencia y `(void)v_n;` para `-Wunused-variable`.
- Sin comprobación de rango: UB documentado; los tests no hacen OOB.
- Corrección frente a 902I: entrada truncada devuelve `0xFFFFFFFE` en vez de emitir C parcial.

## Verificación
```bash
python3 -m unittest discover -s zen/selfhost/tests -p 'test_selfhost_codegen_arrays.py' -v
# 20 tests OK
python3 -m unittest discover -s zen/selfhost/tests
# 147 tests OK (127 previos + 20)
```
Cada programa: codegen → `cc -std=c11 -O2 -Wall -Wextra -Werror` → ejecutar → stdout comparado con referencia Python. Incluye bucles, escritura anidada, arrays locales en funciones, recursión con array por frame, índices anidados, 1/64 elementos, 32 arrays y errores exactos. `nm -u` vacío; sin wrapper.

## Límites
- Máx 64 elementos/array, 32 variables activas, profundidad 32, 2048 tokens, 1024 nodos.
- Arrays no asignables/pasables/imprimibles/comparables; sin OOB checks.
- Decisión: ADR-023 (ampliación).
