# TASK-908 — Evidencia: builds reproducibles y manifiesto

Fecha: 2026-11-11.

## Entregado
- `infrastructure/scripts/repro_build.py`: compara dos emisiones de C (`--emit c --release`) para hello/factorial/arrays/structs y dos builds completos de Ferros en directorios temporales distintos; hashea entradas y artefactos; manifiesto JSON con toolchain, hashes y tiempos; exit ≠0 ante diferencias; `--quick`, `--rebuild`, `--no-build`, `--manifest`.
- `docs/reproducibility.md`: alcance, resultados y límites.
- Integración en la puerta: paso 8 de `verify_all.py` (repro rápida por defecto; completa con `--full`).

## Resultados reales
```bash
python3 infrastructure/scripts/repro_build.py --quick   # PASS 0,23 s
python3 infrastructure/scripts/repro_build.py           # PASS 1,68 s
```
Hashes idénticos en dos builds (representativos):
- C `hello.zen` 9.582 B `06aced6c…42cf58`; `factorial.zen` `fbfa09dc…3aa2d8`; `arrays.zen` `fb2bff30…9e1b04`; `structs.zen` `5ec1bbbd…93301`.
- `kernel.o` 49.168 B `31fac527…49a816`; `ferros-x86_64.elf` 56.848 B `6e2ef29f…42b4da`; `ferros-multiboot.elf` 55.236 B `e537f9b9…b03ca73`; `ferros-user.elf` 13.600 B `2d7d4404…0e51f76`.
- `kernel.zen` combinado idéntico (`392e1eba…7fe26e`).
Toolchain: GCC 16.2.1, GNU ld 2.47, rustc/cargo 1.99.1, zen 0.1.0 release (sha256 del binario registrado).

## Límites
- No se compara bit a bit el binario Rust/Cargo del compilador (solo hash/versión).
- No es CI remoto ni fija contenedor/toolchain; no demuestra otro hardware/distro/GCC/binutils/Rust.
- Sin `.git`: sin commit/bisect/atestación; el manifiesto incluye fecha/rutas y no es byte-reproducible.
- No arranca QEMU ni valida corrección funcional (eso lo cubre la puerta/estrés); dos builds consecutivos no son una campaña.
