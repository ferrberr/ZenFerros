# TASK-703 — Evidencia: shell interactivo COM1 (Fase 7)

Fecha de cierre: 2026-11-11. Ejecutado en este workspace. Trabajo en paralelo: 703A (kernel), 703B (usuario), 703C (QEMU/tests), integración y verificación por el Lead.

## Objetivo
Completar la Fase 7 con un shell interactivo real: entrada por COM1, syscall de lectura, comandos sobre el VFS y sesión verificable en la serie de QEMU.

## Cambios

| Área | Archivo | Cambio |
|---|---|---|
| Driver serie RX | `ferros/kernel/drivers/serial.zen` | `serial_try_read()->i64`: LSR(0x3FD) bit0 → RBR(0x3F8); `-1` sin dato. `serial_init`/TX intactos |
| Syscall | `ferros/kernel/userspace.zen` | `user_read_char()->u64` (`-1`→`0xFFFFFFFF`) y rama `number==8`; comentario del dispatcher actualizado |
| Shell | `ferros/user/main.zen` | `shell_session`, `shell_read_line` (máx 64, 2.000.000 sondeos), `shell_command`, `shell_cat`, comparadores; corre en `case 0` tras las comprobaciones del Hito 7 |
| Runner | `infrastructure/scripts/boot_ferros.py` | Constantes del contrato; inyección de `DEFAULT_INPUT` **tras ver `SHELL: READY`** (el FIFO se limpia en `serial_init`); hilos stdout/stderr; timeout/cancel conservados |
| Aceptación | `ferros/tests/test_boot.py`, `test_shell.py` (nuevo), `test_userspace.py` | Serie y `writes=18`; 11 tests de runner/shell; aserción de usuarios actualizada |
| Tests host | `ferros/tests/fixtures/user_test_api.zen` | Stub `serial_try_read()->-1` para la composición mock |
| Docs | `docs/ferros/shell.md`, `docs/ferros/userspace.md` | Syscall 8, transcripción, guion, límites |

## Contrato verificado

- Syscall 8: `0..255` o `0xFFFFFFFF`, no bloquea.
- Entrada por defecto: `ls\ncat hello.zen\nhelp\nexit\n`.
- Transcripción real (release, QEMU TCG, estado 33, stderr vacío):

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

- Contadores: `runs=7 writes=18 rejected=6 irqs>=1`.
- Sin entrada: el shell agota su presupuesto, imprime `SHELL: NO INPUT` y `SHELL: DONE`, y el guest termina con **estado 33 sin panic** (verificado en QEMU; el runner rechaza esa serie porque no es el guion de aceptación).
- Comandos inválidos en QEMU real (`bogus`, `cat nope.zen`): `SHELL: UNKNOWN COMMAND` y `SHELL: FILE ERROR`, sin panic; el guest termina limpio (la serie no coincide con la de aceptación, como se espera).

Decisión de integración: la comprobación del kernel sobre `writes` se relaja a cota inferior (`>=5`) para no atar el kernel a un guion concreto; el runner exige el valor exacto 18 con el guion por defecto.

## Revisión independiente y correcciones
La revisión dio **CON OBSERVACIONES** (núcleo conforme). Se corrigió:
1. **ALTA — shell inusable a velocidad humana**: el presupuesto de sondeos era acumulado por línea (~1,2 s totales en release). Sustituido por **deadline de inactividad** de 100 ticks rearmado con cada byte; verificado en QEMU release tecleando `cat hello.zen` a 150 ms/tecla: eco + `Hello`, estado 33.
2. **MEDIA — camino sin entrada dependiente de perfil**: ahora termina en ~1,3–1,6 s en debug y release (estado 33, NO INPUT/DONE, sin panic), no ~16 s en debug. Añadidos tests de guest: sin entrada y comandos inválidos.
3. **BAJA/MEDIA — documentación**: corregidos `filesystem.md` (transcripción y `writes=18`), `userspace.md` (alcance del shell), `ARCHITECTURE.md` (tabla y tests), `STATE.md`, guion/`help` y método de inyección en TASK-703, estado de TASK-703C.
4. **BAJA — runner**: `injection_error` se registra en `result.json` si la inyección falla (antes solo se guardaba en estado interno).
5. **BAJA — flake preexistente**: `test_memory` falló una vez de 4 ejecuciones (mmap fijo); no es de TASK-703 y no se enmascara; documentado.

## Comandos y resultados reales

```bash
CARGO_HOME="$PWD/.cargo" cargo build --release --offline --manifest-path zen/compiler/Cargo.toml
python3 infrastructure/scripts/build_ferros.py --release
python3 infrastructure/scripts/boot_ferros.py --all --repeat 3
```
```text
debug boot 1: PASS (QEMU 33, 0.615s)
debug boot 2: PASS (QEMU 33, 0.615s)
debug boot 3: PASS (QEMU 33, 0.615s)
release boot 1: PASS (QEMU 33, 0.365s)
release boot 2: PASS (QEMU 33, 0.365s)
release boot 3: PASS (QEMU 33, 0.365s)
```

```bash
python3 -m unittest discover -s ferros/tests       # Ran 34 tests — OK
cargo test --manifest-path zen/compiler/Cargo.toml # 27+8+11 = 46 — OK
python3 -m unittest discover -s benchmarks/tests   # 6 — OK
```

`test_boot` 13 tests (incluye guest sin entrada y comandos inválidos) y `test_shell` 11 tests (sin QEMU) incluidos en los 34 de Ferros.

## Riesgos y deuda
- La transcripción exacta acopla contrato, shell y runner: cualquier cambio de salida exige actualizar ambos lados.
- Presupuesto de 2.000.000 sondeos por línea: si el runner tardase demasiado tras READY, el shell daría NO INPUT; en QEMU real la inyección es inmediata.
- Sin edición de línea, historial, tuberías ni teclado PS/2; sin IRQ serie (polling).
- Un único ELF: el shell convive con las pruebas de aislamiento; los contadores se ajustaron en consecuencia.
- Sin `.git`: la revisión se apoya en archivos y pruebas, no en diffs de VCS.

## Revisión
Revisión independiente realizada: **CON OBSERVACIONES**, corregidas según lo anterior. Núcleo (driver RX, syscall 8, inyección tras READY, timeout/cancelación, transcripción y contadores) verificado sin hallazgos.
