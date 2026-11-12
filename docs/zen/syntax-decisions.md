# Decisiones de Sintaxis Zen v0

**Autor**: Agente 01 (Arquitecto Zen)
**Fecha**: 2026-11-10
**Estado**: BORRADOR — Pendiente revisión cruzada (Agente 02)

---

## Principios Rectores

1. **Legibilidad sobre brevedad extrema** — Código se lee más que se escribe
2. **Familiaridad para programadores de sistemas** — Rust/C/C++ developers productive day 1
3. **Parseabilidad LR(1)** — Sin ambigüedades, parser generable con lalrpop
4. **Extensibilidad** — Keywords reservadas para features futuras
5. **Optimizable** — Sintaxis que no impide inlining, monomorfización, LTO

---

## Decisiones Clave

### 1. Declaración de Funciones: `fn name(params) -> ret { body }`

**Alternativas consideradas:**
- `func name(params) ret { body }` (Go-style) — más verboso
- `name(params): ret = { body }` (Zig-style) — confunde con type ascription
- `def name(params) -> ret: body` (Python-style) — indentation-sensitive, no

**Decisión**: `fn` — familiar, claro, permite atributos `#[inline]` antes.

### 2. Variables: `let mut x: type = expr;` / `const X: type = expr;`

**Decisiones:**
- `let` obligatorio (no inferencia implícita como `x = 1`)
- `mut` keyword separada (no `let mut x` vs `var x`)
- Type annotation opcional si hay inicializador con tipo obvio
- `const` para compile-time constants, `static` para globals

**Razón**: Explícito, evita shadowing accidents, type inference local.

### 3. Tipos Primitivos: Nombres con tamaño explícito

```
i8 i16 i32 i64 i128 isize    // signed
u8 u16 u32 u64 u128 usize    // unsigned
f32 f64                      // float
bool char                    // bool, unicode scalar
void never                   // unit, bottom type
```

**Por qué no** `int`/`uint`/`float`: Ambigüedad de tamaño rompe ABI y optimización.

### 4. Punteros y Referencias: Tres niveles

| Sintaxis | Significado | Uso |
|----------|-------------|-----|
| `&T` / `&mut T` | Referencia segura (borrowed) | Application code |
| `*const T` / `*mut T` | Raw pointer (unsafe) | FFI, kernel, allocators |
| `&&T` / `&&mut T` | Raw pointer alternativo | Explicit unsafe marker |

**Decisión**: `&&` para raw pointers en lugar de solo `*`.
**Razón**: Visual distinction fuerte — `&` = safe borrow, `&&` = "double reference" = raw/unsafe. Evita confusión `*T` (deref) vs `*T` (pointer type).

### 5. Casting: `expr as Type`

**Alternativas**: `cast(expr, Type)`, `(Type)expr`, `expr:Type`
**Decisión**: `as` — Rust-compatible, claro, no confunde con type ascription.

### 6. Control de Flujo

- `if expr { } else { }` — expression o statement
- `while expr { }` — solo statement
- `loop { }` — infinite loop
- `match expr { pat => expr, ... }` — exhaustivo, pattern matching
- `for pat in expr { }` — reservado para iteradores (Fase 2+)

**No**: `do-while`, `switch` (usa `match`), ternary `? :` (usa `if` expr).

### 7. Structs e Impl Separados

```zen
struct Point { x: f64, y: f64 }
impl Point {
    fn new(x: f64, y: f64) -> Self { ... }
    fn distance(&self, other: &Point) -> f64 { ... }
}
```

**Por qué no** métodos dentro de struct: Separación de datos/comportamiento, permite `impl` para tipos externos (extension methods), `impl` multiples para traits futuros.

### 8. Módulos: Sistema de archivos = módulos

```
src/
  lib.zen          // crate root
  math/
    mod.zen        // modulo math
    vec.zen        // modulo math::vec (archivo)
  io.zen           // modulo io
```

`mod name;` declara submódulo, `use path::to::item;` importa.
Visibilidad: `pub` = público, default = privado al módulo.

### 9. Manejo de Errores MVP: `Result<T, E>` + `?` operator

```zen
fn read_file(path: &str) -> Result<String, IOError> { ... }

fn main() -> i32 {
    let content = read_file("test.txt")?;  // propaga error
    print(content);
    return 0;
}
```

**No exceptions**, **no panic por defecto**. `panic!` solo para bugs invariants.

### 10. Keywords Reservadas (Futuras Fases)

| Categoría | Keywords |
|-----------|----------|
| Async | `async`, `await`, `yield`, `generator` |
| Traits/Generics | `trait`, `interface`, `where`, `associated`, `type` |
| Memory | `own`, `borrow`, `region`, `arena`, `drop`, `move` |
| Unsafe | `unsafe`, `transmute`, `cast`, `offsetof`, `alignof`, `sizeof` |
| Attributes | `inline`, `noinline`, `cold`, `hot`, `export`, `link_section` |
| Meta | `macro`, `macro_rules`, `const_eval`, `comptime` |

---

## Comparación Rápida

| Feature | Zen | Rust | Zig | C |
|---------|-----|------|-----|---|
| Function | `fn` | `fn` | `fn` | `type name()` |
| Variable | `let mut` | `let mut` | `var` | `type name =` |
| Pointer | `&T`, `&&T` | `&T`, `*T` | `*T` | `T*` |
| Cast | `as` | `as` | `@as` | `(Type)` |
| Struct | `struct`+`impl` | `struct`+`impl` | `struct` | `struct` |
| Module | `mod`/`use` | `mod`/`use` | `@import` | `#include` |
| Error | `Result`+`?` | `Result`+`?` | `!E`/try | errno |
| Pattern Match | `match` | `match` | `switch` | - |

---

## Próximos Pasos

1. **Revisión cruzada** por Agente 02 (Frontend) — verificar parseabilidad LR(1)
2. **Prototipo lexer** con casos de test — validar tokens
3. **Definir precedencia exacta** en parser generator (lalrpop)
4. **Resolver ambigüedades** conocidas:
   - `x * y` — multiplicación vs pointer deref en tipo
   - `foo < bar > (baz)` — comparison vs generic args
   - Solución: context-sensitive en lexer o parser

---

*Documento vivo — Actualizar tras cada revisión*