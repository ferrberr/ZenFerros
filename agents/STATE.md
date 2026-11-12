# STATE.md — resumen operativo (actualizar, no duplicar)

Actualizado: 2026-11-12 (ronda 12, cierre de objetivo) · Hitos 1–8 cerrados; Hito 9 parcial, Hito 10 documentado, Fase 9 parcial.

## Dónde estamos
- **Zen**: compilador Rust→C11 (`zen/compiler`), suite **163 tests** (arrays TASK-213, structs TASK-214, slices TASK-915); benchmarks Hito 8 (6 tests); selfhost **166 tests** (once componentes).
- **Ferros**: kernel Zen + CPL3 + VFS/RAMFS; suite **44 tests**; aceptación 6/6 QEMU estado 33 con shell (`writes=18`).
- **Última**: ronda 11 — TASK-919 PFS visible en VFS/shell (Ferros 44, boot=1/2 por `cat`) y TASK-920 release 0.1.1/madurez; TASK-916/917/918 integradas.
- **Hito 9/10**: frontend/ejecución en Zen con once componentes (incluidos slices y cuatro codegens C); release v0.1.0 documentada (corte 151/39/6/147) y evidencia posterior 163/44/6/166; nada declarado Estable/Optimizado.
- Ronda 11 completa: TASK-919 PFS visible en VFS/shell ✅ (Ferros 44, boot=1/2 por `cat`) y TASK-920 release v0.1.1/madurez ✅ (corte pre-919, 163/43/6/166; 919 posterior).
- **Cierre**: auditoría final en `agents/reports/TASK-921.md`; gate 8/8 en 54,61 s con 163/44/6/166. Objetivo NO declarado completo: brechas CI remoto ejecutado, stdlib amplia, self-hosting completo y escritura persistente.

## Comandos canónicos
```bash
CARGO_HOME="$PWD/.cargo" cargo build --release --offline --manifest-path zen/compiler/Cargo.toml
python3 infrastructure/scripts/build_ferros.py --release
python3 infrastructure/scripts/boot_ferros.py --all --repeat 3
python3 -m unittest discover -s ferros/tests
python3 -m unittest discover -s benchmarks/tests
```

## Contrato TASK-703 (congelado para trabajo paralelo)
- **Syscall 8**: `RAX=8`; devuelve `0..255` (byte COM1) o `0xFFFFFFFF` si no hay dato. No bloquea.
- Driver: `serial_try_read()->i64`: LSR(0x3FD)&1, leer RBR(0x3F8); `-1` sin dato.
- **Guion de entrada por defecto**: `ls\ncat hello.zen\nhelp\nexit\n`.
- **Transcripción exacta** (tras el bloque VFS actual):
```text
SHELL: READY
SHELL> ls
hello.zen
notes.txt
boot.txt
SHELL> cat hello.zen
Hello
SHELL> help
commands: help ls cat exit
SHELL> exit
SHELL: DONE
```
- Eco: el shell imprime `SHELL> `, lee hasta `\n`, y escribe la línea recibida (eco) antes de ejecutar.
- Sin entrada: límite de sondeos → `SHELL: NO INPUT` + `SHELL: DONE` (no aplica al guion por defecto).
- Comando desconocido: `SHELL: UNKNOWN COMMAND`.
- Contador de escrituras esperado tras el shell: **18** (5 del bloque VFS + 13 del shell). No cambiar los contadores `runs=7`, `rejected=6`.
- El shell corre dentro de `case 0`, tras la comprobación de ticks; no reordena el bloque VFS del Hito 7.

## Propiedad de archivos (evitar conflictos)
- 703A driver/syscall: `ferros/kernel/drivers/serial.zen`, `ferros/kernel/userspace.zen`.
- 703B shell: `ferros/user/main.zen`.
- 703C QEMU/QA: `infrastructure/scripts/boot_ferros.py`, `ferros/tests/test_boot.py`, `ferros/tests/test_shell.py`.
- Lead: integración, docs (`docs/ferros/shell.md`, ARCHITECTURE/ROADMAP/README), contratos e informes.

## Ciclo actual (objetivo: completar hitos restantes)
- Hito 8 y TASK-703 cerrados. Meta activa: Hito 9 (autohosting parcial) + Hito 10 (madurez) + Fase 8.
- Cerrado este ciclo: TASK-902 (lexer en Zen, 6 tests), TASK-902B (parser/evaluador, 7 tests), TASK-802 (flags: mantener -O2, ADR-015), TASK-907 (`verify_all.py` + `docs/quality.md`).
- Puerta completa: `python3 infrastructure/scripts/verify_all.py` → 8/8 PASS, ~40–48 s (incluye reproducibilidad).
- TASK-902E/F/G/H/I intérpretes, typechecker y codegens ✅ (selfhost 127); TASK-908 repro builds y TASK-911 CI local ✅.

## Progreso TASK-703
- 703A ✅ driver RX + syscall 8 (kernel build GREEN).
- 703B ✅ shell de usuario (ELF GREEN, writes=18 con el guion).
- 703C ✅ runner stdin + tests (11+11 tests) y aceptación (6/6 estado 33).
- Integración Lead: contador kernel `writes>=5`, runner exige 18; sin entrada termina 33 sin panic.
- Integración A+B+Lead: build release OK; arranque manual con entrada diferida → estado 33 y transcripción exacta (writes=18).

## Riesgos activos
- El FIFO serie se limpia en `serial_init`; el runner debe inyectar la entrada **tras** ver `SHELL: READY` (no al arrancar).
- Cambiar la serie esperada afecta a tests negativos y a `writes=18` con el guion → revisar todas las aserciones.
- Sin `.git`: no hay worktrees; aislamiento por propiedad de archivos y builds en directorios privados (/tmp).
