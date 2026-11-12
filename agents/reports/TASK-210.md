# TASK-210: Hito 1 completado — Zen compila y ejecuta programas nativos

**Fecha**: 2026-11-11
**Estado**: COMPLETADA / INTEGRADO
**Responsables**: 00 (integración, CLI, aceptación), native_compiler (frontend/backend), lexer_hardening (lexer), compiler_review (revisión independiente).

## Resultado verificable

Archivo Zen → lexer → parser/AST MVP → nombres/tipos/ámbitos/retornos → C11 → cc → ELF Linux x86_64 → salida comprobada. `hello.zen` imprime `Hello, Zen!\n`; `factorial.zen` imprime `factorial(10) = 3628800\n`. Ambos devuelven 0 en -O0 y -O2. Se verificó cabecera ELF (`7f 45 4c 46`) y se ejecutaron los binarios generados.

El compilador release queda en `zen/compiler/target/release/zen`; los cuatro programas de muestra se conservan en `zen/compiler/target/milestone-1/`. El hito no implica freestanding ni kernel.

## Cambios

- Frontend ejecutable autocontenido `src/mvp.rs`: funciones/recursión, i32/i64/u64/bool/str/void, parámetros y nombres, scopes, let/let mut, inferencia local, asignaciones, if/else, while/break/continue, retornos explícitos y builtins de salida.
- Validación antes de cc; errores con spans y CLI con ruta/línea/columna. Tipos y rangos estrictos, datos no soportados rechazados.
- Emisión C con nombres internos, temporales ordenados, cortocircuito, strings con longitud, wrapping sin overflow firmado de C y fallo controlado de división/resto inválidos.
- CLI real build/run/check/lex/version; run propaga estado, build conserva salida previa en error y protege fuente. Retirados subcomandos que anunciaban éxito sin implementar.
- Backend C de bootstrap (ADR-007), manifest reducido a dependencias usadas y lockfile regenerado offline. Sin dependencias nuevas descargadas; .gitignore excluye caché y target.
- Lexer corregido (TASK-212): literales inválidos/sufijos/rangos/escapes/EOF, operadores .. y ..., comentarios iterativos y spans UTF-8.
- README, arquitectura y roadmap reconciliados con código activo y límites documentados.

## Comandos y salida

Desde la raíz del workspace:

```text
rtk proxy env CARGO_HOME=/home/ferranfg/proyectos/ZenFerros/.cargo cargo generate-lockfile --offline --manifest-path zen/compiler/Cargo.toml
Locking 34 packages to highest compatible versions

rtk proxy env CARGO_HOME=/home/ferranfg/proyectos/ZenFerros/.cargo cargo test --offline --manifest-path zen/compiler/Cargo.toml
Finished test profile in 0.50s (incremental tras arreglo)
23 passed; 0 failed (unitarios, 0.11s)
10 passed; 0 failed (aceptación CLI, 0.21s)
0 doc tests; 0 failed

rtk proxy env CARGO_HOME=/home/ferranfg/proyectos/ZenFerros/.cargo cargo build --release --offline --manifest-path zen/compiler/Cargo.toml
Finished release profile in 6.08s (primer build release)

rtk proxy env CARGO_HOME=/home/ferranfg/proyectos/ZenFerros/.cargo cargo test --release --offline --manifest-path zen/compiler/Cargo.toml
Finished release profile in 4.04s (incluye compilación de tests y arreglo)
23 passed; 0 failed (unitarios, 0.01s)
10 passed; 0 failed (aceptación CLI, 0.21s)
0 doc tests; 0 failed

rtk proxy rustfmt --edition 2021 --check zen/compiler/src/mvp.rs zen/compiler/src/main.rs zen/compiler/src/native.rs zen/compiler/tests/native_cli.rs zen/compiler/src/lexer/scanner.rs zen/compiler/src/lexer/tests.rs
exit 0
```

Los diez tests CLI contienen múltiples casos: ELF y ejecución directa, factorial normal/optimizado, scopes y loops, efectos de llamadas y cortocircuito, C keywords/NUL/UTF-8, estado 37, check sin cc, veinte entradas inválidas, preservación de artefacto y fuente, división/resto inválidos. Hay 33 tests por perfil, todos pasan. No se contabilizan casos internos como tests independientes.

## Fallos encontrados y corrección

- El lexer heredado incluía un test que esperaba el error de implementación de `..`; se corrigieron código y expectativas. Anteriormente números inválidos podían volverse cero o perder sufijos, y una cadena en EOF podía aceptarse.
- El primer test nuevo del agente lexer tuvo un error de préstamo Rust; corregido antes de integrar. No hubo tests de aceptación fallidos tras integración.
- Revisión TASK-211 detectó SIGABRT de `zen check` con 4000 paréntesis. Se limitó la recursión del parser a 128 y AST de expresiones a 64; entradas excesivas producen CompileError localizado. Test de regresión y seis reproducciones CLI verificadas independientemente.
- La revisión no deja hallazgos bloqueantes. Ver informe TASK-211 para método de 180 casos aritméticos independientes y resultados normales/optimizados.

## Métricas observadas (una ejecución, no benchmark comparativo)

| Programa | Flags C | Compilación total s | ELF bytes | Estado |
|----------|---------|--------------------|-----------|--------|
| hello | -O0 | 0.037313 | 17056 | 0 |
| hello | -O2 | 0.033472 | 16104 | 0 |
| factorial | -O0 | 0.036476 | 17088 | 0 |
| factorial | -O2 | 0.038247 | 16192 | 0 |

Compilador release: 1062440 bytes. Entorno: Linux 7.2.11-arch1-1 x86_64; rustc 1.99.1; Cargo 1.99.1; cc GCC 16.2.1. Tiempos observados de frontend + compilador C + enlace, sin separar etapas. No se midieron pico de memoria (`time` externo no disponible), latencias p95/p99, asignaciones, caché o energía. Sin comparación con otros lenguajes ni afirmación de optimización.

Comandos exactos, stdout y estados en `TASK-210-validation.log`; métricas estructuradas en `TASK-210-metrics.json`. Las ejecuciones de medición se lanzaron con subprocess sin shell desde una invocación `rtk proxy python3`.

## Integración y revisión

El `.git/` visible del workspace está vacío y protegido: `git status` devuelve not a git repository. No se creó historial ficticio ni se declaró merge. Los agentes implementaron en repositorios temporales aislados `/tmp/zenferros-task210-frontend` (rama task210-frontend; commit final 79eb51c) y `/tmp/zenferros-task212-lexer` (rama task212-lexer). El orquestador copió entregas secuencialmente a archivos de propiedad exclusiva; reviewer no editó implementación. Revisión cruzada de código crítico favorable en TASK-211.

## Límites y siguiente objetivo

Subconjunto hosted, sin structs/flotantes/punteros/ownership/módulos/FFI, sin argv accesible desde Zen, sin freestanding ni arranque Ferros, sin estabilidad/estrés general ni optimización propia. Los borradores AST/parser históricos no se compilan. Documentación completa del subconjunto: `docs/zen/mvp-native.md`.

Hito 1 alcanzado. Próximo objetivo: objeto freestanding sin libc y ABI externa mínima para Hito 2; después bootloader/QEMU con código de kernel Zen. QEMU no aparece en PATH de esta sesión y debe revalidarse antes del Hito 3; historial Git persistente pendiente del entorno.
