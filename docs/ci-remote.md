# CI remoto — workflow de GitHub Actions (TASK-918)

Fecha: 2026-11-12. Este documento describe `.github/workflows/ci.yml`, su validación local y sus límites. Git local se recuperó en TASK-922 y el **remoto configurado** es `git@github.com:ferrberr/ZenFerros.git`. El primer [run de GitHub Actions](https://github.com/ferrberr/ZenFerros/actions/runs/43195298356), sobre `d39f268`, terminó con **success** y publicó `ci-matrix-json` y `ci-matrix-logs`. Los párrafos históricos de abajo describen la plantilla antes de su primera ejecución.

## Qué haría

El workflow ejecuta la matriz local de TASK-911 (`infrastructure/scripts/ci_matrix.py`) en un runner Linux alojado y publica el resumen JSON como artefacto. No cambia ni sustituye `verify_all.py`, `stress.py` ni `repro_build.py`: solo los invoca a través de la matriz.

| Evento | Rama/condición | Modo de matriz |
|---|---|---|
| `pull_request` | cualquiera | `--quick` (4 pasos) |
| `push` | `main` | `--full` (5 pasos) |
| `workflow_dispatch` | manual | `--full` |

Secuencia de pasos del job `matriz` (runner `ubuntu-24.04`, `timeout-minutes: 45`):

1. `actions/checkout@v4` con `persist-credentials: false`.
2. `actions/setup-python@v5` con Python 3.12.
3. `python3 infrastructure/scripts/check_ci_workflow.py`: valida el propio workflow antes de gastar tiempo de runner.
4. `dtolnay/rust-toolchain@stable`.
5. `apt-get install build-essential qemu-system-x86` (GCC, `ld`, QEMU); imprime las versiones.
6. `actions/cache@v4` sobre `.cargo/registry` y `.cargo/git`, con clave por `hashFiles('zen/compiler/Cargo.lock')`.
7. `cargo fetch --locked --manifest-path zen/compiler/Cargo.toml` con `CARGO_HOME=${{ github.workspace }}/.cargo` para poblar el registro que la matriz usa con `--offline`.
8. Matriz rápida o completa según el evento, con `--json "$RUNNER_TEMP/ci-matrix.json"`.
9. Subida de `ci-matrix-json` (`${{ runner.temp }}/ci-matrix.json`) y de `ci-matrix-logs` (`/tmp/zenferros-ci-*/`) con `if: always()`, retención de 14 días.

`permissions: contents: read`, sin `secrets`, sin `pull_request_target` y con concurrencia por `github.ref` cancelando ejecuciones anteriores de la misma rama. La matriz escribe sus logs en `/tmp/zenferros-ci-*`; el runner es efímero, así que el artefacto de logs es lo que sobrevive.

## Requisitos del runner

- **Checkout con `.git`**: el workflow requiere publicar `main` en el remoto configurado antes de poder ejecutarse allí.
- **Linux x86_64** con `sudo` (los runners `ubuntu-24.04` lo tienen): GCC/`ld` de `build-essential`, QEMU de `qemu-system-x86` y Python 3.12.
- **Rust estable** con Cargo en `PATH` (lo instala `dtolnay/rust-toolchain@stable`).
- **Red la primera vez** para `cargo fetch` y para descargar las acciones. La matriz en sí usa `cargo test --offline`; si `.cargo` no está poblado, los pasos de Cargo fallan.
- **QEMU en `PATH`**: los scripts de Ferros buscan `.tools/qemu` y, si no existe, `qemu-system-x86_64` en `PATH`; el paquete de Ubuntu sirve para eso.
- **Escritura en `/tmp`** para los logs de la matriz y en `$RUNNER_TEMP` para el JSON.
- **Nada más**: no se necesitan credenciales, registros privados, servicios externos ni secretos.

## Diferencias con la matriz local

| Aspecto | Local (`ci_matrix.py`) | Remoto (workflow) |
|---|---|---|
| Host | Este equipo (AMD Ryzen 7 260, Arch, GCC 16.2.1, QEMU 11.1.3 local) | Runner `ubuntu-24.04` (GCC de Ubuntu, QEMU del paquete, Rust stable flotante) |
| Toolchain | El del sistema, solo registrado | Instalado por el workflow; versiones no fijadas por SHA |
| `CARGO_HOME` | `<repo>/.cargo`, ya poblado | `${{ github.workspace }}/.cargo`, poblado con `cargo fetch` y cacheado |
| Build cache | `target/` caliente de ejecuciones previas | Sin cache de `target/`; solo registro/git de Cargo → más lento |
| Disparo | Manual | PR, push a `main` o manual |
| Modo | El que pidas (`--quick`, defecto, `--full`) | PR → `--quick`; `main`/manual → `--full` |
| Logs | `/tmp/zenferros-ci-*` en este host | Igual en el runner efímero, subidos como artefacto |
| JSON | `--json RUTA` opcional | `--json $RUNNER_TEMP/ci-matrix.json`, siempre como artefacto |
| Qué demuestra | PASS de este host | PASS de ese runner y ese día |

La matriz es la misma; lo que cambia es el entorno. Los tiempos de [`ci.md`](ci.md) (≈60 s `--quick`, ≈100 s `--full` con caché caliente) no son extrapolables a un runner frío.

El ejemplo genérico de [`ci.md`](ci.md) dispara la matriz completa con `schedule`; este workflow la dispara en `push` a `main` y a mano, sin `schedule` (contrato de TASK-918). Los comandos, `CARGO_HOME` y el artefacto JSON coinciden; si se prefiere una pasada nocturna, basta añadir `schedule` y una condición más.

## Límites

- **Alcance de la ejecución**: el primer run remoto pasó sobre `d39f268` y publicó logs y JSON; no equivale a una campaña en varios runners o toolchains. La validación local de abajo solo comprueba la estructura del workflow.
- **Primera ejecución remota verificada.** El push de `d39f268` a `main` produjo el run `43195298356`, job `Matriz ZenFerros` con `success` y dos artefactos publicados. Véase TASK-922 para comandos y tamaños.
- **No es una atestación.** El artefacto JSON no está firmado: no hay procedencia, SBOM, firma ni cadena de suministro. Es evidencia de una ejecución, no una garantía de que el binario provenga de ese commit.
- **No fija el toolchain exacto.** `ubuntu-24.04`, `dtolnay/rust-toolchain@stable` y los tags `@v4`/`@v5` son referencias móviles. Un cambio del runner o de Rust puede cambiar resultados sin que cambie el repositorio. Para endurecerlo, fija acciones por SHA y una versión de Rust concreta.
- **No prueba otros hosts ni arquitecturas.** Un PASS en el runner no dice nada sobre Arch, GCC 16, QEMU 11 u otro hardware; y al revés.
- **No verifica que las acciones existan o se resuelvan.** Esa comprobación requiere red y queda fuera del validador; el workflow la hará (o fallará) el día que se ejecute.
- **No garantiza tiempos.** `timeout-minutes: 45` y los timeouts internos de la matriz evitan cuelgues; no son un SLA ni un presupuesto de rendimiento.
- **No cubre secretos ni despliegues.** No hay `secrets`, ni publicación de releases, ni firma, ni notificaciones; el token del job es de solo lectura (`contents: read`).
- **El artefacto de logs puede faltar.** Si la matriz falla antes de crear `/tmp/zenferros-ci-*`, la subida de logs se omite (`if-no-files-found: ignore`); el JSON se intenta subir siempre, pero también puede no existir si el fallo es anterior a la matriz (`warn`).
- **La rama `main` es una suposición.** Si el espejo usa otra rama por defecto, hay que ajustar `on.push.branches`; el validador lo detecta si el filtro no incluye `main`.

## Validación local

```bash
python3 infrastructure/scripts/check_ci_workflow.py
```

Salida esperada (resumen): `Resultado: PASS`. El script no usa red y no ejecuta el workflow: lee el YAML, lo estructura y comprueba el contrato. Con PyYAML instalado lo usa; si no está, emplea un parser mínimo de sangría incluido en el propio script (mapas, secuencias, escalares, secuencias de flujo y bloques `|`/`>`). En este host PyYAML no está instalado, así que la validación se hizo con el parser mínimo y el script lo indica en su salida.

Qué comprueba:

- claves raíz `name`, `on`, `jobs`; disparadores `push`, `pull_request` y `workflow_dispatch`, con `push` limitado a `main`;
- cada job con `runs-on` Linux, `timeout-minutes` positivo y `steps`; cada paso con `uses` o `run`;
- checkout, setup-python con versión, Rust stable, GCC/`build-essential` y QEMU;
- `CARGO_HOME` dentro del workspace, cache de Cargo con clave por `Cargo.lock` y `cargo fetch` antes de la matriz;
- `ci_matrix.py --quick` solo bajo `pull_request` y `--full` en `push`/`workflow_dispatch`, ambos con `--json` en `$RUNNER_TEMP`;
- subida de `ci-matrix.json` con `if: always()` y artefactos fuera del repositorio;
- rutas del repositorio citadas por el workflow que existan de verdad;
- ausencia de secretos hardcodeados, `pull_request_target`, permisos de escritura y acciones sin versión;
- coherencia con [`ci.md`](ci.md) y con las secciones de este documento (no ejecución, `.git`, atestación, requisitos, diferencias, límites y validación).

Códigos de salida: `0` si todo pasa, `1` si algo falla (incluido YAML ilegible o inválido), `2` si el error es de uso (raíz inexistente o backend pedido no disponible).

Opciones útiles:

```bash
# Forzar el parser mínimo y ver todas las comprobaciones
python3 infrastructure/scripts/check_ci_workflow.py --backend mini

# Validar una copia alterada (por ejemplo, tras quitar runs-on) sin tocar el repo
python3 infrastructure/scripts/check_ci_workflow.py --workflow /tmp/ci-roto.yml
```

Un fallo esperado (copia sin `runs-on` o con un `--quick` incondicional) devuelve `1` y lista las comprobaciones fallidas; eso es lo que se usó como prueba negativa. El workflow también ejecuta este validador como primer paso útil, de modo que una edición incoherente del YAML falla antes de la matriz.

## Mantenimiento

- Si cambian los scripts de `infrastructure/scripts/` o el manifiesto de Cargo, actualiza el workflow y vuelve a ejecutar el validador.
- Si cambia la rama por defecto del espejo, ajusta `on.push.branches` y el filtro de la matriz completa.
- Si se añaden pasos que invoquen rutas nuevas, el validador las comprobará automáticamente: debe ejecutarse desde la raíz del repositorio (o con `--root`), porque resuelve las rutas contra el árbol real.
- Si se instala PyYAML en el host, `--backend auto` cambiará de lector sin cambiar las comprobaciones; `--backend yaml` fuerza PyYAML y devuelve `2` si falta.

## Referencias

- [`ci.md`](ci.md): matriz local, perfiles, contrato del JSON y tiempos observados.
- [`quality.md`](quality.md): qué está verificado y con qué evidencia.
- [`reproducibility.md`](reproducibility.md): builds reproducibles y hashes locales.
- [`stability.md`](stability.md): campañas de estrés.
