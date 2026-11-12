# Madurez por subsistema — revisión con evidencia (corte 0.1.1, 2026-11-12)

Este documento es una **auditoría de madurez**, no una certificación. Revisa qué
nivel sostiene la evidencia disponible para cada subsistema de Zen + Ferros,
con fecha y enlace, y aplica una regla explícita para no subir de nivel sin
pruebas. Complementa a [`docs/quality.md`](quality.md): `quality.md` declara el
estado y la puerta; este documento justifica fila a fila y señala lo que **no**
se demuestra. No modifica `quality.md`, no ejecuta código nuevo y no introduce
benchmarks.

**Conclusión de la revisión:** **0 subsistemas en `Estable` y 0 en
`Optimizado`**. La campaña de estabilidad y los benchmarks existentes son
evidencia acotada, no una base suficiente para esos niveles.

**Vigencia del corte:** 2026-11-12, 09:28 CET, árbol con **163/43/6/166** tests
(**378** en total) que pasó `verify_all.py --full` en **8/8 PASS (1m 09,0 s)**,
con **6/6** arranques QEMU en estado 33 y `repro_build.py` completo **PASS** en
1,97 s sin discrepancias. Es el corte de la release **0.1.1**
([`CHANGELOG.md`](../CHANGELOG.md), [`release.md`](release.md)). El corte 0.1.0
(151/39/6/147) queda como histórico.

**Posterior al corte:** TASK-919 (ZENFS01 visible en VFS/shell, read-only)
estaba en curso y, tras congelar el corte, el árbol cambió en `vfs.zen`,
`storage_fs.zen` y `main.zen` (ficheros de TASK-919); no se evalúa aquí. 0.1.1
se corta **antes** de esa integración y PFS-en-VFS queda para 0.1.2. No se
declara un nivel nuevo por trabajo no verificado.

## Definiciones y regla de promoción

Se usan los niveles acumulativos de [`AGENTS.md`](../AGENTS.md), con el mismo
significado que en [`docs/quality.md`](quality.md):

| Nivel | Criterio mínimo |
|---|---|
| Experimental | Prototipo que compila; sin suite funcional completa. |
| Verificado | Pasa tests funcionales automatizados del subsistema. |
| Integrado | Además funciona con los componentes vecinos en la ruta real (CLI, kernel/QEMU). |
| Estable | Regresión sostenida y estrés/fallos inyectados a escala, con límites y fallos conocidos documentados. |
| Optimizado | Benchmarks reproducibles y una mejora medida, atribuible y justificada, sin regresión funcional. |

Reglas de esta auditoría:

1. **No se hereda el nivel.** Un subsistema no es `Integrado` porque lo sea su
   vecino, ni `Estable` porque la puerta pase una vez. Cada fila cita su propia
   evidencia y su fecha.
2. **Sin fecha ni comando reproducible no hay nivel.** Un informe histórico sin
   ejecución actual se cita como evidencia de la fecha que declara, no como
   estado presente.
3. **`Estable` exige más que la campaña actual.** Como mínimo: **3 campañas
   full** en un entorno no compartido (no campañas quick ni host compartido),
   inyección de fallos a escala o estrés sostenido, una ventana de regresión a
   través de varios cambios y un registro de fallos conocidos con su
   recuperación. Ni las 5 quick + 2 full de TASK-913, ni las 10 quick + 3 full
   de TASK-917, ni las 2 full del corte 0.1.1 cumplen: son acotadas, con semilla
   fija, host compartido, sin fault injection y sin cobertura.
4. **`Optimizado` exige una mejora aplicada y medida.** No basta con que exista
   un benchmark ni con una decisión de flags. Se necesita un antes/después
   reproducible con al menos 3 repeticiones y control del ruido del host, una
   mejora que no sea ruido y la regresión funcional preservada. Medir
   `-O3`/LTO y decidir mantener `-O2` es una decisión justificada (ADR-015), no
   una optimización aplicada.
5. **Los niveles no se suben por número de tests.** 163 tests del compilador o
   166 de self-hosting acreditan cobertura funcional, no estabilidad ni
   rendimiento.

## Estado actual por subsistema (corte 0.1.1)

| Subsistema | Nivel | Evidencia concreta (fecha) | Límite declarado |
|---|---|---|---|
| Lexer del compilador (Rust) | **Integrado** | 163 tests del compilador (34 unitarias + 11 binarios de integración), incluidos lexer/errores; TASK-210/211 (2026-11-11); contraste con el lexer selfhost en 40 comparaciones de 8 contadores. | Subconjunto MVP; UTF-8 fuera de strings/comentarios y recuperación de errores tienen límites documentados. |
| Parser, AST, nombres y typechecker MVP | **Integrado** | 163 tests; casos negativos y de aceptación; TASK-210/211, TASK-213/214, TASK-915 (2026-11-11); [`docs/zen/mvp-native.md`](zen/mvp-native.md). | Sin floats, módulos, ownership, métodos ni paso de structs/arrays por ABI; slices solo como parámetro; un solo archivo salvo `use` textual. |
| Emisión C11 y enlace hosted | **Integrado** | 163 tests, incluidos 11 CLI nativos, 9 arrays, 12 slices y 15 structs; ELF hosted y ejecución real; TASK-210/310 (2026-11-11), TASK-915 (2026-11-11). | Depende de `cc` del host; sin LLVM propio ni compilación cruzada general. |
| CLI `build`/`run`/`check`/`lex` + `fmt`/`lint`/`lsp` + `use` | **Integrado** | 163 tests: 11 CLI, 10 `fmt`, 18 lint, 12 LSP, 10 include; TASK-904A, TASK-909, TASK-910, TASK-912 (2026-11-11). | Sin `zen test`/`zen init`, LSP solo diagnósticos push, `fmt`/`lint`/`lsp` mono-fichero; `use` sin namespaces. |
| Punteros raw, `volatile`, `unsafe`, ABI C y freestanding | **Integrado** | 8 tests freestanding, objetos sin libc y enlace/ejecución; TASK-310/311 (2026-11-11); [`docs/zen/freestanding.md`](zen/freestanding.md). | Sin inline asm del lenguaje, secciones ni layout explícito; GCC x86_64 del host. |
| Arrays de tamaño fijo `[T; N]` y slices `[u64]` | **Integrado** | 9 tests de arrays, bounds-check y casos negativos (TASK-213); 12 tests de slices, conversión implícita de array local y builtin `slice_len` (TASK-915/ADR-026, 2026-11-11); [`docs/zen/slices.md`](zen/slices.md). | Slices solo como parámetro `[u64]`; sin locales, retorno, rebanados/rangos, aliasing ni multidimensionales. |
| Structs nominales escalares | **Integrado** | 15 tests de structs, campos y errores; TASK-214 (2026-11-11); ADR-017. | Solo locales y escalares; sin métodos, anidamiento, paso/retorno por ABI ni arrays de structs. |
| Builtins de stdlib de strings | **Verificado** | 12 tests `stdlib` + 12 `stdlib_ext`, hosted y freestanding; TASK-901A/901B (2026-11-11); ADR-019. | Seis builtins byte-oriented; sin colecciones, I/O, formato, heap ni `Result`/`Option`. |
| Composición `use` + `zen/std/core.zen` | **Integrado (mínimo)** | 10 tests de include (anidado, ciclo, profundidad 16/17, error localizado) y ejemplo `use_std.zen`; TASK-912 (2026-11-11); ADR-024. | Inclusión textual sin namespaces, visibilidad, search paths ni stdlib embebida; `fmt`/`lint`/`lsp` no resuelven. |
| Boot Ferros, Multiboot1, UART y runner QEMU | **Integrado** | 6/6 arranques QEMU estado 33 (debug/release ×3) en la puerta del corte 0.1.1 (2026-11-12); TASK-410/411 (2026-11-11); [`docs/ferros/boot.md`](ferros/boot.md). | Solo QEMU TCG, `-smp 1`; sin hardware físico, KVM, UEFI/ISO ni red/discos. |
| PMM, VMM, heap, IDT/PIC/PIT | **Integrado (mínimo)** | 43 tests de Ferros y 6/6 QEMU del corte 0.1.1 (2026-11-12); TASK-510/511 (2026-11-11); [`docs/ferros/memory-interrupts.md`](ferros/memory-interrupts.md). | Identidad 64 MiB, arena sin `free` individual, sin IST/IRQ anidada/SMP; fallos kernel fatales. |
| Threads y scheduler round-robin | **Integrado (mínimo)** | 43 tests de Ferros y estadísticas QEMU (`switches=45`, `preemptions=25`, `yields=16`, `completed=3`), TASK-610/611 (2026-11-11); [`docs/ferros/multitasking.md`](ferros/multitasking.md). | Mismo address space, stacks estáticos, init one-shot; sin prioridades, FPU/SIMD ni SMP. |
| ELF de usuario CPL3 e `int0x80` | **Integrado (mínimo)** | 43 tests de Ferros, 6/6 QEMU, `runs=7`/`writes=18`/`rejected=6`; TASK-710/711 (2026-11-11); [`docs/ferros/userspace.md`](ferros/userspace.md). | Una invocación activa, CR3 compartido; sin `SYSCALL`, ASLR, KPTI, TLS ni cuota de CPU. |
| RAMFS, VFS y `readdir` | **Integrado (mínimo)** | 43 tests de Ferros, 6/6 QEMU, `ls`/`cat` sobre `hello.zen` y `notes.txt` y `readdir`; TASK-701 (2026-11-11), TASK-215/ADR-018. | Volátil en memoria; sin directorios dinámicos, `unlink`, permisos por usuario, caché ni monturas; sin FS persistente montado. |
| Persistencia ATA PIO (contador entre arranques) | **Integrado (mínimo)** | `test_persistence.py` (dos arranques mismo disco: BOOT 1→2), 43 tests Ferros, gate 8/8; TASK-914/ADR-025 (2026-11-12). | Una unidad PIIX IDE/LBA28, 1 sector/operación, sin IRQ/DMA/FS real/journaling/atomicidad; solo QEMU, no hardware real/AHCI. |
| Mini-FS persistente ZENFS01 | **Integrado (mínimo)** | 4 tests de TASK-916 (`test_pfs.py` + test_boot/test_shell), 43/43 Ferros y 6/6 QEMU; línea `PFS: BOOT 1 FILES=1` tras `PERSIST` y antes del shell; 3 arranques con el mismo disco BOOT 1/2/3 y `boot.txt` persistente; TASK-916 (2026-11-12), ADR-027, [`docs/ferros/persistence.md`](ferros/persistence.md). | 8 archivos, 1 bloque de 512 B; sin directorios/journaling/caché/atomicidad; checksum solo del superbloque; **no montado en VFS/shell** (TASK-919 es posterior al corte; PFS-en-VFS queda para 0.1.2); solo QEMU PIIX IDE. |
| Shell interactivo COM1 | **Integrado (mínimo)** | Transcripción exacta y `writes=18` en 6/6 QEMU del corte 0.1.1 (2026-11-12); TASK-703 (2026-11-11); [`docs/ferros/shell.md`](ferros/shell.md). | Polling sin IRQ serie; sin edición de línea, historial, tuberías ni teclado PS/2; no ve archivos PFS. |
| Benchmarks comparativos | **Integrado (mínimo, línea base)** | 6 tests del arnés y 3 suites con checksum previo; TASK-801/802 (2026-11-11); ADR-013/015; [`docs/benchmarks/results.md`](benchmarks/results.md). | Cuatro cargas enteras; sin floats/SIMD/concurrencia ni `perf`; paridad aproximada, no ranking. |
| Componentes de self-hosting (11) | **Verificado** | 166 tests de `zen/selfhost/tests` en la puerta del corte 0.1.1: lexer contador (7), lexer con tokens (11), parser (7), AST (14), intérprete (16), funciones (22), typechecker (16), codegen (16), codegen funciones (18), codegen arrays (20) y codegen structs (19); TASK-902…902K (2026-11-11/12); ADR-014/016/023/024. | No es un compilador completo: sin spans, tabla de símbolos completa, stdlib ni backend Rust; varios componentes son solo de host por stack. |
| Puerta de calidad, CI local/remoto y campaña | **Integrado** | 8/8 PASS en 1m 09,0 s con 163/43/6/166 (2026-11-12); `repro_build` completo PASS 1,97 s; campaña 2/2 full + 5/5 quick PASS en el corte y 10 quick + 3 full de TASK-917; TASK-907/908/911/913/917. Workflow remoto de TASK-918 validado localmente 44/44 (`check_ci_workflow.py`) pero **no ejecutado** en GitHub; [`docs/ci-remote.md`](ci-remote.md). | Puerta y matriz locales; el workflow remoto es una plantilla no ejecutada; sin contenedor hermético; campaña acotada y con semilla fija. |
| Gramática completa / especificación | **Experimental (propuesta)** | [`docs/zen/syntax-v0.ebnf`](zen/syntax-v0.ebnf) y [`docs/zen/syntax-decisions.md`](zen/syntax-decisions.md), borrador del 2026-11-10. | No conectada al parser; no equivale al subconjunto implementado. |

Recuento: **18 Integrado** (9 sin calificador y 9 con alcance mínimo), **2
Verificado**, **1 Experimental**, **0 Estable**, **0 Optimizado** (21 filas).
«Integrado (mínimo)» no es un nivel adicional: es `Integrado` con el alcance
reducido que se declara en la columna de límites.

## Por qué nada es `Estable`

La evidencia de estabilidad existente es real pero **acotada**:

- `stress.py` hace 6 arranques (3 guiones × debug/release), 2 rondas de Ferros y
  2 de selfhost, y 200+200 casos de fuzz con semilla fija
  ([`docs/stability.md`](stability.md), TASK-905).
- `stability_campaign.py` repite esa campaña 5 veces en quick o 2 en full
  ([`docs/stability-campaign.md`](stability-campaign.md), TASK-913). En full añade
  `verify_all --full`, pero no amplía su cobertura.
- TASK-917 repitió la campaña ampliada: **10 rondas quick PASS** (10/10
  arranques, 10/10 suites) y **3 rondas full PASS** (stress 12/12 + gate 12/12
  con estado 33), además de un gate final 8/8 en 51,70 s y un estrés completo
  ([`agents/reports/TASK-917.md`](../agents/reports/TASK-917.md)).
- En el corte 0.1.1 se ejecutaron **2 rondas full PASS** (4m 17,4 s; stress
  12/12 arranques + gate 12/12, 4/4 suites, fuzz 400+400 casos, `warnings: []`)
  y **5 rondas quick PASS** (3m 15,1 s; 10/10 arranques, 10/10 suites).
- El host es compartido, la semilla no cambia entre rondas, no hay inyección de
  fallos en kernel/scheduler/memoria/drivers, no hay fuzzing guiado por cobertura
  y no hay horas de ejecución ni recuperación ante fallos inyectados.

Eso demuestra **repetibilidad de la puerta y de los guiones**, no estabilidad
sostenida. Ningún subsistema cumple el criterio de la regla 3 (ni 3 campañas
full en entorno aislado, ni fault injection, ni ventana de regresión). En
particular, los subsistemas de kernel (memoria, scheduler, VFS, shell, mini-FS)
siguen en `Integrado (mínimo)`: funcionan juntos en la ruta de aceptación, pero
no tienen campaña larga, aislamiento de host ni fault injection.

## Por qué nada es `Optimizado`

- Los benchmarks del Hito 8 miden cuatro cargas enteras con el **mismo backend
  C11 y el mismo GCC** que C; la conclusión documentada es paridad aproximada
  dentro del ruido (Zen/C 0,9385–1,0408 en tres suites) y **no** superioridad.
- No hay `perf`, ciclos, instrucciones ni fallos de caché; el host es compartido
  y las diferencias de pocos puntos no se interpretan como señal.
- TASK-802 midió `-O3`/LTO y decidió **mantener `-O2`** (ADR-015): hay una
  decisión justificada, pero no una mejora aplicada y atribuible. Sin un
  antes/después reproducible y una regresión preservada, `Optimizado` no se
  declara.
- Un `PASS` de la puerta no impone umbral de rendimiento; solo verifica
  corrección y reproducibilidad de la medición.

## Qué NO se demuestra

- **Hardware físico, KVM, UEFI/ISO.** Todo es QEMU TCG con `-smp 1`; no hay
  `/dev/kvm`, metal, ISO ni arranque UEFI (TASK-410/411).
- **SMP y concurrencia real.** Un solo CPU, sin IRQ anidadas, IST, `swapgs`,
  barreras ni sincronización; `volatile` no es atomicidad.
- **PFS visible en VFS/shell y FS read-only.** El mini-FS ZENFS01 existe y
  persiste archivos con nombre entre arranques, pero **no está montado**: el
  shell no lista ni lee `boot.txt`, y no hay operaciones read-only expuestas al
  usuario. TASK-919 (PFS-en-VFS) es posterior al corte 0.1.1 y queda para
  0.1.2; no se declara FS read-only. RAMFS sigue siendo volátil y no hay
  monturas, `unlink`, permisos ni journaling/atomicidad.
- **Self-hosting completo.** El compilador sigue en Rust; los once componentes
  de `zen/selfhost/` verifican comportamiento parcial (166 tests), no un
  compilador completo ni un bootstrap.
- **Stdlib amplia, floats, SIMD, ownership, módulos con namespaces, métodos,
  inline asm del lenguaje.** No implementados o explícitamente rechazados.
- **Seguridad formal.** Hay pruebas negativas y fuzz diferencial acotado, no
  threat modeling, auditoría formal ni fuzzing guiado por cobertura.
- **Rendimiento competitivo o ranking de lenguajes.** Los benchmarks son línea
  base y detector de regresiones.
- **CI remoto ejecutado y procedencia reproducible.** El workflow
  `.github/workflows/ci.yml` de TASK-918 está validado solo en estructura
  (44/44 comprobaciones locales), nunca se ha ejecutado en GitHub. Sin `.git`
  no hay commit, tag, bisect, firma ni SBOM; la puerta es local a este host y
  toolchain.
- **Corrección total.** 378 tests y 6 arranques QEMU no prueban ausencia de
  bugs; prueban que los casos ejecutados pasan.

## Fuentes desfasadas detectadas (no cambian el nivel)

Durante la revisión se encontraron referencias que no coinciden con el árbol
actual. Se documentan aquí porque pueden inducir a error; **no se editaron** por
la propiedad de archivos de esta tarea:

- [`ROADMAP.md`](../ROADMAP.md) conserva al menos un recuento histórico
  desfasado («34 tests Ferros» al cerrar TASK-703); los conteos vigentes del
  corte 0.1.1 son **163/43/6/166** (378 total).
- [`README.md`](../README.md) y [`agents/STATE.md`](../agents/STATE.md) ya
  reflejan 163/44/6/166 y 379; se citan como estado operativo, no como
  certificación.
- [`docs/quality.md`](quality.md) está fechado el 2026-11-11 y describe la
  puerta con 163/43/6/166; sus conteos son correctos para el corte, pero no
  menciona la release 0.1.1 ni la campaña de TASK-917.
- [`docs/README.md`](README.md) sigue presentando el índice y la release como
  0.1.0; es un índice fuera del alcance de esta tarea.
- [`docs/reproducibility.md`](reproducibility.md) conserva hashes y tamaños del
  C generado del 2026-11-11 que no coinciden con el árbol actual; su propio texto
  advierte que son una foto. La referencia de esta release es el manifiesto del
  corte 0.1.1 transcrito en [`docs/release.md`](release.md).
- [`docs/zen/selfhost.md`](zen/selfhost.md) usa «55 ficheros `.zen`» como
  recuento manual; no es un contrato de la suite (166 tests).

## Evidencia del corte 0.1.1

| Comprobación | Resultado | Fecha |
|---|---|---|
| `python3 infrastructure/scripts/verify_all.py --full` | 8/8 PASS, 1m 09,0 s, 163/43/6/166 | 2026-11-12 09:28 |
| `CARGO_HOME="$PWD/.cargo" cargo test --release --offline --manifest-path zen/compiler/Cargo.toml` | 163/163, 13,25 s (paso 2 de la puerta) | 2026-11-12 |
| `python3 -m unittest discover -s ferros/tests` | 43/43, 26,92 s (paso 3) | 2026-11-12 |
| `python3 -m unittest discover -s zen/selfhost/tests` | 166/166, 8,32 s (paso 7) | 2026-11-12 |
| `python3 infrastructure/scripts/boot_ferros.py --all --repeat 3` | 6/6 estado 33, `writes=18`, `PFS: BOOT 1 FILES=1` (paso 5) | 2026-11-12 |
| `python3 infrastructure/scripts/repro_build.py` | PASS, 1,97 s, 0 discrepancias | 2026-11-12 |
| `python3 infrastructure/scripts/stability_campaign.py --rounds 2 --mode full` | PASS, 4m 17,4 s, 2/2 rondas, stress 12/12 + gate 12/12 | 2026-11-12 |
| `python3 infrastructure/scripts/stability_campaign.py --rounds 5` | PASS, 3m 15,1 s, 5/5 rondas, 10/10 arranques, 10/10 suites | 2026-11-12 |
| `python3 infrastructure/scripts/check_ci_workflow.py` | 44/44 PASS (estructura; no ejecución remota) | 2026-11-12 |

Los tiempos son de este host compartido, con caché caliente; no son benchmarks.
Las cifras de campañas históricas y sus límites están en
[`docs/stability-campaign.md`](stability-campaign.md) y
[`docs/stability.md`](stability.md).

## Qué haría falta para subir de nivel

No es un compromiso de roadmap; es el criterio que esta auditoría aplicaría:

- **A `Estable` (cualquier subsistema):** campañas full repetidas en un entorno
  aislado y no compartido, inyección de fallos/estrés sostenido, fuzzing con
  cobertura o corpus, registro de fallos conocidos y recuperación, y una ventana
  de regresión a través de varios cambios. Sin eso, el nivel máximo honesto es
  `Integrado`.
- **A `Optimizado`:** un cambio de implementación medido antes/después con
  benchmark reproducible, control de ruido, mejora fuera del ruido y regresión
  funcional intacta. La decisión de mantener `-O2` no cuenta como mejora.
- **A `Verificado` o `Integrado`:** el criterio normal es una suite que pase y
  una ruta real con los vecinos; eso ya se cumple donde la tabla lo indica.

La puerta y la campaña actuales son la base para detectar regresiones; no son un
certificado. Cualquier subida de nivel debe venir con evidencia nueva, fechada y
enlazada, y actualizar `docs/quality.md` en una tarea con propiedad sobre ese
archivo.
