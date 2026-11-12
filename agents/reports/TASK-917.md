# TASK-917 — Campaña de estabilidad ampliada (evidencia real)

**Agente**: 14/17 · **Fecha**: 2026-11-12 (Europe/Madrid) · **Árbol**: `/home/ferranfg/proyectos/ZenFerros` (sin `.git`)
**Propiedad**: solo se creó este informe; no se modificó código, tests, scripts, gate, docs ni `STATE.md`.
**Veredicto**: las cuatro ejecuciones definitivas terminan **PASS** sobre un corte estable del árbol. La evidencia respalda **estabilidad acotada** (repetición bajo condiciones fijas), **no** una certificación ni la promoción automática a *Estable*.

## 1. Entorno y método

- Host `archfer`, Linux 7.2.11-arch1-1 x86_64, 16 CPU, 30 GiB, Python 3.14.8.
- QEMU 11.1.3 local (`.tools/qemu`), `-machine pc,accel=tcg -cpu qemu64 -smp 1`, sin KVM ni metal.
- Host compartido: durante la ventana había otras tareas del repositorio en paralelo; los tiempos no son benchmark.
- `stress.py` con semilla fija 905; los QEMU se ejecutan siempre en secuencia (nunca dos a la vez).
- Horas locales Europe/Madrid; los JSON de campaña registran UTC (08:00:47Z = 09:00:47 local).
- Los directorios de logs viven en `/tmp`. En este entorno `/tmp` es un tmpfs que se **remonta entre invocaciones**: los `/tmp/zenferros-*` y los JSON dejaron de existir al terminar cada comando. Por eso el informe transcribe la salida literal y las rutas anunciadas, sin enlaces persistentes.

## 2. Corte temporal (TASK-916 en paralelo)

TASK-916 (mini-FS persistente) modificó Ferros durante el primer intento. El corte definitivo se fijó cuando el árbol se estabilizó (TASK-916 `COMPLETADA`, gate actualizado a 43 tests de Ferros).

| Momento | Hora | Evidencia |
|---|---|---|
| Corte inicial (intento 1) | 08:52:10 | `verify_all.py` `8c09e161…`, `main.zen` `8b527595…`, sin `storage_fs.zen` |
| Cambio TASK-916 | 08:54:05–09:00:29 | `build_ferros.py`/`main.zen` 08:54:05; `boot_ferros.py` 08:54:24; `test_boot.py`/`test_shell.py` 08:55:55; `test_pfs.py` 08:57:19; `verify_all.py` con `EXPECTED_COUNTS[3]=43` a las 08:59:21; informe TASK-916 a las 09:00 |
| Corte estable (definitivo) | 09:00:47–09:16:25 | hashes de abajo; ningún fichero de `ferros/`, `zen/` o `infrastructure/` (fuera de `build/` y `target/`) cambió después de las 09:00:47; en `agents/` solo el cierre de TASK-916 (09:00:29) y este informe |

Hashes del corte usado por las cuatro ejecuciones definitivas:

```text
08392603f4783855982d0b667724b28a667d6a2ecd6aaea9b0e38106a9b4bc67  infrastructure/scripts/verify_all.py
b945a035062f034dd521f2c7a5976e32a43ae45f2a310b067b51a2a171da7aa3  infrastructure/scripts/stress.py
696f07f891e730e0590dff2f640f2c1e01091402156e8caad6de04b57900b61c  infrastructure/scripts/stability_campaign.py
b9fa238bc682d142284264636b9d7001d7b74a78c351f73633e69da373c3249a  infrastructure/scripts/build_ferros.py
a8031c45f9b055d0bf9dd9e96372acede77101b32fc804a55fe8100aa1106a74  infrastructure/scripts/boot_ferros.py
afa7aa491700997696a53d54c2d4c36f9df1ab84c9590688b8b7b1b807284599  ferros/kernel/main.zen
2099c8d9bb09be14143c07e7c11148274f21dce2a67988f444705cde5cacaa24  ferros/kernel/storage_fs.zen
2fc1ff00a81e41b9d1295be0a8a7aa876d09f7c12972998f52e488c698cd21ce  ferros/tests/test_pfs.py
422489506e7ff0aa86120964fa7d7dcf31038fa4b02418b56ff0bb7584e6c708  ferros/tests/test_boot.py
b766b8d66bbe809bffc7ef531b634bf7513b562b4dfc3a815c4f4ff4f8a2a985  ferros/tests/test_shell.py
c90a88a81bbea1e922ed5bcb1be10b71d3292bfd7e6c0b4e2698804b2ce701ca  zen/selfhost/lexer.zen
61d89c7b551e1d989349a99bdf5757b80e94b31bc6e5fa085781b4a1e53d252b  zen/selfhost/parser.zen
```

## 3. Intento 1 (descartado por deriva, no es PASS)

Ejecución lanzada a las 08:52:14 con el corte inicial. Paró en la ronda 4, como está diseñado (parada al primer fallo), cuando TASK-916 estaba reescribiendo Ferros:

```text
== Ronda 4/10 ==
  stress (quick): FAIL (28.70s, exit 1)
  metricas: boots 2/2, suites 0/1, fuzz parser - (-/-), lexer - (- comparadas, - omitidas, - toleradas)
  Ronda 4: FAIL (28.70s)
  detalle: ... fase fallida: Suite Ferros (1 ronda(s)): `/usr/bin/python3 -B -m unittest discover -s ferros/tests` salio con 1; log: /tmp/zenferros-stress-l6wo6k7m/logs/suites/ferros-01.log
  Rondas: 3/4 PASS (1 fallidas) · total 2m 18.7s (stress 2m 18.7s, gate 0.00s)
  QEMU: stress 8/8 · gate 0/0 · suites 6/7
  Resultado: FALLO
# fin 2026-11-12T08:54:32+01:00 exit=1
```

Causa: la suite corrió hacia las 08:54:07–08:54:33, mientras `main.zen` (con `pfs_boot()`), `build_ferros.py` y `boot_ferros.py` (con la línea `PFS:`) cambiaban y `ferros/build` se reconstruía a las 08:54:30; los tests aún no estaban adaptados. El texto concreto de `unittest` se perdió con el remontaje de `/tmp`. **No se cuenta como fallo del producto ni como PASS**: se descarta por deriva del árbol y se repite sobre el corte estable. Los 3/4 PASS previos tenían 2/2 boots y 2/2 suites por ronda.

## 4. Ejecuciones definitivas (todas sobre el corte de §2)

| # | Ejecución | Comando | Inicio–fin | Exit | Resultado | Duración |
|---|---|---|---|---|---:|---|
| 1 | Campaña 10 rondas quick | `python3 infrastructure/scripts/stability_campaign.py --rounds 10 --json /tmp/campaign-10.json` | 09:00:47–09:07:28 | 0 | **10/10 PASS** | 6m 40,1 s |
| 2 | Campaña 3 rondas full | `python3 infrastructure/scripts/stability_campaign.py --rounds 3 --mode full --json /tmp/campaign-full-3.json` | 09:07:33–09:14:07 | 0 | **3/3 PASS** | 6m 34,0 s |
| 3 | Gate final | `python3 infrastructure/scripts/verify_all.py --full` | 09:14:09–09:15:01 | 0 | **8/8 PASS** | 51,70 s |
| 4 | Estrés final | `python3 infrastructure/scripts/stress.py` | 09:15:05–09:16:22 | 0 | **PASS** (6/6 fases) | 1m 17,3 s |

### 4.1 Campaña 10 × quick

Rondas 10/10 PASS, 0 fallidas; total 400,072 s. `warnings: []`. Notación: parser = casos (válidos/con error); lexer = mutaciones (comparadas/omitidas/toleradas UTF-8).

| Ronda | Estado | Duración | Boots 33 | Suites | Fuzz parser | Fuzz lexer |
|---:|---|---:|---:|---:|---|---|
| 1 | PASS | 40,03 s | 2/2 | 2/2 | 20 (9/11) | 20 (15/4/1) |
| 2 | PASS | 39,98 s | 2/2 | 2/2 | 20 (9/11) | 20 (15/4/1) |
| 3 | PASS | 39,98 s | 2/2 | 2/2 | 20 (9/11) | 20 (15/4/1) |
| 4 | PASS | 39,93 s | 2/2 | 2/2 | 20 (9/11) | 20 (15/4/1) |
| 5 | PASS | 40,26 s | 2/2 | 2/2 | 20 (9/11) | 20 (15/4/1) |
| 6 | PASS | 39,98 s | 2/2 | 2/2 | 20 (9/11) | 20 (15/4/1) |
| 7 | PASS | 39,89 s | 2/2 | 2/2 | 20 (9/11) | 20 (15/4/1) |
| 8 | PASS | 39,99 s | 2/2 | 2/2 | 20 (9/11) | 20 (15/4/1) |
| 9 | PASS | 40,06 s | 2/2 | 2/2 | 20 (9/11) | 20 (15/4/1) |
| 10 | PASS | 39,98 s | 2/2 | 2/2 | 20 (9/11) | 20 (15/4/1) |

Agregado: QEMU **20/20** (`default` debug y `sin-entrada` release, 2 guiones por ronda), suites **20/20** (2 fases por ronda: Ferros y selfhost), fuzz parser 200 casos (90 válidos, 110 con error), lexer 200 mutaciones (150 comparadas, 40 omitidas, 10 toleradas UTF-8 — 1 por ronda). Logs anunciados: `/tmp/zenferros-campaign-m0ajgyvu`; JSON: `/tmp/campaign-10.json`.

### 4.2 Campaña 3 × full (stress completo + gate `--full` por ronda)

| Ronda | Estado | Total | Stress | Gate | Boots stress 33 | Boots gate 33 | Suites | Fuzz parser | Fuzz lexer |
|---:|---|---:|---:|---:|---:|---:|---:|---|---|
| 1 | PASS | 2m 12,6 s | 1m 19,6 s | 53,02 s | 6/6 | 6/6 | 2/2 | 200 (100/100) | 200 (159/40/1) |
| 2 | PASS | 2m 11,2 s | 1m 19,2 s | 51,97 s | 6/6 | 6/6 | 2/2 | 200 (100/100) | 200 (159/40/1) |
| 3 | PASS | 2m 10,2 s | 1m 18,2 s | 52,02 s | 6/6 | 6/6 | 2/2 | 200 (100/100) | 200 (159/40/1) |

Totales: 3/3 rondas PASS, 394,02 s (stress 237,013 s, gate 157,003 s), **QEMU 18/18 en stress y 18/18 en gate, todas estado 33**, suites 6/6, fuzz parser 600 (300 válidos, 300 con error), lexer 600 (477 comparadas, 120 omitidas, 3 toleradas). `warnings: []`. Gate verificado con `gate-log:05-ferros.log` en cada ronda. Logs: `/tmp/zenferros-campaign-rtfwayt3`; JSON: `/tmp/campaign-full-3.json`; directorios de gate: `/tmp/zenferros-verify-d1gt5lh5`, `/tmp/zenferros-verify-5mmu2ti_`, `/tmp/zenferros-verify-ye04psgx`.

### 4.3 `verify_all.py --full` final

| # | Paso | Estado | Duración |
|---:|---|---|---:|
| 1 | Compilador: build release (offline) | PASS | 0,03 s |
| 2 | Compilador: tests release (offline) | PASS | 3,09 s |
| 3 | Ferros: tests host y QEMU | PASS | 27,10 s |
| 4 | Benchmarks: tests del arnés | PASS | 2,07 s |
| 5 | Ferros: aceptación QEMU (6 arranques) | PASS | 4,36 s |
| 6 | Benchmarks: medición rápida (reps=3, warmup=1) | PASS | 4,75 s |
| 7 | Self-hosting: tests de `zen/selfhost/tests` | PASS | 8,33 s |
| 8 | Reproducibilidad: C generado + Ferros | PASS | 1,96 s |

**8/8 PASS**, TOTAL 51,70 s. Conteos observados: `Ran 43 tests` (Ferros), `Ran 6 tests` (benchmarks), `Ran 166 tests` (selfhost); el paso 2 pasa con el conteo esperado de 163 del compilador. Aceptación QEMU 6/6 (`--all --repeat 3`), estado 33. Logs anunciados: `/tmp/zenferros-verify-0x6qcsi7` (p. ej. `03-ferros.log`, `05-ferros.log`, `07-self-hosting.log`).

### 4.4 `stress.py` completo final

| Fase | Estado | Duración | Detalle |
|---|---|---:|---|
| Build kernel (debug+release) | PASS | 1,30 s | QEMU 11.1.3 |
| Arranques QEMU (6) | PASS | 4,92 s | 6/6 estado 33; `default` con `runs=7 writes=18 rejected=6` |
| Suite Ferros (2 rondas) | PASS | 53,81 s | 43 tests por ronda (26,98 s / 26,83 s) |
| Suite selfhost (2 rondas) | PASS | 16,56 s | 166 tests por ronda (8,22 s / 8,34 s) |
| Fuzz parser (200) | PASS | 0,09 s | 100 válidas, 100 con error |
| Fuzz lexer (200) | PASS | 0,63 s | 159 comparadas, 40 omitidas, 1 tolerada UTF-8 |

**PASS**, TOTAL 1m 17,3 s; sin `PANIC` ni `stderr`. Logs: `/tmp/zenferros-stress-hg021wse`; resumen: `/tmp/zenferros-stress-hg021wse/summary.json`.

## 5. Agregado de la ventana definitiva

- **13 rondas de campaña** (10 quick + 3 full), todas PASS; 68 arranques QEMU (20 quick + 18 stress full + 18 gate full + 6 gate final + 6 stress final), **68/68 con estado 33**, 0 `PANIC` y 0 `stderr`.
- Suites sin fallos en todas las rondas: Ferros **43** tests, selfhost **166**, benchmarks **6**, compilador **163** (según el gate).
- **1.000 expresiones** de fuzz del parser (490 válidas, 510 con error) y **1.000 mutaciones** del lexer (786 comparadas, 200 omitidas, 14 toleradas UTF-8), sin discrepancias no toleradas.
- Tiempo efectivo de las cuatro ejecuciones: ≈ 923 s (≈ 15m 23s).

## 6. Conclusión honesta: qué respalda y qué no

**Respalda**, para el corte exacto de §2: que el árbol pasa de forma repetida y sin flakes la puerta completa (8/8) y el estrés acotado; que los conteos 163/43/6/166 se mantienen; que los 68 arranques QEMU llegan a estado 33 con las tres entradas y ambos perfiles; y que la reproducibilidad del build sigue en PASS.

**No respalda**:
- Estabilidad general ni ausencia de bugs: sin inyección de fallos, caos, recuperación ni fault injection.
- Soak largo: 68 arranques y ~15 min de ejecución efectiva son una muestra acotada.
- Hardware, KVM, UEFI/ISO, SMP o concurrencia real: todo es QEMU TCG con `-smp 1`.
- Persistencia bajo esta campaña: los arranques usan disco por ejecución; el mini-FS persistente lo prueba TASK-916 con sus tres arranques, no TASK-917.
- Fuzzing guiado por cobertura, sanitizers o corpus minimizado: semilla fija y mutaciones acotadas.
- Rendimiento: en el mismo trabajo quick se observaron 36,6 s (08:52) y 39,9–40,3 s (09:00) por carga del host; no hay línea base.
- Procedencia reproducible: sin `.git` no hay commit ni bisect; la procedencia son los hashes de §2.
- Retención de logs: `/tmp` se remonta; las rutas anunciadas pueden no existir al leer el informe.

Por tanto: **PASS repetido y estable dentro del corte**, sin promoción a *Estable* en `docs/quality.md` y sin certificación. Cualquier cambio posterior invalida este corte y exige repetir la campaña.

## 7. Notas para el Lead

- `agents/STATE.md` conserva en la línea de Ferros “suite **39 tests**”, mientras la suite y el gate ya observan **43** (y la propia línea de “Última” dice 163/43/6/166). El Lead lo concilió después a 43.
- `EXPECTED_COUNTS[3] = 43` fue actualizado por la integración a las 08:59:21 (hash `08392603…`); TASK-917 no tocó el gate.
