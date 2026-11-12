# TASK-310: Hito 2 — Zen freestanding mínimo para x86_64

**Agente**: 00 Orquestador (toolchain/CLI/tests/docs), native_compiler (frontend/backend), compiler_review (revisión independiente).
**Estado**: COMPLETADA
**Prioridad**: ALTA
**Dependencias**: [TASK-210, TASK-211]
**Archivos**: [zen/compiler/src/mvp.rs, zen/compiler/src/native.rs, zen/compiler/src/main.rs, zen/compiler/tests/freestanding_cli.rs, zen/examples/freestanding.zen, infrastructure/freestanding/, docs/zen/, README.md, ARCHITECTURE.md, ROADMAP.md, agents/decisions/ADR-008.md, agents/reports/TASK-310*]

## Objetivo medible
Compilar Zen a objeto ELF x86_64 freestanding sin libc/runtime hosted; exportar/importar funciones con ABI C y expresar lógica de kernel: enteros fijos, bits/casts, acceso volatile explícitamente unsafe. Enlazar objeto sin bibliotecas y ejecutar prueba controlada del resultado; conservar regresión del Hito 1. El arranque de un kernel real corresponde al Hito 3.

## Contratos y propiedad
Frontend modifica solo src/mvp.rs en repo Git aislado /tmp/zenferros-task310-frontend rama task310-frontend. API retrocompatible check/emit_c, nuevas Mode::{Hosted,Freestanding}, check_with_mode/emit_c_with_mode. Orquestador modifica archivos restantes, integra entrega secuencialmente. Revisor no edita código, entrega informe TASK-311. Git del workspace sigue vacío/protegido; no se fingen merges.

## Criterios de aceptación / pruebas necesarias
- [x] build --target x86_64-unknown-none --emit obj genera ELF64 REL x86_64, sin startup hosted, libc ni dependencias implícitas; check en ese target no exige main.
- [x] pub fn exporta símbolo ABI C; extern "C" { fn ...; } importa funciones escalares/punteros compatibles sin colisiones de nombres.
- [x] u8/u16/u32 además de i32/i64/u64, casts explícitos y operaciones bitwise/shifts comprobados en normal/optimizado.
- [x] Cadenas estáticas con str_len/str_byte sin libc; builtins print hosted no disponibles en freestanding.
- [x] Punteros raw tipados *T/*mut T y volatile_load/volatile_store sujetos a unsafe; stores a const, tipos erróneos y accesos sin unsafe rechazados.
- [x] Runtime de freestanding sin libc ni memcpy implícito, traps de errores, sin red zone/PIE/stack protector/SIMD host; target y flags documentados.
- [x] Prueba enlazada -nostdlib sin intérprete dinámico/NEEDED, estado verificado; harness C confirma ABI, bits, volatile y strings. Ninguna instrucción privilegiada en host.
- [x] Pruebas hosted regresan; revisión cruzada favorable sin bloqueantes; métricas y comandos persistentes.

## Resultado esperado
Hito 2 verificado/integrado en subconjunto mínimo documentado; structs/arrays/inline asm/layout de kernel se amplían cuando Ferros los requiera. Informe breve al usuario y evidencia completa en agents/reports/TASK-310.md.

## Cierre — 2026-11-11
Evidencia en agents/reports/TASK-310.md y TASK-310-validation.log; revisión independiente favorable TASK-311.md. Hito 2 mínimo integrado, 46 tests por perfil pasan; boot/QEMU queda para Hito 3.
