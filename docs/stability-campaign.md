# Campaña de estabilidad repetida — TASK-913

Fecha: 2026-11-12. Este documento acompaña a
[`infrastructure/scripts/stability_campaign.py`](../infrastructure/scripts/stability_campaign.py),
que repite la campaña acotada de [`stress.py`](../infrastructure/scripts/stress.py)
N veces, mide cada ronda y, en modo `full`, añade la puerta completa
[`verify_all.py --full`](../infrastructure/scripts/verify_all.py) con sus 6
arranques QEMU.

No modifica `stress.py`, `verify_all.py` ni la puerta de
[`quality.md`](quality.md). No es una certificación, no declara ningún
subsistema *Estable* y no sustituye a una campaña prolongada ni a inyección de
fallos a escala.

## Qué mide

Cada ronda es un proceso nuevo e independiente:

| Modo | Comando por ronda | Qué incluye |
|---|---|---|
| `quick` (defecto) | `python3 infrastructure/scripts/stress.py --quick` | 2 arranques QEMU, 1 ronda de Ferros, 1 de selfhost y 20 casos por fuzz. |
| `full` | `python3 infrastructure/scripts/stress.py` + `python3 infrastructure/scripts/verify_all.py --full` | Campaña completa de stress (6 arranques, 2+2 rondas de suites, 200 casos por fuzz) más la puerta completa con 6 arranques QEMU (debug/release × 3), benchmarks y reproducibilidad. |

La campaña registra por ronda:

- **Duración**: reloj de pared de la ronda, del stress y del gate.
- **Estado**: PASS o FAIL según los códigos de salida y los resúmenes, no solo
  por el texto de la consola.
- **Boots**: arranques PASS en `stress`, leídos de los `result.json` que deja el
  runner (estado 33, sin timeout, sin `stderr` de QEMU y sin `PANIC` en la
  serial), y en `full` los 6/6 del gate.
- **Suites**: rondas PASS/ejecutadas de Ferros y selfhost, con el último
  recuento `Ran N tests` que aparece en los logs de `stress`.
- **Fuzz**: casos, expresiones válidas/con error del parser, y
  comparadas/omitidas/toleradas del lexer, extraídos del detalle de las fases
  del `summary.json` de stress.

En `full`, además, verifica explícitamente que el paso 5 de la puerta
(`boot_ferros.py --all --repeat 3`) produce **6/6 arranques con estado 33**. La
fuente principal es el log `05-ferros.log` del gate; si no se puede leer, se
acepta como respaldo un `ferros/build/boot-results.json` fresco con 6/6 estado
33. Si no hay forma de verificar 6/6, la ronda falla: la campaña no declara PASS
un gate que no ha podido comprobar.

## Cómo ejecutar

Requisitos: los mismos que `stress.py` y `verify_all.py` (Python 3.10+,
compilador `zen/compiler/target/release/zen` ya construido, QEMU local, `cc`,
`ld`, `objcopy`, `nm` y el registro offline de Cargo). La campaña no compila
Rust ni descarga nada por sí misma; el gate puede compilar el compilador.

```bash
# Aceptación quick: 5 rondas de stress --quick
python3 infrastructure/scripts/stability_campaign.py --rounds 5

# Aceptación full: 2 rondas de stress completo + verify_all --full
python3 infrastructure/scripts/stability_campaign.py --rounds 2 --mode full

# Guardar una copia del resumen JSON en una ruta concreta
python3 infrastructure/scripts/stability_campaign.py --rounds 3 --json /tmp/campana.json
```

| Opción | Defecto | Significado |
|---|---:|---|
| `--rounds N` | 5 | Número de rondas. Debe ser ≥ 1. |
| `--mode quick\|full` | `quick` | Perfil de cada ronda. |
| `--json RUTA` | — | Copia opcional del resumen. Si es relativa, se resuelve contra el directorio de invocación. |

La campaña **para en la primera ronda fallida**: no ejecuta las restantes y
escribe un resumen parcial (`results` contiene solo las rondas ejecutadas).
Códigos de salida:

| Código | Significado |
|---:|---|
| 0 | Todas las rondas ejecutadas terminaron PASS. |
| 1 | Alguna ronda falló o el JSON solicitado no se pudo escribir. |
| 2 | Argumentos inválidos o faltan los scripts del repositorio. |
| 130 | Cancelada con Ctrl+C; se escribe el resumen parcial. |

Los logs y el resumen viven en `/tmp/zenferros-campaign-*`; no se escriben
artefactos en el repositorio. Estructura:

```text
/tmp/zenferros-campaign-XXXX/
├── summary.json                 # resumen completo (siempre)
└── logs/
    ├── round-01-stress.log      # salida completa de stress.py
    └── round-01-gate.log        # solo en modo full: salida de verify_all.py
```

## Resumen JSON

El JSON se escribe de forma atómica en el directorio temporal y, si se indica,
también en `--json`. Los campos de primer nivel son `schema`, `rounds`,
`results`, `totals` y `warnings`; se añaden metadatos de ejecución.

```json
{
  "schema": "zenferros.stability-campaign/v1",
  "task": "TASK-913",
  "mode": "quick",
  "rounds": 1,
  "stop_on_failure": true,
  "started_at": "2026-11-12T00:20:00+00:00",
  "ended_at": "2026-11-12T00:20:30+00:00",
  "total_seconds": 30.0,
  "interrupted": false,
  "host": {"python": "3.14.8", "platform": "...", "node": "..."},
  "config": {
    "stress_timeout_seconds": 900.0,
    "gate_timeout_seconds": null,
    "gate_expected_boots": null,
    "qemu_success_status": 33
  },
  "results": [
    {
      "round": 1,
      "status": "PASS",
      "seconds": 30.0,
      "stress": {
        "status": "PASS",
        "exit_code": 0,
        "timed_out": false,
        "seconds": 30.0,
        "command": ["python3", "-B", ".../stress.py", "--quick"],
        "log": "/tmp/zenferros-campaign-XXXX/logs/round-01-stress.log",
        "summary_path": "/tmp/zenferros-stress-XXXX/summary.json",
        "metrics": {
          "result": "PASS",
          "boots_pass": 2,
          "boots_total": 2,
          "suites": [
            {"name": "Suite Ferros (1 ronda(s))", "status": "PASS", "rounds": 1, "tests": 34},
            {"name": "Suite selfhost (1 ronda(s))", "status": "PASS", "rounds": 1, "tests": 147}
          ],
          "suites_pass": 2,
          "suites_total": 2,
          "fuzz": {
            "parser": {"status": "PASS", "cases": 20, "valid": 9, "errors": 11},
            "lexer": {"status": "PASS", "cases": 20, "compared": 15, "skipped": 4, "tolerated": 1}
          }
        }
      },
      "gate": null,
      "error": null
    }
  ],
  "totals": {
    "rounds_executed": 1,
    "rounds_passed": 1,
    "rounds_failed": 0,
    "seconds": 30.0,
    "stress_seconds": 30.0,
    "gate_seconds": 0.0,
    "stress": {
      "boots_pass": 2,
      "boots_total": 2,
      "suites_pass": 2,
      "suites_total": 2,
      "fuzz": {
        "parser_cases": 20,
        "parser_valid": 9,
        "parser_errors": 11,
        "lexer_cases": 20,
        "lexer_compared": 15,
        "lexer_skipped": 4,
        "lexer_tolerated": 1
      }
    },
    "gate": {"boots_pass": 0, "boots_total": 0}
  },
  "warnings": []
}
```

En `full`, cada resultado incluye además `gate` con `status`, tiempos, comando,
`run_dir`, `boots_pass`/`boots_total` (6) y `source` (por ejemplo
`gate-log:05-ferros.log`). `totals.gate` acumula esos 6/6 por ronda. Si una
ronda falla, `results` se corta ahí, `gate` puede ser `null` si el stress no
llegó a ejecutarse y `warnings` explica la parada. Los `output_tail` de stress y
gate conservan las últimas líneas para diagnosticar sin abrir los logs.

`warnings` no es decorativo: recoge ausencias de `summary.json`, métricas que no
se pudieron leer, arranques que no cuadran, respaldos usados para verificar el
gate y la parada anticipada. Un PASS con avisos sigue siendo PASS si el stress y
el gate devolvieron 0; un aviso de verificación del gate impide el PASS.

## Tiempos reales

Host de desarrollo (AMD Ryzen 7 260, QEMU TCG, carga compartida), 2026-11-12.
Los tiempos no son un benchmark y varían con la carga del host.

| Comando | Rondas | Resultado | Tiempo por ronda | Total |
|---|---:|---|---:|---:|
| `--rounds 5` (quick) | 5 | PASS | 33,6–36,2 s | 171,9 s |
| `--rounds 2 --mode full` | 2 | PASS | 111,0 s | 222,0 s |

Desglose de una ronda `full` observada: stress completo ≈ 65,7–65,8 s (6
arranques QEMU, 2+2 rondas de suites y 200+200 casos de fuzz) y gate `--full`
≈ 45,2–45,3 s (compilador, suites, 6 arranques, benchmarks y reproducibilidad).
En `quick`, el stress de una ronda se reparte aproximadamente en 1–2 s de
build/arranques, 22–24 s de la suite de Ferros, 6–7 s de selfhost y menos de 1 s
de fuzz; la primera ronda suele ser algo más lenta por el arranque en frío.

El primer comando de aceptación tarda unos **2,9 minutos**; el segundo, unos
**3,7 minutos**. Una compilación limpia o un host más cargado puede tardar más.
Para comparar tiempos hay que usar el mismo host y la misma carga; la campaña no
normaliza ni corrige por contención.

Evidencia de aceptación de este host (2026-11-12, ejecuciones reales):

| Comando | Resultado | Métricas agregadas |
|---|---|---|
| `python3 infrastructure/scripts/stability_campaign.py --rounds 5` | PASS, 171,9 s | 5/5 rondas, stress 10/10 arranques, 10/10 suites; parser 100 casos (45 válidos/55 error), lexer 100 (75 comparadas, 20 omitidas, 5 toleradas UTF-8). |
| `python3 infrastructure/scripts/stability_campaign.py --rounds 2 --mode full` | PASS, 222,0 s | 2/2 rondas, stress 12/12 arranques + gate 12/12 con estado 33, 4/4 suites; parser 400 (200/200), lexer 400 (318 comparadas, 80 omitidas, 2 toleradas). |

Ambas ejecuciones escribieron un `summary.json` válido en el directorio temporal
de la campaña y devolvieron código 0. El esquema se validó además con ejecuciones
equivalentes de 1 ronda en ambos modos y con el fallo simulado.

## Qué NO demuestra

- **No es una certificación de estabilidad.** Repetir 5 o 2 rondas reduce la
  probabilidad de no ver un fallo, pero no la elimina ni establece un intervalo
  de confianza. No declara *Estable* ningún subsistema ni cambia
  [`quality.md`](quality.md).
- **El host es compartido y no está aislado.** Otros procesos, otros agentes y
  otras campañas QEMU compiten por CPU y pueden alterar tiempos y timeouts. Los
  resultados son de este host en esta ventana, no de un entorno reproducible.
- **La semilla del fuzz es fija** (`905`, la de `stress.py`). Las rondas repiten
  el mismo corpus determinista: no hay semilla aleatoria por ronda, ni
  cobertura, ni corpus minimizado, ni fuzzing guiado. Repetir no amplía la
  diversidad de casos.
- **No hay inyección de fallos a escala.** No se inyectan errores en el kernel,
  el scheduler, la memoria, el protocolo serie ni los drivers. El único fallo
  simulado es de entorno (QEMU inexistente) para comprobar que la campaña para,
  deja resumen parcial y devuelve 1; no es fault injection del sistema.
- **No es una campaña prolongada.** 5 rondas quick o 2 full son una muestra
  acotada, no horas de ejecución, caos, recuperación ni pruebas de estrés
  sostenido. No demuestra ausencia de flakiness ni de carreras.
- **No amplía la cobertura de la puerta.** La parte de puerta del modo `full`
  ejecuta exactamente `verify_all.py --full`; no añade pasos, no cambia umbrales
  y no valida nada que la puerta no validara ya. La campaña solo repite y agrega
  (el stress aporta su propia cobertura acotada, descrita en `stability.md`).
- **No cubre hardware físico, KVM, UEFI/ISO, SMP ni persistencia.** Todo es QEMU
  TCG con `-smp 1`; RAMFS es volátil. Los límites detallados están en
  [`stability.md`](stability.md).
- **No es una medición de rendimiento.** Los tiempos sirven para dimensionar la
  campaña, no para comparar versiones ni para declarar *Optimizado*.
- **No hay CI remoto ni procedencia reproducible.** Sin `.git` no hay commit,
  bisect ni historial; la evidencia son estos archivos y las ejecuciones de este
  host.

## Fallos y resumen parcial

La parada es deliberada: un fallo en una ronda invalida la campaña completa y no
tiene sentido seguir acumulando rondas sobre un estado roto. El resumen parcial
conserva lo ejecutado, el error de la ronda y los avisos. Ejemplo de fallo
simulado sin tocar código ni tests:

```bash
QEMU=/tmp/no-existe-qemu python3 infrastructure/scripts/stability_campaign.py \
  --rounds 3 --json /tmp/campana-fallo.json
```

Resultado esperado: la ronda 1 falla en el build de `stress.py` con
`QEMU no disponible`, `results` contiene una sola ronda, `gate` es `null` y el
proceso sale con 1. El JSON sigue siendo válido y documenta la causa; no se
ejecutan las rondas 2 y 3. Este ejercicio valida el manejo de fallos de la
campaña, no la robustez del kernel.

## Relación con `docs/stability.md`

[`stability.md`](stability.md) documenta **qué hace una campaña de stress y qué
demuestra**: fases, guiones de arranque, repetición de suites, fuzz diferencial
con sus tolerancias y límites. Este documento documenta **la repetición de esa
campaña y su agregación**:

- `stress.py` sigue siendo la fuente de verdad de las métricas por fase y de las
  tolerancias (por ejemplo, UTF-8 del lexer). La campaña no replica su lógica:
  lee su `summary.json` y sus logs.
- `stability.md` describe una ejecución; este documento describe N ejecuciones,
  la parada ante el primer fallo, los totales y el esquema JSON.
- En `full`, la campaña añade la puerta completa, pero no la modifica. Los
  detalles de la puerta están en [`quality.md`](quality.md).
- Ninguno de los dos documentos cambia el nivel de madurez ni convierte la
  evidencia acotada en una garantía.

Para interpretar un fallo de fuzz, una tolerancia UTF-8 o los contadores QEMU,
consulta primero [`stability.md`](stability.md); para interpretar una ronda
fallida, un total o un aviso de esta campaña, usa este documento y el JSON.

## Reproducción de una ronda aislada

Si una ronda falla, sus logs y su `summary.json` permiten reproducir la fase:

```bash
# Ver la cola del log de stress de la ronda 2
tail -n 80 /tmp/zenferros-campaign-XXXX/logs/round-02-stress.log

# Repetir el stress completo con la misma semilla y configuración
python3 infrastructure/scripts/stress.py

# Repetir la puerta completa (6 arranques QEMU)
python3 infrastructure/scripts/verify_all.py --full
```

No ejecutar otra campaña o QEMU en paralelo: `stress.py` y `verify_all.py` ya
secuencian sus arranques, pero dos campañas simultáneas competirían por CPU y
podrían alterar timeouts y tiempos observados.
