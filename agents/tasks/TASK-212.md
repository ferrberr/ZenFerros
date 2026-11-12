# TASK-212: Endurecer lexer para compilación real

**Agente**: Lexer (subagente lexer_hardening)
**Estado**: COMPLETADA
**Prioridad**: ALTA
**Dependencias**: [TASK-202]
**Archivos**: [zen/compiler/src/lexer/scanner.rs, zen/compiler/src/lexer/tests.rs]

## Objetivo / propiedad
Corregir errores léxicos que actualmente se aceptan silenciosamente. Trabajar en Git aislado /tmp/zenferros-task212-lexer, rama task212-lexer. Integración secuencial por orquestador; no modificar API pública Token/Lexer.

## Criterios de aceptación / pruebas
- Números inválidos, sufijos desconocidos, overflow u128, strings sin cerrar y escapes inválidos generan TokenKind::Error.
- Operadores .. y ... correctos sin consumir el siguiente carácter.
- Muchos comentarios consecutivos se procesan sin recursión de pila.
- Tests previos corregidos cuando codificaban fallos; regresión automatizada de errores y UTF-8.

## Resultado / evidencia
Archivo scanner.rs y tests.rs entregados, comandos y resultado de pruebas registrados en informe TASK-210 y revisión independiente TASK-211.

## Cierre — 2026-11-11
Evidencia: `agents/reports/TASK-210.md`, métricas JSON y log de ejecución; revisión independiente favorable en `agents/reports/TASK-211.md`.
