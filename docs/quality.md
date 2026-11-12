# Calidad y madurez — Hito 10 (TASK-907)

Fecha: 2026-11-11. Este documento declara **qué está verificado hoy** en Zen/Ferros, con qué evidencia y qué queda fuera. No es una certificación de estabilidad ni una comparación de rendimiento.

La puerta única es `python3 infrastructure/scripts/verify_all.py`; ejecuta las suites y la aceptación QEMU en secuencia, con timeout por paso, y devuelve `0` solo si todo pasa.

## Niveles

Los niveles son los de [`AGENTS.md`](../AGENTS.md), aplicados de forma acumulativa:

| Nivel | Criterio |
|---|---|
| Experimental | Prototipo que compila; sin suite funcional completa. |
| Verificado | Pasa tests funcionales automatizados del subsistema. |
| Integrado | Además funciona con los componentes vecinos en la ruta real (CLI, kernel/QEMU). |
| Estable | Regresión sostenida y estrés/fallos inyectados a escala. |
| Optimizado | Benchmarks reproducibles y una mejora medida y justificada. |

**Ningún subsistema se declara hoy Estable ni Optimizado.** Las suites son de regresión funcional; TASK-905 añade campañas de estrés acotadas (6 boots, 2 rondas, fuzz diferencial), no campañas prolongadas. TASK-802 midió `-O3`/LTO y decidió mantener `-O2` (ADR-015): hay una decisión justificada, pero no una mejora aplicada, así que `Optimizado` no se declara.

## Madurez por subsistema

| Subsistema | Nivel | Evidencia | Límite declarado |
|---|---|---|---|
| Lexer, parser, nombres/tipos, emisión C11, CLI | Integrado | [TASK-210](../agents/reports/TASK-210.md), [TASK-211](../agents/reports/TASK-211.md), [TASK-310](../agents/reports/TASK-310.md), [TASK-311](../agents/reports/TASK-311.md), [TASK-213](../agents/reports/TASK-213.md), [mvp-native](zen/mvp-native.md) | Subconjunto MVP con arrays fijos y structs escalares locales; floats, módulos, globals, ownership, métodos y paso de structs entre funciones no implementados. |
| Punteros raw/volatile/unsafe, ABI C, bits/casts, freestanding | Integrado | [TASK-310](../agents/reports/TASK-310.md)/[TASK-311](../agents/reports/TASK-311.md), [freestanding](zen/freestanding.md) | Objetos x86_64 con GCC del host; sin inline asm, secciones ni layout explícito del lenguaje. |
| Boot Ferros, Multiboot1, UART | Integrado | [TASK-410](../agents/reports/TASK-410.md)/[TASK-411](../agents/reports/TASK-411.md), [boot](ferros/boot.md) | Solo QEMU TCG; sin hardware físico, UEFI/ISO ni KVM. |
| Infraestructura QEMU (runner) | Integrado | [TASK-410](../agents/reports/TASK-410.md)/[TASK-411](../agents/reports/TASK-411.md), [TASK-703](../agents/reports/TASK-703.md) | QEMU local 11.1.3 con versiones/SHA256 fijados; `-smp 1`, sin red; disco raw solo para la demo ATA de persistencia. |
| PMM/VMM/heap, IDT/PIC/PIT | Integrado mínimo | [TASK-510](../agents/reports/TASK-510.md)/[TASK-511](../agents/reports/TASK-511.md), [memory-interrupts](ferros/memory-interrupts.md) | Identidad 64 MiB, arena sin free individual, sin IST/IRQ anidada/SMP. |
| Threads y scheduler round-robin | Integrado mínimo | [TASK-610](../agents/reports/TASK-610.md)/[TASK-611](../agents/reports/TASK-611.md), [multitasking](ferros/multitasking.md) | Mismo address space, stacks estáticos; sin prioridades, FPU/SIMD ni SMP. |
| ELF de usuario CPL3 e `int0x80` | Integrado mínimo | [TASK-710](../agents/reports/TASK-710.md)/[TASK-711](../agents/reports/TASK-711.md), [userspace](ferros/userspace.md) | Una invocación activa, CR3 compartido; sin `SYSCALL`, ASLR, KPTI, TLS ni cuota de CPU. |
| RAMFS/VFS/ZENFS01 | Integrado mínimo | [TASK-701](../agents/reports/TASK-701.md), [TASK-924](../agents/reports/TASK-924.md), [filesystem](ferros/filesystem.md) | RAMFS volátil; ZENFS01 permite reemplazo síncrono de archivos existentes hasta 512 B, sin creación desde CPL3, directorios dinámicos, unlink ni atomicidad ante corte. |
| Shell interactivo COM1 | Integrado mínimo | [TASK-703](../agents/reports/TASK-703.md), [shell](ferros/shell.md) | Polling sin IRQ serie; sin edición de línea, historial, tuberías ni teclado PS/2. |
| Benchmarks comparativos | Integrado mínimo (línea base) | [TASK-801](../agents/reports/TASK-801.md), [TASK-802](../agents/reports/TASK-802.md), [ADR-013](../agents/decisions/ADR-013.md), [ADR-015](../agents/decisions/ADR-015.md), [results](benchmarks/results.md), [opt-flags](../benchmarks/results/opt-flags.md) | Cuatro cargas enteras; sin floats/SIMD/concurrencia ni `perf`; paridad aproximada, no ranking. `-O2` se mantiene. |
| Componentes de self-hosting y CLI mínima | Verificado (Hito 9 parcial) | [TASK-902](../agents/reports/TASK-902.md), [TASK-925](../agents/reports/TASK-925.md), [selfhost](zen/selfhost.md) | La CLI procesa un subconjunto acotado; el compilador completo sigue en Rust y no se compila a sí mismo. |
| Gramática completa | Experimental (propuesta) | [syntax-v0.ebnf](zen/syntax-v0.ebnf) | Borrador no conectado al parser ni equivalente a lo implementado. |

Fuera de la escala (no implementado, se rechaza o no existe): structs con métodos/paso entre funciones, floats, ownership/borrowing, módulos reales, inline asm del lenguaje, stdlib amplia, IPC, procesos concurrentes, VirtIO, creación persistente desde CPL3/journaling, SMP, `SYSCALL/SYSRET`, ASLR/KPTI y LSP avanzado. Arrays fijos, structs escalares, inclusión textual `use`, formatter, linter y LSP mínimo sí existen.

## Estrés y fuzzing

`infrastructure/scripts/stress.py` complementa la puerta con campañas acotadas: arranques QEMU con guiones válidos/sin entrada/inválidos, rondas repetidas de Ferros y selfhost, y fuzz diferencial de parser y lexer contra referencias (TASK-905). Resultados y límites en `docs/stability.md`. No sustituye a una campaña larga ni a fuzzing guiado por cobertura.

## Puertas de calidad

`verify_all.py` ejecuta estos pasos en orden, **comprueba el número de tests esperado de cada suite** (163/45/6/174) y **aborta en el primero que falla**. Si un filtro reduce la cobertura sin cambiar el exit code, la puerta falla; actualizar `EXPECTED_COUNTS` solo cuando el cambio de cobertura sea intencionado. El paso 7 es obligatorio desde que el autohosting parcial forma parte del repo.

| # | Puerta | Cobertura | Timeout |
|---|---|---|---|
| 1 | `cargo build --release --offline` | Compilador Zen compila con `CARGO_HOME=.cargo`. | 600 s |
| 2 | `cargo test --release --offline` | 163 tests: 34 unitarios + 9 arrays + 10 fmt + 8 freestanding + 10 include + 11 native + 12 slices + 12 stdlib + 12 stdlib_ext + 15 structs + 18 lint + 12 LSP. | 600 s |
| 3 | `python3 -m unittest discover -s ferros/tests` | 45 tests de Ferros: host con mocks y UBSan, más guests QEMU (incluido reemplazo persistente desde CPL3). | 900 s |
| 4 | `python3 -m unittest discover -s benchmarks/tests` | 6 tests del arnés: paridad, estadísticas y aborto por checksum. | 300 s |
| 5 | `python3 infrastructure/scripts/boot_ferros.py --all --repeat 1` | Aceptación QEMU: 2 arranques (debug+release), estado 33, transcripción exacta del shell, `writes=18`. Con `--full`: `--repeat 3` → 6 arranques. | 900 s |
| 6 | `python3 benchmarks/scripts/bench.py --reps 3 --warmup 1 --json <tmp> --md <tmp>` | 4 cargas × 4 lenguajes, checksum verificado antes de medir. | 900 s |
| 7 | `python3 -m unittest discover -s zen/selfhost/tests` | 174 tests: 166 de componentes y 8 de la CLI mínima TASK-925, con comparación diferencial de archivos reales. No implica compilador completo. | 300 s |
| 8 | `python3 infrastructure/scripts/repro_build.py --quick` (completo con `--full`) | Dos builds de C generado y `ferros-user.elf` (y kernel en `--full`) con hashes idénticos; manifiesto de toolchain. | 300 s |

Modos:

| Comando | Pasos | QEMU |
|---|---|---|
| `python3 infrastructure/scripts/verify_all.py --quick` | 1–4, 7 y 8 (repro rápida) | — |
| `python3 infrastructure/scripts/verify_all.py` | 1–8 | 2 arranques |
| `python3 infrastructure/scripts/verify_all.py --full` | 1–8 (repro completa) | 6 arranques |

Notas de la puerta:

- La puerta **no impone un umbral de rendimiento**: el paso 6 verifica corrección y reproducibilidad de la medición, no una mejora. TASK-802 ya decidió mantener `-O2` (ADR-015), pero esa decisión no se convierte en un test de rendimiento.
- Los logs completos y el JSON/MD del benchmark se guardan en `/tmp/zenferros-verify-*`; no se escriben artefactos de medición en el repositorio. Los directorios `target/`, `ferros/build/` y `benchmarks/build/` ya están en `.gitignore`.
- El paso 7 es obligatorio: si `zen/selfhost/tests` no existe, la puerta falla; además, cualquier suite que reporte tests `skipped` hace fallar la puerta (no se acepta cobertura reducida por entorno).

## Qué NO está verificado

- **Hardware físico, KVM y UEFI/ISO**: todo se ejecuta en QEMU TCG (`-smp 1`, Multiboot1 directo). No hay `/dev/kvm`, ni arranque en metal, ni ISO/UEFI (TASK-410/411).
- **SMP y concurrencia real**: un solo CPU, sin IRQ anidadas, IST, `swapgs`, barreras ni sincronización; `volatile` no es atomicidad.
- **Persistencia**: RAMFS es volátil; ZENFS01 permite reemplazar desde CPL3 un archivo existente hasta 512 B y leerlo tras reiniciar (TASK-924). No hay creación/borrado desde CPL3, journaling, atomicidad ante corte ni VirtIO.
- **Self-hosting completo**: el compilador sigue escrito en Rust; TASK-902/902B/902C/902D/902E/902F/902G/902H/902I/902J/902K verifican once componentes (lexer contador, lexer con tokens, evaluador, AST, intérprete de sentencias, intérprete con funciones, typechecker y cuatro codegens) por comportamiento, no un compilador completo. Hay stdlib mínima de strings (ADR-019), formatter `zen fmt` (ADR-020), linter `zen lint` con JSON (ADR-021) y LSP mínimo `zen lsp` (ADR-022); no hay CI remoto, stdlib amplia ni bootstrap del compilador en Zen.
- **Floats, SIMD y concurrencia en benchmarks**: el lenguaje no tiene floats/SIMD; las cargas son enteras. Sin `perf` no hay ciclos, instrucciones ni fallos de caché, y el host es compartido (TASK-801).
- **Estabilidad y seguridad**: TASK-905 aporta campañas acotadas y fuzz diferencial; siguen faltando estrés prolongado, inyección de fallos a escala, fuzzing guiado por cobertura y auditoría formal. El heap no libera de forma general y el scheduler es de un solo uso.
- **Aislamiento completo de procesos**: CR3 compartido con el kernel, sin ASLR/KPTI/TLS/estado SIMD aislado; el loader ignora section headers y no relocaliza.
- **Procedencia reproducible**: TASK-922 creó un historial Git local a partir del corte `e7737a6`; los cortes anteriores siguen sin historial recuperable. Hay remoto configurado, pero esta puerta es local y todavía no aporta evidencia de una ejecución de CI en GitHub ni fija un contenedor de build.

## Reproducción

Requisitos: Python 3, `cargo` con el registro offline cacheado, `cc`/GCC x86_64 y QEMU local en `.tools/qemu` (o en `PATH`). `CARGO_HOME` lo fija la propia puerta en `.cargo/`.

```bash
# Puerta rápida (compilador + Ferros + arnés + selfhost si existe)
python3 infrastructure/scripts/verify_all.py --quick

# Puerta completa por defecto: añade 2 arranques QEMU y la medición de benchmarks
python3 infrastructure/scripts/verify_all.py

# Aceptación completa: 6 arranques QEMU (debug+release ×3)
python3 infrastructure/scripts/verify_all.py --full
```

Comandos equivalentes por paso, si se quiere reproducir uno aislado:

```bash
CARGO_HOME="$PWD/.cargo" cargo build --release --offline --manifest-path zen/compiler/Cargo.toml
CARGO_HOME="$PWD/.cargo" cargo test --release --offline --manifest-path zen/compiler/Cargo.toml
python3 -m unittest discover -s ferros/tests
python3 -m unittest discover -s benchmarks/tests
python3 infrastructure/scripts/boot_ferros.py --all --repeat 3
python3 benchmarks/scripts/bench.py --reps 3 --warmup 1 --json /tmp/bench.json --md /tmp/bench.md
python3 -m unittest discover -s zen/selfhost/tests   # solo si existe
```

Tiempos observados en este host (AMD Ryzen 7 260, carga compartida, 2026-11-11): `--quick` ≈ 24 s; `--full` ≈ 33 s, de los cuales ~4 s son los 6 arranques QEMU y ~5 s la medición de benchmarks. Son tiempos de puerta con caché de compilación; una compilación limpia o un host más cargado tardan más. Los tiempos no son un benchmark.

## Cómo leer la evidencia

- Un informe de tarea describe una ejecución concreta; no sustituye a la puerta actual. Si el código cambia, hay que volver a ejecutar `verify_all.py`.
- Los contadores QEMU (`writes=18`, `runs=7`, `rejected=6`) y la transcripción del shell son un contrato congelado en TASK-703; cambiarlos exige actualizar runner, kernel y pruebas a la vez.
- Los benchmarks se leen como línea base y detector de regresiones, no como ranking de lenguajes: Zen y C comparten backend C11 y las diferencias de pocos puntos quedan dentro del ruido del host.
