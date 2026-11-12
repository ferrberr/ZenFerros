# Composición multi-archivo: `use` — TASK-912

```zen
use "../std/core.zen";

fn main() -> i32 {
    print_uint(min_u64(42, 7));
    return 0;
}
```

- Directivas `use "ruta.zen";` al inicio, antes de cualquier item.
- Resolución **textual** y relativa al fichero que incluye; includes anidados; profundidad máxima 16; ciclos y ficheros ausentes con error claro.
- Un mismo fichero canónico se incluye una sola vez por build.
- Los errores dentro de un incluido se reportan con su ruta/línea/columna reales.
- `zen build/run/check` resuelven includes; `zen fmt` formatea el fuente tal cual (preserva directivas); `zen lint` y `zen lsp` son single-file.

Stdlib distribuible: `zen/std/core.zen` y `zen/std/array.zen` (`min_u64`, `max_u64`, `clamp_u64`, `abs_diff_u64`, `is_even`, `is_odd`, `gcd_u64`); ejemplo `zen/examples/use_std.zen`.

Límites: sin namespaces ni visibilidad (colisiones de nombres entre ficheros), sin imports selectivos/condicionales, search paths ni rebuild incremental. Decisión: ADR-024. Evidencia: `agents/reports/TASK-912.md`.
