# Arquitectura actual de Zen + Ferros

Actualización: 2026-11-11. El estado se basa en código activo y evidencia de TASK-210/TASK-211, TASK-310/TASK-311, TASK-410/TASK-411, TASK-510/TASK-511, TASK-610/TASK-611, TASK-710/TASK-711 y TASK-701. Los informes anteriores describen decisiones/prototipos históricos.

## Cadena implementada

```text
archivo .zen
 → Lexer UTF-8 con spans y errores
 → parser recursivo del subconjunto MVP
 → nombres, firmas, ámbitos, tipos, mutabilidad, retornos
 → C11 con temporales ordenados y helpers enteros
 → compilador C del anfitrión (cc, CC opcional)
 → ejecutable ELF hosted o objeto ELF64 freestanding x86_64
```

El frontend está escrito en Rust. `src/lib.rs` expone `lexer`, `mvp`, `native`, `fmt`, `lint`, `lsp` y `diagnostics`; el parser, AST y comprobador activos están en `src/mvp.rs`. `mvp::check` valida sin ejecutar herramientas externas. `mvp::emit_c` produce C solo si el programa completo es válido. `native::build` llama `cc` sin shell, compila a un directorio temporal junto al destino y publica por rename solo tras éxito. La CLI implementa `build`, `run`, `check`, `lex`, `fmt`, `lint`, `lsp`, `version`; build soporta `--emit exe/obj/c` y build/check seleccionan `--target host/x86_64-unknown-none`.

La carpeta histórica `src/ast/`, `src/parser/` y `grammar.lalrpop` conserva borradores no conectados, sin garantía de compilación ni cobertura del MVP. No se ejecuta lalrpop en el build. Se retiraron de Cargo los backends y crates no utilizados.

## Estado de subsistemas

| Subsistema | Madurez | Evidencia / ubicación |
|------------|---------|-----------------------|
| Lexer MVP | Integrado | `src/lexer/`; regresiones de literales, comentarios, spans UTF-8 |
| Parser/AST MVP | Integrado | `src/mvp.rs`; funciones, expresiones y flujo comprobados |
| Nombres y tipos MVP | Integrado | Tipos escalares, ámbitos, mutabilidad y retornos; casos negativos |
| Emisión C y enlace hosted | Integrado | ELF, stdout, estados y semántica normal/optimizada |
| CLI build/run/check | Integrado | Pruebas de aceptación mediante procesos reales |
| Pruebas de compilador | Integrado | `zen/compiler/tests/native_cli.rs` y tests unitarios |
| Gramática completa | Propuesta | `docs/zen/syntax-v0.ebnf`; no equivale a lo implementado |
| Punteros raw/volatile, unsafe, ABI C escalar, bits/casts | Integrado | Hito 2, TASK-310/TASK-311; harness y negativos |
| Arrays de tamaño fijo `[T; N]` | Integrado | TASK-213/915; locales y slices `[u64]` como parámetro; bounds-check; sin inferencia/multidim |
| Structs nominales escalares | Integrado | TASK-214, ADR-017; campos escalares, locales; sin métodos/params/retorno |
| Floats, módulos, ownership, métodos | No implementados | Se rechazan explícitamente; structs escalares locales sí existen (TASK-214) |
| Stdlib amplia, heap, self-hosting completo | Parcial | Builtins de salida + `str_eq/str_cmp/str_find` (ADR-019); sin colecciones/IO/allocación; autohosting parcial en `zen/selfhost/` |
| Freestanding x86_64 | Integrado | Objetos sin libc; enlace estático y ejecución de adaptador Linux |
| Compilación cruzada general | No implementada | Perfil requiere GCC x86_64 del host |
| Kernel/boot Ferros | Integrado | Kernel Zen, Multiboot32→longmode64, header/layout y QEMU verificados |
| Driver serie COM1 Zen | Integrado | Config/loopback/polling acotado en drivers/serial.zen, IO asm mínimo |
| PMM bitmap/arena heap | Integrado mínimo | Mapa Multiboot real, reservas/alloc/free/agotamiento, arena64KiB |
| VMM4KiB protegido | Integrado mínimo | Identidad64MiB, nullguard, textoRX/rodataR-NX/dataRW-NX, CR3/NX/WP y PF reales |
| IDT/excepciones/PIC/PIT | Integrado mínimo | Int3, PF null/RO one-shot y3ticks IRQ0 reales, resto fatal |
| Threads/scheduler RR | Integrado mínimo | 3stacks con guard, preemption PIT/yield/exit/controlador y probes15GPR |
| ELF Zen usuario/CPL3, int0x80 | Integrado mínimo | Loader validado/rollback, U/S/W^X, stack/guard, write/exit/ticks y faults contenidos, TASK-710/711 |
| RAMFS/VFS en memoria | Integrado mínimo | `ferros/kernel/vfs.zen`; 256 bloques×4KiB, 128 inodos, open/read/write/close y errores; TASK-701 |
| Syscalls de archivos int0x80 | Integrado mínimo | open4/read5/write6/close7 con validación de buffers; init/shell CPL3 verificado; TASK-701 |
| Shell interactivo / COM1 RX | Integrado mínimo | `serial_try_read` (polling), syscall 8 read_char, comandos help/ls/cat/exit, inyección de stdin tras READY; TASK-703 |
| Mini-FS persistente ZENFS01 + VFS read-only | Integrado mínimo | `storage_fs.zen` 8 archivos/512 B; `vfs.zen` sirve `ls`/`cat` desde instantánea; TASK-916/919, ADR-027/028 |
| Procesos concurrentes, IPC, otros drivers, FS montado en VFS | No implementados | Hitos posteriores |
| Infraestructura QEMU | Integrada | QEMU11.1.3 local/TCG, timeout, logs, debug-exit y cancelación verificados |
| Benchmarks comparativos | Integrado mínimo | `benchmarks/` 4 cargas × Zen/C/C++/Rust, checksum y CPU-time; TASK-801, ADR-013; sin perf/SIMD/floats |
| Autohosting parcial (frontend en Zen) | Verificado | `zen/selfhost/` lexer contador y con tokens + parser/evaluador + AST + intérpretes de sentencias y funciones + typechecker + cuatro codegens C, compilados por Zen; 166 tests; ADR-014/016/023/024 |
| Puerta de calidad y madurez | Integrado | `verify_all.py` (8 pasos, ~47 s) y `docs/quality.md`; TASK-907/908 |

Integrado significa aquí que los componentes del MVP funcionan juntos; no se declara estabilidad frente a estrés general ni optimización propia.

## Contratos del lenguaje implementado

Tipos: `u8`, `u16`, `u32`, `i32`, `i64`, `u64`, `bool`, `str`, `void` (solo retorno); arrays `[T;N]` y slice `[u64]` solo como parámetro (TASK-915). Tipos exactos sin coerciones entre variables. Literales con inferencia contextual y rango comprobado. Entrada hosted `fn main() -> i32`. Funciones con parámetros inmutables, llamadas adelantadas y recursión. Variables inicializadas e inmutables salvo `let mut`; scopes con shadowing interior. Flujo mediante `if/else`, `while`, `break`, `continue`, `return` explícito.

Semántica de enteros definida por anchura fija; add/sub/mul/neg envuelven en complemento a dos. Division/resto inválidos producen error de ejecución. El backend usa aritmética unsigned y conversión aritmética explícita a firmado para evitar overflow firmado de C, sin memcpy. Cualquier expresión con efectos se evalúa a temporales de izquierda a derecha; booleanos hacen cortocircuito. Las cadenas son vistas estáticas UTF-8 con longitud, incluidos bytes NUL. Los nombres C se generan internamente.

Builtins hosted: `print(str)`, `print_uint(u64)`, `print_int(i64)`, todos void y dependientes de libc. Ambos modos incorporan str_len/str_byte sin libc. Freestanding usa traps nativos ante errores, omite main/startup hosted y exporta pub fn por ABI C; hosted conserva pub con nombres internos para evitar interposición de libc. Extern, volatile y casts pointer↔u64 requieren unsafe. Véase `docs/zen/freestanding.md` para tipos, responsabilidad del autor sobre memoria raw y limitaciones.

## Decisiones

- **ADR-001 (histórica)**: Rust + LLVM/inkwell como intención inicial; TASK-201 documentó cambio a Cranelift sin codegen integrado. Sustituida para el backend MVP por ADR-007.
- **ADR-007 (aceptada)**: Rust → C11 → cc para el primer hito.
- **ADR-008 (aceptada)**: mismo backend con perfil freestanding GCC x86_64, ABI C y unsafe; objetos sin libc, red zone, PIC/PIE, stack protector, SIMD o unwind. Enlace del adaptador Linux sin bibliotecas verificado.
- **Target de Ferros**: x86_64, QEMU aislado, salida serie. System V AMD64 para kernel/usuario y helpers; Multiboot1 directo y bootstrap identidad1GiB/stack64KiB. Kernel reemplaza tablas y entra CPL3 con ABI int0x80 (ADR-012).
- **Memoria Zen (hipótesis)**: ownership/regiones/allocators siguen pendientes de prototipos; no implicados en los escalares/literales de este MVP.
- **ADR-009 (aceptada)**: primer boot con Multiboot1 directo QEMU y wrapper ELF32 para payload64; build Python/GCC/binutils. Bootstrap/IO asm original, UART y kernel Zen.
- **Kernel Ferros (propuesta)**: comparar monolítico modular, microkernel e híbrido antes de cerrar diseño de subsistemas. Limine/UEFI/ISO y CMake no se integran todavía.

## Riesgos y próximos pasos

1. Hitos4–7 cerrados: memoria/IRQs, threads, ELF Zen CPL3 con syscalls/faults y VFS/RAMFS con init/shell sobre int0x80. Próximohito a decidir: VFS ampliado (varios archivos, unlink, permisos) o persistencia mínima; no introducir simultáneamente disco, SMP y rediseño de backend.
2. Mantener semántica independiente de las opciones del compilador C. No generalizar estas pruebas a otras plataformas sin validación.
3. Ampliar gramática y tipos incrementalmente con pruebas; AST/parser históricos requieren reconciliación antes de reutilizarse.
4. TASK-922 inicializó Git local con el corte `e7737a6` y permite worktrees nuevos; el historial anterior no se recuperó y no hay remoto configurado. Los informes previos que afirman ausencia de Git describen sus cortes históricos.
5. QEMU11.1.3 disponible en .tools/qemu con versiones/URL/SHA256 fijados. No hay /dev/kvm; TCG verificado. No se demuestra hardware físico, UEFI/ISO ni KVM.
6. Memoria máxima y rendimiento competitivo no han sido caracterizados; desde TASK-801 existe una línea base reproducible de cuatro cargas (CPU-time, checksum verificado, tres suites con rangos) para detectar regresiones, no un ranking de lenguajes. Sin `perf` no hay ciclos/instrucciones/caché. El pool RAMFS añade1MiB de BSS supervisora que el PMM reserva vía `ferros_kernel_end`.
7. Punteros raw no garantizan seguridad de memoria; volatile no es atomicidad ni sincronización. Structs y arrays fijos existen (ADR-016/017) con límites declarados; no hay layout empaquetado, inline asm del lenguaje ni paso de structs entre funciones.

## Benchmarks — Hito8

`benchmarks/` contiene cuatro cargas (`arith`, `collatz`, `mem`, `sort`) implementadas con el mismo algoritmo y datos en Zen, C, C++ y Rust. El arnés compila, verifica checksums idénticos y solo entonces mide; métrica primaria: tiempo de CPU del hijo (`getrusage`), ejecuciones intercaladas y afinidad de CPU, con wall time como referencia. Resultados versionados en `benchmarks/results/` y resumen en `docs/benchmarks/results.md` (ADR-013). Línea base (3 suites): paridad aproximada Zen/C/C++ dentro de la variabilidad del host (Zen/C 0,9385–1,0408); una ejecución adicional puede salir de ese rango. Rust es más lento en collatz (+8,5…12,1 %) y sort (+39…43 %) con este rustc. No se declara superioridad: Zen comparte backend C11 con C y las diferencias de pocos puntos no se consideran señal. Zig y clang no están disponibles; sin `perf` no hay ciclos/instrucciones/caché. La recursión se excluyó de la comparación principal por una hipótesis no verificada sobre heurísticas de inlining no controlables desde Zen (sin artefactos conservados).

## Autohosting y madurez — Hitos 9 y 10

`zen/selfhost/` contiene once componentes reales escritos en Zen y compilados por `zen`: un lexer contador freestanding (`lexer.zen`, paridad de 8 contadores con el lexer Rust en 5 fixtures y 55 ficheros), un parser/evaluador de expresiones (`parser.zen`, 95 comparaciones contra referencia Python) y un AST real sobre arrays paralelos (`ast_parser.zen`, 14 tests) un lexer con tokens materializados (`lexer_tokens.zen`, 11 tests) un intérprete de sentencias (`interp.zen`, 16 tests) un intérprete con funciones/recursión (`interp_functions.zen`, 22 tests) un typechecker u64/bool (`typecheck.zen`, 16 tests), un codegen C (`codegen.zen`, 16 tests), un codegen con funciones (`codegen_functions.zen`, 18 tests), un codegen con arrays (`codegen_arrays.zen`, 20 tests) y un codegen con structs (`codegen_structs.zen`, 19 tests). Se enlazan con drivers C y no importan libc (`nm -u` vacío). No es un compilador completo: faltan spans, tabla de símbolos con structs, stdlib completa y el backend del compilador Rust en Zen; los cuatro codegens C selfhost existen (ADR-023) y cubren sentencias, funciones, arrays y structs locales, no el compilador Rust completo (ADR-014/016). Hito 10 se documenta en `docs/quality.md` con niveles de madurez, límites explícitos y la puerta única `infrastructure/scripts/verify_all.py` (compilador, Ferros, benchmarks, QEMU, selfhost y reproducibilidad; ~49 s en este host). Nada se declara Estable ni Optimizado.

## Shell interactivo — TASK-703

COM1 RX se expone con `serial_try_read()` (LSR bit0, RBR) y la syscall 8: `0..255` o `0xFFFFFFFF` sin bloqueo. El ELF de usuario ejecuta, tras las comprobaciones del Hito 7, una sesión `SHELL: READY … SHELL: DONE` con prompt, eco, `help`, `ls`, `cat <archivo>` sobre VFS y `exit`; deadline de inactividad (~100 ticks) rearmado con cada byte. El runner inyecta `ls\ncat hello.zen\nhelp\nexit\n` **después** de ver `SHELL: READY` (el FIFO se limpia en `serial_init`) y exige transcripción exacta y `writes=18`; sin entrada el guest imprime `SHELL: NO INPUT`/`SHELL: DONE` en ~1 s y termina en estado 33 sin panic en debug y release; la entrada humana a 150 ms/tecla está verificada. Límites: sin edición de línea, historial, tuberías, IRQ serie ni teclado PS/2; un único ELF convive con las pruebas de aislamiento. Guía `docs/ferros/shell.md`, evidencia TASK-703.

## Kernel actual y composición

Unidades Zen explícitas: ABI, drivers/serial, drivers/ata, memory, interrupts, scheduler, vfs, userspace, storage, storage_fs, runtime y main. `build_ferros.py` concatena esas doce fuentes en build/kernel.zen; no representa módulos ni globals del lenguaje. Estado mutable en BSS reservado y offsets revisados. Algoritmos PMM/VMM/arena, gatesIDT/dispatch/PIC/PIT, loader y syscalls siguen en Zen; asm ofrece entrada/CPUregistros/IO y stubs de interrupción. No hay códigoC de kernel escrito a mano: solo C generado del compilador y mocks externos de tests.

PMM lee Multiboot1 con hasta256registros, disponible/reservado por bitmap y tope64MiB; descarta low1MiB/kernel y reserva hasta el mayor extremo de datos admitidos. Info/mapa bajo1MiB; strings pueden estar más altas con NUL/límites y sus páginas quedan reservadas. Sin módulos/payloads no admitidos; asignación no borra memoria y no es concurrente. Heap es arena64KiB, sin free individual.

El bootstrap establece identidad1GiB/RWX antes del kernel. Zen la reemplaza por páginas4KiB/64MiB con nullguard, textoRX, rodataR+NX y datos/stackRW+NX, supervisor y WP/NXE. Sin higher-half, map/unmap general ni CR3 porproceso. Hito6 añade una rama usuario a1GiB con hojas desde PMM; ejecutar su stackNX produce PF real. Nullread y ROwrite supervisor tienen recuperación one-shot verificada por RIP/CR2/error.

IDT256, stubs0..47/128 y default255,15GPR y llamadaABI alineada, sinSSE/IST/swapgs. Solo puerta128 DPL3, TSS64/RSP0 dedicado y frame de usuario validado. Int3 esperado y3IRQ0PIT reales (~100Hz), EOI master. Inesperados del sistema y faults originados en kernel causan panic35; excepciones síncronas de usuario terminan su invocación. Sin stackoverflow/doublefault robusto niIRQanidado/SMP. Consulta ADR-010/012 y docs/ferros/userspace.md.

## Threads actuales — Hito5

scheduler.zen implementa round-robin, estados y prueba de3workers; context.S únicamente switches/getters/IF/probe CPU. Cada worker tiene32KiB y guard4KiB; controlador0 queda bloqueado hasta3EXITED. Todos los cambios de scheduler son IFoff y el EOI precede al hook PIT. Switch salva6GPRABI/RSP; en preemption el marco15GPR/IRET permanece en el stack del dueño. Al salir el último thread se reanuda la llamada del controlador.

Worker1 espera ocupado sin yield/HLT hasta progreso ajeno; una mutación sin preemption agota timeout. Se verifican8rondas/hash/probes porworker,3exits,16yields y al menos2preemptions reales. El runner extrae números de los logs; muestra observada45switches/25preemptions/16yields/3completed. Casos guardwrite desde stack sano, estado inválido y retorno real del trampoline fallan35 con motivo específico. No se afirma recuperación robusta de overflow sin IST.

Init one-shot, sin rollback parcial de guardas; threads estáticos y mismoaddressspace, sinFPU/SIMD, usuarios, SMP, prioridades, bloqueo de recursos ni reutilización de stacks. Guía docs/ferros/multitasking.md, ADR-011, pruebas/evidencia TASK-610 y revisión TASK-611. El compilador sigue sin módulos/globals; los structs escalares locales existen (ADR-017) y las unidades se concatenan explícitamente.

## Usuario actual — Hito6

Un ELF64 estático separado de Zen se incorpora como rodata y se valida antes de asignar páginas PMM. Ventana0x40000000..0x40200000, imagen debajo0x40100000, stack16KiB al final con guard ausente. PDPT[0] y hojas de identidad son supervisor; PDPT[1] usa PD/PT propios con U. LOADs no solapados RX/R-NX/RW-NX, BSS y stack cero, retirada/invlpg/free al salir y rollback si falla una asignación.

GDT kernel8/16, SSusuario1b, CSusuario23, TSS28/RSP0 con stack supervisor32KiB y puertos denegados. IRETQ limpia GPR y fija flags0x202. int0x80 comparte wrapper de15GPR y devuelve RAX; write1 valida entero el rango≤4096, exit2 vuelve al controlador y ticks3 lee IRQ0 real. No se implementa todavía la instrucción SYSCALL. Solo hay una invocación activa, después de terminar los threads kernel.

## Sistema de archivos y shell — Hito7

RAMFS: pool supervisor de1MiB enBSS,256bloques de4KiB, bitmap,128inodos de64B, directorio raíz real y dos fixtures (`hello.zen`=`Hello`, `notes.txt`=`Zen\n`). VFS: `vfs_init`, `vfs_open/read/write/close` y `vfs_self_test`, con errores ENOENT−2, EBADF−9, EISDIR−21, EMFILE−24 y ENOSPC−28; descriptores en ranuras reutilizables100..115 y ruta copiada a un scratch supervisor de512B. `vfs_init` se ejecuta tras el heap y antes de entrar enCPL3; `vfs_self_test` se ejecuta tras la suite de usuario.

Syscalls int0x80 añadidas sin tocar1–3: open4, read5, write6, close7, read_char8 y readdir9, con validación completa del buffer de usuario antes de cualquier copia. El flujo init/shell se ejecuta en la trayectoria válida del único ELF usuario: el bloque VFS del Hito7 más la sesión interactiva del TASK-703; `ls` enumera por syscall 9 (`hello.zen`, `notes.txt`, `boot.txt` desde ZENFS01 read-only) y `writes` total es 18. Guía `docs/ferros/filesystem.md`, evidencia TASK-701/919. Límites: sin directorios dinámicos, unlink, permisos por usuario, caché, escritura persistente ni montaje real; escrito deCPL3 no ejercitado en la aceptación.

El programa verifica CPL/flags/GPR/BSS/salida/rechazos/ENOSYS/ticks y después abre y lee `hello.zen`/`notes.txt` por VFS y enumera el directorio por readdir. Seis recargas intentan accesos/operaciones prohibidas; el kernel verifica faults y PMM restaurado y ejecuta `vfs_self_test`. 163 tests del compilador y 44 de Ferros pasan, incluyendo mocks Zen normal/O2/UBSan y QEMU real; los 6 arranques de aceptación (debug+release×3) terminan en estado33 con `HITO 7 OK`. Sin escritura persistente/journaling/IPC ni procesos concurrentes/cuotaCPU/TLS/ASLR/KPTI/estadoSIMD aislado/IST; shell interactivo verificado en TASK-703. Alcance y evidencia ADR-012, TASK-710/TASK-711, TASK-701 y TASK-703; siguiente hito: FS persistente real o VFS ampliado, a decidir en el roadmap.
