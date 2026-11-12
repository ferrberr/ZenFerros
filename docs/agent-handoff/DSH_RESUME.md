> **Documento histórico de la transferencia Codex→DSH (2026-11-11).** No describe el estado actual; el estado vigente está en `agents/STATE.md`, `ROADMAP.md`, `ARCHITECTURE.md` y `docs/quality.md`.

# Mensaje para DeepSeek Harness

DeepSeek Harness: retoma Zen + Ferros desde el workspace transferido.

Este proyecto se inició originalmente en DSH. Posteriormente continuó en Codex, donde se cerraron los hitos1–6 mínimos y se conservaron evidencias de compilación, tests y QEMU. Ahora vuelve a DSH por decisión del usuario. Conserva las decisiones originales compatibles con el estado real e incorpora los cambios hechos en Codex; no reinicies el proyecto ni repitas la implementación de tareas completadas.

## Lectura y conciliación inicial

Lee primero `docs/agent-handoff/{CONTEXT,CODEX_WORK,CURRENT_STATE}.md`, `AGENTS.md`, `ROADMAP.md`, `ARCHITECTURE.md`, ADR-007 a ADR-012 y los informes TASK-710/711 con sus revisiones parciales. Consulta los informes anteriores cuando el componente lo requiera. Verifica fuentes y registros antes de afirmar capacidades. Distingue propuesta antigua, implementación actual, resultado histórico documentado y verificación recién ejecutada.

Busca contradicciones con tu contexto anterior, especialmente:

- LLVM/inkwell o Cranelift propuestos frente al backend real C11/cc.
- AST/parser/gramática históricos frente al frontend activo mvp.rs.
- Structs/ownership/módulos/stdlib deseados frente al subconjunto realmente soportado.
- Limine/UEFI/ISO/CMake previstos frente a Multiboot1, wrapper ELF32 y scripts Python actuales.
- Instrucción SYSCALL prevista frente a ABI int0x80 implementada.
- Procesos concurrentes previstos frente a threads kernel y una invocación usuario posterior, compartiendo CR3 supervisor.
- Documentos Hitos3–5 con marcadores antiguos frente a runner actual HITO6OK; BLOCKED-610 ya resuelto.
- Afirmaciones de rendimiento/seguridad de diseño frente a alcance TCG/GPR realmente probado.

No borres ni restaures versiones antiguas automáticamente: registra cada contradicción, su fuente y la resolución propuesta. Mantén la intención original cuando no contradiga contratos y evidencia actuales. Si cambia una decisión de arquitectura, explícala en ADR con pruebas.

## Punto de partida

Hito6 mínimo cerrado: ELF64 estático Zen separado en CPL3, loader validado con rollback, U/S/W^X, stack/guard, TSS y syscalls write/exit/ticks. Se verifican siete invocaciones, seis faults de aislamiento y limpieza PMM.65tests pasaron en el último cierre, con boots repetidos y revisiones cruzadas. Los informes contienen comandos/logs; vuelve a validar baseline en tu entorno, sin presentar esos resultados antiguos como recién ejecutados.

Siguiente hito acordado: VFS/RAMFS e init/shell mínimos. El paso exacto está en CURRENT_STATE.md: comprobar entorno/evidencia, formular nuevo contrato y empezar por VFS/RAMFS acotado y sus errores/tests, después ABI de archivos y programa init/shell. No hay filesystem o shell implementados que debas dar por hechos.

Respeta AGENTS.md: contratos explícitos, propiedad exclusiva, aislamiento de cambios paralelos, evidencia y revisión por otro agente de compilador/kernel/memoria/unsafe/ASM. Mantén lógica del kernel en Zen y primitivas CPU en ASM. Ejecuta código privilegiado solo en VM. No inventes soporte de lenguaje para resolver un módulo.

El usuario prefiere avanzar autónomamente hasta cerrar cada hito y recibir un informe breve con cambios y pruebas. Optimiza el coste de modelos/esfuerzo disponibles sin inventar porcentajes de ahorro. **No uses Astra**; esa es su instrucción explícita final en Codex. No asumas que followup cambia un modelo/esfuerzo si tu herramienta no lo permite.

## Historial y límites de la transferencia

El `.git` del workspace entregado está vacío y `git status`/`git log` fallan. No hay historial principal, remoto o merges verificables aquí. Hay hashes de commits temporales citados en CODEX_WORK.md y reportes; no equivalen a commits disponibles del checkout. Los repositorios temporales consultados ya no proporcionan logs. No dependas de /tmp. Comprobar si DSH conserva otro historial válido es un paso de investigación, no permiso para sobrescribir este workspace.

Codex tuvo acceso a esta conversación (parcialmente resumida), archivos del proyecto y evidencia persistida, no a todo tu historial DSH original. El resumen no contiene secretos ni credenciales y no autoriza copiar configuración privada, autenticación o cuentas entre entornos.

La última petición al preparar esta transferencia fue **solo documentación**. No se modificó código ni configuración ni se inició el siguiente hito. Espera la instrucción de desarrollo aplicable en DSH; este mensaje aporta contexto y una ruta de continuación, no prueba de acceso a herramientas/cuentas de Codex.
