# TASK-912 — Evidencia: `use` / includes textuales y stdlib distribuible

Fecha: 2026-11-11.

## Entregado
| Archivo | Cambio |
|---|---|
| `src/module.rs` | Resolución textual con source map, profundidad 16, ciclos, dedup canónica y errores localizados |
| `src/main.rs` | `build/run/check` resuelven includes; `diagnose_resolved` mapea spans al fichero real |
| `src/lib.rs` | `pub mod module` |
| `tests/include_cli.rs` | 10 tests |
| `zen/std/core.zen` | 7 funciones puras (`min_u64`, `max_u64`, `clamp_u64`, `abs_diff_u64`, `is_even`, `is_odd`, `gcd_u64`) |
| `zen/examples/use_std.zen` | Ejemplo con `use "../std/core.zen"` y salida verificable |

## Reglas
- `use "ruta";` solo antes de items; rutas relativas al fichero que incluye (también `../`, `./`, subdirectorios; absolutas aceptadas como superconjunto).
- Inserción textual depth-first izquierda-a-derecha; depth ≤16; ciclos con cadena; mismo fichero una sola vez; ausente con origen:línea; newline de separación.
- Diagnósticos dentro de incluidos mapeados a fichero/línea/columna reales.
- `fmt` no resuelve (preserva directivas); `lint`/`lsp` single-file lo documentan; `lex` expone `Use`/`String`/`Semi`.

## Verificación
```bash
CARGO_HOME="$PWD/.cargo" cargo build --release --offline --manifest-path zen/compiler/Cargo.toml  # OK
CARGO_HOME="$PWD/.cargo" cargo test  --offline          --manifest-path zen/compiler/Cargo.toml
# 151/151 (141 previos + 10 include)
./zen/compiler/target/release/zen run zen/examples/use_std.zen
# min_u64(42, 7) = 7 ... gcd_u64(84, 30) = 6 / use std ok
```
Tests: include simple/anidado/relativo, ciclo, ausente, profundidad 16 OK/17 falla, duplicado canónico, error localizado en incluido, `use` tras items, y build/check/run del ejemplo.

## Límites
- Inclusión textual sin namespaces/visibilidad: `pub` no aísla; nombres duplicados entre ficheros colisionan.
- Sin `mod`, imports selectivos/condicionales, search paths, stdlib embebida ni rebuild incremental; `fmt/lint/lsp` single-file.
- Decisión: ADR-024.
