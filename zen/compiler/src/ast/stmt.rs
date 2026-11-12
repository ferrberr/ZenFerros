//! Statement AST nodes

use crate::lexer::Span;
use crate::ast::expr::{Expr, Pattern, Param};
use crate::ast::ty::Type;
use crate::ast::ident::{Ident, Path};

#[derive(Debug, Clone, PartialEq)]
pub struct Stmt {
    pub kind: StmtKind,
    pub span: Span,
}

impl Stmt {
    pub fn new(kind: StmtKind, span: Span) -> Self {
        Self { kind, span }
    }
}

#[derive(Debug, Clone, PartialEq)]
pub enum StmtKind {
    // Expression statement (expr;)
    Expr(Expr),

    // Let binding: let pat: ty = expr;
    Let {
        pat: Pattern,
        ty: Option<Type>,
        init: Option<Expr>,
    },

    // Item declaration (fn, struct, impl, const, etc.)
    Item(Item),

    // Empty statement
    Empty,
}

// Items (top-level declarations)
#[derive(Debug, Clone, PartialEq)]
pub struct Item {
    pub kind: ItemKind,
    pub span: Span,
    pub visibility: Visibility,
    pub attributes: Vec<Attribute>,
}

#[derive(Debug, Clone, PartialEq)]
pub enum Visibility {
    Private,
    Public,
    PubCrate,
    PubSuper,
    PubIn(Path),
}

#[derive(Debug, Clone, PartialEq)]
pub struct Attribute {
    pub path: Path,
    pub args: Vec<Expr>, // simplified
}

#[derive(Debug, Clone, PartialEq)]
pub enum ItemKind {
    // Function
    Fn(FnSig, Box<Expr>), // signature, body (block expr)

    // Struct
    Struct {
        name: Ident,
        generics: Vec<GenericParam>,
        fields: Vec<StructField>,
    },

    // Enum
    Enum {
        name: Ident,
        generics: Vec<GenericParam>,
        variants: Vec<EnumVariant>,
    },

    // Impl block
    Impl {
        generics: Vec<GenericParam>,
        trait_ref: Option<Path>, // None for inherent impl
        self_ty: Type,
        items: Vec<ImplItem>,
    },

    // Type alias
    TypeAlias {
        name: Ident,
        generics: Vec<GenericParam>,
        ty: Type,
    },

    // Const
    Const {
        name: Ident,
        ty: Type,
        value: Expr,
    },

    // Static
    Static {
        name: Ident,
        ty: Type,
        mutability: Mutability,
        value: Expr,
    },

    // Module declaration
    Mod {
        name: Ident,
        body: Option<Vec<Item>>, // inline module
    },

    // Use declaration
    Use {
        tree: UseTree,
    },

    // Extern block
    Extern {
        abi: Option<String>,
        items: Vec<ForeignItem>,
    },
}

#[derive(Debug, Clone, PartialEq)]
pub struct GenericParam {
    pub name: Ident,
    pub kind: GenericParamKind,
    pub span: Span,
}

#[derive(Debug, Clone, PartialEq)]
pub enum GenericParamKind {
    Type { bounds: Vec<Path>, default: Option<Type> },
    Const { ty: Type, default: Option<Expr> },
}

#[derive(Debug, Clone, PartialEq)]
pub struct StructField {
    pub name: Ident,
    pub ty: Type,
    pub visibility: Visibility,
    pub span: Span,
}

#[derive(Debug, Clone, PartialEq)]
pub struct EnumVariant {
    pub name: Ident,
    pub data: EnumVariantData,
    pub discriminant: Option<Expr>,
    pub span: Span,
}

#[derive(Debug, Clone, PartialEq)]
pub enum EnumVariantData {
    Unit,
    Tuple(Vec<Type>),
    Struct(Vec<StructField>),
}

#[derive(Debug, Clone, PartialEq)]
pub enum ImplItem {
    Fn(FnSig, Box<Expr>),
    Const { name: Ident, ty: Type, value: Expr },
    TypeAlias { name: Ident, generics: Vec<GenericParam>, ty: Type },
}

#[derive(Debug, Clone, PartialEq)]
pub struct FnSig {
    pub name: Ident,
    pub generics: Vec<GenericParam>,
    pub params: Vec<Param>,
    pub ret_ty: Type,
    pub span: Span,
    pub is_async: bool,
    pub is_unsafe: bool,
    pub is_extern: bool,
    pub abi: Option<String>,
}

#[derive(Debug, Clone, PartialEq)]
pub enum UseTree {
    Path(Path),
    Glob(Path),
    Group { prefix: Path, items: Vec<UseTree> },
    Rename { prefix: Path, name: Ident, alias: Ident },
}

#[derive(Debug, Clone, PartialEq)]
pub struct ForeignItem {
    pub kind: ForeignItemKind,
    pub span: Span,
}

#[derive(Debug, Clone, PartialEq)]
pub enum ForeignItemKind {
    Fn(FnSig),
    Static { name: Ident, ty: Type, mutability: Mutability },
    Type { name: Ident },
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Mutability {
    Immutable,
    Mutable,
}