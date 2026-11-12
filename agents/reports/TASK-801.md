# TASK-801 — Evidencia: laboratorio de benchmarks (Hito 8)

Fecha de cierre: 2026-11-11. Resultados ejecutados en este workspace.

## Qué se implementó

| Componente | Archivos |
|---|---|
| Benchmarks Zen/C/C++/Rust con el mismo algoritmo y checksum | `benchmarks/{zen,c,cpp,rust}/{arith,collatz,mem,sort}.*` |
| Arnés reproducible (build, verificación de checksum, intercalado, CPU-time, JSON+MD) | `benchmarks/scripts/bench.py` |
| Tests (paridad entre lenguajes, estadísticas, aborto por checksum) | `benchmarks/tests/test_benchmarks.py` |
| Metodología | `benchmarks/README.md`, `agents/decisions/ADR-013.md`, `docs/benchmarks/results.md` |
| Resultados versionados (3 suites completas) | `benchmarks/results/bench-run{1,2,3}.{json,md}` |
| Ignorado del directorio de build | `.gitignore` (`/benchmarks/build/`) |

## Benchmarks y corrección

| Bench | Carga | Checksum común |
|---|---|---|
| `arith` | 50M iteraciones LCG envolvente u64 | `385904853` |
| `collatz` | pasos Collatz 1..=500 000 | `62134795` |
| `mem` | 16 MiB volátiles escritura+lectura sobre malloc | `2139062878` |
| `sort` | heapsort in-place 500k u32 con volátiles | `14559707269027860169` |

El arnés compila las cuatro implementaciones, las ejecuta y compara la salida con la referencia C **antes** de medir; una discrepancia aborta con código 4, sin JSON/MD ni líneas de timing.

## Comandos y salidas reales

```bash
python3 -m unittest discover -s benchmarks/tests -v
# Ran 6 tests: paridad Zen↔C, paridad C++/Rust, estadísticas, aborto por checksum — OK
```

```bash
python3 benchmarks/scripts/bench.py --reps 7 --warmup 2   # tres veces
```

Ratios frente a C por ejecución (r1, r2, r3):

| Bench | Zen/C | C++/C | Rust/C |
|---|---|---|---|
| arith | 0.969, 1.005, 1.009 | 1.002, 1.012, 1.034 | 0.981, 1.009, 0.999 |
| collatz | 1.018, 1.037, 1.027 | 1.019, 0.995, 1.029 | 1.085, 1.105, 1.121 |
| mem | 1.015, 1.017, 0.938 | 1.085, 1.057, 0.994 | 0.950, 0.966, 0.880 |
| sort | 1.023, 1.041, 1.027 | 1.048, 1.025, 1.056 | 1.392, 1.395, 1.425 |

Medianas absolutas de CPU en las tres suites (ms):

| Bench | Zen | C | C++ | Rust |
|---|---|---|---|---|
| arith | 42,087–42,935 | 42,422–43,414 | 42,952–44,002 | 42,478–42,797 |
| collatz | 37,710–38,332 | 36,726–37,176 | 36,761–37,900 | 40,324–41,169 |
| mem | 20,386–21,422 | 20,244–21,722 | 21,405–22,895 | 19,118–20,049 |
| sort | 26,693–27,883 | 25,984–27,265 | 27,303–28,564 | 37,038–37,947 |

Desviación típica intra-ejecución: 0,46–2,95 ms. Tamaños: Zen 16,1–16,3 KB; C/C++ ~16,0 KB; Rust ~4,5 MB.
Compilación: 0,0344–0,1030 s en estas tres suites (una cuarta ejecución con más carga llegó a 0,224 s: dato orientativo, no benchmark de compilador).
Afinidad de CPU efectiva registrada en el JSON (`cpu_affinity_effective: true`).

Regresiones: compilador 46 tests OK; Ferros 20 tests OK (sin cambios en kernel/compilador).

## Decisiones metodológicas y por qué

- **Métrica primaria: tiempo de CPU del hijo** (`getrusage`), no tiempo de pared. En pruebas exploratorias el wall time mostró variabilidad no atribuible al código (desalojos del host); no se conservó evidencia de ese diagnóstico, así que se justifica la métrica de CPU por su robustez general frente a desalojos. Sigue sin ser inmune a frecuencia/SMT ni mide ciclos: no hay `perf`.
- **Ejecuciones intercaladas** por lenguaje dentro de cada repetición y **afinidad** con degradación segura registrada.
- **Checksum obligatorio**: aborto verificado automáticamente con una fuente C alterada (`+1`), RC=4 y sin artefactos.
- **Sin hints de inline**: se retiró `#[inline(always)]` de la implementación Rust de `sort` para no darle una ventaja que C/C++/Zen no tienen.
- **Sin recursión**: la hipótesis de trabajo es que el inlining recursivo varía entre lenguaje/compilador (GCC para C, LLVM para Rust) y Zen no permite `noinline`; no se conservaron fuentes ni JSON de la prueba exploratoria, así que se trata como **hipótesis no verificada**, no como resultado. Se sustituyó por `collatz`, que no depende de esa heurística.
- **Zig y clang**: sondeados; no instalados; declarados y sin estimaciones.

## Revisión independiente y correcciones

Una revisión independiente dio **CON OBSERVACIONES**: laboratorio apto como línea base, pero (1) se presentaban diferencias dentro del ruido como hallazgos; (2) asimetría `#[inline(always)]` en Rust; (3) rango de build incorrecto; (4) `mean_ns` no se guardaba pese a documentarse; (5) terminología «ciclos» y atribuciones de fib incorrectas; (6) justificación de fib sin fuentes; (7) fallback de afinidad no registrado; (8) clang no declarado; (9) tests solo cubrían Zen↔C y no el aborto.

Correcciones aplicadas: tres suites completas y rangos entre ejecuciones en `docs/benchmarks/results.md`; afirmación rebajada a «paridad aproximada, diferencias de pocos % no son señal»; inline hints retirados; medias incluidas en JSON; rango de build corregido; terminología y párrafo de fib reescritos sin cifras ni atribuciones erróneas; `cpu_affinity_effective` registrado; clang sondeado y declarado; 6 tests incluyendo paridad C++/Rust y aborto por checksum.

## Riesgos y deuda

- Host compartido: los ratios varían varios puntos entre ejecuciones; no sirven para afirmar ventajas de pocos %.
- Zen y C comparten backend C11 (`cc -O2`): no mide un backend propio.
- Sin `perf`: sin ciclos/instrucciones/fallos de caché.
- Sin floats, SIMD, concurrencia ni cargas reales todavía; sin Zig/clang.
- Rust es consistente en `collatz` (+8,5…12,1 %) y `sort` (+39…43 %) más lento en este rustc con accesos volátiles; dato acotado a estas cargas, no juicio general.
