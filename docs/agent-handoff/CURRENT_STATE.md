> **Documento histórico de la transferencia Codex→DSH (2026-11-11).** No describe el estado actual; el estado vigente está en `agents/STATE.md`, `ROADMAP.md`, `ARCHITECTURE.md` y `docs/quality.md`.

# Estado actual para reanudación

Fecha de transferencia: 2026-11-11. Último cierre: Hito6 mínimo, TASK-710/711 completadas. Esta tarea solo crea documentación: no se han vuelto a ejecutar builds/tests ni cambiado código/configuración. Resultados de abajo corresponden a ejecuciones previas persistidas, contrastadas con fuentes y registros disponibles.

## Qué funciona

Compilador Zen hosted y freestanding con frontend comprobado/C11; hello.zen y programas escalares nativos. Ferros arranca en QEMU, inicializa UART/memoria/interrupciones, ejecuta tres threads kernel preemptivos, luego siete invocaciones del ELF usuario y termina con HITO6OK. Cada hito es un mínimo integrado, no estabilidad general por estrés.

Hito6 prueba CPL3/flags/GPR/BSS cero, write, seis rechazos de punteros/tamaño, ENOSYS y ticks reales; seis ejecuciones posteriores provocan lectura kernel, escritura text, CLI, ejecución stackNX, lectura guard e int0x81. El controlador exige fault/error/CR2 correctos y PMM recuperado.

## Qué no funciona todavía / deuda conocida

- Lenguaje: structs, arrays, floats, ownership, módulos, globals propios, inline ASM, formatter/LSP, stdlib y self-hosting no implementados.
- OS: sin VFS/RAMFS, init/shell, IPC, procesos concurrentes, driver block/persistencia, SMP ni generalización de map/unmap.
- Solo una tarea usuario activa después de acabar los threads; mismoCR3 con supervisor, sin ASLR/KPTI/TLS/cuotaCPU/contextoSIMD aislado.
- Stack RSP0 sin guard/IST, sin doublefault/overflow robustos; no ejecución en hardware/KVM/UEFI demostrada.
- PMM máximo64MiB, heap arena sin free individual, asignación no concurrente. Init scheduler one-shot sin rollback parcial de guards.
- Loader ignora sectionheaders, no reloca ni rechaza necesariamente toda sección REL/RELA; inspector del artefacto de build comprueba ausencia de relocaciones.
- Un user program infinito requiere timeout externo; PIT cuenta pero no lo desaloja por cuota.
- No bloqueantes nuevos conocidos tras TASK-711, dentro del alcance revisado. Esto no equivale a ausencia de bugs ni auditoría formal.
- `.git` vacío impide historial/rollback Git principal; /tmp previo no es fiable. BLOCKED-610 describe un bloqueo **resuelto**, no trabajo actual bloqueado.

## Últimas tareas y pendientes

TASK-710 implementa CPL3/ELF/syscalls y pruebas. TASK-711 combina dos revisiones con autores distintos por componente, favorables. Hito7 todavía no implementado: VFS/RAMFS e init/shell mínimos. ROADMAP mantiene pendientes de largo plazo y borradores; no interpretar todas sus filas como contratos ya cerrados o requisitos inmediatos.

## Evidencia de pruebas anteriores

| Lote | Resultado documentado |
|---|---|
| Compilador | 27unitarias +8freestanding CLI +11hosted CLI =46, todas pasan |
| Ferros |19tests en13.647s, OK; Zen real con mocks O0/O2 y UBSan, runner y guests reales |
| Total suites |65tests; no sumar configuraciones internas como tests distintos |
| Guests dentro de suite Ferros |17:2normales H6,6negativos H6,8negativos anteriores y1timeout esperado sin preemption |
| Lote final normal |6boots normal/optimizado,3por perfil, más2release RAM32/128:8status33 |
| Revisión kernel |10boots propios:4correctos y6negativos esperados; host policy con/sinUBSan |
| Revisión usuario/build |2boots propios y18rechazos ELF del inspector |

Fuente: `agents/reports/TASK-710.md`, TASK-711 y sus dos informes parciales. Logs de tests TemporaryDirectory se borraron; no atribuir persistencia a todos ellos. Sí existen logs/JSON de lotes y revisores en `agents/reports/TASK-710/` y `TASK-711/`, con `source-hashes.json`, `boot-results.json`, `ram-results.json`, métricas y evidencia negativa.

Muestra real optimizada (fragmento, precedido por marcadores memoria/IRQs/scheduler):

```text
SCHEDULER: STATS switches=45 preemptions=25 yields=16 completed=3
USER: Hello from Zen
USERSPACE: RING3 AND SYSCALLS OK
USERSPACE: ISOLATION AND CLEANUP OK
USERSPACE: STATS runs=7 writes=1 rejected=6 irqs=1
Boot successful
HITO 6 OK
```

IRQs/switches pueden variar; el runner aplica umbrales y serie exacta, no valores inventados. Debug observó8IRQs y release1. ELF64 kernel normal126352B/release52256B; contenedores123852B/50744B; usuario20216B/13568B. Tiempos medios QEMU0.498275s/0.343832s, tres muestras por perfil; no benchmarks competitivos.

## Comandos para validar en DSH

Ejecutar desde raíz tras revisar herramientas/caché. Son instrucciones de reanudación, no comandos ejecutados de nuevo durante este handoff.

```bash
CARGO_HOME="$PWD/.cargo" cargo build --offline --release --manifest-path zen/compiler/Cargo.toml
CARGO_HOME="$PWD/.cargo" cargo test --offline --manifest-path zen/compiler/Cargo.toml
python3 -m unittest discover -s ferros/tests -v
python3 infrastructure/scripts/boot_ferros.py --all --repeat 3
```

Para hello: `zen/compiler/target/release/zen run zen/examples/hello.zen`.
Para ELF usuario: `python3 infrastructure/scripts/build_user.py --release` (ABI Ferros, no ejecutarlo como ELF Linux).
Si caché/toolchain local no viajó, diagnosticar primero; `setup_qemu.py` instala copia local fijada y necesita acceso de red. No leer/copiar credenciales de Codex/DSH. El runner aplica entorno/firmware local, evita ejecutar QEMU manual con librerías equivocadas.

## Próximo paso exacto

1. Leer estos cuatro archivos, AGENTS.md, ROADMAP/ARCHITECTURE, ADR-007..012 y cierres TASK-710/711. Contrastar el contexto antiguo DSH con código y hashes actuales; anotar discrepancias antes de cambiar diseño.
2. Inventariar toolchain y Git; ejecutar baseline anterior cuando DSH tenga autorización para desarrollo. Ante fallo, conservar logs y corregir causa, sin reimplementar hitos1–6.
3. Crear **un nuevo contrato de Hito7**, con ID disponible comprobado en agents/tasks (no se ha reservado aquí), responsable/dependencias TASK-710/711, archivos, pruebas y aceptación. Empezar por VFS/RAMFS acotado en memoria y operaciones/rutas/descriptores; definir errores, límites y ownership de buffers.
4. Proponer como aceptación inicial archivos conocidos, abrir/leer/cerrar, contenido/EOF, rutas inválidas y agotamiento/descriptor inválido; después integrar ABI de archivos e init/shell Zen mínimos con transcript QEMU verificable. Son propuestas de alcance para concretar, no interfaces ya implementadas ni decisiones originales firmadas.
5. Revisar código crítico por agente distinto y mantener todas las regresiones. Ampliar Zen solo por necesidad demostrada. No introducir simultáneamente disco VirtIO, SMP y rediseño de backend.

Esta transferencia no inicia Hito7 ni modifica documentación previa/configuración para preparar ese trabajo.
