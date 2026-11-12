# TASK-101: Diseñar gramática MVP Zen (EBNF)

**Agente**: 01 (Arquitecto Zen)
**Estado**: 🔄 EN_PROGRESO
**Prioridad**: ALTA
**Dependencias**: [TASK-008]

## Objetivo
Definir la gramática mínima viable (MVP) de Zen en notación EBNF, cubriendo:
- Tipos primitivos
- Funciones
- Variables y binding
- Operadores básicos
- Control de flujo (if, while, return)
- Estructuras (struct)
- Punteros y referencias
- Módulos y imports
- Modelo de errores básico

## Criterios de Aceptación
- [ ] Gramática EBNF completa en `docs/zen/syntax-v0.ebnf`
- [ ] Ejemplos de programas válidos en `zen/examples/`
- [ ] Tests de aceptación sintáctica (lista de casos) en `zen/tests/syntax/`
- [ ] Documentación de decisiones de sintaxis en `docs/zen/syntax-decisions.md`

## Sub-tareas
1. Definir léxico: keywords, operadores, literales, identificadores
2. Definir tipos: primitivos (i8..i64, u8..u64, f32, f64, bool, char, never), punteros, arrays, tuples, structs
3. Definir expresiones: literales, variables, calls, binary/unary ops, casting, indexing, field access
4. Definir statements: let, assign, if, while, return, break, continue, block, expr stmt
5. Definir funciones: signature, body, generics (básico), calling convention
6. Definir structs: fields, methods, impl blocks
7. Definir módulos: mod, use, visibility (pub)
8. Definir error handling: Result/Option, ? operator, panic

## Principios de Diseño (según PROMPT MAESTRO)
- Clara, concisa, expresiva
- Fácil de analizar (LR(1) preferible)
- Predecible, sin ambigüedades
- Compatible con optimización agresiva
- No copia superficial de Rust/Zig — originalidad con beneficio técnico

## Estado Actual
- Investigación de sintaxis en progreso
- Próxima entrega: borrador EBNF para revisión cruzada (Agente 02)

## Archivos a Crear/Modificar
- `docs/zen/syntax-v0.ebnf` — Gramática formal
- `docs/zen/syntax-decisions.md` — Rationale
- `zen/examples/hello.zen` — Programa ejemplo
- `zen/examples/factorial.zen` — Programa con funciones/recursion
- `zen/examples/structs.zen` — Structs y métodos
- `zen/tests/syntax/accept/*.zen` — Casos válidos
- `zen/tests/syntax/reject/*.zen` — Casos inválidos (con error esperado)

---

*Tarea creada por Orquestador — Ver `AGENTS.md` para protocolo*