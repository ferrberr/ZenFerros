//! Executable Zen subset for the first native bootstrap milestone.
//!
//! This module validates Zen before emitting portable C11. C is an intermediate
//! representation; it is never used to accept programs rejected by Zen's types.
use crate::lexer::{IntSuffix, Lexer, Span, Token, TokenKind as T};
use crate::lint::{self as lint_rules, LintDiagnostic};
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;

#[derive(Debug, Clone)]
pub struct CompileError {
    pub message: String,
    pub span: Span,
}
impl fmt::Display for CompileError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        self.message.fmt(f)
    }
}
impl std::error::Error for CompileError {}
type Result<T> = std::result::Result<T, CompileError>;
fn error(span: Span, message: impl Into<String>) -> CompileError {
    CompileError {
        message: message.into(),
        span,
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Mode {
    Hosted,
    Freestanding,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Pointee {
    U8,
    U16,
    U32,
    U64,
    I32,
    I64,
}
impl Pointee {
    fn ty(self) -> Ty {
        match self {
            Self::U8 => Ty::U8,
            Self::U16 => Ty::U16,
            Self::U32 => Ty::U32,
            Self::U64 => Ty::U64,
            Self::I32 => Ty::I32,
            Self::I64 => Ty::I64,
        }
    }
}
/// Scalar element types admitted by the MVP fixed-size array subset.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Elem {
    U8,
    U16,
    U32,
    U64,
    I32,
    I64,
    Bool,
}
impl Elem {
    fn ty(self) -> Ty {
        match self {
            Self::U8 => Ty::U8,
            Self::U16 => Ty::U16,
            Self::U32 => Ty::U32,
            Self::U64 => Ty::U64,
            Self::I32 => Ty::I32,
            Self::I64 => Ty::I64,
            Self::Bool => Ty::Bool,
        }
    }
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Ty {
    I32,
    I64,
    U8,
    U16,
    U32,
    U64,
    Bool,
    Str,
    Void,
    Ptr(Pointee, bool),
    Array(Elem, usize),
    /// `[u64]` view over a local `[u64; N]` array: element pointer plus runtime
    /// length. Slices are parameter-only and never own storage.
    Slice,
    /// Nominal struct, by index into the declarations collected while parsing.
    Struct(usize),
}
impl Ty {
    fn c(self, structs: &[StructDef]) -> String {
        match self {
            Self::I32 => "int32_t".into(),
            Self::I64 => "int64_t".into(),
            Self::U8 => "uint8_t".into(),
            Self::U16 => "uint16_t".into(),
            Self::U32 => "uint32_t".into(),
            Self::U64 => "uint64_t".into(),
            Self::Bool => "bool".into(),
            Self::Str => "__zen_string".into(),
            Self::Void => "void".into(),
            Self::Ptr(p, mutable) => {
                format!(
                    "{}{} *",
                    if mutable { "" } else { "const " },
                    p.ty().c(structs)
                )
            }
            // Arrays only appear in local declarations, which use `declaration`.
            Self::Array(elem, len) => format!("{}[{}]", elem.ty().c(structs), len),
            // Slices are a (pointer, length) view; the length always travels
            // with the pointer so callees cannot forget the bounds.
            Self::Slice => "__zen_slice_u64".into(),
            Self::Struct(id) => format!("__zen_Struct_{}", struct_name(structs, id)),
        }
    }
    /// C declaration for a local of this type. C arrays need `T name[N]`.
    fn declaration(self, name: &str, structs: &[StructDef]) -> String {
        match self {
            Self::Array(elem, len) => format!("{} {name}[{len}]", elem.ty().c(structs)),
            _ => format!("{} {name}", self.c(structs)),
        }
    }
    fn numeric(self) -> bool {
        matches!(
            self,
            Self::I32 | Self::I64 | Self::U8 | Self::U16 | Self::U32 | Self::U64
        )
    }
    fn bits(self) -> u32 {
        match self {
            Self::U8 => 8,
            Self::U16 => 16,
            Self::U32 | Self::I32 => 32,
            Self::U64 | Self::I64 => 64,
            _ => 0,
        }
    }
    fn limit(self) -> u128 {
        match self {
            Self::I32 => i32::MAX as u128,
            Self::I64 => i64::MAX as u128,
            Self::U8 => u8::MAX as u128,
            Self::U16 => u16::MAX as u128,
            Self::U32 => u32::MAX as u128,
            Self::U64 => u64::MAX as u128,
            _ => 0,
        }
    }
    fn name(self, structs: &[StructDef]) -> String {
        match self {
            Self::I32 => "i32".into(),
            Self::I64 => "i64".into(),
            Self::U8 => "u8".into(),
            Self::U16 => "u16".into(),
            Self::U32 => "u32".into(),
            Self::U64 => "u64".into(),
            Self::Bool => "bool".into(),
            Self::Str => "str".into(),
            Self::Void => "void".into(),
            Self::Ptr(p, mutable) => {
                format!(
                    "*{}{}",
                    if mutable { "mut " } else { "" },
                    p.ty().name(structs)
                )
            }
            Self::Array(elem, len) => format!("[{}; {}]", elem.ty().name(structs), len),
            Self::Slice => "[u64]".into(),
            Self::Struct(id) => struct_name(structs, id),
        }
    }
}
#[derive(Debug)]
struct StructDef {
    name: String,
    fields: Vec<FieldDef>,
}
#[derive(Debug)]
struct FieldDef {
    name: String,
    ty: Ty,
}
fn struct_name(structs: &[StructDef], id: usize) -> String {
    structs
        .get(id)
        .map(|s| s.name.clone())
        .unwrap_or_else(|| format!("__zen_Struct_{id}"))
}
/// Struct members use positional internal names so Zen field names never collide
/// with C keywords or the bootstrap runtime namespace.
fn member_name(index: usize) -> String {
    format!("__zen_m{index}")
}
#[derive(Debug)]
struct Function {
    name: String,
    span: Span,
    params: Vec<(String, Ty, Span)>,
    ret: Ty,
    body: Option<Block>,
    public: bool,
}
type Block = Vec<Stmt>;
#[derive(Debug)]
struct Stmt {
    kind: StmtKind,
    span: Span,
}
#[derive(Debug)]
enum StmtKind {
    Let(String, Span, bool, Option<Ty>, Expr),
    Assign(Place, Option<Op>, Expr),
    Expr(Expr),
    Return(Option<Expr>),
    If(Expr, Block, Option<Block>),
    While(Expr, Block),
    Block(Block),
    Unsafe(Block),
    Break,
    Continue,
}
#[derive(Debug)]
enum Place {
    Var(String),
    Index(String, Box<Expr>),
    /// Field of a local struct variable: `p.x = ...`.
    Field(String, String),
}
#[derive(Debug)]
struct Expr {
    kind: ExprKind,
    span: Span,
    depth: usize,
}
// Bound both parser calls and constructed AST depth. A parser-only limit would
// miss long left-associative binary chains, which recurse during emission/drop.
const MAX_NESTING: usize = 128;
const MAX_EXPR_DEPTH: usize = 64;
impl Expr {
    fn new(kind: ExprKind, span: Span) -> Result<Self> {
        let depth = 1 + match &kind {
            ExprKind::Call(_, args) => args.iter().map(|e| e.depth).max().unwrap_or(0),
            ExprKind::Unary(_, arg) | ExprKind::BitNot(arg) | ExprKind::Cast(arg, _) => arg.depth,
            ExprKind::Binary(_, left, right) => left.depth.max(right.depth),
            ExprKind::ArrayLit(elements) => elements.iter().map(|e| e.depth).max().unwrap_or(0),
            ExprKind::ArrayRepeat(value, _) => value.depth,
            ExprKind::Index(base, index) => base.depth.max(index.depth),
            ExprKind::Field(base, _) => base.depth,
            ExprKind::StructLit(_, fields) => fields
                .iter()
                .map(|field| field.value.depth)
                .max()
                .unwrap_or(0),
            _ => 0,
        };
        if depth > MAX_EXPR_DEPTH {
            return Err(error(
                span,
                "expression nesting limit exceeded (maximum depth 64)",
            ));
        }
        Ok(Self { kind, span, depth })
    }
}
#[derive(Debug)]
struct StructFieldInit {
    name: String,
    value: Expr,
    span: Span,
}
#[derive(Debug)]
enum ExprKind {
    Int(u128, Option<IntSuffix>),
    Bool(bool),
    Str(String),
    Var(String),
    Call(String, Vec<Expr>),
    Unary(bool, Box<Expr>),
    BitNot(Box<Expr>),
    Cast(Box<Expr>, Ty),
    Binary(Op, Box<Expr>, Box<Expr>),
    ArrayLit(Vec<Expr>),
    ArrayRepeat(Box<Expr>, usize),
    Index(Box<Expr>, Box<Expr>),
    Field(Box<Expr>, String),
    StructLit(String, Vec<StructFieldInit>),
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Op {
    Add,
    Sub,
    Mul,
    Div,
    Rem,
    Eq,
    Ne,
    Lt,
    Le,
    Gt,
    Ge,
    And,
    Or,
    BitAnd,
    BitOr,
    BitXor,
    Shl,
    Shr,
}
impl Op {
    fn comparison(self) -> bool {
        matches!(
            self,
            Self::Eq | Self::Ne | Self::Lt | Self::Le | Self::Gt | Self::Ge
        )
    }
    fn c(self) -> &'static str {
        match self {
            Self::Add => "+",
            Self::Sub => "-",
            Self::Mul => "*",
            Self::Div => "/",
            Self::Rem => "%",
            Self::Eq => "==",
            Self::Ne => "!=",
            Self::Lt => "<",
            Self::Le => "<=",
            Self::Gt => ">",
            Self::Ge => ">=",
            Self::And => "&&",
            Self::Or => "||",
            Self::BitAnd => "&",
            Self::BitOr => "|",
            Self::BitXor => "^",
            Self::Shl => "<<",
            Self::Shr => ">>",
        }
    }
}
struct Parser {
    tokens: Vec<Token>,
    pos: usize,
    nesting: usize,
    /// Top-level struct declarations seen so far. Order matters: a type name is
    /// resolved against the declarations that precede its use.
    structs: Vec<StructDef>,
}
impl Parser {
    fn new(source: &str) -> Result<Self> {
        let tokens = Lexer::new(source, 0).collect_all();
        if let Some(t) = tokens.iter().find(|t| matches!(t.kind, T::Error(_))) {
            if let T::Error(s) = &t.kind {
                return Err(error(t.span, s.clone()));
            }
        }
        Ok(Self {
            tokens,
            pos: 0,
            nesting: 0,
            structs: Vec::new(),
        })
    }
    fn struct_index(&self, name: &str) -> Option<usize> {
        self.structs.iter().position(|s| s.name == name)
    }
    /// A struct literal is only recognized when the name is a declared struct
    /// and the tokens are `{}` or `{ ident :`, so `if flag { ... }` is never
    /// misread as a construction.
    fn struct_lit_ahead(&self) -> bool {
        if !matches!(self.tokens.get(self.pos), Some(t) if matches!(t.kind, T::LBrace)) {
            return false;
        }
        if matches!(
            self.tokens.get(self.pos + 1),
            Some(t) if matches!(t.kind, T::RBrace)
        ) {
            return true;
        }
        matches!(
            self.tokens.get(self.pos + 1),
            Some(t) if matches!(t.kind, T::Ident(_))
        ) && matches!(
            self.tokens.get(self.pos + 2),
            Some(t) if matches!(t.kind, T::Colon)
        )
    }
    fn nested<U>(&mut self, parse: impl FnOnce(&mut Self) -> Result<U>) -> Result<U> {
        if self.nesting >= MAX_NESTING {
            return Err(error(
                self.token().span,
                "syntax nesting limit exceeded (maximum parser depth 128)",
            ));
        }
        self.nesting += 1;
        let result = parse(self);
        self.nesting -= 1;
        result
    }
    fn token(&self) -> &Token {
        &self.tokens[self.pos]
    }
    fn at(&self, kind: &T) -> bool {
        std::mem::discriminant(&self.token().kind) == std::mem::discriminant(kind)
    }
    fn take(&mut self) -> Token {
        let t = self.token().clone();
        if !self.at(&T::Eof) {
            self.pos += 1;
        }
        t
    }
    fn eat(&mut self, kind: &T) -> bool {
        if self.at(kind) {
            self.take();
            true
        } else {
            false
        }
    }
    fn expect(&mut self, kind: &T) -> Result<Token> {
        if self.at(kind) {
            Ok(self.take())
        } else {
            Err(error(
                self.token().span,
                format!("expected {kind:?}, found {:?}", self.token().kind),
            ))
        }
    }
    fn ident(&mut self) -> Result<(String, Span)> {
        let t = self.take();
        if let T::Ident(name) = t.kind {
            Ok((name, t.span))
        } else {
            Err(error(t.span, "expected identifier"))
        }
    }
    fn ty(&mut self) -> Result<Ty> {
        let t = self.take();
        match t.kind {
            T::Star => {
                let mutable=self.eat(&T::Mut);
                // Pointers are one level and target integer scalars in this subset.
                let next=self.take();
                let pointee=match next.kind { T::U8=>Pointee::U8,T::U16=>Pointee::U16,T::U32=>Pointee::U32,T::U64=>Pointee::U64,T::I32=>Pointee::I32,T::I64=>Pointee::I64,_=>return Err(error(next.span,"raw pointers require an integer scalar pointee")) };
                Ok(Ty::Ptr(pointee,mutable))
            }
            T::I32 => Ok(Ty::I32),
            T::I64 => Ok(Ty::I64),
            T::U8 => Ok(Ty::U8), T::U16 => Ok(Ty::U16), T::U32 => Ok(Ty::U32),
            T::U64 => Ok(Ty::U64),
            T::Bool_ => Ok(Ty::Bool),
            T::Void => Ok(Ty::Void),
            T::Ident(ref n) if n == "str" => Ok(Ty::Str),
            T::Ident(ref n) => match self.struct_index(n) {
                Some(id) => Ok(Ty::Struct(id)),
                None => Err(error(
                    t.span,
                    format!("unknown type '{n}'; structs must be declared before they are used"),
                )),
            },
            T::LBracket => {
                let elem = self.array_elem()?;
                // `[T]` is a slice view; only `[u64]` is part of the MVP.
                if self.eat(&T::RBracket) {
                    if elem != Elem::U64 {
                        return Err(error(
                            t.span,
                            "slice types support only u64 elements; write [u64]",
                        ));
                    }
                    return Ok(Ty::Slice);
                }
                self.expect(&T::Semi)?;
                let len = self.array_len()?;
                self.expect(&T::RBracket)?;
                Ok(Ty::Array(elem, len))
            }
            _ => Err(error(
                t.span,
                "unsupported type; expected a supported fixed integer, bool, str, void, raw pointer, [T; N] or [u64] slice",
            )),
        }
    }
    /// Array element types stay scalar so the MVP has no multidimensional arrays.
    fn array_elem(&mut self) -> Result<Elem> {
        let t = self.take();
        match t.kind {
            T::U8 => Ok(Elem::U8),
            T::U16 => Ok(Elem::U16),
            T::U32 => Ok(Elem::U32),
            T::U64 => Ok(Elem::U64),
            T::I32 => Ok(Elem::I32),
            T::I64 => Ok(Elem::I64),
            T::Bool_ => Ok(Elem::Bool),
            _ => Err(error(
                t.span,
                "array element type must be u8, u16, u32, i32, i64, u64 or bool",
            )),
        }
    }
    /// Fixed lengths are literal-only: no constants, no runtime expressions.
    fn array_len(&mut self) -> Result<usize> {
        let t = self.take();
        let value = match t.kind {
            T::Integer {
                value,
                suffix: None,
                ..
            } => value,
            T::Integer { .. } => {
                return Err(error(
                    t.span,
                    "array length must be an unsuffixed integer literal",
                ))
            }
            _ => {
                return Err(error(
                    t.span,
                    "array length must be a positive integer literal",
                ))
            }
        };
        if value == 0 {
            return Err(error(t.span, "array length must be greater than zero"));
        }
        if value > usize::MAX as u128 {
            return Err(error(t.span, "array length is too large for this target"));
        }
        Ok(value as usize)
    }
    fn program(&mut self) -> Result<Vec<Function>> {
        let mut functions = Vec::new();
        while !self.at(&T::Eof) {
            if self.at(&T::Struct) {
                self.struct_def()?;
            } else if self.eat(&T::Extern) {
                let abi = self.take();
                if !matches!(abi.kind,T::String(ref s) if s=="C") {
                    return Err(error(abi.span, "only extern \"C\" ABI is supported"));
                }
                self.expect(&T::LBrace)?;
                while !self.at(&T::RBrace) {
                    if self.at(&T::Eof) {
                        return Err(error(self.token().span, "unterminated extern block"));
                    }
                    functions.push(self.function(false, true)?);
                }
                self.expect(&T::RBrace)?;
            } else {
                let public = self.eat(&T::Pub);
                functions.push(self.function(public, false)?);
            }
        }
        Ok(functions)
    }
    /// `struct Name { field: T, ... }` with scalar fields only. The declaration
    /// is registered immediately so later uses resolve; earlier uses cannot.
    fn struct_def(&mut self) -> Result<()> {
        let start = self.expect(&T::Struct)?.span;
        let (name, name_span) = self.ident()?;
        if name == "str" {
            return Err(error(name_span, "struct name 'str' is reserved"));
        }
        if self.struct_index(&name).is_some() {
            return Err(error(name_span, format!("duplicate struct '{name}'")));
        }
        self.expect(&T::LBrace)?;
        let mut fields: Vec<FieldDef> = Vec::new();
        while !self.at(&T::RBrace) {
            if self.at(&T::Eof) {
                return Err(error(self.token().span, "unterminated struct declaration"));
            }
            let (field, field_span) = self.ident()?;
            if fields.iter().any(|f| f.name == field) {
                return Err(error(
                    field_span,
                    format!("duplicate field '{field}' in struct '{name}'"),
                ));
            }
            self.expect(&T::Colon)?;
            let ty_span = self.token().span;
            let scalar_only = || {
                format!(
                    "struct field '{field}' must have scalar type u8, u16, u32, i32, i64, u64 or bool"
                )
            };
            let ty = self.ty().map_err(|e| error(e.span, scalar_only()))?;
            if !matches!(
                ty,
                Ty::U8 | Ty::U16 | Ty::U32 | Ty::I32 | Ty::I64 | Ty::U64 | Ty::Bool
            ) {
                return Err(error(ty_span, scalar_only()));
            }
            fields.push(FieldDef { name: field, ty });
            if !self.eat(&T::Comma) {
                break;
            }
        }
        self.expect(&T::RBrace)?;
        if fields.is_empty() {
            return Err(error(
                start,
                format!("struct '{name}' must declare at least one field"),
            ));
        }
        self.structs.push(StructDef { name, fields });
        Ok(())
    }
    fn function(&mut self, public: bool, external: bool) -> Result<Function> {
        let start = self.expect(&T::Fn)?.span;
        let (name, name_span) = self.ident()?;
        if self.struct_index(&name).is_some() {
            return Err(error(
                name_span,
                format!("function '{name}' conflicts with struct '{name}'"),
            ));
        }
        self.expect(&T::LParen)?;
        let mut params = Vec::new();
        if !self.at(&T::RParen) {
            loop {
                let (name, span) = self.ident()?;
                if self.struct_index(&name).is_some() {
                    return Err(error(
                        span,
                        format!("parameter '{name}' conflicts with struct '{name}'"),
                    ));
                }
                self.expect(&T::Colon)?;
                let ty = self.ty()?;
                if ty == Ty::Void {
                    return Err(error(span, "parameters cannot have type void"));
                }
                if matches!(ty, Ty::Array(..)) {
                    return Err(error(
                        span,
                        "fixed-size arrays cannot be parameters; use a local [T; N] variable",
                    ));
                }
                if matches!(ty, Ty::Struct(..)) {
                    return Err(error(
                        span,
                        "struct types cannot be parameters; structs are local variables only",
                    ));
                }
                params.push((name, ty, span));
                if !self.eat(&T::Comma) || self.at(&T::RParen) {
                    break;
                }
            }
        }
        self.expect(&T::RParen)?;
        let ret = if self.eat(&T::Arrow) {
            let ret_span = self.token().span;
            let ret = self.ty()?;
            if matches!(ret, Ty::Array(..)) {
                return Err(error(
                    ret_span,
                    "fixed-size arrays cannot be returned; use a local [T; N] variable",
                ));
            }
            if matches!(ret, Ty::Slice) {
                return Err(error(
                    ret_span,
                    "slice types cannot be returned; a slice is a borrowed view, return a scalar instead",
                ));
            }
            if matches!(ret, Ty::Struct(..)) {
                return Err(error(
                    ret_span,
                    "struct types cannot be returned; structs are local variables only",
                ));
            }
            ret
        } else {
            Ty::Void
        };
        let body = if external {
            self.expect(&T::Semi)?;
            None
        } else {
            Some(self.block()?)
        };
        Ok(Function {
            name,
            span: start,
            params,
            ret,
            body,
            public,
        })
    }
    fn block(&mut self) -> Result<Block> {
        self.nested(|parser| parser.block_inner())
    }
    fn block_inner(&mut self) -> Result<Block> {
        self.expect(&T::LBrace)?;
        let mut block = Vec::new();
        while !self.at(&T::RBrace) {
            if self.at(&T::Eof) {
                return Err(error(
                    self.token().span,
                    "expected RBrace before end of file",
                ));
            }
            if self.eat(&T::Semi) {
                continue;
            }
            block.push(self.stmt()?);
        }
        self.expect(&T::RBrace)?;
        Ok(block)
    }
    fn stmt(&mut self) -> Result<Stmt> {
        self.nested(|parser| parser.stmt_inner())
    }
    fn stmt_inner(&mut self) -> Result<Stmt> {
        let span = self.token().span;
        let kind = if self.eat(&T::Let) {
            let mutable = self.eat(&T::Mut);
            let (name, name_span) = self.ident()?;
            if self.struct_index(&name).is_some() {
                return Err(error(
                    name_span,
                    format!("local '{name}' conflicts with struct '{name}'"),
                ));
            }
            let ty = if self.eat(&T::Colon) {
                Some(self.ty()?)
            } else {
                None
            };
            if matches!(ty, Some(Ty::Slice)) {
                return Err(error(
                    name_span,
                    format!(
                        "slice type [u64] is parameter-only; local '{name}' cannot be a slice"
                    ),
                ));
            }
            self.expect(&T::Assign)?;
            let init = self.expr(0)?;
            self.expect(&T::Semi)?;
            StmtKind::Let(name, name_span, mutable, ty, init)
        } else if self.eat(&T::Return) {
            let expr = if self.at(&T::Semi) {
                None
            } else {
                Some(self.expr(0)?)
            };
            self.expect(&T::Semi)?;
            StmtKind::Return(expr)
        } else if self.eat(&T::If) {
            let cond = self.expr(0)?;
            let yes = self.block()?;
            let no = if self.eat(&T::Else) {
                Some(if self.at(&T::If) {
                    vec![self.stmt()?]
                } else {
                    self.block()?
                })
            } else {
                None
            };
            StmtKind::If(cond, yes, no)
        } else if self.eat(&T::While) {
            let cond = self.expr(0)?;
            let body = self.block()?;
            StmtKind::While(cond, body)
        } else if self.eat(&T::Unsafe) {
            StmtKind::Unsafe(self.block()?)
        } else if self.at(&T::LBrace) {
            StmtKind::Block(self.block()?)
        } else if self.eat(&T::Break) {
            self.expect(&T::Semi)?;
            StmtKind::Break
        } else if self.eat(&T::Continue) {
            self.expect(&T::Semi)?;
            StmtKind::Continue
        } else {
            let expr = self.expr(0)?;
            let assignment = match self.token().kind {
                T::Assign => Some(None),
                T::PlusEq => Some(Some(Op::Add)),
                T::MinusEq => Some(Some(Op::Sub)),
                T::StarEq => Some(Some(Op::Mul)),
                T::SlashEq => Some(Some(Op::Div)),
                T::PercentEq => Some(Some(Op::Rem)),
                T::AmpEq => Some(Some(Op::BitAnd)),
                T::PipeEq => Some(Some(Op::BitOr)),
                T::CaretEq => Some(Some(Op::BitXor)),
                T::ShlEq => Some(Some(Op::Shl)),
                T::ShrEq => Some(Some(Op::Shr)),
                _ => None,
            };
            let kind = if let Some(op) = assignment {
                self.take();
                let rhs = self.expr(0)?;
                let place = match expr.kind {
                    ExprKind::Var(name) => Place::Var(name),
                    ExprKind::Index(base, index) => match base.kind {
                        ExprKind::Var(name) => Place::Index(name, index),
                        _ => {
                            return Err(error(
                                base.span,
                                "assignment target must be a local variable or an array element",
                            ))
                        }
                    },
                    ExprKind::Field(base, field) => match base.kind {
                        ExprKind::Var(name) => Place::Field(name, field),
                        _ => {
                            return Err(error(
                                base.span,
                                "assignment target must be a field of a local struct variable",
                            ))
                        }
                    },
                    _ => {
                        return Err(error(
                            expr.span,
                            "assignment target must be a local variable, an array element or a struct field",
                        ))
                    }
                };
                StmtKind::Assign(place, op, rhs)
            } else {
                StmtKind::Expr(expr)
            };
            self.expect(&T::Semi)?;
            kind
        };
        Ok(Stmt { kind, span })
    }
    fn expr(&mut self, min: u8) -> Result<Expr> {
        self.nested(|parser| parser.expr_inner(min))
    }
    fn expr_inner(&mut self, min: u8) -> Result<Expr> {
        let mut left = self.cast()?;
        loop {
            let (op, prec) = match self.token().kind {
                T::OrOr => (Op::Or, 1),
                T::AndAnd => (Op::And, 2),
                T::EqEq => (Op::Eq, 3),
                T::NotEq => (Op::Ne, 3),
                T::Lt => (Op::Lt, 4),
                T::LtEq => (Op::Le, 4),
                T::Gt => (Op::Gt, 4),
                T::GtEq => (Op::Ge, 4),
                T::Pipe => (Op::BitOr, 5),
                T::Caret => (Op::BitXor, 6),
                T::Amp => (Op::BitAnd, 7),
                T::Shl => (Op::Shl, 8),
                T::Shr => (Op::Shr, 8),
                T::Plus => (Op::Add, 9),
                T::Minus => (Op::Sub, 9),
                T::Star => (Op::Mul, 10),
                T::Slash => (Op::Div, 10),
                T::Percent => (Op::Rem, 10),
                _ => break,
            };
            if prec < min {
                break;
            }
            self.take();
            let right = self.expr(prec + 1)?;
            let span = left.span.merge(right.span);
            left = Expr::new(ExprKind::Binary(op, Box::new(left), Box::new(right)), span)?;
        }
        Ok(left)
    }
    fn cast(&mut self) -> Result<Expr> {
        let mut expr = self.primary()?;
        while self.eat(&T::As) {
            let ty_span = self.token().span;
            let ty = self.ty()?;
            if matches!(ty, Ty::Array(..)) {
                return Err(error(
                    self.tokens[self.pos - 1].span,
                    "casts to fixed-size array types are not supported",
                ));
            }
            if matches!(ty, Ty::Slice) {
                return Err(error(ty_span, "casts to slice types are not supported"));
            }
            if matches!(ty, Ty::Struct(..)) {
                return Err(error(
                    self.tokens[self.pos - 1].span,
                    "casts to struct types are not supported",
                ));
            }
            let span = expr.span.merge(self.tokens[self.pos - 1].span);
            expr = Expr::new(ExprKind::Cast(Box::new(expr), ty), span)?;
        }
        Ok(expr)
    }
    fn primary(&mut self) -> Result<Expr> {
        self.nested(|parser| parser.primary_inner())
    }
    fn primary_inner(&mut self) -> Result<Expr> {
        let t = self.take();
        let span = t.span;
        let mut expr = match t.kind {
            T::Integer { value, suffix, .. } => Expr::new(ExprKind::Int(value, suffix), span)?,
            T::True => Expr::new(ExprKind::Bool(true), span)?,
            T::False => Expr::new(ExprKind::Bool(false), span)?,
            T::String(s) => Expr::new(ExprKind::Str(s), span)?,
            T::Ident(n) => {
                if self.eat(&T::LParen) {
                    let mut args = Vec::new();
                    if !self.at(&T::RParen) {
                        loop {
                            args.push(self.expr(0)?);
                            if !self.eat(&T::Comma) || self.at(&T::RParen) {
                                break;
                            }
                        }
                    }
                    self.expect(&T::RParen)?;
                    Expr::new(ExprKind::Call(n, args), span)?
                } else if self.struct_index(&n).is_some() && self.struct_lit_ahead() {
                    self.expect(&T::LBrace)?;
                    let mut fields: Vec<StructFieldInit> = Vec::new();
                    while !self.at(&T::RBrace) {
                        if self.at(&T::Eof) {
                            return Err(error(self.token().span, "unterminated struct literal"));
                        }
                        let (field, field_span) = self.ident()?;
                        if fields.iter().any(|f| f.name == field) {
                            return Err(error(
                                field_span,
                                format!("duplicate field '{field}' in struct literal"),
                            ));
                        }
                        self.expect(&T::Colon)?;
                        let value = self.expr(0)?;
                        fields.push(StructFieldInit {
                            name: field,
                            value,
                            span: field_span,
                        });
                        if !self.eat(&T::Comma) {
                            break;
                        }
                    }
                    let close = self.expect(&T::RBrace)?;
                    Expr::new(ExprKind::StructLit(n, fields), span.merge(close.span))?
                } else {
                    Expr::new(ExprKind::Var(n), span)?
                }
            }
            T::Tilde => {
                let arg = self.primary()?;
                let span = span.merge(arg.span);
                Expr::new(ExprKind::BitNot(Box::new(arg)), span)?
            }
            T::Minus | T::Not => {
                let neg = matches!(t.kind, T::Minus);
                let arg = self.primary()?;
                let span = span.merge(arg.span);
                Expr::new(ExprKind::Unary(neg, Box::new(arg)), span)?
            }
            T::LParen => {
                let e = self.expr(0)?;
                self.expect(&T::RParen)?;
                e
            }
            T::LBracket => {
                if self.eat(&T::RBracket) {
                    return Err(error(span, "array literal requires at least one element"));
                }
                let first = self.expr(0)?;
                let kind = if self.eat(&T::Semi) {
                    let len = self.array_len()?;
                    ExprKind::ArrayRepeat(Box::new(first), len)
                } else {
                    let mut elements = vec![first];
                    while self.eat(&T::Comma) {
                        if self.at(&T::RBracket) {
                            break;
                        }
                        elements.push(self.expr(0)?);
                    }
                    ExprKind::ArrayLit(elements)
                };
                let close = self.expect(&T::RBracket)?;
                Expr::new(kind, span.merge(close.span))?
            }
            _ => {
                return Err(error(
                    span,
                    format!("expected expression, found {:?}", t.kind),
                ))
            }
        };
        // Postfix indexing and field access bind tighter than casts and binary operators.
        loop {
            if self.eat(&T::LBracket) {
                let index = self.expr(0)?;
                let close = self.expect(&T::RBracket)?;
                let full = expr.span.merge(close.span);
                expr = Expr::new(ExprKind::Index(Box::new(expr), Box::new(index)), full)?;
            } else if self.eat(&T::Dot) {
                let (field, field_span) = self.ident()?;
                let full = expr.span.merge(field_span);
                expr = Expr::new(ExprKind::Field(Box::new(expr), field), full)?;
            } else {
                break;
            }
        }
        Ok(expr)
    }
}

#[derive(Clone)]
struct Sig {
    params: Vec<Ty>,
    ret: Ty,
    name: String,
    external: bool,
}
#[derive(Clone)]
struct Binding {
    ty: Ty,
    mutable: bool,
    name: String,
}
struct Value {
    ty: Ty,
    name: String,
}
/// What an index expression indexes: a fixed-size local array (compile-time
/// length) or a `[u64]` slice parameter (runtime length).
enum IndexTarget {
    Array {
        binding: Binding,
        elem: Elem,
        len: usize,
    },
    Slice {
        binding: Binding,
    },
}
struct Emitter<'a> {
    signatures: &'a BTreeMap<String, Sig>,
    structs: &'a [StructDef],
    scopes: Vec<BTreeMap<String, Binding>>,
    output: String,
    next: usize,
    ret: Ty,
    loops: usize,
    unsafe_depth: usize,
}
fn suffix_ty(suffix: IntSuffix, span: Span) -> Result<Ty> {
    match suffix {
        IntSuffix::I32 => Ok(Ty::I32),
        IntSuffix::I64 => Ok(Ty::I64),
        IntSuffix::U8 => Ok(Ty::U8),
        IntSuffix::U16 => Ok(Ty::U16),
        IntSuffix::U32 => Ok(Ty::U32),
        IntSuffix::U64 => Ok(Ty::U64),
        _ => Err(error(span, "unsupported integer suffix in native MVP")),
    }
}
impl<'a> Emitter<'a> {
    fn line(&mut self, s: impl AsRef<str>) {
        self.output.push_str(s.as_ref());
        self.output.push('\n');
    }
    fn fresh(&mut self) -> String {
        let name = format!("__zen_v{}", self.next);
        self.next += 1;
        name
    }
    fn temp(&mut self, ty: Ty, init: String) -> Value {
        if ty == Ty::Void {
            self.line(format!("{init};"));
            return Value {
                ty,
                name: String::new(),
            };
        }
        let name = self.fresh();
        self.line(format!("{} {name} = {init};", ty.c(self.structs)));
        Value { ty, name }
    }
    fn ty_name(&self, ty: Ty) -> String {
        ty.name(self.structs)
    }
    /// Resolve `field` on the local struct variable `name`, returning its
    /// binding, declaration index and scalar type.
    fn struct_var_field(
        &self,
        name: &str,
        field: &str,
        span: Span,
    ) -> Result<(Binding, usize, Ty)> {
        let b = self.binding(name, span)?;
        let Ty::Struct(id) = b.ty else {
            return Err(error(
                span,
                format!(
                    "variable '{name}' has type {} and has no fields",
                    b.ty.name(self.structs)
                ),
            ));
        };
        let def = &self.structs[id];
        let index = def
            .fields
            .iter()
            .position(|f| f.name == field)
            .ok_or_else(|| {
                error(
                    span,
                    format!("struct '{}' has no field '{field}'", def.name),
                )
            })?;
        Ok((b, index, def.fields[index].ty))
    }
    fn resolve_field(&self, base: &Expr, field: &str, span: Span) -> Result<(String, usize, Ty)> {
        let ExprKind::Var(name) = &base.kind else {
            return Err(error(span, "field access requires a local struct variable"));
        };
        self.struct_var_field(name, field, span)
            .map(|(b, index, ty)| (b.name, index, ty))
    }
    fn field_type(&self, base: &Expr, field: &str, span: Span) -> Result<Ty> {
        self.resolve_field(base, field, span).map(|(_, _, ty)| ty)
    }
    fn binding(&self, name: &str, span: Span) -> Result<Binding> {
        self.scopes
            .iter()
            .rev()
            .find_map(|s| s.get(name))
            .cloned()
            .ok_or_else(|| error(span, format!("unknown variable '{name}'")))
    }
    fn index_elem(&self, e: &Expr) -> Option<Ty> {
        let ExprKind::Var(name) = &e.kind else {
            return None;
        };
        match self.binding(name, e.span).ok()?.ty {
            Ty::Array(elem, _) => Some(elem.ty()),
            Ty::Slice => Some(Ty::U64),
            _ => None,
        }
    }
    fn index_target(&self, e: &Expr) -> Result<IndexTarget> {
        let ExprKind::Var(name) = &e.kind else {
            return Err(error(
                e.span,
                "indexing requires a local array variable or a [u64] slice parameter",
            ));
        };
        let binding = self.binding(name, e.span)?;
        match binding.ty {
            Ty::Array(elem, len) => Ok(IndexTarget::Array {
                binding,
                elem,
                len,
            }),
            Ty::Slice => Ok(IndexTarget::Slice { binding }),
            other => Err(error(
                e.span,
                format!(
                    "variable '{name}' has type {} and cannot be indexed; indexing requires a local array or a [u64] slice parameter",
                    other.name(self.structs)
                ),
            )),
        }
    }
    /// Coerce a call argument to a `[u64]` slice: a local `[u64; N]` array
    /// contributes its address and length; another slice is passed through
    /// unchanged. No other expression has an address with a known length, so
    /// no copy or allocation is introduced.
    fn slice_argument(&mut self, arg: &Expr) -> Result<Value> {
        let ExprKind::Var(name) = &arg.kind else {
            return Err(error(
                arg.span,
                "a [u64] slice argument must be a local [u64; N] array or another slice parameter",
            ));
        };
        let binding = self.binding(name, arg.span)?;
        match binding.ty {
            Ty::Slice => Ok(Value {
                ty: Ty::Slice,
                name: binding.name,
            }),
            Ty::Array(Elem::U64, len) => Ok(self.temp(
                Ty::Slice,
                format!(
                    "(__zen_slice_u64){{(uint64_t *){}, UINT64_C({len})}}",
                    binding.name
                ),
            )),
            Ty::Array(elem, len) => Err(error(
                arg.span,
                format!(
                    "cannot pass array of type [{}; {}] to a [u64] slice parameter; slice elements must be u64",
                    elem.ty().name(self.structs),
                    len
                ),
            )),
            other => Err(error(
                arg.span,
                format!(
                    "cannot pass {} to a [u64] slice parameter; expected a local [u64; N] array or another slice",
                    other.name(self.structs)
                ),
            )),
        }
    }
    fn expect(&self, got: Ty, want: Ty, span: Span) -> Result<()> {
        if got == want {
            Ok(())
        } else {
            Err(error(
                span,
                format!(
                    "type mismatch: expected {}, found {}",
                    want.name(self.structs),
                    got.name(self.structs)
                ),
            ))
        }
    }
    fn hint(&self, e: &Expr) -> Option<Ty> {
        match &e.kind {
            ExprKind::Int(_, Some(s)) => suffix_ty(*s, e.span).ok(),
            ExprKind::Int(..) => None,
            ExprKind::Bool(_) => Some(Ty::Bool),
            ExprKind::Str(_) => Some(Ty::Str),
            ExprKind::Var(n) => self.binding(n, e.span).ok().map(|b| b.ty),
            ExprKind::Call(n, args) if n == "volatile_load" => args
                .first()
                .and_then(|arg| self.hint(arg))
                .and_then(|ty| match ty {
                    Ty::Ptr(p, _) => Some(p.ty()),
                    _ => None,
                }),
            ExprKind::Call(n, _) => self.signatures.get(n).map(|s| s.ret),
            ExprKind::Cast(_, ty) => Some(*ty),
            ExprKind::BitNot(arg) => self.hint(arg),
            ExprKind::Unary(true, arg) => self.hint(arg),
            ExprKind::Unary(false, _) => Some(Ty::Bool),
            ExprKind::Binary(op, _, _) if op.comparison() || matches!(op, Op::And | Op::Or) => {
                Some(Ty::Bool)
            }
            ExprKind::Binary(_, l, r) => self.hint(l).or_else(|| self.hint(r)),
            ExprKind::Index(base, _) => self.index_elem(base),
            ExprKind::Field(base, field) => self.field_type(base, field, e.span).ok(),
            ExprKind::ArrayLit(_) | ExprKind::ArrayRepeat(..) | ExprKind::StructLit(..) => None,
        }
    }
    fn expr(&mut self, e: &Expr, expected: Option<Ty>) -> Result<Value> {
        let val = match &e.kind {
            ExprKind::Int(n, suffix) => {
                let ty = if let Some(s) = suffix {
                    suffix_ty(*s, e.span)?
                } else {
                    expected.filter(|t| t.numeric()).unwrap_or(Ty::I32)
                };
                if *n > ty.limit() {
                    return Err(error(
                        e.span,
                        format!("integer literal out of range for {}", ty.name(self.structs)),
                    ));
                }
                self.temp(ty, format!("({})UINT64_C({n})", ty.c(self.structs)))
            }
            ExprKind::Bool(b) => self.temp(Ty::Bool, b.to_string()),
            ExprKind::Str(s) => {
                let bytes = s
                    .as_bytes()
                    .iter()
                    .map(|b| format!("\\{b:03o}"))
                    .collect::<String>();
                self.temp(
                    Ty::Str,
                    format!(
                        "(__zen_string){{(const unsigned char *)\"{bytes}\", {}}}",
                        s.len()
                    ),
                )
            }
            ExprKind::Var(name) => {
                let binding = self.binding(name, e.span)?;
                if binding.ty == Ty::Slice {
                    return Err(error(
                        e.span,
                        format!(
                            "slice parameter '{name}' cannot be used as a value; index it with {name}[i] or call slice_len({name})"
                        ),
                    ));
                }
                if matches!(binding.ty, Ty::Array(..)) {
                    return Err(error(
                        e.span,
                        format!(
                            "array '{name}' can only be read or written through an index; whole-array values are not supported"
                        ),
                    ));
                }
                if matches!(binding.ty, Ty::Struct(..)) {
                    return Err(error(
                        e.span,
                        format!(
                            "cannot use struct value '{name}' directly; construct it with Name {{ field: value }} and access its fields"
                        ),
                    ));
                }
                self.temp(binding.ty, binding.name)
            }
            ExprKind::Index(base, index) => {
                let target = self.index_target(base)?;
                // The index expression is evaluated once, before the element is read.
                let idx = self.expr(index, None)?;
                if !idx.ty.numeric() {
                    return Err(error(index.span, "array index must be an integer"));
                }
                match target {
                    IndexTarget::Array { binding, elem, len } => {
                        let checked = self.temp(
                            Ty::U64,
                            format!(
                                "__zen_index_check((uint64_t)({}), UINT64_C({len}))",
                                idx.name
                            ),
                        );
                        self.temp(elem.ty(), format!("{}[{}]", binding.name, checked.name))
                    }
                    IndexTarget::Slice { binding } => {
                        // Slices carry their length at runtime; the same helper
                        // traps before an out-of-range element access.
                        let checked = self.temp(
                            Ty::U64,
                            format!(
                                "__zen_index_check((uint64_t)({}), {}.len)",
                                idx.name, binding.name
                            ),
                        );
                        self.temp(Ty::U64, format!("{}.data[{}]", binding.name, checked.name))
                    }
                }
            }
            ExprKind::Field(base, field) => {
                let (cname, index, ty) = self.resolve_field(base, field, e.span)?;
                self.temp(ty, format!("{cname}.{}", member_name(index)))
            }
            ExprKind::StructLit(name, _) => {
                return Err(error(
                    e.span,
                    format!(
                        "struct literal '{name} {{ ... }}' is only allowed as the initializer of a local variable"
                    ),
                ))
            }
            ExprKind::ArrayLit(_) | ExprKind::ArrayRepeat(..) => {
                return Err(error(
                    e.span,
                    "array literals are only allowed as the initializer of a local variable declared as [T; N]",
                ))
            }
            ExprKind::Cast(arg, ty) => {
                let val = self.expr(arg, None)?;
                let init = if val.ty.numeric() && ty.numeric() {
                    match ty {
                        Ty::I32 => format!("__zen_bits_i32((uint32_t)({}))", val.name),
                        Ty::I64 => format!("__zen_bits_i64((uint64_t)({}))", val.name),
                        _ => format!("({})({})", ty.c(self.structs), val.name),
                    }
                } else if (matches!(val.ty, Ty::Ptr(..)) && *ty == Ty::U64)
                    || (val.ty == Ty::U64 && matches!(ty, Ty::Ptr(..)))
                {
                    if self.unsafe_depth == 0 {
                        return Err(error(e.span, "pointer casts require unsafe block"));
                    }
                    format!("({})(uintptr_t)({})", ty.c(self.structs), val.name)
                } else {
                    return Err(error(
                        e.span,
                        "unsupported cast; use integer-to-integer or unsafe pointer/u64 conversion",
                    ));
                };
                self.temp(*ty, init)
            }
            ExprKind::BitNot(arg) => {
                let ty = expected
                    .filter(|t| t.numeric())
                    .or_else(|| self.hint(arg))
                    .unwrap_or(Ty::I32);
                if !ty.numeric() {
                    return Err(error(e.span, "bitwise complement requires integer"));
                }
                let val = self.expr(arg, Some(ty))?;
                let unsigned = format!("~(uint64_t)({})", val.name);
                let init = match ty {
                    Ty::I32 => format!("__zen_bits_i32((uint32_t)({unsigned}))"),
                    Ty::I64 => format!("__zen_bits_i64({unsigned})"),
                    _ => format!("({})({unsigned})", ty.c(self.structs)),
                };
                self.temp(ty, init)
            }
            ExprKind::Call(name, args) if name == "volatile_load" || name == "volatile_store" => {
                if self.unsafe_depth == 0 {
                    return Err(error(e.span, "volatile access requires unsafe block"));
                }
                let store = name == "volatile_store";
                if args.len() != if store { 2 } else { 1 } {
                    return Err(error(
                        e.span,
                        "wrong number of arguments for volatile intrinsic",
                    ));
                }
                let ptr = self.expr(&args[0], None)?;
                let Ty::Ptr(pointee, mutable) = ptr.ty else {
                    return Err(error(args[0].span, "volatile access requires raw pointer"));
                };
                let ty = pointee.ty();
                if store {
                    if !mutable {
                        return Err(error(e.span, "volatile_store requires mutable raw pointer"));
                    }
                    let val = self.expr(&args[1], Some(ty))?;
                    self.line(format!(
                        "*(volatile {} *){} = {};",
                        ty.c(self.structs),
                        ptr.name,
                        val.name
                    ));
                    Value {
                        ty: Ty::Void,
                        name: String::new(),
                    }
                } else {
                    self.temp(ty, format!("*(const volatile {} *){}", ty.c(self.structs), ptr.name))
                }
            }
            ExprKind::Call(name, args) => {
                let sig = self
                    .signatures
                    .get(name)
                    .cloned()
                    .ok_or_else(|| error(e.span, format!("unknown function '{name}'")))?;
                if sig.external && self.unsafe_depth == 0 {
                    return Err(error(e.span, "extern C calls require unsafe block"));
                }
                if args.len() != sig.params.len() {
                    return Err(error(
                        e.span,
                        format!(
                            "function '{name}' expects {} arguments, found {}",
                            sig.params.len(),
                            args.len()
                        ),
                    ));
                }
                let mut values = Vec::new();
                for (arg, ty) in args.iter().zip(sig.params) {
                    let value = if ty == Ty::Slice {
                        self.slice_argument(arg)?
                    } else {
                        self.expr(arg, Some(ty))?
                    };
                    values.push(value.name);
                }
                self.temp(sig.ret, format!("{}({})", sig.name, values.join(", ")))
            }
            ExprKind::Unary(false, arg) => {
                let v = self.expr(arg, Some(Ty::Bool))?;
                self.temp(Ty::Bool, format!("!{}", v.name))
            }
            ExprKind::Unary(true, arg) => {
                let ty = expected
                    .filter(|t| t.numeric())
                    .or_else(|| self.hint(arg))
                    .unwrap_or(Ty::I32);
                if !matches!(ty, Ty::I32 | Ty::I64) {
                    return Err(error(e.span, "unary minus requires i32 or i64"));
                }
                // Accept the one extra magnitude needed for a signed minimum literal.
                if let ExprKind::Int(n, suffix) = arg.kind {
                    if let Some(s) = suffix {
                        self.expect(suffix_ty(s, arg.span)?, ty, arg.span)?;
                    }
                    if n == ty.limit() + 1 {
                        self.temp(
                            ty,
                            if ty == Ty::I32 {
                                "INT32_MIN"
                            } else {
                                "INT64_MIN"
                            }
                            .into(),
                        )
                    } else {
                        let v = self.expr(arg, Some(ty))?;
                        self.arithmetic(
                            Op::Sub,
                            Value {
                                ty,
                                name: "0".into(),
                            },
                            v,
                        )
                    }
                } else {
                    let v = self.expr(arg, Some(ty))?;
                    self.arithmetic(
                        Op::Sub,
                        Value {
                            ty,
                            name: "0".into(),
                        },
                        v,
                    )
                }
            }
            ExprKind::Binary(op, l, r) if matches!(op, Op::And | Op::Or) => {
                let a = self.expr(l, Some(Ty::Bool))?;
                let result = self.temp(Ty::Bool, a.name);
                self.line(format!(
                    "if ({}{}) {{",
                    if *op == Op::Or { "!" } else { "" },
                    result.name
                ));
                let b = self.expr(r, Some(Ty::Bool))?;
                self.line(format!("{} = {};", result.name, b.name));
                self.line("}");
                result
            }
            ExprKind::Binary(op, l, r) => {
                let ty = if op.comparison() {
                    self.hint(l).or_else(|| self.hint(r)).unwrap_or(Ty::I32)
                } else {
                    expected
                        .filter(|t| t.numeric())
                        .or_else(|| self.hint(l))
                        .or_else(|| self.hint(r))
                        .unwrap_or(Ty::I32)
                };
                let a = self.expr(l, Some(ty))?;
                let b = if matches!(op, Op::Shl | Op::Shr) {
                    let count_ty = self.hint(r).filter(|t| t.numeric()).unwrap_or(Ty::U64);
                    self.expr(r, Some(count_ty))?
                } else {
                    self.expr(r, Some(ty))?
                };
                if op.comparison() {
                    if !ty.numeric() && !(ty == Ty::Bool && matches!(op, Op::Eq | Op::Ne)) {
                        return Err(error(
                            e.span,
                            "comparison requires integers (or bool for == and !=)",
                        ));
                    }
                    self.temp(Ty::Bool, format!("{} {} {}", a.name, op.c(), b.name))
                } else {
                    if !ty.numeric() {
                        return Err(error(e.span, "arithmetic requires integer operands"));
                    }
                    self.arithmetic(*op, a, b)
                }
            }
        };
        if let Some(want) = expected {
            self.expect(val.ty, want, e.span)?;
        }
        Ok(val)
    }
    fn arithmetic(&mut self, op: Op, a: Value, b: Value) -> Value {
        let suffix = a.ty.name(self.structs);
        let operation = match op {
            Op::Add => "add",
            Op::Sub => "sub",
            Op::Mul => "mul",
            Op::Div => "div",
            Op::Rem => "rem",
            Op::BitAnd => "and",
            Op::BitOr => "or",
            Op::BitXor => "xor",
            Op::Shl => "shl",
            Op::Shr => "shr",
            _ => unreachable!(),
        };
        self.temp(
            a.ty,
            format!(
                "__zen_{operation}_{suffix}({}, {})",
                a.name,
                if matches!(op, Op::Shl | Op::Shr) {
                    format!("(uint64_t){}", b.name)
                } else {
                    b.name
                }
            ),
        )
    }
    fn block(&mut self, block: &Block) -> Result<bool> {
        self.scopes.push(BTreeMap::new());
        self.line("{");
        let mut returns = false;
        for stmt in block {
            let r = self.stmt(stmt)?;
            returns |= r;
        }
        self.line("}");
        self.scopes.pop();
        Ok(returns)
    }
    fn let_array(
        &mut self,
        name: &str,
        mutable: bool,
        elem: Elem,
        len: usize,
        init: &Expr,
    ) -> Result<()> {
        let cname = self.fresh();
        self.line(format!(
            "{};",
            Ty::Array(elem, len).declaration(&cname, self.structs)
        ));
        match &init.kind {
            ExprKind::ArrayLit(elements) => {
                if elements.len() != len {
                    return Err(error(
                        init.span,
                        format!(
                            "array literal has {} elements but [{}; {}] requires {}",
                            elements.len(),
                            elem.ty().name(self.structs),
                            len,
                            len
                        ),
                    ));
                }
                for (i, element) in elements.iter().enumerate() {
                    let val = self.expr(element, Some(elem.ty()))?;
                    self.line(format!("{cname}[{i}] = {};", val.name));
                }
            }
            ExprKind::ArrayRepeat(value, count) => {
                if *count != len {
                    return Err(error(
                        init.span,
                        format!(
                            "array repetition count {} does not match declared length {}",
                            count, len
                        ),
                    ));
                }
                // The repeated value is evaluated exactly once, then copied.
                let val = self.expr(value, Some(elem.ty()))?;
                let i = self.fresh();
                self.line(format!(
                    "for (uint64_t {i} = 0; {i} < UINT64_C({len}); {i} += 1) {{ {cname}[{i}] = {}; }}",
                    val.name
                ));
            }
            _ => {
                return Err(error(
                    init.span,
                    "an array variable must be initialized with [e1, e2, ...] or [value; N]",
                ))
            }
        }
        self.scopes.last_mut().unwrap().insert(
            name.to_string(),
            Binding {
                ty: Ty::Array(elem, len),
                mutable,
                name: cname,
            },
        );
        Ok(())
    }
    /// Struct locals are initialized field by field from a literal. Whole-struct
    /// copies are not part of the MVP, so a literal is the only initializer.
    fn let_struct(&mut self, name: &str, mutable: bool, id: usize, init: &Expr) -> Result<()> {
        let ExprKind::StructLit(lit_name, fields) = &init.kind else {
            return Err(error(
                init.span,
                format!(
                    "struct variable '{name}' must be initialized with a struct literal '{} {{ ... }}'",
                    self.structs[id].name
                ),
            ));
        };
        if lit_name != &self.structs[id].name {
            return Err(error(
                init.span,
                format!(
                    "type mismatch: expected struct {}, found struct {}",
                    self.structs[id].name, lit_name
                ),
            ));
        }
        let declared: Vec<(String, Ty)> = self.structs[id]
            .fields
            .iter()
            .map(|field| (field.name.clone(), field.ty))
            .collect();
        // Reject unknown and missing fields before evaluating any value.
        for field in fields {
            if !declared.iter().any(|(name, _)| name == &field.name) {
                return Err(error(
                    field.span,
                    format!(
                        "unknown field '{}' in initializer of struct '{}'",
                        field.name, self.structs[id].name
                    ),
                ));
            }
        }
        for (field, _) in &declared {
            if !fields.iter().any(|init| &init.name == field) {
                return Err(error(
                    init.span,
                    format!(
                        "missing field '{}' in initializer of struct '{}'",
                        field, self.structs[id].name
                    ),
                ));
            }
        }
        let cname = self.fresh();
        self.line(format!("{} {};", Ty::Struct(id).c(self.structs), cname));
        // Evaluate and assign in source order, exactly once per field.
        for field in fields {
            let index = declared
                .iter()
                .position(|(name, _)| name == &field.name)
                .ok_or_else(|| {
                    error(
                        field.span,
                        format!(
                            "unknown field '{}' in initializer of struct '{}'",
                            field.name, self.structs[id].name
                        ),
                    )
                })?;
            let value = self.expr(&field.value, Some(declared[index].1))?;
            self.line(format!("{cname}.{} = {};", member_name(index), value.name));
        }
        self.scopes.last_mut().unwrap().insert(
            name.to_string(),
            Binding {
                ty: Ty::Struct(id),
                mutable,
                name: cname,
            },
        );
        Ok(())
    }
    fn stmt(&mut self, s: &Stmt) -> Result<bool> {
        match &s.kind {
            StmtKind::Let(name, _, mutable, ty, init) => {
                if self.structs.iter().any(|def| def.name == *name) {
                    return Err(error(
                        s.span,
                        format!("local '{name}' conflicts with struct '{name}'"),
                    ));
                }
                if self.scopes.last().unwrap().contains_key(name) {
                    return Err(error(
                        s.span,
                        format!("duplicate local '{name}' in this scope"),
                    ));
                }
                if let Some(Ty::Struct(id)) = *ty {
                    self.let_struct(name, *mutable, id, init)?;
                    return Ok(false);
                }
                if let Some(Ty::Array(elem, len)) = *ty {
                    self.let_array(name, *mutable, elem, len, init)?;
                    return Ok(false);
                }
                if let ExprKind::StructLit(lit_name, _) = &init.kind {
                    if let Some(declared) = *ty {
                        return Err(error(
                            init.span,
                            format!(
                                "type mismatch: expected {}, found struct {}",
                                self.ty_name(declared),
                                lit_name
                            ),
                        ));
                    }
                    let id = self
                        .structs
                        .iter()
                        .position(|def| &def.name == lit_name)
                        .ok_or_else(|| error(init.span, format!("unknown struct '{lit_name}'")))?;
                    self.let_struct(name, *mutable, id, init)?;
                    return Ok(false);
                }
                let val = self.expr(init, *ty)?;
                if val.ty == Ty::Void {
                    return Err(error(s.span, "cannot bind a void value"));
                }
                let cname = self.fresh();
                self.line(format!(
                    "{} {cname} = {};",
                    val.ty.c(self.structs),
                    val.name
                ));
                self.scopes.last_mut().unwrap().insert(
                    name.clone(),
                    Binding {
                        ty: val.ty,
                        mutable: *mutable,
                        name: cname,
                    },
                );
            }
            StmtKind::Assign(place, op, rhs) => match place {
                Place::Var(name) => {
                    let b = self.binding(name, s.span)?;
                    if b.ty == Ty::Slice {
                        return Err(error(
                            s.span,
                            format!(
                                "cannot assign to slice parameter '{name}'; write to an element with {name}[i] = value"
                            ),
                        ));
                    }
                    if matches!(b.ty, Ty::Array(..)) {
                        return Err(error(
                            s.span,
                            format!(
                                "cannot assign to array variable '{name}'; assign to an element with a[i] = value"
                            ),
                        ));
                    }
                    if matches!(b.ty, Ty::Struct(..)) {
                        return Err(error(
                            s.span,
                            format!(
                                "cannot assign to whole struct variable '{name}'; assign to a field with {name}.field = value"
                            ),
                        ));
                    }
                    if !b.mutable {
                        return Err(error(
                            s.span,
                            format!("cannot assign to immutable variable '{name}'; use let mut"),
                        ));
                    }
                    let value = if matches!(op, Some(Op::Shl | Op::Shr)) {
                        let count_ty = self.hint(rhs).filter(|t| t.numeric()).unwrap_or(Ty::U64);
                        self.expr(rhs, Some(count_ty))?
                    } else {
                        self.expr(rhs, Some(b.ty))?
                    };
                    let value = if let Some(op) = op {
                        if !b.ty.numeric() {
                            return Err(error(s.span, "compound assignment requires integers"));
                        }
                        self.arithmetic(
                            *op,
                            Value {
                                ty: b.ty,
                                name: b.name.clone(),
                            },
                            value,
                        )
                    } else {
                        value
                    };
                    self.line(format!("{} = {};", b.name, value.name));
                }
                Place::Index(name, index) => {
                    let b = self.binding(name, s.span)?;
                    let (elem, prefix, len) = match b.ty {
                        Ty::Array(elem, len) => {
                            if !b.mutable {
                                return Err(error(
                                    s.span,
                                    format!(
                                        "cannot write to an element of immutable array '{name}'; use let mut"
                                    ),
                                ));
                            }
                            (elem, b.name.clone(), format!("UINT64_C({len})"))
                        }
                        // A slice parameter borrows its storage: the pointer and
                        // length travel by value, but elements are writable.
                        Ty::Slice => (
                            Elem::U64,
                            format!("{}.data", b.name),
                            format!("{}.len", b.name),
                        ),
                        _ => {
                            return Err(error(
                                index.span,
                                format!(
                                    "variable '{name}' is not an array or slice; only indexed elements can be assigned"
                                ),
                            ))
                        }
                    };
                    let idx = self.expr(index, None)?;
                    if !idx.ty.numeric() {
                        return Err(error(index.span, "array index must be an integer"));
                    }
                    // Index is evaluated once, then checked before the element access.
                    let checked = self.temp(
                        Ty::U64,
                        format!("__zen_index_check((uint64_t)({}), {len})", idx.name),
                    );
                    let value = if matches!(op, Some(Op::Shl | Op::Shr)) {
                        let count_ty = self.hint(rhs).filter(|t| t.numeric()).unwrap_or(Ty::U64);
                        self.expr(rhs, Some(count_ty))?
                    } else {
                        self.expr(rhs, Some(elem.ty()))?
                    };
                    let target = format!("{prefix}[{}]", checked.name);
                    let value_name = if let Some(op) = op {
                        if !elem.ty().numeric() {
                            return Err(error(
                                s.span,
                                "compound assignment requires integer array elements",
                            ));
                        }
                        let current = self.temp(elem.ty(), target.clone());
                        self.arithmetic(*op, current, value).name
                    } else {
                        value.name
                    };
                    self.line(format!("{target} = {value_name};"));
                }
                Place::Field(name, field) => {
                    let (b, index, field_ty) = self.struct_var_field(name, field, s.span)?;
                    if !b.mutable {
                        return Err(error(
                            s.span,
                            format!(
                                "cannot assign to field '{field}' of immutable variable '{name}'; use let mut"
                            ),
                        ));
                    }
                    let value = if matches!(op, Some(Op::Shl | Op::Shr)) {
                        let count_ty = self.hint(rhs).filter(|t| t.numeric()).unwrap_or(Ty::U64);
                        self.expr(rhs, Some(count_ty))?
                    } else {
                        self.expr(rhs, Some(field_ty))?
                    };
                    let target = format!("{}.{}", b.name, member_name(index));
                    let value_name = if let Some(op) = op {
                        if !field_ty.numeric() {
                            return Err(error(
                                s.span,
                                "compound assignment requires integer struct fields",
                            ));
                        }
                        let current = self.temp(field_ty, target.clone());
                        self.arithmetic(*op, current, value).name
                    } else {
                        value.name
                    };
                    self.line(format!("{target} = {value_name};"));
                }
            },
            StmtKind::Expr(e) => {
                self.expr(e, None)?;
            }
            StmtKind::Return(e) => {
                if let Some(e) = e {
                    if self.ret == Ty::Void {
                        return Err(error(s.span, "void function cannot return a value"));
                    }
                    let val = self.expr(e, Some(self.ret))?;
                    self.line(format!("return {};", val.name));
                } else {
                    self.expect(Ty::Void, self.ret, s.span)?;
                    self.line("return;");
                }
                return Ok(true);
            }
            StmtKind::If(cond, yes, no) => {
                let val = self.expr(cond, Some(Ty::Bool))?;
                self.line(format!("if ({})", val.name));
                let yes_returns = self.block(yes)?;
                let no_returns = if let Some(no) = no {
                    self.line("else");
                    self.block(no)?
                } else {
                    false
                };
                return Ok(yes_returns && no_returns);
            }
            StmtKind::While(cond, body) => {
                self.line("while (true) {");
                let val = self.expr(cond, Some(Ty::Bool))?;
                self.line(format!("if (!{}) break;", val.name));
                self.loops += 1;
                self.block(body)?;
                self.loops -= 1;
                self.line("}");
            }
            StmtKind::Block(block) => return self.block(block),
            StmtKind::Unsafe(block) => {
                self.unsafe_depth += 1;
                let result = self.block(block);
                self.unsafe_depth -= 1;
                return result;
            }
            StmtKind::Break | StmtKind::Continue => {
                if self.loops == 0 {
                    return Err(error(
                        s.span,
                        "break/continue is only valid inside a while loop",
                    ));
                }
                self.line(if matches!(s.kind, StmtKind::Break) {
                    "break;"
                } else {
                    "continue;"
                });
            }
        }
        Ok(false)
    }
}

fn prelude(mode: Mode) -> String {
    let mut out=String::from("/* Generated by the checked Zen bootstrap compiler. */\n#include <stdint.h>\n#include <stdbool.h>\n#include <stddef.h>\ntypedef struct { const unsigned char *data; size_t len; } __zen_string;\ntypedef struct { uint64_t *data; uint64_t len; } __zen_slice_u64;\n");
    if mode == Mode::Hosted {
        out.push_str(r#"
#include <stdio.h>
#include <stdlib.h>
#include <inttypes.h>
static void __zen_fail(const char *s) { fputs(s,stderr); exit(1); }
static void __zen_print(__zen_string s) { if (fwrite(s.data,1,s.len,stdout)!=s.len) __zen_fail("Zen runtime error: output failed\n"); }
static void __zen_print_uint(uint64_t n) { if (printf("%" PRIu64,n)<0) __zen_fail("Zen runtime error: output failed\n"); }
static void __zen_print_int(int64_t n) { if (printf("%" PRId64,n)<0) __zen_fail("Zen runtime error: output failed\n"); }
"#);
    } else {
        out.push_str("static void __zen_fail(const char *s) { (void)s; __builtin_trap(); }\n");
    }
    // Arithmetic conversion avoids signed out-of-range casts and libc bit copies.
    out.push_str(r#"
static int32_t __zen_bits_i32(uint32_t n) { return n <= INT32_MAX ? (int32_t)n : -1-(int32_t)(UINT32_MAX-n); }
static int64_t __zen_bits_i64(uint64_t n) { return n <= INT64_MAX ? (int64_t)n : -1-(int64_t)(UINT64_MAX-n); }
static uint64_t __zen_str_len(__zen_string s) { return (uint64_t)s.len; }
static uint8_t __zen_str_byte(__zen_string s,uint64_t n) { if (n>=s.len) __zen_fail("Zen runtime error: string index out of bounds\n"); return s.data[n]; }
static bool __zen_str_eq(__zen_string a,__zen_string b) {
    if (a.len != b.len) return false;
    for (size_t i = 0; i < a.len; i += 1) { if (a.data[i] != b.data[i]) return false; }
    return true;
}
static int32_t __zen_str_cmp(__zen_string a,__zen_string b) {
    size_t n = a.len < b.len ? a.len : b.len;
    for (size_t i = 0; i < n; i += 1) {
        if (a.data[i] < b.data[i]) return -1;
        if (a.data[i] > b.data[i]) return 1;
    }
    if (a.len < b.len) return -1;
    if (a.len > b.len) return 1;
    return 0;
}
static int64_t __zen_str_find(__zen_string haystack,__zen_string needle) {
    if (needle.len == 0) return 0;
    if (needle.len > haystack.len) return -1;
    size_t last = haystack.len - needle.len;
    for (size_t i = 0; i <= last; i += 1) {
        size_t j = 0;
        while (j < needle.len && haystack.data[i+j] == needle.data[j]) j += 1;
        if (j == needle.len) {
            uint64_t index = (uint64_t)i;
            // Static str views are source-bounded; keep the i64 result defined anyway.
            if (index > (uint64_t)INT64_MAX) return -1;
            return (int64_t)index;
        }
    }
    return -1;
}
static bool __zen_str_starts_with(__zen_string s,__zen_string prefix) {
    if (prefix.len > s.len) return false;
    for (size_t i = 0; i < prefix.len; i += 1) { if (s.data[i] != prefix.data[i]) return false; }
    return true;
}
static bool __zen_str_ends_with(__zen_string s,__zen_string suffix) {
    if (suffix.len > s.len) return false;
    size_t offset = s.len - suffix.len;
    for (size_t i = 0; i < suffix.len; i += 1) { if (s.data[offset+i] != suffix.data[i]) return false; }
    return true;
}
static int64_t __zen_str_rfind(__zen_string haystack,__zen_string needle) {
    if (needle.len == 0) {
        // Empty needle matches at the end; keep the i64 result defined.
        if (haystack.len > (size_t)INT64_MAX) return -1;
        return (int64_t)haystack.len;
    }
    if (needle.len > haystack.len) return -1;
    size_t start = haystack.len - needle.len;
    for (;;) {
        size_t j = 0;
        while (j < needle.len && haystack.data[start+j] == needle.data[j]) j += 1;
        if (j == needle.len) {
            uint64_t index = (uint64_t)start;
            // Static str views are source-bounded; keep the i64 result defined anyway.
            if (index > (uint64_t)INT64_MAX) return -1;
            return (int64_t)index;
        }
        if (start == 0) break;
        start -= 1;
    }
    return -1;
}
static uint64_t __zen_index_check(uint64_t idx,uint64_t len) { if (idx>=len) __zen_fail("Zen runtime error: array index out of bounds\n"); return idx; }
static uint64_t __zen_slice_len(__zen_slice_u64 s) { return s.len; }
"#);
    for ty in [Ty::U8, Ty::U16, Ty::U32, Ty::U64, Ty::I32, Ty::I64] {
        let c = ty.c(&[]);
        let suffix = ty.name(&[]);
        let bits = ty.bits();
        let convert = |expr: &str| match ty {
            Ty::I32 => format!("__zen_bits_i32((uint32_t)({expr}))"),
            Ty::I64 => format!("__zen_bits_i64((uint64_t)({expr}))"),
            _ => format!("({c})({expr})"),
        };
        for (name, op) in [
            ("add", "+"),
            ("sub", "-"),
            ("mul", "*"),
            ("and", "&"),
            ("or", "|"),
            ("xor", "^"),
        ] {
            let expr = convert(&format!("(uint64_t)a {op} (uint64_t)b"));
            out.push_str(&format!(
                "static {c} __zen_{name}_{suffix}({c} a,{c} b) {{ return {expr}; }}\n"
            ));
        }
        let overflow = match ty {
            Ty::I32 => " || (a==INT32_MIN && b==-1)",
            Ty::I64 => " || (a==INT64_MIN && b==-1)",
            _ => "",
        };
        for (name, op) in [("div", "/"), ("rem", "%")] {
            out.push_str(&format!("static {c} __zen_{name}_{suffix}({c} a,{c} b) {{ if (!b{overflow}) __zen_fail(\"Zen runtime error: division by zero or signed division overflow\\n\"); return a{op}b; }}\n"));
        }
        let left = convert("(uint64_t)a << b");
        let right = if matches!(ty, Ty::I32 | Ty::I64) {
            format!(
                "a>=0 ? {} : {}",
                convert("(uint64_t)a >> b"),
                convert("~((uint64_t)(~a) >> b)")
            )
        } else {
            convert("(uint64_t)a >> b")
        };
        for (name, expr) in [("shl", left), ("shr", right)] {
            out.push_str(&format!("static {c} __zen_{name}_{suffix}({c} a,uint64_t b) {{ if (b>={bits}) __zen_fail(\"Zen runtime error: shift count out of range\\n\"); return {expr}; }}\n"));
        }
    }
    out
}

pub fn check(source: &str) -> Result<()> {
    check_with_mode(source, Mode::Hosted)
}
pub fn emit_c(source: &str) -> Result<String> {
    emit_c_with_mode(source, Mode::Hosted)
}
pub fn check_with_mode(source: &str, mode: Mode) -> Result<()> {
    emit_c_with_mode(source, mode).map(|_| ())
}

/// Validate and emit C for hosted programs or a freestanding object module.
/// In freestanding mode public functions export scalar C ABI symbols. Hosted
/// pub controls Zen visibility only; symbols stay internal to protect libc.
/// Extern C declarations are imports in both modes and calls require unsafe.
pub fn emit_c_with_mode(source: &str, mode: Mode) -> Result<String> {
    emit_c_with_mode_inner(source, mode, true)
}

/// Shared checker/emitter. `require_main` is false only for linting a module
/// that has no hosted entry point (libraries and freestanding-style modules);
/// every other syntax, name, type, safety and ABI check still runs.
fn emit_c_with_mode_inner(source: &str, mode: Mode, require_main: bool) -> Result<String> {
    let mut parser = Parser::new(source)?;
    let functions = parser.program()?;
    let structs = parser.structs;
    let span = Span::new(0, 0, 0);
    let mut signatures = BTreeMap::new();
    let mut builtins = vec![
        ("slice_len", vec![Ty::Slice], Ty::U64, "__zen_slice_len"),
        ("str_len", vec![Ty::Str], Ty::U64, "__zen_str_len"),
        ("str_byte", vec![Ty::Str, Ty::U64], Ty::U8, "__zen_str_byte"),
        ("str_eq", vec![Ty::Str, Ty::Str], Ty::Bool, "__zen_str_eq"),
        ("str_cmp", vec![Ty::Str, Ty::Str], Ty::I32, "__zen_str_cmp"),
        (
            "str_find",
            vec![Ty::Str, Ty::Str],
            Ty::I64,
            "__zen_str_find",
        ),
        (
            "str_starts_with",
            vec![Ty::Str, Ty::Str],
            Ty::Bool,
            "__zen_str_starts_with",
        ),
        (
            "str_ends_with",
            vec![Ty::Str, Ty::Str],
            Ty::Bool,
            "__zen_str_ends_with",
        ),
        (
            "str_rfind",
            vec![Ty::Str, Ty::Str],
            Ty::I64,
            "__zen_str_rfind",
        ),
    ];
    if mode == Mode::Hosted {
        builtins.extend([
            ("print", vec![Ty::Str], Ty::Void, "__zen_print"),
            ("print_uint", vec![Ty::U64], Ty::Void, "__zen_print_uint"),
            ("print_int", vec![Ty::I64], Ty::Void, "__zen_print_int"),
        ]);
    }
    for (name, params, ret, cname) in builtins {
        signatures.insert(
            name.to_string(),
            Sig {
                params,
                ret,
                name: cname.into(),
                external: false,
            },
        );
    }
    for (i, f) in functions.iter().enumerate() {
        if signatures.contains_key(&f.name)
            || matches!(f.name.as_str(), "volatile_load" | "volatile_store")
        {
            return Err(error(
                f.span,
                format!("duplicate or reserved function '{}'", f.name),
            ));
        }
        let abi = (f.public && mode == Mode::Freestanding) || f.body.is_none();
        if abi {
            if f.name.starts_with("__zen_") {
                return Err(error(
                    f.span,
                    "external symbols with prefix __zen_ are reserved",
                ));
            }
            if f.ret == Ty::Str
                || matches!(f.ret, Ty::Slice)
                || f.params
                    .iter()
                    .any(|p| p.1 == Ty::Str || matches!(p.1, Ty::Slice))
            {
                return Err(error(
                    f.span,
                    "C ABI functions support only scalar and raw-pointer types",
                ));
            }
            if mode == Mode::Hosted && f.name == "main" && f.body.is_none() {
                return Err(error(
                    f.span,
                    "hosted main must be a defined Zen entry function",
                ));
            }
        }
        // Duplicate imported parameter names are invalid even without a body.
        let mut names = BTreeMap::new();
        for (name, _, span) in &f.params {
            if names.insert(name, ()).is_some() {
                return Err(error(*span, format!("duplicate parameter '{name}'")));
            }
            if structs.iter().any(|def| def.name == *name) {
                return Err(error(
                    *span,
                    format!("parameter '{name}' conflicts with struct '{name}'"),
                ));
            }
        }
        if structs.iter().any(|def| def.name == f.name) {
            return Err(error(
                f.span,
                format!("function '{}' conflicts with struct '{}'", f.name, f.name),
            ));
        }
        signatures.insert(
            f.name.clone(),
            Sig {
                params: f.params.iter().map(|p| p.1).collect(),
                ret: f.ret,
                name: format!("__zen_f{i}"),
                external: f.body.is_none(),
            },
        );
    }
    if mode == Mode::Hosted && require_main {
        let main = functions
            .iter()
            .find(|f| f.name == "main" && f.body.is_some())
            .ok_or_else(|| error(span, "program requires fn main() -> i32"))?;
        if main.ret != Ty::I32 || !main.params.is_empty() {
            return Err(error(
                main.span,
                "main must have signature fn main() -> i32",
            ));
        }
    }
    let mut output = prelude(mode);
    // Nominal struct layout: natural C alignment, members renamed positionally
    // so Zen field names can never collide with C keywords or runtime symbols.
    for def in &structs {
        output.push_str("typedef struct {\n");
        for (index, field) in def.fields.iter().enumerate() {
            output.push_str(&format!(
                "{} {};\n",
                field.ty.c(&structs),
                member_name(index)
            ));
        }
        output.push_str(&format!("}} __zen_Struct_{};\n", def.name));
    }
    for f in &functions {
        let sig = &signatures[&f.name];
        let params = if sig.params.is_empty() {
            "void".into()
        } else {
            sig.params
                .iter()
                .map(|t| t.c(&structs))
                .collect::<Vec<_>>()
                .join(", ")
        };
        if (f.public && mode == Mode::Freestanding) || f.body.is_none() {
            // Symbols retain the requested ABI spelling even if it is a C keyword.
            output.push_str(&format!(
                "{} {}({params}) __asm__(\"{}\");\n",
                f.ret.c(&structs),
                sig.name,
                f.name
            ));
        } else {
            output.push_str(&format!(
                "static {} {}({params});\n",
                f.ret.c(&structs),
                sig.name
            ));
        }
    }
    for f in &functions {
        let Some(body) = &f.body else {
            continue;
        };
        let mut emit = Emitter {
            signatures: &signatures,
            structs: &structs,
            scopes: vec![BTreeMap::new()],
            output: String::new(),
            next: 0,
            ret: f.ret,
            loops: 0,
            unsafe_depth: 0,
        };
        let mut params = Vec::new();
        for (name, ty, _) in &f.params {
            let cname = emit.fresh();
            params.push(format!("{} {cname}", ty.c(&structs)));
            emit.scopes[0].insert(
                name.clone(),
                Binding {
                    ty: *ty,
                    mutable: false,
                    name: cname,
                },
            );
        }
        if params.is_empty() {
            params.push("void".into());
        }
        emit.line(format!(
            "{}{} {}({})",
            if f.public && mode == Mode::Freestanding {
                ""
            } else {
                "static "
            },
            f.ret.c(&structs),
            signatures[&f.name].name,
            params.join(", ")
        ));
        let returns = emit.block(body)?;
        if f.ret != Ty::Void && !returns {
            return Err(error(
                f.span,
                format!(
                    "function '{}' does not return a value on every path",
                    f.name
                ),
            ));
        }
        output.push_str(&emit.output);
    }
    if mode == Mode::Hosted && require_main {
        output.push_str(&format!(
            "int main(void) {{ return (int){}(); }}\n",
            signatures["main"].name
        ));
    }
    Ok(output)
}

// ---------------------------------------------------------------------------
// Static lint analysis (TASK-909)
// ---------------------------------------------------------------------------

/// Lint a hosted module: unused locals/parameters/functions and statements
/// after a `return` in the same block. The program is fully checked first, so
/// invalid source is returned as `Err` and rendered by the CLI as a compiler
/// error diagnostic. A module without `fn main` is accepted as a library (or
/// freestanding module) after the normal body/type checks.
pub fn lint(source: &str) -> Result<Vec<LintDiagnostic>> {
    lint_with_mode(source, Mode::Hosted)
}

/// Lint with an explicit target mode. Both modes share the same rules; the
/// mode only affects which compiler checks validate the file first.
pub fn lint_with_mode(source: &str, mode: Mode) -> Result<Vec<LintDiagnostic>> {
    validate_for_lint(source, mode)?;
    let mut parser = Parser::new(source)?;
    let functions = parser.program()?;
    Ok(analyze_lint(source, &functions))
}

fn is_missing_hosted_main(error: &CompileError) -> bool {
    error.message == "program requires fn main() -> i32"
        && error.span.start == 0
        && error.span.end == 0
}

fn validate_for_lint(source: &str, mode: Mode) -> Result<()> {
    match emit_c_with_mode_inner(source, mode, true) {
        Ok(_) => Ok(()),
        Err(error) if mode == Mode::Hosted && is_missing_hosted_main(&error) => {
            // Libraries and freestanding-style modules have no hosted entry
            // point. Re-run every other check without requiring `main`; if the
            // module is broken, that (more informative) error is reported.
            emit_c_with_mode_inner(source, mode, false).map(|_| ())
        }
        Err(error) => Err(error),
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum LocalKind {
    Variable,
    Parameter,
}

#[derive(Debug)]
struct LintLocal {
    name: String,
    span: Span,
    kind: LocalKind,
    read: bool,
    /// True after a simple assignment or a write through an element/field.
    written: bool,
}

struct LintAnalyzer<'a> {
    source: &'a str,
    diagnostics: Vec<LintDiagnostic>,
    locals: Vec<LintLocal>,
    /// Lexical scopes, innermost last. Values are indexes into `locals`, so
    /// shadowed variables are distinguished while counting reads.
    scopes: Vec<BTreeMap<String, usize>>,
    calls: BTreeSet<String>,
}

fn analyze_lint(source: &str, functions: &[Function]) -> Vec<LintDiagnostic> {
    let mut analyzer = LintAnalyzer {
        source,
        diagnostics: Vec::new(),
        locals: Vec::new(),
        scopes: Vec::new(),
        calls: BTreeSet::new(),
    };
    for function in functions {
        analyzer.function(function);
    }
    analyzer.finish(functions)
}

impl<'a> LintAnalyzer<'a> {
    fn function(&mut self, function: &Function) {
        let Some(body) = &function.body else {
            return;
        };
        let mut parameters = BTreeMap::new();
        for (name, _, span) in &function.params {
            let id = self.locals.len();
            self.locals.push(LintLocal {
                name: name.clone(),
                span: *span,
                kind: LocalKind::Parameter,
                read: false,
                written: false,
            });
            parameters.insert(name.clone(), id);
        }
        self.scopes.push(parameters);
        self.block(body);
        self.scopes.pop();
    }

    fn declare(&mut self, name: &str, span: Span) {
        let id = self.locals.len();
        self.locals.push(LintLocal {
            name: name.to_string(),
            span,
            kind: LocalKind::Variable,
            read: false,
            written: false,
        });
        self.scopes
            .last_mut()
            .expect("a block scope is always open")
            .insert(name.to_string(), id);
    }

    fn lookup(&self, name: &str) -> Option<usize> {
        self.scopes
            .iter()
            .rev()
            .find_map(|scope| scope.get(name).copied())
    }

    fn read_var(&mut self, name: &str) {
        if let Some(id) = self.lookup(name) {
            self.locals[id].read = true;
        }
    }

    fn mark_written(&mut self, name: &str) {
        if let Some(id) = self.lookup(name) {
            self.locals[id].written = true;
        }
    }

    /// Statements after a `return` in the same block are unreachable. Each one
    /// is reported once and not descended into, which avoids cascading warnings
    /// such as unused locals that can never run.
    fn block(&mut self, block: &Block) {
        self.scopes.push(BTreeMap::new());
        let mut unreachable = false;
        for statement in block {
            if unreachable {
                self.diagnostics.push(LintDiagnostic::warning(
                    lint_rules::UNREACHABLE_CODE,
                    "unreachable statement after return",
                    statement.span,
                    self.source,
                ));
                continue;
            }
            self.statement(statement);
            if matches!(statement.kind, StmtKind::Return(_)) {
                unreachable = true;
            }
        }
        self.scopes.pop();
    }

    fn statement(&mut self, statement: &Stmt) {
        match &statement.kind {
            StmtKind::Let(name, name_span, _, _, init) => {
                // The initializer is evaluated before the binding exists, so
                // `let x = x;` reads the previous `x`, matching the emitter.
                self.expr(init);
                self.declare(name, *name_span);
            }
            StmtKind::Assign(place, op, rhs) => {
                match place {
                    Place::Var(name) => {
                        if op.is_some() {
                            self.read_var(name);
                        } else {
                            self.mark_written(name);
                        }
                    }
                    Place::Index(name, index) => {
                        self.expr(index);
                        if op.is_some() {
                            self.read_var(name);
                        }
                        self.mark_written(name);
                    }
                    Place::Field(name, _) => {
                        if op.is_some() {
                            self.read_var(name);
                        }
                        self.mark_written(name);
                    }
                }
                self.expr(rhs);
            }
            StmtKind::Expr(expr) => self.expr(expr),
            StmtKind::Return(expr) => {
                if let Some(expr) = expr {
                    self.expr(expr);
                }
            }
            StmtKind::If(condition, yes, no) => {
                self.expr(condition);
                self.block(yes);
                if let Some(no) = no {
                    self.block(no);
                }
            }
            StmtKind::While(condition, body) => {
                self.expr(condition);
                self.block(body);
            }
            StmtKind::Block(block) | StmtKind::Unsafe(block) => self.block(block),
            StmtKind::Break | StmtKind::Continue => {}
        }
    }

    fn expr(&mut self, expr: &Expr) {
        match &expr.kind {
            ExprKind::Int(..) | ExprKind::Bool(_) | ExprKind::Str(_) => {}
            ExprKind::Var(name) => self.read_var(name),
            ExprKind::Call(name, arguments) => {
                // Any syntactic call keeps a function alive. There are no
                // function values or function pointers in the MVP, so a call
                // is the only reference that can reach a definition.
                self.calls.insert(name.clone());
                for argument in arguments {
                    self.expr(argument);
                }
            }
            ExprKind::Unary(_, argument)
            | ExprKind::BitNot(argument)
            | ExprKind::Cast(argument, _) => self.expr(argument),
            ExprKind::Binary(_, left, right) => {
                self.expr(left);
                self.expr(right);
            }
            ExprKind::ArrayLit(elements) => {
                for element in elements {
                    self.expr(element);
                }
            }
            ExprKind::ArrayRepeat(value, _) => self.expr(value),
            ExprKind::Index(base, index) => {
                self.expr(base);
                self.expr(index);
            }
            ExprKind::Field(base, _) => self.expr(base),
            ExprKind::StructLit(_, fields) => {
                for field in fields {
                    self.expr(&field.value);
                }
            }
        }
    }

    fn finish(mut self, functions: &[Function]) -> Vec<LintDiagnostic> {
        for local in &self.locals {
            if local.read || local.name.starts_with('_') {
                continue;
            }
            let (code, message) = match local.kind {
                LocalKind::Variable if local.written => (
                    lint_rules::UNUSED_VARIABLE,
                    format!("variable '{}' is assigned but never read", local.name),
                ),
                LocalKind::Variable => (
                    lint_rules::UNUSED_VARIABLE,
                    format!("unused variable '{}'", local.name),
                ),
                LocalKind::Parameter => (
                    lint_rules::UNUSED_PARAMETER,
                    format!("unused parameter '{}'", local.name),
                ),
            };
            self.diagnostics.push(LintDiagnostic::warning(
                code,
                message,
                local.span,
                self.source,
            ));
        }
        for function in functions {
            if function.public || function.body.is_none() || function.name == "main" {
                continue;
            }
            if self.calls.contains(&function.name) {
                continue;
            }
            self.diagnostics.push(LintDiagnostic::warning(
                lint_rules::UNUSED_FUNCTION,
                format!("unused function '{}'", function.name),
                function.span,
                self.source,
            ));
        }
        self.diagnostics.sort_by(|a, b| {
            (a.span_start, a.span_end, a.code, a.message.as_str()).cmp(&(
                b.span_start,
                b.span_end,
                b.code,
                b.message.as_str(),
            ))
        });
        self.diagnostics
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn freestanding_exports_bits_casts_and_volatile() {
        let source = r#"
extern "C" { fn fetch(port:u16)->u8; }
pub fn touch(address:u64)->u32 {
    unsafe {
        let ptr:*mut u32=address as *mut u32;
        volatile_store(ptr,0xaabbccddu32);
        let port:u16=0x3f8;
        let value:u8=fetch(port);
        return volatile_load(ptr) ^ ((value as u32) << 16);
    }
}
pub fn rotate(x:u64)->u64 { return (x << 3) | (x >> 61); }
pub fn bytes()->u8 { return str_byte("a\0b",2); }
fn internal(s:str)->u64 { return str_len(s); }
"#;
        let c = emit_c_with_mode(source, Mode::Freestanding).unwrap();
        assert!(c.contains("__asm__(\"touch\")"));
        assert!(c.contains("__asm__(\"fetch\")"));
        assert!(!c.contains("#include <stdio.h>"));
        assert!(!c.contains("memcpy"));
        assert!(!c.contains("int main(void)"));
        assert!(!c.contains("__zen_print("));
    }
    #[test]
    fn hosted_public_names_cannot_replace_runtime_symbols() {
        let source="pub fn printf(n:u64)->u64 { return n; } pub fn fwrite(n:u64)->u64 { return n; } pub fn main()->i32 { print_uint(42); print(\"!\"); return 0; }";
        let c = emit_c(source).unwrap();
        assert!(!c.contains("__asm__(\"printf\")"));
        assert!(!c.contains("__asm__(\"fwrite\")"));
        check("pub fn id(s:str)->str { return s; } pub fn main()->i32 { print(id(\"ok\")); return 0; }").unwrap();
        let free = emit_c_with_mode(
            "pub fn printf(n:u64)->u64 { return n; }",
            Mode::Freestanding,
        )
        .unwrap();
        assert!(free.contains("__asm__(\"printf\")"));
    }

    #[test]
    fn rejects_unsafe_and_invalid_abi() {
        for source in [
            "pub fn f(p:*u8)->u8 { return volatile_load(p); }",
            "pub fn f(p:*u8)->void { unsafe { volatile_store(p,1); } }",
            "pub fn f(p:*mut u8)->void { unsafe { volatile_store(p,true); } }",
            "pub fn f(address:u64)->*u8 { return address as *u8; }",
            "pub fn f(s:str)->u64 { return str_len(s); }",
            "extern \"C\" { fn f(s:str); }",
            "pub fn __zen_fail()->void {}",
            "pub fn f()->void { print(\"x\"); }",
            "extern \"C\" { fn f()->u64; } pub fn g()->u64 { return f(); }",
            "pub fn f(p:*bool)->void {}",
            "pub fn f()->u8 { return 256u8; }",
            "pub fn f()->void { let x=1 as bool; }",
        ] {
            assert!(
                check_with_mode(source, Mode::Freestanding).is_err(),
                "{source}"
            );
        }
    }
    #[test]
    fn added_syntax_keeps_resource_limits() {
        for source in [
            format!("pub fn f()->u8 {{ return 1{}; }}", " as u8".repeat(4000)),
            format!("pub fn f()->u64 {{ return {}1u64; }}", "~".repeat(4000)),
            format!(
                "pub fn f()->void {{ {} {} }}",
                "unsafe {".repeat(4000),
                "}".repeat(4000)
            ),
        ] {
            assert!(check_with_mode(&source, Mode::Freestanding)
                .unwrap_err()
                .message
                .contains("nesting limit"));
        }
    }

    #[test]
    fn rejects_excessive_nesting_without_stack_overflow() {
        let programs = [
            format!(
                "fn main()->i32 {{ return {}0{}; }}",
                "(".repeat(4000),
                ")".repeat(4000)
            ),
            format!("fn main()->i32 {{ return {}0; }}", "-".repeat(4000)),
            format!(
                "fn main()->i32 {{ {}return 0;{} }}",
                "{".repeat(4000),
                "}".repeat(4000)
            ),
            format!("fn main()->i32 {{ return 0{}; }}", "+1".repeat(4000)),
            format!(
                "fn main()->i32 {{ {}return 0; }}",
                "if true {} else ".repeat(4000)
            ),
        ];
        for source in programs {
            let err = check(&source).unwrap_err();
            assert!(err.message.contains("nesting limit"), "{err}");
            assert!((err.span.end as usize) <= source.len());
        }
    }

    #[test]
    fn validates_recursion_and_loops() {
        check("fn fact(n:u64)->u64 { if n<=1 { return 1; } return n*fact(n-1); } fn main()->i32 { let mut n=0; while n<5 { n+=1; } print_uint(fact(10)); return 0; }").unwrap();
    }
    #[test]
    fn rejects_invalid_semantics() {
        for source in [
            "fn main()->i32 { return true; }",
            "fn main()->i32 { let x=1; x=2; return x; }",
            "fn main()->i32 { return missing; }",
            "fn main()->i32 { if true { return 1; } }",
            "fn main()->i32 { print_uint(true); return 0; }",
            "fn main()->i32 { return 2147483648; }",
            "fn main()->i32 { break; return 0; }",
            "fn main()->i32 { let x=print(\"x\"); return 0; }",
            "fn main()->i32 { return foo(); } fn foo()->i64 { return 1; }",
            "fn main()->i32 { return 0; } fn main()->i32 { return 1; }",
            "fn main(x:i32)->i32 { return x; }",
        ] {
            assert!(check(source).is_err(), "{source}");
        }
    }
    #[test]
    fn signed_minimum_and_literal_inference() {
        check("fn main()->i32 { let x:i64=-9223372036854775808; let y:u64=18446744073709551615; print_int(x); print_uint(1+y); return -2147483648; }").unwrap();
    }
    #[test]
    fn rejects_unsupported_constructs() {
        // Structs are supported, but a declaration-only program still needs main.
        assert!(check("struct Point { x: i32 }").is_err());
        assert!(check(
            "struct Point { x: i32 } fn main()->i32 { let p: Point = Point { x: 1 }; return p.x; }"
        )
        .is_ok());
        assert!(check("struct Point { x: f64 } fn main()->i32 { return 0; }").is_err());
        assert!(check("fn main()->i32 { let x:f64=1.0; return 0; }").is_err());
        assert!(check("fn main()->i32 { return 0; } ?").is_err());
    }
    #[test]
    fn fixed_arrays_emit_local_declarations_and_bounds_checks() {
        let c = emit_c(
            "fn main()->i32 { let mut a:[u16;3]=[1;3]; a[1]+=2; let b:[i64;2]=[-1,2]; print_int(b[0]); return a[1] as i32; }",
        )
        .unwrap();
        assert!(c.contains("uint16_t __zen_v0[3];"), "{c}");
        assert!(c.contains("int64_t __zen_v8[2];"), "{c}");
        assert!(c.contains("__zen_index_check((uint64_t)"), "{c}");
        assert!(
            c.contains("Zen runtime error: array index out of bounds"),
            "{c}"
        );
        assert!(c.contains("for (uint64_t"), "{c}");
    }
    #[test]
    fn rejects_arrays_outside_local_scope_or_with_wrong_shape() {
        for source in [
            "fn f(a:[u8;2])->i32 { return 0; } fn main()->i32 { return 0; }",
            "fn f()->[u8;2] { let a:[u8;2]=[1;2]; return a; } fn main()->i32 { return 0; }",
            "fn main()->i32 { let a:[u8;2]=[1]; return 0; }",
            "fn main()->i32 { let a=[1,2]; return 0; }",
            "fn main()->i32 { let a:[u8;2]=[1;2]; print_uint(a); return 0; }",
        ] {
            assert!(check(source).is_err(), "{source}");
        }
    }
}
