# Zen freestanding mínimo — Hito 2

## Alcance demostrado

Zen genera un objeto ELF64 x86_64 relocatable sin libc, startup hosted ni runtime obligatorio del anfitrión. El perfil `x86_64-unknown-none` utiliza GCC x86_64 mediante el backend C; no es una toolchain de compilación cruzada general. La sintaxis generada incluye aliases de símbolos `__asm__`, extensión de GCC. Se verifican objetos, ABI C y un ejecutable estático sin bibliotecas. Este ejecutable de prueba usa un adaptador Linux para observar resultados; el arranque de Ferros en QEMU corresponde al Hito 3.

## Uso

Desde la raíz del repositorio, con Cargo y herramientas GCC/binutils:

```bash
rtk proxy env CARGO_HOME="$PWD/.cargo" cargo build --release --offline --manifest-path zen/compiler/Cargo.toml
rtk proxy zen/compiler/target/release/zen check zen/examples/freestanding.zen --target x86_64-unknown-none
rtk proxy zen/compiler/target/release/zen build zen/examples/freestanding.zen --target x86_64-unknown-none --emit obj -o /tmp/zen-free.o
rtk proxy nm -u /tmp/zen-free.o
# U emit_byte  (import explícito, lo aporta el adaptador o el kernel)
rtk proxy python3 infrastructure/scripts/verify_freestanding.py
# debug: ELF64 object + static no-libc executable verified; Zen freestanding OK
# optimized: ELF64 object + static no-libc executable verified; Zen freestanding OK
```

`--emit obj` produce `.o`; `--emit c` produce C validado para inspección, sin ejecutar CC. El nombre de salida por defecto sustituye `.zen` por `.o` o `.c`. El modo hosted conserva `--emit exe` como valor por defecto. Un build freestanding requiere `--emit obj` o `--emit c`: el usuario aporta el punto de entrada y el script de enlace. `zen run` sigue ejecutando programas hosted.

`verify_freestanding.py` guarda objetos, ELF, métricas y comandos en `zen/compiler/target/milestone-2/`. Enlaza con `ld -nostdlib -static`, comprueba que no hay INTERP/NEEDED ni símbolos sin resolver, ejecuta ambos modos y exige stdout exacto y estado 0. No ejecuta instrucciones privilegiadas ni accede a hardware físico. El archivo `infrastructure/freestanding/linux_test.ld` es un layout de proceso Linux; no es el layout del kernel Ferros.

## ABI externa

```zen
extern "C" {
    fn emit_byte(value: u8);
}
pub fn kernel_entry() -> i32 {
    unsafe { emit_byte(65u8); }
    return 0;
}
```

En freestanding, `pub fn` exporta el nombre Zen como símbolo C System V AMD64. Las funciones privadas mantienen símbolos internos. Se permiten parámetros y retornos escalares (`u8/u16/u32/u64/i32/i64/bool`) y punteros raw; `void` es solo retorno. No se permite `str` en la frontera ABI. Las declaraciones extern solo aceptan ABI "C" y sus llamadas requieren unsafe. La firma y la implementación externa deben coincidir; no hay comprobación automática de la biblioteca enlazada.

En hosted, `pub` expresa visibilidad sin publicar el nombre C: se conserva el nombre interno para que funciones Zen llamadas printf/fwrite no puedan sustituir accidentalmente libc. Las declaraciones extern mantienen su significado de import en ambos modos. El prefijo externo `__zen_` está reservado al compilador.

## Enteros, bits y casts

Tipos adicionales: `u8`, `u16`, `u32`, con tamaño y rango fijos. Los literales aceptan esos sufijos. Las operaciones `+ - *` envuelven según anchura; las comparaciones y asignaciones mantienen comprobación estricta de tipos. `expr as T` convierte entre enteros explícitamente: estrechar descarta bits altos y una conversión a firmado interpreta los bits de destino en complemento a dos.

Operadores añadidos: `& | ^ ~ << >>` y asignaciones compuestas. Los shifts conservan el tipo izquierdo; el contador puede ser otro entero, los literales sin sufijo se contextualizan como u64. Contadores negativos o mayores/iguales que la anchura producen trap. El shift derecho de enteros firmados extiende el signo; el izquierdo descarta bits altos. Los operandos y argumentos siguen evaluándose de izquierda a derecha.

## Punteros y volatile

```zen
pub fn set_register(address: u64) -> u32 {
    unsafe {
        let register: *mut u32 = address as *mut u32;
        volatile_store(register, 0x12345678u32);
        return volatile_load(register);
    }
}
```

`*T` es raw pointer de lectura y `*mut T` permite escritura; T se limita a los enteros admitidos. El puntero no posee memoria. `volatile_load(p)` retorna T, `volatile_store(p, value)` requiere puntero mutable y value:T. Ambas operaciones requieren unsafe. Los casts raw pointer↔u64 también requieren unsafe. No se permite aritmética de punteros ni desreferencia general, ni referencias/lifetimes/borrowing en este subconjunto.

`unsafe` es un bloque de statements con ámbito local, no una expresión con valor. Corresponde al autor garantizar que la dirección esté mapeada, sea válida, esté alineada y tenga permisos y duración adecuados. Volatile no proporciona atomicidad, barreras de memoria ni sincronización entre núcleos. Las pruebas acceden solo a buffers válidos del proceso; este ejemplo no se debe llamar con una dirección de hardware en el host.

## Cadenas y errores sin libc

Los literales `str` son vistas estáticas UTF-8 de datos de solo lectura; `str_len` retorna número de bytes como u64 y `str_byte` retorna u8 con comprobación de límites. Esto permite recorrer mensajes y enviar bytes por un helper externo, sin stdio. `print`, `print_int` y `print_uint` solo se incorporan al modo hosted.

Los errores de ejecución del modo freestanding (división/resto inválido, contador shift inválido, índice de cadena fuera de rango) ejecutan un trap nativo (`ud2` en x86_64). No hay formato de mensajes, unwinding ni dependencia de libc. Un kernel necesitará gestionar la excepción; el Hito 2 no incluye IDT ni manejador de panic configurable.

## Código máquina y límites

El compilador desactiva red zone, stack protector, PIC/PIE, SIMD y unwind para los objetos freestanding, con code model kernel y secciones por función/datos. Los flags concretos están en ADR-008 y se comprueban en tests. Sin salida flotante, i128, objetos globales mutables del lenguaje, layout empaquetado/ABI externa de structs, atributos de sección explícitos, inline asm Zen ni toolchain multi-arquitectura. Arrays fijos y structs escalares locales se emiten también en freestanding. La entrada de arquitectura puede escribirse como helper C/ensamblador y llamarse mediante extern C. El lenguaje de sistemas se ampliará según las necesidades comprobadas del boot.

El parser sigue limitando su recursión a 128 y el AST de expresiones a 64, incluyendo casts, bit-not y bloques unsafe. Hito 2 no implica seguridad de memoria de direcciones raw, estabilidad del kernel ni rendimiento competitivo.
