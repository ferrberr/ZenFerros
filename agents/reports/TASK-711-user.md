# TASK-711 — revisión parcial user/build

Dictamen: favorable en este alcance, sin hallazgos bloqueantes. Revisión independiente de `ferros/user/{main.zen,entry.S,linker.ld}` y scripts `build_user.py`/`build_ferros.py`; implementación solo lectura. Excluye deliberadamente mi propio ASM kernel, que requiere otro revisor. Modelo/esfuerzo runtime no expuestos; coordinador identifica herencia histórica Sol/medium. No se ha solicitado ningún cambio de modelo ni delegado a Astra.

## Comprobación del código

`_user_start` alinea RSP a 16 antes de `call user_entry`; entrada Zen queda 8 mod 16. Wrapper SysV convierte RDI/RSI/RDX/RCX en RAX/RDI/RSI/RDX y conserva registros callee-saved. Probe directo int128 verifica los 14 GPR distintos de RAX, comprueba ENOSYS en RAX y restaura sus seis callee-saved. El int no requiere alineación de una llamada C. Pruebas negativas son instrucciones reales; un retorno inesperado termina con status255.

ELF ET_EXEC separado: text RX, rodata R, BSS RW y GNU_STACK RW; página BSS 4096 verificada cero byte a byte por usuario antes de escribir. Entrada 0x40000000; sin undefined ni relocaciones pendientes en ELF enlazado. El perfil nativo usa no-red-zone, general-regs-only, freestanding/noPIE/noPIC y mcmodel=kernel. Las referencias absolutas signed32 del modelo enlazan aquí porque todos los símbolos del kernel están por debajo 0x40000000 y el usuario por debajo 0x40100000, ambos dentro de signed32 positivo; no se generaliza a otras bases virtuales.

`inspect_user` valida longitud 64 antes de desempaquetar, límites completos de PHDR y SHDR antes de iterar, segmentos/overflow mediante enteros Python y rango de imagen, solapamientos de páginas, permisos y entrada ejecutable file-backed. No ejecuta ELF en host. Se probaron 18 rechazos:12 truncados (0,4,7,16,51,52,54,63,64,119,120 y último byte), PHoff máximo, PHnum 9, PHentsize 55, SHoff máximo, SHentsize 63 y entrada+1; todos ValueError, ningún struct.error ni aceptación.

Overrides: construcción propia verifica main_override, unit_overrides(runtime), user_source_override y user_image_override; metadatos/build.log/kernel.zen/user_image.S reflejan rutas correctas. La imagen override admite datos sin validar deliberadamente para negativos del loader; no se confunde con la verificación del ELF generado.

## Evidencia ejecutada

```text
python3 infrastructure/scripts/build_ferros.py --output /tmp/task711-user-debug
Built /tmp/task711-user-debug/ferros-multiboot.elf
python3 infrastructure/scripts/build_ferros.py --release --output /tmp/task711-user-release
Built /tmp/task711-user-release/ferros-multiboot.elf
```

Boots propios con `boot_ferros.boot(image, output/boot, timeout=15)`, QEMU local TCG/qemu64/64 MiB/1 CPU; ambos validan serie completa, stderr vacío, sin timeout. Incluyen 7 ejecuciones CPL3 y los 6 casos de aislamiento; la auditoría de la implementación del aislamiento pertenece al otro revisor.

| Perfil | ELF usuario bytes | BSS bytes | QEMU status | segundos | runs/writes/rejected/irqs |
|---|---:|---:|---:|---:|---|
| debug | 20216 | 4096 | 33 | 0.509316 | 7/1/6/8 |
| release | 13568 | 4096 | 33 | 0.34079 | 7/1/6/1 |

Artefactos propios: `/tmp/task711-user-{debug,release}/{build.json,build.log,user/,boot/}`; negativos en `/tmp/task711-user-negative/checks.json`; overrides en `/tmp/task711-user-overrides/build/`. Ambos boots: switches 45/preemptions 25/yields 16/completed 3, HITO 6 OK exacto.

Riesgos/límites: revisión parcial, sin dictamen independiente sobre ASM kernel/VMM/loader/syscalls; runtime observado en QEMU TCG 64 MiB, sin afirmación hardware/SMP/TLS/SIMD. Sin cambios de implementación.

## SHA256 fuentes revisadas

```text
45a4acf2ad5dff23e7a0a874b7a04ee86511b2356a608d22370a1ff3135478dc  ferros/user/main.zen
c5de12d72f0053c0840585239772cce01831effd959fbb15928e520a4ba4fab0  ferros/user/entry.S
170092ffebeb4a791f528a76584c3cf31cda4426f71848e940db402ed883dcf0  ferros/user/linker.ld
130ac635e2471a1edfb7a89a45d48afaac45d524b97017328e4b7db84894fb8d  infrastructure/scripts/build_user.py
9e270f62b16f2f95b926939fa2e274c72a96e1af52d56839ddc038332a140239  infrastructure/scripts/build_ferros.py
```
