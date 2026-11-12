# TASK-610: Hito 5 completado — multitarea de kernel

**Fecha**: 2026-11-11
**Estado**: COMPLETADA / INTEGRADO MÍNIMO

Ferros ejecuta tres threads reales con stack privado y guarda, round-robin por PIT, yield y exit, y vuelve al controlador de boot. Worker1 espera ocupado sin ceder hasta que avanzan los otros dos; no se puede superar esa espera sin un cambio de tarea por IRQ. Cada worker verifica ocho rondas/hash, ID, progreso, canary y registros después de reanudar.

## Cambios y contratos

- Scheduler y estados en Zen, con IF deshabilitado durante las mutaciones. EOI antes de la selección de otra tarea. Controles de estado/RSP/canary previos al switch, EXITED nunca seleccionado y controlador BLOCKED hasta los tres exits.
- context.S original: seis GPR callee-saved/RSP para switch, frame inicial64B y trampoline ABI, helpers IF y sonda15GPR/canary que fuerza una interrupción real. El marco15GPR/IRET del handler previo permanece en el stack de su thread.
- Tres stacks estáticos32KiB y guardas4KiB. VMM solo permite retirar esas tres páginas, con identidad/RW/NX/CR3/bounds comprobados y flushTLB. Escritura en guarda desde stack sano produce panic específico.
- El kernel imprime contadores reales; el runner los extrae a result.json y exige una única línea en posición correcta, al menos6switches,2preemptions, exactamente16yields y3completions, además de estado33, mensajes completos y stderr vacío.
- Tests host de108selecciones, frames/IF/estado/RSP/canary/init, builds normal/O2 y UBSan. Mocks abortan si se intenta switch/probe privilegiado en host.
- Tests QEMU guard/state/retorno real del trampoline y mutación sin preemption, más regresión de memoria/IDT/UART. Build acepta sustitución explícita de unidades solo para generar las pruebas mutadas. No se modificó el compilador.

## Modelos y recuperación

Se reutilizó la integración persistente del intento interrumpido. No quedaban agentes activos ni entregas /tmp; se recrearon contratos aislados con prompts sin historial completo:

| Agente real | Modelo / esfuerzo | Propiedad |
|---|---|---|
| scheduler_recovery | gpt-6.1-sol / high | scheduler.zen |
| context_recovery | gpt-6.1-sol / medium | context.S |
| scheduler_audit | gpt-6.1-sol / high | revisión independiente, TASK-611 |

Se evitó reintentar Astra tras su límite de uso. La selección reservó esfuerzo alto para política/revisión y medio para ASM acotado, sin multiplicar revisiones ni copiar todo el historial. No se dispone de consumo exacto de tokens/coste por agente y no se atribuye un porcentaje de ahorro no medido. Configuración explícita respaldada por [OpenAI Docs](https://learn.chatgpt.com/docs/agent-configuration/subagents); el uso real está en los contratos y herramientas de esta sesión.

Scheduler aislado task610-scheduler commit b68953d; ASM task610-context commit13e611d, ambos copiados secuencialmente. El integrador dio motivo específico a thread_returned y actualizó runner/tests; el revisor comprobó la fuente final y la ruta asm real. .git del workspace sigue vacío/protegido: no se declara merge inexistente. El snapshot de recuperación se guardó en /tmp/zenferros-task610-baseline; no se confunde con un historial completo anterior a la interrupción.

## Resultados ejecutados

```text
python3 -m unittest discover -s ferros/tests -v
Ran 15 tests in 5.138s
OK

env CARGO_HOME=/home/ferranfg/proyectos/ZenFerros/.cargo cargo test --offline --manifest-path zen/compiler/Cargo.toml
27 unitarios passed; 0 failed (0.11s)
8 freestanding CLI passed; 0 failed (1.01s)
11 hosted CLI passed; 0 failed (0.23s)
0 doc tests; 0 failed

python3 infrastructure/scripts/boot_ferros.py --all --repeat 3
debug: PASS33 tres veces (0.372,0.401,0.381s)
release: PASS33 tres veces (0.332,0.335,0.331s)
SCHEDULER: STATS switches=45 preemptions=25 yields=16 completed=3
Boot successful
HITO 5 OK
```

61 tests permanentes pasan (46compilador+15Ferros). La suite contiene los casos de memoria/IRQ anteriores y añade validación de stats, política del scheduler, seis boots negativos de scheduler y timeout sin preemption. El compilador no cambió: regresión debug ejecutada, release ya verificado anteriormente. Los dos niveles de optimización del kernel se ejecutaron realmente.

Batería final persistente: seis boots64MiB, dos del mismo kernel optimizado con32/128MiB, guard/state/return/unarmedexception en ambos perfiles (ocho rechazos35 con motivo), y mutante sin preemption que agota0.75s sin THREADS/H5OK. Son17ejecuciones de invitado con resultado exigido. Los logs negativos conservan passed=false; su resumen registra separadamente que el rechazo era esperado. No se modifican resultados para aparentar éxito.

La línea de stats se imprime desde contadores, no desde el ejemplo EXPECTED de unit tests. En todas las ejecuciones normales de este lote fueron45/25/16/3; switches/preemptions pueden variar por temporización. Los mensajes de contexto/yield/exits solo se emiten después de validar hashes/progreso/sondas por thread y recuperar el controlador.

## Revisión y fallos corregidos

TASK-611 es favorable, sin bloqueantes. El auditor reconstruyó/arrancó normal y optimizado, RAM32/128, negativos guard/state y retorno real de thread_entry a su trampoline. Reprodujo el timeout al quitar el hook de preemption y verificó tests de políticas/UBSan.

Durante la integración se fortaleció la puerta de worker1: de esperar mediante sondaHLT a busy polling real. Se ajustó el validador a los mismos umbrales del kernel, se fijó la posición de la línea STATS y se diferenció el panic por retorno de entry. Una aserción inicial del auditor esperaba el motivo genérico para retorno; corrigió la expectativa al motivo específico y volvió a verificar ambos perfiles. No se relajó el criterio de éxito para pasar un boot fallido.

## Métricas observadas

| Perfil | ELF64 bytes | ELF32 bytes | Boot medio s | Rango s |
|---|---:|---:|---:|---:|
| debug | 76000 | 73740 | 0.384466 | 0.371639–0.401076 |
| release | 31000 | 29636 | 0.332714 | 0.330887–0.335137 |

Tiempo desde lanzamiento QEMU hasta salida, tres muestras por perfil; no es latencia exclusiva de switch ni benchmark competitivo. QEMU11.1.3 TCG/qemu64/1CPU/64MiB, sin KVM/red/discos. PicoRSS/ciclos/cache/energía no medidos.

SLOC actual del kernel (comentarios/blancos excluidos según script existente):57.15%Zen frente a ASM de primitivas/ISR,53.26%incluyendo bootstrap. CódigoC generado4339líneas físicas contado aparte, sin dependencias ni C de kernel escrito a mano enlazados. Detalle TASK-610-source-metrics.json. No hay atribución de rendimiento a estos porcentajes.

## Evidencia persistente y límites

`agents/reports/TASK-610/`: builds y seis boots, RAMextra, negativos y evidencia independiente copiada antes de perder /tmp. Resúmenes TASK-610-boot-results.json y TASK-610-task610-extra-results.json. Binarios, C generado y unidades combinadas en ferros/build/ (ignorados). Guía docs/ferros/multitasking.md, diseño ADR-011, revisión TASK-611.

Alcance: tres threads estáticos de kernel, una CPU/addressspace, sin usuarios/SMP/FPU/SIMD/CR3porproceso, prioridades, bloqueos de recursos, creación dinámica o reciclado de stacks. Init one-shot no revierte guardas retiradas ante fallo parcial; el caller aborta. Guardwrite desde stack sano no demuestra manejo robusto de overflow del propio stack sin IST/doublefault. No se declara estabilidad por estrés ni soporte general de procesos.

Próximo Hito6: programas de usuario, privilegios, loader y ABI/syscalls mínimos, con contratos y pruebas propias.
