# Zen benchmark results

- Fecha UTC: `2026-11-11T20:06:09+00:00`
- Host: `Linux-7.2.11-arch1-1-x86_64-with-glibc2.44` / `AMD Ryzen 7 260 w/ Radeon 780M Graphics`
- Python: `3.14.8`; loadavg al inicio: `[2.27001953125, 2.2373046875, 2.05859375]`
- Configuración: warmup=2, reps=7, afinidad CPU=0
- Timing: primary: child CPU time (getrusage RUSAGE_CHILDREN, interleaved); secondary: wall clock per process run, includes startup

| Bench | Lenguaje | CPU mediana (ms) | CPU mín (ms) | CPU desv (ms) | pared mediana (ms) | vs C (CPU) | Binario (B) | Build (s) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| arith | zen | 42.626 | 41.879 | 1.174 | 66.651 | x1.005 | 16160 | 0.043 |
| arith | c | 42.422 | 41.875 | 0.726 | 66.764 | x1.000 | 15968 | 0.038 |
| arith | cpp | 42.952 | 42.411 | 0.951 | 66.558 | x1.012 | 15968 | 0.063 |
| arith | rust | 42.797 | 41.937 | 2.050 | 66.480 | x1.009 | 4537080 | 0.072 |
| collatz | zen | 38.332 | 36.886 | 1.247 | 66.813 | x1.037 | 16160 | 0.045 |
| collatz | c | 36.957 | 36.086 | 0.574 | 66.463 | x1.000 | 15968 | 0.034 |
| collatz | cpp | 36.761 | 36.517 | 0.884 | 66.495 | x0.995 | 15976 | 0.063 |
| collatz | rust | 40.830 | 39.869 | 0.885 | 66.717 | x1.105 | 4537056 | 0.072 |
| mem | zen | 20.586 | 20.206 | 0.924 | 34.582 | x1.017 | 16256 | 0.044 |
| mem | c | 20.244 | 20.043 | 0.691 | 34.487 | x1.000 | 16064 | 0.040 |
| mem | cpp | 21.405 | 20.910 | 0.635 | 34.347 | x1.057 | 16072 | 0.071 |
| mem | rust | 19.546 | 18.589 | 0.870 | 34.701 | x0.966 | 4538008 | 0.076 |
| sort | zen | 27.725 | 26.823 | 0.630 | 34.548 | x1.041 | 16288 | 0.056 |
| sort | c | 26.639 | 26.013 | 1.016 | 34.560 | x1.000 | 16096 | 0.048 |
| sort | cpp | 27.303 | 26.838 | 1.514 | 34.518 | x1.025 | 16112 | 0.076 |
| sort | rust | 37.157 | 36.304 | 0.845 | 66.770 | x1.395 | 4538264 | 0.091 |

## Lectura correcta de esta tabla

- Todos los lenguajes ejecutan el mismo algoritmo con los mismos datos y verifican el mismo checksum.
- Métrica primaria: tiempo de CPU del proceso hijo (getrusage), que no se ve afectado por desalojos del planificador del host compartido; el tiempo de pared se incluye como referencia.
- Las cifras incluyen arranque de proceso y son medidas de un host compartido; no son comparaciones absolutas entre lenguajes ni predicen otro hardware.
- Zen usa el backend C11 con `cc -O2`; C usa `cc -O2`; C++ `g++ -O2`; Rust `rustc -O`. Que Zen y C compartan backend es una propiedad del bootstrap actual y se declara explícitamente.
- Zig no está instalado en este host: se marca como no disponible, sin estimaciones.
