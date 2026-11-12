//! CLI-level acceptance tests for `zen lsp` (TASK-910).
//!
//! Every test spawns the real binary and speaks framed JSON-RPC over its
//! stdin/stdout, so framing, dispatch and process exit codes are exercised
//! end to end.
use std::{
    fs,
    io::{BufRead, BufReader, Read, Write},
    path::PathBuf,
    process::{Child, ChildStdin, ChildStdout, Command, Stdio},
    sync::atomic::{AtomicU64, Ordering},
};

const WARNING_SOURCE: &str = "fn main() -> i32 {\n  let x = 1;\n  return 0;\n}\n";
const CLEAN_SOURCE: &str = "fn main() -> i32 {\n  print(\"ok\");\n  return 0;\n}\n";
const BROKEN_SOURCE: &str = "fn main() -> i32 {\n  return missing;\n}\n";

// --- harness ---------------------------------------------------------------

struct Lsp {
    child: Child,
    stdin: Option<ChildStdin>,
    stdout: BufReader<ChildStdout>,
}

impl Lsp {
    fn start() -> Self {
        let mut child = Command::new(env!("CARGO_BIN_EXE_zen"))
            .arg("lsp")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .spawn()
            .expect("spawn zen lsp");
        let stdin = child.stdin.take().expect("LSP stdin");
        let stdout = BufReader::new(child.stdout.take().expect("LSP stdout"));
        Self {
            child,
            stdin: Some(stdin),
            stdout,
        }
    }

    fn write_bytes(&mut self, bytes: &[u8]) {
        let stdin = self.stdin.as_mut().expect("LSP stdin is open");
        stdin.write_all(bytes).expect("write to LSP stdin");
        stdin.flush().expect("flush LSP stdin");
    }

    fn send(&mut self, body: &str) {
        let frame = format!("Content-Length: {}\r\n\r\n{body}", body.len());
        self.write_bytes(frame.as_bytes());
    }

    fn recv(&mut self) -> Json {
        let body = read_frame(&mut self.stdout);
        Json::parse(&body)
            .unwrap_or_else(|error| panic!("invalid JSON from server: {error}\n{body}"))
    }

    fn request(&mut self, id: i64, method: &str, params: &str) -> Json {
        self.send(&format!(
            r#"{{"jsonrpc":"2.0","id":{id},"method":"{method}","params":{params}}}"#
        ));
        self.recv()
    }

    fn notify(&mut self, method: &str, params: &str) {
        self.send(&format!(
            r#"{{"jsonrpc":"2.0","method":"{method}","params":{params}}}"#
        ));
    }

    fn initialize(&mut self) -> Json {
        let response = self.request(
            1,
            "initialize",
            r#"{"processId":null,"rootUri":null,"capabilities":{}}"#,
        );
        self.notify("initialized", "{}");
        response
    }

    fn exit(&mut self) -> i32 {
        self.notify("exit", "null");
        self.stdin.take();
        self.child
            .wait()
            .expect("wait for zen lsp")
            .code()
            .expect("zen lsp exited normally")
    }

    fn finish(&mut self) -> i32 {
        let response = self.request(999, "shutdown", "null");
        assert_eq!(response.get("result"), Some(&Json::Null));
        self.exit()
    }
}

impl Drop for Lsp {
    fn drop(&mut self) {
        drop(self.stdin.take());
        if matches!(self.child.try_wait(), Ok(None)) {
            let _ = self.child.kill();
            let _ = self.child.wait();
        }
    }
}

fn read_frame(reader: &mut BufReader<ChildStdout>) -> String {
    let mut content_length = None;
    loop {
        let mut line = String::new();
        let read = reader.read_line(&mut line).expect("read LSP header");
        assert!(read > 0, "unexpected EOF while reading LSP headers");
        let trimmed = line.trim_end_matches(|character| character == '\r' || character == '\n');
        if trimmed.is_empty() {
            break;
        }
        if let Some((name, value)) = trimmed.split_once(':') {
            if name.eq_ignore_ascii_case("content-length") {
                content_length = Some(
                    value
                        .trim()
                        .parse::<usize>()
                        .expect("invalid Content-Length from server"),
                );
            }
        }
    }
    let length = content_length.expect("server response has no Content-Length");
    let mut body = vec![0u8; length];
    reader.read_exact(&mut body).expect("read LSP body");
    String::from_utf8(body).expect("LSP body is UTF-8")
}

fn diagnostics(message: &Json) -> &[Json] {
    assert_eq!(
        message.get("method").and_then(Json::as_str),
        Some("textDocument/publishDiagnostics"),
        "unexpected notification: {message:?}"
    );
    message
        .get("params")
        .and_then(|params| params.get("diagnostics"))
        .and_then(Json::as_array)
        .expect("publishDiagnostics has a diagnostics array")
}

// --- request builders ------------------------------------------------------

fn quote(text: &str) -> String {
    let mut output = String::from("\"");
    for character in text.chars() {
        match character {
            '"' => output.push_str("\\\""),
            '\\' => output.push_str("\\\\"),
            '\n' => output.push_str("\\n"),
            '\r' => output.push_str("\\r"),
            '\t' => output.push_str("\\t"),
            character if (character as u32) < 0x20 => {
                output.push_str(&format!("\\u{:04x}", character as u32))
            }
            character => output.push(character),
        }
    }
    output.push('"');
    output
}

fn did_open(uri: &str, version: i64, text: &str) -> String {
    format!(
        r#"{{"textDocument":{{"uri":{},"languageId":"zen","version":{version},"text":{}}}}}"#,
        quote(uri),
        quote(text)
    )
}

fn did_change(uri: &str, version: i64, text: &str) -> String {
    format!(
        r#"{{"textDocument":{{"uri":{},"version":{version}}},"contentChanges":[{{"text":{}}}]}}"#,
        quote(uri),
        quote(text)
    )
}

fn did_save(uri: &str) -> String {
    format!(r#"{{"textDocument":{{"uri":{}}}}}"#, quote(uri))
}

fn did_close(uri: &str) -> String {
    format!(r#"{{"textDocument":{{"uri":{}}}}}"#, quote(uri))
}

fn diagnostic_field<'a>(diagnostic: &'a Json, name: &str) -> &'a Json {
    diagnostic
        .get(name)
        .unwrap_or_else(|| panic!("diagnostic has no '{name}': {diagnostic:?}"))
}

fn position_field<'a>(diagnostic: &'a Json, end: &str, name: &str) -> i64 {
    diagnostic
        .get("range")
        .and_then(|range| range.get(end))
        .and_then(|position| position.get(name))
        .and_then(Json::as_i64)
        .unwrap_or_else(|| panic!("diagnostic has no range.{end}.{name}: {diagnostic:?}"))
}

// --- tests -----------------------------------------------------------------

#[test]
fn initialize_advertises_full_sync_and_server_info() {
    let mut lsp = Lsp::start();
    let response = lsp.initialize();
    assert_eq!(response.get("jsonrpc").and_then(Json::as_str), Some("2.0"));
    assert_eq!(response.get("id").and_then(Json::as_i64), Some(1));
    let result = response.get("result").expect("initialize result");
    let capabilities = result.get("capabilities").expect("capabilities");
    assert_eq!(
        capabilities.get("textDocumentSync").and_then(Json::as_i64),
        Some(1),
        "full synchronization must be advertised"
    );
    let info = result.get("serverInfo").expect("serverInfo");
    assert_eq!(info.get("name").and_then(Json::as_str), Some("zen-lsp"));
    assert!(!info
        .get("version")
        .and_then(Json::as_str)
        .expect("serverInfo.version")
        .is_empty());
    assert_eq!(lsp.finish(), 0);
}

#[test]
fn did_open_publishes_warning_diagnostics() {
    let uri = "file:///tmp/zen-lsp-warning.zen";
    let mut lsp = Lsp::start();
    lsp.initialize();
    lsp.notify("textDocument/didOpen", &did_open(uri, 4, WARNING_SOURCE));
    let message = lsp.recv();
    let params = message.get("params").expect("publishDiagnostics params");
    assert_eq!(params.get("uri").and_then(Json::as_str), Some(uri));
    assert_eq!(params.get("version").and_then(Json::as_i64), Some(4));
    let diagnostics = diagnostics(&message);
    assert_eq!(diagnostics.len(), 1, "{diagnostics:?}");
    let diagnostic = &diagnostics[0];
    assert_eq!(
        diagnostic_field(diagnostic, "severity").as_i64(),
        Some(2),
        "LSP warning severity is 2"
    );
    assert_eq!(
        diagnostic_field(diagnostic, "code").as_str(),
        Some("unused-variable")
    );
    assert!(diagnostic_field(diagnostic, "message")
        .as_str()
        .expect("message text")
        .contains("unused variable 'x'"));
    // Zero-based LSP positions: x is at line 1, UTF-16 character 6.
    assert_eq!(position_field(diagnostic, "start", "line"), 1);
    assert_eq!(position_field(diagnostic, "start", "character"), 6);
    assert_eq!(position_field(diagnostic, "end", "line"), 1);
    assert_eq!(position_field(diagnostic, "end", "character"), 7);
    assert_eq!(lsp.finish(), 0);
}

#[test]
fn did_change_clears_then_updates_diagnostics() {
    let uri = "file:///tmp/zen-lsp-change.zen";
    let mut lsp = Lsp::start();
    lsp.initialize();
    lsp.notify("textDocument/didOpen", &did_open(uri, 1, WARNING_SOURCE));
    let message = lsp.recv();
    assert_eq!(diagnostics(&message).len(), 1);

    // Full sync replaces the buffer: the warning disappears.
    lsp.notify("textDocument/didChange", &did_change(uri, 2, CLEAN_SOURCE));
    let message = lsp.recv();
    assert_eq!(
        message
            .get("params")
            .and_then(|params| params.get("version"))
            .and_then(Json::as_i64),
        Some(2)
    );
    assert!(
        diagnostics(&message).is_empty(),
        "clean edit must clear diagnostics"
    );

    // Editing back to a warning republishes and bumps the version.
    lsp.notify(
        "textDocument/didChange",
        &did_change(uri, 3, WARNING_SOURCE),
    );
    let message = lsp.recv();
    assert_eq!(
        message
            .get("params")
            .and_then(|params| params.get("version"))
            .and_then(Json::as_i64),
        Some(3)
    );
    let diagnostics = diagnostics(&message);
    assert_eq!(diagnostics.len(), 1);
    assert_eq!(
        diagnostic_field(&diagnostics[0], "code").as_str(),
        Some("unused-variable")
    );
    assert_eq!(lsp.finish(), 0);
}

#[test]
fn did_save_re_publishes_diagnostics_from_the_stored_buffer() {
    let uri = "file:///tmp/zen-lsp-save.zen";
    let mut lsp = Lsp::start();
    lsp.initialize();
    lsp.notify("textDocument/didOpen", &did_open(uri, 6, WARNING_SOURCE));
    assert_eq!(diagnostics(&lsp.recv()).len(), 1);

    lsp.notify("textDocument/didSave", &did_save(uri));
    let message = lsp.recv();
    let params = message.get("params").expect("publishDiagnostics params");
    assert_eq!(params.get("uri").and_then(Json::as_str), Some(uri));
    assert_eq!(params.get("version").and_then(Json::as_i64), Some(6));
    assert_eq!(diagnostics(&message).len(), 1);
    assert_eq!(lsp.finish(), 0);
}

#[test]
fn did_close_publishes_an_empty_list() {
    let uri = "file:///tmp/zen-lsp-close.zen";
    let mut lsp = Lsp::start();
    lsp.initialize();
    lsp.notify("textDocument/didOpen", &did_open(uri, 7, WARNING_SOURCE));
    assert_eq!(diagnostics(&lsp.recv()).len(), 1);

    lsp.notify("textDocument/didClose", &did_close(uri));
    let message = lsp.recv();
    let params = message.get("params").expect("publishDiagnostics params");
    assert_eq!(params.get("uri").and_then(Json::as_str), Some(uri));
    assert_eq!(params.get("version").and_then(Json::as_i64), Some(7));
    assert!(diagnostics(&message).is_empty());
    assert_eq!(lsp.finish(), 0);
}

#[test]
fn shutdown_returns_null_and_exit_zero() {
    let mut lsp = Lsp::start();
    lsp.initialize();
    let response = lsp.request(42, "shutdown", "null");
    assert_eq!(response.get("id").and_then(Json::as_i64), Some(42));
    assert_eq!(response.get("result"), Some(&Json::Null));
    assert_eq!(lsp.exit(), 0);
}

#[test]
fn exit_without_shutdown_returns_one() {
    let mut lsp = Lsp::start();
    lsp.initialize();
    assert_eq!(lsp.exit(), 1);
}

#[test]
fn unknown_method_returns_method_not_found_and_keeps_serving() {
    let mut lsp = Lsp::start();
    let response = lsp.request(7, "workspace/unknown", "{}");
    assert_eq!(response.get("id").and_then(Json::as_i64), Some(7));
    assert_eq!(
        response
            .get("error")
            .and_then(|error| error.get("code"))
            .and_then(Json::as_i64),
        Some(-32601)
    );
    // The server must still answer valid requests afterwards.
    let response = lsp.request(8, "initialize", "{}");
    assert!(response.get("result").is_some());
    lsp.notify("initialized", "{}");
    assert_eq!(lsp.finish(), 0);
}

#[test]
fn invalid_json_returns_parse_error_and_keeps_serving() {
    let mut lsp = Lsp::start();
    let body = "this is not json";
    let frame = format!("Content-Length: {}\r\n\r\n{body}", body.len());
    lsp.write_bytes(frame.as_bytes());

    let response = lsp.recv();
    assert_eq!(
        response
            .get("error")
            .and_then(|error| error.get("code"))
            .and_then(Json::as_i64),
        Some(-32700)
    );
    assert_eq!(response.get("id"), Some(&Json::Null));

    let response = lsp.request(1, "initialize", "{}");
    assert!(response.get("result").is_some());
    lsp.notify("initialized", "{}");
    assert_eq!(lsp.finish(), 0);
}

#[test]
fn framing_split_across_writes_is_reassembled() {
    let mut lsp = Lsp::start();
    let body = r#"{"jsonrpc":"2.0","id":3,"method":"initialize","params":{}}"#;
    let frame = format!("Content-Length: {}\r\n\r\n{body}", body.len());
    // One byte per write: headers and body arrive in tiny fragments.
    for byte in frame.as_bytes() {
        lsp.write_bytes(&[*byte]);
    }
    let response = lsp.recv();
    assert_eq!(response.get("id").and_then(Json::as_i64), Some(3));
    assert_eq!(
        response
            .get("result")
            .and_then(|result| result.get("capabilities"))
            .and_then(|capabilities| capabilities.get("textDocumentSync"))
            .and_then(Json::as_i64),
        Some(1)
    );
    lsp.notify("initialized", "{}");
    assert_eq!(lsp.finish(), 0);
}

#[test]
fn compiler_errors_are_published_as_errors() {
    let uri = "file:///tmp/zen-lsp-error.zen";
    let mut lsp = Lsp::start();
    lsp.initialize();
    lsp.notify("textDocument/didOpen", &did_open(uri, 1, BROKEN_SOURCE));
    let message = lsp.recv();
    let diagnostics = diagnostics(&message);
    assert_eq!(diagnostics.len(), 1);
    let diagnostic = &diagnostics[0];
    assert_eq!(
        diagnostic_field(diagnostic, "severity").as_i64(),
        Some(1),
        "LSP error severity is 1"
    );
    assert_eq!(
        diagnostic_field(diagnostic, "code").as_str(),
        Some("compile-error")
    );
    assert!(diagnostic_field(diagnostic, "message")
        .as_str()
        .expect("message text")
        .contains("unknown variable"));
    assert_eq!(position_field(diagnostic, "start", "line"), 1);
    assert_eq!(lsp.finish(), 0);
}

#[test]
fn diagnostics_match_lint_json_code_severity_and_line() {
    let case = Case::new();
    let path = case.write("input.zen", WARNING_SOURCE);
    let output = Command::new(env!("CARGO_BIN_EXE_zen"))
        .current_dir(&case.0)
        .args(["lint", "--json", "input.zen"])
        .output()
        .expect("run zen lint --json");
    assert!(
        output.status.success(),
        "lint failed: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    let cli = Json::parse(&String::from_utf8(output.stdout).expect("lint JSON is UTF-8"))
        .expect("valid lint JSON");
    let cli_diagnostics = cli.as_array().expect("lint JSON array");

    let uri = format!("file://{}", path.display());
    let mut lsp = Lsp::start();
    lsp.initialize();
    lsp.notify("textDocument/didOpen", &did_open(&uri, 1, WARNING_SOURCE));
    let message = lsp.recv();
    let lsp_diagnostics = diagnostics(&message);
    assert_eq!(lsp_diagnostics.len(), cli_diagnostics.len());
    for (lsp_diagnostic, cli_diagnostic) in lsp_diagnostics.iter().zip(cli_diagnostics) {
        assert_eq!(
            diagnostic_field(lsp_diagnostic, "code").as_str(),
            cli_diagnostic.get("code").and_then(Json::as_str)
        );
        assert_eq!(
            diagnostic_field(lsp_diagnostic, "message").as_str(),
            cli_diagnostic.get("message").and_then(Json::as_str)
        );
        let expected_severity = match cli_diagnostic
            .get("severity")
            .and_then(Json::as_str)
            .expect("lint severity")
        {
            "error" => 1,
            "warning" => 2,
            other => panic!("unexpected lint severity {other}"),
        };
        assert_eq!(
            diagnostic_field(lsp_diagnostic, "severity").as_i64(),
            Some(expected_severity)
        );
        // Lint lines are one-based; LSP lines are zero-based.
        assert_eq!(
            position_field(lsp_diagnostic, "start", "line") + 1,
            cli_diagnostic
                .get("line")
                .and_then(Json::as_i64)
                .expect("lint line")
        );
    }
    assert_eq!(lsp.finish(), 0);
}

// --- temporary directory ---------------------------------------------------

static NEXT_CASE: AtomicU64 = AtomicU64::new(0);

struct Case(PathBuf);

impl Case {
    fn new() -> Self {
        let path = std::env::temp_dir().join(format!(
            "zen-lsp-test-{}-{}",
            std::process::id(),
            NEXT_CASE.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&path).expect("create temporary directory");
        Self(path)
    }

    fn write(&self, name: &str, source: &str) -> PathBuf {
        let path = self.0.join(name);
        fs::write(&path, source).expect("write temporary source");
        path
    }
}

impl Drop for Case {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

// --- minimal JSON parser (tests must not trust the server's own writer) -----

#[derive(Debug, Clone, PartialEq)]
enum Json {
    Null,
    Bool(bool),
    Number(i64),
    String(String),
    Array(Vec<Json>),
    Object(Vec<(String, Json)>),
}

impl Json {
    fn parse(input: &str) -> Result<Self, String> {
        let mut parser = Parser { input, pos: 0 };
        parser.skip_whitespace();
        let value = parser.value()?;
        parser.skip_whitespace();
        if parser.pos == input.len() {
            Ok(value)
        } else {
            Err(format!("trailing characters at byte {}", parser.pos))
        }
    }

    fn get(&self, key: &str) -> Option<&Json> {
        match self {
            Json::Object(fields) => fields
                .iter()
                .find(|(name, _)| name == key)
                .map(|(_, value)| value),
            _ => None,
        }
    }

    fn as_str(&self) -> Option<&str> {
        match self {
            Json::String(value) => Some(value),
            _ => None,
        }
    }

    fn as_i64(&self) -> Option<i64> {
        match self {
            Json::Number(value) => Some(*value),
            _ => None,
        }
    }

    fn as_array(&self) -> Option<&[Json]> {
        match self {
            Json::Array(items) => Some(items),
            _ => None,
        }
    }
}

struct Parser<'a> {
    input: &'a str,
    pos: usize,
}

impl<'a> Parser<'a> {
    fn peek(&self) -> Option<u8> {
        self.input.as_bytes().get(self.pos).copied()
    }

    fn bump(&mut self) -> Option<u8> {
        let byte = self.peek()?;
        self.pos += 1;
        Some(byte)
    }

    fn expect(&mut self, expected: u8) -> Result<(), String> {
        if self.bump() == Some(expected) {
            Ok(())
        } else {
            Err(format!(
                "expected '{}' at byte {}",
                expected as char,
                self.pos - 1
            ))
        }
    }

    fn skip_whitespace(&mut self) {
        while matches!(self.peek(), Some(b' ' | b'\n' | b'\r' | b'\t')) {
            self.pos += 1;
        }
    }

    fn value(&mut self) -> Result<Json, String> {
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
            other => Err(format!("unexpected token {other:?} at byte {}", self.pos)),
        }
    }

    fn keyword(&mut self, word: &str) -> Result<(), String> {
        for byte in word.bytes() {
            self.expect(byte)?;
        }
        Ok(())
    }

    fn object(&mut self) -> Result<Json, String> {
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
                other => return Err(format!("expected ',' or '}}', found {other:?}")),
            }
        }
    }

    fn array(&mut self) -> Result<Json, String> {
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
                other => return Err(format!("expected ',' or ']', found {other:?}")),
            }
        }
    }

    fn string(&mut self) -> Result<String, String> {
        self.expect(b'"')?;
        let mut output = String::new();
        loop {
            let byte = self.peek().ok_or("unexpected end of JSON string")?;
            match byte {
                b'"' => {
                    self.pos += 1;
                    return Ok(output);
                }
                b'\\' => {
                    self.pos += 1;
                    match self.bump().ok_or("unexpected end after escape")? {
                        b'"' => output.push('"'),
                        b'\\' => output.push('\\'),
                        b'/' => output.push('/'),
                        b'b' => output.push('\u{08}'),
                        b'f' => output.push('\u{0c}'),
                        b'n' => output.push('\n'),
                        b'r' => output.push('\r'),
                        b't' => output.push('\t'),
                        b'u' => output.push(self.unicode_escape()?),
                        other => return Err(format!("invalid escape \\{other}")),
                    }
                }
                byte if byte < 0x20 => return Err("raw control byte in string".to_owned()),
                _ => {
                    let character = self.input[self.pos..]
                        .chars()
                        .next()
                        .ok_or("unexpected end of string")?;
                    self.pos += character.len_utf8();
                    output.push(character);
                }
            }
        }
    }

    fn unicode_escape(&mut self) -> Result<char, String> {
        let first = self.hex4()?;
        let code = if (0xd800..=0xdbff).contains(&first) {
            self.expect(b'\\')?;
            self.expect(b'u')?;
            let second = self.hex4()?;
            if !(0xdc00..=0xdfff).contains(&second) {
                return Err("invalid surrogate pair".to_owned());
            }
            0x1_0000 + ((first - 0xd800) << 10) + (second - 0xdc00)
        } else {
            first
        };
        char::from_u32(code).ok_or_else(|| "invalid unicode escape".to_owned())
    }

    fn hex4(&mut self) -> Result<u32, String> {
        let mut value = 0;
        for _ in 0..4 {
            let digit = self.bump().ok_or("short \\u escape")?;
            value = value * 16
                + match digit {
                    b'0'..=b'9' => (digit - b'0') as u32,
                    b'a'..=b'f' => (digit - b'a' + 10) as u32,
                    b'A'..=b'F' => (digit - b'A' + 10) as u32,
                    _ => return Err("invalid hex digit in \\u escape".to_owned()),
                };
        }
        Ok(value)
    }

    fn number(&mut self) -> Result<Json, String> {
        let start = self.pos;
        if self.peek() == Some(b'-') {
            self.pos += 1;
        }
        while matches!(self.peek(), Some(b'0'..=b'9')) {
            self.pos += 1;
        }
        let text = &self.input[start..self.pos];
        text.parse::<i64>()
            .map(Json::Number)
            .map_err(|_| format!("invalid integer number {text:?}"))
    }
}
