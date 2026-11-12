//! Lint diagnostics and machine-readable rendering for `zen lint` (TASK-909).
//!
//! The analysis itself lives in [`crate::mvp::lint`] because it needs the
//! private parser/AST. This module owns the diagnostic schema, the human
//! format, the JSON encoding (no external serialization dependency) and the
//! exit-code policy shared by the CLI.
use crate::lexer::Span;
use std::fmt;

pub const UNUSED_VARIABLE: &str = "unused-variable";
pub const UNUSED_PARAMETER: &str = "unused-parameter";
pub const UNUSED_FUNCTION: &str = "unused-function";
pub const UNREACHABLE_CODE: &str = "unreachable-code";
/// Code used when the compiler frontend/checker rejects the file.
pub const COMPILE_ERROR: &str = "compile-error";

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Severity {
    Warning,
    Error,
}

impl Severity {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Warning => "warning",
            Self::Error => "error",
        }
    }
}

impl fmt::Display for Severity {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

/// One lint or compiler diagnostic.
///
/// `line` and `column` are 1-based; `span_start`/`span_end` are byte offsets
/// into the original source, which makes them stable for editors and CI.
/// The file name is not stored here because the analysis works on a source
/// string; renderers receive it explicitly.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LintDiagnostic {
    pub severity: Severity,
    pub code: &'static str,
    pub message: String,
    pub line: u32,
    pub column: u32,
    pub span_start: u32,
    pub span_end: u32,
}

impl LintDiagnostic {
    pub fn new(
        severity: Severity,
        code: &'static str,
        message: impl Into<String>,
        span: Span,
        source: &str,
    ) -> Self {
        let (line, column) = line_column(source, span.start);
        Self {
            severity,
            code,
            message: message.into(),
            line,
            column,
            span_start: span.start,
            span_end: span.end,
        }
    }

    pub fn warning(
        code: &'static str,
        message: impl Into<String>,
        span: Span,
        source: &str,
    ) -> Self {
        Self::new(Severity::Warning, code, message, span, source)
    }

    pub fn error(code: &'static str, message: impl Into<String>, span: Span, source: &str) -> Self {
        Self::new(Severity::Error, code, message, span, source)
    }
}

/// Compute the 1-based line and 1-based Unicode-scalar column of a byte offset.
///
/// Offsets that are not on a character boundary (or past the end) fall back to
/// the whole source, which keeps diagnostics printable even if a future lexer
/// reports an unusual span.
pub fn line_column(source: &str, offset: u32) -> (u32, u32) {
    let offset = offset as usize;
    let prefix = source.get(..offset).unwrap_or(source);
    let line = prefix.bytes().filter(|byte| *byte == b'\n').count() as u32 + 1;
    let column = prefix
        .rsplit('\n')
        .next()
        .map(|line| line.chars().count() as u32 + 1)
        .unwrap_or(1);
    (line, column)
}

pub fn has_errors(diagnostics: &[LintDiagnostic]) -> bool {
    diagnostics
        .iter()
        .any(|diagnostic| diagnostic.severity == Severity::Error)
}

pub fn has_warnings(diagnostics: &[LintDiagnostic]) -> bool {
    diagnostics
        .iter()
        .any(|diagnostic| diagnostic.severity == Severity::Warning)
}

/// Exit code contract: errors win, then `--deny-warnings`, otherwise success.
pub fn exit_code(diagnostics: &[LintDiagnostic], deny_warnings: bool) -> u8 {
    if has_errors(diagnostics) {
        1
    } else if deny_warnings && has_warnings(diagnostics) {
        2
    } else {
        0
    }
}

/// Human-readable format: `file:line:column: severity[code]: message`.
pub fn render_text(file: &str, diagnostics: &[LintDiagnostic]) -> String {
    let mut output = String::new();
    for diagnostic in diagnostics {
        output.push_str(&format!(
            "{}:{}:{}: {}[{}]: {}\n",
            file,
            diagnostic.line,
            diagnostic.column,
            diagnostic.severity.as_str(),
            diagnostic.code,
            diagnostic.message
        ));
    }
    output
}

/// Compact JSON array with a fixed, documented field order.
///
/// Serialization is manual to keep the bootstrap compiler free of a JSON
/// dependency; escaping covers every character JSON requires.
pub fn render_json(file: &str, diagnostics: &[LintDiagnostic]) -> String {
    let mut output = String::from("[");
    for (index, diagnostic) in diagnostics.iter().enumerate() {
        if index > 0 {
            output.push(',');
        }
        output.push_str(&format!(
            "{{\"severity\":\"{}\",\"code\":\"{}\",\"message\":\"{}\",\"file\":\"{}\",\"line\":{},\"column\":{},\"span_start\":{},\"span_end\":{}}}",
            diagnostic.severity.as_str(),
            escape_json(diagnostic.code),
            escape_json(&diagnostic.message),
            escape_json(file),
            diagnostic.line,
            diagnostic.column,
            diagnostic.span_start,
            diagnostic.span_end
        ));
    }
    output.push_str("]\n");
    output
}

/// Escape a string for inclusion inside a JSON string literal.
pub fn escape_json(input: &str) -> String {
    let mut output = String::with_capacity(input.len());
    for character in input.chars() {
        match character {
            '"' => output.push_str("\\\""),
            '\\' => output.push_str("\\\\"),
            '\u{08}' => output.push_str("\\b"),
            '\u{0c}' => output.push_str("\\f"),
            '\n' => output.push_str("\\n"),
            '\r' => output.push_str("\\r"),
            '\t' => output.push_str("\\t"),
            character if (character as u32) < 0x20 => {
                output.push_str(&format!("\\u{:04x}", character as u32))
            }
            character => output.push(character),
        }
    }
    output
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn json_escapes_quotes_backslashes_and_controls() {
        assert_eq!(
            escape_json("a\"b\\c\n\t\r\u{08}\u{0c}\u{01}"),
            "a\\\"b\\\\c\\n\\t\\r\\b\\f\\u0001"
        );
        assert_eq!(escape_json("áé"), "áé");
    }

    #[test]
    fn line_and_column_are_one_based_and_utf8_aware() {
        let source = "uno\n  año\n";
        assert_eq!(line_column(source, 0), (1, 1));
        assert_eq!(line_column(source, 4), (2, 1));
        // "  " is two characters; the ñ counts as one column.
        assert_eq!(line_column(source, 9), (2, 5));
        assert_eq!(line_column(source, 10_000), (3, 1));
    }
}
