# TASK-703: Shell interactivo en Ferros (entrada serie COM1)

**Agente**: 10/12/13 (drivers / userspace / QA)
**Estado**: COMPLETADA
**Prioridad**: ALTA
**Dependencias**: [TASK-701 (VFS/RAMFS), TASK-710/711 (CPL3/syscalls)]
**Archivos**: `ferros/kernel/drivers/serial.zen`, `ferros/kernel/arch/x86_64/abi.zen`, `ferros/kernel/userspace.zen`, `ferros/user/main.zen`, `infrastructure/scripts/boot_ferros.py`, `ferros/tests/*.py`, `docs/ferros/shell.md`

## Objetivo
Completar la Fase 7 con un shell mínimo **interactivo**: el usuario escribe comandos por el puerto serie (COM1 RX), el kernel los entrega por syscall, el programa de usuario ejecuta `ls`, `cat <archivo>`, `help` y `exit` sobre el VFS, y la sesión queda registrada en la serie de QEMU de forma verificable.

## Criterios de aceptación
- [x] Driver serie: `serial_try_read()->i64` no bloqueante (LSR bit0, RBR), sin tocar la configuración de TX ni el loopback de init.
- [x] Syscall 8 `read_char`: devuelve 0..255 si hay byte, `0xFFFFFFFF` si no hay datos; sin bloquear el kernel; validada en dispatcher y documentada en el ABI.
- [x] Shell en el ELF de usuario: prompt `SHELL> `, bucle con deadline de inactividad (~100 ticks) que lee una línea, ejecuta comandos y termina con `exit`.
- [x] Comandos: `help`, `ls` (lista el nombre del VFS), `cat <archivo>` (contenido por VFS), `exit`; entrada inválida imprime error claro y no panica.
- [x] QEMU: el runner alimenta stdin con un guion (`ls\ncat hello.zen\nexit\n`); la serie esperada incluye el transcript exacto; estado 33.
- [x] Sin entrada (stdin vacío) el shell agota su límite y sale limpiamente: la aceptación de Hito 7 no se rompe; estado 33 y serie previsible.
- [x] Tests: runner/shell host (11), integración QEMU con guion, y tests de guest sin entrada y con comandos inválidos (UNKNOWN/FILE ERROR) sin panic.
- [x] Regresiones completas: compilador 46, Ferros ≥20, 6 arranques `--all --repeat 3`.
- [x] Documentación `docs/ferros/shell.md`, ABI actualizada y evidencia TASK-703.

## Diseño propuesto
1. **Kernel**: `serial_try_read` en `drivers/serial.zen` (poll LSR bit0; leer RBR). Exponer `ferros_in8` ya existe. Syscalls 8 en `userspace.zen`.
2. **Usuario**: `ferros/user/main.zen`, tras las comprobaciones del Hito 7, ejecuta `shell_session()`: imprime prompt, lee bytes hasta `\n` (máx. 64), separa comando/argumento, reutiliza `user_syscall` 4/5/7 para VFS. Sin teclado PS/2 ni edición de línea en esta tarea.
3. **QA**: `boot()` acepta `input: bytes|None`; el runner usa hilos lectores y escribe la entrada **sólo tras ver `SHELL: READY`** (el FIFO se limpia en `serial_init`). Guion por defecto en la aceptación; los negativos que panican antes del shell no dependen de la entrada.
4. **Serie esperada**: mantener los marcadores actuales y añadir un bloque delimitado:
   ```text
   SHELL: READY
   SHELL> ls
   hello.zen
   SHELL> cat hello.zen
   Hello
   SHELL> help
   commands: help ls cat exit
   SHELL> exit
   SHELL: DONE
   ```
   El runner normaliza la entrada y compara de forma exacta.

## Resultado
Implementación paralela 703A/703B/703C integrada por el Lead. Syscall 8, shell y runner verificados: Ferros 32 tests, QEMU 6/6 estado 33 con transcripción exacta, `writes=18`; sin entrada termina con estado 33 sin panic (NO INPUT/DONE). Evidencia: `agents/reports/TASK-703.md`.

## Riesgos
- El bucle de lectura debe tener cota dura para no colgar QEMU sin entrada (timeout del runner como red de seguridad).
- No hay IRQ serie: polling con `IF` activo; mantener llamadas cortas y sin bloquear el scheduler.
- El ELF es único: el shell convive con las pruebas de aislamiento del Hito 6; no debe alterar sus contadores (`writes`, `rejected`, `runs`).
- Cambiar la serie esperada afecta a tests negativos: revisar todas las aserciones de marcadores.
