# Zen benchmark results

- Fecha UTC: `2026-11-11T20:06:18+00:00`
- Host: `Linux-7.2.11-arch1-1-x86_64-with-glibc2.44` / `AMD Ryzen 7 260 w/ Radeon 780M Graphics`
- Python: `3.14.8`; loadavg al inicio: `[2.07421875, 2.19580078125, 2.046875]`
- Configuración: warmup=2, reps=7, afinidad CPU=0
- Timing: primary: child CPU time (getrusage RUSAGE_CHILDREN, interleaved); secondary: wall clock per process run, includes startup

| Bench | Lenguaje | CPU mediana (ms) | CPU mín (ms) | CPU desv (ms) | pared mediana (ms) | vs C (CPU) | Binario (B) | Build (s) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| arith | zen | 42.935 | 41.845 | 0.764 | 66.597 | x1.009 | 16160 | 0.042 |
| arith | c | 42.536 | 41.422 | 1.388 | 66.554 | x1.000 | 15968 | 0.039 |
| arith | cpp | 44.002 | 42.841 | 1.080 | 66.656 | x1.034 | 15968 | 0.064 |
| arith | rust | 42.478 | 42.205 | 1.545 | 66.629 | x0.999 | 4537080 | 0.072 |
| collatz | zen | 37.710 | 36.785 | 0.741 | 66.645 | x1.027 | 16160 | 0.043 |
| collatz | c | 36.726 | 35.771 | 0.955 | 66.620 | x1.000 | 15968 | 0.037 |
| collatz | cpp | 37.787 | 37.155 | 0.639 | 66.905 | x1.029 | 15976 | 0.064 |
| collatz | rust | 41.169 | 40.198 | 0.464 | 66.870 | x1.121 | 4537056 | 0.074 |
| mem | zen | 20.386 | 20.233 | 0.587 | 34.597 | x0.939 | 16256 | 0.044 |
| mem | c | 21.722 | 19.999 | 1.272 | 34.211 | x1.000 | 16064 | 0.038 |
| mem | cpp | 21.583 | 20.965 | 1.030 | 34.287 | x0.994 | 16072 | 0.070 |
| mem | rust | 19.118 | 18.702 | 0.500 | 34.613 | x0.880 | 4538008 | 0.077 |
| sort | zen | 26.693 | 26.395 | 0.858 | 34.427 | x1.027 | 16288 | 0.057 |
| sort | c | 25.984 | 25.700 | 1.261 | 34.157 | x1.000 | 16096 | 0.047 |
| sort | cpp | 27.448 | 26.710 | 0.988 | 34.310 | x1.056 | 16112 | 0.103 |
| sort | rust | 37.038 | 35.880 | 0.962 | 66.754 | x1.425 | 4538264 | 0.082 |

## Lectura correcta de esta tabla

- Todos los lenguajes ejecutan el mismo algoritmo con los mismos datos y verifican el mismo checksum.
- Métrica primaria: tiempo de CPU del proceso hijo (getrusage), que no se ve afectado por desalojos del planificador del host compartido; el tiempo de pared se incluye como referencia.
- Las cifras incluyen arranque de proceso y son medidas de un host compartido; no son comparaciones absolutas entre lenguajes ni predicen otro hardware.
- Zen usa el backend C11 con `cc -O2`; C usa `cc -O2`; C++ `g++ -O2`; Rust `rustc -O`. Que Zen y C compartan backend es una propiedad del bootstrap actual y se declara explícitamente.
- Zig no está instalado en este host: se marca como no disponible, sin estimaciones.
