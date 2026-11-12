# TASK-902B: Evaluador de expresiones escrito en Zen (Hito 9, parser etapa B)

**Agente**: 01/02
**Estado**: COMPLETADA
**Resultado**: parser/evaluador self-hosted verificado (7 tests, 95 comparaciones + fuzz 400 sin discrepancias).
**Dependencias**: TASK-902 (independiente en archivos)
**Archivos (propiedad exclusiva)**: `zen/selfhost/parser.zen`, `zen/selfhost/parser_driver.c`, `zen/selfhost/tests/test_selfhost_parser.py`

## Objetivo
Segundo componente del compilador escrito en Zen: un parser/evaluador recursivo de expresiones enteras, compilado por `zen` (freestanding) y verificado contra un evaluador de referencia independiente.

## Contrato
- `pub fn zen_eval(text:u64,length:u64,out:u64)->u64`: escribe en `out` dos u64: `[0]=estado` (0 ok, 1 error sintáctico, 2 división por cero, 3 desbordamiento de pila de parser), `[1]=valor u64`.
- Gramática: `expr := term (('+'|'-') term)*`, `term := factor (('*'|'/'|'%') factor)*`, `factor := número | '(' expr ')' | '-' factor`; espacios ignorados; números decimales u64; sin variables ni funciones.
- Sin libc; punteros/volatile/while/if; profundidad máxima acotada (p.ej. 64) y error 3 al excederla.
- Driver C: lee un fichero de líneas (una expresión por línea), llama a `zen_eval` y escribe `status=<> value=<>` por línea; compila con `cc -std=c11 -O2 -fno-pie -no-pie`.
- Test Python: fixtures de expresiones válidas e inválidas; referencia independiente en Python (parser propio pequeño, NO `eval` directo para evitar trampas); comparar estado y valor; incluir negativos, paréntesis anidados, división por cero y desbordamiento de profundidad.

## Aceptación
- `python3 -m unittest discover -s zen/selfhost/tests -p 'test_selfhost_parser.py' -v` verde (≥30 expresiones válidas y casos de error).
- Sin tocar `zen/compiler/src/**`, `ferros/**`, ni los archivos de TASK-902.
