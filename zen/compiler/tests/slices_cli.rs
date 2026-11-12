//! CLI-level acceptance tests for `[u64]` slice parameters (TASK-915).
//!
//! Slices are borrowed (pointer + runtime length) views produced from a local
//! `[u64; N]` array or another slice. These tests exercise reads and writes,
//! runtime bounds checks, length-0 views, the distributed array stdlib and the
//! freestanding codegen path.
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
            "zen-slices-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&path).unwrap();
        fs::write(path.join("input.zen"), source).unwrap();
        Self(path)
    }
    fn write(&self, relative: &str, contents: &str) {
        let path = self.0.join(relative);
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).unwrap();
        }
        fs::write(path, contents).unwrap();
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
    fn program(&self, name: &str) -> Output {
        Command::new(self.0.join(name)).current_dir(&self.0).output().unwrap()
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
        assert_eq!(
            out.stdout,
            expected,
            "unexpected output with {args:?}: {}",
            String::from_utf8_lossy(&out.stdout)
        );
    }
}
fn reject(source: &str) {
    let case = Case::new(source);
    for args in [
        vec!["check", "input.zen"],
        vec!["check", "input.zen", "--target", TARGET],
    ] {
        let out = case.cli(&args);
        assert!(
            !out.status.success(),
            "accepted invalid slice source with {args:?}: {source}"
        );
        let stderr = String::from_utf8_lossy(&out.stderr);
        assert!(
            stderr.contains("error") && stderr.contains("input.zen:"),
            "missing localized diagnostic for {source}: {stderr}"
        );
        assert!(!stderr.contains("panicked"), "{stderr}");
    }
}

#[test]
fn slices_read_sum_max_and_contains_over_arrays() {
    run_both(
        r#"
fn sum(s: [u64]) -> u64 {
    let n: u64 = slice_len(s);
    let mut total: u64 = 0;
    let mut i: u64 = 0;
    while i < n {
        total += s[i];
        i += 1;
    }
    return total;
}
fn max(s: [u64]) -> u64 {
    let mut best: u64 = s[0];
    let mut i: u64 = 1;
    while i < slice_len(s) {
        if s[i] > best { best = s[i]; }
        i += 1;
    }
    return best;
}
fn has(s: [u64], value: u64) -> bool {
    let mut i: u64 = 0;
    while i < slice_len(s) {
        if s[i] == value { return true; }
        i += 1;
    }
    return false;
}
fn main() -> i32 {
    let a: [u64; 4] = [10, 20, 30, 40];
    let b: [u64; 2] = [7, 9];
    print_uint(sum(a));
    print(" ");
    print_uint(sum(b));
    print(" ");
    print_uint(max(a));
    print(" ");
    if has(a, 30) { print("yes"); } else { print("no"); }
    print(" ");
    if has(a, 31) { print("yes"); } else { print("no"); }
    print(" ");
    print_uint(slice_len(a));
    print("\n");
    return 0;
}
"#,
        b"100 16 40 yes no 4\n",
    );
}

#[test]
fn slice_writes_mutate_the_caller_array_through_forwarded_slices() {
    run_both(
        r#"
fn bump(s: [u64]) -> void {
    let mut i: u64 = 0;
    while i < slice_len(s) {
        s[i] += 1;
        i += 1;
    }
}
fn bump_twice(s: [u64]) -> void {
    bump(s);
    bump(s);
}
fn reverse(s: [u64]) -> void {
    let n: u64 = slice_len(s);
    let mut i: u64 = 0;
    while i < n / 2 {
        let j: u64 = n - 1 - i;
        let tmp: u64 = s[i];
        s[i] = s[j];
        s[j] = tmp;
        i += 1;
    }
}
fn main() -> i32 {
    let mut a: [u64; 4] = [1, 2, 3, 4];
    bump_twice(a);
    print_uint(a[0]);
    print(" ");
    print_uint(a[3]);
    print(" ");
    reverse(a);
    print_uint(a[0]);
    print(" ");
    print_uint(a[1]);
    print(" ");
    print_uint(a[2]);
    print(" ");
    print_uint(a[3]);
    print("\n");
    return 0;
}
"#,
        b"3 6 6 5 4 3\n",
    );
}

#[test]
fn one_slice_parameter_accepts_arrays_of_different_lengths() {
    run_both(
        r#"
fn total(s: [u64]) -> u64 {
    let mut total: u64 = 0;
    let mut i: u64 = 0;
    while i < slice_len(s) {
        total += s[i];
        i += 1;
    }
    return total;
}
fn relay(s: [u64]) -> u64 {
    return total(s);
}
fn main() -> i32 {
    let a: [u64; 1] = [7];
    let b: [u64; 2] = [1, 2];
    let c: [u64; 7] = [1, 2, 3, 4, 5, 6, 7];
    print_uint(total(a));
    print(" ");
    print_uint(total(b));
    print(" ");
    print_uint(relay(c));
    print(" ");
    print_uint(slice_len(c));
    print(" ");
    print_uint(slice_len(b));
    print("\n");
    return 0;
}
"#,
        b"7 3 28 7 2\n",
    );
}

#[test]
fn slice_index_and_rhs_are_evaluated_once_in_source_order() {
    run_both(
        r#"
fn idx() -> u64 { print("i"); return 1; }
fn val() -> u64 { print("v"); return 7; }
fn write(s: [u64]) -> void { s[idx()] = val(); }
fn read(s: [u64]) -> u64 { return s[idx()]; }
fn main() -> i32 {
    let mut a: [u64; 3] = [1, 2, 3];
    write(a);
    print_uint(read(a));
    write(a);
    print_uint(a[1]);
    print("\n");
    return 0;
}
"#,
        b"ivi7iv7\n",
    );
}

#[test]
fn out_of_bounds_slice_access_traps_at_runtime_in_both_modes() {
    for source in [
        r#"fn at(s: [u64], i: u64) -> u64 { return s[i]; } fn main() -> i32 { let a: [u64; 3] = [1; 3]; print_uint(at(a, 3)); return 0; }"#,
        r#"fn at(s: [u64], i: u64) -> u64 { return s[i]; } fn main() -> i32 { let a: [u64; 3] = [1; 3]; print_uint(at(a, 18446744073709551615)); return 0; }"#,
        r#"fn put(s: [u64], i: u64, v: u64) -> void { s[i] = v; } fn main() -> i32 { let mut a: [u64; 3] = [1; 3]; put(a, 3, 9); return 0; }"#,
        r#"fn at(s: [u64], i: u64) -> u64 { return s[i]; } fn main() -> i32 { let a: [u64; 3] = [1; 3]; let i: i32 = -1; print_uint(at(a, i as u64)); return 0; }"#,
        r#"fn bump(s: [u64]) -> void { let mut i: u64 = 0; while i <= slice_len(s) { s[i] += 1; i += 1; } } fn main() -> i32 { let mut a: [u64; 2] = [1; 2]; bump(a); return 0; }"#,
    ] {
        let case = Case::new(source);
        // Bounds are a runtime property: the checker must accept the program.
        success(&case.cli(&["check", "input.zen"]));
        for release in [false, true] {
            let mut args = vec!["run", "input.zen"];
            if release {
                args.push("--release");
            }
            let out = case.cli(&args);
            assert!(
                !out.status.success(),
                "out-of-bounds slice access succeeded (release={release}): {source}"
            );
            let stderr = String::from_utf8_lossy(&out.stderr);
            assert!(
                stderr.contains("array index out of bounds"),
                "missing runtime bounds diagnostic: {stderr}"
            );
            assert!(!stderr.contains("panicked"), "{stderr}");
        }
    }
}

#[test]
fn zero_length_slice_sums_to_zero_and_any_index_traps() {
    let case = Case::new(
        r#"
fn sum_empty(s: [u64]) -> u64 {
    let mut total: u64 = 0;
    let mut i: u64 = 0;
    while i < slice_len(s) {
        total += s[i];
        i += 1;
    }
    return total;
}
fn first(s: [u64]) -> u64 {
    return s[0];
}
"#,
    );
    success(&case.cli(&[
        "build",
        "input.zen",
        "--target",
        TARGET,
        "--emit",
        "c",
        "-o",
        "program.c",
    ]));
    let c = fs::read_to_string(case.0.join("program.c")).unwrap();
    assert!(c.contains("static uint64_t __zen_f0("), "{c}");
    assert!(c.contains("static uint64_t __zen_f1("), "{c}");
    // Freestanding code keeps both helpers internal; a hand-written C harness
    // can build the only slice the MVP cannot construct in Zen: length 0.
    let harness = |name: &str, main: &str| {
        case.write(&format!("{name}.c"), &format!("{c}\n{main}\n"));
        success(&case.tool(
            "cc",
            &["-std=c11", &format!("{name}.c"), "-o", name],
        ));
        case.program(name)
    };
    let sum = harness(
        "sum_empty",
        "#include <stdint.h>\nint main(void) { __zen_slice_u64 empty = {0, 0}; return __zen_f0(empty) == 0 ? 0 : 1; }",
    );
    success(&sum);
    let first = harness(
        "first_empty",
        "#include <stdint.h>\nint main(void) { __zen_slice_u64 empty = {0, 0}; return (int)__zen_f1(empty); }",
    );
    assert!(
        !first.status.success(),
        "indexing a zero-length slice must trap"
    );
}

#[test]
fn rejects_slices_outside_parameters_and_whole_slice_values() {
    for source in [
        // Slices are parameter-only: no locals, no retained views.
        "fn f(s: [u64]) -> u64 { let t: [u64] = s; return 0; } fn main() -> i32 { return 0; }",
        "fn f(s: [u64]) -> u64 { let t = s; return 0; } fn main() -> i32 { return 0; }",
        "fn f(s: [u64]) -> u64 { s = 1; return 0; } fn main() -> i32 { return 0; }",
        "fn f(s: [u64]) -> u64 { return s; } fn main() -> i32 { return 0; }",
        // No whole-value copies, comparisons, casts or prints.
        "fn f(s: [u64]) -> u64 { if s == s { return 1; } return 0; } fn main() -> i32 { return 0; }",
        "fn f(s: [u64]) -> u64 { return s as u64; } fn main() -> i32 { return 0; }",
        "fn f(s: [u64]) -> u64 { print_uint(s); return 0; } fn main() -> i32 { return 0; }",
        // A scalar parameter does not accept a slice as a whole value.
        "fn g(x: u64) -> u64 { return x; } fn f(s: [u64]) -> u64 { return g(s); } fn main() -> i32 { return 0; }",
        // Slices cannot be returned or stored in structs.
        "fn f(s: [u64]) -> [u64] { return s; } fn main() -> i32 { return 0; }",
        "struct Box { items: [u64] } fn main() -> i32 { return 0; }",
        // Only u64 slices exist, and only u64 arrays can produce them.
        "fn f(s: [u32]) -> u64 { return 0; } fn main() -> i32 { return 0; }",
        "fn f(s: [bool]) -> u64 { return 0; } fn main() -> i32 { return 0; }",
        // Slice parameters are not C ABI exports.
        "pub fn f(s: [u64]) -> u64 { return slice_len(s); }",
        "extern \"C\" { fn f(s: [u64]); } pub fn g() -> u64 { return 0; }",
    ] {
        reject(source);
    }
}

#[test]
fn rejects_invalid_slice_arguments_and_builtin_uses() {
    for source in [
        // Arguments need a local array or another slice.
        "fn f(s: [u64]) -> u64 { return 0; } fn main() -> i32 { print_uint(f([1, 2])); return 0; }",
        "fn f(s: [u64]) -> u64 { return 0; } fn main() -> i32 { let x: u64 = 1; print_uint(f(x)); return 0; }",
        "fn f(s: [u64]) -> u64 { return 0; } fn main() -> i32 { let a: [u64; 2] = [1; 2]; let b = a[0]; print_uint(f(b)); return 0; }",
        // Array element types must match u64 exactly.
        "fn main() -> i32 { let a: [u8; 2] = [1, 2]; print_uint(slice_len(a)); return 0; }",
        "fn main() -> i32 { let a: [i64; 2] = [1, 2]; print_uint(slice_len(a)); return 0; }",
        // slice_len is a fixed-arity builtin over [u64].
        "fn main() -> i32 { print_uint(slice_len()); return 0; }",
        "fn main() -> i32 { print_uint(slice_len(5)); return 0; }",
        "fn main() -> i32 { let a: [u64; 2] = [1; 2]; print_uint(slice_len(a, 1)); return 0; }",
        "fn main() -> i32 { let a: [u64; 2] = [1; 2]; let x: u64 = slice_len(a) as u64; let y: bool = slice_len(a); return 0; }",
        // Indexing a slice still requires a numeric index.
        "fn f(s: [u64]) -> u64 { return s[true]; } fn main() -> i32 { return 0; }",
        // slice_len is a reserved function name.
        "fn slice_len(s: u64) -> u64 { return s; } fn main() -> i32 { return 0; }",
    ] {
        reject(source);
    }
}

#[test]
fn freestanding_slice_codegen_is_libc_free_and_has_no_undefined_symbols() {
    let case = Case::new(
        r#"
fn sum_slice(s: [u64]) -> u64 {
    let mut total: u64 = 0;
    let mut i: u64 = 0;
    while i < slice_len(s) {
        total += s[i];
        i += 1;
    }
    return total;
}
pub fn answer() -> u64 {
    let a: [u64; 3] = [10, 20, 12];
    return sum_slice(a);
}
"#,
    );
    for release in [false, true] {
        let mut args = vec![
            "build",
            "input.zen",
            "--target",
            TARGET,
            "--emit",
            "obj",
            "-o",
            "program.o",
        ];
        if release {
            args.push("--release");
        }
        success(&case.cli(&args));
        let undefined = case.tool("nm", &["-u", "program.o"]);
        success(&undefined);
        assert!(
            String::from_utf8_lossy(&undefined.stdout).trim().is_empty(),
            "undefined symbols: {}",
            String::from_utf8_lossy(&undefined.stdout)
        );
    }
    success(&case.cli(&[
        "build",
        "input.zen",
        "--target",
        TARGET,
        "--emit",
        "c",
        "-o",
        "program.c",
    ]));
    let c = fs::read_to_string(case.0.join("program.c")).unwrap();
    assert!(
        c.contains("typedef struct { uint64_t *data; uint64_t len; } __zen_slice_u64;"),
        "{c}"
    );
    assert!(c.contains("static uint64_t __zen_slice_len(__zen_slice_u64 s)"), "{c}");
    assert!(c.contains("__zen_index_check((uint64_t)(__zen_v"), "{c}");
    assert!(c.contains(", __zen_v0.len)"), "{c}");
    assert!(
        c.contains("(__zen_slice_u64){(uint64_t *)__zen_v0, UINT64_C(3)}"),
        "{c}"
    );
    assert!(c.contains("__zen_v0.data[__zen_v"), "{c}");
    for forbidden in [
        "#include <stdio.h>",
        "#include <stdlib.h>",
        "#include <string.h>",
        "memcpy(",
        "malloc(",
        "int main(",
    ] {
        assert!(!c.contains(forbidden), "found {forbidden:?}");
    }
}

#[test]
fn stdlib_array_module_is_distributed_with_use_and_runs() {
    let case = Case::new("");
    case.write("std/array.zen", include_str!("../../std/array.zen"));
    case.write(
        "main.zen",
        r#"
use "std/array.zen";

fn main() -> i32 {
    let mut a: [u64; 5] = [4, 1, 3, 1, 5];
    print_uint(sum_slice(a));
    print(" ");
    print_uint(max_slice(a));
    print(" ");
    if contains_slice(a, 3) { print("yes"); } else { print("no"); }
    print(" ");
    reverse_slice(a);
    print_uint(a[0]);
    print(" ");
    sort_slice(a);
    print_uint(a[0]);
    print_uint(a[4]);
    print("\n");
    let b: [u64; 2] = [8, 9];
    print_uint(sum_slice(b));
    print(" ");
    print_uint(slice_len(b));
    print("\n");
    return 0;
}
"#,
    );
    for args in [
        vec!["run", "main.zen"],
        vec!["run", "main.zen", "--release"],
    ] {
        let out = case.cli(&args);
        success(&out);
        assert_eq!(
            out.stdout, b"14 5 yes 5 15\n17 2\n",
            "unexpected stdlib output with {args:?}: {}",
            String::from_utf8_lossy(&out.stdout)
        );
    }
    // The checked program also builds and runs as a native executable.
    success(&case.cli(&["build", "main.zen", "-o", "array_program"]));
    let built = case.program("array_program");
    success(&built);
    assert_eq!(built.stdout, b"14 5 yes 5 15\n17 2\n");

    // The same textual include works in freestanding code: the stdlib helpers
    // stay internal because slices are not part of the C ABI.
    case.write(
        "free.zen",
        r#"
use "std/array.zen";

pub fn answer() -> u64 {
    let mut a: [u64; 4] = [4, 1, 3, 2];
    sort_slice(a);
    reverse_slice(a);
    if !contains_slice(a, 3) {
        return 0;
    }
    return sum_slice(a);
}
"#,
    );
    success(&case.cli(&["check", "free.zen", "--target", TARGET]));
    success(&case.cli(&[
        "build",
        "free.zen",
        "--target",
        TARGET,
        "--emit",
        "c",
        "-o",
        "free.c",
    ]));
    let free = fs::read_to_string(case.0.join("free.c")).unwrap();
    assert!(!free.contains("__asm__(\"sort_slice\")"), "{free}");
    assert!(!free.contains("int main("), "{free}");
}

#[test]
fn slices_example_runs_with_documented_output() {
    let example = concat!(env!("CARGO_MANIFEST_DIR"), "/../examples/slices.zen");
    let expected = "values=42 7 19 42 3 88\n\
len=6\n\
sum=201\n\
max=88\n\
contains 19 = true\n\
contains 50 = false\n\
reversed=88 3 42 19 7 42\n\
sorted=3 7 19 42 42 88\n\
small_sum=10\n\
small_max=5\n\
small_sorted=1 4 5\n\
slices ok\n";
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
        assert_eq!(
            out.stdout,
            expected.as_bytes(),
            "unexpected example output: {}",
            String::from_utf8_lossy(&out.stdout)
        );
        assert_eq!(out.status.code(), Some(0));
    }
}

#[test]
fn slice_compound_assignment_and_shift_helpers_stay_checked() {
    run_both(
        r#"
fn scale(s: [u64], factor: u64) -> void {
    let mut i: u64 = 0;
    while i < slice_len(s) {
        s[i] *= factor;
        s[i] += 1;
        s[i] -= 1;
        s[i] <<= 1;
        s[i] >>= 1;
        i += 1;
    }
}
fn main() -> i32 {
    let mut a: [u64; 3] = [2, 3, 4];
    scale(a, 3);
    print_uint(a[0]);
    print(" ");
    print_uint(a[1]);
    print(" ");
    print_uint(a[2]);
    print("\n");
    return 0;
}
"#,
        b"6 9 12\n",
    );
}
