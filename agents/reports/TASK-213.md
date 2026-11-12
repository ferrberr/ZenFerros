# TASK-213 — Evidencia: arrays de tamaño fijo `[T; N]`

Fecha: 2026-11-11. Implementado en `zen/compiler/src/mvp.rs`, con tests nuevos y ejemplo.

## Entregado
| Archivo | Contenido |
|---|---|
| `zen/compiler/src/mvp.rs` | `Ty::Array(Elem,N)`, `Place::{Var,Index}`, `ExprKind::{ArrayLit,ArrayRepeat,Index}`; parser de tipo `[T; N]`, literales/repeat, indexación lectura/escritura/compuestas; emisión C con `T name[N]` y `__zen_index_check`; rechazos localizados |
| `zen/compiler/tests/arrays_cli.rs` | 9 tests: positivos, repeat, tipos, orden/evaluación única, límites de recursos, OOB debug/release, 39 negativos |
| `zen/examples/arrays.zen` | Ejemplo ejecutable |

## Comandos y salida real
```bash
CARGO_HOME="$PWD/.cargo" cargo build --release --offline --manifest-path zen/compiler/Cargo.toml  # OK
CARGO_HOME="$PWD/.cargo" cargo test  --offline          --manifest-path zen/compiler/Cargo.toml
# 29 unit + 9 arrays + 8 freestanding + 11 native = 57 passed, 0 failed
./zen/compiler/target/release/zen run zen/examples/arrays.zen
# sum=15
# doubled=2 4 6 8 10
# flags=1
# bytes=90,42
# exit=0
```
OOB: exit 1 con `Zen runtime error: array index out of bounds` en debug y release. Negativo de parámetro: diagnóstico `error: fixed-size arrays cannot be parameters...` con ruta/posición.

## Semántica
- Índice evaluado una vez, de izquierda a derecha, y comprobado antes del acceso; helper `uint64_t __zen_index_check(uint64_t,uint64_t)` evita UB con índices negativos (quedan fuera de rango).
- `[e; N]` evalúa `e` una vez; literal con longitud exacta y tipos exactos.
- Escritura exige `let mut`; arrays solo locales; params/retorno/argumento/copia/comparación/cast/slice/`.len`/multidim rechazados.
- Semántica idéntica debug/release; freestanding usa `ud2`.

## Límites y deuda
- Sin inferencia de arrays (anotación obligatoria), sin multidimensionales, slicing, puntero a array ni `.len`.
- Sin paso de arrays entre funciones; sin arrays de structs (no hay structs).
- `N` gigante válido puede fallar en el backend C; no hay tope artificial.
- Asignación compuesta relee el elemento tras el RHS; no observable sin aliasing/paso de arrays.

## Relevancia
Desbloquea el siguiente paso del Hito 9: un parser con AST de tamaño fijo escrito en Zen (antes imposible por falta de secuencias). Decisión: ADR-016.
