# Zen + Ferros

Zen es un lenguaje compilado en desarrollo para programación de sistemas. Ferros será un kernel propio escrito principalmente en Zen.

## Estado real

**Hitos 1–8: completados y verificados** — compilación de archivos `.zen` a ejecutables nativos Linux con frontend Rust y backend C de bootstrap. La cadena es Zen → tokens → AST → comprobación de nombres/tipos → C11 → `cc` → ELF.

El subconjunto ejecutable incluye funciones y recursión, enteros `u8`/`u16`/`u32`/`i32`/`i64`/`u64`, `bool`, `str`, `void`, variables, flujo de control, casts, operaciones de bits y **arrays de tamaño fijo** `[T; N]` con comprobación de rango, además de **structs nominales escalares** locales. Freestanding añade objetos ELF sin libc, ABI C explícita, punteros raw y acceso volatile bajo `unsafe`. Métodos, flotantes, ownership y módulos siguen pendientes.

Ferros arranca en QEMU TCG con kernel y driver serie Zen, PMM, páginas protegidas, heap, excepciones e IRQ0. Ejecuta tres threads con scheduler preemptivo y un ELF Zen separado en ring3 con write/exit/ticks, guarda y W^X. Comprueba seis faults de aislamiento y recupera las páginas de cada invocación.

El Hito7 añade un RAMFS de 1 MiB con VFS mínimo (open/read/write/close) y syscalls de archivos 4–7. El flujo init/shell en CPL3 lista y lee `hello.zen` por VFS (`ls`/`cat`).

La Fase 7 se amplía con **persistencia ATA PIO entre arranques** (`PERSIST: BOOT n`), un **mini-FS persistente ZENFS01** (`PFS: BOOT n FILES=n`, archivos de 512 B visibles por `ls`/`cat`) y un **shell interactivo por COM1**. TASK-924 añade `put archivo texto`: reemplaza un archivo ZENFS01 ya existente desde CPL3 y confirma su contenido tras reiniciar QEMU. La creación desde CPL3 y la atomicidad ante corte de energía siguen pendientes. El runner inyecta el guion de aceptación tras ver `SHELL: READY`.

Hito 9 (parcial) e Hito 10: once componentes del frontend/ejecución están escritos en Zen y verificados. TASK-925 integra lexer, lowering y codegen en una CLI mínima escrita principalmente en Zen, para un subconjunto acotado de archivos reales; el compilador general sigue en Rust. Hay 174 pruebas de self-hosting y una puerta única de calidad (`python3 infrastructure/scripts/verify_all.py`) con madurez y límites en [docs/quality.md](docs/quality.md).

El Hito8 añade un laboratorio de benchmarks reproducible en `benchmarks/` (Zen, C, C++ y Rust; mismo algoritmo, checksum verificado, tiempo de CPU, resultados versionados). Línea base y límites en [docs/benchmarks/results.md](docs/benchmarks/results.md); la conclusión sostenible es paridad aproximada con C/C++ en estas cargas, sin declarar superioridad y sin interpretar diferencias de pocos puntos como señal.

## Arrancar Ferros

Desde la raíz del proyecto (GCC/binutils/Python y compilador Zen release ya construido):

```bash
python3 infrastructure/scripts/boot_ferros.py --all --repeat 3
```

Salida del kernel:

```text
FERROS KERNEL
Powered by Zen
MEMORY: PMM OK
MEMORY: VMM OK
MEMORY: HEAP OK
INTERRUPTS: BREAKPOINT OK
INTERRUPTS: PAGE FAULT OK
INTERRUPTS: TIMER OK
THREADS: CONTEXT OK
SCHEDULER: PREEMPTION OK
SCHEDULER: YIELD AND EXIT OK
SCHEDULER: STATS switches=45 preemptions=25 yields=16 completed=3
PERSIST: BOOT 1
PFS: BOOT 1 FILES=1
USER: Hello from Zen
SHELL> ls
hello.zen
notes.txt
boot.txt
SHELL> cat hello.zen
Hello
USERSPACE: RING3 AND SYSCALLS OK
USERSPACE: ISOLATION AND CLEANUP OK
USERSPACE: STATS runs=7 writes=18 rejected=6 irqs=1
FS: RAMFS OK
FS: VFS OPEN/READ/CLOSE OK
Boot successful
HITO 7 OK
```

QEMU usa TCG, 64 MiB y 1 vCPU, sin red; disco raw solo para la demo ATA. Si falta QEMU: `python3 infrastructure/scripts/setup_qemu.py` descarga las versiones fijadas a `.tools/qemu`, sin instalar paquetes del sistema. Hay timeout, logs y prueba de cancelación. [Guía de usuario](docs/ferros/userspace.md), [sistema de archivos](docs/ferros/filesystem.md) y [evidencia del hito7](agents/reports/TASK-701.md). Los contadores mostrados son de una ejecución real y pueden variar según la temporización.

## Formateador y stdlib

```bash
zen fmt --check archivo.zen
zen fmt --write archivo.zen
zen lint --json archivo.zen
zen lsp                 # servidor LSP para editores
```

`str_eq`, `str_cmp`, `str_find`, `str_starts_with`, `str_ends_with` y `str_rfind` son builtins hosted/freestanding. Guía: `docs/zen/formatter.md`.

## Verificación completa

```bash
python3 infrastructure/scripts/verify_all.py        # puerta completa (compilador, Ferros, QEMU, benchmarks, selfhost)
python3 infrastructure/scripts/verify_all.py --quick
python3 infrastructure/scripts/repro_build.py   # builds reproducibles (C, kernel, usuario)
python3 infrastructure/scripts/ci_matrix.py     # matriz local (quick/defecto/full)
python3 infrastructure/scripts/stability_campaign.py --rounds 5  # estabilidad repetida
```

## Shell interactivo

```bash
python3 infrastructure/scripts/boot_ferros.py --release
```

El runner alimenta `ls\ncat hello.zen\nhelp\nexit\n` y exige la transcripción exacta con `writes=18`. Detalle en [docs/ferros/shell.md](docs/ferros/shell.md).

## Benchmarks

```bash
python3 benchmarks/scripts/bench.py
python3 -m unittest discover -s benchmarks/tests -v
```

Compara Zen con C/C++/Rust en cuatro cargas con el mismo algoritmo y verifica el checksum antes de medir. Zig y clang no están instalados y se declaran como no disponibles. Metodología en [ADR-013](agents/decisions/ADR-013.md) y resultados en [docs/benchmarks/results.md](docs/benchmarks/results.md).

## Compilar y ejecutar

Requisitos actuales: Rust/Cargo y un compilador C11 accesible como `cc` en un anfitrión Linux x86_64. Para freestanding, GCC x86_64 compatible con los flags documentados y binutils (`ld`, `nm`, `readelf`). `CC` puede indicar otra ruta de compilador; se pasa como un único ejecutable, sin shell ni flags embebidos.

Desde la raíz del workspace:

```bash
cargo build --manifest-path zen/compiler/Cargo.toml
zen/compiler/target/debug/zen build zen/examples/hello.zen -o /tmp/hello-zen
/tmp/hello-zen
# Hello, Zen!

zen/compiler/target/debug/zen run zen/examples/factorial.zen
# factorial(10) = 3628800

zen/compiler/target/debug/zen check zen/examples/factorial.zen
zen/compiler/target/debug/zen build zen/examples/factorial.zen --release -o /tmp/factorial-zen
```

En este entorno las dependencias se encuentran en `.cargo/`; usar `CARGO_HOME="$PWD/.cargo" cargo ... --offline` si Cargo no encuentra su caché habitual. El binario de la CLI se llama `zen`.

`zen build` produce un ejecutable en la ruta de `-o`, o junto al archivo de entrada sin la extensión `.zen`. `zen run` usa archivos temporales y propaga el código de salida del programa; `zen check` comprueba el programa sin invocar `cc`. `zen lex` muestra tokens y `zen version` informa del backend real. Solo se aceptan archivos individuales `.zen`; `zen init` y `zen test` quedan para futuras tareas.

Para generar un objeto sin libc y comprobar el enlace:

```bash
zen/compiler/target/release/zen build zen/examples/freestanding.zen --target x86_64-unknown-none --emit obj -o /tmp/zen-free.o
python3 infrastructure/scripts/verify_freestanding.py
```

El script verifica modos normal y optimizado, ausencia de dependencias dinámicas y salida `Zen freestanding OK`. `--emit c` permite inspeccionar C validado. Detalles y límites: [freestanding](docs/zen/freestanding.md).

## Validación

```bash
CARGO_HOME="$PWD/.cargo" cargo test --offline --manifest-path zen/compiler/Cargo.toml
```

La puerta exige **163 pruebas del compilador**, **45 de Ferros**, **6 de benchmarks** y **174 de self-hosting**: **388 en total**. Ferros verifica políticas Zen con mocks/UBSan y QEMU real, incluyendo ELF malformado, rollback PMM, syscalls, aislamiento y faults kernel. TASK-924 añade reemplazo persistente desde CPL3 y TASK-925 añade una CLI parcial con comparación diferencial frente al compilador Rust. Evidencia: [TASK-924](agents/reports/TASK-924.md) y [TASK-925](agents/reports/TASK-925.md).

## Documentación

- [Subconjunto hosted implementado](docs/zen/mvp-native.md)
- [Freestanding, ABI C y unsafe](docs/zen/freestanding.md)
- [Boot inicial y logs QEMU](docs/ferros/boot.md)
- [Persistencia ATA](docs/ferros/persistence.md)
- [Memoria e interrupciones](docs/ferros/memory-interrupts.md)
- [Threads y scheduler](docs/ferros/multitasking.md)
- [Usuario, ELF y syscalls](docs/ferros/userspace.md)
- [Arquitectura actual](ARCHITECTURE.md)
- [Roadmap](ROADMAP.md)
- [Decisión de backend de bootstrap](agents/decisions/ADR-007.md)
- [Reglas de colaboración](AGENTS.md)
- [Formateador](docs/zen/formatter.md), [linter](docs/zen/linter.md) y [LSP](docs/zen/lsp.md)
- [Slices y stdlib de arrays](docs/zen/slices.md)
- [Matriz de CI local](docs/ci.md)
- [CI remoto (workflow no ejecutado)](docs/ci-remote.md)
- [Campaña de estabilidad](docs/stability-campaign.md)
- [Campaña ampliada TASK-917](agents/reports/TASK-917.md)

La gramática `docs/zen/syntax-v0.ebnf` es una propuesta de diseño más amplia que el subconjunto implementado; `zen/examples/structs.zen` ya es código válido y ejecutable. La licencia global del proyecto está pendiente de decisión; no se han incorporado componentes externos de kernel.
