# TASK-902C — Evidencia: AST real en Zen con arrays fijos

Fecha: 2026-11-11. Tercer componente de self-hosting parcial, habilitado por los arrays de TASK-213.

## Entregado
| Archivo | Contenido |
|---|---|
| `zen/selfhost/ast_parser.zen` (414 líneas) | Tokenizador + descenso recursivo que construye un AST en arrays paralelos locales y lo recorre para evaluar; `pub fn zen_ast_eval(text,length,out)` |
| `zen/selfhost/ast_driver.c` | Driver C por línea: `status= value= nodes= ast=` |
| `zen/selfhost/tests/test_selfhost_ast.py` | 14 tests: valores contra referencia Python, nodos>0, checksum determinista y distinto por estructura, precedencia, errores, div0, límites de arena/profundidad y `nm -u` vacío |

## Representación
Arena de 512 nodos en arrays locales Zen: `kinds: [u8;512]`, `values: [u64;512]`, `lefts/rights: [u32;512]`, más pila de operadores `[u32;512]`. `zen_ast_eval` escribe `out[0]` estado (0 ok,1 sintaxis,2 div0,3 arena/profundidad), `out[1]` valor, `out[2]` nodos y `out[3]` checksum FNV-1a estructural. El AST se **construye y luego se recorre**; no se reevalúa durante el parseo.

## Verificación
```bash
python3 -m unittest discover -s zen/selfhost/tests -p 'test_selfhost_ast.py' -v
# Ran 14 tests — OK
python3 -m unittest discover -s zen/selfhost/tests
# Ran 28 tests — OK (7 lexer + 7 parser + 14 AST)
```
El objeto Zen no importa libc (`nm -u` vacío) y el test comprueba en el fuente que se usan arrays locales y recorrido.

## Límites
- Gramática de expresiones enteras; sin declaraciones, tipos ni spans; no es un frontend completo.
- Arena fija de 512 nodos y profundidad 128 (estado 3 al exceder).
- Checksum estructural, no comparación de AST contra un oráculo estructural externo (sí valores/nodos contra referencia).
- Sin structs: la "forma" del nodo se reparte en arrays paralelos.
- El driver C usa libc; el objeto Zen no.

## Relevancia
Demuestra que Zen puede **representar y recorrer un AST real** con su propio subconjunto actual, que era el bloqueo identificado en ADR-014. Siguiente paso: spans y tabla de símbolos (requiere structs/strings gestionadas) y ampliar gramática.
