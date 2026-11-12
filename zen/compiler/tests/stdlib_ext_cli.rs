//! TASK-901B: stdlib extension builtins (`str_starts_with`, `str_ends_with`,
//! `str_rfind`) checked through the real CLI, hosted and freestanding.
use std::{
    fs,
    path::PathBuf,
    process::{Command, Output},
    sync::atomic::{AtomicU64, Ordering},
};
static NEXT: AtomicU64 = AtomicU64::new(0);
const TARGET: &str = "x86_64-unknown-none";
struct Case(PathBuf);
impl Case {
    fn new(source: &str) -> Self {
        let path = std::env::temp_dir().join(format!(
            "zen-stdlib-ext-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&path).unwrap();
        fs::write(path.join("input.zen"), source).unwrap();
        Self(path)
    }
    fn cli(&self, args: &[&str]) -> Output {
        Command::new(env!("CARGO_BIN_EXE_zen"))
            .current_dir(&self.0)
            .args(args)
            .output()
            .unwrap()
    }
    fn tool(&self, tool: &str, args: &[&str]) -> Output {
        Command::new(tool)
            .current_dir(&self.0)
            .env("LC_ALL", "C")
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
fn run_both(source: &str, expected: &[u8]) {
    let case = Case::new(source);
    for args in [
        vec!["run", "input.zen"],
        vec!["run", "input.zen", "--release"],
    ] {
        let out = case.cli(&args);
        success(&out);
        assert_eq!(out.stdout, expected);
    }
}
fn reject(source: &str, needles: &[&str]) {
    let case = Case::new(source);
    for args in [
        vec!["check", "input.zen"],
        vec!["check", "input.zen", "--target", TARGET],
    ] {
        let out = case.cli(&args);
        assert!(
            !out.status.success(),
            "accepted invalid source with {args:?}: {source}"
        );
        let stderr = String::from_utf8_lossy(&out.stderr);
        assert!(stderr.contains("input.zen:"), "{stderr}");
        assert!(!stderr.contains("panicked"), "{stderr}");
        for needle in needles {
            assert!(stderr.contains(needle), "missing {needle:?}: {stderr}");
        }
    }
}
fn emit_freestanding_c(case: &Case, name: &str) -> String {
    let out = case.cli(&[
        "build",
        "input.zen",
        "--target",
        TARGET,
        "--emit",
        "c",
        "-o",
        name,
    ]);
    success(&out);
    fs::read_to_string(case.0.join(name)).unwrap()
}

const EXAMPLE_OUTPUT: &str = "\
starts zen zen = true
starts zen zebra = false
starts zen empty = true
starts empty empty = true
starts empty z = false
starts longer zen = false
starts banana ban = true
starts banana ana = false
starts nul a\\0b a\\0 = true
ends zen zen = true
ends zen en = true
ends zen z = false
ends zen empty = true
ends empty empty = true
ends empty z = false
ends longer zen = false
ends banana nana = true
ends banana ban = false
ends nul a\\0b \\0b = true
rfind banana na = 4
rfind banana ana = 3
rfind banana ba = 0
rfind banana z = -1
rfind banana empty = 6
rfind empty empty = 0
rfind empty x = -1
rfind longer bananas = -1
rfind aaaa aa = 2
rfind aaaa aaa = 1
rfind ababab abab = 2
rfind nul a\\0b \\0b = 1
ext ok
";

#[test]
fn hosted_str_starts_with_compares_prefix_bytes() {
    run_both(
        r#"
fn show(v: bool) -> void { if v { print("1"); } else { print("0"); } print("\n"); }
fn main() -> i32 {
    show(str_starts_with("zen", "zen"));
    show(str_starts_with("zen", "ze"));
    show(str_starts_with("zen", "z"));
    show(str_starts_with("zen", "zen "));
    show(str_starts_with("zen", "zebra"));
    show(str_starts_with("zen", ""));
    show(str_starts_with("", ""));
    show(str_starts_with("", "z"));
    show(str_starts_with("banana", "ban"));
    show(str_starts_with("banana", "ana"));
    show(str_starts_with("a\0b", "a\0"));
    show(str_starts_with("a\0b", "a\0c"));
    show(str_starts_with("é", "é"));
    return 0;
}
"#,
        b"1\n1\n1\n0\n0\n1\n1\n0\n1\n0\n1\n0\n1\n",
    );
}

#[test]
fn hosted_str_ends_with_compares_suffix_bytes() {
    run_both(
        r#"
fn show(v: bool) -> void { if v { print("1"); } else { print("0"); } print("\n"); }
fn main() -> i32 {
    show(str_ends_with("zen", "zen"));
    show(str_ends_with("zen", "en"));
    show(str_ends_with("zen", "n"));
    show(str_ends_with("zen", " zen"));
    show(str_ends_with("zen", "longer zen"));
    show(str_ends_with("zen", ""));
    show(str_ends_with("", ""));
    show(str_ends_with("", "z"));
    show(str_ends_with("banana", "nana"));
    show(str_ends_with("banana", "ban"));
    show(str_ends_with("a\0b", "\0b"));
    show(str_ends_with("a\0b", "\0c"));
    show(str_ends_with("é", "é"));
    return 0;
}
"#,
        b"1\n1\n1\n0\n0\n1\n1\n0\n1\n0\n1\n0\n1\n",
    );
}

#[test]
fn hosted_str_rfind_reports_last_byte_index() {
    run_both(
        r#"
fn show(a: str, b: str) -> void { print_int(str_rfind(a, b)); print("\n"); }
fn main() -> i32 {
    show("banana", "na");
    show("banana", "ana");
    show("banana", "ba");
    show("banana", "banana");
    show("banana", "bananas");
    show("banana", "z");
    show("banana", "");
    show("", "");
    show("", "x");
    show("aaaa", "aa");
    show("aaaa", "aaa");
    show("aaaa", "a");
    show("ababab", "abab");
    show("ababab", "bab");
    show("abc", "c");
    show("a\0b", "\0b");
    show("a\0a", "a\0a");
    return 0;
}
"#,
        b"4\n3\n0\n0\n-1\n-1\n6\n0\n-1\n2\n1\n3\n2\n3\n2\n1\n0\n",
    );
}

#[test]
fn hosted_extension_composes_with_existing_builtins() {
    run_both(
        r#"
fn main() -> i32 {
    let text: str = "zen-stdlib-ext";
    if str_starts_with(text, "zen-")
        && str_ends_with(text, "-ext")
        && str_rfind(text, "-") == 10
        && str_find(text, "-") == 3
        && str_len(text) == 14
        && !str_starts_with(text, "ext")
        && !str_ends_with(text, "zen-")
    {
        print("composed ext\n");
        return 0;
    }
    return 1;
}
"#,
        b"composed ext\n",
    );
}

#[test]
fn hosted_example_file_runs_with_expected_output() {
    let example = concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../examples/stdlib_ext.zen"
    );
    for release in [false, true] {
        let mut args = vec!["run", example];
        if release {
            args.push("--release");
        }
        let out = Command::new(env!("CARGO_BIN_EXE_zen"))
            .args(&args)
            .output()
            .unwrap();
        success(&out);
        assert_eq!(out.stdout, EXAMPLE_OUTPUT.as_bytes());
        assert_eq!(out.status.code(), Some(0));
    }
}

#[test]
fn builtin_function_names_are_reserved() {
    for name in ["str_starts_with", "str_ends_with", "str_rfind"] {
        let source = format!(
            "fn {name}(a: str, b: str) -> bool {{ return true; }}\nfn main() -> i32 {{ return 0; }}"
        );
        reject(&source, &["duplicate or reserved function", name]);
    }
}

#[test]
fn local_bindings_may_shadow_extension_builtin_names() {
    // Only function definitions are reserved: a local may reuse the identifier,
    // while `name(...)` still resolves to the builtin signature.
    run_both(
        r#"
fn main() -> i32 {
    let str_starts_with: bool = true;
    let str_ends_with: bool = false;
    let str_rfind: u64 = 7;
    if str_starts_with
        && !str_ends_with
        && str_rfind == 7
        && str_starts_with("zen", "ze")
        && str_ends_with("zen", "en")
        && str_rfind("banana", "na") == 4
    {
        print("shadow ext\n");
    }
    return 0;
}
"#,
        b"shadow ext\n",
    );
}

#[test]
fn rejects_non_string_arguments_in_both_modes() {
    for expression in [
        "let x: bool = str_starts_with(\"a\", 1);",
        "let x: bool = str_starts_with(1, \"a\");",
        "let x: bool = str_ends_with(\"a\", true);",
        "let x: bool = str_ends_with(1u64, \"a\");",
        "let x: i64 = str_rfind(\"a\", true);",
        "let x: i64 = str_rfind(1, \"a\");",
    ] {
        reject(
            &format!("fn main() -> i32 {{ {expression} return 0; }}"),
            &["type mismatch", "expected str"],
        );
    }
    for (expression, needles) in [
        (
            "let x: i64 = str_starts_with(\"a\", \"a\");",
            &["expected i64", "found bool"][..],
        ),
        (
            "let x: i32 = str_ends_with(\"a\", \"a\");",
            &["expected i32", "found bool"][..],
        ),
        (
            "let x: bool = str_rfind(\"a\", \"a\");",
            &["expected bool", "found i64"][..],
        ),
    ] {
        reject(
            &format!("fn main() -> i32 {{ {expression} return 0; }}"),
            needles,
        );
    }
}

#[test]
fn rejects_wrong_builtin_arity_in_both_modes() {
    for call in [
        "let x: bool = str_starts_with(\"a\");",
        "let x: bool = str_starts_with(\"a\", \"b\", \"c\");",
        "let x: bool = str_ends_with();",
        "let x: bool = str_ends_with(\"a\");",
        "let x: i64 = str_rfind(\"a\");",
        "let x: i64 = str_rfind(\"a\", \"b\", \"c\");",
    ] {
        reject(
            &format!("fn main() -> i32 {{ {call} return 0; }}"),
            &["expects 2 arguments"],
        );
    }
}

#[test]
fn emitted_helpers_are_static_and_libc_free_in_both_modes() {
    let case = Case::new(
        r#"
fn main() -> i32 {
    if str_starts_with("abc", "ab")
        && str_ends_with("abc", "bc")
        && str_rfind("abcabc", "bc") == 4
    {
        return 0;
    }
    return 1;
}
"#,
    );
    for (args, name) in [
        (
            vec!["build", "input.zen", "--emit", "c", "-o", "hosted.c"],
            "hosted.c",
        ),
        (
            vec![
                "build",
                "input.zen",
                "--target",
                TARGET,
                "--emit",
                "c",
                "-o",
                "free.c",
            ],
            "free.c",
        ),
    ] {
        success(&case.cli(&args));
        let c = fs::read_to_string(case.0.join(name)).unwrap();
        for helper in [
            "static bool __zen_str_starts_with(",
            "static bool __zen_str_ends_with(",
            "static int64_t __zen_str_rfind(",
        ] {
            assert!(c.contains(helper), "missing {helper:?} in {name}");
        }
        for forbidden in [
            "#include <string.h>",
            "memcmp(",
            "memchr(",
            "memrchr(",
            "memcpy(",
            "strcmp(",
            "strlen(",
            "strncmp(",
            "strstr(",
            "strrchr(",
            "malloc(",
        ] {
            assert!(!c.contains(forbidden), "found {forbidden:?} in {name}");
        }
        if name == "free.c" {
            // Helpers must stay libc-free; hosted prelude only pulls libc for print.
            for forbidden in ["#include <stdio.h>", "#include <stdlib.h>"] {
                assert!(!c.contains(forbidden), "found {forbidden:?} in {name}");
            }
            assert!(!c.contains("int main(void)"));
        }
    }
    // The extension helpers are one shared prelude block: identical text in
    // hosted and freestanding output, so semantics cannot drift per mode.
    let block = |text: &str| {
        let start = text
            .find("static bool __zen_str_starts_with(")
            .expect("extension helper block");
        let end = text[start..]
            .find("static uint64_t __zen_index_check(")
            .map(|offset| start + offset)
            .expect("index check helper");
        text[start..end].to_string()
    };
    let hosted = fs::read_to_string(case.0.join("hosted.c")).unwrap();
    let free = fs::read_to_string(case.0.join("free.c")).unwrap();
    assert!(!block(&hosted).is_empty());
    assert_eq!(block(&hosted), block(&free));
}

#[test]
fn freestanding_probe_matches_hosted_semantics() {
    let case = Case::new(
        r#"
pub fn probe() -> i32 {
    if !str_starts_with("zen", "zen") { return 1; }
    if !str_starts_with("zen", "") { return 2; }
    if str_starts_with("zen", "zen ") { return 3; }
    if !str_ends_with("zen", "en") { return 4; }
    if !str_ends_with("zen", "") { return 5; }
    if str_ends_with("zen", "z") { return 6; }
    if str_rfind("banana", "na") != 4 { return 7; }
    if str_rfind("banana", "") != 6 { return 8; }
    if str_rfind("banana", "z") != -1 { return 9; }
    if str_rfind("", "") != 0 { return 10; }
    if str_rfind("banana", "bananas") != -1 { return 11; }
    if str_rfind("aaaa", "aa") != 2 { return 12; }
    if str_rfind("a\0b", "\0b") != 1 { return 13; }
    if !str_starts_with("a\0b", "a\0") { return 14; }
    if !str_ends_with("a\0b", "\0b") { return 15; }
    if str_rfind("", "x") != -1 { return 16; }
    return 0;
}
"#,
    );
    let c = emit_freestanding_c(&case, "program.c");
    assert!(!c.contains("int main(void)"));
    fs::write(
        case.0.join("harness.c"),
        r#"
#include <stdint.h>
#include <stdio.h>
extern int32_t probe(void);
int main(void) {
    int32_t code = probe();
    if (code != 0) { printf("probe=%d\n", (int)code); return 1; }
    printf("freestanding-ext-ok\n");
    return 0;
}
"#,
    )
    .unwrap();
    let compile = case.tool(
        "cc",
        &[
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-ffreestanding",
            "-fno-builtin",
            "-c",
            "program.c",
            "-o",
            "program.o",
        ],
    );
    success(&compile);
    let undefined = case.tool("nm", &["-u", "program.o"]);
    success(&undefined);
    assert!(
        String::from_utf8_lossy(&undefined.stdout).trim().is_empty(),
        "freestanding object has undefined symbols: {}",
        String::from_utf8_lossy(&undefined.stdout)
    );
    success(&case.tool(
        "cc",
        &[
            "-std=c11",
            "-Wall",
            "-Wextra",
            "program.c",
            "harness.c",
            "-o",
            "harness",
        ],
    ));
    let run = case.tool("sh", &["-c", "ulimit -c 0; exec ./harness"]);
    success(&run);
    assert_eq!(run.stdout, b"freestanding-ext-ok\n");
}

#[test]
fn freestanding_rejects_non_string_arguments() {
    let case = Case::new(
        "pub fn probe() -> i32 { if str_rfind(\"a\", 1) == 0 { return 0; } return 1; }",
    );
    let out = case.cli(&["check", "input.zen", "--target", TARGET]);
    assert!(!out.status.success());
    let stderr = String::from_utf8_lossy(&out.stderr);
    assert!(stderr.contains("expected str"), "{stderr}");
    assert!(stderr.contains("input.zen:"), "{stderr}");
}
