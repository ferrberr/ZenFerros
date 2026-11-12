# Slices `[u64]` y stdlib de arrays — TASK-915

```zen
use "../std/array.zen";

fn main() -> i32 {
    let mut values = [3u64, 1u64, 4u64, 2u64];
    sort_slice(values);
    print_uint(sum_slice(values));
    return 0;
}
```

- Un **slice** `[u64]` es una vista `{puntero, longitud}` y solo puede usarse como parámetro de función.
- Al pasar un array local `[u64; N]` se convierte sin copia: las escrituras del callee se ven en el caller.
- `slice_len(s)` devuelve la longitud; `s[i]` comprueba límites en tiempo de ejecución (también en `--release`).
- `zen/std/array.zen` ofrece `sum_slice`, `max_slice`, `reverse_slice`, `sort_slice` (inserción) y `contains_slice`, sin heap ni libc.
- Rechazado: slices locales, retorno, copia/comparación, campos de struct, ABI C/freestanding y elementos distintos de u64. Sin tracking de aliasing: un array no-`mut` puede modificarse a través de un slice.

Decisión: ADR-026. Evidencia: `agents/reports/TASK-915.md`.
