# Release local 0.1.1 — Zen + Ferros

Fecha del corte: **2026-11-12, 09:28 CET**. Versión de release declarada en este
documento: **0.1.1**. El binario del compilador sigue declarando
`zen 0.1.0 (bootstrap)` y el paquete `zen-compiler` mantiene
`version = "0.1.0"` en `zen/compiler/Cargo.toml`: **0.1.1 es un corte documental
del árbol, no un cambio de versión del binario**. Este documento define qué
significa una release **local** en este workspace, qué artefactos se pueden
reproducir, qué se verificó y qué no se publica.

El corte es el árbol congelado que pasó la puerta completa con **163/43/6/166**
tests (**378** en total), **6/6** arranques QEMU en estado 33 y
`repro_build.py` completo **PASS** en 1,97 s sin discrepancias. Detalle de
cambios en [`CHANGELOG.md`](../CHANGELOG.md); madurez sin promociones en
[`docs/maturity.md`](maturity.md).

> **No es una release publicada.** No hay CI remoto ejecutado, tag, commit,
> firma, SBOM ni repositorio de artefactos. El workspace no tiene `.git`. Una
> release local es un corte documental + evidencia de una puerta ejecutada en
> este host; no es una atestación de cadena de suministro ni una promesa de
> compatibilidad.

## Qué se congela en 0.1.1

- El árbol de fuentes de `zen/`, `ferros/`, `benchmarks/`, `infrastructure/`,
  `.github/`, `docs/` y `agents/` en el estado descrito por
  [`CHANGELOG.md`](../CHANGELOG.md), **antes** de la integración PFS-en-VFS de
  TASK-919.
- La puerta de 8 pasos de [`verify_all.py`](../infrastructure/scripts/verify_all.py)
  con los conteos **163/43/6/166** y los 6 arranques QEMU de `--full`.
- Las herramientas locales: `fmt`, `lint`, `lsp`, `use`, `verify_all`,
  `repro_build`, `stress`, `ci_matrix`, `stability_campaign` y
  `check_ci_workflow`.
- El workflow remoto `.github/workflows/ci.yml` (TASK-918) como **plantilla
  validada localmente, no ejecutada**; su alcance y límites están en
  [`docs/ci-remote.md`](ci-remote.md).
- Los documentos de alcance y madurez: [`docs/quality.md`](quality.md),
  [`docs/maturity.md`](maturity.md), [`docs/reproducibility.md`](reproducibility.md),
  [`docs/stability.md`](stability.md), [`docs/stability-campaign.md`](stability-campaign.md),
  [`docs/ci.md`](ci.md) y [`docs/ci-remote.md`](ci-remote.md).

No se versionan binarios ni artefactos de build: `target/`, `ferros/build/` y
`benchmarks/build/` están en `.gitignore`. La release se reconstruye; el valor
está en la evidencia y en la reproducibilidad local, no en un tarball firmado.

## Corte antes de TASK-919 (PFS-en-VFS → 0.1.2)

TASK-919 (ZENFS01 visible desde VFS y shell, read-only) estaba **en curso**
durante el corte y, después de congelarlo, el árbol cambió en
`ferros/kernel/vfs.zen`, `ferros/kernel/storage_fs.zen`, `ferros/kernel/main.zen`,
`infrastructure/scripts/boot_ferros.py`, tests de Ferros y docs (TASK-919).
Las anclas de la tabla siguiente son del **corte 0.1.1**, no del árbol posterior;
este último eleva Ferros a 44 tests. Por contrato, 0.1.1 se corta
**antes** de ella:

- En este corte PFS solo se anuncia al arrancar (`PFS: BOOT n FILES=n`, tras
  `PERSIST: BOOT n`) y su API interna (`pfs_find/create/write/read/delete/list`)
  existe en el kernel, pero **no está montado en VFS ni es legible por el
  shell**: `ls` sigue mostrando solo los archivos de RAMFS.
- No hay FS read-only expuesto al usuario, ni monturas, `unlink`, permisos por
  usuario, journaling ni atomicidad; RAMFS sigue siendo volátil.
- PFS-en-VFS se documentará y verificará en **0.1.2** cuando TASK-919 cierre
  con su propia puerta y conteos. Este documento no adelanta ese resultado.

## Toolchain de referencia

| Herramienta | Versión observada el 2026-11-12 |
|---|---|
| `cc` | `cc (GCC) 16.2.1 20260810` |
| `ld` | `GNU ld (GNU Binutils) 2.47` |
| `rustc` | `rustc 1.99.1 (58cf8f9c3 2026-10-13)` |
| `cargo` | `cargo 1.99.1 (5f94df478 2026-08-27)` |
| `zen` | `zen 0.1.0 (bootstrap)`, release, backend C11 vía `cc` |
| QEMU | 11.1.3 local en `.tools/qemu` (versiones/URL/SHA256 fijados), TCG, `-smp 1` |
| Python | 3.14.8 |

Requisitos: Linux x86_64, Python 3, Rust/Cargo con el registro offline en
`.cargo/`, `cc`/`ld`/binutils, QEMU local (o en `PATH`) y `nm`, `objcopy`,
`readelf` para la evidencia de reproducibilidad.

## Artefactos reproducibles

`repro_build.py` compara **dos builds consecutivos** con el mismo fuente y el
mismo toolchain en directorios temporales distintos. Criterio normal: igualdad
byte a byte; si solo difieren `.comment`/`build-id`, se marca `PASS_METADATA`
con aviso. La ejecución de referencia del corte fue **PASS** en **1,97 s**, con
los cuatro artefactos de Ferros y el C generado idénticos, sin
`PASS_METADATA` ni discrepancias.

### C generado (`zen build --emit c --release`)

| Fuente | Bytes | sha256 (idéntico en run1/run2) |
|---|---:|---|
| `zen/examples/hello.zen` | 12.215 | `d94caed018c5cfe54c39b1e5d3d29442c7bcd48321e6682a3fd47b1796cb0388` |
| `zen/examples/factorial.zen` | 13.045 | `d68e27b04880eefd1e027215b7c5514fa1cd8bd6f5afeb5e813c1fdbbe9162b0` |
| `zen/examples/arrays.zen` | 17.232 | `8d6f736383bc17750c356c9e13cf9036f2a9cdc7ec677c5fcc0f63d4c8ebe624` |
| `zen/examples/structs.zen` | 16.919 | `17894dacdc153b6c0ccfbc3252c63c6b347e854035007ee1c8a0bb48f9f7691d` |

### Ferros release

| Artefacto | Bytes | sha256 (idéntico en run1/run2) |
|---|---:|---|
| `kernel.o` | 55.520 | `2bc353afcaa02865f814e64553a0e4621f0644779d262215573f80d01d1bb4e7` |
| `ferros-x86_64.elf` | 61.288 | `7f9da40a8898da441bef3f59f4fa39876a27e05db9fae7c982a26ed9601eb933` |
| `ferros-multiboot.elf` | 59.600 | `081a6d4a7999679da65cab78f0b5117037f7873e4c733f6da45885a35eedc197` |
| `ferros-user.elf` | 13.600 | `2d7d4404d0223425592613f45b975aada82a5f6e4fa9c10c3e34cca061e51f76` |

El `kernel.zen` combinado de ambos builds coincidió
(`302e2ead139042544a8374c0a5958a5bea9b6091059beccfada35406aaa6ed09`), de modo
que la comparación se hizo sobre las mismas entradas. El binario Rust del
compilador se registra
(`290c54997a3013e20aacb7ae2bb251589feee20cc8ff023e785ac7a31fc6619f`,
1.337.784 B en el corte) pero **no se compara bit a bit** entre builds y su
hash no es estable entre recompilaciones (ver `docs/reproducibility.md`).

### Anclas de fuente del corte

| Fichero | sha256 |
|---|---|
| `infrastructure/scripts/verify_all.py` | `08392603f4783855982d0b667724b28a667d6a2ecd6aaea9b0e38106a9b4bc67` |
| `infrastructure/scripts/build_ferros.py` | `b9fa238bc682d142284264636b9d7001d7b74a78c351f73633e69da373c3249a` |
| `infrastructure/scripts/boot_ferros.py` | `a8031c45f9b055d0bf9dd9e96372acede77101b32fc804a55fe8100aa1106a74` |
| `ferros/kernel/main.zen` | `afa7aa491700997696a53d54c2d4c36f9df1ab84c9590688b8b7b1b807284599` |
| `ferros/kernel/storage_fs.zen` | `d561b0e84bde1f3e4154f2d48bed892b354dc40c8551c1941f6c8a4dd0d40cd7` |
| `ferros/kernel/vfs.zen` | `7013cecede96f055ead6bf95bb8a402185b263dd7ed3e2d0271e75471ec61a37` |
| `ferros/kernel/userspace.zen` | `ad2f214f9a5d48a2a4063b83dbff36ef03aa477873755369a8d30dbdf34187bd` |
| `ferros/user/main.zen` | `0bea79f76eb7de6fdd842b82a698fd2060303a0cdf4723bb1e1eef03a22dc916` |

Estas anclas identifican el corte **pre-TASK-919**. Si el árbol cambia (por
ejemplo, cuando TASK-919 integre PFS en VFS), los hashes de sus ficheros
cambiarán y la release vigente será 0.1.2, no esta.

### Qué significa (y qué no)

- **Sí**: en este host y con este toolchain, dos builds consecutivos del mismo
  árbol producen los mismos bytes para el C generado y los cuatro artefactos de
  Ferros.
- **No**: builds herméticos, `SOURCE_DATE_EPOCH`, contenedor fijado, otro
  CPU/distro/glibc/GCC/binutils/Rust, ni el binario del compilador bit a bit.
- **No**: corrección funcional. Un build determinista puede ser incorrecto; eso
  lo cubren la puerta, las suites y QEMU.
- Los hashes son una **foto** del corte, no constantes que el script imponga. Un
  cambio legítimo de fuente o toolchain cambia los hashes y puede seguir siendo
  PASS.
- **Persistencia del manifiesto**: el JSON completo se escribió fuera del
  repositorio, en la ruta de `--manifest` de la ejecución. En este host `/tmp`
  es un tmpfs que se remonta entre invocaciones, así que el manifiesto no
  persiste; las tablas anteriores transcriben sus valores.

> Nota de vigencia: [`docs/reproducibility.md`](reproducibility.md) conserva una
> foto del 2026-11-11 con hashes y tamaños de una revisión anterior del C
> generado. Para esta release prevalecen los valores de las tablas anteriores,
> que salen del manifiesto del corte 0.1.1 (2026-11-12).

## Comandos de la release

```bash
# 1. Compilador release
CARGO_HOME="$PWD/.cargo" cargo build --release --offline \
  --manifest-path zen/compiler/Cargo.toml
./zen/compiler/target/release/zen version
# zen 0.1.0 (bootstrap) / Compiler build: release (0.1.1 es el corte documental)

# 2. Puerta completa: 8 pasos, 163/43/6/166, 6 arranques QEMU
python3 infrastructure/scripts/verify_all.py --full

# 3. Reproducibilidad completa (C + usuario + kernel)
python3 infrastructure/scripts/repro_build.py --manifest /tmp/repro.json

# 4. Estrés acotado y campaña repetida
python3 infrastructure/scripts/stress.py --quick
python3 infrastructure/scripts/stability_campaign.py --rounds 1 --json /tmp/campaign.json

# 5. Matriz local (compone las puertas anteriores)
python3 infrastructure/scripts/ci_matrix.py --quick --json /tmp/ci-quick.json
python3 infrastructure/scripts/ci_matrix.py --full  --json /tmp/ci-full.json

# 6. Validación estructural del workflow remoto (no lo ejecuta)
python3 infrastructure/scripts/check_ci_workflow.py
```

La puerta `--full` del corte ejecutó en **1m 09,0 s** (host compartido, caché
caliente): 8/8 PASS, 6/6 arranques QEMU con estado 33, `writes=18`, `runs=7`,
`rejected=6`, `PFS: BOOT 1 FILES=1`, benchmarks con checksum verificado antes de
medir (la suite incluye además un caso negativo que aborta al detectar un
checksum distinto) y reproducibilidad sin discrepancias. Es un tiempo de puerta,
no un benchmark.

## Matriz CI local y workflow remoto

`ci_matrix.py` no es CI remoto: ordena en serie las puertas locales y registra
logs y JSON. La composición es la de [`docs/ci.md`](ci.md):

| Paso | `--quick` | Defecto | `--full` |
|---|:---:|:---:|:---:|
| `cargo test` debug (offline) | — | ✓ | ✓ |
| `cargo test` release (offline) | ✓ | ✓ | ✓ |
| `verify_all.py` | `--quick` | normal | `--full` |
| `stress.py` | `--quick` | `--quick` | completo |
| `repro_build.py` | `--quick` | completo | completo |

Modos: **4 pasos** en quick, **5** en defecto y **5** en full. Los pasos son
secuenciales y nunca hay dos QEMU en paralelo. Un fallo detiene la matriz, deja
los pasos restantes en `SKIP` y escribe el resumen parcial. El JSON contiene
fecha, rutas temporales y duraciones: es evidencia, no un artefacto
byte-reproducible.

La matriz no fija umbrales de rendimiento ni sustituye a las puertas; solo las
compone. Su referencia de aceptación es TASK-911 (65,8 s quick y 114,3 s full en
este host, 2026-11-12). La matriz no forma parte del PASS del corte: se apoya en
la evidencia de TASK-911 y hay que releerla si el árbol cambia (por ejemplo, si
otra tarea añade tests sin actualizar `EXPECTED_COUNTS`, el paso de la puerta
falla por conteo, como debe).

**Workflow remoto (TASK-918).** `.github/workflows/ci.yml` es una plantilla de
GitHub Actions que invoca `ci_matrix.py` (`--quick` en PR, `--full` en `main` y
manual) y publica el JSON/logs como artefactos. **No se ha ejecutado nunca en
GitHub**: no hay `.git`, remoto ni push. Su validación es local y estructural:
`check_ci_workflow.py` → **44/44 comprobaciones PASS** (2026-11-12), incluidas
`runs-on`, toolchain, QEMU, `cargo fetch --locked`, rutas existentes, ausencia de
secretos/`pull_request_target` y `permissions: contents: read`. Detalles y
límites en [`docs/ci-remote.md`](ci-remote.md).

## Campaña de estabilidad

| Comando | Cobertura | Resultado de referencia |
|---|---|---|
| `stress.py --quick` | 2 arranques QEMU, 1 ronda de Ferros, 1 de selfhost, 20+20 casos de fuzz | PASS, 38,75–39,59 s en el corte |
| `stress.py` | 6 arranques, 2+2 rondas, 200+200 casos de fuzz | PASS, 1m 17,7 s en el corte |
| `stability_campaign.py --rounds 5` | 5 × `stress --quick` | **PASS, 3m 15,1 s**; 10/10 arranques, 10/10 suites, 100+100 casos de fuzz |
| `stability_campaign.py --rounds 2 --mode full` | 2 × (`stress` completo + `verify_all --full`) | **PASS, 4m 17,4 s**; stress 12/12 + gate 12/12 estado 33, 4/4 suites |

En el corte 0.1.1 se ejecutó **2 rondas full** (2/2 PASS, 257,4 s) con
`warnings: []`: stress 12/12 arranques y gate 12/12 con estado 33, 4/4 suites,
fuzz parser 400 casos (200 válidos/200 con error) y lexer 400 (318 comparadas,
80 omitidas, 2 toleradas UTF-8). También se ejecutó la campaña quick de 5 rondas
sobre el mismo corte: **5/5 PASS** en 195,1 s, 10/10 arranques, 10/10 suites,
parser 100 (45 válidos/55 con error) y lexer 100 (75 comparadas, 20 omitidas, 5
toleradas UTF-8), `warnings: []`.

Evidencia histórica del mismo día, sobre un corte inmediatamente anterior:
**TASK-917** ejecutó 10 rondas quick PASS (10/10 arranques, 10/10 suites, 400,1 s)
y 3 rondas full PASS (stress 12/12 + gate 12/12 estado 33, 394,0 s), más un gate
final 8/8 en 51,70 s y un estrés completo en 77,3 s
([`agents/reports/TASK-917.md`](../agents/reports/TASK-917.md)). Se cita como
evidencia histórica, no como medición byte a byte del corte 0.1.1.

La campaña **no demuestra estabilidad**: host compartido, semilla fija, sin
inyección de fallos real, sin cobertura y sin horas de ejecución. Por eso no
cambia el nivel de madurez de [`docs/maturity.md`](maturity.md).

## Checklist de release 0.1.1

- [x] Corte documentado en **2026-11-12, 09:28 CET**, antes de TASK-919.
- [x] `zen version` declara `0.1.0` y `Compiler build: release`; 0.1.1 es el corte documental (no se cambia `Cargo.toml`).
- [x] `cargo test` release: **163/163** (34 unitarios + 129 en 11 binarios de integración).
- [x] Ferros: **43/43** tests host/QEMU.
- [x] Benchmarks: **6/6** tests del arnés.
- [x] Self-hosting: **166/166** tests de los once componentes.
- [x] `verify_all.py --full`: **8/8 PASS** en 1m 09,0 s, sin `skipped`, y **6/6** arranques QEMU estado 33 con transcripción y `writes=18`.
- [x] `repro_build.py` completo: **PASS** en 1,97 s, cuatro artefactos idénticos, sin discrepancias.
- [x] Campaña al corte: **2/2 rondas full PASS** (4m 17,4 s) y **5/5 rondas quick PASS** (3m 15,1 s); campaña ampliada histórica de TASK-917.
- [x] Workflow remoto validado localmente: `check_ci_workflow.py` **44/44 PASS**; **no ejecutado en GitHub**.
- [x] Documentos de release, madurez y changelog enlazados y revisados.
- [x] Conteos canónicos comprobados contra el árbol del corte y contra `EXPECTED_COUNTS` (163/43/6/166).
- [ ] **PFS visible en VFS/shell**: no incluido; TASK-919 es posterior y queda para 0.1.2.
- [ ] **Publicación, tag o firma**: no aplica; no hay `.git`, registro ni CI remoto.
- [ ] **CI remoto ejecutado**: no disponible; el workflow es una plantilla validada solo en estructura.
- [ ] **Garantía de compatibilidad**: no se promete; es un corte 0.1.1 local.

## Límites de la release

- **Local y de un solo host.** Un PASS no es universal: otro CPU, distro, glibc,
  GCC, binutils, Rust o QEMU pueden cambiar resultados y tiempos.
- **Sin procedencia VCS.** No hay `.git`: no hay commit, tag, bisect, firma ni
  historial. Los sha256 del manifiesto identifican artefactos, no un commit.
- **Sin publicación ni artefacto firmado.** El JSON y los logs son evidencia de
  ejecución; no son una atestación de cadena de suministro.
- **Sin CI remoto ejecutado.** `ci_matrix.py` se lanza a mano en este host y
  describe este host; el workflow de TASK-918 no ha corrido en GitHub y sus
  acciones/runner son referencias móviles. No usa contenedores herméticos.
- **Sin FS persistente visible en VFS/shell ni read-only de usuario.** RAMFS es
  volátil; ZENFS01 persiste archivos pero solo se anuncia al arrancar y no está
  montado. PFS-en-VFS (TASK-919) queda para 0.1.2; no hay journaling,
  atomicidad, permisos, monturas ni `unlink`.
- **Sin rendimiento garantizado.** Los benchmarks son línea base con paridad
  aproximada Zen/C/C++ (mismo backend C11); no hay ranking ni mejora declarada.
- **Sin estabilidad certificada.** La campaña es acotada; `Estable` y
  `Optimizado` no se declaran (ver [`docs/maturity.md`](maturity.md)).
- **Sin hardware físico, KVM, SMP, UEFI/ISO.** Todo es QEMU TCG con `-smp 1`.
- **Sin stdlib amplia ni self-hosting completo.** Solo builtins de strings,
  slices como parámetro y siete funciones en `zen/std/core.zen`; el compilador
  sigue en Rust y los once componentes selfhost son parciales.
- **Sin promesa de compatibilidad.** 0.1.0 queda como corte histórico
  (151/39/6/147, [`CHANGELOG.md`](../CHANGELOG.md)); 0.1.1 reemplaza su
  evidencia vigente, no su historia.

## Anexo: corte 0.1.0 (histórico)

La release 0.1.0 se cerró el **2026-11-12, 08:16 CET** y no incluía TASK-915,
TASK-916, TASK-917, TASK-918 ni TASK-919: **151/39/6/147** tests, gate 8/8
en ~46,9 s y reproducibilidad completa PASS en 1,89 s. Sus hashes no son los del
árbol 0.1.1 y **no deben compararse** con los de este documento; se transcriben
solo como archivo histórico del corte (detalle y contexto en
[`CHANGELOG.md`](../CHANGELOG.md)):

| Artefacto 0.1.0 | Bytes | sha256 |
|---|---:|---|
| `hello.c` | 12.080 | `356652e385cb443d3ffaae2fb0fb394411a9201f49602a6e5ad25939dded5e47` |
| `factorial.c` | 12.910 | `639ecbd9d350f88568cc788d021bdc7208a15616d38858cca9fc6a16d59b5f49` |
| `arrays.c` | 17.097 | `c51804758a00c82efeb5e28786dc9856dd83080e3c723a4f43e5dfc64b72accb` |
| `structs.c` | 16.784 | `a6c523a56d2976e34ae2107ff7c550cca03f42332ea921a9b5a7ea20eca03313` |
| `kernel.o` | 51.504 | `25d3684f9d8fe2bd61920419522c774f147f31a8c7ff99385bc46c27a8549179` |
| `ferros-x86_64.elf` | 57.016 | `6b07272d0de54cb6ed728aabbfc34c5827c30abd2ca7299a22dc01c575b056fe` |
| `ferros-multiboot.elf` | 55.368 | `e7aaac9b9b0737fb8394499c86622660a087cb8745105f12d9f5ce7933ca4a7b` |
| `ferros-user.elf` | 13.600 | `2d7d4404d0223425592613f45b975aada82a5f6e4fa9c10c3e34cca061e51f76` |

El `ferros-user.elf` de 0.1.0 coincide byte a byte con el de 0.1.1; el resto
cambió con slices, mini-FS/C y los `.zen` del kernel. Esta tabla no demuestra
reproducibilidad de 0.1.0 contra el árbol actual: es un archivo.
