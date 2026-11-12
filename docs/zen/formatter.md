# Formateador `zen fmt` — TASK-904A

```bash
zen fmt archivo.zen            # stdout
zen fmt --check archivo.zen    # 0 si ya está formateado; 1 si difiere (no escribe)
zen fmt --write archivo.zen    # reemplazo atómico; solo si cambia
```

Reglas canónicas: indentación de 2 espacios por nivel de `{}`; una sentencia por línea; `{` al final de línea; `}` en línea propia (con `else` pegado); espacio alrededor de operadores y tras `,`; sin espacio tras `(`/`[`; comentarios `//` y `/* */` (anidados) conservados; los que siguen a `{`/`;` o preceden a `}` pasan a línea propia; una línea en blanco entre items top-level consecutivos (no se inserta si media un comentario).

Garantías: copia los lexemas originales desde los spans (no reescribe literales), re-lexa la salida y exige la misma secuencia de tokens, y comprueba idempotencia antes de devolver/escribir. Los ejemplos `hello.zen`, `factorial.zen`, `arrays.zen` y `structs.zen` formateados pasan `zen check`.

Límites: no preserva líneas en blanco arbitrarias; comentarios de bloque multilínea conservan su interior sin reindentar; requiere extensión `.zen`; no reordena ni elimina tokens. Decisión y alternativas: ADR-020. Evidencia: `agents/reports/TASK-904A.md`.
