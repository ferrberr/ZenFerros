# TASK-902H: Codegen C selfhost (Hito 9)

**Agente**: 02/03
**Estado**: COMPLETADA
**Resultado**: codegen C selfhost; 16 tests; C emitido compila y ejecuta; ADR-023.
**Dependencias**: TASK-902G
**Archivos (propiedad exclusiva)**: `zen/selfhost/codegen.zen` (nuevo), `zen/selfhost/codegen_driver.c` (nuevo), `zen/selfhost/tests/test_selfhost_codegen.py` (nuevo)

## Objetivo
Primer **generador de código escrito en Zen**: compilar el lenguaje de sentencias u64/bool a C, verificando que el C emitido compila con `cc`, ejecuta y produce la salida de referencia.

## Contrato
- `pub fn zen_codegen(source:u64,length:u64,out:u64,cap:u64)->u64`: escribe C (bytes ASCII) en `out`; devuelve bytes escritos o código de error (`0xFFFFFFFF` límite, `0xFFFFFFFE` sintaxis, `0xFFFFFFFD` tipos/no definida). Emite un programa C completo `#include <stdio.h>` + `#include <stdint.h>` + `int main(void){...}` usando `uint64_t`/`int` y `printf("%llu\n", ...)` (o `PRIu64`), sin reutilizar el emitter Rust.
- Lenguaje: el de TASK-902G (`let`, asignación, `print`, `if/else`, `while`, u64/bool, comparaciones, aritmética, `&& || !`).
- Reglas de emisión: nombres saneados a `v_<n>`; variables declaradas al inicio del bloque donde se crean (C99 permite mixto, pero se prefiere declaración en el punto); condiciones bool como `int`; sin UB (división por cero se mantiene como en C, documentar); indentación legible.
- Driver C: lee fuente, llama, escribe el C por stdout o a argv[2]; exit 0 si ok, ≠0 con mensaje si error.
- Test Python: ≥15 programas; para cada uno, ejecuta el codegen, compila el C con `cc -std=c11 -O2`, ejecuta y compara stdout exacto con un intérprete de referencia Python; incluye if/while, comparaciones, bool print (0/1), aritmética envolvente, programa vacío. Verifica que el objeto Zen no importa libc (`nm -u` vacío) y que el C emitido no contiene texto del compilador Rust (no es un wrapper).

## Aceptación
- `python3 -m unittest discover -s zen/selfhost/tests -p 'test_selfhost_codegen.py' -v` verde.
- Sin tocar compilador, ferros, benchmarks, infra ni otros ficheros de selfhost.
- Informe: diseño, emisión, cobertura, límites y desviaciones.
