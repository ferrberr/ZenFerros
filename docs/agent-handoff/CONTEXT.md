> **Documento histórico de la transferencia Codex→DSH (2026-11-11).** No describe el estado actual; el estado vigente está en `agents/STATE.md`, `ROADMAP.md`, `ARCHITECTURE.md` y `docs/quality.md`.

# Contexto de Zen + Ferros

Transferencia Codex → DeepSeek Harness (DSH), 11 de noviembre de 2026.
Rutas de este documento relativas a la raíz del proyecto, salvo indicación expresa.

## Objetivo y procedencia

El proyecto comenzó en DSH, continuó en Codex y vuelve a DSH por petición del usuario. Crear un lenguaje compilado de sistemas (Zen) y un sistema operativo independiente (Ferros), escrito principalmente en Zen. Ferros debe probar las capacidades reales del lenguaje. Rendimiento extremo, seguridad de memoria, herramientas, stdlib y self-hosting son objetivos de investigación; no capacidades demostradas del MVP.

La misión original exige software compilable y verificable, sin declarar resultados sin evidencia. Se consultó el inicio del prompt maestro adjunto a la conversación; no se copia el adjunto completo ni se asume que esté disponible en DSH. Se mantienen sus objetivos compatibles con la implementación actual.

## Arquitectura ejecutable

```text
.zen → lexer Rust → parser/AST/typechecker MVP → C11 → cc/GCC → ELF
                                      ├─ host Linux: ejecutable
                                      └─ freestanding: objeto sin libc
objetos kernel + ASM + linker → ELF64 → contenedor ELF32 Multiboot → QEMU
ELF64 usuario separado → bytes rodata kernel → loader Zen → páginas U → CPL3
```

No hay backend LLVM/Cranelift operativo. El frontend activo vive en `zen/compiler/src/mvp.rs`; `src/lib.rs` expone lexer, diagnostics, mvp y native. `src/native.rs` genera/compila C, usa procesos sin shell y publica resultados tras éxito. `src/ast/`, `src/parser/` y `grammar.lalrpop` conservan borradores históricos no conectados al pipeline vigente.

## Componentes y relaciones

| Ruta | Responsabilidad y relación |
|---|---|
| `zen/compiler/` | CLI y frontend/backend C11; produce objetos usados por Ferros |
| `zen/examples/` | Ejemplos; algunos, como structs, son propuestas todavía rechazadas |
| `ferros/boot/entry.S`, `linker.ld` | Multiboot32, long mode, BSS/GDT/tablas iniciales y layout ELF |
| `ferros/kernel/arch/x86_64/` | ABI externa y primitivas ASM de CPU, interrupciones, cambio de contexto y CPL3 |
| `ferros/kernel/drivers/serial.zen` | COM1, configuración/loopback y polling acotado |
| `memory.zen` | PMM bitmap, VMM 4KiB, protección y arena heap |
| `interrupts.zen` | IDT/PIC/PIT y dispatch; reconoce EOI antes de scheduler |
| `scheduler.zen` | Tres threads kernel, round-robin PIT/yield/exit y pruebas de contexto |
| `userspace.zen` | Loader ELF, páginas de usuario, syscalls, faults y teardown |
| `runtime.zen`, `main.zen` | Panic/fin y secuencia de aceptación de hitos |
| `ferros/user/` | Programa Zen separado, adaptadores ASM int0x80 y linker usuario |
| `infrastructure/scripts/` | Build kernel/usuario, QEMU, toolchain local y métricas |
| `ferros/tests/`, `zen/compiler/tests/` | Mocks host seguros, CLI real y pruebas QEMU |
| `agents/tasks`, `agents/reports`, `agents/decisions` | Contratos, evidencia y ADR; fuente de continuidad |

Los nombres de unidades kernel de la tabla residen bajo `ferros/kernel/`. El build concatena explícitamente ocho unidades Zen; no son módulos del lenguaje. ASM reserva BSS y expone getters para estado mutable. Algoritmos y políticas principales están escritos en Zen; el C del kernel es generado, no un kernel manual en C.

## Tecnologías y dependencias

- Rust/Cargo, edición2021; paquete `zen-compiler`0.1.0. Dependencias directas verificadas en Cargo.toml: clap4.5/derive, phf0.11/macros, anyhow1.0, codespan-reporting0.11. Consultar Cargo.lock para resoluciones exactas.
- Linux x86_64, GCC/cc compatible con C11 y binutils (`ld`, `as`, `nm`, `readelf`, `objcopy`, `objdump`). `CC` admite una ruta de ejecutable; no flags embebidos.
- Python3 para scripts/tests; mocks C y UBSan en pruebas host. Código privilegiado exclusivamente en guest.
- QEMU11.1.3 local según evidencia, TCG/qemu64/una CPU. Paquetes/URLs/SHA256 fijados en `infrastructure/toolchains/qemu-packages.json`, instalación local con `setup_qemu.py`. `.tools/qemu` y `.cargo` son recursos locales ignorados: comprobar disponibilidad al trasladar.
- Perfil freestanding sin libc, PIC/PIE, red zone, stack protector, SIMD ni unwind; actual `-mcmodel=kernel`. No es compilación cruzada general. Usuario se enlaza debajo de2GiB para compatibilidad con este perfil.

## Contratos importantes del producto

No existen reglas comerciales de dominio; las reglas relevantes son semánticas, de seguridad y aceptación:

- Tipos implementados: u8/u16/u32/i32/i64/u64/bool/str/void; funciones, recursión, control de flujo, mutabilidad explícita y ámbitos. Sin structs, arrays, floats, módulos, ownership o stdlib general.
- Enteros de anchura fija con add/sub/mul/neg envolventes; errores de división y shifts fuera de rango producen trap. Evaluación de efectos de izquierda a derecha y booleanos en cortocircuito.
- `str` es vista estática UTF-8 con longitud; `str_len`/`str_byte`, con comprobación de límites. ABI externa no pasa str.
- Punteros raw/volatile/casts puntero-entero y llamadas extern requieren unsafe. Eso no garantiza seguridad de memoria ni atomicidad SMP.
- `pub fn` exporta símbolo exacto freestanding; hosted conserva nombres internos para no interponer libc. Prefijo `__zen_` reservado.
- PMM máximo64MiB y mapa Multiboot acotado. Heap arena64KiB sin free individual. IRQs y mutaciones críticas IF0, una CPU.
- Kernel: hojas supervisor, textoRX, rodataR-NX y datos/stackRW-NX; nullguard, WP y NX. Bootstrap previo usa identidad1GiB/RWX transitoria.
- Usuario: ventana [0x40000000,0x40200000), imagen debajo0x40100000, stack16KiB desde0x401fc000 y guard0x401fb000. Una invocación activa, mismoCR3 con páginas kernel supervisor.
- Loader ELF64 ET_EXEC estático, hasta128KiB/8PHDR, LOADs alineados/no solapados/W^X y entry ejecutable dentro de bytes de archivo; zero/copy antes de publicar, rollback y unmap/invlpg antes de devolver PMM.
- ABI int0x80: RAX número/resultado, RDI/RSI/RDX argumentos; write1,exit2,ticks3. Write≤4096 valida rango entero antes de salida. EFAULT−14, EINVAL−22, ENOSYS−38.
- Solo IDT128 DPL3; GDT/TSS/RSP0, IOPL0. Fault síncrono de usuario termina tarea; kernel faults y eventos graves del sistema siguen fatales.
- Éxito QEMU requiere estado33, serie exacta y contadores válidos. Panic35. Nunca sustituir resultados observados por mensajes estáticos de éxito.

## Reglas de colaboración

Leer `AGENTS.md` vigente: contratos con ID/responsable/dependencias/archivos/aceptación/tests/resultado; evidencia y revisión por otro agente del código crítico. Aislar cambios paralelos y no editar concurrentemente el mismo componente. Resolver y registrar bloqueos, leer roadmap/arquitectura/tareas/informes al reanudar.

Preferencias del usuario: progreso autónomo por hitos con informe breve al cierre; optimizar modelos/esfuerzo/tokens según tarea, sin inventar ahorro medido. Instrucción explícita final: **no usar Astra**. No se presupone equivalencia entre modelos de Codex y los disponibles en DSH.

Fuentes principales: `ARCHITECTURE.md`, `ROADMAP.md`, `docs/zen/{mvp-native,freestanding}.md`, `docs/ferros/`, ADR-007 a ADR-012 y reportes TASK-210 a TASK-711.
