# Multitarea de kernel — Hito5

## Ejecutar

```bash
python3 infrastructure/scripts/boot_ferros.py --all --repeat 3
python3 -m unittest discover -s ferros/tests -v
```

Tras las comprobaciones de memoria e interrupciones, el kernel imprime:

```text
THREADS: CONTEXT OK
SCHEDULER: PREEMPTION OK
SCHEDULER: YIELD AND EXIT OK
SCHEDULER: STATS switches=45 preemptions=25 yields=16 completed=3
Boot successful
HITO 5 OK
```

Los números anteriores son una observación real de esta muestra; switches/preemptions pueden variar con la temporización. El runner analiza la línea real (una sola, antes de Boot successful), exige >=2preemptions, exactamente16yields y3completed, >=6switches y preemptions<=switches. Exige también todos los mensajes, estadoQEMU33 y stderr vacío. El ejemplo EXPECTED del módulo solo se usa en tests de validador; el CLI imprime los bytes capturados reales y result.json conserva los contadores extraídos.

## Cómo funciona

Controller0 usa stack de boot. Threads1/2/3 tienen32KiB privados y guarda4KiB, todos dentro de BSS reservado. El PMM no ofrece esas páginas. VMM solo permite retirar las tres guardas exactas, con CR3 y PTE identidadRW+NX válidos; invalida TLB tras borrarlas. No se permite retirar páginas arbitrarias de BSS, tablas ni stack de boot.

Scheduler en scheduler.zen, estado explícito4096B: initialized0,active8,current16,switches24,preemptions32,yields40,completions48,timerIRQs56,failures64,startticks72. Records128+id*128: rsp0,state8,progress16,hash24,probes32,canary40,low48,top56. READY1/RUNNING2/EXITED3/BLOCKED4. Controller queda bloqueado hasta que los3workers están EXITED. El selector round-robin ignora EXITED/BLOCKED, nunca resucita un stack terminado.

Todas las mutaciones se hacen con IFoff. IRQ0 incrementa ticks y envía EOI antes de llamar al scheduler. El switch guarda los6GPR callee-saved y RSP; cuando sucede desde IRQ, el marco de15GPR y retornoCPU queda suspendido en el stack del thread. Al reanudar, se vuelve al handler y a IRET. Yield restaura el IF previo, los nuevos threads habilitan IF después de validar estado y los exits no regresan.

context.S es original y solo contiene primitivas de CPU/contexto, getters y memoria reservada. Frame inicial64B y trampoline siguen ABI SystemV. El probe coloca patrones en15GPR y canary de stack, ejecuta sti/hlt/cli, compara al reanudar y conserva los registros ABI del caller. Los checks de ID, hashes y progreso por thread completan la comprobación de que no se mezclan contextos.

## Prueba de preemption real

Worker1 espera ocupado hasta que2/3 tengan progreso, con IFon pero sin yield ni HLT en ese bucle. Es necesario que un IRQ0 cambie de stack para romper la espera. Cada worker calcula8rondas/hash y pasa probes. Workers2/3 ceden una vez por ronda;16yield en total. La prueba mutada que deja scheduler_on_timer vacío agota el timeout y no emite ni THREADS CONTEXT OK ni H5OK. Esto evita aceptar llamadas secuenciales como multitarea.

## Regresiones y fallos

Hay15tests Ferros, más46del compilador. Se comprueba selector contra108combinaciones de estados, frameABI, restauraciónIF, canary/RSP inválidos, init/reinit/fallo de guarda, política de memoria y traps previos. Los objetos reales Zen de políticas se ejecutan con mocks seguros enO0/O2, también con UBSan. Los mocks abortan si se intenta cambiar contexto o ejecutar instrucciones privilegiadas en host.

QEMU normal/optimizado verifica guardwrite desde stack sano (PF write/notpresent y CR2 de guarda), currentID inválido y retorno real del trampoline mediante una unidad mutada de test. Todos deben terminar35 con panic específico, nuncaH5OK. El test sin preemption debe terminar por timeout. Los logs conservan el resultado bruto de rechazo; el resumen señala por separado si cumplió la expectativa negativa.

## Alcance

Una CPU, mismo addressspace, solo threads de kernel; no procesos aislados, programas de usuario, syscall ABI, prioridades, SMP ni bloqueo de recursos. No hay creación dinámica/reutilización de stacks, FPU/SIMD o protección robusta de overflow mediante IST. Init es una operación de una vez, sin rollback de guardas ya retiradas ante fallo parcial. Las unidades Zen siguen concatenadas, sin módulos/structs/globals del lenguaje. El próximo hito es ejecución de programas de usuario y sus contratos de privilegios/ABI/memoria.
