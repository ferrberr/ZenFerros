# Shell interactivo de Ferros — TASK-703 (Fase 7)

Estado: integrado y verificado en QEMU (estado 33). La transcripción real coincide con el contrato; evidencia en `agents/reports/TASK-703.md`.

## Camino de entrada

```text
QEMU stdio (stdin) → UART 16550 COM1 RX → serial_try_read() [Zen, polling LSR bit0]
→ syscall 8 (int0x80) → shell del ELF de usuario → comandos VFS (4/5/7) → COM1 TX
```

- No hay IRQ serie ni teclado PS/2: el shell sondea con un límite duro.
- El runner inyecta el guion **después** de ver `SHELL: READY`, porque `serial_init` limpia los FIFO del UART.

## Syscall 8 — read_char

| Syscall | RAX | RDI/RSI/RDX | Resultado |
|---|---:|---|---|
| read_char | 8 | ignorados | `0..255` si hay byte; `0xFFFFFFFF` si no hay dato |

No bloquea; no altera los contadores de `write` del Hito 6.

## Comandos

| Comando | Efecto |
|---|---|
| `help` | imprime `commands: help ls cat put exit` |
| `ls` | enumera el directorio raíz por syscall 9: RAMFS (`hello.zen`, `notes.txt`) y después ZENFS01 (`boot.txt`) |
| `cat <archivo>` | abre por VFS, lee y escribe el contenido; error → `SHELL: FILE ERROR`. Con TASK-919 admite también archivos persistentes de solo lectura como `cat boot.txt` |
| `exit` | termina la sesión (`SHELL: DONE`) |
| otra cosa | `SHELL: UNKNOWN COMMAND` |

## Guion de aceptación

Entrada: `ls\ncat hello.zen\nhelp\nexit\n` (sin cambios desde TASK-703).

Salida añadida (tras el bloque VFS del Hito 7):

```text
SHELL: READY
SHELL> ls
hello.zen
notes.txt
boot.txt
SHELL> cat hello.zen
Hello
SHELL> help
commands: help ls cat put exit
SHELL> exit
SHELL: DONE
```

TASK-919 solo amplía la salida de `ls` con `boot.txt`: no añade comandos,
syscalls ni escrituras. `cat boot.txt` funciona por el mismo camino
`open`/`read`/`close` y se ejercita con entrada propia en
`ferros/tests/test_pfs_vfs.py` (dos arranques con el mismo disco: `boot=1` y
`boot=2`).

Contadores esperados: `runs=7 writes=18 rejected=6 irqs>=1`. Sin entrada, el shell espera ~1 s de inactividad (deadline de 100 ticks, rearmado con cada byte), imprime `SHELL: NO INPUT` y `SHELL: DONE`, y el guest termina en estado 33 sin panic tanto en debug como en release. La entrada humana a 150 ms/tecla está verificada.

## Reproducir

```bash
CARGO_HOME="$PWD/.cargo" cargo build --release --offline --manifest-path zen/compiler/Cargo.toml
python3 infrastructure/scripts/build_ferros.py --release
python3 infrastructure/scripts/boot_ferros.py --all --repeat 3
```

## Límites

- Sin edición de línea (backspace), historial, tuberías ni redirecciones.
- Sin IRQ serie ni entrada concurrente; lectura por polling con deadline de inactividad.
- Un único ELF de usuario; el shell convive con las pruebas de aislamiento del Hito 6.
- `cat` de un archivo ZENFS01 es de solo lectura; cualquier intento de escritura
  del shell o de la syscall 6 devuelve EROFS (−30).
- La salida se delimita con `SHELL: READY`/`SHELL: DONE` para que el runner no dependa de temporización.
