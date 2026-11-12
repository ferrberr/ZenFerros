# Matriz de CI local — TASK-911

Fecha: 2026-11-12. Este documento describe `infrastructure/scripts/ci_matrix.py`, el comando único que compone las puertas locales de Zen/Ferros (compilador, `verify_all`, `stress` y `repro_build`) en una matriz por perfiles, con logs, timeouts, fallo temprano y resumen JSON.

La matriz **no es CI remoto**: es una forma reproducible de ejecutar en este host lo que ya verifican [`quality.md`](quality.md), [`stability.md`](stability.md) y [`reproducibility.md`](reproducibility.md). No sustituye a esas puertas ni las modifica; solo las ordena y registra.

## Matriz

| Paso | `--quick` | Defecto | `--full` | Timeout |
|---|:---:|:---:|:---:|---:|
| `cargo test` debug (offline) | — | ✓ | ✓ | 900 s |
| `cargo test` release (offline) | ✓ | ✓ | ✓ | 900 s |
| `verify_all.py` | `--quick` | normal | `--full` | 1200 / 1800 / 1800 s |
| `stress.py` | `--quick` | `--quick` | completo | 900 / 900 / 1800 s |
| `repro_build.py` | `--quick` | completo | completo | 600 / 900 / 900 s |

Los pasos se ejecutan en ese orden, en serie y con `cwd` en la raíz del repositorio. `--quick` tiene 4 pasos (no ejecuta el compilador en debug); el modo por defecto y `--full` tienen 5.

Comandos exactos (los construye el script; aquí se muestran sin el prefijo `env CARGO_HOME=...`):

```bash
# --quick
cargo test --offline --manifest-path zen/compiler/Cargo.toml --release
python3 infrastructure/scripts/verify_all.py --quick
python3 infrastructure/scripts/stress.py --quick
python3 infrastructure/scripts/repro_build.py --quick

# defecto: añade el test debug, la puerta normal y la repro completa
cargo test --offline --manifest-path zen/compiler/Cargo.toml
python3 infrastructure/scripts/verify_all.py
python3 infrastructure/scripts/repro_build.py

# --full: cambia la puerta a --full y el estrés a campaña completa
python3 infrastructure/scripts/verify_all.py --full
python3 infrastructure/scripts/stress.py
```

Cada paso lleva su propio timeout (holgado: los valores observados están muy por debajo) y se ejecuta con `subprocess.run(..., shell=False)`, sin interpretar una shell. Los pasos de Cargo reciben `CARGO_HOME=<repo>/.cargo`; todos reciben `PYTHONDONTWRITEBYTECODE=1` y `CARGO_TERM_COLOR=never`.

## Uso

```bash
# Matriz rápida (compilador release + puerta rápida + estrés acotado + repro rápida)
python3 infrastructure/scripts/ci_matrix.py --quick

# Matriz por defecto: añade compilador debug, puerta normal y repro completa
python3 infrastructure/scripts/ci_matrix.py

# Matriz completa: añade verify_all --full y estrés completo (~2 min)
python3 infrastructure/scripts/ci_matrix.py --full

# Exportar el resumen a JSON (ruta fuera del repositorio recomendada)
python3 infrastructure/scripts/ci_matrix.py --full --json /tmp/ci-matrix.json
```

Salidas:

- **Consola**: por paso, nombre, comando, estado, duración y últimas líneas del log; al final, tabla resumen con número, paso, estado, duración, comando abreviado y fichero de log.
- **Logs**: un fichero por paso en un directorio temporal `/tmp/zenferros-ci-*`, con cabecera (`cwd`, comando, timeout, exit y duración) y salida combinada. También se escribe `summary.json` en ese directorio.
- **JSON opcional**: `--json RUTA` escribe el mismo resumen en la ruta indicada. Se escribe también cuando la matriz falla, para que el consumidor vea los pasos ejecutados, los omitidos y el primer fallo.

El script no escribe logs, JSON ni artefactos propios en el repositorio. Los directorios de build que ya usan las herramientas (`target/`, `ferros/build/`, `benchmarks/build/`) siguen apareciendo porque los generan Cargo y los scripts de build; están declarados en `.gitignore`.

### Fallo temprano y códigos de salida

Al primer paso que falla se omite el resto (estado `SKIP`, con motivo y log), se imprime el resumen y se sale con código distinto de cero. El JSON conserva todos los pasos planificados, no solo los ejecutados.

| Código | Significado |
|---:|---|
| `0` | Todos los pasos planificados terminaron en `PASS`. |
| `1` | Un paso falló (exit distinto de cero, timeout o error al ejecutar) o no se pudo escribir el `--json`. |
| `2` | Error de uso: `--quick` y `--full` juntos, o `--json` con un destino inválido (directorio, padre no creable). Se detecta antes de ejecutar la matriz. |
| `130` | Interrupción por `Ctrl-C`; se imprime el resumen de lo ejecutado. |

Un fallo de escritura del `--json` posterior a la matriz también devuelve `1`, aunque los pasos hayan pasado: la evidencia pedida no se pudo entregar. El `summary.json` del temporal se intenta escribir siempre.

## Toolchain registrado

Antes de la matriz, el script sondea y registra `cc`, `ld`, `rustc` y `zen` (con `zen version`, que declara el perfil de build), incluyendo ruta, versión, exit y duración de la sonda. Si falta una herramienta o `zen` no declara `Compiler build: release`, se emite un aviso y se registra en el JSON; las sondas **no** son pasos de la matriz y no bloquean por sí mismas: el fallo real lo produce el paso que necesita la herramienta.

`cargo` no se sondea como parte del contrato de toolchain, pero los pasos de Cargo lo requieren en `PATH`. `zen` release puede no existir al arrancar: `verify_all` lo construye y `repro_build` lo reconstruye en un target temporal si hace falta; el aviso queda registrado.

En la ejecución de referencia (2026-11-12) el registro fue: `cc` GCC 16.2.1, `ld` GNU Binutils 2.47, `rustc` 1.99.1 y `zen` 0.1.0 (bootstrap) con `Compiler build: release`.

## Tiempos observados

Host de referencia: AMD Ryzen 7 260 w/ Radeon 780M Graphics, Linux 7.2.11-arch1-1 x86_64, 2026-11-12, host compartido y caché de compilación caliente. No es un benchmark y los tiempos varían con la carga y con el número de tests.

| Modo | Pasos | Tiempo total observado |
|---|---:|---:|
| `--quick` | 4 | 59,5–65,8 s |
| defecto | 5 | 78,5 s |
| `--full` | 5 | 1m 40,5 s–1m 54,3 s |

En la pasada final de aceptación (los comandos exactos, sin `--json`) fueron 63,9 s (`--quick`) y 108,4 s (`--full`). Desglose de una ejecución representativa:

| Paso | `--quick` | Defecto | `--full` |
|---|---:|---:|---:|
| `cargo test` debug | — | 2,79 s | 2,73 s |
| `cargo test` release | 2,42 s | 2,67 s | 2,43 s |
| `verify_all` | 30,31 s (`--quick`) | 40,01 s (normal) | 43,40 s (`--full`) |
| `stress` | 30,28 s (`--quick`) | 31,08 s (`--quick`) | 63,28 s (completo) |
| `repro_build` | 0,28 s (`--quick`) | 1,91 s (completo) | 1,97 s (completo) |

Ejecuciones anteriores del mismo día dieron 59,51 s (`--quick`) y 100,49 s (`--full`), con la misma caché: la diferencia es ruido de host y del estado de las suites. Los tiempos de `verify_all` incluyen sus propios pasos (tests, QEMU y benchmarks), no solo la puerta.

## Contrato del JSON

Ejemplo abreviado (el fichero real incluye todos los pasos y la salida de las sondas):

```json
{
  "task": "TASK-911",
  "schema": 1,
  "generated_at": "2026-11-12T00:47:00+00:00",
  "mode": "quick",
  "result": "PASS",
  "repo": { "root": "/home/usuario/ZenFerros", "git": false },
  "host": { "platform": "Linux-...", "machine": "x86_64", "processor": "..." },
  "toolchain": {
    "cc":    { "found": true, "version": "cc (GCC) ...", "path": "/usr/bin/cc", "exit": 0 },
    "ld":    { "found": true, "version": "GNU ld ...", "exit": 0 },
    "rustc": { "found": true, "version": "rustc ...", "exit": 0 },
    "zen":   { "found": true, "version": "zen 0.1.0 (bootstrap)", "release": true }
  },
  "matrix": {
    "steps": [
      {
        "number": 1,
        "name": "Compilador: cargo test release (offline)",
        "status": "PASS",
        "seconds": 2.42,
        "timeout_seconds": 900.0,
        "returncode": 0,
        "command": ["cargo", "test", "--offline", "--manifest-path", "zen/compiler/Cargo.toml", "--release"],
        "command_line": "env CARGO_HOME=... cargo test ...",
        "log": "/tmp/zenferros-ci-.../01-cargo-test-release-offline.log",
        "error": null,
        "skip_reason": null
      }
    ],
    "executed": 4,
    "passed": 4,
    "failed": 0,
    "skipped": 0
  },
  "failed_step": null,
  "total_seconds": 63.29,
  "logs": "/tmp/zenferros-ci-...",
  "warnings": [],
  "limits": ["..."]
}
```

Campos relevantes: `result` (`PASS`, `FAIL` o `INTERRUPTED`), `failed_step` (número del primer fallo o `null`), `matrix.steps[].status` (`PASS`, `FAIL`, `SKIP`) y `matrix.steps[].log`. El JSON contiene fecha, rutas temporales y duraciones, así que **no es reproducible byte a byte**; es un registro de evidencia.

## Qué NO es

- **No es CI remoto.** No hay servidor, cola, webhooks ni ejecución en la nube: se lanza a mano en este host y describe este host.
- **No usa contenedores** ni una imagen o toolchain fijados. `cc`, `ld`, `rustc`, Cargo y QEMU son los del sistema; el script solo registra sus versiones.
- **No demuestra nada sobre otros hosts.** Otro CPU, distro, glibc, GCC, binutils, Rust o QEMU pueden cambiar tiempos y resultados. Un `PASS` aquí no es un `PASS` universal.
- **No es una atestación de procedencia.** El repositorio no tiene `.git`: no hay commit, firma, SBOM ni cadena de suministro. Los hashes de `repro_build` son evidencia local, no una firma.
- **No fija umbrales de rendimiento.** Mide duración de pasos para detectar cuelgues; no compara el rendimiento de Zen con C ni declara un subsistema «Optimizado».
- **No provisiona el entorno.** Requiere un registro offline de Cargo en `.cargo/`, `cc`/`ld` del sistema y QEMU local (`.tools/qemu`) o en `PATH`. Sin ellos, los pasos que los usan fallan; la matriz no los instala.
- **No sustituye a las puertas.** `verify_all.py` sigue siendo la puerta de calidad, `stress.py` la campaña de estabilidad y `repro_build.py` la evidencia de reproducibilidad. La matriz solo las compone.
- **No admite paralelismo.** Los pasos son secuenciales; en particular, nunca hay dos QEMU en paralelo.
- **No fija los conteos de tests.** `verify_all.py` comprueba el número esperado de tests y falla si una tarea cambia la cobertura sin actualizar `EXPECTED_COUNTS`; eso es intencionado y la matriz lo propaga como fallo del paso.
- **No limpia los temporales.** Los directorios `/tmp/zenferros-ci-*` se conservan para inspeccionar logs; bórralos a mano cuando no hagan falta.

## Integración en un CI externo (ejemplo genérico)

La matriz se puede invocar desde un CI externo, pero el runner debe provisionar lo que este host ya tiene: checkout con `.git`, toolchain de Rust, `cc`/`ld`, Python 3, QEMU y el registro offline de Cargo. Este repo local no tiene `.git`, así que el YAML es una plantilla para un espejo o una copia versionada; ajústalo al sistema del runner.

```yaml
name: zenferros-ci
on:
  push:
  pull_request:
  schedule:
    - cron: "0 3 * * *"

jobs:
  matrix:
    runs-on: ubuntu-24.04
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4

      - name: Dependencias del sistema
        run: |
          sudo apt-get update
          sudo apt-get install -y build-essential python3 qemu-system-x86

      - uses: dtolnay/rust-toolchain@stable

      # La matriz usa --offline y CARGO_HOME=<repo>/.cargo: hay que poblarlo.
      - name: Provisionar registro offline de Cargo
        run: CARGO_HOME="$PWD/.cargo" cargo fetch --manifest-path zen/compiler/Cargo.toml

      - name: Matriz rápida (push y PR)
        if: github.event_name != 'schedule'
        run: python3 infrastructure/scripts/ci_matrix.py --quick --json "$RUNNER_TEMP/ci-matrix.json"

      - name: Matriz completa (nocturna)
        if: github.event_name == 'schedule'
        run: python3 infrastructure/scripts/ci_matrix.py --full --json "$RUNNER_TEMP/ci-matrix.json"

      - name: Publicar resumen JSON
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: ci-matrix-json
          path: ${{ runner.temp }}/ci-matrix.json
          if-no-files-found: warn
```

Notas para el CI externo:

- El `cargo fetch` necesita red una vez; después la matriz trabaja con `--offline`. Si el runner ya cachea `.cargo`, ese paso puede sustituirse por una caché.
- El JSON se escribe en `$RUNNER_TEMP`, nunca en el repositorio. El artefacto es evidencia de la ejecución, no una atestación firmada.
- El runner de CI no es el host de referencia: sus tiempos y versiones de toolchain serán distintos. Un fallo por timeout o por una suite ausente debe leerse con el log del paso.
- Para un CI que no sea GitHub Actions, los mismos comandos valen en cualquier runner con shell; el YAML solo ilustra el aprovisionamiento y la publicación del JSON.

## Reproducción rápida de un paso aislado

Si la matriz falla, el log del paso y el comando exacto están en el resumen y en el JSON. Para repetir un paso suelto:

```bash
CARGO_HOME="$PWD/.cargo" cargo test --release --offline --manifest-path zen/compiler/Cargo.toml
python3 infrastructure/scripts/verify_all.py --quick
python3 infrastructure/scripts/stress.py --quick
python3 infrastructure/scripts/repro_build.py --quick
```

Los detalles de cada puerta están en [`quality.md`](quality.md), [`stability.md`](stability.md) y [`reproducibility.md`](reproducibility.md).
