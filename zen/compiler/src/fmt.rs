//! Canonical formatter for the Zen source subset (`zen fmt`).
//!
//! The formatter works on the token stream produced by
//! [`Lexer::with_comments`], so comments can be preserved without making the
//! parser aware of them. Token text is copied from the original source span;
//! the formatter only inserts whitespace and never rewrites a literal.
//!
//! Safety: [`format`] re-lexes its own output and rejects any result whose
//! token stream differs from the input, then checks that formatting is
//! idempotent. `zen fmt --write` relies on this before replacing a file.
use crate::lexer::{Lexer, Token, TokenKind};
use anyhow::{bail, Result};

/// Format `source`, preserving every token and comment.
///
/// Fails when the input has lexical errors, when the formatted output would
/// lex differently (which would mean a semantic change), or when the
/// formatter is not idempotent for this input.
pub fn format(source: &str) -> Result<String> {
    let formatted = format_once(source)?;
    let second = format_once(&formatted)?;
    if second != formatted {
        bail!("internal error: formatter is not idempotent for this input");
    }
    Ok(formatted)
}

fn format_once(source: &str) -> Result<String> {
    let tokens = lex(source)?;
    let formatted = Printer::new(source, &tokens).run()?;
    verify_token_stream(&tokens, &formatted)?;
    Ok(formatted)
}

fn lex(source: &str) -> Result<Vec<Token>> {
    let tokens = Lexer::with_comments(source, 0).collect_all();
    if let Some(token) = tokens
        .iter()
        .find(|token| matches!(token.kind, TokenKind::Error(_)))
    {
        if let TokenKind::Error(message) = &token.kind {
            bail!("cannot format: {message} (byte {})", token.span.start);
        }
    }
    Ok(tokens)
}

/// Re-lex the output and compare it with the input token stream. Line-comment
/// trailing whitespace is normalized because the formatter trims it.
fn verify_token_stream(original: &[Token], formatted: &str) -> Result<()> {
    let formatted = lex(formatted)?;
    let left = normalized_kinds(original);
    let right = normalized_kinds(&formatted);
    if left != right {
        bail!("internal error: formatting would change the token stream; refusing output");
    }
    Ok(())
}

fn normalized_kinds(tokens: &[Token]) -> Vec<TokenKind> {
    tokens
        .iter()
        .map(|token| match &token.kind {
            TokenKind::Comment(text, true) => TokenKind::Comment(text.trim_end().into(), true),
            other => other.clone(),
        })
        .collect()
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum Break {
    None,
    Line,
    Blank,
}

struct Printer<'a> {
    source: &'a str,
    tokens: &'a [Token],
    out: String,
    indent: usize,
    line_has_content: bool,
    break_pending: Break,
    pending_space: bool,
    paren_depth: usize,
    bracket_depth: usize,
    brace_depth: usize,
    last_sig: Option<TokenKind>,
}

impl<'a> Printer<'a> {
    fn new(source: &'a str, tokens: &'a [Token]) -> Self {
        Self {
            source,
            tokens,
            out: String::new(),
            indent: 0,
            line_has_content: false,
            break_pending: Break::None,
            pending_space: false,
            paren_depth: 0,
            bracket_depth: 0,
            brace_depth: 0,
            last_sig: None,
        }
    }

    fn run(&mut self) -> Result<String> {
        let mut index = 0;
        while index < self.tokens.len() {
            let kind = self.tokens[index].kind.clone();
            match &kind {
                TokenKind::Eof => break,
                TokenKind::Error(message) => {
                    bail!(
                        "cannot format: {message} (byte {})",
                        self.tokens[index].span.start
                    )
                }
                TokenKind::Comment(text, is_line) => {
                    self.comment(index, text, *is_line);
                    index += 1;
                }
                TokenKind::LBrace => {
                    self.resolve_break(false);
                    self.write_kind(&TokenKind::LBrace, "{");
                    self.indent += 1;
                    self.brace_depth += 1;
                    self.pending_space = false;
                    self.hard_newline();
                    self.last_sig = Some(TokenKind::LBrace);
                    index += 1;
                }
                TokenKind::RBrace => {
                    self.indent = self.indent.saturating_sub(1);
                    self.brace_depth = self.brace_depth.saturating_sub(1);
                    self.hard_newline();
                    self.write_kind(&TokenKind::RBrace, "}");
                    self.pending_space = false;
                    self.break_pending = if self.indent == 0 {
                        Break::Blank
                    } else {
                        Break::Line
                    };
                    self.last_sig = Some(TokenKind::RBrace);
                    index += 1;
                }
                TokenKind::Semi => {
                    self.resolve_break(true);
                    self.write_kind(&TokenKind::Semi, ";");
                    if self.paren_depth == 0 && self.bracket_depth == 0 {
                        self.hard_newline();
                    } else {
                        self.pending_space = true;
                    }
                    self.last_sig = Some(TokenKind::Semi);
                    index += 1;
                }
                TokenKind::Comma => {
                    self.resolve_break(true);
                    self.write_kind(&TokenKind::Comma, ",");
                    if self.brace_depth > 0 && self.paren_depth == 0 && self.bracket_depth == 0 {
                        self.hard_newline();
                    } else {
                        self.pending_space = true;
                    }
                    self.last_sig = Some(TokenKind::Comma);
                    index += 1;
                }
                TokenKind::LParen
                | TokenKind::RParen
                | TokenKind::LBracket
                | TokenKind::RBracket => {
                    self.resolve_break(is_continuation(&kind));
                    let text = self.text(index).to_string();
                    self.write_kind(&kind, &text);
                    match kind {
                        TokenKind::LParen => {
                            self.paren_depth += 1;
                            self.pending_space = false;
                        }
                        TokenKind::RParen => {
                            self.paren_depth = self.paren_depth.saturating_sub(1);
                            self.pending_space = true;
                        }
                        TokenKind::LBracket => {
                            self.bracket_depth += 1;
                            self.pending_space = false;
                        }
                        _ => {
                            self.bracket_depth = self.bracket_depth.saturating_sub(1);
                            self.pending_space = true;
                        }
                    }
                    self.last_sig = Some(kind);
                    index += 1;
                }
                _ => {
                    self.resolve_break(is_continuation(&kind));
                    let unary = is_unary_prefix(&kind, self.last_sig.as_ref());
                    let text = self.text(index).to_string();
                    self.write_kind(&kind, &text);
                    self.pending_space = trailing_space(&kind, unary);
                    self.last_sig = Some(kind);
                    index += 1;
                }
            }
        }
        if self.line_has_content {
            self.out.push('\n');
        }
        Ok(std::mem::take(&mut self.out))
    }

    fn text(&self, index: usize) -> &str {
        let span = self.tokens[index].span;
        &self.source[span.start as usize..span.end as usize]
    }

    /// True when a block comment was written after a token on the same
    /// original line. Such comments stay inline; everything else moves to its
    /// own indented line.
    fn is_inline_comment(&self, index: usize) -> bool {
        let Some(previous) = index.checked_sub(1).and_then(|i| self.tokens.get(i)) else {
            return false;
        };
        let gap = &self.source[previous.span.end as usize..self.tokens[index].span.start as usize];
        !gap.contains('\n')
    }

    fn comment(&mut self, index: usize, text: &str, is_line: bool) {
        if !is_line && self.is_inline_comment(index) && self.line_has_content {
            let tight = self.out.ends_with('(') || self.out.ends_with('[');
            if !tight && !self.out.ends_with(' ') {
                self.out.push(' ');
            }
            self.out.push_str(text.trim_end());
            self.line_has_content = true;
            self.pending_space = true;
            return;
        }
        self.hard_newline();
        self.break_pending = Break::None;
        self.write_indent();
        self.out.push_str(text.trim_end());
        self.line_has_content = true;
        self.hard_newline();
    }

    fn write_indent(&mut self) {
        for _ in 0..self.indent {
            self.out.push_str("  ");
        }
    }

    fn resolve_break(&mut self, continuation: bool) {
        let pending = self.break_pending;
        match pending {
            Break::None => {}
            Break::Line | Break::Blank => {
                self.break_pending = Break::None;
                if continuation {
                    self.pending_space = true;
                } else {
                    self.hard_newline();
                    if pending == Break::Blank {
                        self.blank_line();
                    }
                }
            }
        }
    }

    fn blank_line(&mut self) {
        if !self.out.is_empty() && !self.out.ends_with("\n\n") {
            self.out.push('\n');
        }
    }

    fn hard_newline(&mut self) {
        if self.line_has_content {
            self.out.push('\n');
            self.line_has_content = false;
        }
        self.pending_space = false;
    }

    fn space_before(&self, kind: &TokenKind) -> bool {
        if !self.line_has_content {
            return false;
        }
        match kind {
            TokenKind::Comma
            | TokenKind::Semi
            | TokenKind::RParen
            | TokenKind::RBracket
            | TokenKind::RBrace
            | TokenKind::Dot
            | TokenKind::DoubleColon
            | TokenKind::Question
            | TokenKind::At
            | TokenKind::Colon => false,
            TokenKind::LParen | TokenKind::LBracket => {
                !self.last_sig.as_ref().is_some_and(is_value_like) && self.pending_space
            }
            TokenKind::DotDot | TokenKind::DotDotDot => {
                matches!(self.last_sig, Some(TokenKind::Dot))
                    || (self.pending_space && !self.last_sig.as_ref().is_some_and(is_value_like))
            }
            _ => self.pending_space,
        }
    }

    fn write_kind(&mut self, kind: &TokenKind, text: &str) {
        if !self.line_has_content {
            self.write_indent();
        } else if self.space_before(kind) {
            self.out.push(' ');
        }
        self.out.push_str(text);
        self.line_has_content = true;
    }
}

fn is_continuation(kind: &TokenKind) -> bool {
    matches!(
        kind,
        TokenKind::Else
            | TokenKind::Semi
            | TokenKind::Comma
            | TokenKind::RParen
            | TokenKind::RBracket
            | TokenKind::Dot
            | TokenKind::DoubleColon
            | TokenKind::Question
    )
}

/// Tokens that can end an expression. Used to distinguish binary operators
/// from unary prefixes and indexing brackets from array type/literal brackets.
fn is_value_like(kind: &TokenKind) -> bool {
    matches!(
        kind,
        TokenKind::Ident(_)
            | TokenKind::Integer { .. }
            | TokenKind::Float { .. }
            | TokenKind::Bool(_)
            | TokenKind::Char(_)
            | TokenKind::String(_)
            | TokenKind::Null
            | TokenKind::True
            | TokenKind::False
            | TokenKind::RParen
            | TokenKind::RBracket
            | TokenKind::RBrace
            | TokenKind::Question
    )
}

fn is_unary_prefix(kind: &TokenKind, last: Option<&TokenKind>) -> bool {
    match kind {
        TokenKind::Not | TokenKind::Tilde => true,
        TokenKind::Minus | TokenKind::Plus | TokenKind::Star | TokenKind::Amp => {
            !last.is_some_and(is_value_like)
        }
        _ => false,
    }
}

/// Whether a space is required after a token written by the generic branch.
fn trailing_space(kind: &TokenKind, unary: bool) -> bool {
    match kind {
        TokenKind::Dot
        | TokenKind::DoubleColon
        | TokenKind::DotDot
        | TokenKind::DotDotDot
        | TokenKind::Question
        | TokenKind::At => false,
        _ => !unary,
    }
}
