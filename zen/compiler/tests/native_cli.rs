use std::{
    fs,
    path::PathBuf,
    process::{Command, Output},
    sync::atomic::{AtomicU64, Ordering},
};
static NEXT: AtomicU64 = AtomicU64::new(0);
struct Case(PathBuf);
impl Case {
    fn new(source: &str) -> Self {
        let path = std::env::temp_dir().join(format!(
            "zen-acceptance-{}-{}",
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
#[test]
fn hello_builds_a_native_elf() {
    let case = Case::new(include_str!("../../examples/hello.zen"));
    let out = case.cli(&["build", "input.zen", "-o", "hello binary"]);
    success(&out);
    let binary = case.0.join("hello binary");
    assert_eq!(&fs::read(&binary).unwrap()[..4], b"\x7fELF");
    let out = Command::new(&binary).output().unwrap();
    success(&out);
    assert_eq!(out.stdout, b"Hello, Zen!\n");
}
#[test]
fn factorial_recursion() {
    run_both(
        include_str!("../../examples/factorial.zen"),
        b"factorial(10) = 3628800\n",
    );
}
#[test]
fn loops_mutability_shadowing_and_forward_calls() {
    run_both(
        r#"
fn main() -> i32 {
    let mut n: u64 = 0;
    let mut sum: u64 = 0;
    while n < 10 { sum += n; n += 1; }
    if sum == 45 { print_uint(twice(sum)); } else { return 1; }
    { let sum: u64 = 3; print_uint(sum); }
    print_uint(sum);
    return 0;
}
fn twice(n: u64) -> u64 { return n * 2; }
"#,
        b"90345",
    );
}
#[test]
fn short_circuit_and_left_to_right_calls() {
    run_both(
        r#"
fn side() -> bool { print("bad"); return true; }
fn a() -> i32 { print("a"); return 1; }
fn b() -> i32 { print("b"); return 2; }
fn combine(x: i32, y: i32) -> i32 { return x + y; }
fn main() -> i32 {
    if false && side() { return 1; }
    if true || side() { print("ok"); }
    let result: i32 = combine(a(), b());
    if result != 3 { return 2; }
    return 0;
}
"#,
        b"okab",
    );
}
#[test]
fn integers_c_names_and_embedded_nul_strings() {
    run_both(
        r#"
fn switch(int: u64) -> u64 { return int + 1; }
fn main() -> i32 {
    let printf: u64 = switch(18446744073709551615u64);
    print_uint(printf);
    let x: i64 = -42;
    print_int(x);
    print("\0é\n");
    return 0;
}
"#,
        "0-42\0é\n".as_bytes(),
    );
}
#[test]
fn run_propagates_program_exit_code() {
    let case = Case::new("fn main() -> i32 { return 37; }");
    let out = case.cli(&["run", "input.zen", "--", "argument"]);
    assert_eq!(out.status.code(), Some(37));
}
#[test]
fn check_needs_no_c_toolchain_and_creates_no_binary() {
    let case = Case::new("fn main() -> i32 { let n = 42; return n; }");
    let out = Command::new(env!("CARGO_BIN_EXE_zen"))
        .current_dir(&case.0)
        .env("CC", "/missing-zen-cc")
        .args(["check", "input.zen"])
        .output()
        .unwrap();
    success(&out);
    assert!(!case.0.join("input").exists());
}
#[test]
fn reject_invalid_sources_with_located_errors() {
    for source in [
        "fn main() -> i32 { return missing; }",
        "fn main() -> i32 { let n: bool = 1; return 0; }",
        "fn main() -> i32 { let n = 1; n = 2; return n; }",
        "fn main() -> i32 { if true { return 0; } }",
        "fn main() -> i32 { return true; }",
        "fn main() -> i32 { return 2147483648; }",
        "fn main() -> i32 { print_uint(); return 0; }",
        "fn main() -> i32 { print(3); return 0; }",
        "fn main() -> i32 { let x = print(\"hi\"); return 0; }",
        "fn main() -> i32 { return 0; } fn main() -> i32 { return 1; }",
        "fn main(x: i32) -> i32 { return x; }",
        "fn foo() -> i32 { return 0; }",
        "fn main() -> i32 { return 0x; }",
        "fn main() -> i32 { return 1garbage; }",
        "fn main() -> i32 { return 340282366920938463463374607431768211456; }",
        "fn main() -> i32 { print(\"\\q\"); return 0; }",
        "fn main() -> i32 { print(\"unterminated",
        "fn main() -> i32 { return 0; } /*",
        "struct S {} fn main() -> i32 { return 0; }",
        "fn main() -> i32 { let x: f64 = 1.0; return 0; }",
    ] {
        let case = Case::new(source);
        let out = case.cli(&["check", "input.zen"]);
        assert!(!out.status.success(), "accepted invalid source: {source}");
        let stderr = String::from_utf8_lossy(&out.stderr);
        assert!(
            stderr.contains("error") && stderr.contains("input.zen:"),
            "missing diagnostic for {source}: {stderr}"
        );
        assert!(!stderr.contains("panicked"), "{stderr}");
    }
}
#[test]
fn failed_build_preserves_existing_artifact_and_source() {
    let case = Case::new("fn main() -> i32 { return 0; }");
    let original = fs::read(case.0.join("input.zen")).unwrap();
    let out = case.cli(&["build", "input.zen", "-o", "./input.zen"]);
    assert!(!out.status.success());
    assert_eq!(fs::read(case.0.join("input.zen")).unwrap(), original);
    fs::write(case.0.join("previous"), "existing artifact").unwrap();
    let out = Command::new(env!("CARGO_BIN_EXE_zen"))
        .current_dir(&case.0)
        .env("CC", "false")
        .args(["build", "input.zen", "-o", "previous"])
        .output()
        .unwrap();
    assert!(!out.status.success());
    assert_eq!(
        fs::read_to_string(case.0.join("previous")).unwrap(),
        "existing artifact"
    );
    assert_eq!(fs::read_dir(&case.0).unwrap().count(), 2);
}
#[test]
fn arithmetic_errors_fail_in_native_program() {
    for expression in ["1 / 0", "1 % 0", "(-9223372036854775807i64 - 1i64) / -1i64"] {
        let case = Case::new(&format!(
            "fn main() -> i32 {{ let x = {expression}; return 0; }}"
        ));
        for release in [false, true] {
            let mut args = vec!["run", "input.zen"];
            if release {
                args.push("--release");
            }
            let out = case.cli(&args);
            assert!(
                !out.status.success(),
                "arithmetic error succeeded: {expression}"
            );
        }
    }
}

#[test]
fn hosted_public_functions_cannot_override_runtime_symbols() {
    run_both(
        r#"
pub fn printf(n:u64)->u64 { return n; }
pub fn fwrite()->u64 { return 3; }
pub fn main()->i32 {
    print_uint(42);
    print("hi");
    if printf(7) != 7 || fwrite() != 3 { return 1; }
    return 0;
}
"#,
        b"42hi",
    );
}
