# Programas Zen de usuario — Hitos 6 y 7

Desde la raíz, con el compilador Zen release disponible:

```bash
python3 infrastructure/scripts/boot_ferros.py --all --repeat 3
```

Compila dos ELF diferentes: el kernel y `user/ferros-user.elf` dentro del directorio de cada perfil. El segundo se incorpora al kernel como archivo ELF; el loader Zen valida headers, asigna páginas, copia datos y borra BSS/stack. QEMU ejecuta ese código en CPL3, con textoRX, datosRW-NX, mapa kernel supervisor y guarda de pila.

Para compilar únicamente el artefacto de usuario:

```bash
python3 infrastructure/scripts/build_user.py --release
```

Ese ELF usa la ABI de Ferros y se ejecuta en su guest QEMU. No es un ejecutable Linux. El archivo editable es `ferros/user/main.zen`; `pub fn user_entry(case_id:u64)` recibe un argumento de pruebas. El pequeño adaptador ASM hace la transición entre CABI e int0x80. Las cadenas se copian a un buffer BSS mediante `str_byte`, sin pasar `str` por ABI externa.

| Syscall | RAX | RDI | RSI | Resultado RAX |
|---|---:|---|---|---|
| write |1|puntero usuario|longitud≤4096|bytes escritos, −14 dirección inválida, −22 tamaño excesivo|
| exit |2|estado|ignorado|no retorna; recupera controlador kernel|
| ticks |3|ignorado|ignorado|contador IRQ0 PIT, aproximadamente100Hz|
| open |4|puntero a ruta usuario|flags reservado|fd≥100 o error negativo|
| read |5|fd|buffer usuario|bytes leídos o error negativo|
| write |6|fd|buffer usuario|bytes escritos o error negativo|
| close |7|fd|ignorado|0 o error negativo|
| read_char |8|ignorado|ignorado|`0..255` byte de COM1 o `0xFFFFFFFF` si no hay dato (no bloquea)|
| readdir |9|buffer usuario|count≤4096|bytes de nombres NUL-separados o error negativo|
| desconocida |otro|ignorado|ignorado|−38 ENOSYS|

RDX queda reservado como tercer argumento. El dispatcher preserva los otros14GPR; no modifica los valores CS/RIP/RSP del marco de retorno normal. write valida el rango entero antes del primer byte, con restas para evitar overflow y comprobación de cada hoja U/presente. Una llamada que cruza un hueco no produce salida parcial.

La ejecución normal comprueba en usuario CPL3, flags, GPR, BSS cero, salida, errores y avance de ticks. Después se recarga el ELF para seis intentos prohibidos: leer kernel, escribir text, CLI, ejecutar stackNX, leer guard y usar otra puerta IDT. Cada tarea termina por su fault; el controlador verifica GP/PF/error/CR2 y la recuperación del mismo número de páginas libres. Solo entonces aparece `USERSPACE: ISOLATION AND CLEANUP OK` y, tras el flujo init/VFS, la sesión de shell del TASK-703 (READY…DONE), la autoprueba de VFS y `FS: RAMFS OK`/`FS: VFS OPEN/READ/CLOSE OK`/`HITO 7 OK`. Detalle en `docs/ferros/filesystem.md` y `docs/ferros/shell.md`.

Los contadores reales aparecen en `USERSPACE: STATS`: con el guion de shell por defecto, 7 invocaciones, **18 escrituras** (5 del bloque VFS + 13 del shell), 6 rechazos e IRQs≥1. Sin entrada, el shell termina con 9 escrituras y sin panic; `boot_ferros.py` exige el guion y el valor exacto 18. La cantidad de IRQs depende de la temporización TCG. `boot_ferros.py` exige los mensajes, contadores, stderr vacío y salida33. Un panic termina35 y conserva logs; un programa infinito agota el timeout y el runner termina/recolecta el guest.

Pruebas:

```bash
python3 -m unittest discover -s ferros/tests -v
CARGO_HOME="$PWD/.cargo" cargo test --offline --manifest-path zen/compiler/Cargo.toml
```

Los tests host usan el código Zen real con mocks PMM/CPU/IO, en normal/O2 y UBSan; no ejecutan instrucciones privilegiadas en el anfitrión. Incluyen mutaciones ELF, truncados, ocho fallos sucesivos de asignación, BSS/permisos, rangos cruzados y clasificación de traps. QEMU añade ejecución normal y negativos con ELF inválido, U ausente y PF dentro del kernel de write; los últimos deben fallar sin marcador de éxito.

Esta versión tiene una invocación activa, sin scheduler de procesos ni límite de CPU. Aísla páginas y privilegios para el perfil Zen/GPR probado; no guarda estado SIMD/FPU entre binarios arbitrarios. Kernel y usuario comparten CR3 con páginas supervisor. No hay FS persistente, IPC, TLS, ASLR ni IST; el shell interactivo COM1 (TASK-703) y el VFS en memoria existen y están verificados. Contratos completos y referencias: ADR-012; evidencia TASK-710 y revisión TASK-711.
