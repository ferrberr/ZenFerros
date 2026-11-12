//! Keyword lookup for Zen lexer

use crate::lexer::token::TokenKind;
use phf::phf_map;

pub static KEYWORDS: phf::Map<&'static str, TokenKind> = phf_map! {
    "fn" => TokenKind::Fn,
    "let" => TokenKind::Let,
    "mut" => TokenKind::Mut,
    "const" => TokenKind::Const,
    "if" => TokenKind::If,
    "else" => TokenKind::Else,
    "while" => TokenKind::While,
    "for" => TokenKind::For,
    "return" => TokenKind::Return,
    "break" => TokenKind::Break,
    "continue" => TokenKind::Continue,
    "struct" => TokenKind::Struct,
    "impl" => TokenKind::Impl,
    "mod" => TokenKind::Mod,
    "use" => TokenKind::Use,
    "pub" => TokenKind::Pub,
    "as" => TokenKind::As,
    "type" => TokenKind::Type,
    "enum" => TokenKind::Enum,
    "match" => TokenKind::Match,
    "loop" => TokenKind::Loop,
    "unsafe" => TokenKind::Unsafe,
    "extern" => TokenKind::Extern,
    "sizeof" => TokenKind::Sizeof,
    "alignof" => TokenKind::Alignof,
    "offsetof" => TokenKind::Offsetof,
    "cast" => TokenKind::Cast,
    "transmute" => TokenKind::Transmute,
    "true" => TokenKind::True,
    "false" => TokenKind::False,
    "void" => TokenKind::Void,
    "bool" => TokenKind::Bool_,
    "char" => TokenKind::Char_,
    "i8" => TokenKind::I8, "i16" => TokenKind::I16, "i32" => TokenKind::I32, "i64" => TokenKind::I64, "i128" => TokenKind::I128, "isize" => TokenKind::Isize,
    "u8" => TokenKind::U8, "u16" => TokenKind::U16, "u32" => TokenKind::U32, "u64" => TokenKind::U64, "u128" => TokenKind::U128, "usize" => TokenKind::Usize,
    "f32" => TokenKind::F32, "f64" => TokenKind::F64,
    "never" => TokenKind::Never,
};

pub fn is_keyword(s: &str) -> bool {
    KEYWORDS.contains_key(s)
}

pub fn keyword_kind(s: &str) -> Option<TokenKind> {
    KEYWORDS.get(s).cloned()
}
