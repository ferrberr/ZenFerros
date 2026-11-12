# Estabilidad acotada — TASK-905

Fecha: 2026-11-11. Este documento acompaña a
[`infrastructure/scripts/stress.py`](../infrastructure/scripts/stress.py), que
añade evidencia de estabilidad **más allá de la regresión funcional** sin
modificar la puerta de [`quality.md`](quality.md) ni declarar ningún subsistema
como *Estable*.

`stress.py` es complementario a `verify_all.py`: la puerta comprueba que el
estado actual pasa una vez; el estrés repite arranques, entradas y suites, y
hace fuzzing diferencial acotado del lexer y el parser self-hosted (no de los once componentes). No está
conectado a la puerta ni a CI: se ejecuta a mano. No es una campaña de
estabilidad continua ni una certificación.

## Qué demuestra

- **Repetición multi-perfil**: compila Ferros en debug y release y arranca QEMU
  alternando ambos perfiles. Con los valores por defecto son 6 arranques: cada
  uno de los tres guiones se ejecuta una vez en debug y otra en release.
- **Entradas diversas**: además del guion canónico del shell, ejercita el
  camino sin entrada y comandos inválidos. Los tres terminan con estado 33, sin
  `PANIC`, sin `stderr` y con los marcadores esperados.
- **Repetición de suites**: las suites de Ferros y de self-hosting se ejecutan
  varias veces; se registra tiempo, resultado y el número de tests que descubre
  `unittest` en cada ronda (el script no fija esa cifra).
- **Fuzz diferencial acotado**: 200 expresiones aleatorias con semilla fija
  contra la referencia recursiva Python del parser self-hosted, y 200
  mutaciones de fixtures canónicas contra `zen lex` para el lexer. Las
  expresiones se compilan una sola vez (`parser.zen` + driver C) y las
  mutaciones se comparan contador a contador.
- **Determinismo de la campaña**: la semilla por defecto es `905`. Los casos
  generados son reproducibles; los tiempos no (dependen de la carga del host).
- **Aislamiento de artefactos**: builds, logs y resumen viven en un directorio
  temporal (`/tmp/zenferros-stress-*`). El script no escribe en el repositorio y
  ejecuta los QEMU en secuencia, nunca en paralelo.

## Contrato de los arranques

`stress.py` reutiliza `build_ferros.build_kernel` y `boot_ferros.boot`; no
duplica la lógica de build ni la captura de QEMU. Para los guiones que no son
el canónico, `boot()` rechaza la transcripción (su validador exige el guion por
defecto); el script captura ese rechazo esperado y valida las propiedades sobre
`serial.log` y `result.json`, que el runner ya guarda.

| Guion | Payload | Validación además de estado 33, `stderr` vacío y ausencia de `PANIC` |
|---|---|---|
| `default` | `DEFAULT_INPUT` (`ls\ncat hello.zen\nhelp\nexit\n`) | La validación normal del runner: transcripción exacta, `writes=18`, `runs=7`, `rejected=6`, estadísticas y orden. |
| `sin-entrada` | `input=None` | `SHELL: READY`, `SHELL: NO INPUT` y `SHELL: DONE`; no debe aparecer `UNKNOWN COMMAND`. |
| `comandos-invalidos` | `b"bogus\ncat nope.zen\nexit\n"` | `SHELL: READY`, `SHELL: UNKNOWN COMMAND`, `SHELL: FILE ERROR` y `SHELL: DONE`; no debe aparecer `NO INPUT`. |

La asignación es determinista: en el arranque `i` (0-based), el perfil es debug
si `i` es par y release si es impar; el guion es
`default`, `sin-entrada`, `comandos-invalidos` ciclando en ese orden. Con 2
arranques (`--quick`) se cubren `default` (debug) y `sin-entrada` (release); el
guion de comandos inválidos se cubre en la campaña completa.

Cada arranque usa `--boot-timeout` (15 s por defecto). Un timeout, un estado
distinto de 33, `stderr` no vacío o cualquier `PANIC` hacen fallar la fase.

## Repetición de suites

| Suite | Rondas por defecto | `--quick` | Timeout por ronda |
|---|---:|---:|---:|
| `python3 -m unittest discover -s ferros/tests` | `--rounds` (2) | 1 | 900 s |
| `python3 -m unittest discover -s zen/selfhost/tests` | 2 | 1 | 300 s |

`--rounds` solo afecta a Ferros; selfhost mantiene 2 rondas (1 con `--quick`).
Cada ronda guarda su log y se ejecuta con `PYTHONDONTWRITEBYTECODE=1`. La suite
de Ferros incluye sus propios guests QEMU; por eso las rondas y los arranques
del estrés se ejecutan estrictamente en secuencia.

## Fuzz diferencial del parser

- Se compila **una vez** `zen/selfhost/parser.zen` a objeto freestanding con el
  compilador `zen` y se enlaza con `zen/selfhost/parser_driver.c` usando `cc`.
- La referencia se importa por ruta con `importlib` desde
  [`test_selfhost_parser.py`](../zen/selfhost/tests/test_selfhost_parser.py).
  Ese test expone `reference(expression) -> (status, value)`, así que el script
  **no replica la gramática**. Si desapareciera `reference()` pero siguiera
  `ReferenceParser`, se usa su método `parse()` con un aviso; si no hubiera
  ninguna de las dos APIs, el script falla explícitamente en vez de comparar
  contra una semántica inventada.
- Los casos son deterministas con la semilla: incluyen expresiones válidas con
  precedencia, paréntesis, unarios, `/` y `%`, literales u64 grandes y límites
  de profundidad 64/65; también expresiones vacías, truncadas o con errores
  léxicos/sintácticos, y divisiones por cero.
- Se compara `(status, value)` línea a línea. Cualquier discrepancia falla y
  deja el caso, la expresión y ambos resultados en un fichero de detalle.

## Fuzz diferencial del lexer

- Se compila **una vez** `zen/selfhost/lexer.zen` y su driver C.
- Las fixtures canónicas y el fixture sintético se importan de
  [`test_selfhost_lexer.py`](../zen/selfhost/tests/test_selfhost_lexer.py)
  (`FIXTURES` y `SYNTHETIC`), junto con la tabla de categorías usada por el
  test.
- Cada caso muta bytes de una fixture: añade un fragmento léxicamente válido,
  inserta una porción de otra fixture, reemplaza/inserta/borra bytes ASCII, o
  sustituye un byte dentro de un comentario, string o literal de carácter por
  un carácter UTF-8 multibyte.
- Para cada fuente se ejecuta `zen lex`:
  - si `zen lex` devuelve un código distinto de cero o emite un token `Error`,
    **no se comparan contadores** y el caso se contabiliza como omitido;
  - si la fuente sigue siendo válida, se comparan los ocho contadores
    (`tokens`, `idents`, `numbers`, `strings`, `keywords`, `punct`, `errors`,
    `bytes`) entre el driver self-hosted y `zen lex`.
- **Tolerancia documentada**: una discrepancia solo se tolera cuando la fuente
  contiene bytes no ASCII y `zen lex` la acepta. El lexer Zen recorre bytes, no
  caracteres Unicode; por ejemplo, un literal `'é'` cuenta distinto aunque la
  fuente sea válida para el lexer Rust. Estos casos se cuentan y se registran en
  `fuzz/lexer/tolerated.log`; no se ocultan. Una discrepancia en una fuente
  puramente ASCII falla.
- **Valores numéricos**: `zen lex` rechaza literales enteros o flotantes
  desbordados (sale con error), así que esos casos caen en “omitidos” y no se
  comparan contadores. No se aplica ninguna tolerancia numérica adicional.
- El primer caso es siempre un literal de carácter multibyte válido para
  `zen lex`, de modo que la ruta de tolerancia UTF-8 se ejercita en cada
  campaña; con el lexer actual se observa `toleradas UTF-8: 1`.

## Resultados observados

Host de desarrollo, QEMU TCG, 2026-11-11. Los tiempos no son un benchmark y
varían con la carga del host.

| Fase | `--quick` | Campaña completa |
|---|---:|---:|
| Build debug+release | 1,00 s | 0,99 s |
| Arranques QEMU | 1,96 s (2) | 4,85 s (6) |
| Suite Ferros | 20,15 s (1 ronda) | 40,34 s (2 rondas) |
| Suite selfhost | 0,27 s (1 ronda) | 0,80 s (2 rondas) |
| Fuzz parser | 0,09 s (20 casos) | 0,10 s (200 casos) |
| Fuzz lexer | 0,16 s (20 casos) | 0,58 s (200 casos) |
| **Total** | **≈24,9 s** | **≈50,7 s** |

Resultado de la campaña completa:

- 6/6 arranques `status=33`, `stderr` vacío y sin `PANIC`; los dos `default`
  con `runs=7`, `writes=18`, `rejected=6`.
- Ferros 44/44 tests en las dos rondas; selfhost completo en las dos rondas
  (166 tests en la ejecución final, un directorio compartido que puede crecer
  durante el ciclo). El script no codifica los recuentos: registra los que
  descubre `unittest` en cada ronda y los guarda en su log.
- Parser: 200 expresiones, 100 válidas y 100 con error, sin discrepancias
  frente a la referencia.
- Lexer: 200 mutaciones; 161 comparadas, 38 omitidas porque `zen lex` rechaza
  la fuente y 1 tolerada por UTF-8 (el literal `'é'`); ninguna discrepancia no
  tolerada.
- En `--quick`: 20 expresiones (9 válidas, 11 con error) y 20 mutaciones
  (15 comparadas, 4 omitidas, 1 tolerada), también sin fallos.

## Qué NO demuestra

- El intérprete selfhost no se fuzzea en esta campaña; solo se ejecutan sus tests.
- `while 1 {}` en el intérprete termina por el límite de 1.000.000 de pasos (estado 4), no es un test de progreso justo.

- **Hardware físico, KVM y UEFI/ISO**: todo es QEMU TCG con `-smp 1`; no hay
  `/dev/kvm`, metal, ISO ni arranque UEFI.
- **SMP y concurrencia real**: un solo CPU, sin IRQ anidadas, sincronización,
  barreras ni carreras. La repetición no convierte el scheduler en concurrente.
- **Persistencia**: RAMFS es volátil; no se prueba reinicio con estado, ni
  VirtIO block, ni monturas.
- **Campañas largas o inyección de fallos a escala**: 6 arranques, 2 rondas y
  200 casos por fuzz son una muestra acotada, no horas de ejecución ni fault
  injection, caos, ni pruebas de recuperación.
- **Cobertura del shell o del kernel**: solo se ejercitan tres guiones de
  entrada. No hay fuzzing del protocolo serie, del kernel ni de los drivers.
- **Self-hosting completo**: se ejecutan las suites de los once componentes (lexer contador, lexer con tokens, evaluador, AST, intérprete de sentencias, intérprete de funciones, typechecker, codegen, codegen con funciones, codegen con arrays y codegen con structs); solo lexer y parser tienen fuzz diferencial. El compilador completo sigue en Rust y no se hace bootstrap.
- **Fuzzing guiado por cobertura**: las mutaciones y expresiones son aleatorias
  con semilla fija; no hay corpus minimizado, cobertura, sanitizers ni
  comparación de valores de token (el lexer solo compara contadores).
- **Seguridad**: no es una auditoría, no busca vulnerabilidades ni hace threat
  modeling; la tolerancia UTF-8 es una limitación conocida, no una garantía.
- **Rendimiento**: los tiempos son de una ejecución concreta y no se comparan
  con líneas base; no hay `perf`, ciclos ni instrucciones.
- **Procedencia reproducible**: no hay `.git` útil, commit, bisect ni CI
  remoto. La evidencia son los archivos y las salidas de este host.

Por tanto, este trabajo **no cambia el nivel de madurez** de
[`quality.md`](quality.md) ni declara *Estable* u *Optimizado* ningún
subsistema. La tabla de `quality.md` refleja TASK-905 como parcial (campaña acotada); este
documento aporta la evidencia y los límites de esa campaña.

## Reproducción

Requisitos: Python 3.10 o posterior, QEMU local en `.tools/qemu` (o en `PATH`),
el compilador `zen/compiler/target/release/zen` ya construido, y `cc`, `ld`,
`objcopy` y `nm`. El script no compila Rust ni descarga nada.

```bash
# Campaña rápida: 2 boots, 1 ronda por suite, 20 casos por fuzz (<60 s)
python3 infrastructure/scripts/stress.py --quick

# Campaña completa: 6 boots, 2 rondas de Ferros, 2 de selfhost, 200 por fuzz
python3 infrastructure/scripts/stress.py

# Campaña intermedia o con otra semilla
python3 infrastructure/scripts/stress.py --boots 3 --rounds 1 --fuzz-cases 50 --seed 905
```

Opciones: `--boots`, `--rounds`, `--fuzz-cases`, `--seed`, `--boot-timeout`
(15 s por defecto) y `--qemu RUTA`. Los valores por defecto son 6 boots,
2 rondas de Ferros, 2 de selfhost y 200 casos por fuzz; `--quick` los reduce a
2, 1, 1 y 20 salvo que se indiquen explícitamente.

Salida y códigos:

- `0`: todas las fases PASS; `1`: primer fallo (las fases siguientes no se
  ejecutan); `2`: argumentos inválidos; `130`: cancelado con Ctrl+C.
- Logs por fase dentro del directorio temporal que imprime el encabezado:
  `build/{debug,release}/build.log`, `logs/boots/boot-*`, `logs/suites/*.log`,
  `fuzz/parser/` (casos y `driver.log`) y `fuzz/lexer/` (casos, logs y
  `tolerated.log`).
- `summary.json` en ese mismo directorio contiene el resultado, los tiempos por
  fase y la configuración de la campaña.

No ejecutar otro QEMU en paralelo: el script ya secuencia sus arranques y la
suite de Ferros, pero dos campañas simultáneas competirían por CPU y podrían
alterar timeouts y tiempos observados.
