# TASK-908: Builds reproducibles y manifiesto de release (Fase 9)

**Agente**: 17/15
**Estado**: COMPLETADA
**Resultado**: `repro_build.py` PASS quick 0,23 s y completo 1,68 s; hashes idénticos de C, kernel.o, payload, contenedor y ELF usuario; paso 8 de la puerta.
**Dependencias**: TASK-905, TASK-907
**Archivos (propiedad exclusiva)**: `infrastructure/scripts/repro_build.py` (nuevo), `docs/reproducibility.md` (nuevo)

## Objetivo
Evidencia reproducible de build local: mismo fuente + mismo toolchain ⇒ mismos artefactos (C generado, objeto kernel, payload, contenedor, ELF usuario), con manifiesto de versiones/hashes.

## Contrato
- `repro_build.py` (sin shell, cwd raíz, timeouts, todo en tempfiles):
  1. Compila el compilador release (`cargo build --release --offline`) o lo exige ya compilado (documentar).
  2. **C determinista**: `zen build --emit c` dos veces para `zen/examples/hello.zen`, `factorial.zen`, `arrays.zen`, `structs.zen`; compara bytes y registra sha256.
  3. **Kernel/usuario deterministas**: `build_kernel`/`build_user` dos veces en directorios temporales distintos (release), compara sha256 de `kernel.o`, `ferros-x86_64.elf`, `ferros-multiboot.elf`, `ferros-user.elf`; si `ld` embebe algo variable, documenta el campo y falla si cambia el resto.
  4. Manifiesto JSON con versiones (`cc`, `ld`, `rustc`, zen), flags relevantes, hashes y resultado.
  5. Exit ≠0 si algún artefacto difiere; resumen legible.
- `docs/reproducibility.md`: qué se verifica, cómo reproducir, qué NO (build de Rust/Cargo bit a bit, entorno/CI remoto, hardware distinto, .git ausente) y límites.
- No editar verify_all.py, código, tests ni otros docs.

## Aceptación
- `python3 infrastructure/scripts/repro_build.py` → PASS en este host, con manifiesto y hashes.
- `--quick` que solo haga C+usuario (sin kernel) si el completo es lento; documentar tiempos.
- Informe: comandos, hashes representativos, tiempos, discrepancias y límites.
