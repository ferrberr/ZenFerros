# TASK-214 — Evidencia: structs nominales mínimos

Fecha: 2026-11-11.

## Entregado
| Archivo | Cambio |
|---|---|
| `zen/compiler/src/mvp.rs` | Tabla de structs, tipo de struct, parser de declaración/construcción, acceso y asignación de campo, emisión C con `typedef struct`, diagnósticos |
| `zen/compiler/tests/structs_cli.rs` | 14 tests: construcción, lectura, escritura, mutabilidad, varios campos, duplicados/faltantes/tipos, struct como parámetro/retorno, negativos, ejemplo |
| `zen/examples/structs.zen` | Ejemplo ejecutable |

## Verificación
```bash
CARGO_HOME="$PWD/.cargo" cargo build --release --offline --manifest-path zen/compiler/Cargo.toml  # OK
CARGO_HOME="$PWD/.cargo" cargo test  --offline          --manifest-path zen/compiler/Cargo.toml
# 29 unit + 9 arrays + 14 structs + 8 freestanding + 11 native = 71 passed, 0 failed
./zen/compiler/target/release/zen run zen/examples/structs.zen
# token=7 at 3:12 valid=yes
# token=7 at 13:13 valid=no
# stats=3,1,no
```

## Alcance y límites
- Campos escalares; sin métodos, genéricos, anidamiento, arrays como campo ni structs como parámetro/retorno/copia/comparación/cast (diagnóstico localizado).
- Solo variables locales; layout C natural, sin ABI externa de structs.
- Semántica idéntica debug/release.

## Relevancia
Desbloquea modelar tokens/símbolos con nombre en Zen (junto a arrays) para el Hito 9. Decisión: ADR-017.
