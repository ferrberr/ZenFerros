# Changelog

Cambios de Zen + Ferros. Este proyecto **no tiene `.git`** en el workspace, así
que no hay tags, commits ni historial que consultar: las versiones son cortes
locales documentados y la evidencia son los ficheros, los informes y las
ejecuciones de la puerta.

Formato: versión, fecha, hitos, herramientas, cambios por fase y límites. Las
fechas son locales (CET). Los conteos de tests se verifican contra
[`verify_all.py`](infrastructure/scripts/verify_all.py), no se copian de informes
antiguos.

## [0.1.1] — 2026-11-12

Segunda versión local de Zen + Ferros. Como 0.1.0, **no es una release
publicada, firmada ni etiquetada**: no hay `.git`, CI remoto ejecutado ni
artefacto distribuible. Alcance y límites en [`docs/release.md`](docs/release.md);
madurez sin cambios de nivel en [`docs/maturity.md`](docs/maturity.md).

**Corte de evidencia:** 2026-11-12, 09:28 CET. Es el árbol congelado que pasó
`verify_all.py --full` en **8/8 PASS (1m 09,0 s)**, con **163/43/6/166** tests
(**378** en total), **6/6** arranques QEMU en estado 33 y `repro_build.py`
completo **PASS** en 1,97 s sin discrepancias. El binario sigue declarando
`zen 0.1.0 (bootstrap)`: 0.1.1 es un corte documental, no un cambio de versión
en `Cargo.toml`.

**Corte antes de TASK-919.** La integración de ZENFS01 en VFS/shell (PFS
visible con `ls`/`cat`, read-only) estaba en curso; tras el corte, el árbol
cambió en `vfs.zen`, `storage_fs.zen` y `main.zen` (ficheros de TASK-919).
0.1.1 se corta **antes** de ella: PFS solo se anuncia al arrancar
(`PFS: BOOT n FILES=n`) y no es visible desde VFS/shell; no se declara FS
read-only. PFS-en-VFS queda para **0.1.2**.

### Cambios de 0.1.1

| Área | Cambio | Evidencia |
|---|---|---|
| Slices | `[u64]` como parámetro de función, conversión implícita desde array local, bounds check contra `len`, builtin `slice_len` y `zen/std/array.zen` (`sum`, `max`, `reverse`, `sort`, `contains`); compilador 151→163. | [TASK-915](agents/reports/TASK-915.md), [ADR-026](agents/decisions/ADR-026.md), [`docs/zen/slices.md`](docs/zen/slices.md) |
| Self-hosting | Undécimo componente: codegen C11 con structs nominales (declaración, literal, lectura/escritura de campo); selfhost 147→166 y 166 tests en once componentes. | [TASK-902K](agents/reports/TASK-902K.md), [ADR-023](agents/decisions/ADR-023.md) |
| Persistencia | Mini-FS **ZENFS01** sobre ATA PIO: superbloque, 8 inodos y 8 bloques de 512 B, API crear/leer/escribir/borrar/listar y `PFS: BOOT n FILES=n` tras `PERSIST`; Ferros 39→43 con 3 arranques y el mismo disco. | [TASK-916](agents/reports/TASK-916.md), [ADR-027](agents/decisions/ADR-027.md), [`docs/ferros/persistence.md`](docs/ferros/persistence.md) |
| Estabilidad | Campaña ampliada: 10 rondas quick PASS (10/10 arranques, 10/10 suites) y 3 rondas full PASS (stress 12/12 + gate 12/12 estado 33), más gate final 8/8 en 51,70 s. | [TASK-917](agents/reports/TASK-917.md), [`docs/stability-campaign.md`](docs/stability-campaign.md) |
| CI remoto | Workflow `.github/workflows/ci.yml` (PR quick, `main`/manual full, artefactos JSON/logs) y validador `check_ci_workflow.py` con 44/44 comprobaciones. **No ejecutado en GitHub.** | [TASK-918](agents/reports/TASK-918.md), [`docs/ci-remote.md`](docs/ci-remote.md) |

### Conteos del corte

| Suite | Tests | Desglose |
|---|---:|---|
| Compilador | **163** | 34 unitarias + 9 arrays + 10 `fmt` + 8 freestanding + 10 include + 11 CLI + 12 slices + 12 stdlib + 12 stdlib_ext + 15 structs + 18 lint + 12 LSP |
| Ferros | **43** | 39 previos + 4 de persistencia/mini-FS (TASK-916) |
| Benchmarks | **6** | arnés comparativo con checksum previo |
| Self-hosting | **166** | 11 componentes; 19 tests de codegen structs (TASK-902K) |
| **Total** | **378** | |

### Verificación de esta versión

```bash
# Puerta completa: 8 pasos, 6 arranques QEMU, benchmarks y reproducibilidad
python3 infrastructure/scripts/verify_all.py --full

# Desglose de los conteos canónicos
CARGO_HOME="$PWD/.cargo" cargo test --release --offline --manifest-path zen/compiler/Cargo.toml  # 163
python3 -m unittest discover -s ferros/tests        # 43
python3 -m unittest discover -s benchmarks/tests    # 6
python3 -m unittest discover -s zen/selfhost/tests  # 166
```

La puerta `--full` del corte dio **8/8 PASS en 1m 09,0 s** (sin `skipped`), con
6/6 QEMU estado 33, `writes=18`, `runs=7`, `rejected=6` y
`PFS: BOOT 1 FILES=1`; `repro_build.py` completo PASS en 1,97 s. La campaña al
corte dio **2/2 rondas full PASS** (4m 17,4 s; stress 12/12 + gate 12/12, 4/4
suites, `warnings: []`) y **5/5 rondas quick PASS** (3m 15,1 s; 10/10 arranques y
10/10 suites). La puerta falla si un paso ejecuta menos tests de los esperados o
si aparece un `skipped`.

### No incluido en 0.1.1

- **PFS visible en VFS/shell y FS read-only.** TASK-919 quedó después del corte;
  queda para 0.1.2. En 0.1.1 el shell solo ve RAMFS y PFS únicamente emite su
  línea de arranque.
- **CI remoto ejecutado, publicación, tag y firma.** El workflow de TASK-918 es
  una plantilla validada solo en estructura; no hay `.git`, runner remoto,
  SBOM ni artefacto firmado.
- **Self-hosting completo y stdlib amplia.** El compilador sigue en Rust; los
  once componentes selfhost son parciales y la stdlib se limita a builtins de
  strings, slices y siete funciones puras.
- **Hardware físico, KVM, SMP, UEFI/ISO y estabilidad certificada.** Todo es
  QEMU TCG `-smp 1`; ningún subsistema es `Estable` ni `Optimizado`.

## [0.1.0] — 2026-11-12

Primera versión local de Zen + Ferros. **No es una release publicada ni
firmada**: es un corte documental y verificable del workspace, sin CI remoto ni
artefacto distribuible fuera de este host. Alcance y limitaciones de 0.1.0 en
[`docs/quality.md`](docs/quality.md) y en el anexo histórico de
[`docs/release.md`](docs/release.md); madurez honesta en
[`docs/maturity.md`](docs/maturity.md).

**Corte de evidencia:** 2026-11-12, 08:16 CET. Es el árbol que pasó la puerta
completa con **151/39/6/147** tests, incluida la persistencia ATA PIO
(TASK-914).

**Evidencia de cierre (2026-11-12):** puerta completa 8/8 PASS en ~46,9 s con
**151/39/6/147** tests; campaña de estabilidad de 1 ronda quick PASS (32,16 s),
además de las 5 rondas quick y 2 full de TASK-913; reproducibilidad completa
PASS (1,89 s, sin discrepancias). Detalle y comandos en
[`docs/quality.md`](docs/quality.md) y [`docs/release.md`](docs/release.md).

### Posterior al corte 0.1.0 (incorporado en 0.1.1)

Trabajo posterior a la evidencia congelada de 0.1.0 y ya incluido en la release
0.1.1: **TASK-915** slices `[u64]` como parámetro + stdlib de arrays
(compilador 163), **TASK-902K** codegen selfhost con structs (selfhost 166),
**TASK-916** mini-FS persistente ZENFS01 (Ferros 43), **TASK-917** campaña
ampliada (10 quick + 3 full) **TASK-918** workflow CI remoto (no ejecutado) y **TASK-919** PFS visible en el VFS (Ferros 44), posterior a 0.1.1.
No forman parte de los conteos ni hashes de 0.1.0 (151/39/6/147); sus conteos e
hashes son los del corte 0.1.1 descrito arriba.

### Hitos 1–10

| Hito | Estado en 0.1.0 | Qué quedó implementado | Evidencia |
|---|---|---|---|
| 1 | Completado | Compilador hosted: Zen → frontend comprobado → C11 → `cc` → ELF Linux x86_64. | [TASK-210](agents/reports/TASK-210.md), [TASK-211](agents/reports/TASK-211.md), [ADR-007](agents/decisions/ADR-007.md) |
| 2 | Completado | Objeto freestanding sin libc, ABI C explícita, punteros raw/`volatile`, bits/casts y `unsafe`. | [TASK-310](agents/reports/TASK-310.md), [TASK-311](agents/reports/TASK-311.md), [ADR-008](agents/decisions/ADR-008.md) |
| 3 | Completado | Kernel Zen, UART COM1, bootstrap Multiboot32→longmode64 y aceptación QEMU. | [TASK-410](agents/reports/TASK-410.md), [TASK-411](agents/reports/TASK-411.md), [ADR-009](agents/decisions/ADR-009.md) |
| 4 | Completado | PMM bitmap, VMM 4 KiB, heap arena, IDT/PIC/PIT y excepciones contenidas. | [TASK-510](agents/reports/TASK-510.md), [TASK-511](agents/reports/TASK-511.md), [ADR-010](agents/decisions/ADR-010.md) |
| 5 | Completado | Tres threads de kernel con guardas, scheduler round-robin preemptivo, `yield`/`exit`. | [TASK-610](agents/reports/TASK-610.md), [TASK-611](agents/reports/TASK-611.md), [ADR-011](agents/decisions/ADR-011.md) |
| 6 | Completado | ELF Zen separado en CPL3, loader con rollback, W^X, `int0x80` (`write`/`exit`/`ticks`) y faults de aislamiento. | [TASK-710](agents/reports/TASK-710.md), [TASK-711](agents/reports/TASK-711.md), [ADR-012](agents/decisions/ADR-012.md) |
| 7 | Completado | RAMFS 1 MiB, VFS mínimo, syscalls de archivos 4–7/9, `readdir`, init/shell y shell interactivo COM1. | [TASK-701](agents/reports/TASK-701.md), [TASK-703](agents/reports/TASK-703.md), [ADR-018](agents/decisions/ADR-018.md) |
| 8 | Completado | Laboratorio de benchmarks Zen/C/C++/Rust con checksum previo, CPU-time y resultados versionados. | [TASK-801](agents/reports/TASK-801.md), [TASK-802](agents/reports/TASK-802.md), [ADR-013](agents/decisions/ADR-013.md), [ADR-015](agents/decisions/ADR-015.md) |
| 9 | Parcial | Diez componentes del frontend/ejecución (corte 0.1.0) escritos en Zen y compilados por `zen` (lexer, parser, AST, intérpretes, typechecker y tres codegens). No hay compilador completo en Zen. | [TASK-902](agents/reports/TASK-902.md), [TASK-902C](agents/reports/TASK-902C.md), [TASK-902J](agents/reports/TASK-902J.md), [ADR-014](agents/decisions/ADR-014.md), [ADR-023](agents/decisions/ADR-023.md) |
| 10 | Documentado | Puerta única, builds reproducibles locales, estrés/fuzz, matriz CI local, campaña repetida e informe de madurez. Sin certificación de estabilidad. | [TASK-905](agents/reports/TASK-905.md), [TASK-907](agents/reports/TASK-907.md), [TASK-908](agents/reports/TASK-908.md), [TASK-911](agents/reports/TASK-911.md), [TASK-913](agents/reports/TASK-913.md) |

### Herramientas

| Herramienta | Qué aporta | Evidencia |
|---|---|---|
| `zen fmt` | Formato canónico token a token, comentarios preservados, `--check`/`--write` atómico e idempotencia. | [TASK-904A](agents/reports/TASK-904A.md), [ADR-020](agents/decisions/ADR-020.md), [`docs/zen/formatter.md`](docs/zen/formatter.md) |
| `zen lint` | Avisos `unused-*`/`unreachable-code`, texto y JSON, `--deny-warnings`. | [TASK-909](agents/reports/TASK-909.md), [ADR-021](agents/decisions/ADR-021.md), [`docs/zen/linter.md`](docs/zen/linter.md) |
| `zen lsp` | Servidor JSON-RPC por stdio con sincronización full y diagnósticos UTF-16. | [TASK-910](agents/reports/TASK-910.md), [ADR-022](agents/decisions/ADR-022.md), [`docs/zen/lsp.md`](docs/zen/lsp.md) |
| `use` + `zen/std/core.zen` | Composición textual multi-archivo con depth 16, ciclos y deduplicación; siete funciones puras. | [TASK-912](agents/reports/TASK-912.md), [ADR-024](agents/decisions/ADR-024.md), [`docs/zen/modules.md`](docs/zen/modules.md) |
| `verify_all.py` | Puerta local de 8 pasos con timeouts, aborto temprano y conteos esperados. | [TASK-907](agents/reports/TASK-907.md), [`docs/quality.md`](docs/quality.md) |
| `repro_build.py` | Dos builds consecutivos de C generado y artefactos de Ferros; manifiesto JSON. | [TASK-908](agents/reports/TASK-908.md), [`docs/reproducibility.md`](docs/reproducibility.md) |
| `stress.py` | Arranques con tres guiones, repetición de suites y fuzz diferencial acotado. | [TASK-905](agents/reports/TASK-905.md), [`docs/stability.md`](docs/stability.md) |
| `ci_matrix.py` | Matriz local quick/defecto/full con logs, timeouts, fallo temprano y JSON. | [TASK-911](agents/reports/TASK-911.md), [`docs/ci.md`](docs/ci.md) |
| `stability_campaign.py` | Repite la campaña N rondas y agrega 6/6 arranques del gate en modo full. | [TASK-913](agents/reports/TASK-913.md), [`docs/stability-campaign.md`](docs/stability-campaign.md) |

### Cambios por fase

**Fase 0 — Reconocimiento y base.** Estructura del workspace, README,
ARCHITECTURE y ROADMAP; QEMU local con versiones y SHA256 fijados; decisión de
bootstrap ([ADR-001](agents/decisions/ADR-001.md), sustituida por
[ADR-007](agents/decisions/ADR-007.md) para el MVP). Ver
[`ROADMAP.md`](ROADMAP.md).

**Fase 1 — Especificación de Zen.** Gramática propuesta y decisiones de sintaxis
en [`docs/zen/syntax-decisions.md`](docs/zen/syntax-decisions.md) y
[`docs/zen/syntax-v0.ebnf`](docs/zen/syntax-v0.ebnf). Sigue siendo un borrador
más amplio que el subconjunto ejecutable; no hay parser completo.

**Fase 2 — Compilador mínimo.** Lexer, parser, comprobación de nombres/tipos,
emisión C11, CLI `build`/`run`/`check`/`lex` y pruebas de aceptación; arrays
fijos y structs escalares locales. Evidencia: [ADR-007](agents/decisions/ADR-007.md),
[ADR-016](agents/decisions/ADR-016.md), [ADR-017](agents/decisions/ADR-017.md),
[TASK-213](agents/reports/TASK-213.md), [TASK-214](agents/reports/TASK-214.md),
[`docs/zen/mvp-native.md`](docs/zen/mvp-native.md).

**Fase 3 — Freestanding.** Perfil `x86_64-unknown-none`, objetos sin libc, ABI C,
punteros raw, `volatile`, bits/casts y `unsafe`; verificación de enlace y
ejecución sin libc. Evidencia: [ADR-008](agents/decisions/ADR-008.md),
[TASK-310](agents/reports/TASK-310.md), [TASK-311](agents/reports/TASK-311.md),
[`docs/zen/freestanding.md`](docs/zen/freestanding.md).

**Fase 4 — Primer arranque de Ferros.** Multiboot1 directo, bootstrap
32→64 bits, kernel Zen, UART y aceptación QEMU con timeout, logs y cancelación.
Evidencia: [ADR-009](agents/decisions/ADR-009.md),
[TASK-410](agents/reports/TASK-410.md), [TASK-411](agents/reports/TASK-411.md),
[`docs/ferros/boot.md`](docs/ferros/boot.md).

**Fase 5 — Memoria e interrupciones.** PMM bitmap, VMM con páginas 4 KiB y
protección, heap arena, IDT/PIC/PIT, excepciones y pruebas negativas. Evidencia:
[ADR-010](agents/decisions/ADR-010.md), [TASK-510](agents/reports/TASK-510.md),
[TASK-511](agents/reports/TASK-511.md),
[`docs/ferros/memory-interrupts.md`](docs/ferros/memory-interrupts.md).

**Fase 6 — Procesos y multitarea.** Threads con stack/guarda, scheduler
preemptivo, cambio de contexto, ELF de usuario en CPL3, `int0x80` y aislamiento
de faults. Evidencia: [ADR-011](agents/decisions/ADR-011.md),
[ADR-012](agents/decisions/ADR-012.md), [TASK-610](agents/reports/TASK-610.md),
[TASK-611](agents/reports/TASK-611.md), [TASK-710](agents/reports/TASK-710.md),
[TASK-711](agents/reports/TASK-711.md).

**Fase 7 — Almacenamiento y userspace.** RAMFS/VFS, syscalls de archivos,
`readdir`, init/shell en CPL3 y shell interactivo por COM1 con guion inyectado
tras `SHELL: READY`. Evidencia: [ADR-018](agents/decisions/ADR-018.md),
[TASK-701](agents/reports/TASK-701.md), [TASK-703](agents/reports/TASK-703.md),
[`docs/ferros/filesystem.md`](docs/ferros/filesystem.md),
[`docs/ferros/shell.md`](docs/ferros/shell.md).

**Fase 8 — Optimización y benchmarks.** Arnés reproducible con cuatro cargas,
checksum antes de medir, CPU-time y tres suites; estudio de `-O2`/`-O3`/LTO que
decidió mantener `-O2` sin declarar mejora. Evidencia:
[ADR-013](agents/decisions/ADR-013.md), [ADR-015](agents/decisions/ADR-015.md),
[TASK-801](agents/reports/TASK-801.md), [TASK-802](agents/reports/TASK-802.md),
[`docs/benchmarks/results.md`](docs/benchmarks/results.md).

**Fase 9 — Madurez y autohosting.** Builtins de strings, arrays/structs para el
autohosting, diez componentes en Zen (corte 0.1.0), formateador, linter, LSP, `use`, gate
único, reproducibilidad, estrés y campaña repetida. Evidencia:
[ADR-014](agents/decisions/ADR-014.md), [ADR-016](agents/decisions/ADR-016.md),
[ADR-017](agents/decisions/ADR-017.md), [ADR-019](agents/decisions/ADR-019.md),
[ADR-020](agents/decisions/ADR-020.md), [ADR-021](agents/decisions/ADR-021.md),
[ADR-022](agents/decisions/ADR-022.md), [ADR-023](agents/decisions/ADR-023.md),
[ADR-024](agents/decisions/ADR-024.md), [TASK-901A](agents/reports/TASK-901A.md),
[TASK-901B](agents/reports/TASK-901B.md), [TASK-902J](agents/reports/TASK-902J.md),
[TASK-905](agents/reports/TASK-905.md), [TASK-907](agents/reports/TASK-907.md),
[TASK-908](agents/reports/TASK-908.md), [TASK-912](agents/reports/TASK-912.md),
[TASK-913](agents/reports/TASK-913.md).

### No incluido

- **CI remoto, publicación y firma.** No hay servidor CI, contenedor hermético,
  tag, commit, SBOM, atestación ni artefacto firmado. `.git` no existe en el
  workspace; todo PASS es local a este host y toolchain.
- **Stdlib amplia.** Solo hay seis builtins de strings y siete funciones puras en
  `zen/std/core.zen`; no hay colecciones, I/O, asignación dinámica, heap de
  usuario ni `Result`/`Option`.
- **Self-hosting completo.** El compilador sigue escrito en Rust. Los diez
  componentes de `zen/selfhost/` son parciales y no cubren spans, tabla de
  símbolos completa, stdlib ni backend completo; algunos son solo de host por
  tamaño de stack.
- **Persistencia y VFS avanzado (más allá de 0.1.0).** RAMFS es volátil; no hay VirtIO
  block, monturas, directorios dinámicos, `unlink`, permisos por usuario ni caché.
  TASK-914 añade una demo ATA PIO entre arranques (contador `PERSIST: BOOT n`),
  incluida en 0.1.0, pero sin FS real.
- **KVM, SMP y hardware.** Todo se ejecuta en QEMU TCG con `-smp 1`; no hay
  `/dev/kvm`, hardware físico, UEFI, ISO, IRQ anidada, IST ni sincronización SMP.
- **Lenguaje completo.** Sin floats, métodos, ownership/borrowing, módulos con
  namespaces, genéricos, inline asm del lenguaje, globals propios ni paso de
  structs/arrays entre funciones.
- **Madurez Estable/Optimizado.** No se declara ningún subsistema `Estable` ni
  `Optimizado`; los benchmarks son línea base, no ranking, y la campaña es
  acotada. Justificación en [`docs/maturity.md`](docs/maturity.md).
- **Publicación de una release.** No hay paquete instalable, repositorio de
  artefactos ni promesa de compatibilidad; la release es un corte documental.

### Verificación de esta versión

```bash
# Puerta completa: 8 pasos, 6 arranques QEMU, benchmarks y reproducibilidad
python3 infrastructure/scripts/verify_all.py --full

# Desglose de los conteos canónicos
CARGO_HOME="$PWD/.cargo" cargo test --release --offline --manifest-path zen/compiler/Cargo.toml  # 151
python3 -m unittest discover -s ferros/tests        # 39
python3 -m unittest discover -s benchmarks/tests    # 6
python3 -m unittest discover -s zen/selfhost/tests  # 147
```

**151** se reparte en 34 unitarias + 9 arrays + 10 `fmt` + 8 freestanding +
10 include + 11 CLI nativa + 12 stdlib + 12 stdlib ampliada + 15 structs +
18 lint + 12 LSP. El total de tests es **343**. La puerta falla si un paso
ejecuta menos tests de los esperados o si aparece un `skipped`.

### Nota de coherencia

Este changelog cita el estado del árbol en el momento de cada corte. **0.1.0**
queda como histórico con 151/39/6/147 (343 tests); **0.1.1** es el corte vigente
con 163/43/6/166 (378 tests) y los hashes de [`docs/release.md`](docs/release.md).
Algunas filas históricas de [`ROADMAP.md`](ROADMAP.md) conservan conteos de
cortes anteriores (por ejemplo, «34 tests Ferros»); el estado operativo está en
[`agents/STATE.md`](agents/STATE.md). [`docs/reproducibility.md`](docs/reproducibility.md)
conserva una foto de hashes del 2026-11-11; para 0.1.1 prevalecen los del
manifiesto del 2026-11-12 transcritos en [`docs/release.md`](docs/release.md).
