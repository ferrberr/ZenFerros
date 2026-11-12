# Flags de optimización del backend C11 de Zen — TASK-802

- Fecha UTC: `2026-11-11T21:05:23+00:00`
- Host: `AMD Ryzen 7 260 w/ Radeon 780M Graphics` · `Linux-7.2.11-arch1-1-x86_64-with-glibc2.44` · loadavg al inicio `3.25, 3.11, 2.62` · máscara de CPU `[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]`
- Compilador: `cc (GCC) 16.2.1 20260810` (`cc`) · Zen `zen 0.1.0 (bootstrap)`
- Configuración: warmup=2 rondas, reps=7, pasadas=2, CPU fijada=0 (efectiva=True), métrica primaria = tiempo de CPU del hijo (`getrusage(RUSAGE_CHILDREN)`)
- Comando: `/usr/bin/python3 benchmarks/scripts/flags.py --reps 7 --warmup 2 --passes 2`

## Método

Para cada benchmark se generó C con `zen build benchmarks/zen/<b>.zen --emit c --release` y se compiló ese mismo fichero con `cc -std=c11 <flags>`. Antes de medir, cada binario se ejecutó y su checksum debía coincidir con el del benchmark C; una discrepancia se registra y esa variante no se mide. Las variantes se ejecutan intercaladas, rotando el orden inicial en cada repetición, y la suite completa se repite 2 veces. Se compara cada variante contra `-O2` **de la misma pasada**. Se incluye el arranque del proceso y no se incluye la compilación.

## Checksums

| Benchmark | Esperado | C de referencia | O2 | O3 | O2-LTO | O3-LTO |
|---|---|---|---|---|---|---|
| arith | `385904853` | `385904853` (benchmarks/build/c/arith) | OK | OK | OK | OK |
| collatz | `62134795` | `62134795` (benchmarks/build/c/collatz) | OK | OK | OK | OK |
| mem | `2139062878` | `2139062878` (benchmarks/build/c/mem) | OK | OK | OK | OK |
| sort | `14559707269027860169` | `14559707269027860169` (benchmarks/build/c/sort) | OK | OK | OK | OK |

## Generación y compilación

| Benchmark | C generado (B) | `zen --emit c` (s) |
|---|---:|---:|
| arith | 10482 | 0.001 |
| collatz | 11219 | 0.002 |
| mem | 12083 | 0.002 |
| sort | 17634 | 0.002 |

| Benchmark | Variante | Flags | Binario (B) | Δ tamaño vs -O2 | Compilación (s) |
|---|---|---|---:|---:|---:|
| arith | O2 | `-O2` | 16152 | +0.00 % | 0.039 |
| arith | O3 | `-O3` | 16152 | +0.00 % | 0.036 |
| arith | O2-LTO | `-O2 -flto` | 16120 | -0.20 % | 0.060 |
| arith | O3-LTO | `-O3 -flto` | 16120 | -0.20 % | 0.061 |
| collatz | O2 | `-O2` | 16160 | +0.00 % | 0.040 |
| collatz | O3 | `-O3` | 16160 | +0.00 % | 0.038 |
| collatz | O2-LTO | `-O2 -flto` | 16120 | -0.25 % | 0.064 |
| collatz | O3-LTO | `-O3 -flto` | 16120 | -0.25 % | 0.065 |
| mem | O2 | `-O2` | 16256 | +0.00 % | 0.041 |
| mem | O3 | `-O3` | 16256 | +0.00 % | 0.040 |
| mem | O2-LTO | `-O2 -flto` | 16224 | -0.20 % | 0.066 |
| mem | O3-LTO | `-O3 -flto` | 16224 | -0.20 % | 0.063 |
| sort | O2 | `-O2` | 16288 | +0.00 % | 0.050 |
| sort | O3 | `-O3` | 16256 | -0.20 % | 0.050 |
| sort | O2-LTO | `-O2 -flto` | 16280 | -0.05 % | 0.072 |
| sort | O3-LTO | `-O3 -flto` | 16224 | -0.39 % | 0.078 |


## Resultados por pasada

### Pasada 1

loadavg al inicio `3.25, 3.11, 2.62` · al final `3.55, 3.17, 2.64`

| Benchmark | Variante | Flags | CPU mediana (ms) | CPU mín (ms) | CPU desv (ms) | vs -O2 |
|---|---|---|---:|---:|---:|---:|
| arith | O2 | `-O2` | 44.165 | 43.847 | 0.195 | x1.000 |
| arith | O3 | `-O3` | 44.553 | 43.959 | 1.222 | x1.009 |
| arith | O2-LTO | `-O2 -flto` | 44.279 | 43.971 | 0.778 | x1.003 |
| arith | O3-LTO | `-O3 -flto` | 44.107 | 43.658 | 0.531 | x0.999 |
| collatz | O2 | `-O2` | 38.943 | 38.613 | 0.492 | x1.000 |
| collatz | O3 | `-O3` | 37.737 | 37.520 | 0.191 | x0.969 |
| collatz | O2-LTO | `-O2 -flto` | 38.781 | 38.471 | 2.136 | x0.996 |
| collatz | O3-LTO | `-O3 -flto` | 37.711 | 37.496 | 0.139 | x0.968 |
| mem | O2 | `-O2` | 20.563 | 20.128 | 0.527 | x1.000 |
| mem | O3 | `-O3` | 20.681 | 20.348 | 0.813 | x1.006 |
| mem | O2-LTO | `-O2 -flto` | 20.576 | 20.115 | 0.280 | x1.001 |
| mem | O3-LTO | `-O3 -flto` | 20.467 | 20.224 | 0.325 | x0.995 |
| sort | O2 | `-O2` | 30.134 | 29.132 | 2.394 | x1.000 |
| sort | O3 | `-O3` | 29.980 | 27.747 | 1.262 | x0.995 |
| sort | O2-LTO | `-O2 -flto` | 30.116 | 29.120 | 2.026 | x0.999 |
| sort | O3-LTO | `-O3 -flto` | 29.665 | 28.420 | 2.307 | x0.984 |

### Pasada 2

loadavg al inicio `3.55, 3.17, 2.64` · al final `3.62, 3.20, 2.66`

| Benchmark | Variante | Flags | CPU mediana (ms) | CPU mín (ms) | CPU desv (ms) | vs -O2 |
|---|---|---|---:|---:|---:|---:|
| arith | O2 | `-O2` | 44.581 | 44.073 | 0.453 | x1.000 |
| arith | O3 | `-O3` | 44.608 | 43.986 | 0.352 | x1.001 |
| arith | O2-LTO | `-O2 -flto` | 44.565 | 44.149 | 0.391 | x1.000 |
| arith | O3-LTO | `-O3 -flto` | 44.362 | 44.079 | 0.390 | x0.995 |
| collatz | O2 | `-O2` | 39.161 | 38.754 | 0.361 | x1.000 |
| collatz | O3 | `-O3` | 37.690 | 36.918 | 0.514 | x0.962 |
| collatz | O2-LTO | `-O2 -flto` | 39.027 | 38.265 | 0.353 | x0.997 |
| collatz | O3-LTO | `-O3 -flto` | 37.967 | 37.688 | 0.312 | x0.970 |
| mem | O2 | `-O2` | 20.481 | 20.163 | 0.289 | x1.000 |
| mem | O3 | `-O3` | 20.592 | 20.026 | 0.381 | x1.005 |
| mem | O2-LTO | `-O2 -flto` | 20.610 | 20.426 | 0.174 | x1.006 |
| mem | O3-LTO | `-O3 -flto` | 20.806 | 20.304 | 0.612 | x1.016 |
| sort | O2 | `-O2` | 28.576 | 28.325 | 0.988 | x1.000 |
| sort | O3 | `-O3` | 28.803 | 28.040 | 1.825 | x1.008 |
| sort | O2-LTO | `-O2 -flto` | 28.670 | 28.128 | 1.430 | x1.003 |
| sort | O3-LTO | `-O3 -flto` | 28.460 | 28.012 | 0.656 | x0.996 |

## Resumen entre pasadas (ratio frente a -O2, menor es mejor)

| Benchmark | Variante | ratio p1 | ratio p2 | mejora media | dispersión p1↔p2 | CV intra-pasada máx. | ¿>3 % en ambas? |
|---|---|---:|---:|---:|---:|---:|---|
| arith | O3 | 1.009 | 1.001 | -0.47 % | 0.81 % | 2.74 % | no |
| arith | O2-LTO | 1.003 | 1.000 | -0.11 % | 0.29 % | 1.76 % | no |
| arith | O3-LTO | 0.999 | 0.995 | +0.31 % | 0.36 % | 1.20 % | no |
| collatz | O3 | 0.969 | 0.962 | +3.43 % | 0.68 % | 1.36 % | sí |
| collatz | O2-LTO | 0.996 | 0.997 | +0.38 % | 0.07 % | 5.51 % | no |
| collatz | O3-LTO | 0.968 | 0.970 | +3.11 % | 0.12 % | 0.82 % | sí |
| mem | O3 | 1.006 | 1.005 | -0.56 % | 0.03 % | 3.93 % | no |
| mem | O2-LTO | 1.001 | 1.006 | -0.35 % | 0.56 % | 1.36 % | no |
| mem | O3-LTO | 0.995 | 1.016 | -0.56 % | 2.04 % | 2.94 % | no |
| sort | O3 | 0.995 | 1.008 | -0.14 % | 1.30 % | 6.34 % | no |
| sort | O2-LTO | 0.999 | 1.003 | -0.13 % | 0.39 % | 6.73 % | no |
| sort | O3-LTO | 0.984 | 0.996 | +0.98 % | 1.16 % | 7.78 % | no |

## Lectura de los datos

- `arith`: la menor mediana media es de `O3-LTO` (+0.31 % de mejora media; p1 x0.999, p2 x0.995).
- `collatz`: la menor mediana media es de `O3` (+3.43 % de mejora media; p1 x0.969, p2 x0.962).
- `mem`: la menor mediana media es de `O2-LTO` (-0.35 % de mejora media; p1 x1.001, p2 x1.006).
- `sort`: la menor mediana media es de `O3-LTO` (+0.98 % de mejora media; p1 x0.984, p2 x0.996).

Mejoras superiores al 3 % y reproducibles en ambas pasadas: `collatz` (O3, O3-LTO). Ninguna variante las presenta en las cuatro cargas a la vez.

## Conclusión

**Recomendación: mantener `-O2`.**

Ninguna variante cumple el criterio preregistrado (mejora >3 % frente a -O2 en las cuatro cargas y en ambas pasadas, sin regresión (ratio > 1.0)). No hay evidencia reproducible de una mejora superior al 3 % en todas las cargas; cambiar flags sin esa evidencia añadiría riesgo (LTO, compilación más lenta, binarios distintos) sin beneficio demostrado.
- `O3`: la mejora no es uniforme entre cargas (peor carga: mem -0.56 %).
- `O2-LTO`: la mejora no es uniforme entre cargas (peor carga: mem -0.35 %).
- `O3-LTO`: la mejora no es uniforme entre cargas (peor carga: mem -0.56 %).
La señal reproducible se limita a `collatz` (O3, O3-LTO); no se extiende al resto de cargas y no justifica cambiar el flag global.

Criterio explícito: una variante solo se recomienda si su mediana de CPU es más de un 3 % inferior a la de `-O2` en **todos** los benchmarks y en **ambas** pasadas, y no es más lenta que `-O2` en ninguna medición. Las diferencias por debajo de ese umbral no se consideran señal en este host.

## Variabilidad y límites

- Dispersión entre pasadas: 0.00–2.04 % según benchmark y variante.
- Coeficiente de variación intra-pasada máximo: 0.82–7.94 %.
- **Zen comparte backend con C**: este estudio mide el efecto de los flags del compilador C sobre el C generado, no un backend propio de Zen. No se declara superioridad de Zen sobre C ni de una variante sobre otra fuera de estas cargas.
- Host compartido, sin `perf`: la métrica es tiempo de CPU, no ciclos ni instrucciones; los cambios de frecuencia y la contención SMT no se eliminan. Las cifras no generalizan a otro hardware ni a otras cargas.
- Se incluye el arranque del proceso; en cargas cortas puede pesar más que en un benchmark de larga duración.
- LTO: `-flto` se pasa también en el enlace (una sola unidad de traducción). El tiempo de compilación y el tamaño de binario se reportan, pero no son el criterio de decisión.
- Solo se miden cuatro benchmarks; los resultados no justifican cambiar flags para cargas no representadas aquí.
- No se modificó `zen/compiler/src/native.rs`: su build release sigue usando `-O2` (línea 77). Este informe solo recomienda; el cambio, si lo hubiera, correspondería al Lead.
- Los cuatro flags compilaron y verificaron checksum en este host; no hubo variantes no disponibles.

## Reproducir

```bash
/usr/bin/python3 benchmarks/scripts/flags.py --reps 7 --warmup 2 --passes 2
```

JSON completo: `/home/ferranfg/proyectos/ZenFerros/benchmarks/results/opt-flags.json`. Script: `/home/ferranfg/proyectos/ZenFerros/benchmarks/scripts/flags.py`.

