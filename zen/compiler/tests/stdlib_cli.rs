//! TASK-901A: bootstrap stdlib string builtins (`str_eq`, `str_cmp`, `str_find`)
//! checked through the real CLI, hosted and freestanding.
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
            "zen-stdlib-{}-{}",
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
eq zen zen = true
eq zen zen-space = false
eq empty empty = true
eq nul-a nul-b = false
cmp abc abd = -1
cmp abd abc = 1
cmp abc abc = 0
cmp ab abc = -1
cmp empty x = -1
find banana na = 2
find banana ba = 0
find banana ana = 1
find banana z = -1
find banana empty = 0
find empty x = -1
stdlib ok
";

#[test]
fn hosted_str_eq_compares_bytes_and_lengths() {
    run_both(
        r#"
fn show(v: bool) -> void { if v { print("1"); } else { print("0"); } print("\n"); }
fn main() -> i32 {
    show(str_eq("zen", "zen"));
    show(str_eq("zen", "zen "));
    show(str_eq("", ""));
    show(str_eq("a\0b", "a\0b"));
    show(str_eq("a\0b", "a\0c"));
    show(str_eq("é", "é"));
    return 0;
}
"#,
        b"1\n0\n1\n1\n0\n1\n",
    );
}

#[test]
fn hosted_str_cmp_is_unsigned_lexicographic() {
    run_both(
        r#"
fn show(a: str, b: str) -> void { print_int(str_cmp(a, b) as i64); print("\n"); }
fn main() -> i32 {
    show("abc", "abd");
    show("abd", "abc");
    show("abc", "abc");
    show("ab", "abc");
    show("abc", "ab");
    show("", "");
    show("", "a");
    show("a", "");
    show("é", "z");
    show("a\0b", "a\0a");
    show("A", "a");
    return 0;
}
"#,
        b"-1\n1\n0\n-1\n1\n0\n-1\n1\n1\n1\n-1\n",
    );
}

#[test]
fn hosted_str_find_reports_first_byte_index() {
    run_both(
        r#"
fn show(a: str, b: str) -> void { print_int(str_find(a, b)); print("\n"); }
fn main() -> i32 {
    show("banana", "ba");
    show("banana", "na");
    show("banana", "ana");
    show("banana", "banana");
    show("banana", "bananas");
    show("banana", "z");
    show("banana", "");
    show("", "");
    show("", "x");
    show("aaaa", "aa");
    show("aaaa", "aaa");
    show("ababab", "abab");
    show("ababab", "bab");
    show("abc", "c");
    show("a\0b", "\0b");
    return 0;
}
"#,
        b"0\n2\n1\n0\n-1\n-1\n0\n0\n-1\n0\n0\n0\n1\n2\n1\n",
    );
}

#[test]
fn hosted_builtins_compose_with_variables_and_conditions() {
    run_both(
        r#"
fn main() -> i32 {
    let text: str = "zen stdlib";
    if str_eq(text, "zen stdlib")
        && str_find(text, "stdlib") == 4
        && str_cmp(text, "zen stdlib") == 0
        && !str_eq(text, "zen")
    {
        print("composed\n");
        return 0;
    }
    return 1;
}
"#,
        b"composed\n",
    );
}

#[test]
fn hosted_example_file_runs_with_expected_output() {
    let example = concat!(env!("CARGO_MANIFEST_DIR"), "/../examples/stdlib.zen");
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
    for name in ["str_eq", "str_cmp", "str_find"] {
        let source = format!(
            "fn {name}(a: str, b: str) -> bool {{ return true; }}\nfn main() -> i32 {{ return 0; }}"
        );
        reject(&source, &["duplicate or reserved function", name]);
    }
}

#[test]
fn local_bindings_may_shadow_builtin_value_names() {
    // Only function definitions are reserved: a local may reuse the identifier,
    // while `name(...)` still resolves to the builtin signature.
    run_both(
        r#"
fn main() -> i32 {
    let str_find: u64 = 7;
    let str_eq: bool = true;
    if str_eq && str_find == 7 && str_eq("zen", "zen") {
        print("shadow ok\n");
    }
    return 0;
}
"#,
        b"shadow ok\n",
    );
}

#[test]
fn rejects_non_string_arguments_in_both_modes() {
    for expression in [
        "let x: bool = str_eq(\"a\", 1);",
        "let x: bool = str_eq(1, \"a\");",
        "let x: i32 = str_cmp(\"a\", true);",
        "let x: i64 = str_find(\"a\", 1u64);",
    ] {
        reject(
            &format!("fn main() -> i32 {{ {expression} return 0; }}"),
            &["type mismatch", "expected str"],
        );
    }
    for (expression, needles) in [
        (
            "let x: i32 = str_eq(\"a\", \"a\");",
            &["expected i32", "found bool"][..],
        ),
        (
            "let x: i64 = str_cmp(\"a\", \"a\");",
            &["expected i64", "found i32"][..],
        ),
        (
            "let x: bool = str_find(\"a\", \"a\");",
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
        "let x: bool = str_eq(\"a\");",
        "let x: bool = str_eq(\"a\", \"b\", \"c\");",
        "let x: i32 = str_cmp();",
        "let x: i64 = str_find(\"a\");",
        "let x: i64 = str_find(\"a\", \"b\", \"c\");",
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
    if str_eq("a", "a") && str_cmp("a", "b") == -1 && str_find("abc", "bc") == 1 {
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
            "static bool __zen_str_eq(",
            "static int32_t __zen_str_cmp(",
            "static int64_t __zen_str_find(",
        ] {
            assert!(c.contains(helper), "missing {helper:?} in {name}");
        }
        for forbidden in [
            "#include <string.h>",
            "memcmp(",
            "memchr(",
            "memcpy(",
            "strcmp(",
            "strlen(",
            "strstr(",
            "malloc(",
        ] {
            assert!(!c.contains(forbidden), "found {forbidden:?} in {name}");
        }
        if name == "free.c" {
            // Helpers must stay libc-free; hosted prelude only pulls libc for print.
            for forbidden in ["#include <stdio.h>", "#include <stdlib.h>"] {
                assert!(!c.contains(forbidden), "found {forbidden:?} in {name}");
            }
        }
    }
    let hosted = fs::read_to_string(case.0.join("hosted.c")).unwrap();
    assert!(!hosted.contains("__asm__(\"str_eq\")"));
    let free = fs::read_to_string(case.0.join("free.c")).unwrap();
    assert!(!free.contains("int main(void)"));
    assert!(!free.contains("__zen_print("));
}

#[test]
fn freestanding_probe_matches_hosted_semantics() {
    let case = Case::new(
        r#"
pub fn probe() -> i32 {
    if !str_eq("zen", "zen") { return 1; }
    if str_eq("zen", "zen ") { return 2; }
    if str_cmp("abc", "abd") != -1 { return 3; }
    if str_cmp("é", "z") != 1 { return 4; }
    if str_cmp("abc", "abc") != 0 { return 5; }
    if str_find("banana", "ana") != 1 { return 6; }
    if str_find("banana", "") != 0 { return 7; }
    if str_find("banana", "z") != -1 { return 8; }
    if str_find("", "z") != -1 { return 9; }
    if str_find("abc", "abc") != 0 { return 10; }
    if str_find("abc", "abcx") != -1 { return 11; }
    if str_len("zen") != 3 { return 12; }
    if str_byte("zen", 1) != 101u8 { return 13; }
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
    printf("freestanding-ok\n");
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
    assert_eq!(run.stdout, b"freestanding-ok\n");
}

#[test]
fn freestanding_rejects_non_string_arguments() {
    let case = Case::new("pub fn probe() -> i32 { if str_eq(\"a\", 1) { return 0; } return 1; }");
    let out = case.cli(&["check", "input.zen", "--target", TARGET]);
    assert!(!out.status.success());
    let stderr = String::from_utf8_lossy(&out.stderr);
    assert!(stderr.contains("expected str"), "{stderr}");
    assert!(stderr.contains("input.zen:"), "{stderr}");
}
