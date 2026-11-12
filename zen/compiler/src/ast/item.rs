//! Function signature and parameter helpers

use crate::lexer::Span;
use crate::ast::ty::Type;
use crate::ast::ident::Ident;

#[derive(Debug, Clone, PartialEq)]
pub struct Param {
    pub pat: crate::ast::expr::Pattern,
    pub ty: Option<Type>,
    pub span: Span,
}

impl Param {
    pub fn new(pat: crate::ast::expr::Pattern, ty: Option<Type>, span: Span) -> Self {
        Self { pat, ty, span }
    }
}