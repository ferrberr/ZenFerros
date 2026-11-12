//! Token definitions for Zen lexer

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Base {
    Binary = 2,
    Octal = 8,
    Decimal = 10,
    Hex = 16,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum IntSuffix {
    I8,
    I16,
    I32,
    I64,
    I128,
    Isize,
    U8,
    U16,
    U32,
    U64,
    U128,
    Usize,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum FloatSuffix {
    F32,
    F64,
}

// TokenKind cannot be Copy due to String variants (Ident, String, Error)
// Use Clone instead
#[derive(Debug, Clone, PartialEq)]
pub enum TokenKind {
    // Literals
    Integer {
        value: u128,
        base: Base,
        suffix: Option<IntSuffix>,
    },
    Float {
        value: f64,
        suffix: Option<FloatSuffix>,
    },
    Bool(bool),
    Char(char),
    String(String),
    Null,

    // Identifiers & Keywords
    Ident(String),
    // Keywords as separate variants for parser convenience
    Fn,
    Let,
    Mut,
    Const,
    If,
    Else,
    While,
    For,
    Return,
    Break,
    Continue,
    Struct,
    Impl,
    Mod,
    Use,
    Pub,
    As,
    Type,
    Enum,
    Match,
    Loop,
    Unsafe,
    Extern,
    Sizeof,
    Alignof,
    Offsetof,
    Cast,
    Transmute,
    True,
    False,

    // Types (primitives as keywords)
    Void,
    Bool_,
    Char_,
    I8,
    I16,
    I32,
    I64,
    I128,
    Isize,
    U8,
    U16,
    U32,
    U64,
    U128,
    Usize,
    F32,
    F64,
    Never,

    // Operators
    Plus,
    Minus,
    Star,
    Slash,
    Percent,
    StarStar,
    EqEq,
    NotEq,
    Lt,
    Gt,
    LtEq,
    GtEq,
    AndAnd,
    OrOr,
    Not,
    Amp,
    Pipe,
    Caret,
    Tilde,
    Shl,
    Shr,
    Assign,
    PlusEq,
    MinusEq,
    StarEq,
    SlashEq,
    PercentEq,
    AmpEq,
    PipeEq,
    CaretEq,
    ShlEq,
    ShrEq,
    Dot,
    DotDot,
    DotDotDot,
    Arrow,
    FatArrow,
    DoubleColon,
    Colon,
    Semi,
    Comma,
    LParen,
    RParen,
    LBracket,
    RBracket,
    LBrace,
    RBrace,
    Pipe2,
    Question,
    At,

    // Special
    /// A comment emitted only by the opt-in comment-preserving lexer mode
    /// (`Lexer::with_comments`). The string is the raw source text, including
    /// its `//` or `/* ... */` delimiters; `true` marks a line comment.
    Comment(String, bool),
    Eof,
    Error(String),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Span {
    pub file_id: usize,
    pub start: u32,
    pub end: u32,
}

impl Span {
    pub fn new(file_id: usize, start: u32, end: u32) -> Self {
        Self {
            file_id,
            start,
            end,
        }
    }

    pub fn merge(self, other: Span) -> Span {
        Span {
            file_id: self.file_id,
            start: self.start.min(other.start),
            end: self.end.max(other.end),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Location {
    pub file_id: usize,
    pub line: u32,
    pub column: u32,
}

#[derive(Debug, Clone)]
pub struct Token {
    pub kind: TokenKind,
    pub span: Span,
}

impl Token {
    pub fn new(kind: TokenKind, span: Span) -> Self {
        Self { kind, span }
    }

    pub fn eof(file_id: usize, pos: u32) -> Self {
        Self::new(TokenKind::Eof, Span::new(file_id, pos, pos))
    }

    pub fn error(file_id: usize, start: u32, end: u32, msg: String) -> Self {
        Self::new(TokenKind::Error(msg), Span::new(file_id, start, end))
    }
}
