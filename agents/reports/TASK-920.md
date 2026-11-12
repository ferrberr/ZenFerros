# TASK-920 — Evidencia: release local 0.1.1 y madurez

Fecha: 2026-11-12.

## Corte
Corte **0.1.1: 09:28 CET, antes de TASK-919** (PFS-en-VFS posterior, 0.1.2).
- Gate: **8/8 PASS, 1m09,0 s**, **163/43/6/166 = 378 tests**, 6/6 QEMU estado 33, `writes=18`, `PFS: BOOT 1 FILES=1`.
- `repro_build` completo PASS 1,97 s; `check_ci_workflow` 44/44 (workflow no ejecutado).
- Campaña al corte: 2 full PASS (4m17,4 s, 12+12 arranques) y 5 quick PASS (3m15,1 s).
- Hashes C/Ferros/compilador/anclas registrados en `docs/release.md`; CHANGELOG 0.1.1 con 0.1.0 histórica; madurez 18 Integrado / 2 Verificado / 1 Experimental / 0 Estable / 0 Optimizado (21 filas).
- Enlaces relativos verificados: 190, 0 rotos.

## Posterior al corte
TASK-919 (PFS visible en VFS read-only, Ferros 44) se documenta como posterior; el árbol actual exige 163/44/6/166 y gate 8/8 (54,71 s).

## Límites
- No hay CI remoto ejecutado, tag/firma/SBOM ni `.git`; el binario declara `zen 0.1.0` (corte documental).
- PFS-en-VFS queda para 0.1.2; sin self-hosting completo, hardware/KVM/SMP/UEFI ni ranking.
- Los hashes del binario del compilador no son estables entre recompilaciones; no se comparan bit a bit.
