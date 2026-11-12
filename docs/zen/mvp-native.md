# Zen nativo v0.1: subconjunto ejecutable

> Referencia normativa actual: [spec-mvp.md](spec-mvp.md). Este documento conserva ejemplos y notas históricas; ante cualquier diferencia prevalece la especificación vinculada al código activo. La gramática de diseño `syntax-v0.ebnf` no describe exactamente el parser implementado.

## Plataforma y cadena

El primer compilador verificable usa Rust para el frontend, C11 como representación intermedia y `cc` para generar/enlazar ELF en Linux x86_64. No requiere LLVM ni Cranelift. Es un bootstrap: no demuestra self-hosting, freestanding ni rendimiento competitivo. El código de AST/parser anterior en `src/ast/` y `src/parser/` se conserva como borrador histórico sin compilar; `src/mvp.rs` es el parser y comprobador activo. `grammar.lalrpop` no se genera ni se usa.

## Programa mínimo

```zen
fn main() -> i32 {
    print("Hello, Zen!\n");
    return 0;
}
```

Un programa contiene funciones de un archivo; debe definir exactamente `fn main() -> i32`. Se permiten llamadas adelantadas, recursión, parámetros con tipo y retorno explícito. Omitir `->` significa `void`; las funciones no `void` deben retornar en todos los caminos comprobables. Los bucles no se consideran garantía de retorno. No se admiten expresiones finales como retorno implícito.

Tipos admitidos: `u8`, `u16`, `u32`, `i32`, `i64`, `u64`, `bool`, `str`, `void`. `void` solo sirve como retorno. No hay conversiones numéricas implícitas entre variables con tipos distintos. Los literales enteros sin sufijo toman el tipo entero esperado; por defecto son `i32`. Se comprueba su rango, incluidos mínimos negativos y sufijos. `str` es una vista inmutable de bytes UTF-8 de literales estáticos; puede pasarse y retornarse entre funciones, sin asignación dinámica.

## Variables, ámbito y flujo

```zen
fn twice(n: u64) -> u64 { return n * 2; }
fn main() -> i32 {
    let mut n: u64 = 0;
    let mut total: u64 = 0;
    while n < 10 {
        total += n;
        n += 1;
    }
    if total == 45 {
        print_uint(twice(total));
    } else {
        return 1;
    }
    return 0;
}
```

`let` es inmutable, `let mut` permite asignación. Toda variable requiere inicializador. Se permite inferencia (`let n = 3;`), bloques anidados y shadowing en ámbitos interiores; los nombres duplicados dentro del mismo ámbito se rechazan. Parámetros inmutables. Las condiciones requieren `bool`. `break` y `continue` solo son válidos dentro de `while`. Se admiten asignación y `+=`, `-=`, `*=`, `/=`, `%=`.

Operadores: `+ - * / %`, comparaciones `== != < <= > >=`, `&& ||`, negación `-` y `!`, paréntesis. El Hito 2 añade casts `as`, operadores `& | ^ ~ << >>` y asignaciones compuestas; véase `freestanding.md` para su semántica. La evaluación de operandos y argumentos es de izquierda a derecha. `&&` y `||` hacen cortocircuito. Los nombres se traducen a identificadores C internos para evitar colisiones con C y el runtime.

Los enteros tienen anchura fija; suma, resta, multiplicación y negación con desbordamiento envuelven en complemento a dos. División y resto por cero, y división o resto del mínimo firmado entre `-1`, terminan el programa con error. No se usa overflow firmado de C. El comportamiento debe coincidir con y sin `--release`.

## Salida estándar y errores

Funciones incorporadas reservadas (hosted):

| Función | Firma | Efecto |
|---------|-------|--------|
| `print` | `fn(str) -> void` | Escribe bytes, sin añadir salto de línea; conserva NUL |
| `print_uint` | `fn(u64) -> void` | Decimal sin signo |
| `print_int` | `fn(i64) -> void` | Decimal con signo |

`print_int` requiere `i64`: por ejemplo `print_int(42i64)`. Los escapes implementados son `\n`, `\t`, `\r`, `\\`, `\"`, `\'`, `\0` y `\xHH` (valor de carácter U+00HH, codificado después en UTF-8). Los identificadores son ASCII. Los comentarios `//` y `/* ... */` anidados se ignoran. Errores léxicos, sintácticos y semánticos incluyen ruta y posición; devuelven estado distinto de cero sin generar ejecutable.

`str_len(str) -> u64` y `str_byte(str, u64) -> u8` se admiten en ambos modos desde el Hito 2, con longitud en bytes y comprobación de límites. Desde TASK-901A se añaden `str_eq`, `str_cmp` y `str_find`, y desde TASK-901B `str_starts_with`, `str_ends_with` y `str_rfind`, como builtins sin libc en ambos modos. `extern "C"` importa funciones bajo `unsafe`; `pub` en hosted mantiene nombres internos y no exporta nombres C.

## Slices `[u64]` (TASK-915)

`fn sum(s: [u64]) -> u64` recibe una vista `{puntero, longitud}`; al pasar un array local `[u64; N]` no se copia y las escrituras del callee se ven en el caller. `s[i]` comprueba límites en runtime y `slice_len(s)` devuelve la longitud. Los slices solo valen como parámetro: no hay locales, retorno, copia, comparación, campos ni ABI C. Sin tracking de aliasing: un array no-`mut` puede mutarse a través de un slice. `zen/std/array.zen` ofrece suma/max/reverse/sort/contains (ADR-026).

## Structs nominales (TASK-214)

```zen
struct Token { kind: u64, start: u64, valid: bool }

fn main() -> i32 {
    let mut token: Token = Token { kind: 7u64, start: 12u64, valid: true };
    token.start = 13u64;
    token.valid = false;
    print_uint(token.kind); print("\n");
    return 0;
}
```

- `struct Name { campo: T, ... }` de nivel superior, campos escalares; debe declararse **antes** de usarse (parser de una pasada).
- Construcción `Name { campo: expr, ... }` solo como inicializador directo de `let [mut] p[: T] = ...`; campos exactos y tipos exactos; evaluación en orden fuente.
- Acceso `p.campo` y escritura `p.campo = ...`/compuestas; escritura solo con `let mut`; un solo nivel (`p.a.b` se rechaza).
- Struct como parámetro, retorno, extern, copia, asignación completa, comparación, cast, campo de struct o array de struct → diagnóstico localizado. Sin métodos, genéricos, anidamiento ni campos array/ptr/str/void; struct vacío rechazado.
- Emisión C: `typedef struct { ... } __zen_Struct_Name;` con miembros posicionales internos; layout natural, sin ABI externa de structs.

## Arrays de tamaño fijo (TASK-213)

```zen
fn main() -> i32 {
    let mut values: [u64; 4] = [1u64, 2u64, 3u64, 4u64];
    let mut i: u64 = 0u64;
    while i < 4u64 {
        values[i] = values[i] * 2u64;
        i += 1u64;
    }
    print_uint(values[3]);
    print("\n");
    return 0;
}
```

- Tipo `[T; N]` con `T` escalar (`u8/u16/u32/i32/i64/u64/bool`) y `N` literal entero sin sufijo >0. La anotación es obligatoria: no hay inferencia de arrays desde `let a = [1,2];`.
- Inicializadores `[e1,e2,...]` (longitud exacta) y repetición `[e; N]`. El valor de `[e; N]` se evalúa una sola vez antes del bucle de copia.
- Lectura `a[i]` y escritura `a[i] = ...`/compuestas (`+=`…`>>=`). El índice se evalúa una vez y antes de `__zen_index_check`; fuera de rango termina con `Zen runtime error: array index out of bounds`: stderr + estado 1 en hosted, `ud2` en freestanding. Sin comportamiento indefinido.
- Solo variables locales. Arrays como valor completo (retorno, copia, comparación, asignación completa, cast) y `.len`/multidimensionales/puntero a array se rechazan; **sí** se pasan como slice `[u64]` a funciones (TASK-915).
- Sin `.len`: la longitud vive en el tipo; usa `N` explícito en el código.
- El índice puede ser cualquier entero (`u8`…`u64`, `i32`, `i64`); los valores negativos o fuera de rango fallan la comprobación.

## Límites

Sin métodos, floats, referencias, módulos, genéricos, ownership, heap, optimizaciones propias ni API de sistema operativo. Arrays fijos (TASK-213) y structs escalares locales (TASK-214) existen con las restricciones anteriores. Los punteros raw y la FFI escalar del Hito 2 se describen en `freestanding.md`. No hay entrada argv en Zen, aunque `zen run -- ...` pasa argumentos al proceso nativo. No hay compilación cruzada general; el perfil freestanding x86_64 requiere GCC anfitrión compatible. El parser limita su profundidad recursiva interna a 128 y el AST de expresiones a 64 niveles; entradas que superan estos límites producen un diagnóstico localizado. No se promete recuperación de errores múltiples. La gramática completa es una propuesta y no amplía automáticamente este subconjunto.
