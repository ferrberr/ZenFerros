# TASK-902D: Lexer selfhost con tokens materializados (Hito 9)

**Agente**: 02/03
**Estado**: COMPLETADA
**Resultado**: lexer con tokens materializados (kind/span/value), 4.369 tokens comparados, 11 tests; selfhost 39.
**Dependencias**: TASK-902, TASK-213
**Archivos (propiedad exclusiva)**: `zen/selfhost/lexer_tokens.zen`, `zen/selfhost/lexer_tokens_driver.c`, `zen/selfhost/tests/test_selfhost_lexer_tokens.py`

## Objetivo
Pasar del lexer contador a un lexer que **materializa** tokens (categoría, span, valor/hash) en arrays fijos, comparando la secuencia completa con el lexer Rust.

## Contrato
- `pub fn zen_lex_tokens(source:u64,length:u64,out:u64,max_tokens:u64)->u64`: escribe registros de 16 bytes en `out`: `[0] u32 kind`, `[4] u32 start`, `[8] u32 end`, `[12] u32 reserved`; devuelve número de tokens (sin Eof) o `0xFFFFFFFF` si excede `max_tokens`/error irrecuperable. Adicionalmente `pub fn zen_lex_value(index:u64)->u64` no es viable sin estado global: en su lugar, para números escribe el valor en `[12]` (u32) y para ident/string escribe un **hash FNV-1a de 32 bits de los bytes** (sobre el lexema sin quotes/escapes decodificados: documentar); para el resto `[12]=0`.
- Sin libc/structs; arrays fijos locales en la función de escaneo; sin estado global.
- Driver C: recorre registros e imprime una línea por token `kind=<n> start=<n> end=<n> value=<hex>`; `kind` usa una tabla numérica estable **definida en el test** (mapear TokenKind Rust → número).
- Test Python: para ≥3 fixtures, compara la **secuencia completa** (kind,start,end,value) con la salida de `zen lex` (que imprime kind+span y valores de ident/string/int). Para ident/string calcula el mismo FNV-1a32 sobre los bytes del lexema tal como aparecen en el fuente entre delimitadores (documentar limitación de escapes); para enteros usa el valor impreso por `zen lex`. Si una categoría no es comparable (p. ej. escapes complejos), exclúyela explícitamente y documenta.
- Comprueba `nm -u` vacío y que el objeto no importa libc.

## Aceptación
- `python3 -m unittest discover -s zen/selfhost/tests -p 'test_selfhost_lexer_tokens.py' -v` verde (≥3 fixtures; miles de tokens en vfs.zen).
- Sin tocar compilador, ferros, benchmarks, infra ni otros ficheros de selfhost.
- Informe: cobertura comparada (tokens/kind/span/value), exclusiones documentadas y límites.
