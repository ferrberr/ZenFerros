//! UTF-8 aware scanner. Every malformed literal produces an error token.
use crate::lexer::keywords::keyword_kind;
use crate::lexer::token::{Base, FloatSuffix, IntSuffix, Span, Token, TokenKind};

pub struct Scanner<'a> {
    source: &'a str,
    file_id: usize,
    pos: usize,
    /// When enabled, comments are returned as `TokenKind::Comment` instead of
    /// being skipped. The default (`Scanner::new`) keeps the parser contract
    /// unchanged: comments never reach the token stream.
    comments: bool,
}

impl<'a> Scanner<'a> {
    pub fn new(source: &'a str, file_id: usize) -> Self {
        Self {
            source,
            file_id,
            pos: 0,
            comments: false,
        }
    }

    /// Build a scanner that emits `//` and nested `/* ... */` comments as
    /// `TokenKind::Comment(raw_text, is_line)` tokens.
    pub fn with_comments(source: &'a str, file_id: usize) -> Self {
        Self {
            source,
            file_id,
            pos: 0,
            comments: true,
        }
    }

    fn current(&self) -> Option<char> {
        self.source[self.pos..].chars().next()
    }
    fn advance(&mut self) -> Option<char> {
        let c = self.current()?;
        self.pos += c.len_utf8();
        Some(c)
    }
    fn starts(&self, text: &str) -> bool {
        self.source[self.pos..].starts_with(text)
    }
    fn token(&self, start: usize, kind: TokenKind) -> Token {
        Token::new(kind, Span::new(self.file_id, start as u32, self.pos as u32))
    }
    fn error(&self, start: usize, message: impl Into<String>) -> Token {
        self.token(start, TokenKind::Error(message.into()))
    }

    fn scan_number(&mut self) -> Token {
        let start = self.pos;
        let base = if self.starts("0x") || self.starts("0X") {
            self.pos += 2;
            Base::Hex
        } else if self.starts("0b") || self.starts("0B") {
            self.pos += 2;
            Base::Binary
        } else if self.starts("0o") || self.starts("0O") {
            self.pos += 2;
            Base::Octal
        } else {
            Base::Decimal
        };
        let invalid_prefix = !matches!(self.current(), Some(c) if c.is_digit(base as u32));
        let mut digits = String::new();
        while let Some(c) = self.current() {
            if c.is_digit(base as u32) {
                digits.push(c);
                self.advance();
            } else if c == '_' {
                self.advance();
            } else {
                break;
            }
        }
        let mut float = false;
        if base == Base::Decimal && self.starts(".") && !self.starts("..") {
            float = true;
            digits.push('.');
            self.advance();
            while let Some(c) = self.current() {
                if c.is_ascii_digit() {
                    digits.push(c);
                    self.advance();
                } else if c == '_' {
                    self.advance();
                } else {
                    break;
                }
            }
        }
        if base == Base::Decimal && matches!(self.current(), Some('e' | 'E')) {
            float = true;
            digits.push('e');
            self.advance();
            if matches!(self.current(), Some('+' | '-')) {
                digits.push(self.advance().unwrap());
            }
            if !matches!(self.current(), Some(c) if c.is_ascii_digit()) {
                return self.error(start, "Exponent requires a digit");
            }
            let before = digits.len();
            while let Some(c) = self.current() {
                if c.is_ascii_digit() {
                    digits.push(c);
                    self.advance();
                } else if c == '_' {
                    self.advance();
                } else {
                    break;
                }
            }
            if before == digits.len() {
                return self.error(start, "Missing exponent digits");
            }
        }
        let suffix_start = self.pos;
        while matches!(self.current(), Some(c) if c.is_ascii_alphanumeric() || c == '_') {
            self.advance();
        }
        let suffix = &self.source[suffix_start..self.pos];
        if invalid_prefix {
            return self.error(start, "Base prefix requires a digit");
        }
        if float {
            let suffix = match suffix {
                "" => None,
                "f32" => Some(FloatSuffix::F32),
                "f64" => Some(FloatSuffix::F64),
                _ => return self.error(start, format!("Invalid float suffix: {suffix}")),
            };
            match digits.parse::<f64>() {
                Ok(value) if value.is_finite() => {
                    self.token(start, TokenKind::Float { value, suffix })
                }
                _ => self.error(start, "Invalid or overflowing float literal"),
            }
        } else {
            let suffix = match suffix {
                "" => None,
                "i8" => Some(IntSuffix::I8),
                "i16" => Some(IntSuffix::I16),
                "i32" => Some(IntSuffix::I32),
                "i64" => Some(IntSuffix::I64),
                "i128" => Some(IntSuffix::I128),
                "isize" => Some(IntSuffix::Isize),
                "u8" => Some(IntSuffix::U8),
                "u16" => Some(IntSuffix::U16),
                "u32" => Some(IntSuffix::U32),
                "u64" => Some(IntSuffix::U64),
                "u128" => Some(IntSuffix::U128),
                "usize" => Some(IntSuffix::Usize),
                _ => {
                    return self.error(
                        start,
                        format!("Invalid integer suffix or base digit: {suffix}"),
                    )
                }
            };
            match u128::from_str_radix(&digits, base as u32) {
                Ok(value) => self.token(
                    start,
                    TokenKind::Integer {
                        value,
                        base,
                        suffix,
                    },
                ),
                Err(_) => self.error(start, "Invalid or overflowing integer literal"),
            }
        }
    }

    fn escape(&mut self) -> Result<char, &'static str> {
        self.advance(); // backslash
        match self.advance() {
            Some('n') => Ok('\n'),
            Some('t') => Ok('\t'),
            Some('r') => Ok('\r'),
            Some('\\') => Ok('\\'),
            Some('"') => Ok('"'),
            Some('\'') => Ok('\''),
            Some('0') => Ok('\0'),
            Some('x') => {
                let mut value = 0;
                for _ in 0..2 {
                    let digit = self
                        .current()
                        .and_then(|c| c.to_digit(16))
                        .ok_or("Hex escape requires exactly two hexadecimal digits")?;
                    value = value * 16 + digit;
                    self.advance();
                }
                Ok(char::from_u32(value).unwrap())
            }
            Some(_) => Err("Invalid escape sequence"),
            None => Err("Unterminated escape sequence"),
        }
    }

    fn scan_string(&mut self) -> Token {
        let start = self.pos;
        self.advance();
        let mut value = String::new();
        loop {
            match self.current() {
                Some('"') => {
                    self.advance();
                    return self.token(start, TokenKind::String(value));
                }
                Some('\n' | '\r') | None => {
                    return self.error(start, "Unterminated string literal")
                }
                Some('\\') => match self.escape() {
                    Ok(c) => value.push(c),
                    Err(message) => return self.error(start, message),
                },
                Some(c) => {
                    value.push(c);
                    self.advance();
                }
            }
        }
    }

    fn scan_char(&mut self) -> Token {
        let start = self.pos;
        self.advance();
        let value = match self.current() {
            Some('\\') => match self.escape() {
                Ok(c) => c,
                Err(message) => return self.error(start, message),
            },
            Some('\'' | '\n' | '\r') | None => {
                return self.error(start, "Empty or unterminated char literal")
            }
            Some(c) => {
                self.advance();
                c
            }
        };
        if self.current() != Some('\'') {
            return self.error(start, "Unterminated char literal");
        }
        self.advance();
        self.token(start, TokenKind::Char(value))
    }

    fn operator(&mut self) -> Token {
        let start = self.pos;
        let operators = [
            ("...", TokenKind::DotDotDot),
            ("<<=", TokenKind::ShlEq),
            (">>=", TokenKind::ShrEq),
            ("==", TokenKind::EqEq),
            ("!=", TokenKind::NotEq),
            ("<=", TokenKind::LtEq),
            (">=", TokenKind::GtEq),
            ("&&", TokenKind::AndAnd),
            ("||", TokenKind::OrOr),
            ("+=", TokenKind::PlusEq),
            ("-=", TokenKind::MinusEq),
            ("**", TokenKind::StarStar),
            ("*=", TokenKind::StarEq),
            ("/=", TokenKind::SlashEq),
            ("%=", TokenKind::PercentEq),
            ("&=", TokenKind::AmpEq),
            ("|=", TokenKind::PipeEq),
            ("^=", TokenKind::CaretEq),
            ("<<", TokenKind::Shl),
            (">>", TokenKind::Shr),
            ("..", TokenKind::DotDot),
            ("->", TokenKind::Arrow),
            ("=>", TokenKind::FatArrow),
            ("::", TokenKind::DoubleColon),
        ];
        for (text, kind) in operators {
            if self.starts(text) {
                self.pos += text.len();
                return self.token(start, kind);
            }
        }
        let kind = match self.advance() {
            Some('+') => TokenKind::Plus,
            Some('-') => TokenKind::Minus,
            Some('*') => TokenKind::Star,
            Some('/') => TokenKind::Slash,
            Some('%') => TokenKind::Percent,
            Some('<') => TokenKind::Lt,
            Some('>') => TokenKind::Gt,
            Some('!') => TokenKind::Not,
            Some('&') => TokenKind::Amp,
            Some('|') => TokenKind::Pipe,
            Some('^') => TokenKind::Caret,
            Some('~') => TokenKind::Tilde,
            Some('=') => TokenKind::Assign,
            Some('.') => TokenKind::Dot,
            Some(':') => TokenKind::Colon,
            Some(';') => TokenKind::Semi,
            Some(',') => TokenKind::Comma,
            Some('(') => TokenKind::LParen,
            Some(')') => TokenKind::RParen,
            Some('[') => TokenKind::LBracket,
            Some(']') => TokenKind::RBracket,
            Some('{') => TokenKind::LBrace,
            Some('}') => TokenKind::RBrace,
            Some('?') => TokenKind::Question,
            Some('@') => TokenKind::At,
            Some(c) => return self.error(start, format!("Unexpected character: '{c}'")),
            None => TokenKind::Eof,
        };
        self.token(start, kind)
    }

    pub fn next_token(&mut self) -> Token {
        // Iterate instead of recursing: a long sequence of comments uses constant stack space.
        loop {
            while matches!(self.current(), Some(c) if c.is_whitespace()) {
                self.advance();
            }
            if self.starts("//") {
                let start = self.pos;
                while matches!(self.current(), Some(c) if c != '\n') {
                    self.advance();
                }
                if self.comments {
                    let text = self.source[start..self.pos].to_string();
                    return self.token(start, TokenKind::Comment(text, true));
                }
            } else if self.starts("/*") {
                let start = self.pos;
                self.pos += 2;
                let mut depth: usize = 1;
                while depth > 0 {
                    if self.starts("/*") {
                        depth += 1;
                        self.pos += 2;
                    } else if self.starts("*/") {
                        depth -= 1;
                        self.pos += 2;
                    } else if self.advance().is_none() {
                        return self.error(start, "Unterminated block comment");
                    }
                }
                if self.comments {
                    let text = self.source[start..self.pos].to_string();
                    return self.token(start, TokenKind::Comment(text, false));
                }
            } else {
                break;
            }
        }
        let start = self.pos;
        match self.current() {
            Some(c) if c.is_ascii_alphabetic() || c == '_' => {
                self.advance();
                while matches!(self.current(), Some(c) if c.is_ascii_alphanumeric() || c == '_') {
                    self.advance();
                }
                let text = &self.source[start..self.pos];
                self.token(
                    start,
                    keyword_kind(text).unwrap_or_else(|| TokenKind::Ident(text.into())),
                )
            }
            Some(c) if c.is_ascii_digit() => self.scan_number(),
            Some('"') => self.scan_string(),
            Some('\'') => self.scan_char(),
            _ => self.operator(),
        }
    }
}

pub struct Lexer<'a> {
    scanner: Scanner<'a>,
    peeked: Option<Token>,
}
impl<'a> Lexer<'a> {
    /// Default lexer: comments are skipped and never reach the parser.
    pub fn new(source: &'a str, file_id: usize) -> Self {
        Self {
            scanner: Scanner::new(source, file_id),
            peeked: None,
        }
    }
    /// Comment-preserving lexer used by tools such as `zen fmt`. Comments are
    /// emitted as `TokenKind::Comment(raw_text, is_line)`; all other tokens are
    /// identical to `Lexer::new`.
    pub fn with_comments(source: &'a str, file_id: usize) -> Self {
        Self {
            scanner: Scanner::with_comments(source, file_id),
            peeked: None,
        }
    }
    pub fn next_token(&mut self) -> Token {
        self.peeked
            .take()
            .unwrap_or_else(|| self.scanner.next_token())
    }
    pub fn peek_token(&mut self) -> &Token {
        if self.peeked.is_none() {
            self.peeked = Some(self.scanner.next_token());
        }
        self.peeked.as_ref().unwrap()
    }
    pub fn collect_all(&mut self) -> Vec<Token> {
        let mut tokens = Vec::new();
        loop {
            let token = self.next_token();
            let done = matches!(token.kind, TokenKind::Eof);
            tokens.push(token);
            if done {
                return tokens;
            }
        }
    }
}
