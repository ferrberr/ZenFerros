//! Textual source inclusion for `use "path.zen";`.
//!
//! Zen has no module system yet: a `use` directive is a compile-time textual
//! include. The directive must appear at the top of a file, before any item,
//! and is replaced in place by the fully expanded contents of the referenced
//! file, so all functions and types share one global namespace.
//!
//! Resolution rules
//! - A directive is exactly `use "relative/path.zen";` (the lexer already
//!   reserves `use`, comments before it are skipped).
//! - Paths are resolved against the directory of the file that contains the
//!   directive, never against the process working directory. Absolute paths
//!   are accepted verbatim for tooling, but they make a tree non-relocatable,
//!   so relative paths are the intended style.
//! - Includes nest to a maximum depth of [`MAX_INCLUDE_DEPTH`] edges from the
//!   root file (root depth is 0).
//! - A cycle is an error that reports the full chain.
//! - A missing or unreadable file is an error that names the directive, the
//!   including file and the resolved path.
//! - The same canonical file is expanded at most once per build: the first
//!   inclusion wins and later directives that resolve to it expand to
//!   nothing. This keeps shared libraries from redefining functions and makes
//!   include order stable (depth-first, left-to-right).
//!
//! Diagnostics
//! The resolver keeps a map from every byte of the expanded source back to the
//! file and offset it came from, so compiler errors in an included file are
//! reported against that file with its own path, line and column.
//!
//! Tooling scope
//! `zen build`, `zen run` and `zen check` use this resolver. `zen fmt`,
//! `zen lint`, `zen lex` and `zen lsp` deliberately keep working on the exact
//! bytes of a single source file: formatting a concatenation and writing it
//! back would destroy the split, and moving lint ranges onto a synthetic file
//! would be misleading. Concretely, `zen fmt` preserves `use` directives and
//! formats the rest of the file as written; `zen lint`, `zen lex` and the LSP
//! do not expand includes (lint reports the directive as a compile error and
//! the LSP publishes that same single-file diagnostic).

use crate::lexer::{Lexer, Span, Token, TokenKind};
use std::{
    collections::BTreeSet,
    fmt,
    path::{Path, PathBuf},
};

/// Maximum number of nested include edges below the root file.
pub const MAX_INCLUDE_DEPTH: usize = 16;

/// A source file participating in one build, in inclusion order.
#[derive(Debug, Clone)]
pub struct SourceFile {
    /// Path used in diagnostics (relative to the working directory when possible).
    pub path: PathBuf,
    pub text: String,
}

#[derive(Debug, Clone)]
struct Segment {
    output_start: usize,
    output_end: usize,
    file: usize,
    source_offset: usize,
}

/// Fully expanded source plus the file map used to report diagnostics.
#[derive(Debug, Clone)]
pub struct Resolved {
    /// Concatenated source handed to the parser and type checker.
    pub text: String,
    /// Every included file, with the root at index 0.
    pub files: Vec<SourceFile>,
    segments: Vec<Segment>,
}

impl Resolved {
    /// Map an offset range in [`Resolved::text`] back to
    /// `(file index, local start, local end)`.
    pub fn locate(&self, start: usize, end: usize) -> (usize, usize, usize) {
        let segment = self
            .segments
            .iter()
            .find(|segment| start >= segment.output_start && start < segment.output_end)
            .or_else(|| {
                self.segments
                    .last()
                    .filter(|segment| start >= segment.output_start)
            })
            .or_else(|| self.segments.first());
        let Some(segment) = segment else {
            return (0, 0, 0);
        };
        let local_start =
            segment.source_offset + start.max(segment.output_start) - segment.output_start;
        let local_end = if end >= segment.output_start && end <= segment.output_end {
            segment.source_offset + end - segment.output_start
        } else {
            local_start
        };
        let length = self
            .files
            .get(segment.file)
            .map(|file| file.text.len())
            .unwrap_or(0);
        let local_start = local_start.min(length);
        let local_end = local_end.min(length).max(local_start);
        (segment.file, local_start, local_end)
    }

    /// Locate a compiler span in the expanded source.
    pub fn locate_span(&self, span: Span) -> (usize, usize, usize) {
        self.locate(span.start as usize, span.end as usize)
    }
}

/// A resolution or directive error; rendered by the CLI as `zen: <message>`.
#[derive(Debug, Clone)]
pub struct IncludeError {
    pub message: String,
}

impl IncludeError {
    fn new(message: impl Into<String>) -> Self {
        Self {
            message: message.into(),
        }
    }
}

impl fmt::Display for IncludeError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        self.message.fmt(f)
    }
}

impl std::error::Error for IncludeError {}

struct Directive {
    start: usize,
    end: usize,
    path: String,
    line: usize,
}

/// Read `path` and expand every `use` directive it reaches.
pub fn resolve(path: &Path) -> Result<Resolved, IncludeError> {
    if path.extension().and_then(|extension| extension.to_str()) != Some("zen") {
        return Err(IncludeError::new(format!(
            "expected a .zen source file: {}",
            path.display()
        )));
    }
    let mut resolved = Resolved {
        text: String::new(),
        files: Vec::new(),
        segments: Vec::new(),
    };
    let mut stack = Vec::new();
    let mut included = BTreeSet::new();
    let literal = path.display().to_string();
    expand(
        path,
        &literal,
        None,
        0,
        &mut stack,
        &mut included,
        &mut resolved,
    )?;
    Ok(resolved)
}

/// Expand one file. `origin` is the including file and directive line, or
/// `None` for the root source.
fn expand(
    requested: &Path,
    literal: &str,
    origin: Option<(&Path, usize)>,
    depth: usize,
    stack: &mut Vec<PathBuf>,
    included: &mut BTreeSet<PathBuf>,
    out: &mut Resolved,
) -> Result<(), IncludeError> {
    let canonical = std::fs::canonicalize(requested).map_err(|error| match origin {
        Some((including, line)) => IncludeError::new(format!(
            "{}:{}: cannot include \"{}\": {}: {}",
            display_path(including).display(),
            line,
            literal,
            display_path(requested).display(),
            error
        )),
        None => IncludeError::new(format!(
            "cannot read {}: {}",
            display_path(requested).display(),
            error
        )),
    })?;
    if depth > MAX_INCLUDE_DEPTH {
        let mut chain: Vec<String> = stack
            .iter()
            .map(|entry| display_path(entry).display().to_string())
            .collect();
        chain.push(display_path(&canonical).display().to_string());
        return Err(IncludeError::new(format!(
            "include depth limit exceeded (maximum {MAX_INCLUDE_DEPTH}): {}",
            chain.join(" -> ")
        )));
    }
    // Cycles win over de-duplication: a file that is still on the stack is an
    // error, a file already left on the stack was included earlier and is
    // silently skipped.
    if let Some(position) = stack.iter().position(|entry| entry == &canonical) {
        let mut chain: Vec<String> = stack[position..]
            .iter()
            .map(|entry| display_path(entry).display().to_string())
            .collect();
        chain.push(display_path(&canonical).display().to_string());
        let location = origin
            .map(|(including, line)| format!("{}:{}: ", display_path(including).display(), line))
            .unwrap_or_default();
        return Err(IncludeError::new(format!(
            "{location}include cycle detected: {}",
            chain.join(" -> ")
        )));
    }
    if !included.insert(canonical.clone()) {
        // Already expanded once (first inclusion wins).
        return Ok(());
    }
    let source = std::fs::read_to_string(&canonical).map_err(|error| match origin {
        Some((including, line)) => IncludeError::new(format!(
            "{}:{}: cannot include \"{}\": {}: {}",
            display_path(including).display(),
            line,
            literal,
            display_path(&canonical).display(),
            error
        )),
        None => IncludeError::new(format!(
            "cannot read {}: {}",
            display_path(&canonical).display(),
            error
        )),
    })?;
    let file = out.files.len();
    out.files.push(SourceFile {
        path: display_path(&canonical),
        text: source.clone(),
    });
    stack.push(canonical.clone());
    let result = expand_contents(&source, &canonical, file, depth, stack, included, out);
    stack.pop();
    result
}

fn expand_contents(
    source: &str,
    current: &Path,
    file: usize,
    depth: usize,
    stack: &mut Vec<PathBuf>,
    included: &mut BTreeSet<PathBuf>,
    out: &mut Resolved,
) -> Result<(), IncludeError> {
    let directives = directives(source, current)?;
    let directory = current.parent().unwrap_or_else(|| Path::new("."));
    let mut cursor = 0;
    for directive in directives {
        push_origin(out, file, cursor, &source[cursor..directive.start]);
        let target = directory.join(&directive.path);
        expand(
            &target,
            &directive.path,
            Some((current, directive.line)),
            depth + 1,
            stack,
            included,
            out,
        )?;
        cursor = directive.end;
    }
    push_origin(out, file, cursor, &source[cursor..]);
    // Keep a token boundary between the end of this file and whatever the
    // including file appends next (or the next included file).
    if !out.text.is_empty() && !out.text.ends_with('\n') {
        push_origin(out, file, source.len(), "\n");
    }
    Ok(())
}

/// Parse the leading `use "path.zen";` directives of one file.
fn directives(source: &str, origin: &Path) -> Result<Vec<Directive>, IncludeError> {
    let tokens = Lexer::new(source, 0).collect_all();
    let mut directives = Vec::new();
    let mut index = 0;
    while index < tokens.len() {
        let token = &tokens[index];
        match &token.kind {
            TokenKind::Use => {
                let path = match tokens.get(index + 1).map(|token| &token.kind) {
                    Some(TokenKind::String(path)) => path.clone(),
                    _ => return Err(syntax_error(source, origin, token.span.start as usize)),
                };
                let end = match tokens.get(index + 2) {
                    Some(Token {
                        kind: TokenKind::Semi,
                        span,
                    }) => span.end as usize,
                    _ => return Err(syntax_error(source, origin, token.span.start as usize)),
                };
                if path.is_empty() {
                    return Err(IncludeError::new(format!(
                        "{}:{}: include path cannot be empty",
                        display_path(origin).display(),
                        line_of(source, token.span.start as usize)
                    )));
                }
                directives.push(Directive {
                    start: token.span.start as usize,
                    end,
                    path,
                    line: line_of(source, token.span.start as usize),
                });
                index += 3;
            }
            TokenKind::Eof | TokenKind::Error(_) => break,
            _ => break,
        }
    }
    if let Some(token) = tokens[index..]
        .iter()
        .find(|token| matches!(&token.kind, TokenKind::Use))
    {
        return Err(IncludeError::new(format!(
            "{}:{}: include directives must appear before any item",
            display_path(origin).display(),
            line_of(source, token.span.start as usize)
        )));
    }
    Ok(directives)
}

fn syntax_error(source: &str, origin: &Path, offset: usize) -> IncludeError {
    IncludeError::new(format!(
        "{}:{}: expected `use \"path.zen\";` at the top of the file",
        display_path(origin).display(),
        line_of(source, offset)
    ))
}

fn line_of(source: &str, offset: usize) -> usize {
    source[..offset.min(source.len())]
        .bytes()
        .filter(|byte| *byte == b'\n')
        .count()
        + 1
}

fn push_origin(out: &mut Resolved, file: usize, source_offset: usize, text: &str) {
    if text.is_empty() {
        return;
    }
    let output_start = out.text.len();
    out.text.push_str(text);
    out.segments.push(Segment {
        output_start,
        output_end: out.text.len(),
        file,
        source_offset,
    });
}

/// Prefer paths relative to the working directory so diagnostics stay short.
fn display_path(path: &Path) -> PathBuf {
    std::env::current_dir()
        .ok()
        .and_then(|directory| path.strip_prefix(&directory).ok().map(Path::to_path_buf))
        .filter(|relative| !relative.as_os_str().is_empty())
        .unwrap_or_else(|| path.to_path_buf())
}
