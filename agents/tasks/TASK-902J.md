# TASK-902J: Codegen selfhost con arrays (Hito 9)

**Agente**: 02/03
**Estado**: COMPLETADA
**Resultado**: codegen con arrays u64; 20 tests; C emitido compila/ejecuta.
**Dependencias**: TASK-902I
**Archivos (propiedad exclusiva)**: `zen/selfhost/codegen_arrays.zen` (nuevo), `zen/selfhost/codegen_arrays_driver.c` (nuevo), `zen/selfhost/tests/test_selfhost_codegen_arrays.py` (nuevo)

## Objetivo
Ampliar el codegen selfhost con **arrays fijos de u64**, su inicialización, lectura y escritura por índice, emitiendo C y verificando ejecución real.

## Contrato
- `pub fn zen_codegen_arrays(source:u64,length:u64,out:u64,cap:u64)->u64`: C11; bytes o 0xFFFFFFFF límite / 0xFFFFFFFE sintaxis / 0xFFFFFFFD tipos.
- Lenguaje = TASK-902I (funciones) más:
  - `let a = [e0, e1, ..., eN-1];` (N≥1, u64, inferido), ámbito léxico como `let`.
  - índice `a[expr]` como expresión u64; asignación `a[expr] = expr;`.
  - sin arrays como parámetro/retorno; sin multidimensionales; sin `len` intrínseco (documentar).
- Emisión C: `uint64_t v_n[N] = { ... };` para inicialización; `v_n[(size_t)(EXPR)]` para lectura/escritura; sin comprobación de rango en C (documentar UB y evitar OOB en tests); paréntesis para precedencia.
- Driver igual que TASK-902I; test Python ≥15 programas: inicialización, lectura, escritura, bucles sobre arrays, arrays en funciones (locales), precedencia de índices, sombreado, errores de sintaxis/tipos (índice no u64, array como parámetro, asignación de tipo), sin OOB; codegen → `cc -Wall -Wextra -Werror` → ejecutar → comparar con referencia Python; `nm -u` vacío; sin wrapper.

## Aceptación
- `python3 -m unittest discover -s zen/selfhost/tests -p 'test_selfhost_codegen_arrays.py' -v` verde.
- Sin tocar compilador, ferros, benchmarks, infra ni otros ficheros de selfhost.
- Informe: diseño, emisión, cobertura, límites (sin OOB, arrays locales, tamaño máx) y desviaciones.
