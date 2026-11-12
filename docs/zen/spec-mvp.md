# Zen MVP implementado

**Estado:** especificación descriptiva del compilador Rust activo (`zen/compiler/src/mvp.rs`), no diseño del lenguaje futuro. La aceptación depende de `mvp::check`/`emit_c`; que el lexer reconozca un token no significa que pueda usarse en un programa. El parser LALRPOP y `docs/zen/syntax-v0.ebnf` son históricos/propuesta y no definen este contrato.

## Unidad de compilación

Un archivo contiene declaraciones de `struct`, funciones y bloques `extern "C"`. `zen build`, `zen run` y `zen check` aceptan al inicio de cada archivo `use "ruta.zen";`: el resolvedor expande los archivos como inclusión textual, sin namespaces ni sistema de módulos. No hay constantes globales, aliases, implementaciones, genéricos ni atributos. Los structs se declaran antes de usarse. Las funciones pueden llamarse antes de su definición y recursivamente. Una función es `fn nombre(param: Tipo, ...) [-> Tipo] { ... }`; sin retorno explícito el retorno es `void`. `pub` se acepta ante funciones. El modo hosted exige exactamente una entrada definida `fn main() -> i32` sin parámetros. `extern "C" { fn nombre(...); }` importa símbolos; sus llamadas requieren `unsafe`.

```ebnf
archivo    = { use_directiva } programa ;
use_directiva = "use" string_ruta ";" ;
programa   = { struct_decl | ["pub"] funcion | extern_block } ;
struct_decl= "struct" ident "{" campo { "," campo } [","] "}" ;
campo      = ident ":" escalar ;
funcion    = "fn" ident "(" [param { "," param } [","]] ")" ["->" tipo] bloque ;
param      = ident ":" tipo ;
extern_block = "extern" string_C "{" { "fn" ident "(" [param { "," param }] ")" ["->" tipo] ";" } "}" ;
tipo       = escalar | "str" | "void" | puntero | array | "[" "u64" "]" | ident_struct ;
escalar    = "u8" | "u16" | "u32" | "i32" | "i64" | "u64" | "bool" ;
puntero    = "*" ["mut"] ("u8"|"u16"|"u32"|"u64"|"i32"|"i64") ;
array      = "[" elem_array ";" entero_sin_sufijo_positivo "]" ;
elem_array = "u8" | "u16" | "u32" | "u64" | "i32" | "i64" | "bool" ;
bloque     = "{" { sentencia } "}" ;
sentencia  = let | asignacion ";" | expresion ";" | "return" [expresion] ";"
           | "if" expresion bloque ["else" (bloque | sentencia)]
           | "while" expresion bloque | "unsafe" bloque | bloque
           | "break" ";" | "continue" ";" ;
let        = "let" ["mut"] ident [":" tipo] "=" expresion ";" ;
```

Expresiones: enteros, `true`/`false`, literales string, variables, llamadas por nombre, paréntesis, prefijos `-`, `!`, `~`, casts `as Tipo`, indexado, acceso a campo, literales de array y literales de struct. No hay expresiones de bloque, `if` expresión, llamadas a valores ni sufijos postfix distintos de `[]` y `.campo`.

Precedencia (alta a baja): postfix `[] .`; unarios/casts (`- ! ~`, `as`); `* / %`; `+ -`; `<< >>`; `&`; `^`; `|`; `< <= > >=`; `== !=`; `&&`; `||`. Binarios son asociativos a izquierda. Asignación no es expresión. `&&` y `||` hacen cortocircuito.

## Tipos y reglas estáticas

- Enteros exactos `u8/u16/u32/u64/i32/i64`, `bool`, `str`, y retorno `void`. Tipos de variables/argumentos/retornos deben coincidir exactamente; no hay coerciones entre variables. `void` no puede ser parámetro ni local.
- Literales enteros soportan bases decimal/hex/binaria/octal, separadores `_` y sufijos aceptados `u8/u16/u32/u64/i32/i64`. También existen sufijos léxicos `i8/i16/i128/isize/u128/usize`, pero se rechazan en el compilador nativo. Sin sufijo, el tipo se infiere por contexto numérico o es `i32`; se comprueba rango, incluido el mínimo signed con unary minus.
- Las operaciones enteras conservan anchura; aritmética suma/resta/multiplicación/negación envuelve en complemento a dos. Dividir/remainder por cero y `MIN / -1` o `MIN % -1` son error de ejecución. Los shifts permiten contador entero independiente; contador negativo o >= anchura es error. `>>` sobre signed extiende signo. Comparaciones producen `bool`; igualdad admite además `bool`. No hay aritmética float ni comparación de cadenas.
- `str` solo proviene de literal estático UTF-8; es vista bytes+longitud, puede viajar por parámetros/retornos Zen, no se asigna ni modifica. `str_len` mide bytes; `str_byte` comprueba el índice.
- Variables requieren inicializador. `let` inmutable; `let mut` mutable. Parámetros son inmutables. Se permiten ámbitos anidados y shadowing interior; nombres duplicados en el mismo ámbito se rechazan. Asignaciones simples y `+= -= *= /= %= &= |= ^= <<= >>=`; `break` y `continue` solo dentro de `while`. Condiciones deben ser `bool`. No hay retorno implícito; funciones no-void deben retornar en ambos lados de un `if/else`; bucles no prueban retorno.
- Profundidad sintáctica máxima 128 y profundidad de AST de expresión 64; el exceso produce diagnóstico.

## Arrays, slices y structs

- `[T; N]` es local, con `N` literal sin sufijo mayor que cero y `T` escalar de `elem_array`. Requiere anotación de tipo e inicializador `[e1, ...]` de longitud exacta o `[e; N]` de longitud coincidente (evalúa `e` una vez). Solo indexado; índices enteros se evalúan una vez y se comprueban en ejecución. No se lee/pasa/retorna/copia/asigna el array completo; no hay arrays multidimensionales ni `.len`.
- `[u64]` es parámetro de función únicamente; al llamar se acepta un array local `[u64;N]` como vista pointer+longitud sin copia. El callee puede leer o escribir sus elementos incluso si el array original se declaró `let` inmutable: no hay tracking de aliasing. `slice_len` devuelve longitud. No hay retorno/local/asignación de slice ni ABI C de slices.
- Struct nominal con uno o más campos escalares `u8/u16/u32/i32/i64/u64/bool`; se declara antes de uso, no puede tener campos repetidos. Solo variable local inicializada directamente con `Nombre { campo: expresión, ... }`; deben aparecer todos los campos una vez y con tipos exactos. `p.campo` y escritura (incluidas compuestas) en variable `let mut`. No admite paso/retorno/extern/copia/comparación/arrays/campos anidados/métodos.

## Punteros, unsafe y FFI

Tipos raw de un nivel: `*T` o `*mut T`, donde `T` es entero de ancho fijo (`u8/u16/u32/u64/i32/i64`). No hay desreferencia general, aritmética de punteros, referencias, borrowing ni ownership. `unsafe { sentencias }` habilita llamadas extern C, accesos volatile y casts pointer↔`u64`; no convierte esas operaciones en seguras. `volatile_load(ptr)` retorna el tipo apuntado; `volatile_store(ptr, valor)` exige `*mut T`. Volatile no es atomicidad/sincronización.

ABI C: solo tipos escalares y punteros raw en la frontera; sin `str`, slices, arrays ni structs. Extern solo ABI `"C"`. `pub fn` exporta nombre C solo en freestanding; en hosted se mantiene interno. `main` hosted es especial y debe ser `fn main() -> i32`.

## Builtins y destinos

Siempre disponibles: `str_len(str)->u64`, `str_byte(str,u64)->u8`, `str_eq(str,str)->bool`, `str_cmp(str,str)->i32`, `str_find(str,str)->i64`, `str_starts_with(str,str)->bool`, `str_ends_with(str,str)->bool`, `str_rfind(str,str)->i64`, `slice_len([u64])->u64`. `volatile_load/store` son intrínsecos reservados, no funciones ordinarias. Hosted añade `print(str)`, `print_uint(u64)` y `print_int(i64)`, con retorno void. El modo freestanding emite objeto/C sin libc ni startup; usa GCC x86_64 del anfitrión y requiere que el usuario aporte entry point/enlace. No es cross-compilación general.

## Sintaxis reconocida pero rechazada

El lexer también reconoce `for`, `const`, `impl`, `mod`, `type`, `enum`, `match`, `loop`, `char`, floats, `null`, y tokens/sufijos más amplios. Eso no los implementa: no son producción válida del parser/comprobador MVP. `use` sí se acepta como directiva inicial de inclusión textual mediante `module::resolve`; no es una declaración del parser MVP y `fmt`/`lint`/`lsp` no la expanden. También se rechazan floats, `i8/i16/i128/isize/u128/usize`, referencias, tuplas, genéricos, aliases, módulos, globals, constantes, métodos, `for`, `loop`, `match`, `enum`, `char`, `null`, `**`, funciones externas no C y constructos de la gramática propuesta.

## Evidencia de mantenimiento

El parser/typechecker/emisor está en [mvp.rs](../../zen/compiler/src/mvp.rs); lexer en `zen/compiler/src/lexer/`. Regresiones: `zen/compiler/src/mvp.rs` (tests unitarios incluidos al final del módulo), `tests/native_cli.rs`, `tests/freestanding_cli.rs`, `tests/arrays_cli.rs`, `tests/slices_cli.rs`, `tests/structs_cli.rs`. Pruebas de aceptación actuales deben ejecutarse con Cargo offline desde `zen/compiler`.

Esta especificación sustituye a `docs/zen/mvp-native.md` como referencia normativa. `docs/zen/syntax-v0.ebnf` se conserva únicamente como propuesta histórica y no como gramática del compilador actual.
