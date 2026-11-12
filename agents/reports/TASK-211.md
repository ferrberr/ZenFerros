# TASK-211 — Revisión independiente del compilador nativo

**Revisor**: compiler_review (distinto de los autores de frontend/lexer/CLI)
**Fecha**: 2026-11-11
**Estado**: COMPLETADA — revisión favorable del subconjunto Hito 1

## Alcance
Lectura independiente de `src/mvp.rs`, `src/native.rs`, `src/main.rs`, lexer, manifest y aceptación CLI. Se revisaron tipos, llamadas, mutabilidad, ámbitos, retornos, emisión C, enteros, evaluación, literales, publicación de binarios y errores externos.

## Hallazgo reproducido
- **P2: pila del compilador sin límite de profundidad**. Una expresión con 4.000 pares de paréntesis (~8 KiB) causa SIGABRT por stack overflow en `zen check` en lugar de un diagnóstico localizado. Fuente: `fn main()->i32 { return ` + `(` repetido 4000 + `0` + `)` repetido 4000 + `; }`. 100 y 1.000 pares se aceptan. Se notificó al orquestador y al autor. Prueba aislada en `/tmp/zenferros-task211-review`, subprocess con core dumps desactivados; no se generaron cores en el workspace. Se corrigió con límite de recursión del parser de 128 y límite independiente de profundidad de AST de 64, para proteger también emisión y destrucción del árbol. La revisión comprobó ambos límites en código.

## Evidencia ejecutada
1. Snapshot aislado: `rtk proxy env CARGO_HOME=/home/ferranfg/proyectos/ZenFerros/.cargo cargo build --offline --manifest-path /tmp/zenferros-task211-review/Cargo.toml`: compilación correcta (2,91 s).
2. Script Python independiente con semilla 211: 180 operaciones `+`, `-`, `*`, `/`, `%` para i32/i64/u64, comparadas con cálculo Python de wrapping y división truncada. Ejecuciones nativas `-O0` y `-O2`: estado 0 y `arithmetic verified` en ambas.
3. `rtk proxy env CARGO_HOME=/home/ferranfg/proyectos/ZenFerros/.cargo cargo test --offline --manifest-path zen/compiler/Cargo.toml`: **23 tests unitarios y 10 tests CLI, 0 fallos**, tras integrar la corrección (0,11 s + 0,21 s). Incluye ELF real, stdout, factorial, cortocircuito, orden de argumentos, ámbito y shadowing, errores semánticos/léxicos, preservación de archivo y fallo del compilador externo.

4. Verificación independiente de la corrección usando la CLI real del workspace, en CWD temporal y sin core dumps: 4.000 paréntesis, 4.000 negaciones, 4.000 operadores binarios, 4.000 bloques, 4.000 ramas else-if y mezcla de 400 if anidados: **6/6 rechazan con estado 1 y diagnóstico localizado de límite; 0 aborts/panics**.
5. Se leyeron README, ARCHITECTURE.md, docs/zen/mvp-native.md y ADR-007: anuncian el backend C y límites reales; no atribuyen freestanding, structs o rendimiento no verificados.

## Observaciones confirmadas
- C es un backend bootstrap explícito. Zen valida los tipos antes de ejecutar cc; las características no soportadas se rechazan.
- Temporales C preservan evaluación de operandos/argumentos; && y || emiten ramas de cortocircuito.
- Suma/resta/multiplicación signed usan operaciones unsigned y reinterpretación por memcpy. División y resto comprueban cero y MIN/-1 antes de operar.
- Identificadores Zen se renombran, evitando colisiones con keywords C o runtime. Strings usan longitud y conservan NUL/UTF-8.
- cc se invoca con argumentos sin shell; un fallo no reemplaza el ejecutable previo. Las pruebas verifican protección del archivo fuente.

## Límites
Revisión funcional del subconjunto del hito 1 para host Linux x86_64; no demuestra ausencia de todos los fallos, seguridad de memoria para futuras referencias, freestanding, ABI externo, rendimiento competitivo ni arranque Ferros. El análisis de retornos es conservador para bucles; programas que retornan solo desde `while true` necesitan retorno posterior o son rechazados.

## Dictamen
**Favorable para cerrar TASK-210 y Hito 1.** El único hallazgo P2 reproducido se corrigió y se verificó independientemente; no quedan hallazgos bloqueantes de esta revisión. La evidencia cubre el subconjunto hosted descrito y los límites indicados, sin afirmar estabilidad general o equivalencia con la gramática futura.
