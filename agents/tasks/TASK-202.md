# TASK-202: Implementar Lexer para Zen

**Agente**: 02 (Frontend Zen)
**Estado**: MVP INTEGRADO (TASK-212); alcance completo de gramática pendiente de auditoría
**Prioridad**: ALTA
**Dependencias**: [TASK-201, TASK-101]

## Objetivo
Implementar un lexer (análisis léxico) para Zen basado en la gramática EBNF v0.1, produciendo tokens para el parser.

## Criterios de Aceptación
- [ ] Lexer completo en `zen/compiler/src/lexer/`
- [ ] Token types definidos cubriendo toda la gramática léxica
- [ ] Manejo de: identificadores, keywords, literales (int, float, bool, char, string), operadores, puntuación
- [ ] Comentarios: `//` line, `/* */` block (anidados)
- [ ] Source location tracking (file, line, column, span)
- [ ] Error reporting con codespan (diagnostics)
- [ ] Tests unitarios para cada token type
- [ ] Integration test: lexer examples/hello.zen → tokens válidos

## Arquitectura Propuesta

```
zen/compiler/src/
├── lexer/
│   ├── mod.rs          # Public API: Lexer, Token, TokenKind
│   ├── token.rs        # TokenKind enum, Token struct
│   ├── scanner.rs      # Core scanning logic
│   ├── keywords.rs     # Keyword lookup table
│   └── tests.rs        # Unit tests
├── diagnostics/
│   └── mod.rs          # Error types, codespan integration
└── main.rs             # CLI (existing)
```

## TokenKind Enum (Borrador)

```rust
#[derive(Debug, Clone, PartialEq)]
pub enum TokenKind {
    // Literals
    Integer { value: u128, base: Base, suffix: Option<IntSuffix> },
    Float { value: f64, suffix: Option<FloatSuffix> },
    Bool(bool),
    Char(char),
    String(String),
    Null,
    
    // Identifiers & Keywords
    Ident(String),
    // Keywords as separate variants for parser convenience
    Fn, Let, Mut, Const, If, Else, While, For, Return, Break, Continue,
    Struct, Impl, Mod, Use, Pub, As, Type, Enum, Match, Loop, Unsafe, Extern,
    Sizeof, Alignof, Offsetof, Cast, Transmute,
    True, False,
    
    // Types (primitives as keywords)
    Void, Bool_, Char_, 
    I8, I16, I32, I64, I128, Isize,
    U8, U16, U32, U64, U128, Usize,
    F32, F64,
    Never,
    
    // Operators
    Plus, Minus, Star, Slash, Percent, StarStar,
    EqEq, NotEq, Lt, Gt, LtEq, GtEq,
    AndAnd, OrOr, Not,
    Amp, Pipe, Caret, Tilde, Shl, Shr,
    Assign, PlusEq, MinusEq, StarEq, SlashEq, PercentEq, AmpEq, PipeEq, CaretEq, ShlEq, ShrEq,
    Dot, DotDot, DotDotDot, Arrow, FatArrow, DoubleColon,
    Colon, Semi, Comma, LParen, RParen, LBracket, RBracket, LBrace, RBrace, Pipe2, Question, At,
    
    // Special
    Eof,
    Error(String),
}
```

## Source Location

```rust
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Span {
    pub file_id: usize,
    pub start: u32,   // byte offset
    pub end: u32,     // byte offset
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Location {
    pub file_id: usize,
    pub line: u32,
    pub column: u32,
}
```

## Integración con codespan-reporting

- `Diagnostic` struct con `Level`, `Message`, `Labels` (primary/secondary)
- `FileMap` para source code storage
- Emitir diagnósticos en lexer errors (invalid escape, unterminated string, etc.)

## Próximos Pasos

1. Crear estructura de módulos en `zen/compiler/src/lexer/`
2. Implementar `TokenKind` y `Token`
3. Implementar `Scanner` con cursor sobre source string
4. Keyword recognition (perfect hash o trie)
5. Literal parsing (int bases, float, escapes)
6. Operator/punctuation recognition (longest match)
7. Comment handling (nested block comments)
8. Tests unitarios exhaustivos
9. Test integración con `zen/examples/hello.zen`

---

*Tarea creada por Orquestador basado en entrega Agente 01 — Ver `AGENTS.md`*
## Recuperación en Codex — 2026-11-11
Lexer integrado con compilación nativa; 18 tests léxicos pasan. TASK-212 corrige corrupción silenciosa de literales y operadores; TASK-211 revisa el cambio. Las casillas originales de alcance completo no se marcan sin comprobarlas individualmente.
