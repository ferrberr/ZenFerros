# TASK-902C: AST en Zen con arrays fijos (Hito 9)

**Agente**: 02/03
**Estado**: COMPLETADA
**Resultado**: AST real en Zen sobre arrays fijos, 14 tests; selfhost total 28; `nm -u` vacío.
**Dependencias**: TASK-902B, TASK-213
**Archivos (propiedad exclusiva)**: `zen/selfhost/ast_parser.zen`, `zen/selfhost/ast_driver.c`, `zen/selfhost/tests/test_selfhost_ast.py`

## Objetivo
Representar y recorrer un AST real **en Zen**, usando los arrays fijos de TASK-213 (sin structs): tokenizar una expresión, construir nodos en arrays paralelos y evaluarla recorriendo el AST.

## Contrato
- `pub fn zen_ast_eval(text:u64,length:u64,out:u64)->u64`: escribe en `out` `[0]=estado` (0 ok, 1 sintaxis, 2 div0, 3 desbordamiento de arena/profundidad), `[1]=valor u64`, `[2]=número de nodos AST construidos`, `[3]=checksum estructural del AST` (p. ej. FNV-1a sobre kind/value/left/right).
- Gramática: la misma de TASK-902B (`+ - * / %`, paréntesis, unario) y precedencia.
- Representación obligatoria: arrays locales de tamaño fijo declarados en Zen, p. ej. `let mut kinds: [u8; 512]`, `values: [u64; 512]`, `lefts/rights: [u32; 512]`, arena con índice raíz; el recorrido de evaluación **debe leer los arrays** (no reevaluar durante el parseo).
- Sin libc/structs; arrays locales solamente (params/retorno/global rechazados). Límite de nodos y profundidad con estado 3.
- Driver C: fichero de líneas, imprime `status=<n> value=<n> nodes=<n> ast=<n>`; enlaza driver + objeto Zen.
- Test Python: compila `ast_parser.zen` con `zen build --target x86_64-unknown-none --emit obj` (verifica que usa arrays), compila driver, ejecuta ≥40 expresiones y compara `status/value` con la referencia Python; comprueba que `nodes>0` y que `ast` es determinista y distinto para expresiones distintas; negativos de sintaxis/div0/arena.

## Aceptación
- `python3 -m unittest discover -s zen/selfhost/tests -p 'test_selfhost_ast.py' -v` verde.
- Sin tocar `zen/compiler/**`, `ferros/**`, `benchmarks/**`, `infrastructure/**`, ni los ficheros de TASK-902/902B.
