# Reproducibilidad local de builds — TASK-908

Fecha: 2026-11-11. Este documento describe la evidencia **local** de que dos builds consecutivos con el mismo fuente y el mismo toolchain producen los mismos artefactos en este host, y delimita lo que esa evidencia **no** demuestra. No es una certificación de build hermético ni una atestación de cadena de suministro.

El instrumento es [`infrastructure/scripts/repro_build.py`](../infrastructure/scripts/repro_build.py). Está integrado como **paso 8** de `verify_all.py` (rápida en modo normal/quick; completa con `--full`) y no escribe artefactos en el repositorio.

## Qué se verifica

| Comprobación | Método | Artefactos comparados |
|---|---|---|
| C generado determinista | `zen build <src> --emit c --release` dos veces, en ficheros `a.c`/`b.c` temporales distintos | `hello.zen`, `factorial.zen`, `arrays.zen`, `structs.zen` |
| ELF de usuario determinista | `build_user(ZEN, dir, True)` dos veces, en directorios temporales distintos | `ferros-user.elf` |
| Kernel determinista | `build_kernel(ZEN, dir, True)` dos veces, en directorios temporales distintos | `kernel.o`, `ferros-x86_64.elf`, `ferros-multiboot.elf` |
| Entradas estables | sha256 de fuentes, ensamblador, linker scripts y scripts de build; `kernel.zen` combinado de ambos builds | fuentes C, kernel (9 unidades `.zen` + `.S`/`.ld`), usuario (`main.zen`, `entry.S`, `linker.ld`), `build_ferros.py`/`build_user.py` |
| Registro | manifiesto JSON en un directorio temporal + resumen por stdout | versiones, flags, hashes, tamaños, duraciones, PASS/FAIL |

Detalles del procedimiento:

1. **Compilador.** Se exige `zen/compiler/target/release/zen` y que `zen version` declare `Compiler build: release`. Si el binario no existe, o si se pasa `--rebuild`, se construye con `cargo build --release --offline --manifest-path zen/compiler/Cargo.toml` usando un `CARGO_TARGET_DIR` y un `CARGO_HOME` temporales; el registro offline del repo se enlaza para resolver dependencias sin red. Así no se sobrescribe el target del repo y las cachés de Cargo van al home temporal. El hash del binario del compilador se registra, pero **no se compara bit a bit** entre builds.
2. **C generado.** Cada ejemplo se emite dos veces con `--release` a dos ficheros temporales (`a.c` y `b.c`). Se exige igualdad de bytes y se guarda el sha256 de cada ejecución. El C emitido no contiene rutas absolutas de origen, así que el directorio de salida no influye.
3. **Kernel y usuario.** `build_user` y `build_kernel` se invocan dos veces con `release=True` en directorios temporales distintos (run1/run2). `build_kernel` reconstruye internamente la imagen de usuario que embebe; la comparación de `ferros-user.elf` se hace sobre la invocación independiente de `build_user`. Se comparan los cuatro artefactos del contrato: `kernel.o`, `ferros-x86_64.elf`, `ferros-multiboot.elf` y `ferros-user.elf`.
4. **Comparación.** El criterio normal es **igualdad byte a byte**. Si un artefacto difiere, el script:
   - localiza el primer byte distinto,
   - calcula sha256 por sección con `readelf -SW`,
   - genera copias con `objcopy --remove-section .comment --remove-section .note.gnu.build-id` y compara el sha256 normalizado.
   Si tras quitar solo esas secciones de metadatos el contenido coincide, el artefacto se marca `PASS_METADATA` con un aviso (el contenido relevante es el mismo). Si el contenido normalizado también difiere, se marca `FAIL` y el script termina con código distinto de cero. En esta ejecución no hubo ninguna diferencia, así que la ruta de normalización no se activó.
5. **Manifiesto.** El JSON incluye `host`, `repo` (con `git: false`), `toolchain` (`cc`, `ld`, `rustc`, `cargo`), `compiler` (versión, sha256, si se reconstruyó, si está obsoleto respecto a `zen/compiler/src`), `flags`, los resultados de C y Ferros, las entradas hasheadas, tiempos, avisos, fallos y límites. Se escribe por defecto en `/tmp/zenferros-repro-*/manifest.json`; el directorio temporal se conserva para poder inspeccionar objetos, logs y ELF. `--manifest RUTA` permite elegir otra ruta (pensado para un consumidor externo; por defecto nada va al repo).

### Modos y códigos de salida

| Comando | Cobertura | Tiempo observado |
|---|---|---|
| `python3 infrastructure/scripts/repro_build.py --quick` | C + ELF de usuario; omite `kernel.o` y los dos ELF del kernel | ≈ 0,23 s |
| `python3 infrastructure/scripts/repro_build.py` | C + usuario + kernel (defecto) | ≈ 1,6–1,7 s |
| `... --rebuild` | Fuerza compilador nuevo en target temporal y repite todo | ≈ 6,7–6,9 s |
| `... --no-build` | Falla si no existe el binario release; nunca invoca cargo | — |

- `0`: todos los artefactos solicitados coinciden (o solo difieren en metadatos declarados y el contenido normalizado coincide).
- `1`: artefacto ausente/diferente, build fallido, compilador no release o error de preparación.
- `2`: error de uso de `argparse`.

## Resultados en este host

Ejecución del 2026-11-11 (hora local CET) en AMD Ryzen 7 260 w/ Radeon 780M Graphics, Linux 7.2.11-arch1-1 x86_64. Modo `full`: **PASS**, sin discrepancias; `--quick`: **PASS**.

| Herramienta | Versión |
|---|---|
| `cc` | `cc (GCC) 16.2.1 20260810` |
| `ld` | `GNU ld (GNU Binutils) 2.47` |
| `rustc` | `rustc 1.99.1 (58cf8f9c3 2026-10-13)` |
| `cargo` | `cargo 1.99.1 (5f94df478 2026-08-27)` |
| `zen` | `zen 0.1.0 (bootstrap)`, `Compiler build: release`, sha256 `5f2ed167c198e2e730ef4976da978ede76dae751fde3ec78065e6bb4367303c6` |

C generado (dos ejecuciones idénticas, `--release`):

| Fuente | Bytes | sha256 |
|---|---:|---|
| `hello.zen` | 9.582 | `06aced6c4079a27b43f98fd7fff1b215dc0f240dd7c980fc1a62b5bca642cf58` |
| `factorial.zen` | 10.412 | `fbfa09dc95697375df766cf5aca5e9fc5b6b658fd7050d76a4a975171e3aa2d8` |
| `arrays.zen` | 14.599 | `fb2bff30ecffc3eb105e65d301bbfe025d77a242efd245930ccecf8baa9e1b04` |
| `structs.zen` | 14.286 | `5ec1bbbd31dbb620b4726e5b4bf205c5667c107dd8f91474ecc0412583693301` |

Ferros release (run1 y run2 en directorios temporales distintos):

| Artefacto | Bytes | sha256 |
|---|---:|---|
| `kernel.o` | 49.168 | `31fac52715da0d7c0ca7475ed4c418cb270cad07be1ac64cd6fb9edde949a816` |
| `ferros-x86_64.elf` | 56.848 | `6e2ef29fee2ac7c492aceb22f9afaa93c1f8ba7fce8df750469aefff8742b4da` |
| `ferros-multiboot.elf` | 55.236 | `e537f9b9915135708e308b3f6eb33aeb855a1018d4139ad02a1c90086b03ca73` |
| `ferros-user.elf` | 13.600 | `2d7d4404d0223425592613f45b975aada82a5f6e4fa9c10c3e34cca061e51f76` |

El `kernel.zen` combinado de ambos builds coincidió (`392e1ebaec24487ccc7c62851c915c569cb48c60bc64a6e1a4e60cb4437fe26e`), así que la comparación de artefactos se hizo sobre las mismas entradas. Tiempos representativos: C ≈ 0,002–0,003 s por fuente (dos emisiones), usuario ≈ 0,09–0,11 s por build, kernel ≈ 0,69–0,73 s por build; total del modo completo ≈ 1,6–1,7 s. Son tiempos de build con caché de compilación y host compartido, no un benchmark.

## Qué NO se demuestra

- **Build Rust/Cargo bit a bit.** El binario del compilador Zen no se compara entre builds; solo se registra su hash y su perfil. Si `cargo build` produce binarios distintos por metadatos, rutas o versión de Rust, este script no lo detecta ni es su objetivo. Tampoco se comparan los `.rlib` ni el resto de artefactos de Cargo.
- **CI remoto, contenedor o toolchain fijado.** Todo se ejecuta en este host, con el `cc`/`ld` del sistema, el `cargo` del usuario y el registro offline de `.cargo/`. No hay imagen reproducible, ni `SOURCE_DATE_EPOCH`, ni flags de build-id/frandom-seed, ni contenedor con versiones fijadas.
- **Hardware, distro o toolchain distintos.** No se demuestra que otro CPU, kernel, glibc, GCC, binutils o Rust produzcan los mismos bytes. Cambiar `CC`, `ld`, el linker script o la versión de cualquiera de ellos puede cambiar legítimamente los hashes.
- **Procedencia VCS.** TASK-922 creó el commit local inicial `e7737a6`; no recupera historial anterior ni proporciona firma o procedencia remota. Los sha256 de las entradas registrados en el manifiesto siguen siendo evidencia del árbol construido, no una atestación firmada.
- **Manifiesto reproducible.** El JSON contiene fecha, rutas temporales, duraciones y estado de la máquina; dos manifiestos de dos ejecuciones no son idénticos byte a byte. Es un registro de evidencia, no un artefacto de release firmado.
- **Corrección en ejecución.** No se arranca QEMU ni se ejecuta el kernel o el ELF de usuario. Un build determinista puede seguir siendo funcionalmente incorrecto; eso lo cubren `verify_all.py`, `ferros/tests` y la aceptación QEMU.
- **Cobertura total de artefactos.** No se comparan individualmente los objetos intermedios (`entry.o`, `io.o`, `interrupts.o`, `context.o`, `userspace.o`, `user_image.o`, `user.o`, `user-entry.o`), los ejecutables host de los ejemplos, los binarios de benchmarks ni los artefactos de QEMU. Se comparan el C emitido y los cuatro artefactos del contrato; el resto queda cubierto de forma indirecta por los ELF enlazados.
- **Timestamps y metadatos de toolchain.** El script no fija ni normaliza timestamps, `build-id`, `.comment`, rutas de depuración ni locale del compilador. Si una versión futura de `ld`/`cc` los embebe de forma variable, el diagnóstico de secciones lo señalará, pero la reproducibilidad no está garantizada por el script.
- **Dos ejecuciones no son una campaña.** El PASS significa dos builds consecutivos en la misma sesión/host, no cientos de repeticiones, ni arranques limpios, ni builds cruzados entre máquinas.

## Foto de hashes y vigencia

Los hashes/tamaños citados en este documento corresponden a la ejecución original (2026-11-11). El compilador y Ferros han cambiado desde entonces (TASK-912/914/902J), por lo que las cifras concretas son una **foto histórica**; lo que sigue vigente es el procedimiento y el PASS de `repro_build.py` en cada corte. El manifiesto de la última ejecución prevalece.

## Relación con la puerta de calidad

[`quality.md`](quality.md) declara que la procedencia reproducible no está verificada y que la puerta es local. TASK-908 añade evidencia acotada para el build local (C generado, objeto kernel, payload, contenedor Multiboot y ELF de usuario), y está integrado como paso 8 de `verify_all.py`; no convierte el proyecto en reproducible en CI remoto. Para la puerta funcional sigue mandando:

```bash
python3 infrastructure/scripts/verify_all.py --quick
python3 infrastructure/scripts/verify_all.py
```

## Reproducir esta evidencia

Requisitos: Python 3, compilador release ya construido (o `cargo` con el registro offline cacheado en `.cargo/`), `cc`, `ld`, `objcopy`, `readelf` y `nm`.

```bash
# C + usuario, sin kernel (~0,23 s en este host)
python3 infrastructure/scripts/repro_build.py --quick

# Todo: C + usuario + kernel (~1,7 s)
python3 infrastructure/scripts/repro_build.py

# Forzar compilador nuevo en target temporal (~6,8 s con deps cacheadas)
python3 infrastructure/scripts/repro_build.py --rebuild

# Guardar el manifiesto en una ruta concreta (por defecto va a /tmp)
python3 infrastructure/scripts/repro_build.py --manifest /tmp/repro.json
```

El script fija `cwd` en la raíz del repo, no usa shell, aplica timeouts por comando y escribe todo (C, objetos, ELF, logs, manifiesto) en `/tmp/zenferros-repro-*`. La única escritura posible dentro del repo sería la de Cargo si se compilara el compilador; para evitarla, el target y el `CARGO_HOME` de esa compilación también son temporales. El directorio se conserva para inspección; con `--rebuild` incluye además el target de Cargo temporal y puede ocupar bastante espacio, así que conviene borrarlo cuando ya no haga falta.

## Mantenimiento

- Reejecutar tras cambios en `zen/compiler`, `ferros/kernel`, `ferros/user`, `ferros/boot`, los linker scripts, `build_ferros.py`, `build_user.py` o el toolchain.
- Los hashes de este documento son una **foto** de la ejecución del 2026-11-11, no constantes que el script imponga. El script comprueba autoconsistencia entre dos builds, no contra una línea base congelada; un cambio legítimo de compilador puede cambiar los hashes y seguir siendo PASS.
- Si se quiere convertir en puerta, el consumidor debe decidir si compara contra hashes esperados y si acepta `PASS_METADATA`; este script no lo hace por diseño para no ocultar cambios de toolchain.
