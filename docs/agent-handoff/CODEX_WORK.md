> **Documento histórico de la transferencia Codex→DSH (2026-11-11).** No describe el estado actual; el estado vigente está en `agents/STATE.md`, `ROADMAP.md`, `ARCHITECTURE.md` y `docs/quality.md`.

# Trabajo realizado durante Codex

Transferencia a DSH — 2026-11-11. Síntesis de conversación accesible, fuentes actuales e informes persistidos. No es un diff Git certificado de toda la etapa.

## Evolución por hitos

| Hito | Resultado incorporado | Evidencia y revisión |
|---|---|---|
| 1 | Compilador nativo Zen: lexer, parser/checker activo, generación C11, enlace y CLI build/run/check; ejecutables reales | TASK-210/211 y endurecimiento lexer TASK-212 |
| 2 | Freestanding x86_64 sin libc, ABI C, exports, unsafe/raw/volatile, bits/casts y semántica comprobada | TASK-310/311, ADR-008 |
| 3 | Bootstrap Multiboot32→64, kernel Zen, COM1, build ELF64/contenedor ELF32, runner QEMU real | TASK-410/411, ADR-009 |
| 4 | Mapa físico real/reservas, PMM, VMM4KiB protegido, heap, IDT/excepciones y PIT | TASK-510/511, ADR-010 |
| 5 | Tres threads kernel con stack/guard, contexto, round-robin preemptivo, yield/exit y retorno a controlador | TASK-610/611, ADR-011 |
| 6 | ELF Zen usuario separado, loader validado/rollback, CPL3/TSS, permisos U/S/W^X y write/exit/ticks; faults contenidos | TASK-710/711, ADR-012 |

Se continuó desde trabajo previo de DSH; no se atribuye a Codex toda la estructura o cada línea preexistente. Sin historial comparativo completo no se puede cuantificar un delta total fiable.

## Decisiones y motivos

- **ADR-007:** bootstrap Rust→C11→cc para disponer de compilación ejecutable y verificable; sustituye intención LLVM/inkwell y prototipos Cranelift sin backend operativo. No reactivar esos backends suponiendo que ya funcionan.
- **ADR-008:** perfil freestanding del mismo frontend, sin runtime hosted; primitivas ABI externa para CPU y memoria raw en vez de fingir inline ASM/structs todavía inexistentes.
- **ADR-009:** Multiboot1 directo en QEMU con wrapper ELF32 para payload64. Soluciona la carga del kernel64 sin incorporar ISO/GRUB/Limine/UEFI en este mínimo. Build verifica header/layout/símbolos y preservación de bytes text/rodata.
- **ADR-010:** memoria inicial acotada64MiB, páginas4KiB, heap arena y PIC/PIT legacy para poder demostrar protección/excepciones reales en una CPU.
- **ADR-011:** threads estáticos, switches ABI IF0 y EOI antes del hook scheduler. Worker1 espera progreso ajeno sin yield/HLT, para que el test dependa de preemption real.
- **ADR-012:** int0x80 reutiliza wrapper IDT15GPR existente; pospone instrucción SYSCALL/SYSRET/MSR. ELF usuario estático y mapas dedicados en el CR3 existente; una invocación activa, sin afirmar procesos concurrentes.

## Problemas encontrados y soluciones

| Problema documentado | Solución/verificación |
|---|---|
| Borradores históricos no equivalían a compilador funcional | Pipeline MVP activo en mvp.rs/native.rs, validación CLI y documentación de límites |
| `.git` principal vacío/protegido | Snapshots Git temporales, archivos exclusivos y copia secuencial revisada; sin fingir merges |
| QEMU local y dependencias ausentes al inicio | Paquetes locales fijados/hash, script setup y entorno LD_LIBRARY_PATH/QEMU_MODULE_DIR/firmware |
| Metadata Multiboot de QEMU situada tras kernel/BSS | Reservar hasta extremos reales de strings admitidos, con NUL y límites; evita PMM pisar metadata |
| `-no-shutdown` retenía guest tras debug-exit en QEMU11 | Retirada en runner; estado33/35 y logs/timeout/cancelación comprobados |
| Scheduler provisional podía aparentar preemption solo en probes | Worker ocupado IFon dependiente de otros; mutante sin hook no termina y agota timeout |
| Límites de uso de agentes y desaparición de /tmp | Recuperación desde workspace/informes, snapshots nuevos y tareas acotadas; BLOCKED-610 quedó resuelto |
| Entrada ASM usuario desalineaba llamada Zen | `_user_start` alinea RSP antes de call; revisión independiente |
| Dispatcher atribuía cualquier evento con CPL3 a usuario | Clasificación explícita: síncronos admitidos frente a NMI/DF/MC/IRQ; PF_RSVD/sinU fatales |
| Error esperado para int0x81 confundía tamaño de gate e índice | GP esperado0x40a=(129<<3)|2; probado en QEMU |
| UBSan en fixture C de trap | Indexar array completo por slot RAX; no desactivar sanitizador; cuatro combinaciones pasan |

## Funcionalidades pospuestas o redefinidas

LLVM, Cranelift, ownership/lifetimes, gramática completa, structs/arrays/floats/módulos, inlineASM Zen, stdlib general y self-hosting siguen pendientes. La composición por concatenación no constituye soporte de módulos. Kernel no implementa aún SMP, procesos concurrentes, IPC, VFS/RAMFS, shell, VirtIO, persistencia, ISO/UEFI o SYSCALL/SYSRET. No se eliminaron esas metas del proyecto: se redujo el alcance de cada hito a un mínimo verificable.

No hay prueba de rendimiento superior a otros lenguajes/sistemas. Tiempos TCG son observaciones, no benchmarks comparativos. Tampoco se declara seguridad de binarios arbitrarios con SIMD/cuotas ni recuperación robusta de stack overflow.

## Referencias para navegar

- Frontend/backend: `zen/compiler/src/{lexer/,mvp.rs,native.rs,main.rs}`; tests unitarios y `tests/{native_cli,freestanding_cli}.rs`.
- Núcleo: `ferros/boot/`, `ferros/kernel/{memory,interrupts,scheduler,userspace}.zen`, `arch/x86_64/{io,interrupts,context,userspace}.S`.
- Usuario/build: `ferros/user/{main.zen,entry.S,linker.ld}`, `infrastructure/scripts/{build_user,build_ferros,boot_ferros}.py`.
- Evidencia final: `agents/reports/TASK-710.md`, `TASK-711.md`, `TASK-711-kernel.md`, `TASK-711-user.md`; carpetas TASK-710/ y TASK-711/ con JSON/logs/hash.

## Historial y commits: limitación expresa

En esta transferencia `git status --short` y `git log -6 --oneline` fallan: «not a git repository». `.git/` existe, vacío y de solo lectura. No hay HEAD, ramas, remoto ni historial principal consultable. No se ha restaurado ni alterado Git.

Los informes anteriores registran commits temporales: Hito5 scheduler `b68953d`, contexto `13e611d`; Hito6 ASM `96a9135`, user/build `f491a49`. Son **referencias documentales**, no commits verificados ahora en este checkout ni hashes de su estado completo. Las consultas actuales a los repositorios /tmp citados no recuperan logs. No dependa de /tmp para retomar: use fuentes y evidencia persistente. La conversación accesible está parcialmente resumida; no hay acceso completo a sesiones originales de DSH ni a todas las acciones/turnos de Codex. No inventar autoría por línea, fechas de commits, merges o cifras de líneas añadidas.
