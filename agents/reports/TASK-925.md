# TASK-925 — CLI mínima parcial del compilador en Zen

**Estado**: REVISION (pendiente de integración por el orquestador).
**Responsable**: agente `selfhost_cli`, roles 02 Frontend / 03 Backend.
**Dependencia**: TASK-902K. Base Git: `e7737a6`.
**Rama aislada**: `task-925-selfhost-cli`, clon `/tmp/zenferros-task925`.

## Contrato y resultado

Objetivo medible: leer un archivo Zen real, emitir C11 compilable y comparar
exactamente su ejecución con el compilador Rust sobre el mismo subconjunto.
Resultado: CLI en Zen que integra lexer materializado → lowering del subconjunto
real → parser/typechecker/codegen existente en Zen; genera C en stdout. El
fixture versionado `zen/selfhost/tests/fixtures/cli/sum.zen` imprime `45` por
ambas rutas. No se declara autohosting completo.

Archivos afectados:

- `zen/selfhost/cli.zen`: selección de argumentos, fases, buffers, lowering,
  comprobaciones de mutabilidad y anotaciones, salida y errores en Zen.
- `zen/selfhost/cli_io.c`: 33 líneas de puente libc, sin parser ni generación.
- `zen/selfhost/build_cli.py`: concatenación/compilación bootstrap, fuera del
  proceso final. No invoca compiladores al ejecutar la CLI resultante.
- `zen/selfhost/codegen_structs.zen`: punto de entrada estricto para Zen real;
  el entrypoint histórico conserva el dialecto anterior.
- `zen/selfhost/tests/test_selfhost_cli.py` y fixture real: ocho pruebas.
- `docs/zen/selfhost.md`: contrato, uso, límites y componentes no integrados.

El worktree gestionado se creó correctamente en
`/home/ferranfg/.codex/worktrees/task-925-selfhost-cli/ZenFerros`, pero el sistema
de archivos lo hizo read-only. Tras avisar al orquestador se usó un clon Git
con rama propia en `/tmp`, sin modificar el checkout compartido. El primer
`git clone --local` falló por hardlink entre dispositivos; `git clone
--no-hardlinks` funcionó. No hubo bloqueo persistente de desarrollo.

## Verificación y salida

Bootstrap usado (solo lectura):
`/home/ferranfg/proyectos/ZenFerros/zen/compiler/target/release/zen`.
Para las pruebas históricas, que fijan esa ruta relativa, se añadió un symlink
local ignorado en `zen/compiler/target/release/zen`. No se construyó sobre el
target compartido ni se modificó el compilador Rust.

```bash
ZEN=/home/ferranfg/proyectos/ZenFerros/zen/compiler/target/release/zen \
  python3 -m unittest discover -s zen/selfhost/tests -p test_selfhost_cli.py -v
# 8 tests OK

ZEN=/home/ferranfg/proyectos/ZenFerros/zen/compiler/target/release/zen \
  python3 -m unittest discover -s zen/selfhost/tests -v \
  > /tmp/task925-selfhost-tests-final.log 2>&1
# Ran 174 tests in 10.363s
# OK

rg -n 'skip|FAIL|ERROR' /tmp/task925-selfhost-tests-final.log
# Sin coincidencias: 0 skips, 0 failures, 0 errors.

git diff --check
# Sin salida.

python3 zen/selfhost/build_cli.py \
  --zen /home/ferranfg/proyectos/ZenFerros/zen/compiler/target/release/zen \
  -o /tmp/task925-cli
/tmp/task925-cli zen/selfhost/tests/fixtures/cli/sum.zen > /tmp/task925-sum.c
cc -std=c11 -O2 -Wall -Wextra -Werror /tmp/task925-sum.c -o /tmp/task925-sum
/tmp/task925-sum
# 45, sin salto de línea
```

Las 8 pruebas contienen **19 positivos** (18 cuerpos y un archivo real),
**25 negativos** rechazados por ambos compiladores y **8 programas válidos para
Rust fuera del subconjunto** rechazados limpiamente por la CLI. Los positivos
compilan el C generado con `-O0` y `-O2`, ejecutan ambas variantes, compilan y
ejecutan el mismo archivo con Rust y comparan estado/stdout/stderr exactos.
También verifican determinismo, `PATH=/nonexistent` (sin depender de procesos
Rust/cc en ejecución), ausencia de C parcial por errores de compilación,
entrada de 65.536 bytes y rechazo de 65.537, límites de tokens y E/S.

La suite completa incluye los **19 tests históricos de TASK-902K**, preservando
el entrypoint de su dialecto. No se requiere cambiar esas expectativas.

Las primeras comparaciones detectaron divergencias del dialecto anterior:
asignación a escalar inmutable, negación unaria u64 y orden entre bool. Se
corrigieron y quedaron como negativos diferenciales. Las anotaciones de tipo
se preservan con comprobaciones auxiliares sin efectos. Los literales del
cuerpo exigen sufijo u64 explícito para evitar diferencias de inferencia i32.

## Métricas

Medición local informativa, no benchmark:

- CLI enlazada: **234.560 bytes**; `size`: text 220.036, data 632, bss 48.
- Fixture de suma: **720 bytes C**, ejecución de compilación ~**0,0013 s**
  wall clock medidos con `time.perf_counter` alrededor de `subprocess.run`.
- Fuente nueva de CLI: 272 líneas Zen y 33 líneas C; reutiliza 645 líneas del
  lexer de tokens y el codegen de structs (2.750 líneas tras el modo estricto).
- Suite completa: 174 tests, 10,363 s en este host. Memoria pico y rendimiento
  sostenido no caracterizados; no se presentan como límites operativos.

## Revisión cruzada

El orquestador `/root`, distinto del autor, revisó el flujo y la suite inicial
sin encontrar bloqueo. La revisión quedó condicionada al último diff del modo
estricto para comparaciones ordenadas de bool; se le envió ese diff y la
regresión de 174 tests para validación final. La integración sigue pendiente;
no se hizo merge ni se modificó el estado de la tarea compartida.

## Riesgos y límites

- Entrada real deliberadamente menor que Rust: solo main final `return 0`,
  locales anotados u64/bool, asignación, +/−/*, bool/comparaciones, if/else,
  while y print_uint. Una comparación textual por expresión/condición.
- Sin funciones de usuario, structs/arrays de entrada real, strings, casts,
  bitwise, división/resto, break/continue ni retornos interiores. Los demás
  componentes selfhost mantienen sus pruebas separadas.
- Buffers acotados: entrada 64 KiB, tokens 2048, lowering 128 KiB, C 1 MiB;
  las comprobaciones añadidas pueden agotar antes los tokens/nodos del codegen.
- Mensajes sin spans; léxico y límite del lexer comparten estado 5. Uso/E/S/
  memoria y tamaño de archivo comparten estado 2. Una avería de stdout puede
  publicar parte de la salida, como en cualquier escritura de un flujo.
- Solo host x86_64 Linux/libc; no se valida ejecución del compilador en Ferros.
- Rust sigue siendo necesario para el bootstrap y la referencia. No se compila
  esta CLI consigo misma y no hay selfhosting completo ni AST unificado.
