# TASK-902D — Evidencia: lexer selfhost con tokens materializados

Fecha: 2026-11-11. Cuarto componente del frontend en Zen.

## Entregado
| Archivo | Contenido |
|---|---|
| `zen/selfhost/lexer_tokens.zen` (25 KB) | `pub fn zen_lex_tokens(source,length,out,max_tokens)->u64`: registros de 16 B (kind u32, start u32, end u32, value u32); réplica de scanner.rs; escritura directa en el array del llamador; sin libc ni estado global |
| `zen/selfhost/lexer_tokens_driver.c` | Ejecuta el lexer y emite `kind= start= end= value=` por token |
| `zen/selfhost/tests/test_selfhost_lexer_tokens.py` | 11 tests: tabla de 108 kinds (incluye Comment, inalcanzable en el scanner por defecto) parseada de `token.rs`, cobertura total, 4.369 tokens comparados con `zen lex`, límites de capacidad, errores, `nm -u` vacío |

## Verificación
```bash
python3 -m unittest discover -s zen/selfhost/tests -p 'test_selfhost_lexer_tokens.py' -v
# 11 tests OK
python3 -m unittest discover -s zen/selfhost/tests
# 39 tests OK (7 lexer + 7 parser + 14 AST + 11 tokens)
```
Comparación campo a campo (kind, start, end, value) sobre hello, factorial, structs, arrays, vfs.zen (3.393 tokens) y fixture sintético: **≈17.300 comprobaciones**, 0 discrepancias. Objeto ELF64 REL, `nm -u` vacío, único símbolo global `zen_lex_tokens`.

## Exclusiones documentadas
- Floats: solo kind/span; value=0 (f64 no cabe en u32).
- Enteros >u32: saturación a 0xFFFFFFFF; el test replica el clamp.
- Enteros >u128: Rust emite Error, Zen satura (sin casos en fixtures).
- `Bool/Null/Pipe2`: inalcanzables en scanner.rs; mapeados para cobertura de tabla.
- Errores léxicos: Zen devuelve 0xFFFFFFFF; probado con 5 entradas inválidas.
- Whitespace Unicode y literales no ASCII fuera de strings: solo ASCII, documentado.

## Límites
- Spans u32 (fuentes ≤4 GiB), sin recuperación de errores, sin valores float.
- `vfs.zen` es fixture vivo: si crece >8192 tokens o deja de ser léxico-válido, el test fallará (hoy 3.393).
- No es un parser: solo materializa tokens.
