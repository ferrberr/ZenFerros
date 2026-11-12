# TASK-902E: Intérprete selfhost de un lenguaje de sentencias (Hito 9)

**Agente**: 02/03
**Estado**: COMPLETADA
**Resultado**: intérprete de sentencias en Zen; 16 tests, selfhost 55; límite de 1.000.000 de pasos; stack ~37,5 KB (no apto para stacks de usuario de Ferros); objeto sin libc.
**Dependencias**: TASK-902C, TASK-902D, TASK-213/214
**Archivos (propiedad exclusiva)**: `zen/selfhost/interp.zen`, `zen/selfhost/interp_driver.c`, `zen/selfhost/tests/test_selfhost_interp.py`

## Objetivo
Cuarto salto del autohosting: un intérprete **escrito en Zen** que escanee, parsee a AST en arrays fijos y ejecute un lenguaje de sentencias con variables, `if`, `while`, aritmética y `print`, verificado contra una implementación de referencia independiente.

## Contrato
- `pub fn zen_interp(source:u64,length:u64,out:u64)->u64`: escribe en `out`: [0] estado (0 ok,1 sintaxis,2 div0,3 variable desconocida,4 límites), [1] nº de sentencias ejecutadas, [2] FNV-1a32 de la salida impresa, [3] bytes impresos.
- Gramática mínima:
  - programa = sentencia*; sentencia = `let name = expr ;` | `name = expr ;` | `print expr ;` | `if expr { sentencia* } (else { sentencia* })?` | `while expr { sentencia* }`.
  - expr = comparaciones (`< <= > >= == !=`) sobre sumas/restas, productos/divisiones/restos, números decimales u64, variables, paréntesis, unario `-`.
- Semántica: u64 envolvente; div/resto por cero → estado 2; variable no definida → estado 3; `print expr;` añade la representación decimal y `\n` a la salida (hash FNV-1a32 y contador de bytes).
- Límites fijos documentados: ≤256 nodos AST, profundidad ≤32, ≤16 variables, ≤256 bytes impresos, ≤1.024 tokens y **≤1.000.000 de pasos de ejecución**; estado 4 al exceder (incluye `while 1 {}`).
- Sin libc ni estado global; arrays fijos locales; puede usar structs locales si son útiles (sin pasarlos).
- Driver C: lee fichero, llama y escribe `status= statements= hash= bytes=`.
- Test Python: compila con `zen build --target x86_64-unknown-none --emit obj`, enlaza driver, ejecuta ≥30 programas y compara estado, sentencias, hash y bytes contra un intérprete de referencia **propio en Python** (sin eval); cubre if/else, while, variables, precedencia, div0, variable desconocida, sintaxis y límites. `nm -u` vacío.

## Aceptación
- `python3 -m unittest discover -s zen/selfhost/tests -p 'test_selfhost_interp.py' -v` verde.
- Sin tocar compilador, ferros, benchmarks, infra ni otros ficheros de selfhost.
- Informe: diseño (arrays/estructuras), cobertura, límites y desviaciones.
