# TASK-906: Cierre documental, release y madurez (Fase 9/Hito 10)

**Agente**: 15/17
**Estado**: COMPLETADA
**Resultado**: CHANGELOG v0.1.0, docs/release, docs/README y docs/maturity; 247 enlaces OK; conciliado con persistencia (151/39/6/147).
**Dependencias**: TASK-907, TASK-911, TASK-913
**Archivos (propiedad exclusiva)**: `CHANGELOG.md` (nuevo), `docs/release.md` (nuevo), `docs/README.md` (nuevo índice), `docs/maturity.md` (nuevo)

## Objetivo
Cerrar la deuda documental de Fase 9/Hito 10: changelog/release v0.1.0, índice de documentación, y una **revisión de madurez basada en evidencia** (sin sobreafirmar).

## Contrato
- `CHANGELOG.md`: versión 0.1.0 (fecha), hitos 1–10, herramientas (`fmt`, `lint`, `lsp`, CI local, campaña), cambios por fase con enlaces a ADR/reportes; sección "No incluido" (CI remoto, stdlib amplia, self-hosting completo, persistencia, KVM/SMP).
- `docs/release.md`: qué es una release local, artefactos reproducibles (`repro_build.py`), matriz CI local (`ci_matrix.py`), campaña de estabilidad, comandos, límites y checklist de release (tests, gate full, estrés, reproducibilidad); sin afirmar publicación/artefacto firmado.
- `docs/README.md`: índice navegable por subsistemas (Zen, Ferros, calidad, decisiones, benchmarks, handoff histórico).
- `docs/maturity.md`: tabla de niveles por subsistema (Experimental/Verificado/Integrado/Estable/Optimizado) con **evidencia concreta y fecha**, actualizando `docs/quality.md` solo si hay evidencia; regla explícita: nada sube a Estable/Optimizado sin campañas repetidas/benchmarks; estado actual sin sobreafirmar.
- No edites código, tests, scripts, ADR ni otros docs; si detectas contradicciones, documéntalas y avisa en el informe.
- Verifica enlaces de markdown y consistencia de conteos (151/34/6/147) con `verify_all.py`/`cargo test`/selfhost.

## Aceptación
- Los cuatro documentos existen, enlazan correctamente y son coherentes con el árbol actual (conteos, hitos, límites).
- `python3 infrastructure/scripts/verify_all.py --full` PASS (no debe romperse nada).
- Informe: documentos, enlaces verificados, evidencia citada, contradicciones detectadas y qué NO se demuestra.
