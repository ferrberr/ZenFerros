# TASK-215: RAMFS multifichero + readdir + shell ls real (Fase 7 ampliada)

**Agente**: 11/12
**Estado**: COMPLETADA
**Resultado**: dos fixtures, directorio raíz real, syscall 9 readdir y `ls` dinámico; QEMU status 33, Ferros 34 tests; integración de runner/tests por el Lead.
**Dependencias**: TASK-701, TASK-703
**Archivos (propiedad exclusiva)**: `ferros/kernel/vfs.zen`, `ferros/kernel/userspace.zen`, `ferros/user/main.zen`

## Objetivo
Ampliar el VFS a varios archivos con un directorio real y un `ls` dinámico en el shell, sin romper los hitos 1–8.

## Contrato
- RAMFS con dos fixtures: `hello.zen` = `Hello` (5 B) y `notes.txt` = `Zen\n` (4 B), más directorio raíz con entradas reales.
- Bloque 0 bitmap; bloques 1–2 inodos (128×64 B); bloque 3 directorio raíz con entradas de 32 B (`name[24]` con NUL, `u64 inode_index` en +24, fin en nombre vacío); bloques 4 y 5 datos de los fixtures. `free_blocks` coherente (250).
- `ramfs_lookup` recorre entradas del directorio y compara nombre NUL; soporta `hello.zen` y `notes.txt`.
- Syscall 9 `readdir`: RAX=9, RDI=buffer usuario, RSI=count (≤4096); valida buffer escribible con `user_buffer_writable`; escribe nombres separados por NUL (`hello.zen\0notes.txt\0`) y devuelve bytes escritos o error negativo.
- Shell: `ls` usa syscall 9 y escribe el buffer recibido (ya incluye saltos? no: añade `\n` tras cada nombre o escribe NUL como salto); el resto de comandos y el bloque VFS del Hito 7 no cambian.
- `vfs_self_test` comprueba: hello (open/read/close), notes (open/read), ENOENT de ruta desconocida, readdir con ambos nombres, EISDIR en raíz, EMFILE/reuse y ENOSPC siguen.
- No cambies syscalls 1–8 ni los contadores del Hito 6; `writes` del shell debe seguir siendo 18 con el guion congelado.

## Aceptación
- `python3 infrastructure/scripts/build_ferros.py --release` y build debug compilan.
- `python3 infrastructure/scripts/build_user.py --release` compila.
- Verifica en QEMU manualmente con entrada `ls\ncat hello.zen\ncat notes.txt\nexit\n` (puedes usar `boot_ferros.boot` con input personalizado; la serie esperada del runner aún no está actualizada): estado 33, sin PANIC, `ls` muestra ambos nombres, `cat notes.txt` muestra `Zen`.
- No toques runner/tests/docs (los actualiza el Lead).
