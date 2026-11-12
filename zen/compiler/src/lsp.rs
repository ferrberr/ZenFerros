//! Minimal Language Server Protocol server for Zen (TASK-910).
//!
//! Scope and design constraints:
//! - transport: JSON-RPC 2.0 over stdin/stdout with `Content-Length` framing;
//! - no shell, no threads, no new dependencies: the JSON reader/writer is
//!   hand-written on top of `std` and the existing linter;
//! - synchronization is *full* (`textDocumentSync: 1`): the client owns the
//!   buffer and sends the whole document on open/change/save;
//! - diagnostics are *push* notifications produced by `mvp::lint`, with the
//!   compiler error converted to a `compile-error` diagnostic exactly as the
//!   `zen lint` CLI does;
//! - LSP positions are zero-based lines and UTF-16 code units, as required by
//!   the protocol (the linter stores one-based lines and byte spans).

use crate::lint::{escape_json, LintDiagnostic, Severity, COMPILE_ERROR};
use crate::mvp;
use std::collections::HashMap;
use std::io::{self, BufRead, BufReader, Write};

pub const SERVER_NAME: &str = "zen-lsp";
pub const SERVER_VERSION: &str = env!("CARGO_PKG_VERSION");
const JSONRPC_VERSION: &str = "2.0";

// JSON-RPC 2.0 error codes used by this server.
const PARSE_ERROR: i64 = -32700;
const INVALID_REQUEST: i64 = -32600;
const METHOD_NOT_FOUND: i64 = -32601;

/// Upper bound for a single `Content-Length` body (guards against a corrupt
/// header trying to allocate an enormous buffer). Real editor documents are
/// far smaller.
const MAX_BODY_BYTES: usize = 64 * 1024 * 1024;

/// Run the LSP server until `exit` (or stdin EOF).
///
/// Returns the process exit code mandated by the protocol: `0` when a
/// `shutdown` request was received before `exit`, `1` otherwise. EOF without
/// `exit` is treated as a clean client disconnect and returns `0`.
pub fn run() -> io::Result<u8> {
    let stdin = io::stdin();
    let stdout = io::stdout();
    let mut server = Server {
        input: BufReader::new(stdin.lock()),
        output: stdout.lock(),
        documents: HashMap::new(),
        shutdown_requested: false,
    };
    server.serve()
}

struct Document {
    text: String,
    version: i64,
}

struct Server<R: BufRead, W: Write> {
    input: R,
    output: W,
    documents: HashMap<String, Document>,
    shutdown_requested: bool,
}

enum Frame {
    /// A complete JSON-RPC body.
    Body(Vec<u8>),
    /// A header block without a usable `Content-Length`.
    Malformed,
    /// stdin closed (before or between messages).
    Eof,
}

impl<R: BufRead, W: Write> Server<R, W> {
    fn serve(&mut self) -> io::Result<u8> {
        loop {
            match read_frame(&mut self.input)? {
                Frame::Eof => return Ok(0),
                Frame::Malformed => {
                    self.send_error(Json::Null, PARSE_ERROR, "Parse error")?;
                }
                Frame::Body(body) => {
                    if let Some(code) = self.handle(&body)? {
                        return Ok(code);
                    }
                }
            }
        }
    }

    /// Dispatch one JSON-RPC message. `Some(code)` means "terminate now".
    fn handle(&mut self, body: &[u8]) -> io::Result<Option<u8>> {
        let text = match std::str::from_utf8(body) {
            Ok(text) => text,
            Err(_) => {
                self.send_error(Json::Null, PARSE_ERROR, "Parse error")?;
                return Ok(None);
            }
        };
        let message = match Json::parse(text) {
            Ok(message) => message,
            Err(JsonError) => {
                self.send_error(Json::Null, PARSE_ERROR, "Parse error")?;
                return Ok(None);
            }
        };
        let Json::Object(fields) = message else {
            self.send_error(Json::Null, INVALID_REQUEST, "Invalid Request")?;
            return Ok(None);
        };
        let id = fields
            .iter()
            .find(|(name, _)| name == "id")
            .map(|(_, value)| value.clone());
        let method = fields
            .iter()
            .find(|(name, _)| name == "method")
            .and_then(|(_, value)| value.as_str())
            .map(str::to_owned);
        let params = fields
            .iter()
            .find(|(name, _)| name == "params")
            .map(|(_, value)| value);

        let Some(method) = method else {
            let response_id = id.unwrap_or(Json::Null);
            self.send_error(response_id, INVALID_REQUEST, "Invalid Request")?;
            return Ok(None);
        };

        match method.as_str() {
            "initialize" => {
                if let Some(id) = id {
                    self.send_result(id, initialize_result())?;
                }
            }
            // Notification: acknowledge nothing.
            "initialized" => {}
            "shutdown" => {
                self.shutdown_requested = true;
                if let Some(id) = id {
                    self.send_result(id, Json::Null)?;
                }
            }
            "exit" => {
                return Ok(Some(if self.shutdown_requested { 0 } else { 1 }));
            }
            "textDocument/didOpen" => self.did_open(params)?,
            "textDocument/didChange" => self.did_change(params)?,
            "textDocument/didSave" => self.did_save(params)?,
            "textDocument/didClose" => self.did_close(params)?,
            _ => {
                // Unknown notifications are ignored per JSON-RPC 2.0; requests
                // receive the standard "method not found" error.
                if let Some(id) = id {
                    self.send_error(id, METHOD_NOT_FOUND, "Method not found")?;
                }
            }
        }
        Ok(None)
    }

    fn did_open(&mut self, params: Option<&Json>) -> io::Result<()> {
        let Some(document) = params.and_then(|params| params.get("textDocument")) else {
            return Ok(());
        };
        let Some(uri) = document.get("uri").and_then(Json::as_str) else {
            return Ok(());
        };
        let uri = uri.to_owned();
        let text = document
            .get("text")
            .and_then(Json::as_str)
            .unwrap_or_default()
            .to_owned();
        let version = document.get("version").and_then(Json::as_i64).unwrap_or(0);
        self.documents
            .insert(uri.clone(), Document { text, version });
        let text = self
            .documents
            .get(&uri)
            .map(|document| document.text.clone())
            .unwrap_or_default();
        self.publish(&uri, version, Some(&text))
    }

    /// Full synchronization: `contentChanges[0].text` replaces the buffer.
    fn did_change(&mut self, params: Option<&Json>) -> io::Result<()> {
        let Some(document) = params.and_then(|params| params.get("textDocument")) else {
            return Ok(());
        };
        let Some(uri) = document.get("uri").and_then(Json::as_str) else {
            return Ok(());
        };
        let uri = uri.to_owned();
        let version = document.get("version").and_then(Json::as_i64).unwrap_or(0);
        let text = params
            .and_then(|params| params.get("contentChanges"))
            .and_then(Json::as_array)
            .and_then(|changes| changes.first())
            .and_then(|change| change.get("text"))
            .and_then(Json::as_str)
            .map(str::to_owned);

        let mut published_version = version;
        match self.documents.get_mut(&uri) {
            Some(stored) => {
                if let Some(text) = text {
                    stored.text = text;
                }
                if document.get("version").and_then(Json::as_i64).is_some() {
                    stored.version = version;
                }
                published_version = stored.version;
            }
            None => {
                // Be forgiving with clients that skip `didOpen`.
                let Some(text) = text else {
                    return Ok(());
                };
                self.documents
                    .insert(uri.clone(), Document { text, version });
            }
        }
        let text = self
            .documents
            .get(&uri)
            .map(|document| document.text.clone())
            .unwrap_or_default();
        self.publish(&uri, published_version, Some(&text))
    }

    fn did_save(&mut self, params: Option<&Json>) -> io::Result<()> {
        let Some(document) = params.and_then(|params| params.get("textDocument")) else {
            return Ok(());
        };
        let Some(uri) = document.get("uri").and_then(Json::as_str) else {
            return Ok(());
        };
        let uri = uri.to_owned();
        let saved_text = params
            .and_then(|params| params.get("text"))
            .and_then(Json::as_str)
            .map(str::to_owned);
        let version = document.get("version").and_then(Json::as_i64);

        let mut published = None;
        if let Some(stored) = self.documents.get_mut(&uri) {
            if let Some(text) = saved_text {
                stored.text = text;
            }
            if let Some(version) = version {
                stored.version = version;
            }
            published = Some((stored.version, stored.text.clone()));
        }
        match published {
            Some((version, text)) => self.publish(&uri, version, Some(&text)),
            // Saving a document that was never opened still clears stale
            // diagnostics instead of leaving the editor in an unknown state.
            None => self.publish(&uri, version.unwrap_or(0), None),
        }
    }

    fn did_close(&mut self, params: Option<&Json>) -> io::Result<()> {
        let Some(document) = params.and_then(|params| params.get("textDocument")) else {
            return Ok(());
        };
        let Some(uri) = document.get("uri").and_then(Json::as_str) else {
            return Ok(());
        };
        let uri = uri.to_owned();
        let version = self
            .documents
            .remove(&uri)
            .map(|document| document.version)
            .unwrap_or(0);
        self.publish(&uri, version, None)
    }

    /// Send `textDocument/publishDiagnostics`; `source == None` publishes an
    /// empty list (used when a document is closed or unknown).
    fn publish(&mut self, uri: &str, version: i64, source: Option<&str>) -> io::Result<()> {
        let diagnostics = source.map(diagnostics_json).unwrap_or_default();
        let params = Json::Object(vec![
            ("uri".to_owned(), Json::String(uri.to_owned())),
            ("version".to_owned(), Json::Number(version.to_string())),
            ("diagnostics".to_owned(), Json::Array(diagnostics)),
        ]);
        let message = Json::Object(vec![
            (
                "jsonrpc".to_owned(),
                Json::String(JSONRPC_VERSION.to_owned()),
            ),
            (
                "method".to_owned(),
                Json::String("textDocument/publishDiagnostics".to_owned()),
            ),
            ("params".to_owned(), params),
        ]);
        self.send(&message.to_json())
    }

    fn send_result(&mut self, id: Json, result: Json) -> io::Result<()> {
        self.send(
            &Json::Object(vec![
                (
                    "jsonrpc".to_owned(),
                    Json::String(JSONRPC_VERSION.to_owned()),
                ),
                ("id".to_owned(), id),
                ("result".to_owned(), result),
            ])
            .to_json(),
        )
    }

    fn send_error(&mut self, id: Json, code: i64, message: &str) -> io::Result<()> {
        self.send(
            &Json::Object(vec![
                (
                    "jsonrpc".to_owned(),
                    Json::String(JSONRPC_VERSION.to_owned()),
                ),
                ("id".to_owned(), id),
                (
                    "error".to_owned(),
                    Json::Object(vec![
                        ("code".to_owned(), Json::Number(code.to_string())),
                        ("message".to_owned(), Json::String(message.to_owned())),
                    ]),
                ),
            ])
            .to_json(),
        )
    }

    fn send(&mut self, body: &str) -> io::Result<()> {
        write!(self.output, "Content-Length: {}\r\n\r\n", body.len())?;
        self.output.write_all(body.as_bytes())?;
        self.output.flush()
    }
}

fn initialize_result() -> Json {
    Json::Object(vec![
        (
            "capabilities".to_owned(),
            Json::Object(vec![
                // 1 = full document synchronization.
                ("textDocumentSync".to_owned(), Json::Number("1".to_owned())),
                (
                    "positionEncoding".to_owned(),
                    Json::String("utf-16".to_owned()),
                ),
            ]),
        ),
        (
            "serverInfo".to_owned(),
            Json::Object(vec![
                ("name".to_owned(), Json::String(SERVER_NAME.to_owned())),
                (
                    "version".to_owned(),
                    Json::String(SERVER_VERSION.to_owned()),
                ),
            ]),
        ),
    ])
}

/// Read one framed message. Header lines are read until the empty line; the
/// body is read with `read_exact`, so a frame split across several writes (or
/// even one byte per write) is handled without busy-waiting.
fn read_frame<R: BufRead>(input: &mut R) -> io::Result<Frame> {
    let mut content_length = None;
    let mut saw_header = false;
    loop {
        let mut line = Vec::new();
        let read = input.read_until(b'\n', &mut line)?;
        if read == 0 {
            return Ok(Frame::Eof);
        }
        while matches!(line.last(), Some(b'\r' | b'\n')) {
            line.pop();
        }
        if line.is_empty() {
            if !saw_header {
                // Tolerate stray blank lines between frames.
                continue;
            }
            break;
        }
        saw_header = true;
        let line = String::from_utf8_lossy(&line);
        if let Some((name, value)) = line.split_once(':') {
            if name.trim().eq_ignore_ascii_case("content-length") {
                match value.trim().parse::<usize>() {
                    Ok(length) if length <= MAX_BODY_BYTES => content_length = Some(length),
                    _ => return Ok(Frame::Malformed),
                }
            }
        }
    }
    let Some(length) = content_length else {
        return Ok(Frame::Malformed);
    };
    let mut body = vec![0u8; length];
    input.read_exact(&mut body)?;
    Ok(Frame::Body(body))
}

/// Run the linter (or convert the compiler error) exactly like `zen lint`.
fn diagnostics_json(source: &str) -> Vec<Json> {
    let diagnostics = match mvp::lint(source) {
        Ok(diagnostics) => diagnostics,
        Err(error) => vec![LintDiagnostic::error(
            COMPILE_ERROR,
            error.message,
            error.span,
            source,
        )],
    };
    diagnostics
        .iter()
        .map(|diagnostic| diagnostic_json(source, diagnostic))
        .collect()
}

fn diagnostic_json(source: &str, diagnostic: &LintDiagnostic) -> Json {
    let start = lsp_position(source, diagnostic.span_start);
    let end = lsp_position(source, diagnostic.span_end.max(diagnostic.span_start));
    // LSP DiagnosticSeverity: 1 = Error, 2 = Warning (standard values).
    let severity = match diagnostic.severity {
        Severity::Error => "1",
        Severity::Warning => "2",
    };
    Json::Object(vec![
        (
            "range".to_owned(),
            Json::Object(vec![
                ("start".to_owned(), position_json(start)),
                ("end".to_owned(), position_json(end)),
            ]),
        ),
        ("severity".to_owned(), Json::Number(severity.to_owned())),
        ("code".to_owned(), Json::String(diagnostic.code.to_owned())),
        ("source".to_owned(), Json::String("zen".to_owned())),
        (
            "message".to_owned(),
            Json::String(diagnostic.message.clone()),
        ),
    ])
}

fn position_json((line, character): (u32, u32)) -> Json {
    Json::Object(vec![
        ("line".to_owned(), Json::Number(line.to_string())),
        ("character".to_owned(), Json::Number(character.to_string())),
    ])
}

/// Convert a byte offset into a zero-based LSP position (line, UTF-16 column).
///
/// Offsets outside the source or inside a multi-byte character fall back to
/// the whole source, mirroring `lint::line_column`, so malformed spans remain
/// serializable instead of panicking.
fn lsp_position(source: &str, offset: u32) -> (u32, u32) {
    let prefix = source.get(..offset as usize).unwrap_or(source);
    let line = prefix.bytes().filter(|byte| *byte == b'\n').count() as u32;
    let line_start = prefix.rfind('\n').map(|index| index + 1).unwrap_or(0);
    let character = prefix[line_start..]
        .chars()
        .map(|character| character.len_utf16() as u32)
        .sum();
    (line, character)
}

// ---------------------------------------------------------------------------
// Minimal JSON (no dependency)
// ---------------------------------------------------------------------------

/// Parse failure; intentionally opaque because callers only report -32700.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct JsonError;

/// Tiny JSON tree used for requests and responses. Numbers keep their original
/// lexeme so integer ids and versions round-trip without precision loss.
#[derive(Debug, Clone, PartialEq)]
pub enum Json {
    Null,
    Bool(bool),
    Number(String),
    String(String),
    Array(Vec<Json>),
    Object(Vec<(String, Json)>),
}

impl Json {
    pub fn parse(input: &str) -> Result<Self, JsonError> {
        let mut parser = JsonParser { input, pos: 0 };
        parser.skip_whitespace();
        let value = parser.value().map_err(|()| JsonError)?;
        parser.skip_whitespace();
        if parser.pos == input.len() {
            Ok(value)
        } else {
            Err(JsonError)
        }
    }

    pub fn get(&self, key: &str) -> Option<&Json> {
        match self {
            Json::Object(fields) => fields
                .iter()
                .find(|(name, _)| name == key)
                .map(|(_, value)| value),
            _ => None,
        }
    }

    pub fn as_str(&self) -> Option<&str> {
        match self {
            Json::String(value) => Some(value),
            _ => None,
        }
    }

    pub fn as_i64(&self) -> Option<i64> {
        match self {
            Json::Number(value) => value.parse().ok(),
            _ => None,
        }
    }

    pub fn as_array(&self) -> Option<&[Json]> {
        match self {
            Json::Array(items) => Some(items),
            _ => None,
        }
    }

    pub fn to_json(&self) -> String {
        match self {
            Json::Null => "null".to_owned(),
            Json::Bool(value) => value.to_string(),
            Json::Number(value) => value.clone(),
            Json::String(value) => format!("\"{}\"", escape_json(value)),
            Json::Array(items) => format!(
                "[{}]",
                items
                    .iter()
                    .map(Json::to_json)
                    .collect::<Vec<_>>()
                    .join(",")
            ),
            Json::Object(fields) => format!(
                "{{{}}}",
                fields
                    .iter()
                    .map(|(name, value)| format!("\"{}\":{}", escape_json(name), value.to_json()))
                    .collect::<Vec<_>>()
                    .join(",")
            ),
        }
    }
}

struct JsonParser<'a> {
    input: &'a str,
    pos: usize,
}

impl<'a> JsonParser<'a> {
    fn peek(&self) -> Option<u8> {
        self.input.as_bytes().get(self.pos).copied()
    }

    fn bump(&mut self) -> Option<u8> {
        let byte = self.peek()?;
        self.pos += 1;
        Some(byte)
    }

    fn expect(&mut self, expected: u8) -> Result<(), ()> {
        if self.bump() == Some(expected) {
            Ok(())
        } else {
            Err(())
        }
    }

    fn skip_whitespace(&mut self) {
        while matches!(self.peek(), Some(b' ' | b'\n' | b'\r' | b'\t')) {
            self.pos += 1;
        }
    }

    fn value(&mut self) -> Result<Json, ()> {
        match self.peek() {
            Some(b'{') => self.object(),
            Some(b'[') => self.array(),
            Some(b'"') => self.string().map(Json::String),
            Some(b't') => {
                self.keyword("true")?;
                Ok(Json::Bool(true))
            }
            Some(b'f') => {
                self.keyword("false")?;
                Ok(Json::Bool(false))
            }
            Some(b'n') => {
                self.keyword("null")?;
                Ok(Json::Null)
            }
            Some(b'-' | b'0'..=b'9') => self.number(),
            _ => Err(()),
        }
    }

    fn keyword(&mut self, word: &str) -> Result<(), ()> {
        for byte in word.bytes() {
            self.expect(byte)?;
        }
        Ok(())
    }

    fn object(&mut self) -> Result<Json, ()> {
        self.expect(b'{')?;
        let mut fields = Vec::new();
        self.skip_whitespace();
        if self.peek() == Some(b'}') {
            self.pos += 1;
            return Ok(Json::Object(fields));
        }
        loop {
            self.skip_whitespace();
            let key = self.string()?;
            self.skip_whitespace();
            self.expect(b':')?;
            self.skip_whitespace();
            let value = self.value()?;
            fields.push((key, value));
            self.skip_whitespace();
            match self.bump() {
                Some(b',') => {}
                Some(b'}') => return Ok(Json::Object(fields)),
                _ => return Err(()),
            }
        }
    }

    fn array(&mut self) -> Result<Json, ()> {
        self.expect(b'[')?;
        let mut items = Vec::new();
        self.skip_whitespace();
        if self.peek() == Some(b']') {
            self.pos += 1;
            return Ok(Json::Array(items));
        }
        loop {
            self.skip_whitespace();
            items.push(self.value()?);
            self.skip_whitespace();
            match self.bump() {
                Some(b',') => {}
                Some(b']') => return Ok(Json::Array(items)),
                _ => return Err(()),
            }
        }
    }

    fn string(&mut self) -> Result<String, ()> {
        self.expect(b'"')?;
        let mut output = String::new();
        loop {
            let byte = self.peek().ok_or(())?;
            match byte {
                b'"' => {
                    self.pos += 1;
                    return Ok(output);
                }
                b'\\' => {
                    self.pos += 1;
                    let escape = self.bump().ok_or(())?;
                    match escape {
                        b'"' => output.push('"'),
                        b'\\' => output.push('\\'),
                        b'/' => output.push('/'),
                        b'b' => output.push('\u{08}'),
                        b'f' => output.push('\u{0c}'),
                        b'n' => output.push('\n'),
                        b'r' => output.push('\r'),
                        b't' => output.push('\t'),
                        b'u' => output.push(self.unicode_escape()?),
                        _ => return Err(()),
                    }
                }
                byte if byte < 0x20 => return Err(()),
                _ => {
                    let character = self.input[self.pos..].chars().next().ok_or(())?;
                    self.pos += character.len_utf8();
                    output.push(character);
                }
            }
        }
    }

    fn unicode_escape(&mut self) -> Result<char, ()> {
        let first = self.hex4()?;
        let code = if (0xd800..=0xdbff).contains(&first) {
            // High surrogate: JSON encodes the pair as two `\uXXXX` escapes.
            self.expect(b'\\')?;
            self.expect(b'u')?;
            let second = self.hex4()?;
            if !(0xdc00..=0xdfff).contains(&second) {
                return Err(());
            }
            0x1_0000 + ((first - 0xd800) << 10) + (second - 0xdc00)
        } else if (0xdc00..=0xdfff).contains(&first) {
            return Err(());
        } else {
            first
        };
        char::from_u32(code).ok_or(())
    }

    fn hex4(&mut self) -> Result<u32, ()> {
        let mut value = 0;
        for _ in 0..4 {
            let digit = self.bump().ok_or(())?;
            value = value * 16
                + match digit {
                    b'0'..=b'9' => (digit - b'0') as u32,
                    b'a'..=b'f' => (digit - b'a' + 10) as u32,
                    b'A'..=b'F' => (digit - b'A' + 10) as u32,
                    _ => return Err(()),
                };
        }
        Ok(value)
    }

    fn number(&mut self) -> Result<Json, ()> {
        let start = self.pos;
        if self.peek() == Some(b'-') {
            self.pos += 1;
        }
        match self.peek() {
            Some(b'0') => {
                self.pos += 1;
                if matches!(self.peek(), Some(b'0'..=b'9')) {
                    return Err(());
                }
            }
            Some(b'1'..=b'9') => {
                while matches!(self.peek(), Some(b'0'..=b'9')) {
                    self.pos += 1;
                }
            }
            _ => return Err(()),
        }
        if self.peek() == Some(b'.') {
            self.pos += 1;
            if !matches!(self.peek(), Some(b'0'..=b'9')) {
                return Err(());
            }
            while matches!(self.peek(), Some(b'0'..=b'9')) {
                self.pos += 1;
            }
        }
        if matches!(self.peek(), Some(b'e' | b'E')) {
            self.pos += 1;
            if matches!(self.peek(), Some(b'+' | b'-')) {
                self.pos += 1;
            }
            if !matches!(self.peek(), Some(b'0'..=b'9')) {
                return Err(());
            }
            while matches!(self.peek(), Some(b'0'..=b'9')) {
                self.pos += 1;
            }
        }
        Ok(Json::Number(self.input[start..self.pos].to_owned()))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn json_parser_handles_rpc_messages_and_escapes() {
        let value = Json::parse(
            r#"{"jsonrpc":"2.0","id":7,"params":{"text":"let x = \"a\";\n","n":-1,"ok":true,"arr":[null]}}"#,
        )
        .unwrap();
        assert_eq!(value.get("id").and_then(Json::as_i64), Some(7));
        assert_eq!(
            value
                .get("params")
                .and_then(|params| params.get("text"))
                .and_then(Json::as_str),
            Some("let x = \"a\";\n")
        );
        assert_eq!(
            value
                .get("params")
                .and_then(|params| params.get("n"))
                .and_then(Json::as_i64),
            Some(-1)
        );
        assert!(Json::parse("{").is_err());
        assert!(Json::parse("{} trailing").is_err());
    }

    #[test]
    fn positions_are_zero_based_and_utf16_aware() {
        let source = "uno\n  año";
        assert_eq!(lsp_position(source, 0), (0, 0));
        assert_eq!(lsp_position(source, 4), (1, 0));
        // The ñ occupies one UTF-16 code unit and two UTF-8 bytes.
        assert_eq!(lsp_position(source, 9), (1, 4));
        assert_eq!(lsp_position(source, 10), (1, 5));
        assert_eq!(lsp_position(source, 10_000), (1, 5));
    }

    #[test]
    fn diagnostics_use_lsp_severities_and_ranges() {
        let source = "fn main() -> i32 {\n  let x = 1;\n  return 0;\n}\n";
        let diagnostics = diagnostics_json(source);
        assert_eq!(diagnostics.len(), 1);
        let diagnostic = &diagnostics[0];
        assert_eq!(diagnostic.get("severity").and_then(Json::as_i64), Some(2));
        assert_eq!(
            diagnostic.get("code").and_then(Json::as_str),
            Some("unused-variable")
        );
        let range = diagnostic.get("range").unwrap();
        let start = range.get("start").unwrap();
        assert_eq!(start.get("line").and_then(Json::as_i64), Some(1));
        assert_eq!(start.get("character").and_then(Json::as_i64), Some(6));
        let end = range.get("end").unwrap();
        assert_eq!(end.get("line").and_then(Json::as_i64), Some(1));
        assert_eq!(end.get("character").and_then(Json::as_i64), Some(7));

        let broken = diagnostics_json("fn main() -> i32 {\n  return missing;\n}\n");
        assert_eq!(broken.len(), 1);
        assert_eq!(broken[0].get("severity").and_then(Json::as_i64), Some(1));
        assert_eq!(
            broken[0].get("code").and_then(Json::as_str),
            Some("compile-error")
        );
    }
}
