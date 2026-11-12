# TASK-902K: Codegen selfhost con structs (Hito 9)

**Agente**: 02/03
**Estado**: COMPLETADA
**Resultado**: codegen selfhost con structs; 19 tests; C emitido compila/ejecuta.
**Dependencias**: TASK-902J
**Archivos (propiedad exclusiva)**: `zen/selfhost/codegen_structs.zen` (nuevo), `zen/selfhost/codegen_structs_driver.c` (nuevo), `zen/selfhost/tests/test_selfhost_codegen_structs.py` (nuevo)

## Objetivo
Añadir structs nominales al lenguaje que compila el codegen selfhost: declaración, literal, acceso/escritura de campo, emitiendo C y verificando ejecución real.

## Contrato
- `pub fn zen_codegen_structs(source:u64,length:u64,out:u64,cap:u64)->u64`: C11; bytes o 0xFFFFFFFF límite / 0xFFFFFFFE sintaxis / 0xFFFFFFFD tipos.
- Lenguaje = TASK-902J (funciones + arrays) más:
  - `struct Nombre { campo: u64, ..., }` a nivel superior (campos u64, ≥1, únicos, ≤8 campos, ≤16 structs).
  - literal `Nombre { campo: expr, ... }` como inicializador de `let`.
  - acceso `p.campo` (u64) y asignación `p.campo = expr;`; `let mut` para escribir.
  - sin structs como parámetro/retorno/copia/comparación/array de structs/campo struct; sin métodos.
- Emisión C: `typedef struct { uint64_t f0; ... } zn_<N>;` antes de funciones; locales `zn_<N> v_n;`; inicialización campo a campo; `v_n.f0`; nombres saneados (struct/campos keyword C probados).
- Driver igual que TASK-902J. Test Python (unittest, discover) ≥15 programas: literal, lectura, escritura, varios campos, structs locales en funciones, sombreado, errores (campo faltante/extra/duplicado, tipo, copia/asignación/parámetro/retorno/comparación, struct vacío, >8 campos, >16 structs), límites, determinismo; codegen → `cc -std=c11 -O2 -Wall -Wextra -Werror` → ejecutar → stdout comparado con referencia Python; `nm -u` vacío; sin wrapper.

## Aceptación
- `python3 -m unittest discover -s zen/selfhost/tests -p 'test_selfhost_codegen_structs.py' -v` verde.
- Sin tocar compilador, ferros, benchmarks, infra ni otros ficheros de selfhost.
- Informe: diseño, emisión, cobertura, límites y desviaciones.
