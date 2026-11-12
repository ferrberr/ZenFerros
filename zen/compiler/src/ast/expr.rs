//! Expression AST nodes

use crate::lexer::Span;
use crate::ast::ident::{Ident, Path};
use crate::ast::ty::Type;
use std::fmt;

#[derive(Debug, Clone, PartialEq)]
pub struct Expr {
    pub kind: ExprKind,
    pub span: Span,
    pub ty: Option<Type>, // Filled during type checking
}

impl Expr {
    pub fn new(kind: ExprKind, span: Span) -> Self {
        Self { kind, span, ty: None }
    }
}

#[derive(Debug, Clone, PartialEq)]
pub enum ExprKind {
    // Literals
    Literal(Literal),

    // Variables
    Ident(Ident),
    Path(Path),

    // Binary operations
    Binary {
        op: BinaryOp,
        left: Box<Expr>,
        right: Box<Expr>,
    },

    // Unary operations
    Unary {
        op: UnaryOp,
        expr: Box<Expr>,
    },

    // Call
    Call {
        callee: Box<Expr>,
        args: Vec<Expr>,
    },

    // Method call
    MethodCall {
        receiver: Box<Expr>,
        method: Ident,
        args: Vec<Expr>,
    },

    // Field access
    Field {
        expr: Box<Expr>,
        field: Ident,
    },

    // Index access
    Index {
        expr: Box<Expr>,
        index: Box<Expr>,
    },

    // Cast: expr as Type
    Cast {
        expr: Box<Expr>,
        ty: Type,
    },

    // Block expression { stmt*; expr? }
    Block {
        stmts: Vec<Stmt>,
        tail: Option<Box<Expr>>,
    },

    // If expression
    If {
        cond: Box<Expr>,
        then_branch: Box<Expr>,
        else_branch: Option<Box<Expr>>,
    },

    // While loop (as expression, yields ())
    While {
        cond: Box<Expr>,
        body: Box<Expr>,
    },

    // For loop
    For {
        pat: Pattern,
        iter: Box<Expr>,
        body: Box<Expr>,
    },

    // Loop expression
    Loop {
        body: Box<Expr>,
    },

    // Break/Continue
    Break(Option<Box<Expr>>),
    Continue,

    // Return
    Return(Option<Box<Expr>>),

    // Let binding (expression form)
    Let {
        pat: Pattern,
        ty: Option<Type>,
        init: Box<Expr>,
    },

    // Assignment
    Assign {
        left: Box<Expr>,
        right: Box<Expr>,
    },

    // Compound assignment (+=, -=, etc.)
    AssignOp {
        op: BinaryOp,
        left: Box<Expr>,
        right: Box<Expr>,
    },

    // Struct literal: Struct { field: expr, ... }
    StructLit {
        path: Path,
        fields: Vec<StructFieldInit>,
    },

    // Array literal: [expr, ...] or [expr; size]
    ArrayLit {
        elems: Vec<Expr>,
        repeat: Option<Box<Expr>>, // for [expr; N]
    },

    // Tuple literal
    TupleLit(Vec<Expr>),

    // Match expression
    Match {
        expr: Box<Expr>,
        arms: Vec<MatchArm>,
    },

    // Closure
    Closure {
        params: Vec<Param>,
        ret_ty: Option<Type>,
        body: Box<Expr>,
    },

    // Unsafe block
    UnsafeBlock(Box<Expr>),

    // Error placeholder
    Error,
}

#[derive(Debug, Clone, PartialEq)]
pub enum Literal {
    Integer(u128),
    Float(f64),
    Bool(bool),
    Char(char),
    String(String),
    Null,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum BinaryOp {
    // Arithmetic
    Add, Sub, Mul, Div, Rem,
    // Comparison
    Eq, Ne, Lt, Gt, Le, Ge,
    // Logical
    And, Or,
    // Bitwise
    BitAnd, BitOr, BitXor, Shl, Shr,
    // Assignment handled separately
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum UnaryOp {
    Neg,     // -
    Not,     // !
    BitNot,  // ~
    Deref,   // *
    Ref,     // &
    RefMut,  // &mut
}

#[derive(Debug, Clone, PartialEq)]
pub struct Pattern {
    pub kind: PatternKind,
    pub span: Span,
}

#[derive(Debug, Clone, PartialEq)]
pub enum PatternKind {
    Wildcard,
    Ident(Ident),
    Literal(Literal),
    Tuple(Vec<Pattern>),
    Struct { path: Path, fields: Vec<StructFieldPattern> },
    Ref(Box<Pattern>, Mutability),
    Or(Box<Pattern>, Box<Pattern>),
}

#[derive(Debug, Clone, PartialEq)]
pub struct StructFieldPattern {
    pub field: Ident,
    pub pat: Pattern,
}

#[derive(Debug, Clone, PartialEq)]
pub struct StructFieldInit {
    pub field: Ident,
    pub expr: Expr,
}

#[derive(Debug, Clone, PartialEq)]
pub struct MatchArm {
    pub pat: Pattern,
    pub guard: Option<Expr>,
    pub body: Expr,
}

// Forward declare Stmt for Block expression
use crate::ast::stmt::Stmt;

// Parameter (used in fn declarations and closures)
#[derive(Debug, Clone, PartialEq)]
pub struct Param {
    pub pat: Pattern,
    pub ty: Option<Type>,
    pub span: Span,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Mutability {
    Immutable,
    Mutable,
}