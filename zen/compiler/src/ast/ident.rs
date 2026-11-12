//! Identifiers and paths

use crate::lexer::Span;
use std::fmt;

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct Ident {
    pub name: String,
    pub span: Span,
}

impl Ident {
    pub fn new(name: String, span: Span) -> Self {
        Self { name, span }
    }
}

impl fmt::Display for Ident {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.name)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct PathSegment {
    pub ident: Ident,
    // For future: generic args
}

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct Path {
    pub segments: Vec<PathSegment>,
    pub span: Span,
    pub is_absolute: bool, // starts with ::
}

impl Path {
    pub fn new(segments: Vec<PathSegment>, span: Span, is_absolute: bool) -> Self {
        Self { segments, span, is_absolute }
    }

    pub fn single(ident: Ident) -> Self {
        let span = ident.span;
        Self::new(vec![PathSegment { ident }], span, false)
    }
}