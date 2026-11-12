# TASK-215 — Evidencia: RAMFS multifichero, readdir y `ls` real

Fecha: 2026-11-11.

## Entregado
| Archivo | Cambio |
|---|---|
| `ferros/kernel/vfs.zen` | Layout con bloque de directorio, entradas de 32 B, dos fixtures (`hello.zen`, `notes.txt`), lookup por tabla, `vfs_readdir`, self-test ampliado, `free_blocks=250` |
| `ferros/kernel/userspace.zen` | Syscall 9 `readdir` con validación de destino escribible y `count≤4096` |
| `ferros/user/main.zen` | `ls` por syscall 9 (una escritura, NUL→`\n`); `cat` no duplica newline final |

## Verificación
- Builds debug/release de kernel y usuario: OK.
- QEMU manual release con `ls\ncat hello.zen\ncat notes.txt\nexit\n`: **status 33**, sin PANIC, `runs=7 writes=18 rejected=6`; `ls` muestra `hello.zen` y `notes.txt`; `cat notes.txt` = `Zen`.
- Integración Lead: runner/tests actualizados; **Ferros 34 tests OK**; aceptación QEMU release con guion por defecto PASS (transcripción con `notes.txt`).
- Host: `vfs_test_api.zen` ampliado con notes/readdir y layout de 0..5; `test_vfs` verde debug/release.

## Límites
- Sin subdirectorios, creación, borrado (`unlink`), `stat`, renombrado ni persistencia.
- `readdir` lista solo la raíz y no mantiene posición (no hay `getdents` incremental).
- `read` sigue sin offset por descriptor; `open` ignora flags.
- Un único ELF de usuario y una invocación activa (sin cambios respecto al Hito 7).

## Relevancia
El shell ya enumera el VFS real y el kernel prueba un directorio con dos entradas, base para un `ls`/navegación más completa. Decisión: ADR-018.
