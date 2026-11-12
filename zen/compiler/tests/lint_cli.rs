//! CLI-level acceptance tests for `zen lint` (TASK-909).
use std::{
    fs,
    path::PathBuf,
    process::{Command, Output},
    sync::atomic::{AtomicU64, Ordering},
};

static NEXT: AtomicU64 = AtomicU64::new(0);

struct Case(PathBuf);

impl Case {
    fn new() -> Self {
        let path = std::env::temp_dir().join(format!(
            "zen-lint-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&path).unwrap();
        Self(path)
    }
    fn write(&self, source: &str) {
        fs::write(self.0.join("input.zen"), source).unwrap();
    }
    fn cli(&self, args: &[&str]) -> Output {
        Command::new(env!("CARGO_BIN_EXE_zen"))
            .current_dir(&self.0)
            .args(args)
            .output()
            .unwrap()
    }
}

impl Drop for Case {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

fn text(out: &Output) -> String {
    String::from_utf8(out.stdout.clone()).expect("stdout is UTF-8")
}

fn status(out: &Output) -> i32 {
    out.status
        .code()
        .unwrap_or_else(|| panic!("killed by signal\nstderr={}", String::from_utf8_lossy(&out.stderr)))
}

fn assert_clean(out: &Output) {
    assert_eq!(
        status(out),
        0,
        "stdout={}\nstderr={}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
    assert!(out.stdout.is_empty(), "expected no diagnostics, got: {}", text(out));
    assert!(out.stderr.is_empty(), "unexpected stderr: {}", String::from_utf8_lossy(&out.stderr));
}

// --- minimal JSON parser ---------------------------------------------------
// The compiler has no JSON dependency, so the tests validate stdout with a
// small dependency-free parser instead of trusting a substring check.

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
    fn as_array(&self) -> &[Json] {
        match self {
            Self::Array(items) => items,
            other => panic!("expected array, found {other:?}"),
        }
    }
    fn as_str(&self) -> &str {
        match self {
            Self::String(value) => value,
            other => panic!("expected string, found {other:?}"),
        }
    }
    fn as_i64(&self) -> i64 {
        match self {
            Self::Number(value) => *value,
            other => panic!("expected number, found {other:?}"),
        }
    }
    fn get(&self, key: &str) -> &Json {
        match self {
            Self::Object(fields) => fields
                .iter()
                .find(|(name, _)| name == key)
                .map(|(_, value)| value)
                .unwrap_or_else(|| panic!("missing key '{key}' in {self:?}")),
            other => panic!("expected object, found {other:?}"),
        }
    }
    fn field_count(&self) -> usize {
        match self {
            Self::Object(fields) => fields.len(),
            other => panic!("expected object, found {other:?}"),
        }
    }
}

struct JsonParser<'a> {
    input: &'a [u8],
    pos: usize,
}

impl<'a> JsonParser<'a> {
    fn parse(input: &'a str) -> Json {
        let mut parser = Self {
            input: input.as_bytes(),
            pos: 0,
        };
        parser.skip_whitespace();
        let value = parser.value();
        parser.skip_whitespace();
        assert_eq!(
            parser.pos,
            parser.input.len(),
            "trailing characters in JSON output: {:?}",
            &input[parser.pos..]
        );
        value
    }

    fn peek(&self) -> Option<u8> {
        self.input.get(self.pos).copied()
    }

    fn take(&mut self) -> u8 {
        let byte = self.peek().expect("unexpected end of JSON");
        self.pos += 1;
        byte
    }

    fn expect(&mut self, expected: u8) {
        let found = self.take();
        assert_eq!(found, expected, "unexpected byte at offset {}", self.pos - 1);
    }

    fn skip_whitespace(&mut self) {
        while matches!(self.peek(), Some(b' ' | b'\n' | b'\r' | b'\t')) {
            self.pos += 1;
        }
    }

    fn value(&mut self) -> Json {
        match self.peek() {
            Some(b'{') => self.object(),
            Some(b'[') => self.array(),
            Some(b'"') => Json::String(self.string()),
            Some(b't') => {
                self.keyword("true");
                Json::Bool(true)
            }
            Some(b'f') => {
                self.keyword("false");
                Json::Bool(false)
            }
            Some(b'n') => {
                self.keyword("null");
                Json::Null
            }
            Some(b'-' | b'0'..=b'9') => self.number(),
            other => panic!("unexpected JSON token {other:?} at {}", self.pos),
        }
    }

    fn keyword(&mut self, expected: &str) {
        for byte in expected.bytes() {
            self.expect(byte);
        }
    }

    fn object(&mut self) -> Json {
        self.expect(b'{');
        let mut fields = Vec::new();
        self.skip_whitespace();
        if self.peek() == Some(b'}') {
            self.pos += 1;
            return Json::Object(fields);
        }
        loop {
            self.skip_whitespace();
            let key = self.string();
            self.skip_whitespace();
            self.expect(b':');
            self.skip_whitespace();
            let value = self.value();
            fields.push((key, value));
            self.skip_whitespace();
            match self.take() {
                b',' => continue,
                b'}' => break,
                other => panic!("expected ',' or '}}', found byte {other}"),
            }
        }
        Json::Object(fields)
    }

    fn array(&mut self) -> Json {
        self.expect(b'[');
        let mut items = Vec::new();
        self.skip_whitespace();
        if self.peek() == Some(b']') {
            self.pos += 1;
            return Json::Array(items);
        }
        loop {
            self.skip_whitespace();
            items.push(self.value());
            self.skip_whitespace();
            match self.take() {
                b',' => continue,
                b']' => break,
                other => panic!("expected ',' or ']', found byte {other}"),
            }
        }
        Json::Array(items)
    }

    fn string(&mut self) -> String {
        self.expect(b'"');
        let mut output = String::new();
        loop {
            let byte = self.take();
            match byte {
                b'"' => break,
                b'\\' => match self.take() {
                    b'"' => output.push('"'),
                    b'\\' => output.push('\\'),
                    b'/' => output.push('/'),
                    b'b' => output.push('\u{08}'),
                    b'f' => output.push('\u{0c}'),
                    b'n' => output.push('\n'),
                    b'r' => output.push('\r'),
                    b't' => output.push('\t'),
                    b'u' => {
                        let mut code = 0u32;
                        for _ in 0..4 {
                            let digit = self.take();
                            code = code * 16
                                + match digit {
                                    b'0'..=b'9' => (digit - b'0') as u32,
                                    b'a'..=b'f' => (digit - b'a' + 10) as u32,
                                    b'A'..=b'F' => (digit - b'A' + 10) as u32,
                                    other => panic!("invalid \\u escape byte {other}"),
                                };
                        }
                        output.push(char::from_u32(code).expect("valid unicode escape"));
                    }
                    other => panic!("invalid JSON escape {other}"),
                },
                byte if byte < 0x20 => panic!("raw control byte in JSON string"),
                byte if byte < 0x80 => output.push(byte as char),
                _ => {
                    let start = self.pos - 1;
                    let len = if byte & 0xE0 == 0xC0 {
                        2
                    } else if byte & 0xF0 == 0xE0 {
                        3
                    } else if byte & 0xF8 == 0xF0 {
                        4
                    } else {
                        panic!("invalid UTF-8 lead byte {byte}")
                    };
                    let end = start + len;
                    output.push_str(
                        std::str::from_utf8(&self.input[start..end]).expect("valid UTF-8"),
                    );
                    self.pos = end;
                }
            }
        }
        output
    }

    fn number(&mut self) -> Json {
        let start = self.pos;
        if self.peek() == Some(b'-') {
            self.pos += 1;
        }
        while matches!(self.peek(), Some(b'0'..=b'9')) {
            self.pos += 1;
        }
        let text = std::str::from_utf8(&self.input[start..self.pos]).expect("UTF-8 number");
        Json::Number(text.parse().expect("integer JSON number"))
    }
}

fn parse_json(text: &str) -> Json {
    JsonParser::parse(text)
}

fn parse_json_array(text: &str) -> Vec<Json> {
    parse_json(text).as_array().to_vec()
}

fn assert_diagnostic_schema(diagnostic: &Json) {
    assert_eq!(diagnostic.field_count(), 8, "unexpected fields: {diagnostic:?}");
    let severity = diagnostic.get("severity").as_str();
    assert!(
        severity == "warning" || severity == "error",
        "unexpected severity {severity}"
    );
    assert!(!diagnostic.get("code").as_str().is_empty());
    assert!(!diagnostic.get("message").as_str().is_empty());
    assert_eq!(diagnostic.get("file").as_str(), "input.zen");
    assert!(diagnostic.get("line").as_i64() >= 1);
    assert!(diagnostic.get("column").as_i64() >= 1);
    assert!(diagnostic.get("span_start").as_i64() >= 0);
    assert!(
        diagnostic.get("span_end").as_i64() >= diagnostic.get("span_start").as_i64(),
        "invalid span: {diagnostic:?}"
    );
}

// --- rules -----------------------------------------------------------------

#[test]
fn unused_variable_is_a_warning_and_exit_zero() {
    let case = Case::new();
    case.write("fn main() -> i32 {\n  let x = 1;\n  return 0;\n}\n");
    let out = case.cli(&["lint", "input.zen"]);
    assert_eq!(status(&out), 0);
    let out_text = text(&out);
    assert!(
        out_text.contains("input.zen:2:7: warning[unused-variable]:"),
        "{out_text}"
    );
    assert!(out_text.contains("unused variable 'x'"), "{out_text}");
    assert!(out.stderr.is_empty());
}

#[test]
fn underscore_names_are_ignored() {
    let case = Case::new();
    case.write("fn main() -> i32 {\n  let _ignored = 1;\n  let _ = 2;\n  return 0;\n}\n");
    let out = case.cli(&["lint", "input.zen"]);
    assert_clean(&out);
}

#[test]
fn read_and_compound_assigned_variables_are_not_flagged() {
    let case = Case::new();
    case.write(
        "fn main() -> i32 {\n  let mut x = 1;\n  x += 1;\n  print_uint(x as u64);\n  return 0;\n}\n",
    );
    assert_clean(&case.cli(&["lint", "input.zen"]));
}

#[test]
fn assignment_without_read_is_reported() {
    let case = Case::new();
    case.write("fn main() -> i32 {\n  let mut x = 1;\n  x = 2;\n  return 0;\n}\n");
    let out = case.cli(&["lint", "input.zen"]);
    assert_eq!(status(&out), 0);
    let out_text = text(&out);
    assert!(out_text.contains("warning[unused-variable]"), "{out_text}");
    assert!(
        out_text.contains("variable 'x' is assigned but never read"),
        "{out_text}"
    );
}

#[test]
fn unused_parameter_is_reported_but_called_functions_are_not() {
    let case = Case::new();
    case.write(
        "fn helper(x: i32) -> i32 {\n  return 0;\n}\nfn main() -> i32 {\n  return helper(1);\n}\n",
    );
    let out = case.cli(&["lint", "input.zen"]);
    assert_eq!(status(&out), 0);
    let out_text = text(&out);
    assert!(out_text.contains("warning[unused-parameter]"), "{out_text}");
    assert!(out_text.contains("unused parameter 'x'"), "{out_text}");
    assert!(
        !out_text.contains("unused-function"),
        "called helper must not be reported: {out_text}"
    );
}

#[test]
fn underscore_parameters_are_ignored() {
    let case = Case::new();
    case.write(
        "fn helper(_x: i32) -> i32 {\n  return 0;\n}\nfn main() -> i32 {\n  return helper(1);\n}\n",
    );
    assert_clean(&case.cli(&["lint", "input.zen"]));
}

#[test]
fn unused_private_function_is_reported() {
    let case = Case::new();
    case.write("fn helper() -> i32 {\n  return 1;\n}\nfn main() -> i32 {\n  return 0;\n}\n");
    let out = case.cli(&["lint", "input.zen"]);
    assert_eq!(status(&out), 0);
    let out_text = text(&out);
    assert!(out_text.contains("warning[unused-function]"), "{out_text}");
    assert!(out_text.contains("unused function 'helper'"), "{out_text}");
}

#[test]
fn public_functions_and_main_are_never_reported() {
    let case = Case::new();
    case.write("pub fn exported() -> i32 {\n  return 1;\n}\nfn main() -> i32 {\n  return 0;\n}\n");
    assert_clean(&case.cli(&["lint", "input.zen"]));
}

#[test]
fn module_without_main_is_linted_as_a_library() {
    let case = Case::new();
    case.write("fn helper(x: i32) -> i32 {\n  return x;\n}\n");
    let out = case.cli(&["lint", "input.zen"]);
    assert_eq!(status(&out), 0);
    let out_text = text(&out);
    assert!(out_text.contains("warning[unused-function]"), "{out_text}");
    assert!(
        !out_text.contains("compile-error"),
        "a module without main must not be a compile error: {out_text}"
    );
}

#[test]
fn statements_after_return_are_unreachable() {
    let case = Case::new();
    case.write(
        "fn main() -> i32 {\n  return 0;\n  print(\"dead\");\n  return 1;\n}\n",
    );
    let out = case.cli(&["lint", "input.zen"]);
    assert_eq!(status(&out), 0);
    let out_text = text(&out);
    assert_eq!(
        out_text.matches("warning[unreachable-code]").count(),
        2,
        "{out_text}"
    );
    assert!(
        !out_text.contains("unused-variable"),
        "unreachable lets must not cascade: {out_text}"
    );
}

#[test]
fn shadowed_outer_variable_is_reported() {
    let case = Case::new();
    case.write(
        "fn main() -> i32 {\n  let x = 1;\n  {\n    let x = 2;\n    print_uint(x as u64);\n  }\n  return 0;\n}\n",
    );
    let out = case.cli(&["lint", "input.zen"]);
    assert_eq!(status(&out), 0);
    let out_text = text(&out);
    assert_eq!(
        out_text.matches("warning[unused-variable]").count(),
        1,
        "{out_text}"
    );
    assert!(out_text.contains("input.zen:2:7:"), "{out_text}");
}

// --- exit codes ------------------------------------------------------------

#[test]
fn deny_warnings_exits_two() {
    let case = Case::new();
    case.write("fn main() -> i32 { let x = 1; return 0; }\n");
    assert_eq!(status(&case.cli(&["lint", "--deny-warnings", "input.zen"])), 2);
}

#[test]
fn deny_warnings_with_clean_file_exits_zero() {
    let case = Case::new();
    case.write("fn main() -> i32 { print(\"ok\"); return 0; }\n");
    assert_clean(&case.cli(&["lint", "--deny-warnings", "input.zen"]));
}

#[test]
fn errors_win_over_deny_warnings() {
    let case = Case::new();
    case.write("fn main() -> i32 { return missing; }\n");
    let out = case.cli(&["lint", "--deny-warnings", "input.zen"]);
    assert_eq!(status(&out), 1);
    let out_text = text(&out);
    assert!(out_text.contains("error[compile-error]"), "{out_text}");
}

// --- JSON ------------------------------------------------------------------

#[test]
fn json_reports_every_rule_with_the_documented_schema() {
    let case = Case::new();
    case.write(
        "fn unused(x: i32) -> i32 {\n  return 0;\n  print(\"dead\");\n}\nfn main() -> i32 {\n  let idle = 1;\n  return 0;\n}\n",
    );
    let out = case.cli(&["lint", "--json", "input.zen"]);
    assert_eq!(status(&out), 0);
    let diagnostics = parse_json_array(&text(&out));
    assert_eq!(diagnostics.len(), 4, "{diagnostics:?}");
    for diagnostic in &diagnostics {
        assert_diagnostic_schema(diagnostic);
        assert_eq!(diagnostic.get("severity").as_str(), "warning");
        assert_eq!(diagnostic.get("file").as_str(), "input.zen");
    }
    let codes: Vec<&str> = diagnostics
        .iter()
        .map(|diagnostic| diagnostic.get("code").as_str())
        .collect();
    for expected in [
        "unused-function",
        "unused-parameter",
        "unreachable-code",
        "unused-variable",
    ] {
        assert!(codes.contains(&expected), "missing {expected} in {codes:?}");
    }
}

#[test]
fn json_compile_error_is_machine_readable() {
    let case = Case::new();
    case.write("fn main() -> i32 {\n  return missing;\n}\n");
    let out = case.cli(&["lint", "--json", "input.zen"]);
    assert_eq!(status(&out), 1);
    let diagnostics = parse_json_array(&text(&out));
    assert_eq!(diagnostics.len(), 1, "{diagnostics:?}");
    let diagnostic = &diagnostics[0];
    assert_diagnostic_schema(diagnostic);
    assert_eq!(diagnostic.get("severity").as_str(), "error");
    assert_eq!(diagnostic.get("code").as_str(), "compile-error");
    assert_eq!(diagnostic.get("line").as_i64(), 2);
    assert!(
        diagnostic.get("message").as_str().contains("unknown variable"),
        "{diagnostic:?}"
    );
}

#[test]
fn valid_complex_program_has_no_false_positives() {
    let case = Case::new();
    case.write(
        r#"struct Point {
  x: i32,
  y: i32,
}

fn add(a: i32, b: i32) -> i32 {
  return a + b;
}

fn main() -> i32 {
  let mut p: Point = Point { x: 1, y: 2 };
  let mut values: [u64; 3] = [1; 3];
  values[1] = add(p.x, p.y) as u64;
  p.x += 1;
  let mut i: u64 = 0;
  while i < 3 {
    if values[i] > 0 {
      print_uint(values[i]);
    }
    i += 1;
  }
  unsafe {
    let ptr: *mut u32 = 0x1000u64 as *mut u32;
    volatile_store(ptr, p.x as u32);
    p.y = volatile_load(ptr) as i32;
  }
  print_int(p.y as i64);
  return 0;
}
"#,
    );
    assert_clean(&case.cli(&["lint", "input.zen"]));
}

#[test]
fn valid_examples_have_no_diagnostics() {
    for (name, source) in [
        ("hello", include_str!("../../examples/hello.zen")),
        ("factorial", include_str!("../../examples/factorial.zen")),
        ("arrays", include_str!("../../examples/arrays.zen")),
        ("structs", include_str!("../../examples/structs.zen")),
        ("stdlib", include_str!("../../examples/stdlib.zen")),
        ("freestanding", include_str!("../../examples/freestanding.zen")),
    ] {
        let case = Case::new();
        case.write(source);
        let out = case.cli(&["lint", "input.zen"]);
        assert_eq!(
            status(&out),
            0,
            "{name}: unexpected status\nstdout={}\nstderr={}\n--- source ---\n{source}",
            String::from_utf8_lossy(&out.stdout),
            String::from_utf8_lossy(&out.stderr),
        );
        assert!(
            out.stdout.is_empty(),
            "{name}: examples must be warning-free, got:\n{}",
            text(&out)
        );
    }
}
