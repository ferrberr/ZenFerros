# TASK-611 — Revisión independiente Hito 5

**Revisor**: scheduler_audit, distinto de autores de scheduler/contexto/integración.
**Fecha**: 2026-11-11.
**Estado**: COMPLETADA — revisión técnica favorable para Hito5 mínimo.

## Contrato y propiedad

Revisión de TASK-610: threads de kernel en una CPU, round-robin por PIT, yield y exit, contexto GPR/stack y guardas. Único archivo modificado en el workspace por el revisor: este informe. Los artefactos de compilación y QEMU independientes se guardarán bajo `/tmp/zenferros-task611-review`. No se ejecuta ensamblador privilegiado en el host.

## Revisión crítica

- `interrupts.S`: 15 GPR, vector/error normalizados, base en RBX callee-saved, llamada alineada y restauración exacta antes de IRETQ. El marco del IRQ puede permanecer en el stack del thread durante el cambio cooperativo interno.
- `interrupts.zen`: EOI master precede a `scheduler_on_timer`; evita mantener el IRQ0 en servicio mientras otro thread ejecuta. Los guards no presentes con escritura supervisor causan panic, sin recuperación de RIP.
- `memory.zen/vmm_guard_page`: limita el cambio a los tres símbolos de guarda, página alineada y dentro del kernel; comprueba CR3, identidad y permisos supervisor/RW/NX antes de limpiar PTE e invalidar TLB. No se presenta como unmap general.
- Entrega preliminar `context.S`: seis registros callee-saved y RSP; orden consistente con frame inicial de64bytes. Trampoline entra con RSP8mod16 y resta8 antes de llamar Zen. Tres reservas de guarda4KiB+stack32KiB independientes y estado4KiB en BSS. Sonda comprueba15GPR con patrones distintos y canary local tras STI/HLT/CLI y retorna con IF0.
- `scheduler.zen` integrado: política y estado permanecen en Zen. Inicialización one-shot con guards, frame64bytes y canary inferior; slots y tamaños coinciden con ASM. Las mutaciones de política ocurren con IF0, y yield restaura el IF previo tras reanudar el mismo ID. El timer conserva IF0 hasta retornar por el wrapper. Las comprobaciones recorren todos los workers y rechazan estado/RSP/canary inválidos antes de cambiar.
- READY/RUNNING/EXITED/BLOCKED: el controlador queda BLOCKED hasta tres exits; el round-robin omite el actual y nunca selecciona EXITED. Cada exit se cuenta una sola vez y el último restaura el stack guardado del controlador; cualquier reanudación de exit sería fatal. El scheduler es one-shot y no reutiliza stacks terminados.
- Worker1 mantiene IF habilitado en un bucle que solo lee progreso volatile de2/3: no llama yield ni HLT en esa puerta. Por tanto, requiere que el PIT lo preempte. Después cada worker ejecuta8rondas de trabajo con hash/local-canary/ID y sonda15GPR+canary. Workers2/3 ceden una vez por ronda,16yields totales. No hay I/O ni alloc en workers.
- Al volver al controlador se exigen3completions, cero fallos, al menos2preemptions, exactamente16yields, progreso8/hashes calculados y al menos8sondas por worker, y ticks activos iguales al delta de IRQ0. Los mensajes OK se emiten después de esas comprobaciones. Los números impresos se leen de los contadores reales, no de una cadena fija.
- Runner: mantiene estado33, mensajes exactos y stderr vacío; admite exactamente una línea estructurada de números y comprueba switches>=6,2<=preemptions<=switches,yields16,completed3. Se recomendó al integrador alinear sus umbrales con el self-test; la versión revisada ya incorpora ese ajuste.

## Evidencia independiente ejecutada

Comandos utilizados: `python3` con imports de `build_kernel`/`boot`, salidas explícitas bajo `/tmp/zenferros-task611-review`; `python3 -m unittest discover -s ferros/tests -v`; inspección de fuentes, frames y hashes. Ningún contexto ASM se ejecutó en host. Los tests host usan mocks que abortan si se intenta el context switch o la sonda privilegiada.

1. **QEMU real TCG, builds propios normal/optimizado** desde fuentes integradas con la puerta busy-poll final:

| Perfil | Estado | Tiempo observado | ELF64 / contenedor bytes | Switch / preempt / yield / complete |
|---|---:|---:|---:|---|
| Normal |33|0,376644s|76000 /73740|45 /25 /16 /3|
| Optimizado |33|0,330667s|31000 /29636|45 /25 /16 /3|

Ambos con stderr vacío, mensajes completos hasta `HITO 5 OK`, contexto/hashes/progreso comprobados antes del éxito. Logs y resultados en `{debug,release}/boot`; resumen propio `review-results.json`.

2. **Guard y estado inválido reales**, builds propios de `scheduler_guard.zen` y `scheduler_invalid.zen`, ambos perfiles: cuatro boots terminan35, sin timeout ni HITO5OK, con `thread stack guard violation` o `invalid thread scheduler state` respectivamente. Guard realiza escritura real después de CR3/IDT y scheduler_init; no es un mock del page fault.

3. **Retorno accidental real por trampoline**, mutación temporal de la fuente que hace retornar `thread_entry`, sin alterar el fallback ASM: ambos perfiles terminan35 con `FERROS PANIC: thread entry returned`, sin HITO5OK (0,119511s/0,082817s). La primera aserción del script esperaba la razón genérica de estado; se corrigió la expectativa al mensaje específico y se repitieron ambos boots satisfactoriamente. El código del kernel no se cambió para resolver esa aserción. Fuentes mutadas en `return-source`, evidencia en `{debug,release}/actual-worker-return/boot`.

4. **Control negativo de necesidad de preemption**: en copia temporal optimizada, `scheduler_on_timer` retorna sin elegir/cambiar thread. El PIT sigue existiendo pero worker1 no puede superar la puerta de progreso; timeout controlado1,005232s, sin `THREADS: CONTEXT OK` ni HITO5OK. El runner recoge logs y termina el guest. Evidencia en `release/no-preemption/boot`, copia `no-preemption-source`. Esto descarta que el test pueda completarse ejecutando solo el primer worker sin preemption.

5. **RAM32/128MiB**, nuevo build optimizado final: ambos estado33, stderr vacío,45/25/16/3;0,325294s/0,328274s. Evidencia en `final-release/ram-{32,128}` y hashes fuente en `final-release/source-hashes.json`. No implica que PMM gestione más de su límite64MiB.

6. **Suite Ferros actual**:

```text
$ python3 -m unittest discover -s ferros/tests -v
Ran 14 tests in 3.923s
OK
```

Incluye108combinaciones de round-robin, frames iniciales, IF/restauración, errores de estado/RSP/canary/inicialización, rutas inactivas y retorno fatal; host normal/O2 y UBSan. También memoria/PIC/PIT/UART, validación de stats, cancelación/timeout/logs y seis negativos guard/state/return reales en QEMU. La regresión completa del compilador y el lote persistente global corresponden al integrador; esta revisión no los sustituye por una cifra no ejecutada.

7. Tras incorporarse el control negativo de preemption como test permanente, se revisó la mutación y se ejecutó `python3 -m unittest discover -s ferros/tests -p test_scheduler.py -v`: **3 tests pasan en3,361s**, incluyendo el nuevo timeout0,75s sin hook de scheduler, los seis negativos y host/UBSan. La suite Ferros contiene ahora15tests; no se confunde ese total con los14ejecutados en el lote anterior. También se comprobó el ajuste final que fija la posición de stats antes de `Boot successful`.

## Dictamen

**Favorable para la implementación mínima de TASK-610.** No quedan bloqueantes técnicos observados en los caminos inspeccionados y ejecutados. Solo se modificó este informe dentro del workspace; las mutaciones de prueba quedaron en `/tmp` y nunca se integraron.

## Límites y deuda

Una CPU y un addressspace; no usuarios/SMP/SIMD, bloqueo de recursos, prioridades, allocator concurrente ni robustez IST/double-fault. Un acceso explícito a guard con stack sano no equivale a recuperación de stack overflow real.

Init no revierte guards ya retirados si falla parcialmente y es one-shot; el llamador falla el boot. Los tres stacks son reservas estáticas32KiB, sin creación dinámica ni reutilización. Volatile no es sincronización SMP. Los tiempos son observaciones TCG, no benchmarks de rendimiento o latencia garantizada. No se demuestra hardware físico, KVM ni estrés prolongado. La infraestructura `.git` principal continúa sin historial disponible; no se afirma merge Git revisado inexistente.
