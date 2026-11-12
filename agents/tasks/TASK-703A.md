# TASK-703A: driver serie RX + syscall read_char

**Agente**: 10 (drivers) / 09
**Estado**: COMPLETADA
**Resultado**: `serial_try_read` + syscall 8 implementadas; kernel build GREEN en `/tmp/task703a`. Stub host `serial_try_read` añadido por el Lead en `ferros/tests/fixtures/user_test_api.zen`; `test_elf_rollback` pasa.
**Dependencias**: TASK-701, TASK-710/711
**Archivos (propiedad exclusiva)**: `ferros/kernel/drivers/serial.zen`, `ferros/kernel/userspace.zen`

## Objetivo
Exponer lectura no bloqueante del puerto serie COM1 al espacio de usuario mediante la syscall 8, sin alterar TX ni la inicialización existente.

## Contrato
- `serial_try_read()->i64` en `drivers/serial.zen`: si `in8(0x3FD) & 1 != 0` devolver `in8(0x3F8) as i64`; si no, `-1`. No bloquear, no tocar `serial_init`/`serial_byte`.
- `user_read_char()->u64` en `userspace.zen`: `-1` → `0xFFFFFFFF`; si no, el byte.
- Dispatcher `number==8` → `result=user_read_char()`; conservar 1–7 intactas.
- Documentar el número 8 en el comentario de cabecera del dispatcher (no editar docs).

## Aceptación
- `python3 infrastructure/scripts/build_ferros.py --release --output /tmp/task703a` compila.
- No tocar `ferros/user/main.zen`, runner, tests ni docs.
- Reportar diff resumido, comandos y salida.
