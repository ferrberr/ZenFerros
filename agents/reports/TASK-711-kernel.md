# TASK-711 — Revisión independiente del núcleo del Hito 6

**Revisor**: gpt-6.1-sol (boot_engineer reutilizado para revisión)
**Fecha**: 2026-11-11
**Estado**: COMPLETADA — favorable para el subconjunto del Hito 6
**Propiedad**: implementación de solo lectura; este informe es la única edición del workspace. No se usaron subagentes.

## Independencia y alcance

Se revisaron `ferros/kernel/userspace.zen`, integración VMM/PMM relevante, `interrupts.zen`, `main.zen`, los añadidos CPL3/TSS de `arch/x86_64/userspace.S` y `interrupts.S`, y el build/runner de kernel/QEMU. Las fuentes `ferros/user/` y `build_user.py`, escritas por este mismo agente, **se excluyen de este dictamen independiente**; sus artefactos solo se consumen como entrada del kernel y requieren la revisión distinta asignada por el orquestador. El ISR común previo es infraestructura de un hito anterior; aquí se revisó su integración con los nuevos marcos CPL3 y syscall128.

## Revisión de fuentes

- **ELF y límites**: las comprobaciones acotan el buffer de imagen, tabla de program headers, número de headers, rangos de fichero/memoria, alineación de páginas, solapes de páginas y ventana de imagen. Las sumas y restas se realizan después de cotas que evitan wrap u64. La entrada debe caer en bytes de fichero de un LOAD ejecutable. El perfil admite solo NULL/LOAD/GNU_STACK; rechaza dynamic/interp y W+X.
- **VMM y rollback**: PML4 y enlaces superiores de la ventana reciben U, manteniendo las hojas y rama del kernel supervisor. El loader solo publica hojas RX, R+NX o RW+NX sobre páginas de PMM previamente puestas a cero/copiadas por el alias supervisor. Stack separado RW+NX y guard no presente. El clear invalida la hoja antes de liberar la página. Los fallos de asignación deshacen las hojas publicadas; el estado activo impide liberar durante una ejecución.
- **Syscalls**: write acota primero longitud<=4096 y rango completo dentro de la ventana; comprueba P/U de cada página antes del primer byte leído o escrito en serie. Rechazos de overflow, alias kernel, gap y cruce de página evitan salida parcial. El diseño de una CPU/IF0 impide desmapear la memoria entre validación y copia; no se generaliza esta propiedad a concurrencia futura. Ticks/ENOSYS/exit usan el slot RAX comprobado del marco.
- **TSS/entrada/retorno**: GDT conserva selectores kernel8/16 y añade CS0x23/SS0x1b, TSS64 límite103, RSP0 privado e I/O-map base104 fuera de límite. Datos GDT/TSS son supervisor RW, no memoria de usuario. IRETQ fija RFLAGS0x202/IOPL0 y limpia registros fuera del argumento. Leave abandona el stack de trap y restaura stack, seis GPR callee-saved y retorno del controlador con IF0.
- **Marcos**: normalización vector/error +15GPR hace RIP=base+136; RAX=frame-24, RDI=-64, RSI=-56 y RDX=-48 coinciden con el código. La llamada Zen usa RSP alineado y recupera la base guardada. Un marco CPL3 válido debe estar dentro del stack RSP0 y tener CS0x23/SS0x1b. IRQ0 reconoce EOI antes de volver; solo IDT128 tiene DPL3.
- **Clasificación de fallos**: un fault originado en kernel conserva CS8 y no se atribuye al usuario por el mero hecho de estar activo. Se verificaron las correcciones ya presentes al comenzar esta revisión: NMI/DF/MC/IRQ inesperada son fatales, PF_RSVD o PF sin bit U son fatales; SS/NP y faults síncronos admitidos de CPL3 terminan la tarea. No se modifica RIP para recuperar un fault de usuario.
- **Runner**: TCG una CPU, red/discos desactivados, RAM y timeout acotados, serial/stderr/estado persistidos; éxito exige status33, salida exacta y estadísticas válidas. Los negativos no pueden publicar éxito de Hito 6.

No se encontró un nuevo defecto bloqueante en este alcance.

## Ejecución propia en QEMU

Comando independiente real:

```text
python3 /tmp/zenferros-task711-sol/audit.py
# debug normal+RAMvariation and 3 negatives PASS
# release normal+RAMvariation and 3 negatives PASS
# INDEPENDENT KERNEL AUDIT: PASS
```

El script usa `build_kernel`/`boot` del workspace, guarda todas sus builds y logs en `/tmp/zenferros-task711-sol`, y verifica que las siete fuentes auditadas tengan los mismos SHA256 antes y después. No modifica implementación. Se construyeron mutaciones negativas en archivos temporales: clase ELF incorrecta; entrada ELF `0x100000` (kernel); y una lectura null real dentro de `user_write`, después de una entrada CPL3 válida. Esta última debe ser un fallo **de kernel**, no terminación atribuida al usuario.

| Perfil | Escenario | Status QEMU | Segundos | Evidencia |
|--------|-----------|-------------|----------|-----------|
| debug | good64 | 33 | 0.500929 | runs=7, writes=1, rejected=6, irqs=8 |
| debug | good32 | 33 | 0.481125 | runs=7, writes=1, rejected=6, irqs=8 |
| debug | invalid-class | 35 | 0.380038 | FERROS PANIC: userspace test failed |
| debug | entry-kernel | 35 | 0.379604 | FERROS PANIC: userspace test failed |
| debug | kernel-origin-pf | 35 | 0.397279 | FERROS PANIC: unexpected interrupt or exception |
| release | good64 | 33 | 0.340817 | runs=7, writes=1, rejected=6, irqs=1 |
| release | good128 | 33 | 0.345711 | runs=7, writes=1, rejected=6, irqs=1 |
| release | invalid-class | 35 | 0.330233 | FERROS PANIC: userspace test failed |
| release | entry-kernel | 35 | 0.330439 | FERROS PANIC: userspace test failed |
| release | kernel-origin-pf | 35 | 0.331160 | FERROS PANIC: unexpected interrupt or exception |

Son **10 boots propios**: cuatro correctos y seis negativos esperados. Los negativos terminaron con status35, sin timeout, con el panic previsto y sin los marcadores `USERSPACE: RING3 AND SYSCALLS OK` ni `HITO 6 OK`. Los boots correctos contienen siete invocaciones user/exit/fault, una escritura, seis buffers rechazados, ticks reales y las pruebas previas de memoria/interrupts/scheduler.

Datos completos y SHA256: `/tmp/zenferros-task711-sol/audit-results.json`. Por escenario: subdirectorio `boot/serial.log`, `boot/qemu.stderr.log`, `boot/result.json`; por build: `build.log` y `build.json`. Mutaciones y script se conservan en la misma raíz temporal.

## ELF/rollback/políticas con mocks host-safe

Comando propio real:

```text
python3 -m unittest ferros.tests.test_userspace.UserPolicyTests.test_elf_rollback_memory_permissions_buffers_and_faults -v
# test_elf_rollback_memory_permissions_buffers_and_faults ... ok
# Ran 1 test in 0.644s
# OK
```

El test ejecuta las políticas Zen reales en cuatro configuraciones (-O0/-O2, con/sin UBSan) y verifica mutaciones de cabeceras/rangos/flags/entry/solapes, truncamiento, ocho etapas de rollback, BSS cero, flags W^X, buffers completos y clasificación de traps fatales frente a fallos de tarea. Los mocks no enlazan ni ejecutan instrucciones privilegiadas. Log propio: `/tmp/zenferros-task711-sol/host-policy.log`.

## Límites y dictamen

**Favorable para el mínimo del Hito 6**, sin nuevos hallazgos bloqueantes en núcleo/integración revisados. La revisión y las ejecuciones reales no equivalen a una prueba formal de seguridad ni a procesos concurrentes: comparten CR3, una CPU y una sola tarea user activa; no hay copyin tolerante a fallos concurrentes, IST, TLS/GS, estado SIMD, scheduler de usuarios ni carga desde filesystem. Las tablas y punteros raw siguen siendo código crítico.

El dictamen independiente de la imagen fuente y build de usuario debe proceder de otro autor; este informe no sustituye ese requisito. El orquestador decide el cierre global combinando ambas revisiones y su evidencia de regresión.
