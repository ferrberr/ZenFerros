# Lexer self-hosted de Zen — TASK-902

Primer componente del compilador escrito en Zen y compilado por el propio
compilador. Es un lexer **contador** freestanding del subconjunto MVP: recorre
un fuente y clasifica cada token, sin construir valores, spans ni AST. Su
resultado se compara con el lexer Rust de referencia (`zen/compiler/src/lexer`)
sobre los mismos ficheros.

## Alcance

- `zen/selfhost/lexer.zen`: implementación freestanding. Solo usa punteros raw,
  `volatile_load`/`volatile_store`, `while`, `if`, `return`, `break`/`continue`
  de bucle, `let`, `str_len` y `str_byte`; no hay libc, structs, arrays, módulos
  ni floats literales.
- `zen/selfhost/lexer_driver.c`: adaptador de proceso Linux que lee el fichero
  en memoria, llama a `zen_lex_report` e imprime los contadores.
- `zen/selfhost/tests/test_selfhost_lexer.py`: compila, enlaza y compara contra
  `zen lex` sobre los fixtures canónicos más un fixture sintético de lexemas.
- Objeto ELF64 relocatable para `x86_64-unknown-none`, sin símbolos indefinidos
  (`nm -u` vacío) y con `zen_lex_report` exportado (`T`).

## Contrato

```zen
pub fn zen_lex_report(source:u64, length:u64, out:u64)
```

`source` es la dirección del buffer, `length` su longitud en bytes y `out` la
dirección de ocho contadores `u64` que escribe la función:

| Índice | Offset | Contador | Significado |
|---|---|---|---|
| 0 | +0  | `tokens`   | tokens emitidos, sin `Eof` |
| 1 | +8  | `idents`   | `Ident` |
| 2 | +16 | `numbers`  | `Integer` + `Float` |
| 3 | +24 | `strings`  | `String` + `Char` |
| 4 | +32 | `keywords` | keywords y tipos primitivos |
| 5 | +40 | `punct`    | operadores y puntuación |
| 6 | +48 | `errors`   | tokens `Error` |
| 7 | +56 | `bytes`    | bytes consumidos (posición final) |

Invariante para fuentes válidas: `tokens == idents + numbers + strings +
keywords + punct` (los errores también cuentan como token, de ahí que en
fuentes inválidas se sumen a `errors`). `bytes` incluye espacios y comentarios;
en un fuente válido coincide con el tamaño del fichero.

## Compilar y ejecutar

Desde la raíz del repositorio:

```bash
zen/compiler/target/release/zen build zen/selfhost/lexer.zen \
    --target x86_64-unknown-none --emit obj -o /tmp/lexer.o
cc -std=c11 -O2 -fno-pie -no-pie zen/selfhost/lexer_driver.c /tmp/lexer.o \
    -o /tmp/lexer_driver
/tmp/lexer_driver zen/examples/hello.zen
# tokens=16 idents=2 numbers=1 strings=1 keywords=3 punct=9 errors=0 bytes=141
```

El driver no usa el runtime Zen: abre el fichero con libc, reserva el buffer y
pasa direcciones como `u64`. El objeto Zen es el que es freestanding.

## Verificación

```bash
python3 -m unittest discover -s zen/selfhost/tests -v
```

`setUpClass` compila el objeto y enlaza el driver una sola vez en un
`tempfile.TemporaryDirectory`; cada test ejecuta ambos lexers sobre un fichero,
excluye `Eof` de la salida de `zen lex` y compara las ocho categorías. Se
comparan 5 fixtures (4 canónicos + 1 sintético) × 8 contadores = 40
comparaciones, más 2 casos de error directos (carácter inesperado y comentario
de bloque sin cerrar). Resultado actual: **7 tests OK** (incluye `nm -u` vacío).

Además se ejecutó una comprobación diferencial manual sobre **55 ficheros
`.zen`** (recuento manual a fecha de la última comprobación) de `zen/` y `ferros/` (27 fuentes + copias generadas del build):
0 discrepancias en las ocho categorías. Comando de recuento:
`find zen ferros -name '*.zen' -not -path '*/target/*' | wc -l`. No forma parte de la suite para no depender de ficheros de otros
agentes; los fixtures canónicos sí están fijados.

| Fixture | tokens | idents | numbers | strings | keywords | punct | errors | bytes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `zen/examples/hello.zen` | 16 | 2 | 1 | 1 | 3 | 9 | 0 | 141 |
| `zen/examples/factorial.zen` | 66 | 13 | 5 | 2 | 11 | 35 | 0 | 343 |
| `zen/examples/structs.zen` | 336 | 107 | 11 | 4 | 34 | 180 | 0 | 1780 |
| `ferros/kernel/vfs.zen` | 3393 | 660 | 430 | 2 | 520 | 1781 | 0 | 15744 |

El fixture sintético cubre comentarios `/* */` anidados, `//`, escapes de string
(`\"`, `\\`, `\n`, `\t`, `\x41`), char con escape, enteros dec/hex/bin/oct con
sufijos, floats con exponente y sufijo, y todos los operadores del MVP.

## Mapa de categorías

La clasificación replica `TokenKind` (`zen/compiler/src/lexer/token.rs`):

| Categoría | Variantes |
|---|---|
| `idents` | `Ident` |
| `numbers` | `Integer`, `Float` |
| `strings` | `String`, `Char` |
| `keywords` | `Fn`, `Let`, `Mut`, `Const`, `If`, `Else`, `While`, `For`, `Return`, `Break`, `Continue`, `Struct`, `Impl`, `Mod`, `Use`, `Pub`, `As`, `Type`, `Enum`, `Match`, `Loop`, `Unsafe`, `Extern`, `Sizeof`, `Alignof`, `Offsetof`, `Cast`, `Transmute`, `True`, `False`, `Null`, `Bool`, `Void`, `Bool_`, `Char_`, enteros `I8..I128`/`Isize`/`U8..U128`/`Usize`, `F32`, `F64`, `Never` |
| `punct` | cualquier otra variante salvo `Ident`, números, strings, keywords, `Eof` y `Error` |
| `errors` | `Error` |

`Eof` nunca se cuenta. El mapa del test incluye `Null` y `Bool` por completitud,
aunque el lexer Rust actual no los produce: `keywords.rs` no registra `"null"`,
así que `null` es un `Ident` y `TokenKind::Null` es inalcanzable. El lexer
self-hosted mantiene esa paridad estricta; si la referencia empieza a emitir
`Null`, hay que añadir `"null"` a ambos.

## Cobertura léxica

- Espacios ASCII (`' '`, `\t`, `\n`, `\r`, `\v`, `\f`).
- Comentarios de línea `//` y de bloque `/* ... */` con anidamiento por
  profundidad.
- Identificadores ASCII `[A-Za-z_][A-Za-z0-9_]*` y tabla de keywords.
- Enteros con prefijo `0x`/`0X`, `0b`/`0B`, `0o`/`0O`, guiones bajos y sufijos
  `i8..i128`, `isize`, `u8..u128`, `usize`.
- Floats decimales básicos (`1.5`, `1.`, `1e10`, `1.5f64`), con sufijos `f32` y
  `f64`; un `.` seguido de otro `.` no forma float (`1..2`).
- Strings con escapes `\n \t \r \\ \" \' \0 \xHH`, y chars con los mismos
  escapes.
- Operadores: `+ - * / % **`, comparaciones, `&& || ! & | ^ ~ << >>`, todas las
  asignaciones compuestas, `.. ... . -> => ::`, delimitadores y `? @`.

## Límites y desviaciones

- **No construye tokens**: solo cuenta. No valida tipos ni construye AST; un
  fuente válido léxicamente pero inválido sintácticamente también se cuenta.
- **Valores numéricos**: no se calcula el valor. Un entero mayor que `u128` o un
  float no finito/desbordado (`1e999`) serían `Error` en Rust y aquí se cuentan
  como número válido. El driver no ejecuta el parser, así que esto no afecta a
  los fixtures.
- **UTF-8 fuera de comentarios/strings**: el escáner es byte a byte. Los
  identificadores válidos son ASCII; un carácter multibyte inesperado o un char
  literal no ASCII produciría más de un `Error` que el lexer Rust (que avanza un
  `char` completo).
- **Recuperación de errores**: `zen lex` aborta en el primer `Error`, por lo que
  la comparación de contadores solo es posible en fuentes válidos. Los casos de
  error del test comprueban el contador `errors`, no la posición exacta de
  recuperación tras un escape `\x` malformado.
- **`null`**: ver arriba; paridad con la tabla actual, no keyword.
- El driver C usa libc; el objeto Zen no la usa.

## Parser y evaluador (TASK-902B)

`zen/selfhost/parser.zen` (205 líneas) es el segundo componente: un descenso
recursivo freestanding que evalúa expresiones enteras.

```zen
pub fn zen_eval(text:u64, length:u64, out:u64)
```

- `out[0]`: estado (0 ok, 1 sintaxis, 2 división/resto por cero, 3 profundidad >64).
- `out[1]`: valor `u64` con aritmética envolvente.
- Gramática: `expr := term (('+'|'-') term)*`, `term := factor (('*'|'/'|'%') factor)*`,
  `factor := número | '(' expr ')' | '-' factor`; espacios/tabs/CR/LF ignorados.
- El estado y la posición se empaquetan en el `u64` de retorno para no necesitar
  punteros a locales; el driver imprime `status=<n> value=<n>` por línea.
- Sin libc, structs, arrays ni módulos; `nm -u` vacío. Driver C y mismo esquema
  de compilación que el lexer (`--target x86_64-unknown-none --emit obj`).

Verificación: `python3 -m unittest discover -s zen/selfhost/tests -p 'test_selfhost_parser.py' -v`
→ **7 tests OK**, con **95 comparaciones** estado/valor contra un parser de
referencia independiente en Python (43 válidas, 26 errores, 20 de
precedencia/asociatividad y 6 de profundidad), formato exacto y `nm -u` vacío.
El fuzz de 400 expresiones fue manual; el script de estrés (TASK-905) añade
fuzz diferencial reproducible.

## AST real (TASK-902C)

`zen/selfhost/ast_parser.zen` (414 líneas) construye y recorre un AST de
expresiones **sin structs**, con arena de 512 nodos en arrays locales:

```zen
pub fn zen_ast_eval(text:u64, length:u64, out:u64)
```

`out` = [estado (0 ok,1 sintaxis,2 div0,3 arena/profundidad), valor u64, nodos,
checksum FNV-1a de kind/value/left/right]. Nodos en `kinds:[u8;512]`,
`values:[u64;512]`, `lefts/rights:[u32;512]` con centinela 0xFFFFFFFF; pilas
locales para operadores. El AST se construye (shunting-yard) y **se recorre
después** para evaluar; no se reparsea. Verificación: 14 tests, 45 expresiones
válidas, 24 errores, 9 div0, 8 casos de profundidad, AST determinista y distinto
por estructura, `nm -u` vacío. Selfhost total: **166 tests**.

## Lexer con tokens materializados (TASK-902D)

`zen/selfhost/lexer_tokens.zen` materializa tokens en el array del llamador:
`pub fn zen_lex_tokens(source,length,out,max_tokens)->u64` escribe registros de
16 B (`kind u32`, `start u32`, `end u32`, `value u32`) y devuelve el número de
tokens sin Eof. `value` = valor del entero (saturado a u32) o FNV-1a32 de los
bytes del lexema para Ident/String/Char. Sin libc ni estado global; el test
compara **4.369 tokens (~17.300 comprobaciones)** contra `zen lex` en 6
fixtures, valida la tabla de 108 kinds (incluye Comment, inalcanzable en el scanner por defecto) contra `token.rs`, y cubre límites de
capacidad y errores. Exclusiones: floats sin value, enteros >u32 saturados,
whitespace Unicode.

## Intérprete de sentencias (TASK-902E)

`zen/selfhost/interp.zen` (936 líneas) escanea, parsea y **ejecuta** un lenguaje
de sentencias con variables, `if/else`, `while`, aritmética y `print`, todo en
arrays fijos locales:

```zen
pub fn zen_interp(source:u64, length:u64, out:u64) -> u64
```

`out` = [estado (0 ok,1 sintaxis,2 div0,3 variable desconocida,4 límites),
sentencias ejecutadas, FNV-1a32 de la salida, bytes impresos]. Parser iterativo
sin recursión con expresiones en RPN y pila explícita; ejecución sin reparsear.
Límites: 256 nodos, profundidad 32, 16 variables, 256 bytes impresos, 1024
tokens y 1.000.000 de pasos de ejecución. 16 tests comparan ≥30 programas (incluidos límites, errores y
determinismo) con un intérprete de referencia independiente en Python; objeto
sin libc (`nm -u` vacío).

## Intérprete con funciones (TASK-902F)

`zen/selfhost/interp_functions.zen` amplía el intérprete con `fn nombre(a,b){...}`,
parámetros, `return`, llamadas y recursión acotada. Estados adicionales:
5 función desconocida, 6 aridad incorrecta; marcos por invocación, profundidad
≤16, pasos ≤1.000.000. 22 tests contra referencia Python (factorial, fibonacci,
ámbito local, errores y límites); objeto sin libc. Su stack (~177 KiB debug / ~156 KiB
release, medido con `objdump`) supera los 32 KiB de una tarea Ferros: es un
intérprete de host, no un componente ejecutable en usuario.

## Typechecker (TASK-902G)

`zen/selfhost/typecheck.zen` verifica tipos u64/bool de un lenguaje de sentencias:
inferencia en `let`, asignación con tipo exacto, condiciones bool, aritmética u64,
comparaciones mismo tipo, scopes por bloque y shadowing. Estados 0/1/2/3/4,
primer error con resumen FNV estable; límites 512 nodos, 32 profundidad,
32 variables, 1024 tokens. 16 tests contra referencia Python; sin libc. Stack 34,2 KiB (por encima de los 32 KiB de Ferros): componente de host.

## Codegen C (TASK-902H)

`zen/selfhost/codegen.zen` es el primer generador de código en Zen: compila el
lenguaje de sentencias u64/bool a C11 (`uint64_t`/`int`, `printf`, nombres
`v_<slot>`), con emisión directa y paréntesis en operaciones para preservar
precedencia. 16 tests compilan el C con `cc`, lo ejecutan y comparan la salida
con una referencia Python (44 programas válidos + 17 de error/límite); objeto
sin libc. División por cero: comportamiento C, no comprobado. Decisión: ADR-023.

## Codegen con funciones (TASK-902I)

`zen/selfhost/codegen_functions.zen` emite C11 con `fn` de usuario:
`static uint64_t fn_<n>(...)`, parámetros/retorno u64, `return`, llamadas y
recursión, con prototipos antes de `main`. 18 tests compilan el C con
`cc -Wall -Wextra -Werror`, lo ejecutan y comparan con la referencia
(factorial, fibonacci, returns tempranos, errores y límites). Decisión: ADR-023.

## Codegen con arrays (TASK-902J)

`zen/selfhost/codegen_arrays.zen` emite C11 con arrays fijos de u64:
`uint64_t v_n[N] = {...};`, lectura/escritura `v_n[(size_t)(expr)]`, ámbitos y
arrays locales por frame de función. 20 tests compilan/ejecutan el C y lo
comparan con la referencia (39 programas válidos + 53 de error); sin OOB
checks (UB documentado), máx 64 elementos. Decisión: ADR-023.

## Codegen con structs (TASK-902K)

`zen/selfhost/codegen_structs.zen` emite C11 con structs nominales:
`typedef struct { uint64_t f0; ... } zn_N;`, literal campo a campo y acceso
`v.f0`/escritura con `let mut`. 19 tests (18 programas válidos + 26 errores)
compilan/ejecutan el C y comparan con referencia; sin parámetros/retorno de
structs, sin métodos. Decisión: ADR-023.

## Siguiente paso

El **AST real en Zen** ya está implementado (TASK-902C, `ast_parser.zen`):

1. Arena de nodos en arrays paralelos (`kinds: [u8;512]`, `values: [u64;512]`,
   `lefts/rights: [u32;512]`) con raíz e índice; sin structs. Implementado.
2. Construir el AST durante el parseo y **recorrerlo** para evaluar, con checksum
   estructural determinista.
3. Mantener la verificación diferencial contra una referencia independiente y
   ampliar la gramática (declaraciones, tipos) cuando exista AST materializable
   y comparación de estructura, no solo de valor.

Los arrays fijos cubren la necesidad de secuencias; el límite principal restante
para el compilador completo es el AST con spans, la tabla de símbolos con
structs y la stdlib.
