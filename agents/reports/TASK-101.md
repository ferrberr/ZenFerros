# TASK-101: Diseñar gramática MVP Zen (EBNF)

**Agente**: 01 (Arquitecto Zen)
**Estado**: ✅ COMPLETADA (Borrador v0.1)
**Prioridad**: ALTA
**Dependencias**: [TASK-008]

## Objetivo
Definir la gramática mínima viable (MVP) de Zen en notación EBNF.

## Entregables Completados

1. **`docs/zen/syntax-v0.ebnf`** — Gramática formal completa (~400 líneas)
   - Léxico: keywords, literales, operadores, comentarios
   - Tipos: primitivos, punteros (3 niveles), arrays, tuplas, funciones
   - Expresiones: precedencia completa (14 niveles), casting, postfix, match
   - Statements: let, const, assign, control flow, blocks
   - Top-level: functions, structs, impl, type aliases, modules, extern
   - Atributos y keywords reservadas

2. **`docs/zen/syntax-decisions.md`** — Rationale de decisiones (10 decisiones clave)
   - Comparación Rust/Zig/C
   - Keywords reservadas para fases futuras
   - Ambigüedades conocidas y soluciones propuestas

3. **Ejemplos en `zen/examples/`**:
   - `hello.zen` — Hello world mínimo
   - `factorial.zen` — Funciones, recursión, enteros, if/else
   - `structs.zen` — Structs, impl, métodos, referencias mutables

## Decisiones Arquitectónicas Clave

| Aspecto | Decisión | Alternativa Rechazada |
|---------|----------|----------------------|
| Function keyword | `fn` | `func`, `def` |
| Variables | `let mut` / `const` | `var`, inferencia implícita |
| Primitive types | Tamaño explícito (i32, u64, f64) | `int`, `uint`, `float` |
| Pointers | 3 niveles: `&T`, `*T`, `&&T` | Solo `*T` (Rust) |
| Raw pointer syntax | `&&T` (explícito unsafe) | `*const T` / `*mut T` |
| Casting | `expr as Type` | `(Type)expr`, `cast()` |
| Error handling | `Result<T,E>` + `?` | Exceptions, panic-only |
| Methods | `impl` separado | Inside struct |
| Modules | File-based + `mod`/`use` | Package-based |

## Ambigüedades Identificadas (Requieren Resolución en Parser)

1. **`x * y`** — Multiplicación vs deref en tipo (`*T` en contexto tipo)
2. **`foo < bar > (baz)`** — Comparison vs generic instantiation
3. **`ident { ... }`** — Struct literal vs block expression
4. **`::` vs `:`** — Path separator vs type ascription

**Solución propuesta**: Context-sensitive lexing o disambiguation en parser (lalrpop permite precedencia y asociatividad).

## Tests de Aceptación (Pendientes — TASK-106)

- `zen/tests/syntax/accept/` — Programas válidos MVP
- `zen/tests/syntax/reject/` — Programas inválidos con error esperado

## Próximas Acciones

1. **Revisión cruzada** por Agente 02 (Frontend) — Validar parseabilidad LR(1)
2. **TASK-202**: Implementar Lexer basado en esta gramática
3. **TASK-203**: Parser → AST con lalrpop
4. **TASK-102**: Definir tipos primitivos y layout en memoria (con Agente 05)

---

*Report generado por Agente 01 — Ver `AGENTS.md` para formato*