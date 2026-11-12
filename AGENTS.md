# AGENTS.md — Instrucciones de Colaboración Multiagente

## Protocolo de Colaboración (Reglas Fundamentales)

### Regla 1: Contratos Explícitos
Cada tarea debe tener:
- Identificador único (ej: `TASK-001`)
- Responsable (agente asignado)
- Objetivo claro y medible
- Dependencias (IDs de tareas previas)
- Archivos afectados (rutas relativas)
- Criterios de aceptación (tests, benchmarks, verificación)
- Pruebas necesarias
- Resultado esperado

### Regla 2: Integración Controlada
- Usar ramas Git o worktrees para trabajo paralelo
- No modificar concurrentemente el mismo componente sin coordinación
- Pull requests / merges revisados por agente distinto al autor

### Regla 3: Revisión Cruzada Obligatoria
Código crítico requiere revisión de agente distinto:
- Compilador (lexer, parser, typechecker, backend)
- Sistema de tipos y memoria
- Kernel (scheduler, syscalls, memory management, drivers)
- Código `unsafe` / ensamblador

### Regla 4: Evidencia Obligatoria
Toda tarea completada debe documentar:
- Cambios realizados (diff o resumen)
- Comandos ejecutados y salida
- Tests pasados/fallidos (con output)
- Métricas relevantes (tiempo, memoria, tamaño binario)
- Riesgos pendientes y deuda técnica

### Regla 5: Gestión de Bloqueos
Si un agente queda bloqueado:
1. Identificar causa raíz
2. Registrar en `agents/tasks/BLOCKED-<id>.md`
3. Solicitar ayuda a agente apropiado via `send_message`
4. Investigar alternativas (prototipos aislados si necesario)
5. Aplicar solución verificable
6. Continuar desarrollo

## Roles de Agentes (Referencia del Prompt Maestro)

| ID | Rol | Responsabilidad Principal |
|----|-----|---------------------------|
| 00 | **Orquestador Principal** | Dirección, coordinación, roadmap, integración |
| 01 | **Arquitecto Zen** | Sintaxis, semántica, tipos, memoria, concurrencia |
| 02 | **Frontend Zen** | Lexer, parser, AST, análisis semántico, tipos |
| 03 | **Backend Zen** | Codegen, LLVM, ABI, optimización, linking |
| 04 | **Optimización** | Benchmarks, profiling, SIMD, PGO, LTO |
| 05 | **Seguridad Memoria** | Ownership, borrowing, lifetimes, static analysis |
| 06 | **Arquitecto Kernel Ferros** | Arquitectura, syscalls, procesos, SMP, aislamiento |
| 07 | **Boot Engineer** | Bootloader, entry point, CPU/memory init, QEMU |
| 08 | **Kernel Memory** | PMM, VMM, page allocator, heap, page faults |
| 09 | **Procesos/Concurrencia** | Scheduler, threads, context switch, IPC, timers |
| 10 | **Drivers** | Console, serial, timer, keyboard, storage, PCI, VirtIO |
| 11 | **Filesystems** | VFS, RAMFS, persistent FS, cache, permissions |
| 12 | **Userspace** | Syscall ABI, loader, runtime, stdlib, init, shell |
| 13 | **Virtualización/QA** | QEMU automation, integration tests, regression |
| 14 | **Seguridad** | Threat modeling, fuzzing, audit, hardening |
| 15 | **Toolchain/DevEx** | CLI, build system, formatter, LSP, debugging |
| 16 | **Investigación** | Nuevas estrategias, CPU arch, prototipos experimentales |
| 17 | **Integración/Releases** | Merge, versioning, CI, reproducibility, changelog |

## Gestión de Tareas

### Ubicación
- `agents/tasks/` — Tareas pendientes, activas, completadas
- `agents/reports/` — Resultados de ejecución por agente/tarea
- `agents/decisions/` — Decisiones arquitectónicas (ADR)

### Formato de Tarea (`agents/tasks/TASK-<NNN>.md`)
```markdown
# TASK-<NNN>: <Título>

**Agente**: <ID/Rol>
**Estado**: PENDIENTE | EN_PROGRESO | BLOQUEADA | COMPLETADA | REVISION
**Prioridad**: ALTA | MEDIA | BAJA
**Dependencias**: [TASK-XXX, TASK-YYY]
**Archivos**: [rutas/afectadas]

## Objetivo
Descripción clara y medible.

## Criterios de Aceptación
- [ ] Criterio 1 verificable
- [ ] Criterio 2 medible
- [ ] Test X pasa

## Evidencia Requerida
- Comandos ejecutados
- Output de tests
- Métricas
- Riesgos
```

### Ciclo de Vida
1. **Orquestador crea tarea** en `agents/tasks/`
2. **Agente asignado** la mueve a `EN_PROGRESO`
3. **Agente trabaja** y produce evidencia en `agents/reports/`
4. **Agente marca** `COMPLETADA` con evidencia
5. **Orquestador/Revisor** valida y cierra o solicita cambios

## Comunicación

- **Orquestador ↔ Agentes**: `send_message` para delegar, steer, unblock
- **Agente → Agente**: `send_message` para coordinación técnica puntual
- **Decisiones importantes**: Registrar en `agents/decisions/ADR-<NNN>.md`

## Estado Persistente

Al reiniciar sesión:
1. Leer `ROADMAP.md` y `ARCHITECTURE.md`
2. Listar `agents/tasks/` para ver pendientes
3. Leer `agents/reports/` para contexto reciente
4. Continuar desde último estado conocido

## Métricas de Calidad por Nivel de Madurez

| Nivel | Criterio |
|-------|----------|
| Experimental | Prototipo funcional compila |
| Verificado | Pasa tests funcionales automatizados |
| Integrado | Funciona con componentes relacionados |
| Estable | Pasa tests de regresión y estrés |
| Optimizado | Benchmarks reproducibles, mejoras justificadas |

Cada subsistema debe tener estado explícito en `ARCHITECTURE.md`.

---

*Generado según PROMPT MAESTRO ZEN + FERROS — Sección 4, 11, 12*