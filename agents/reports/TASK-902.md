# TASK-902/902B — Evidencia: lexer y parser en Zen (Hito 9, etapa B)

Fecha: 2026-11-11. Dos componentes del frontend escritos en Zen y compilados por `zen`, verificados contra referencias independientes.

## Entregado

| Componente | Archivos | Contrato |
|---|---|---|
| Lexer contador | `zen/selfhost/lexer.zen` (457 líneas), `lexer_driver.c`, `tests/test_selfhost_lexer.py` | `pub fn zen_lex_report(source:u64,length:u64,out:u64)`: 8 contadores u64 (tokens sin EOF, idents, numbers, strings, keywords —`null` sigue clasificándose como Ident por paridad con el lexer Rust, que no lo registra—, punct, errors, bytes) |
| Parser/evaluador | `zen/selfhost/parser.zen` (205 líneas), `parser_driver.c`, `tests/test_selfhost_parser.py` | `pub fn zen_eval(text:u64,length:u64,out:u64)`: estado/valor u64; gramática de expresiones con precedencia, paréntesis, unario, `/`/`%` con error de división por cero y profundidad ≤64 |

Ambos son freestanding: objeto ELF64 `x86_64-unknown-none`, `nm -u` vacío, exportados por ABI C y ejecutados desde un driver C; el objeto Zen no usa libc. Documentación: `docs/zen/selfhost.md`; decisión ADR-014.

## Verificación real

```bash
python3 -m unittest discover -s zen/selfhost/tests -v
# Ran 166 tests — OK (7 lexer + 7 parser + 14 AST + 11 tokens + 16 intérprete + 22 funciones)
```

- Lexer: 5 fixtures × 8 contadores = **40 comparaciones exactas** contra `zen lex` (hello, factorial, structs, vfs, fixture sintético) + 2 casos de error; verificación manual adicional sobre **44 ficheros `.zen`** de `zen/` y `ferros/` (incluye copias generadas del build) sin discrepancias.
- Parser: **95 comparaciones** estado/valor contra un parser de referencia en Python (43 válidas, 26 errores, 20 precedencia/asociatividad, 6 profundidad), formato exacto de salida y `nm -u` vacío; fuzz manual de 400 expresiones sin discrepancias (no está automatizado en la suite; el script de estrés TASK-905 añade fuzz diferencial reproducible).
- `zen check --target x86_64-unknown-none` y `build --emit obj` verdes en debug y release.

## Límites honestos
- No es un compilador completo: el AST es de expresiones aritméticas, sin spans, tabla de símbolos ni stdlib; el lexer no calcula valores de token.
- `null` se cuenta como `Ident` porque el lexer Rust actual no lo registra como keyword; se mantiene paridad estricta.
- UTF-8 multibyte inesperado puede diferir del lexer Rust; la comparación se hace sobre fuentes válidos.
- El parser limita la profundidad a 64 y devuelve estado 3 al excederla; no hay recuperación de errores.
- El driver C usa libc; el objeto Zen no.

## Conclusión
Hito 9 queda **parcialmente demostrado** con tres componentes reales del compilador escritos en Zen y verificados (lexer, parser/evaluador y AST con arrays). El AST ya existe; el siguiente paso exige spans y tabla de símbolos (structs) y stdlib.
