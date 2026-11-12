# TASK-902: Lexer de Zen escrito en Zen (Hito 9, etapa B)

**Agente**: 01/02/03
**Estado**: COMPLETADA
**Resultado**: lexer self-hosted verificado (6 tests, 40 comparaciones exactas en 5 fixtures + manual en 42 ficheros).
**Dependencias**: TASK-208, TASK-310/311
**Archivos (propiedad exclusiva)**: `zen/selfhost/lexer.zen`, `zen/selfhost/lexer_driver.c`, `zen/selfhost/tests/test_selfhost_lexer.py`, `docs/zen/selfhost.md`

## Objetivo
Primer componente real del compilador escrito en Zen: un lexer freestanding del subconjunto MVP, compilado por el propio compilador Zen y verificado contra el lexer Rust sobre los mismos ficheros.

## Contrato
- `pub fn zen_lex_report(source:u64,length:u64,out:u64)`: recorre el fuente y escribe 8 contadores u64 en `out`: total tokens (sin EOF), identificadores, enteros y floats, cadenas y chars, palabras clave (incl. true/false; `null` se clasifica como Ident por paridad con el lexer Rust actual), puntuación/operadores, errores léxicos, bytes consumidos.
- Sintaxis aceptada: identificadores ASCII, enteros dec/hex/bin/oct con sufijos, floats básicos, strings/chars con escapes, `//` y `/* */` anidados, operadores del MVP, keywords del subconjunto.
- Sin libc: solo punteros/volatile/while/if; sin structs; los arrays fijos existen desde TASK-213, pero este lexer usa memoria cruda para mantener el alcance original.
- Driver C `lexer_driver.c`: lee el fichero, llama a `zen_lex_report` e imprime `key=value` por línea; enlaza con `cc -no-pie`.
- Test Python: para ≥4 ficheros (`zen/examples/*.zen`, `ferros/kernel/vfs.zen`), compila el objeto con `zen build --target x86_64-unknown-none --emit obj`, ejecuta el driver y compara contadores con los que produce `zen lex <file>` (excluyendo `Eof`; mapear TokenKind a categorías).

## Aceptación
- `python3 -m unittest discover -s zen/selfhost/tests -v` verde en ≥4 fixtures.
- Sin tocar `zen/compiler/src/**` ni `ferros/**`.
- Evidencia: diff resumido, comandos y salida; documentar límites (subset exacto).
