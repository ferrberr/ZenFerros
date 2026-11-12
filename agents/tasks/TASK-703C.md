# TASK-703C: inyección de entrada serie en QEMU y aceptación

**Agente**: 13 (QA)
**Estado**: COMPLETADA
**Resultado**: `run_process/boot` con inyección tras READY, timeout/cancelación conservados, serie esperada con shell y `writes=18`; 11 tests de runner y 11 de shell; 6/6 QEMU estado 33.
**Dependencias**: contrato TASK-703 (syscall 8 + transcripción)
**Archivos (propiedad exclusiva)**: `infrastructure/scripts/boot_ferros.py`, `ferros/tests/test_boot.py`, `ferros/tests/test_shell.py` (nuevo)

## Objetivo
Permitir que el runner inyecte un guion por stdin de QEMU **después** de ver `SHELL: READY` (el FIFO se limpia en `serial_init`) y actualizar la aceptación a la transcripción del contrato.

## Contrato
- `run_process(..., input: bytes|None)` y `boot(..., input=b"ls\ncat hello.zen\nhelp\nexit\n")`.
- Con `input`: `Popen(stdin=PIPE, stdout=PIPE, stderr=PIPE, start_new_session=True)`; hilos lectores de stdout/stderr; cuando stdout acumulado contiene `SHELL: READY`, escribir toda la entrada, cerrar stdin, y seguir capturando. Timeout/cancelación deben seguir guardando logs y matando el grupo.
- Serie esperada: la actual + bloque del contrato; contadores userspace `runs=7 writes=18 rejected=6 irqs>=1`.
- Actualizar aserciones de test_boot y añadir `ferros/tests/test_shell.py` para: validación con serie sintética, guion por defecto presente, y que el escritor no inyecta antes del marcador (test de la lógica con un proceso falso, sin QEMU).
- No editar kernel ni `ferros/user/main.zen`.

## Aceptación
- `python3 -m unittest test_boot -v` (desde `ferros/tests`) pasa usando serie sintética; los tests que arrancan QEMU pueden fallar hasta integrar 703A/703B: documentarlo y no relajar aserciones.
- No modificar `EXPECTED_MESSAGES` a la baja ni suprimir tests.
- Reportar diff, comandos y resultados.
