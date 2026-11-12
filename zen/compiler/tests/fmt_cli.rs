//! CLI-level acceptance tests for `zen fmt` (TASK-904A).
use std::{
    fs,
    path::PathBuf,
    process::{Command, Output},
    sync::atomic::{AtomicU64, Ordering},
};
use zen_compiler::fmt::format;

static NEXT: AtomicU64 = AtomicU64::new(0);

struct Case(PathBuf);

impl Case {
    fn new() -> Self {
        let path = std::env::temp_dir().join(format!(
            "zen-fmt-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&path).unwrap();
        Self(path)
    }
    fn path(&self) -> PathBuf {
        self.0.join("input.zen")
    }
    fn write(&self, source: &str) {
        fs::write(self.path(), source).unwrap();
    }
    fn read(&self) -> String {
        fs::read_to_string(self.path()).unwrap()
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

fn success(out: &Output) {
    assert!(
        out.status.success(),
        "status={}\nstdout={}\nstderr={}",
        out.status,
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
}

#[test]
fn spacing_around_operators_commas_and_delimiters() {
    let case = Case::new();
    case.write("fn add(a:i32,b:i32)->i32{return a+b*2;}\nfn main()->i32{let x=add(1,2);print_uint(x as u64);return 0;}\n");
    let out = case.cli(&["fmt", "input.zen"]);
    success(&out);
    assert_eq!(
        String::from_utf8(out.stdout).unwrap(),
        concat!(
            "fn add(a: i32, b: i32) -> i32 {\n",
            "  return a + b * 2;\n",
            "}\n",
            "\n",
            "fn main() -> i32 {\n",
            "  let x = add(1, 2);\n",
            "  print_uint(x as u64);\n",
            "  return 0;\n",
            "}\n",
        )
    );
}

#[test]
fn indentation_uses_two_spaces_per_block() {
    let case = Case::new();
    case.write(
        "fn main()->i32{let mut i:u64=0;while i<2{if i==1{print(\"one\");}i+=1;}return 0;}\n",
    );
    let out = case.cli(&["fmt", "input.zen"]);
    success(&out);
    assert_eq!(
        String::from_utf8(out.stdout).unwrap(),
        concat!(
            "fn main() -> i32 {\n",
            "  let mut i: u64 = 0;\n",
            "  while i < 2 {\n",
            "    if i == 1 {\n",
            "      print(\"one\");\n",
            "    }\n",
            "    i += 1;\n",
            "  }\n",
            "  return 0;\n",
            "}\n",
        )
    );
}

#[test]
fn line_comments_move_to_their_own_indented_line() {
    let case = Case::new();
    case.write("// header\nfn main()->i32{ // trailing\nlet x=1;\n// own\nreturn x; // end\n}\n");
    let out = case.cli(&["fmt", "input.zen"]);
    success(&out);
    assert_eq!(
        String::from_utf8(out.stdout).unwrap(),
        concat!(
            "// header\n",
            "fn main() -> i32 {\n",
            "  // trailing\n",
            "  let x = 1;\n",
            "  // own\n",
            "  return x;\n",
            "  // end\n",
            "}\n",
        )
    );
}

#[test]
fn block_comments_are_preserved_inline_or_on_their_own_line() {
    let case = Case::new();
    case.write("fn main()->i32{let x=/* keep */1;/* own /* nested */ block */return x;}\n");
    let out = case.cli(&["fmt", "input.zen"]);
    success(&out);
    assert_eq!(
        String::from_utf8(out.stdout).unwrap(),
        concat!(
            "fn main() -> i32 {\n",
            "  let x = /* keep */ 1;\n",
            "  /* own /* nested */ block */\n",
            "  return x;\n",
            "}\n",
        )
    );
}

#[test]
fn formatting_is_idempotent_with_comments() {
    let source = concat!(
        "// top\n",
        "fn main()->i32{ /* before */ let x=1; // after\n",
        "if x>0{return x;}else{return 0;}\n",
        "}\n",
    );
    let once = format(source).expect("first format");
    let twice = format(&once).expect("second format");
    assert_eq!(once, twice);
    assert_eq!(format(&twice).expect("third format"), once);

    let case = Case::new();
    case.write(&once);
    let out = case.cli(&["fmt", "input.zen"]);
    success(&out);
    assert_eq!(String::from_utf8(out.stdout).unwrap(), once);
}

#[test]
fn check_accepts_an_already_formatted_file() {
    let case = Case::new();
    let formatted = format("fn main()->i32{return 0;}\n").expect("format");
    case.write(&formatted);
    let out = case.cli(&["fmt", "--check", "input.zen"]);
    success(&out);
    assert!(out.stdout.is_empty(), "check should be quiet on success");
    assert_eq!(case.read(), formatted);
}

#[test]
fn check_rejects_unformatted_input_without_writing() {
    let case = Case::new();
    let source = "fn main()->i32{return 0;}\n";
    case.write(source);
    let out = case.cli(&["fmt", "--check", "input.zen"]);
    assert_eq!(
        out.status.code(),
        Some(1),
        "stderr={}",
        String::from_utf8_lossy(&out.stderr)
    );
    let stderr = String::from_utf8_lossy(&out.stderr);
    assert!(
        stderr.contains("not formatted") && stderr.contains("input.zen"),
        "missing clear diagnostic: {stderr}"
    );
    assert_eq!(case.read(), source, "--check must not modify the file");
    assert_eq!(fs::read_dir(&case.0).unwrap().count(), 1);
}

#[cfg(unix)]
#[test]
fn write_replaces_atomically_and_preserves_permissions() {
    use std::os::unix::fs::PermissionsExt;

    let case = Case::new();
    let source = "fn main()->i32{return 0;}\n";
    let expected = format(source).expect("format");
    case.write(source);
    fs::set_permissions(case.path(), fs::Permissions::from_mode(0o640)).unwrap();

    let out = case.cli(&["fmt", "--write", "input.zen"]);
    success(&out);
    assert_eq!(case.read(), expected);
    assert_eq!(
        fs::metadata(case.path()).unwrap().permissions().mode() & 0o777,
        0o640
    );
    let names: Vec<_> = fs::read_dir(&case.0)
        .unwrap()
        .map(|entry| entry.unwrap().file_name().to_string_lossy().into_owned())
        .collect();
    assert_eq!(
        names,
        vec!["input.zen".to_string()],
        "temporary file leaked"
    );

    // A second --write is a no-op and still leaves no temporary files behind.
    let out = case.cli(&["fmt", "--write", "input.zen"]);
    success(&out);
    assert_eq!(case.read(), expected);
    success(&case.cli(&["fmt", "--check", "input.zen"]));
}

#[test]
fn missing_file_fails_with_a_clear_error() {
    let case = Case::new();
    let out = case.cli(&["fmt", "missing.zen"]);
    assert!(!out.status.success());
    let stderr = String::from_utf8_lossy(&out.stderr);
    assert!(
        stderr.contains("cannot read") && stderr.contains("missing.zen"),
        "unclear error: {stderr}"
    );
}

#[test]
fn formatted_examples_still_pass_zen_check() {
    // `freestanding.zen` is intentionally excluded: it needs an external
    // `emit_byte` at link time, although `zen check` currently accepts it.
    for (name, source) in [
        ("hello", include_str!("../../examples/hello.zen")),
        ("factorial", include_str!("../../examples/factorial.zen")),
        ("arrays", include_str!("../../examples/arrays.zen")),
        ("structs", include_str!("../../examples/structs.zen")),
    ] {
        let formatted = format(source).unwrap_or_else(|error| panic!("{name}: {error}"));
        assert_eq!(
            format(&formatted).unwrap_or_else(|error| panic!("{name}: {error}")),
            formatted,
            "{name}: formatter is not idempotent"
        );
        let case = Case::new();
        case.write(&formatted);
        let out = case.cli(&["check", "input.zen"]);
        assert!(
            out.status.success(),
            "{name}: formatted example does not check\nstdout={}\nstderr={}\n--- source ---\n{formatted}",
            String::from_utf8_lossy(&out.stdout),
            String::from_utf8_lossy(&out.stderr),
        );
        success(&case.cli(&["fmt", "--check", "input.zen"]));
    }
}
