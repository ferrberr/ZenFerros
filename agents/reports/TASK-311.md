# TASK-311 — Revisión independiente de freestanding

**Revisor**: compiler_review (distinto de autores de frontend/CLI/runtime)
**Fecha**: 2026-11-11
**Estado**: COMPLETADA — revisión favorable del subconjunto freestanding Hito 2

## Alcance
Revisión de CLI/flags, emisión y ABI C, tipos/casts/bits, punteros/unsafe/volatile, símbolos de runtime y pruebas de objeto/enlace. Solo este informe fue modificado por el revisor. Reproducciones aisladas en `/tmp/zenferros-task311-review`; subprocess con core dumps desactivados.

## Hallazgos
1. **P2, colisión de exports hosted con libc**: `pub fn printf(n:u64)->u64{return n;} fn main()->i32{print_uint(42);return 0;}` pasa check pero ejecuta con estado 1, sin stdout y con error de salida. `pub fn fwrite` afecta a `print` análogamente. La ABI nueva conservaba el nombre del export y sustituía símbolos de libc usados por builtins. Notificado; decisión del orquestador/autor: en Hosted `pub` conservará la semántica previa de visibilidad con nombre interno/static; solo Freestanding `pub` exporta ABI C. **Corregido y verificado**: la CLI real del workspace imprime `42!`, estado 0 y stderr vacío, tanto en normal como optimizado, usando pub printf/pub fwrite/pub main en el mismo programa. Unit y CLI incluyen regresión permanente.
2. **Prueba con declaración C incompatible**: el harness de traps declaraba `extern void failure(void)` para definiciones que devolvían u8/i64/u64. Corregido por orquestador a prototipo coincidente por fixture. Traps en proceso de prueba ejecutados con límite de core 0 para evitar ficheros de crash; **Corregido y verificado** mediante lectura de fixtures y ejecución completa de las pruebas de traps en normal y optimizado.

## Evidencia independiente inicial
- Snapshot aislado: `rtk proxy env CARGO_HOME=/home/ferranfg/proyectos/ZenFerros/.cargo cargo build --offline --manifest-path /tmp/zenferros-task311-review/Cargo.toml`: build correcto, 3,71 s.
- Script Python con semilla 311 genera 384 operaciones `+ - * & | ^ << >>` repartidas entre u8/u16/u32/u64/i32/i64. Referencia: aritmética Python, módulo 2^bits y reinterpretación signed; shift signed de Python. `zen build --target x86_64-unknown-none --emit obj` en -O0/-O2, enlazado a harness C con `cc -std=c11 -no-pie`: **384/384 comparaciones correctas y estado 0 en ambos modos**. Son comprobaciones de corrección, no benchmarks de rendimiento.

## Evidencia final en workspace integrado
- `rtk proxy env CARGO_HOME=/home/ferranfg/proyectos/ZenFerros/.cargo cargo test --offline --manifest-path zen/compiler/Cargo.toml`: **27 unitarios + 8 aceptación freestanding + 11 aceptación hosted, 0 fallos**. Duraciones observadas: 0,23 s + 1,56 s + 0,26 s. Tests usan toolchain real, ELF, ABI C, volatile sobre buffers válidos, strings, negativos, traps y preservación de archivos.
- `rtk proxy python3 infrastructure/scripts/verify_freestanding.py --zen zen/compiler/target/debug/zen --output /tmp/zenferros-task311-review/validation`: **debug y optimized verificados**. Objetos ELF64 x86_64 REL con único import explícito `emit_byte`; link `ld -nostdlib -static`; ELF final sin INTERP/NEEDED ni símbolos pendientes; stdout exacto `Zen freestanding OK\n`, estado 0 en ambos. Script leído y comprobaciones examinadas; logs/métricas de revisión están en el directorio temporal indicado.
- Se reejecutó aisladamente la colisión hosted original con printf/fwrite y main públicos: **normal y optimizado imprimen `42!`, estado 0, stderr vacío**.
- Se leyeron `docs/zen/freestanding.md` y ADR-008: documentan ABI, GCC, tipos, unsafe, runtime, flags y límites reales. No presentan la ejecución del adaptador Linux como arranque de kernel.

## Dictamen
**Favorable para cerrar TASK-310 y Hito 2** en el subconjunto descrito. Los dos hallazgos fueron corregidos y verificados; no quedan hallazgos bloqueantes de esta revisión.

Esta revisión demuestra compilación y enlace freestanding del subconjunto para x86_64 con GCC/binutils del host y ejecución de un adaptador de proceso Linux. No demuestra boot de Ferros, funcionamiento de MMIO real, manejo de interrupciones/traps en kernel, seguridad de punteros raw ni rendimiento competitivo. Las firmas C externas y la validez/alineación/permisos/vida de las direcciones usadas en unsafe siguen siendo responsabilidad del autor.
