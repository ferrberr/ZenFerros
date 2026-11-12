# TASK-902H — Evidencia: codegen C selfhost

Fecha: 2026-11-11. Octavo componente del frontend en Zen.

## Entregado
| Archivo | Contenido |
|---|---|
| `zen/selfhost/codegen.zen` | Scanner + parser/typechecker iterativo + emisión directa de C11; `zen_codegen(source,len,out,cap)` |
| `zen/selfhost/codegen_driver.c` | Driver: C a stdout o fichero; exit 0/2/4/5/6 |
| `zen/selfhost/tests/test_selfhost_codegen.py` | 16 tests; 44 programas válidos + 17 de error/límite |

## Emisión
- u64 → `uint64_t`, bool → `int` (0/1), literales `<n>ULL` mod 2^64, `print` → `printf("%llu\n", ...)`, nombres `v_<slot>` con ámbitos/sombreado, indentación 4 espacios.
- Operadores binarios entre paréntesis (C separa precedencias de comparación; sin ello `a == b < c` se malcompilaba).
- División/resto por cero: comportamiento C, no comprobado (documentado).
- Límites: 1024 tokens, 512 nodos, 32 profundidad, 32 variables, capacidad de salida → `0xFFFFFFFF`.

## Verificación
```bash
python3 -m unittest discover -s zen/selfhost/tests -p 'test_selfhost_codegen.py' -v
# 16 tests OK
python3 -m unittest discover -s zen/selfhost/tests
# 109 tests OK (93 previos + 16)
```
Cada programa: codegen → `cc -std=c11 -O2` → ejecutar → stdout comparado con referencia Python. Incluye if/else, while, cadenas de comparación, bool 0/1, &&/||/!, wrapping, u64 grande, sombreado, nombres keyword de C, programa vacío, límites exactos de capacidad y determinismo. `nm -u` vacío; el C emitido no contiene rastros de wrapper.

## Límites
- Solo lenguaje u64/bool; sin funciones, arrays, strings ni structs generados.
- `&&`/`||` usan cortocircuito de C (sin efectos laterales salvo div0).
- Sin comprobación de div0 ni optimización; el driver acota salida a 64 MiB.
- Decisión: ADR-023.
