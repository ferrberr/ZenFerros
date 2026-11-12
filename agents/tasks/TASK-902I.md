# TASK-902I: Codegen selfhost con funciones (Hito 9)

**Agente**: 02/03
**Estado**: COMPLETADA
**Resultado**: codegen C con funciones/recursión; 18 tests; C emitido compila/ejecuta.
**Dependencias**: TASK-902H
**Archivos (propiedad exclusiva)**: `zen/selfhost/codegen_functions.zen` (nuevo), `zen/selfhost/codegen_functions_driver.c` (nuevo), `zen/selfhost/tests/test_selfhost_codegen_functions.py` (nuevo)

## Objetivo
Ampliar el codegen escrito en Zen con **funciones de usuario, parámetros y return**, emitiendo C con funciones reales y verificando compilación/ejecución contra una referencia.

## Contrato
- `pub fn zen_codegen_fns(source:u64,length:u64,out:u64,cap:u64)->u64`: escribe C11 completo; devuelve bytes o errores 0xFFFFFFFF límite, 0xFFFFFFFE sintaxis, 0xFFFFFFFD tipos/no definida.
- Lenguaje: el de TASK-902H (let/asignación/print/if/while/expresiones u64/bool) más:
  - `fn nombre(a, b) { sentencia* }` a nivel superior; parámetros y retorno **u64** (bool interno permitido).
  - `return expr;` dentro de función; llamadas `nombre(expr,...)` como expresión.
  - Recursión permitida (C la soporta; el test incluye factorial/fibonacci).
- Emisión: `static uint64_t fn_<n>(uint64_t a, ...)` para cada función; `uint64_t` para args/retorno; nombres saneados; prototipos antes de `main` para permitir orden libre; `main` ejecuta sentencias de nivel superior. Sin reutilizar el emitter Rust.
- Sin libc en el objeto Zen; el C emitido usa stdio.
- Driver C igual que TASK-902H (`PROGRAMA.zen [SALIDA.c]`), exit 0/2/4/5/6.
- Test Python: ≥15 programas con funciones (factorial recursivo, fibonacci acotado, parámetros, returns tempranos, llamadas anidadas, funciones no usadas, orden de definición), codegen → `cc -std=c11 -O2 -Wall -Wextra -Werror` → ejecutar → comparar stdout con referencia Python; errores de sintaxis/tipos/aridad; `nm -u` vacío; sin rastro de wrapper.

## Aceptación
- `python3 -m unittest discover -s zen/selfhost/tests -p 'test_selfhost_codegen_functions.py' -v` verde.
- Sin tocar compilador, ferros, benchmarks, infra ni otros ficheros de selfhost.
- Informe: diseño, emisión, cobertura, límites (div0 C, profundidad stack C, funciones 64, params 16) y desviaciones.
