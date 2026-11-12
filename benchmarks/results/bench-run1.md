# Zen benchmark results

- Fecha UTC: `2026-11-11T20:06:00+00:00`
- Host: `Linux-7.2.11-arch1-1-x86_64-with-glibc2.44` / `AMD Ryzen 7 260 w/ Radeon 780M Graphics`
- Python: `3.14.8`; loadavg al inicio: `[2.50146484375, 2.27978515625, 2.0703125]`
- Configuración: warmup=2, reps=7, afinidad CPU=0
- Timing: primary: child CPU time (getrusage RUSAGE_CHILDREN, interleaved); secondary: wall clock per process run, includes startup

| Bench | Lenguaje | CPU mediana (ms) | CPU mín (ms) | CPU desv (ms) | pared mediana (ms) | vs C (CPU) | Binario (B) | Build (s) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| arith | zen | 42.087 | 41.551 | 0.969 | 66.439 | x0.969 | 16160 | 0.046 |
| arith | c | 43.414 | 42.103 | 1.661 | 66.467 | x1.000 | 15968 | 0.040 |
| arith | cpp | 43.497 | 42.473 | 1.777 | 66.417 | x1.002 | 15968 | 0.084 |
| arith | rust | 42.570 | 41.983 | 1.871 | 66.575 | x0.981 | 4537080 | 0.075 |
| collatz | zen | 37.835 | 36.844 | 1.481 | 66.589 | x1.018 | 16160 | 0.045 |
| collatz | c | 37.176 | 35.555 | 1.088 | 66.737 | x1.000 | 15968 | 0.037 |
| collatz | cpp | 37.900 | 36.645 | 0.739 | 66.856 | x1.020 | 15976 | 0.063 |
| collatz | rust | 40.324 | 39.876 | 0.902 | 66.588 | x1.085 | 4537056 | 0.070 |
| mem | zen | 21.422 | 19.983 | 1.010 | 34.570 | x1.015 | 16256 | 0.045 |
| mem | c | 21.099 | 20.376 | 1.130 | 34.535 | x1.000 | 16064 | 0.040 |
| mem | cpp | 22.895 | 21.186 | 1.318 | 34.532 | x1.085 | 16072 | 0.069 |
| mem | rust | 20.049 | 18.369 | 1.485 | 34.847 | x0.950 | 4538008 | 0.076 |
| sort | zen | 27.883 | 27.137 | 0.676 | 34.534 | x1.023 | 16288 | 0.052 |
| sort | c | 27.265 | 25.890 | 1.288 | 34.278 | x1.000 | 16096 | 0.045 |
| sort | cpp | 28.564 | 26.918 | 1.887 | 34.499 | x1.048 | 16112 | 0.075 |
| sort | rust | 37.947 | 35.749 | 2.951 | 66.602 | x1.392 | 4538264 | 0.080 |

## Lectura correcta de esta tabla

- Todos los lenguajes ejecutan el mismo algoritmo con los mismos datos y verifican el mismo checksum.
- Métrica primaria: tiempo de CPU del proceso hijo (getrusage), que no se ve afectado por desalojos del planificador del host compartido; el tiempo de pared se incluye como referencia.
- Las cifras incluyen arranque de proceso y son medidas de un host compartido; no son comparaciones absolutas entre lenguajes ni predicen otro hardware.
- Zen usa el backend C11 con `cc -O2`; C usa `cc -O2`; C++ `g++ -O2`; Rust `rustc -O`. Que Zen y C compartan backend es una propiedad del bootstrap actual y se declara explícitamente.
- Zig no está instalado en este host: se marca como no disponible, sin estimaciones.
