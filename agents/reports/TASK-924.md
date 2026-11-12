# TASK-924 — Reemplazo persistente desde CPL3

**Responsable**: agente 08/11 (`/root/ferros_persist`).
**Estado**: REVISION; implementación, regresión y revisión independiente verificadas; pendiente integración.
**Dependencias**: TASK-916, TASK-919. **Base**: `e7737a6`.
**Checkout aislado**: `/tmp/zenferros-task924`, rama `task-924-persist`.

## Contrato y cambios

- `vfs_write`/`vfs_write_user` enrutan los fds ZENFS01 al nuevo
  `pfs_commit_ptr`. Reemplazo completo de un archivo existente desde offset 0,
  no append: longitud 0..512 B, retorno exacto tras datos → inodo → ATA flush.
  Longitud cero trunca. `boot.txt` devuelve EACCES (−13), reservado al kernel.
- Syscall 6 conserva validación previa de páginas usuario: EFAULT (−14) por
  puntero/rango inválido y EINVAL (−22) por count >4096; la capa PFS devuelve
  EFBIG (−27) por 513..4096 B. Los rechazos no escriben datos. EBADF, RAMFS
  0644/EACCES y demás errores anteriores permanecen.
- Fallos ATA/superbloque/inodo devuelven EIO (−5). Se actualizan datos y tamaño
  en la caché VFS solamente tras flush exitoso, visibles en todos los fds.
  Tras intentar escribir datos, cualquier fallo invalida toda la caché: los fds
  PFS abiertos leen EIO, nuevos open reciben ENOENT y readdir solo lista RAMFS.
  Fallos anteriores a intentar datos no invalidan la copia aún no modificada.
- Scratch supervisor reutilizable +4608..5119 dentro de la reserva de 8192 B
  existente. No hay `heap_alloc` en la nueva ruta; 150 reemplazos consecutivos
  verifican que no agota el heap. El layout de disco no cambia.
- Shell: `put <ruta> <texto>` abre, llama syscall6 y cierra; éxito imprime
  `SHELL: STORED`. La línea de 64 B limita el texto a `64−5−len(ruta)` B;
  la syscall admite 512 B. El help y guion de aceptación previo conservan
  su transcripción. `put saved.txt ` trunca a cero.
- Crear/borrar desde CPL3 queda fuera del contrato, aprobado explícitamente
  por el orquestador. La prueba prepara un archivo vacío en una imagen válida
  antes del primer boot; desde ese punto solo el guest escribe el disco.
- Documentación scoped actualizada en `docs/ferros/filesystem.md` y
  `docs/ferros/persistence.md`; no se editaron README/ROADMAP/ARCHITECTURE.

La secuencia **no es atómica**. Error o corte entre datos/inodo/flush puede
mostrar datos nuevos o parciales con el tamaño anterior, tamaño nuevo con
datos incompletos o escrituras sin persistir. No hay rollback, journal,
checksum de datos ni garantía de conservar la versión anterior.

## Evidencia de ejecución

El worktree administrado se creó en
`/home/ferranfg/.codex/worktrees/task-924-persist/ZenFerros`, pero su primera
escritura falló `OSError: [Errno 30] Read-only file system`, sin modificar nada.
Se informó al orquestador y este autorizó usar clon aislado en /tmp. El primer
clone local detectó `Invalid cross-device link`; se resolvió con `--no-hardlinks`:

```text
git clone --local --no-hardlinks /home/ferranfg/proyectos/ZenFerros /tmp/zenferros-task924
Cloning into '/tmp/zenferros-task924'...
done.
git -C /tmp/zenferros-task924 switch -c task-924-persist e7737a6
Switched to a new branch 'task-924-persist'
```

Se usaron enlaces locales a `.tools` y al binario release `zen` del checkout
original, sin reconstruir ni escribir el target compartido. Todas las imágenes
kernel/usuario y discos se construyeron en /tmp.

Comandos ejecutados desde el clon:

```text
python3 -m unittest ferros.tests.test_vfs ferros.tests.test_userspace.UserPolicyTests.test_elf_rollback_memory_permissions_buffers_and_faults -v
Ran 2 tests in 1.340s
OK

python3 -m unittest ferros.tests.test_pfs.PfsHostTests ferros.tests.test_pfs_vfs -v
Ran 3 tests in 5.937s
OK

python3 -m unittest ferros.tests.test_pfs_vfs.PfsVfsGuestTests.test_cpl3_replacement_survives_restart -v
Ran 1 test in 3.236s
OK

python3 -m unittest discover -s ferros/tests -v > /tmp/task924-tests.log 2>&1
Ran 45 tests in 31.733s
OK

git diff --check
(sin salida, exit 0)
```

La suite completa incluye los últimos casos de fallo ATA, el host policy mock
normal/release y UBSan, pruebas reales de CPL3, seis faults contenidos y los
negativos ELF/U-S/fault kernel en ambos perfiles. No se modificó el compilador.
No se ejecutó una campaña de benchmarks ni se atribuye mejora de rendimiento.

El test QEMU nuevo usa una variante de usuario solo para las sondas adicionales:

1. Comprueba en CPL3 la escritura de 512 B binarios a un fd PFS real.
2. Verifica 513 B → EFBIG, puntero 0 → EFAULT, 4097 B → EINVAL.
3. Lee y compara los 512 B para demostrar que los rechazos no alteraron datos.
4. Ejecuta el comando normal `put saved.txt Zen-CPL3-debug` o `...release`,
   lo lee inmediatamente con `cat` y comprueba bytes/tamaño en el disco raw.
5. Reinicia QEMU con la misma imagen y lee/valida exactamente el mismo texto.

Son 4 boots en el test nuevo (2 perfiles × escribir/reiniciar). Todos requieren
status 33, sin timeout ni stderr QEMU, sin FILE ERROR, aislamiento correcto y
`HITO 7 OK`. El mock ATA prueba errores al escribir datos, releer el inodo después
de datos, escribir metadatos y flush; cada uno retorna EIO e invalida la caché.

El runner mantiene la transcripción por defecto congelada: los scripts propios
son rechazados deliberadamente con `shell transcript violates acceptance` y
`passed=false`. El test no ignora fallos de guest: valida status 33, serie,
contenido y tamaño persistido explícitamente. Esta restricción ya existía en
TASK-919 y no se relajó el validador global.

## Métricas y artefactos

Una ejecución adicional con producto sin sondas y disco compartido produjo:

| Perfil/fase | QEMU status | Tiempo (s) |
|---|---:|---:|
| debug / escritura y lectura | 33 | 0.616262 |
| debug / reinicio y lectura | 33 | 0.618265 |
| release / escritura y lectura | 33 | 0.365209 |
| release / reinicio y lectura | 33 | 0.366859 |

| Artefacto | debug (B) | release (B) |
|---|---:|---:|
| ferros-x86_64.elf | 220600 | 65832 |
| ferros-multiboot.elf | 217180 | 64044 |

Logs adicionales: `/tmp/task924-evidence/{summary.json,ferros-tests.log,disk.img}`
y carpetas `boot-False-{0,1}`, `boot-True-{0,1}` con result.json, serial.log,
qemu.stderr.log; builds completos en `build-False` y `build-True`.
Los tiempos son observaciones locales TCG, no benchmarks comparativos.
Consumo adicional de heap por nueva syscall write: 0 B; reserva de caché total
sigue siendo 8192 B. No se midió RSS del host.

## Revisión y riesgos

Revisión independiente final realizada por el orquestador `/root`, distinto
al autor: «no encuentra bloqueo: validación antes de lectura de usuario,
actualización de caché tras flush y pruebas de fallos están cubiertas».
Se atendió su petición preventiva de sondas CPL3 negativas (pasadas en ambos
perfiles). Solicitó dejar estado REVISION hasta integración y registrar los
límites de durabilidad/atomicidad de este informe. El autor no realizó merge.

Límites: una CPU, una syscall activa, sin escrituras del FS desde IRQ; scratch
compartido no admite concurrencia/SMP. Inodos/sectores no tienen checksum ni
recuperación. `boot.txt` protegido, pero los demás archivos PFS no tienen
credenciales por usuario; no hay flags de apertura implementados. Cambios
externos al disco durante ejecución no se sincronizan con la caché. Errores de
escritura pueden dejar cambios duraderos aunque el retorno sea negativo.
La nueva ruta no corrige el consumo de heap por las APIs originales kernel.
