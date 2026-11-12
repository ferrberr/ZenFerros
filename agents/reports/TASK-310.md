# TASK-310: Hito 2 completado — freestanding mínimo x86_64

**Fecha**: 2026-11-11
**Estado**: COMPLETADA / INTEGRADO
**Responsables**: 00 (CLI, flags/toolchain, integración, aceptación y documentación); native_compiler (frontend/backend); compiler_review (revisión independiente TASK-311).

## Resultado

Zen produce objetos ELF64 REL x86_64 sin libc ni startup hosted, con símbolos ABI C definidos por el programa. Se enlazó la muestra Zen con una pequeña entrada asm mediante `ld -nostdlib -static`; el ejecutable resultante no tiene INTERP, NEEDED ni símbolos sin resolver. En normal y optimizado imprime exactamente `Zen freestanding OK\n`, estado 0.

La muestra valida el objeto freestanding en un proceso Linux: el adaptador asm implementa _start, salida de bytes y terminación mediante syscalls. No es un boot de Ferros ni ejecuta instrucciones privilegiadas. El Hito 3 debe proporcionar bootloader, entry/kernel, helper de puertos serie y logs QEMU.

## Cambios implementados

- API Mode Hosted/Freestanding; check_with_mode y emit_c_with_mode, conservando wrappers hosted previos.
- CLI `build --target x86_64-unknown-none --emit obj/c`; `check --target ...`; emisión hosted exe por defecto y obj/c también disponibles. Sin main requerido en freestanding y sin autoenlace de kernel ficticio.
- Backend freestanding con encabezados C freestanding, conversiones aritméticas sin memcpy, helpers escalares y trap nativo. Se omiten libc/print, main y runtime hosted.
- Flags de objeto: sin red zone, PIC/PIE, stack protector, SIMD ni unwind; code model kernel, secciones por función/datos. Contrato GCC x86_64 y flags exactos en ADR-008; no se anuncia compilación cruzada general.
- u8/u16/u32, casts enteros explícitos, bits y shifts con wrapping/rango/semántica definidos, incluyendo compuestos.
- Freestanding pub fn exporta nombre ABI C; extern "C" importa firmas escalares y raw pointers. Sin str en frontera ABI, sin prefix externo __zen_. Hosted pub conserva visibilidad/nombres internos.
- Punteros raw de un nivel a enteros, casts pointer↔u64 y volatile_load/store bajo unsafe. Escritura solo por pointer mutable y con valor del tipo correcto. La validez, alineación, permisos y vida son obligación del autor del bloque unsafe.
- str_len y str_byte sin libc sobre strings estáticos UTF-8, NUL conservado e índice comprobado.
- Nueva muestra `zen/examples/freestanding.zen`, adaptador y linker Linux en `infrastructure/freestanding/`, verificador reproducible `infrastructure/scripts/verify_freestanding.py`.
- README, especificación del subconjunto, arquitectura, roadmap y ADR-008 actualizados. Structs/layout, arrays, inline asm Zen, manejo de excepciones y atributos de sección personalizados siguen pendientes explícitamente.

## Pruebas y comandos reales

```text
rtk proxy env CARGO_HOME=/home/ferranfg/proyectos/ZenFerros/.cargo cargo test --offline --manifest-path zen/compiler/Cargo.toml
Finished test profile in 1.26s
27 unitarios passed; 0 failed (0.11s)
8 aceptación freestanding passed; 0 failed (0.99s)
11 aceptación hosted passed; 0 failed (0.26s)
0 doc tests; 0 failed

rtk proxy env CARGO_HOME=/home/ferranfg/proyectos/ZenFerros/.cargo cargo test --release --offline --manifest-path zen/compiler/Cargo.toml
Finished release profile in 5.51s
27 unitarios passed; 0 failed (0.01s)
8 aceptación freestanding passed; 0 failed (1.02s)
11 aceptación hosted passed; 0 failed (0.26s)
0 doc tests; 0 failed

rtk proxy python3 infrastructure/scripts/verify_freestanding.py
debug: ELF64 object + static no-libc executable verified; Zen freestanding OK
optimized: ELF64 object + static no-libc executable verified; Zen freestanding OK

rtk proxy rustfmt --edition 2021 --check zen/compiler/src/mvp.rs zen/compiler/src/main.rs zen/compiler/src/native.rs zen/compiler/tests/freestanding_cli.rs zen/compiler/tests/native_cli.rs
exit 0
```

Son 46 tests permanentes por perfil (13 más que al cerrar Hito 1), con múltiples casos por test. Se prueban ELF REL, ausencia de runtime implícito, flags reales capturados mediante wrapper CC, ABI C, punteros/volatile en buffers válidos, bits/casts/shifts, strings/NUL/UTF-8, negativos de unsafe/tipos/ABI/rangos, traps, emisión C/check sin CC, preservación de fuente y objeto ante fallo y regresión completa hosted.

La revisión independiente añade 384 operaciones aritméticas/de bits/shift contra referencia Python en ambos niveles; la implementación también comprobó C generado y harness con UBSan en -O0/-O2, sin diagnósticos. Detalles en TASK-311 y reporte del agente; no se contabilizan estos casos internos como tests Cargo adicionales.

## Fallos descubiertos y corregidos

1. P2: exportar pub printf/fwrite en hosted podía reemplazar libc y romper los builtins. Corregido: solo freestanding pub exporta ABI; hosted mantiene nombres internos. Revisión independiente y tests unitario/CLI permanentes verifican regresión en ambos modos. No se usa una denylist incompleta de símbolos libc.
2. El primer harness de traps usaba retorno C void para funciones Zen escalares: prototipos corregidos para coincidir antes de validar. Los hijos que prueban traps tienen core dumps desactivados.
3. Se corrigió una expectativa aritmética del fixture (resultado correcto 1255) antes de su primera ejecución integrada.

No hubo fallos en las suites integradas debug/release finales. Revisión cruzada TASK-311 favorable, sin hallazgos bloqueantes.

## Métricas observadas — sin comparación de rendimiento

| Flags C | Objeto bytes | ELF sin libc bytes | Compilación s | Enlace s |
|---------|--------------|--------------------|---------------|----------|
| -O0 | 16744 | 10264 | 0.062379 | 0.004228 |
| -O2 | 1344 | 4832 | 0.036185 | 0.003865 |

Una ejecución por configuración, en este entorno Linux x86_64/GCC 16.2.1/Rust 1.99.1. Incluyen frontend + cc en compilación, y ld por separado. No se midió memoria máxima, p95/p99, energía, caché o asignaciones. La reducción optimizada de la muestra pequeña no constituye benchmark comparativo del lenguaje.

- Objetos y ELF conservados: `zen/compiler/target/milestone-2/`.
- Comandos completos, readelf/nm, stdout y estados: `agents/reports/TASK-310-validation.log`.
- Métricas estructuradas: `agents/reports/TASK-310-metrics.json`.
- Guía reproducible y semántica: `docs/zen/freestanding.md`.

## Integración y riesgos pendientes

Frontend implementado en repositorio Git aislado `/tmp/zenferros-task310-frontend`, rama task310-frontend, commit final eed3358; copiado a workspace secuencialmente después de entrega. CLI/native/tests son propiedad exclusiva del orquestador. Revisor distinto de los autores no modificó implementación. El .git visible del workspace sigue vacío/protegido; no se declara commit/merge allí.

Pointers no son memoria segura ni volatile una operación atómica/barrera. La firma C externa debe coincidir con el proveedor. No se han validado MMIO real, interrupciones, SSE context, SMP, stack de kernel, bootloader ni QEMU. El trap exige futura gestión de excepciones. `-mcmodel=kernel` y las convenciones de llamada condicionan el layout/stack que deberá aportar Ferros. QEMU no está actualmente en PATH.

## Próximo objetivo verificable

Hito 3: arrancar Ferros con código de kernel compilado desde Zen, inicializar salida serie y capturar el mensaje requerido en QEMU con timeout y resultado automatizado. Revalidar herramientas de boot/QEMU y documentar helpers asm/C indispensables, sin convertir el kernel en una implementación mayoritariamente anfitriona.
