//! CLI-level acceptance tests for fixed-size arrays in the Zen MVP subset.
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
            "zen-arrays-{}-{}",
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
    let out = case.cli(&["check", "input.zen"]);
    assert!(
        !out.status.success(),
        "accepted invalid array source: {source}"
    );
    let stderr = String::from_utf8_lossy(&out.stderr);
    assert!(
        stderr.contains("error") && stderr.contains("input.zen:"),
        "missing localized diagnostic for {source}: {stderr}"
    );
    assert!(!stderr.contains("panicked"), "{stderr}");
}

#[test]
fn fixed_arrays_support_literals_reads_writes_and_loops() {
    run_both(
        r#"
fn main() -> i32 {
    let mut a: [u64; 4] = [10, 20, 30, 40];
    let mut total: u64 = 0;
    let mut i: u64 = 0;
    while i < 4 {
        a[i] += 1;
        total += a[i];
        i += 1;
    }
    print_uint(total);
    print(" ");
    print_uint(a[0]);
    print(" ");
    print_uint(a[3]);
    print("\n");
    return 0;
}
"#,
        b"104 11 41\n",
    );
}

#[test]
fn array_repeat_and_every_scalar_element_type() {
    run_both(
        r#"
fn main() -> i32 {
    let mut a: [u8; 3] = [7; 3];
    let mut b: [u16; 2] = [65535, 1];
    let mut c: [u32; 1] = [4294967295];
    let mut d: [i32; 2] = [-2147483648, 2147483647];
    let mut e: [i64; 2] = [-9223372036854775808, 9223372036854775807];
    let mut f: [u64; 2] = [0, 18446744073709551615];
    let mut g: [bool; 2] = [true, false];
    a[1] *= 2;
    b[1] <<= 4;
    c[0] >>= 31;
    d[0] += 1;
    e[1] -= 1;
    f[1] += 1;
    g[0] = !g[0];
    print_uint(a[1] as u64);
    print(" ");
    print_uint(b[1] as u64);
    print(" ");
    print_uint(c[0] as u64);
    print(" ");
    print_int(d[0] as i64);
    print(" ");
    print_int(e[1]);
    print(" ");
    print_uint(f[1]);
    print(" ");
    if g[0] { print("T"); } else { print("F"); }
    print("\n");
    return 0;
}
"#,
        b"14 16 1 -2147483647 9223372036854775806 0 F\n",
    );
}

#[test]
fn array_index_and_repeated_value_are_evaluated_once_in_order() {
    run_both(
        r#"
fn side() -> u64 { print("s"); return 9; }
fn idx() -> u64 { print("i"); return 2; }
fn main() -> i32 {
    let mut h: [u64; 4] = [side(); 4];
    print_uint(h[0] + h[3]);
    h[idx()] = side();
    print_uint(h[idx()]);
    h[idx()] += 1;
    print_uint(h[idx()]);
    return 0;
}
"#,
        b"s18isi9ii10",
    );
}

#[test]
fn arrays_shadow_in_nested_blocks_and_loop_iterations() {
    run_both(
        r#"
fn main() -> i32 {
    let a: [u8; 2] = [1, 2];
    {
        let a: [u16; 2] = [10, 20];
        print_uint(a[0] as u64);
    }
    print_uint(a[1] as u64);
    let mut i: u64 = 0;
    while i < 2 {
        let mut temp: [u64; 2] = [i, i + 1];
        temp[1] += 10;
        print_uint(temp[1]);
        i += 1;
    }
    return 0;
}
"#,
        b"1021112",
    );
}

#[test]
fn unsigned_and_signed_index_types_are_accepted() {
    run_both(
        r#"
fn main() -> i32 {
    let a: [u64; 4] = [10, 20, 30, 40];
    let a8: u8 = 0;
    let a16: u16 = 1;
    let a32: u32 = 2;
    let s32: i32 = 3;
    let s64: i64 = 2;
    print_uint(a[a8]);
    print(" ");
    print_uint(a[a16]);
    print(" ");
    print_uint(a[a32]);
    print(" ");
    print_uint(a[s32]);
    print(" ");
    print_uint(a[s64]);
    print("\n");
    return 0;
}
"#,
        b"10 20 30 40 30\n",
    );
}

#[test]
fn array_index_chains_keep_resource_limits() {
    let case = Case::new(&format!(
        "fn main() -> i32 {{ let a: [u64; 2] = [1; 2]; let x = a{}; return 0; }}",
        "[0]".repeat(200)
    ));
    let out = case.cli(&["check", "input.zen"]);
    assert!(!out.status.success());
    let stderr = String::from_utf8_lossy(&out.stderr);
    assert!(stderr.contains("nesting limit"), "{stderr}");
    assert!(!stderr.contains("panicked"), "{stderr}");

    let case = Case::new(&format!(
        "fn main() -> i32 {{ let a = {}1{}; return 0; }}",
        "[".repeat(300),
        "]".repeat(300)
    ));
    let out = case.cli(&["check", "input.zen"]);
    assert!(!out.status.success());
    let stderr = String::from_utf8_lossy(&out.stderr);
    assert!(stderr.contains("nesting limit"), "{stderr}");
    assert!(!stderr.contains("panicked"), "{stderr}");
}

#[test]
fn out_of_bounds_array_access_fails_at_runtime_in_both_modes() {
    for source in [
        r#"fn main() -> i32 { let a: [u64; 3] = [1; 3]; let i: u64 = 3; print_uint(a[i]); return 0; }"#,
        r#"fn main() -> i32 { let a: [u64; 3] = [1; 3]; let i: u64 = 18446744073709551615; print_uint(a[i]); return 0; }"#,
        r#"fn main() -> i32 { let mut a: [u64; 3] = [1; 3]; a[3] = 9; return 0; }"#,
        r#"fn main() -> i32 { let a: [u64; 3] = [1; 3]; let i: i32 = -1; print_uint(a[i] as u64); return 0; }"#,
        r#"fn main() -> i32 { let a: [u64; 3] = [1; 3]; let i: i64 = -9223372036854775808; print_uint(a[i] as u64); return 0; }"#,
        r#"fn main() -> i32 { let a: [u64; 3] = [1; 3]; let mut i: u64 = 0; let mut total: u64 = 0; while i <= 3 { total += a[i]; i += 1; } print_uint(total); return 0; }"#,
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
                "out-of-bounds access succeeded (release={release}): {source}"
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
fn rejects_invalid_array_programs_with_localized_errors() {
    for source in [
        // Literal/repetition length must match the annotation exactly.
        "fn main() -> i32 { let mut a: [u64; 3] = [1, 2]; return 0; }",
        "fn main() -> i32 { let mut a: [u64; 3] = [1, 2, 3, 4]; return 0; }",
        "fn main() -> i32 { let mut a: [u64; 3] = [1; 4]; return 0; }",
        // Element types are exact, with no implicit coercions.
        "fn main() -> i32 { let a: [u64; 3] = [1, 2, 3u32]; return 0; }",
        "fn main() -> i32 { let a: [bool; 2] = [1, 0]; return 0; }",
        "fn main() -> i32 { let a: [u8; 2] = [255, 256]; return 0; }",
        "fn main() -> i32 { let a: [u8; 2] = [true; 2]; return 0; }",
        // Lengths are positive unsuffixed integer literals only.
        "fn main() -> i32 { let a: [u64; 0] = [1; 0]; return 0; }",
        "fn main() -> i32 { let a: [u64; -1] = [1; 1]; return 0; }",
        "fn main() -> i32 { let a: [u64; 3u64] = [1; 3]; return 0; }",
        "fn main() -> i32 { let a: [u64; 1 + 2] = [1; 3]; return 0; }",
        "fn main(n: u64) -> i32 { let a: [u64; n] = [1; 3]; return 0; }",
        "fn main() -> i32 { let a: [u64; 18446744073709551616] = [1; 1]; return 0; }",
        // Unsupported element types (strings, pointers, nested arrays).
        "fn main() -> i32 { let a: [str; 2] = [\"a\", \"b\"]; return 0; }",
        "fn main() -> i32 { let a: [*u8; 2] = [1; 2]; return 0; }",
        "fn main() -> i32 { let a: [[u8; 2]; 2] = [[1, 2], [3, 4]]; return 0; }",
        "fn main() -> i32 { let a: [f64; 2] = [1, 2]; return 0; }",
        "fn main() -> i32 { let a: *[u8; 2] = 0 as *[u8; 2]; return 0; }",
        // Arrays only exist as local variables: no parameters or returns.
        "fn f(a: [u64; 3]) -> i32 { return 0; } fn main() -> i32 { return 0; }",
        "extern \"C\" { fn f(a: [u8; 2]); } fn main() -> i32 { return 0; }",
        "fn f() -> [u64; 3] { let a: [u64; 3] = [1; 3]; return a; } fn main() -> i32 { return 0; }",
        // Whole-array values are not copyable, comparable or passable.
        "fn f(n: u64) -> u64 { return n; } fn main() -> i32 { let a: [u64; 2] = [1; 2]; return f(a) as i32; }",
        "fn main() -> i32 { let a: [u64; 2] = [1; 2]; let b = a; return 0; }",
        "fn main() -> i32 { let a: [u64; 2] = [1; 2]; let mut b: [u64; 2] = a; return 0; }",
        "fn main() -> i32 { let mut a: [u64; 2] = [1; 2]; a = a; return 0; }",
        "fn main() -> i32 { let a: [u64; 2] = [1; 2]; if a == a { return 1; } return 0; }",
        "fn main() -> i32 { let a: [u64; 2] = [1; 2]; print_uint(a); return 0; }",
        "fn main() -> i32 { print_uint([1, 2]); return 0; }",
        // An array initializer requires the [T; N] annotation.
        "fn main() -> i32 { let a = [1, 2]; return 0; }",
        "fn main() -> i32 { let a: [u64; 2] = 5; return 0; }",
        // Indexing requires a local array and an integer index.
        "fn main() -> i32 { let mut a: [u64; 2] = [1; 2]; let x: u8 = 1; x[0] = 3; return 0; }",
        "fn main() -> i32 { let a: [u64; 2] = [1; 2]; let b = a[true]; return 0; }",
        "fn main() -> i32 { let a: [u64; 2] = [1; 2]; let b = a[0][0]; return 0; }",
        "fn main() -> i32 { let a: [u64; 2] = [1; 2]; let b = a[0:1]; return 0; }",
        "fn main() -> i32 { let a: [u64; 2] = [1; 2]; let b = a.len; return 0; }",
        "fn main() -> i32 { let a: [u64; 2] = [1; 2]; let b = a as [u64; 2]; return 0; }",
        // Mutability and element typing apply to indexed writes too.
        "fn main() -> i32 { let a: [u64; 2] = [1; 2]; a[0] = 3; return 0; }",
        "fn main() -> i32 { let mut a: [u64; 2] = [1; 2]; a[0] = true; return 0; }",
        "fn main() -> i32 { let mut f: [bool; 1] = [true]; f[0] += true; return 0; }",
    ] {
        reject(source);
    }
}

#[test]
fn freestanding_array_codegen_uses_the_checked_index_helper() {
    let case = Case::new(
        r#"
pub fn kernel_entry() -> i32 {
    let mut a: [u8; 2] = [1, 2];
    a[0] += 1;
    return a[0] as i32;
}
"#,
    );
    let out = case.cli(&[
        "build",
        "input.zen",
        "--target",
        "x86_64-unknown-none",
        "--emit",
        "c",
        "-o",
        "out.c",
    ]);
    success(&out);
    let c = fs::read_to_string(case.0.join("out.c")).unwrap();
    assert!(c.contains("__zen_index_check(uint64_t idx,uint64_t len)"));
    assert!(c.contains("Zen runtime error: array index out of bounds"));
    assert!(c.contains("uint8_t __zen_v0[2];"));
    assert!(!c.contains("#include <stdio.h>"));
}
