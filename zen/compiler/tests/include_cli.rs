//! CLI acceptance tests for textual `use "path.zen";` includes (TASK-912).

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
            "zen-include-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&path).unwrap();
        Self(path)
    }
    fn write(&self, relative: &str, source: &str) -> &Self {
        let path = self.0.join(relative);
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).unwrap();
        }
        fs::write(path, source).unwrap();
        self
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

fn failure(out: &Output) -> String {
    assert!(
        !out.status.success(),
        "unexpected success\nstdout={}\nstderr={}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
    String::from_utf8_lossy(&out.stderr).into_owned()
}

const EXAMPLE_STDOUT: &[u8] = b"min_u64(42, 7) = 7
max_u64(42, 7) = 42
clamp_u64(120, 10, 99) = 99
clamp_u64(5, 10, 99) = 10
clamp_u64(50, 10, 99) = 50
abs_diff_u64(9, 4) = 5
abs_diff_u64(4, 9) = 5
is_even(42) = true
is_even(7) = false
is_odd(7) = true
gcd_u64(84, 30) = 6
use std ok
";

#[test]
fn simple_include_adds_functions_textually() {
    let case = Case::new();
    case.write(
        "lib.zen",
        "pub fn triple(n: u64) -> u64 { return n * 3; }\n",
    );
    case.write(
        "input.zen",
        "use \"lib.zen\";\n\nfn main() -> i32 {\n    print_uint(triple(14));\n    print(\"\\n\");\n    return 0;\n}\n",
    );
    let out = case.cli(&["run", "input.zen"]);
    success(&out);
    assert_eq!(out.stdout, b"42\n");
    let out = case.cli(&["check", "input.zen"]);
    success(&out);
    assert!(String::from_utf8_lossy(&out.stdout).contains("Checked"));
}

#[test]
fn nested_includes_expand_before_the_including_items() {
    let case = Case::new();
    case.write("inner.zen", "pub fn inner() -> u64 { return 3; }\n");
    case.write(
        "outer.zen",
        "use \"inner.zen\";\npub fn outer() -> u64 { return inner() + 1; }\n",
    );
    case.write(
        "input.zen",
        "use \"outer.zen\";\nfn main() -> i32 { print_uint(outer()); return 0; }\n",
    );
    let out = case.cli(&["run", "input.zen"]);
    success(&out);
    assert_eq!(out.stdout, b"4");
}

#[test]
fn include_paths_are_relative_to_the_including_file() {
    let case = Case::new();
    case.write("base.zen", "pub fn base() -> u64 { return 10; }\n");
    case.write("sub/two.zen", "pub fn two() -> u64 { return 5; }\n");
    case.write(
        "sub/one.zen",
        "use \"../base.zen\";\nuse \"two.zen\";\npub fn one() -> u64 { return base() + two(); }\n",
    );
    case.write(
        "input.zen",
        "use \"sub/one.zen\";\nfn main() -> i32 { print_uint(one()); return 0; }\n",
    );
    let out = case.cli(&["run", "input.zen"]);
    success(&out);
    assert_eq!(out.stdout, b"15");
}

#[test]
fn include_cycles_report_the_whole_chain() {
    let case = Case::new();
    case.write("a.zen", "use \"b.zen\";\npub fn a() -> u64 { return 1; }\n");
    case.write("b.zen", "use \"a.zen\";\npub fn b() -> u64 { return 2; }\n");
    case.write(
        "input.zen",
        "use \"a.zen\";\nfn main() -> i32 { return 0; }\n",
    );
    let stderr = failure(&case.cli(&["check", "input.zen"]));
    assert!(stderr.contains("cycle"), "{stderr}");
    assert!(stderr.contains("a.zen"), "{stderr}");
    assert!(stderr.contains("b.zen"), "{stderr}");
    assert!(stderr.contains("->"), "{stderr}");
}

#[test]
fn missing_include_reports_the_resolved_path() {
    let case = Case::new();
    case.write(
        "input.zen",
        "use \"does_not_exist.zen\";\nfn main() -> i32 { return 0; }\n",
    );
    let stderr = failure(&case.cli(&["check", "input.zen"]));
    assert!(stderr.contains("does_not_exist.zen"), "{stderr}");
    assert!(stderr.contains("input.zen:1"), "{stderr}");
    assert!(stderr.contains("cannot include"), "{stderr}");
}

#[test]
fn include_depth_is_limited_to_sixteen_edges() {
    // root -> l0 .. l16 is seventeen edges and must fail.
    let deep = Case::new();
    for index in 0..18u32 {
        let source = if index < 17 {
            format!(
                "use \"l{}.zen\";\npub fn f{index}() -> u64 {{ return {index}; }}\n",
                index + 1
            )
        } else {
            format!("pub fn f{index}() -> u64 {{ return {index}; }}\n")
        };
        deep.write(&format!("l{index}.zen"), &source);
    }
    deep.write(
        "input.zen",
        "use \"l0.zen\";\nfn main() -> i32 { return 0; }\n",
    );
    let stderr = failure(&deep.cli(&["check", "input.zen"]));
    assert!(stderr.contains("depth"), "{stderr}");
    assert!(stderr.contains("16"), "{stderr}");

    // root -> l0 .. l15 is exactly sixteen edges and must pass.
    let allowed = Case::new();
    for index in 0..16u32 {
        let source = if index < 15 {
            format!(
                "use \"l{}.zen\";\npub fn f{index}() -> u64 {{ return {index}; }}\n",
                index + 1
            )
        } else {
            format!("pub fn f{index}() -> u64 {{ return {index}; }}\n")
        };
        allowed.write(&format!("l{index}.zen"), &source);
    }
    allowed.write(
        "input.zen",
        "use \"l0.zen\";\nfn main() -> i32 { return 0; }\n",
    );
    success(&allowed.cli(&["check", "input.zen"]));
}

#[test]
fn duplicate_canonical_includes_expand_only_once() {
    let case = Case::new();
    case.write("lib.zen", "pub fn shared() -> u64 { return 7; }\n");
    case.write(
        "a.zen",
        "use \"lib.zen\";\npub fn a() -> u64 { return shared(); }\n",
    );
    case.write(
        "b.zen",
        "use \"lib.zen\";\npub fn b() -> u64 { return shared(); }\n",
    );
    // The same canonical file arrives through a, through b and directly,
    // including a non-canonical spelling. It must be defined only once.
    case.write(
        "input.zen",
        "use \"a.zen\";\nuse \"b.zen\";\nuse \"./lib.zen\";\nfn main() -> i32 { print_uint(a() + b() + shared()); return 0; }\n",
    );
    let out = case.cli(&["run", "input.zen"]);
    success(&out);
    assert_eq!(out.stdout, b"21");
}

#[test]
fn errors_inside_included_files_name_the_included_path() {
    let case = Case::new();
    case.write("bad.zen", "pub fn broken() -> i32 { return true; }\n");
    case.write(
        "input.zen",
        "use \"bad.zen\";\nfn main() -> i32 { return 0; }\n",
    );
    let stderr = failure(&case.cli(&["check", "input.zen"]));
    assert!(stderr.contains("bad.zen:"), "{stderr}");
    assert!(stderr.contains("type mismatch"), "{stderr}");
    assert!(!stderr.contains("panicked"), "{stderr}");
}

#[test]
fn use_after_items_is_rejected() {
    let case = Case::new();
    case.write("lib.zen", "pub fn helper() -> u64 { return 1; }\n");
    case.write(
        "input.zen",
        "fn main() -> i32 { return 0; }\nuse \"lib.zen\";\n",
    );
    let stderr = failure(&case.cli(&["check", "input.zen"]));
    assert!(stderr.contains("before any item"), "{stderr}");
    assert!(stderr.contains("input.zen:2"), "{stderr}");
}

#[test]
fn distributed_example_builds_checks_and_runs() {
    let case = Case::new();
    case.write("std/core.zen", include_str!("../../std/core.zen"));
    case.write(
        "examples/use_std.zen",
        include_str!("../../examples/use_std.zen"),
    );

    let checked = case.cli(&["check", "examples/use_std.zen"]);
    success(&checked);
    assert!(String::from_utf8_lossy(&checked.stdout).contains("use_std.zen"));

    let run = case.cli(&["run", "examples/use_std.zen"]);
    success(&run);
    assert_eq!(run.stdout, EXAMPLE_STDOUT);

    let build = case.cli(&["build", "examples/use_std.zen", "-o", "use_std_program"]);
    success(&build);
    let built = Command::new(case.0.join("use_std_program"))
        .output()
        .unwrap();
    success(&built);
    assert_eq!(built.stdout, EXAMPLE_STDOUT);
}
