# TASK-703B: shell interactivo en el ELF de usuario

**Agente**: 12 (userspace)
**Estado**: COMPLETADA
**Resultado**: shell con READY/prompt/eco/ls/cat/help/exit/UNKNOWN/NO INPUT; ELF construye (13 600 B, `nm -u` vacío). Harness con mocks: guion congelado → writes=18 y transcripción exacta; sin entrada → writes=9.
**Dependencias**: TASK-701, contrato syscall 8 (TASK-703A)
**Archivos (propiedad exclusiva)**: `ferros/user/main.zen`

## Objetivo
Añadir una sesión de shell interactiva al programa de usuario que use la syscall 8 para leer de COM1 y el VFS para `ls`/`cat`.

## Contrato congelado
- Syscall 8: `user_syscall(8,0,0,0)` → byte 0..255 o `0xFFFFFFFF` si no hay dato.
- Tras la comprobación de ticks de `case 0`, ejecutar `shell_session()` y luego `return 0`:
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
- Por cada línea: escribir `SHELL> `, leer hasta `\n` (máx 64) con sondeos acotados (p.ej. 2.000.000); al recibir la línea, **eco** de la línea + `\n` y ejecutar.
- `ls`: escribir `hello.zen\n`. `cat <f>`: abrir por VFS (syscall 4), leer hasta 256 (syscall 5), escribir bytes, cerrar (7); si falla, `SHELL: FILE ERROR\n`. `help`: `commands: help ls cat exit\n`. `exit`: terminar sesión. Desconocido: `SHELL: UNKNOWN COMMAND\n`. Línea vacía: repetir prompt.
- Si se agota el límite sin datos: escribir `SHELL: NO INPUT\n` y `SHELL: DONE\n`, salir de la sesión.
- No alterar el bloque VFS del Hito 7 ni los códigos de error 15–24 existentes; el shell va después.
- Escrituras esperadas: 5 (bloque VFS) + 13 (shell: 4 prompts + 4 ecos + 3 salidas + READY + DONE = 18 totales).

## Aceptación
- `python3 infrastructure/scripts/build_user.py --release --source ferros/user/main.zen --output /tmp/task703b` genera ELF válido.
- No tocar kernel, runner, tests ni docs.
- Reportar diff, comandos, y confirmación del conteo de escrituras.
