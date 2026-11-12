# TASK-701: VFS/RAMFS e init/shell Zen mínimos (Hito 7)

**Agente**: 00 (integración/reparación) con contribución previa de 11/12
**Estado**: COMPLETADA (revisión independiente final APROBADA)
**Prioridad**: ALTA
**Dependencias**: [TASK-710, TASK-711]
**Archivos**: `ferros/kernel/vfs.zen` (nuevo), `ferros/kernel/main.zen`, `ferros/kernel/userspace.zen`, `ferros/kernel/arch/x86_64/abi.zen`, `ferros/kernel/arch/x86_64/userspace.S`, `ferros/user/main.zen`, `ferros/tests/{test_boot,test_userspace,test_scheduler,test_interrupts}.py`, `ferros/tests/fixtures/user_mock.c`, `infrastructure/scripts/{build_ferros,boot_ferros}.py`, `zen/compiler/tests/freestanding_cli.rs`

## Objetivo
Añadir a Ferros un sistema de archivos en memoria (RAMFS) con una capa VFS acotada, expuesto al espacio de usuario mediante syscalls int0x80, y demostrar `ls`/`cat` desde CPL3 sobre un archivo conocido, sin romper las regresiones de los hitos 1–6.

## Criterios de aceptación (verificados)
- [x] RAMFS de 1 MiB: 256 bloques de 4 KiB, bitmap de bloques e inodos de 64 bytes.
- [x] VFS acotado: `open`, `read`, `write`, `close` con errores ENOENT(-2), EACCES/EISDIR(-21), EBADF(-9), EMFILE(-24), ENOSPC(-28).
- [x] Syscalls de archivos desde CPL3 por int0x80: números 4=open, 5=read, 6=write, 7=close, con validación previa del buffer de usuario.
- [x] Flujo de init/shell verificado en la imagen de usuario real: `ls` lista `hello.zen`, `cat hello.zen` imprime el contenido leído por VFS.
- [x] Autoprueba del kernel de RAMFS y de open/read/close antes de declarar el hito.
- [x] Aislamiento: `read` solo escribe en buffers de usuario escribibles (PTE&7); `write` desde CPL3 devuelve EACCES por modo; los descriptores se cierran al salir o fallar la tarea (`vfs_close_all`).
- [x] Aceptación QEMU: 6/6 arranques (debug+release ×3) con estado 33 y serie exacta que termina en `HITO 7 OK`.
- [x] Suites completas verdes: compilador 46 tests y Ferros 20 tests (incluye `test_vfs.py` con errores VFS).
- [x] Revisión del diff completo por el Lead; regresiones de hitos 1–6 intactas.

## Alcance finalmente implementado (y desviaciones)
El loader soporta un único ELF estático con una invocación activa. Por eso el flujo init/shell se implementa **dentro de la trayectoria válida (`case 0`) de la imagen de usuario verificada** (`ferros/user/main.zen`), no como procesos separados: tras las comprobaciones de CPL3/syscalls, el programa abre `hello.zen`, lista el directorio, lee el archivo por VFS y lo imprime al puerto serie. Los borradores `ferros/user/init.zen`, `ferros/user/shell.zen` y `ferros/kernel/vfs_ramfs.zen` de la sesión anterior no formaban parte del build ni de la aceptación y se retiraron para no declarar artefactos no verificados.

## Evidencia
- Informe autoritativo: `agents/reports/TASK-701.md` (comandos y salidas reales).
- Serie QEMU release observada:

```text
SCHEDULER: STATS switches=45 preemptions=25 yields=16 completed=3
USER: Hello from Zen
SHELL> ls
hello.zen
SHELL> cat hello.zen
Hello
USERSPACE: RING3 AND SYSCALLS OK
USERSPACE: ISOLATION AND CLEANUP OK
USERSPACE: STATS runs=7 writes=5 rejected=6 irqs=1
FS: RAMFS OK
FS: VFS OPEN/READ/CLOSE OK
Boot successful
HITO 7 OK
```

## Revisión independiente
La primera versión fue rechazada por un revisor distinto (3 vías de panic desde CPL3, fuga de fd, scratch en el pool, cobertura VFS inexistente y contabilidad/bitmap). Correcciones aplicadas: validación de destino escribible en read, `vfs_write_user` con EACCES, `vfs_close_all` en teardown, self-test ampliado (EISDIR/EACCES/EMFILE/ENOSPC/reuse), `free_blocks=252`, bloque lleno → −28, pruebas host `test_vfs.py` y doc del bitmap. Sondas negativas añadidas al propio programa de usuario (−14 en read a texto, −13 en write, fd filtrado). Segunda revisión independiente: **CON OBSERVACIONES**, sin panic reproducido en A1/A2/A3 y con las suites verdes; señaló que el self-test no restauraba el fixture (quedaba `HelloHi`, tamaño 7) y que la sonda de fuga del usuario era inerte. Corregido: instantánea temprana y restauración completa (tamaño 5, contenido `Hello`, bitmap y `free_blocks`), sonda de fuga que re-etiqueta la ruta y valida `100<=fd<=115`, `vfs_write(count=0)` devuelve 0, comentario del bitmap corregido y cobertura host ampliada (`vfs_self_test`, ENOSPC sin bloques, contador de libres, `user_buffer_writable` vía dispatcher). Verificado por mutación que quitar `vfs_close_all`, `user_buffer_writable` o `vfs_write_user` hace fallar el arranque. Re-revisión final independiente: **APROBADO**, sin hallazgos Alta/Media; observaciones menores corregidas. TASK-701 cerrada.

## Riesgos y deuda
- La lectura desde CPL3 está verificada; `write` se ejercita en la autoprueba del kernel (añade `Hi` y relee 7 bytes), no desde CPL3.
- Sin nombres de directorio dinámicos, sin `unlink`, sin permisos por usuario (solo kernel/CPL0 escribe).
- Un directorio con entradas arbitrarias, shell interactivo por teclado y VFS persistente quedan para hitos posteriores.
