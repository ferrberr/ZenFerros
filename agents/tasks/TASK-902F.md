# TASK-902F: Intérprete selfhost con funciones (Hito 9)

**Agente**: 02/03
**Estado**: COMPLETADA
**Resultado**: intérprete selfhost con funciones/recursión; 22 tests; selfhost 77.
**Dependencias**: TASK-902E
**Archivos (propiedad exclusiva)**: `zen/selfhost/interp_functions.zen` (nuevo), `zen/selfhost/interp_functions_driver.c` (nuevo), `zen/selfhost/tests/test_selfhost_interp_functions.py` (nuevo)

## Objetivo
Ampliar el intérprete selfhost con **funciones definidas por el usuario**: parámetros, `return`, llamadas, recursión acotada y errores (aridad, función desconocida, profundidad), verificado contra referencia independiente.

## Contrato
- `pub fn zen_interp_fns(source:u64,length:u64,out:u64)->u64`: out[0]=estado (0 ok,1 sintaxis,2 div0,3 variable desconocida,4 límites,5 función desconocida,6 aridad incorrecta), out[1]=sentencias ejecutadas, out[2]=FNV-1a32 de la salida, out[3]=bytes impresos.
- Gramática base de TASK-902E más:
  - `fn nombre(a, b) { sentencia* }` a nivel superior (sin anidar), parámetros identificadores.
  - `return expr;` dentro de función.
  - llamada `nombre(expr, expr...)` como expresión.
  - Variables locales por invocación (ámbito de función), parámetros mutables por asignación.
- Semántica: u64 envolvente; div0→2; variable no definida→3; función no definida→5; aridad errónea→6 (detectada en parseo); profundidad de llamadas ≤16 y pasos totales ≤1.000.000→4; sin `main` implícito: se ejecutan las sentencias de nivel superior (pueden llamar funciones).
- Sin libc/estado global; arrays fijos locales; límites documentados (nodos 512, vars por marco 16, marcos 16, tokens 2048, salida 256 B).
- Driver C: `status= statements= hash= bytes=`.
- Test Python: ≥30 programas contra un intérprete de referencia propio en Python (con funciones/recursión, sin eval): factorial recursivo, fibonacci acotado, parámetros, returns, aridad, función desconocida, recursión infinita (límite), div0, sintaxis; `nm -u` vacío.

## Aceptación
- `python3 -m unittest discover -s zen/selfhost/tests -p 'test_selfhost_interp_functions.py' -v` verde.
- Sin tocar compilador, ferros, benchmarks, infra ni otros ficheros de selfhost.
- Informe con diseño, cobertura, límites y desviaciones.
