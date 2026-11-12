# TASK-710 — Hito6: ELF Zen en ring3 y syscalls

**Fecha**: 2026-11-11. **Resultado**: mínimo implementado y verificado; revisión cruzada TASK-711 por autores distintos de cada componente.

## Cambios

- `userspace.zen`: loader ELF64 estático de dos pases, validación de headers/rangos/solapamientos/entry/W^X antes de asignar, BSS cero y rollback PMM. PD/PT reservados conectan una ventana U en1GiB sin abrir el mapa de identidad supervisor. Stack usuario16KiB con guard y teardown/invlpg/free entre invocaciones.
- GDT/TSS64/RSP0 dedicado, selectores kernel conservados, usuarioCS23/SS1b, puertos denegados, flags fijos y registros inicializados al entrar con IRETQ. Retorno por exit/fault recupera contexto del controlador con IF0. IDT128 DPL3 comparte wrapper15GPR; resto de puertas DPL0.
- ABI int0x80: write/exit/ticks y ENOSYS; write≤4096 valida todo el rango y cada hoja antes del primer byte serie. Kernel-origin faults y eventos graves del sistema siguen fatales. Excepciones síncronas de usuario terminan la tarea y vuelven al controlador.
- ELF usuario separado en Zen con adaptadores ASM, build/linker e inspección propios, sin libc/undefined/relocaciones en el artefacto. El kernel incorpora el archivo ELF como bytes, no como funciones kernel enlazadas.
- Caso0 prueba CPL3/IOPL0/IF1,14GPR, BSS cero, salida, seis rechazos, ENOSYS y avance PIT. Seis recargas prueban lectura kernel, escritura text, CLI, ejecución stackNX, guard y puerta IDT no autorizada. Se comprueban fault/error/CR2 y PMM restaurado tras cada una. Runner exige marcadores y contadores reales.
- Pruebas permanentes, ADR-012 y guía `docs/ferros/userspace.md`; README/ROADMAP/ARCHITECTURE reflejan el mínimo real.

## Comandos ejecutados y resultados

```text
env CARGO_HOME=/home/ferranfg/proyectos/ZenFerros/.cargo cargo test --offline --manifest-path zen/compiler/Cargo.toml
27 unitarias +8freestanding_cli +11native_cli: 46 passed; 0 failed.

python3 -m unittest discover -s ferros/tests -v
Ran 19 tests in 13.647s
OK

python3 infrastructure/scripts/boot_ferros.py --all --repeat 3
debug: PASS33 /0.503414s,0.49619s,0.49522s
release: PASS33 /0.342426s,0.344368s,0.344701s
Todos: stderr vacío, sin timeout, HITO 6 OK.
```

**65tests pasan**, sin cambiar el compilador. Host usa Zen real normal/O2 y UBSan con CPU/IO/PMM simulados, nunca instrucciones privilegiadas. Loader:33mutaciones,64truncados iniciales, tamaño/overflow, ocho fallos sucesivos de asignación del fixture, cero BSS, W^X, rango cruzado/supervisor, clasificación NMI/DF/MC/IRQ/PF_RSVD y resultados del dispatcher. El primer UBSan detectó un problema de instrumentación/acceso negativo en el fixture C; se cambió a indexar el array completo de trap por su slot RAX, y pasan las cuatro combinaciones. No se desactivó UBSan.

La suite Ferros incluye17guests reales:2normales de Hito6,6negativos Hito6 (ELF inválido/U ausente/PF kernel, ambos perfiles),8negativos anteriores (excepción inesperada/guard/estado/retorno, ambos perfiles) y1timeout esperado sin preemption. Cada negativo exige ausencia de éxito prematuro. Los logs de TemporaryDirectory se eliminan con el fixture; la salida/resumen de la suite consta aquí. La revisión independiente conserva logs adicionales de negativos.

Además del lote de6repeticiones, se ejecutó la imagen optimizada con `boot(...,memory_mib=32)` y128: ambos33,7runs/1write/6rechazos/IRQs1, sin stderr ni timeout. Son8boots finales normales en evidencia persistente `TASK-710/`, cada uno con siete invocaciones de usuario; no se confunden con siete guests.

Salida real optimizada:

```text
SCHEDULER: STATS switches=45 preemptions=25 yields=16 completed=3
USER: Hello from Zen
USERSPACE: RING3 AND SYSCALLS OK
USERSPACE: ISOLATION AND CLEANUP OK
USERSPACE: STATS runs=7 writes=1 rejected=6 irqs=1
Boot successful
HITO 6 OK
```

Los marcadores previos de memoria/IRQs/threads también se verifican. Normal obtuvo8IRQs de usuario; optimizado1. No son valores fijados en el kernel ni un benchmark de latencia.

## Métricas finales

| Perfil | Kernel ELF64 | Contenedor ELF32 | ELF usuario | Build observado | QEMU media/rango,3boots |
|---|---:|---:|---:|---:|---|
| Normal |126352B|123852B|20216B|0.290891s|0.498275s /0.495220–0.503414s|
| Optimizado |52256B|50744B|13568B|0.540472s|0.343832s /0.342426–0.344701s|

QEMU11.1.3, TCG/qemu64,1CPU,64MiB principal;32/128 adicionales. Sin KVM ni dispositivos/red/discos del host. Memoria física gestionada sigue limitada64MiB. Fuentes kernel Zen:59.51% de SLOC frente al ASM de primitivas;56.41% incluyendo bootstrap. Método textual sin comentarios/blancos; tests/linker/C generado separados, no se presenta C generado como código Zen escrito. JSON de métricas/source-metrics y build/logs en `TASK-710/`.

## Integración y revisión

Snapshots Git temporales, propiedad exclusiva e integración por copia secuencial: ASM `96a9135` en `/tmp/zenferros-task710-arch`; user/build `f491a49` en `/tmp/zenferros-task710-user`. El `.git` principal sigue vacío/protegido, sin afirmar commit/merge local. Root implementó loader/mapeo/syscalls/routing/runner/tests y documentación.

La revisión detectó y corrigió alineación del stub de usuario, atribución indebida de eventos del sistema al usuario y error de índice IDT esperado en GP (0x40a). Se incorporó política fatal para PF_RSVD y excepciones de stack/segmento de usuario. Los tests y lote final se ejecutaron después de los cambios de implementación.

Se reutilizaron agentes Sol; boot_engineer revisó núcleo/ASM ajenos y context_recovery revisó user/build ajenos. La herramienta rechazó nuevos agentes por límite de chats; no se atribuye un cambio real de esfuerzo al texto de un followup. Tras la orden «no uses astra» se detuvo el revisor de modelo no verificable y continuaron estos agentes Sol heredados. No se ejecutó ninguna nueva selección de Astra ni se estima ahorro numérico de tokens. Detalles ADR-012 y TASK-711.

## Riesgos y siguiente hito

Una invocación activa, compartiendo CR3 con kernel supervisor, sin procesos concurrentes/IPC/FS/shell. ABI int0x80; instrucción SYSCALL/SYSRET pendiente. El loader ignora sectionheaders, no reloca ni garantiza rechazo de toda sección REL/RELA; el inspector sí verifica el artefacto generado. Perfil Zen sin FPU/SIMD/TLS; no hay aislamiento de ese estado para binarios arbitrarios. Sin cuotas de CPU: un programa infinito necesita timeout QEMU. Sin ASLR/KPTI/IST, guard de RSP0 o recuperación robusta de doublefault/overflow. Volatile no sincroniza SMP.

SiguienteHito7: VFS/RAMFS e init/shell mínimos con contratos de descriptores, lectura y comandos; drivers persistentes/IPC y generalización de procesos se planifican aparte.
