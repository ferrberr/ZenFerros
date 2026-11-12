# TASK-902G: Typechecker selfhost (Hito 9)

**Agente**: 02/03
**Estado**: COMPLETADA
**Resultado**: typechecker selfhost u64/bool; 16 tests; selfhost 93.
**Dependencias**: TASK-902F
**Archivos (propiedad exclusiva)**: `zen/selfhost/typecheck.zen` (nuevo), `zen/selfhost/typecheck_driver.c` (nuevo), `zen/selfhost/tests/test_selfhost_typecheck.py` (nuevo)

## Objetivo
Añadir **comprobación de tipos** escrita en Zen: inferir/verificar tipos de un lenguaje de sentencias con enteros u64 y bool, detectar usos incorrectos y verificar contra una referencia independiente.

## Contrato
- `pub fn zen_typecheck(source:u64,length:u64,out:u64)->u64`: out[0]=estado (0 ok,1 sintaxis,2 error de tipos,3 variable no definida,4 límites), out[1]=nº de sentencias comprobadas, out[2]=nº de errores de tipos (0 si ok), out[3]=FNV-1a32 de un resumen textual estable de errores (vacío si ok).
- Lenguaje: sentencias `let n = expr;`, `n = expr;`, `if expr { ... } else { ... }`, `while expr { ... }`, `print expr;`; expresiones con enteros, variables, `+ - * / %` (u64), comparaciones `< <= > >= == !=` (bool), `&& || !` (bool, sin cortocircuito observable), paréntesis. Sin funciones/arrays/strings.
- Tipos: `u64` y `bool`; `let` infiere; asignación exige el mismo tipo; condiciones exigen bool; aritmética exige u64; comparaciones exigen operandos del mismo tipo y producen bool; `print` acepta u64 o bool (representación 0/1).
- Errores: variable no definida (3), error de tipos (2) con código localizado; el primer error detiene la comprobación (documentar). Límites: 512 nodos, profundidad 32, 32 variables, 1024 tokens → 4.
- Sin libc/estado global; arrays fijos locales; driver C `status= checked= errors= hash=`.
- Test Python: ≥30 programas contra un typechecker de referencia propio en Python (sin eval): inferencia, scopes, asignación incompatible, condición no bool, aritmética con bool, comparación de tipos distintos, variables no definidas, sintaxis, límites, resumen estable.

## Aceptación
- `python3 -m unittest discover -s zen/selfhost/tests -p 'test_selfhost_typecheck.py' -v` verde.
- Sin tocar compilador, ferros, benchmarks, infra ni otros ficheros de selfhost.
- Informe: diseño, tipos/reglas, cobertura, límites y desviaciones.
