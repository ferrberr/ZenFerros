//! Type system AST nodes

use crate::lexer::Span;
use crate::ast::ident::{Ident, Path};
use std::fmt;

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct Type {
    pub kind: TypeKind,
    pub span: Span,
}

impl Type {
    pub fn new(kind: TypeKind, span: Span) -> Self {
        Self { kind, span }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum TypeKind {
    // Primitives
    Void,
    Bool,
    Char,
    I8, I16, I32, I64, I128, Isize,
    U8, U16, U32, U64, U128, Usize,
    F32, F64,
    Never,

    // Composite
    Tuple(Vec<Type>),
    Array(Box<Type>, Option<usize>), // element type, optional size (None = slice)
    Ptr(Box<Type>, Mutability),     // &T, *T
    Ref(Box<Type>, Mutability),     // &&T (explicit unsafe)

    // Named types
    Path(Path),
    SelfType, // Self in impl blocks

    // Function type
    Fn(Vec<Type>, Box<Type>), // params, return type

    // Inferred
    Infer,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Mutability {
    Immutable,
    Mutable,
}

impl fmt::Display for TypeKind {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            TypeKind::Void => write!(f, "void"),
            TypeKind::Bool => write!(f, "bool"),
            TypeKind::Char => write!(f, "char"),
            TypeKind::I8 => write!(f, "i8"),
            TypeKind::I16 => write!(f, "i16"),
            TypeKind::I32 => write!(f, "i32"),
            TypeKind::I64 => write!(f, "i64"),
            TypeKind::I128 => write!(f, "i128"),
            TypeKind::Isize => write!(f, "isize"),
            TypeKind::U8 => write!(f, "u8"),
            TypeKind::U16 => write!(f, "u16"),
            TypeKind::U32 => write!(f, "u32"),
            TypeKind::U64 => write!(f, "u64"),
            TypeKind::U128 => write!(f, "u128"),
            TypeKind::Usize => write!(f, "usize"),
            TypeKind::F32 => write!(f, "f32"),
            TypeKind::F64 => write!(f, "f64"),
            TypeKind::Never => write!(f, "!"),
            TypeKind::Tuple(tys) => {
                write!(f, "(")?;
                for (i, ty) in tys.iter().enumerate() {
                    if i > 0 { write!(f, ", ")?; }
                    write!(f, "{}", ty)?;
                }
                write!(f, ")")
            }
            TypeKind::Array(ty, size) => {
                write!(f, "[{}", ty)?;
                if let Some(s) = size { write!(f, "; {}", s)?; }
                write!(f, "]")
            }
            TypeKind::Ptr(ty, mut_) => write!(f, "*{}{}", if *mut_ == Mutability::Mutable { "mut " } else { "" }, ty),
            TypeKind::Ref(ty, mut_) => write!(f, "&&{}{}", if *mut_ == Mutability::Mutable { "mut " } else { "" }, ty),
            TypeKind::Path(p) => write!(f, "{}", p),
            TypeKind::SelfType => write!(f, "Self"),
            TypeKind::Fn(params, ret) => {
                write!(f, "fn(")?;
                for (i, p) in params.iter().enumerate() {
                    if i > 0 { write!(f, ", ")?; }
                    write!(f, "{}", p)?;
                }
                write!(f, ") -> {}", ret)
            }
            TypeKind::Infer => write!(f, "_"),
        }
    }
}