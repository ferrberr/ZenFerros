//! CLI-level acceptance tests for nominal structs in the Zen MVP subset.
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
            "zen-structs-{}-{}",
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
fn reject_with(source: &str, needle: &str) {
    let case = Case::new(source);
    let out = case.cli(&["check", "input.zen"]);
    assert!(!out.status.success(), "accepted invalid struct source: {source}");
    let stderr = String::from_utf8_lossy(&out.stderr);
    assert!(
        stderr.contains("error") && stderr.contains("input.zen:"),
        "missing localized diagnostic for {source}: {stderr}"
    );
    assert!(
        stderr.contains(needle),
        "expected {needle:?} for {source}: {stderr}"
    );
    assert!(!stderr.contains("panicked"), "{stderr}");
}
fn reject(source: &str) {
    let case = Case::new(source);
    let out = case.cli(&["check", "input.zen"]);
    assert!(!out.status.success(), "accepted invalid struct source: {source}");
    let stderr = String::from_utf8_lossy(&out.stderr);
    assert!(
        stderr.contains("error") && stderr.contains("input.zen:"),
        "missing localized diagnostic for {source}: {stderr}"
    );
    assert!(!stderr.contains("panicked"), "{stderr}");
}

#[test]
fn structs_construct_read_and_write_fields_in_both_modes() {
    run_both(
        r#"
struct Point { x: i32, y: i32, }
fn main() -> i32 {
    let mut p: Point = Point { x: 3, y: 4 };
    p.x += 5;
    p.y = p.x * 2;
    print_int(p.x as i64);
    print(",");
    print_int(p.y as i64);
    let sum = p.x + p.y;
    print(",");
    print_int(sum as i64);
    print("\n");
    return 0;
}
"#,
        b"8,16,24\n",
    );
}

#[test]
fn every_scalar_field_type_and_out_of_order_literals() {
    run_both(
        r#"
struct All { a: u8, b: u16, c: u32, d: i32, e: i64, f: u64, g: bool }
fn main() -> i32 {
    let mut v: All = All { g: true, e: -5, a: 255, f: 18446744073709551615, c: 4294967295, b: 65535, d: -2147483648 };
    v.a = 0;
    v.b >>= 8;
    v.c ^= 1;
    v.d += 1;
    v.e += 5;
    v.f += 1;
    v.g = !v.g;
    print_uint(v.a as u64);
    print(" ");
    print_uint(v.b as u64);
    print(" ");
    print_uint(v.c as u64);
    print(" ");
    print_int(v.d as i64);
    print(" ");
    print_int(v.e);
    print(" ");
    print_uint(v.f);
    print(" ");
    if v.g { print("T"); } else { print("F"); }
    print("\n");
    return 0;
}
"#,
        b"0 255 4294967294 -2147483647 0 0 F\n",
    );
}

#[test]
fn structs_shadow_in_nested_blocks_and_rebuild_in_loops() {
    run_both(
        r#"
struct Item { id: u32, active: bool }
fn main() -> i32 {
    let outer: Item = Item { id: 1, active: true };
    {
        let outer: Item = Item { id: 2, active: false };
        print_uint(outer.id as u64);
    }
    print_uint(outer.id as u64);
    let inferred = Item { id: 3, active: false };
    print_uint(inferred.id as u64);
    let mut i: u64 = 0;
    while i < 2 {
        let mut item: Item = Item { id: i as u32 + 10, active: i == 0 };
        item.id += 1;
        print_uint(item.id as u64);
        i += 1;
    }
    return 0;
}
"#,
        b"2131112",
    );
}

#[test]
fn struct_literal_fields_and_writes_evaluate_left_to_right_once() {
    run_both(
        r#"
struct Pair { a: u64, b: u64 }
fn side(n: u64) -> u64 { print("s"); return n; }
fn main() -> i32 {
    let mut p: Pair = Pair { a: side(1), b: side(2) };
    print_uint(p.a + p.b);
    p.a = side(3);
    p.b += side(4);
    print_uint(p.a + p.b);
    return 0;
}
"#,
        b"ss3ss9",
    );
}

#[test]
fn c_keyword_struct_and_field_names_emit_safely() {
    let source = r#"
struct int { int: i32, signed: bool }
fn main() -> i32 {
    let mut v: int = int { int: 7, signed: true };
    v.int += 1;
    print_int(v.int as i64);
    print(" ");
    if v.signed { print("T"); } else { print("F"); }
    print("\n");
    return 0;
}
"#;
    run_both(source, b"8 T\n");

    let case = Case::new(source);
    let out = case.cli(&["build", "input.zen", "--emit", "c", "-o", "out.c"]);
    success(&out);
    let c = fs::read_to_string(case.0.join("out.c")).unwrap();
    assert!(c.contains("typedef struct {"), "{c}");
    assert!(c.contains("} __zen_Struct_int;"), "{c}");
    assert!(c.contains("int32_t __zen_m0;"), "{c}");
    assert!(c.contains("bool __zen_m1;"), "{c}");
    assert!(c.contains("__zen_Struct_int __zen_v"), "{c}");
    assert!(!c.contains(".int"), "{c}");
    assert!(!c.contains(".signed"), "{c}");
    let typedef = c.find("} __zen_Struct_int;").unwrap();
    let first_fn = c.find("__zen_f0").unwrap();
    assert!(typedef < first_fn, "typedefs must precede functions:\n{c}");
}

#[test]
fn rejects_invalid_struct_declarations() {
    for (source, needle) in [
        (
            "struct P { x: i32 } struct P { y: i32 } fn main() -> i32 { return 0; }",
            "duplicate struct 'P'",
        ),
        (
            "struct P { x: i32, x: u8 } fn main() -> i32 { return 0; }",
            "duplicate field 'x' in struct 'P'",
        ),
        (
            "struct P {} fn main() -> i32 { return 0; }",
            "at least one field",
        ),
        (
            "struct P { x: f64 } fn main() -> i32 { return 0; }",
            "must have scalar type",
        ),
        (
            "struct P { x: u8, y: [u8; 2] } fn main() -> i32 { return 0; }",
            "must have scalar type",
        ),
        (
            "struct A { x: i32 } struct B { a: A } fn main() -> i32 { return 0; }",
            "must have scalar type",
        ),
        (
            "struct P { s: str } fn main() -> i32 { return 0; }",
            "must have scalar type",
        ),
        (
            "struct P { p: *u8 } fn main() -> i32 { return 0; }",
            "must have scalar type",
        ),
        (
            "struct P { v: void } fn main() -> i32 { return 0; }",
            "must have scalar type",
        ),
        (
            "struct str { x: i32 } fn main() -> i32 { return 0; }",
            "reserved",
        ),
        (
            "struct P { for: i32 } fn main() -> i32 { return 0; }",
            "expected identifier",
        ),
        (
            "struct P { x: i32,",
            "unterminated struct declaration",
        ),
        (
            "struct P { x: i32 } fn main() -> i32 { let p: P = P { x: 1,",
            "unterminated struct literal",
        ),
    ] {
        reject_with(source, needle);
    }
    // Methods/impl blocks are outside the MVP scope.
    reject("struct P { x: i32 } impl P { } fn main() -> i32 { return 0; }");
}

#[test]
fn rejects_struct_literal_field_mismatches() {
    for (source, needle) in [
        (
            "struct P { x: i32, y: u8 } fn main() -> i32 { let p: P = P { x: 1, z: 2 }; return 0; }",
            "unknown field 'z'",
        ),
        (
            "struct P { x: i32, y: u8 } fn main() -> i32 { let p: P = P { x: 1 }; return 0; }",
            "missing field 'y'",
        ),
        (
            "struct P { x: i32 } fn main() -> i32 { let p: P = P {}; return 0; }",
            "missing field 'x'",
        ),
        (
            "struct P { x: i32, y: u8 } fn main() -> i32 { let p: P = P { x: 1u16, y: 2 }; return 0; }",
            "type mismatch",
        ),
        (
            "struct P { x: i32 } fn main() -> i32 { let p: P = P { x: 1, x: 2 }; return 0; }",
            "duplicate field 'x' in struct literal",
        ),
        (
            "struct A { x: i32 } struct B { y: i32 } fn main() -> i32 { let p: A = B { y: 1 }; return 0; }",
            "type mismatch: expected struct A, found struct B",
        ),
        (
            "struct P { x: i32 } fn main() -> i32 { let x: u64 = P { x: 1 }; return 0; }",
            "type mismatch: expected u64, found struct P",
        ),
    ] {
        reject_with(source, needle);
    }
}

#[test]
fn rejects_struct_parameters_returns_and_abi_uses() {
    for (source, needle) in [
        (
            "struct P { x: i32 } fn f(p: P) -> i32 { return 0; } fn main() -> i32 { return 0; }",
            "cannot be parameters",
        ),
        (
            "struct P { x: i32 } fn f() -> P { let p: P = P { x: 1 }; return p; } fn main() -> i32 { return 0; }",
            "cannot be returned",
        ),
        (
            "struct P { x: i32 } extern \"C\" { fn f(p: P); } fn main() -> i32 { return 0; }",
            "cannot be parameters",
        ),
        (
            "struct P { x: i32 } extern \"C\" { fn f() -> P; } fn main() -> i32 { return 0; }",
            "cannot be returned",
        ),
        (
            "struct P { x: i32 } fn main() -> i32 { let p: *P = 0 as *P; return 0; }",
            "raw pointers require an integer scalar pointee",
        ),
    ] {
        reject_with(source, needle);
    }
}

#[test]
fn rejects_whole_struct_values_and_unsupported_uses() {
    for (source, needle) in [
        (
            "struct P { x: i32 } fn main() -> i32 { let a: P = P { x: 1 }; let b = a; return 0; }",
            "cannot use struct value",
        ),
        (
            "struct P { x: i32 } fn main() -> i32 { let a: P = P { x: 1 }; let b: P = a; return 0; }",
            "must be initialized with a struct literal",
        ),
        (
            "struct P { x: i32 } fn main() -> i32 { let mut a: P = P { x: 1 }; let b: P = P { x: 2 }; a = b; return 0; }",
            "cannot assign to whole struct variable",
        ),
        (
            "struct P { x: i32 } fn main() -> i32 { let a: P = P { x: 1 }; if a == a { return 1; } return 0; }",
            "cannot use struct value",
        ),
        (
            "struct P { x: i32 } fn main() -> i32 { let a: P = P { x: 1 }; let b = a as i32; return 0; }",
            "cannot use struct value",
        ),
        (
            "struct P { x: i32 } fn main() -> i32 { let a: P = P { x: 1 }; print_uint(a); return 0; }",
            "cannot use struct value",
        ),
        (
            "struct P { x: i32 } fn f(n: u64) -> u64 { return n; } fn main() -> i32 { let a: P = P { x: 1 }; return f(a) as i32; }",
            "cannot use struct value",
        ),
        (
            "struct P { x: i32 } fn f() -> i32 { let a: P = P { x: 1 }; return a; } fn main() -> i32 { return 0; }",
            "cannot use struct value",
        ),
        (
            "struct P { x: i32 } fn f(n: u64) -> u64 { return n; } fn main() -> i32 { return f(P { x: 1 }) as i32; }",
            "only allowed as the initializer",
        ),
        (
            "struct P { x: i32 } fn main() -> i32 { let mut a: P = P { x: 1 }; a = P { x: 2 }; return 0; }",
            "cannot assign to whole struct variable",
        ),
        (
            "struct P { x: i32 } fn main() -> i32 { P { x: 1 } = P { x: 2 }; return 0; }",
            "assignment target must be a local variable",
        ),
        (
            "struct P { x: i32 } fn main() -> i32 { let a: [P; 1] = [P { x: 1 }]; return 0; }",
            "array element type",
        ),
    ] {
        reject_with(source, needle);
    }
}

#[test]
fn rejects_field_access_and_write_errors() {
    for (source, needle) in [
        (
            "struct P { x: i32 } fn main() -> i32 { let p: P = P { x: 1 }; p.x = 2; return 0; }",
            "use let mut",
        ),
        (
            "struct P { x: i32 } fn main() -> i32 { let p: P = P { x: 1 }; print_int(p.z as i64); return 0; }",
            "has no field 'z'",
        ),
        (
            "struct P { x: i32 } fn main() -> i32 { let mut p: P = P { x: 1 }; p.z = 2; return 0; }",
            "has no field 'z'",
        ),
        (
            "struct P { x: i32 } fn main() -> i32 { let mut p: P = P { x: 1 }; p.x = true; return 0; }",
            "type mismatch",
        ),
        (
            "fn main() -> i32 { let n: u8 = 1; n.x = 2; return 0; }",
            "has no fields",
        ),
        (
            "fn main() -> i32 { let a: [u8; 2] = [1; 2]; let n = a.len; return 0; }",
            "has no fields",
        ),
        (
            "struct P { x: i32, b: bool } fn main() -> i32 { let mut p: P = P { x: 1, b: true }; p.b += true; return 0; }",
            "compound assignment requires integer struct fields",
        ),
        (
            "struct P { x: i32 } fn main() -> i32 { let mut p: P = P { x: 1 }; p.x.y = 2; return 0; }",
            "assignment target must be a field of a local struct variable",
        ),
        (
            "struct P { x: i32 } fn f() -> i32 { return 1; } fn main() -> i32 { f().x = 2; return 0; }",
            "assignment target must be a field of a local struct variable",
        ),
        (
            "struct P { x: i32 } fn main() -> i32 { let mut a: [u8; 2] = [1; 2]; a[0].x = 2; return 0; }",
            "assignment target must be a field of a local struct variable",
        ),
        (
            "struct P { x: i32 } fn f() -> i32 { return 1; } fn main() -> i32 { let n = f().x; return 0; }",
            "field access requires a local struct variable",
        ),
        (
            "struct P { x: i32 } fn main() -> i32 { let p: P = P { x: 1 }; let n = p[0]; return 0; }",
            "cannot be indexed",
        ),
        (
            "struct P { x: i32 } fn main() -> i32 { let p: P = P { x: 1 }; let n = p.x[0]; return 0; }",
            "indexing requires a local array variable",
        ),
    ] {
        reject_with(source, needle);
    }
}

#[test]
fn struct_declarations_must_precede_their_uses() {
    reject_with(
        "fn main() -> i32 { let p: P = P { x: 1 }; return 0; } struct P { x: i32 }",
        "unknown type 'P'",
    );
    // Without a preceding declaration the name parses as a variable, so the
    // literal shape is rejected as a syntax error rather than a type error.
    reject("fn main() -> i32 { let p = P { x: 1 }; return 0; } struct P { x: i32 }");
}

#[test]
fn struct_field_chains_keep_resource_limits() {
    let case = Case::new(&format!(
        "struct P {{ x: i32 }} fn main() -> i32 {{ let p: P = P {{ x: 1 }}; let q = p{}; return 0; }}",
        ".x".repeat(200)
    ));
    let out = case.cli(&["check", "input.zen"]);
    assert!(!out.status.success());
    let stderr = String::from_utf8_lossy(&out.stderr);
    assert!(stderr.contains("nesting limit"), "{stderr}");
    assert!(!stderr.contains("panicked"), "{stderr}");

    let case = Case::new(&format!(
        "struct P {{ x: u8 }} fn main() -> i32 {{ let p: P = P {{ x: {}1{} }}; return 0; }}",
        "(".repeat(300),
        ")".repeat(300)
    ));
    let out = case.cli(&["check", "input.zen"]);
    assert!(!out.status.success());
    let stderr = String::from_utf8_lossy(&out.stderr);
    assert!(stderr.contains("nesting limit"), "{stderr}");
    assert!(!stderr.contains("panicked"), "{stderr}");
}

#[test]
fn freestanding_struct_codegen_emits_typedefs_without_stdio() {
    let case = Case::new(
        r#"
struct Token { kind: u8, flag: bool }
pub fn kernel_entry() -> i32 {
    let mut t: Token = Token { kind: 1, flag: true };
    t.kind += 2;
    return t.kind as i32;
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
    assert!(c.contains("typedef struct {"), "{c}");
    assert!(c.contains("} __zen_Struct_Token;"), "{c}");
    assert!(c.contains("uint8_t __zen_m0;"), "{c}");
    assert!(c.contains("bool __zen_m1;"), "{c}");
    assert!(c.contains("__zen_Struct_Token __zen_v"), "{c}");
    assert!(!c.contains("#include <stdio.h>"), "{c}");
}

#[test]
fn structs_example_runs_with_documented_output() {
    let example =
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../examples/structs.zen");
    assert!(example.exists(), "missing {}", example.display());
    for release in [false, true] {
        let mut command = Command::new(env!("CARGO_BIN_EXE_zen"));
        command.arg("run").arg(&example);
        if release {
            command.arg("--release");
        }
        let out = command.output().unwrap();
        success(&out);
        assert_eq!(
            out.stdout,
            b"token=7 at 3:12 valid=yes\ntoken=7 at 13:13 valid=no\nstats=3,1,no\n",
            "unexpected example output (release={release}): {}",
            String::from_utf8_lossy(&out.stdout)
        );
    }
}

#[test]
fn struct_names_cannot_shadow_value_names() {
    // Otherwise `if P {}` would be ambiguous between a block and a literal.
    reject_with(
        "struct P { x: i32 } fn main() -> i32 { let P: bool = true; if P {} return 0; }",
        "local 'P' conflicts with struct 'P'",
    );
    reject_with(
        "struct P { x: i32 } fn f(P: bool) -> i32 { return 0; } fn main() -> i32 { return f(true); }",
        "parameter 'P' conflicts with struct 'P'",
    );
    reject_with(
        "struct P { x: i32 } fn P() -> i32 { return 0; } fn main() -> i32 { return P(); }",
        "function 'P' conflicts with struct 'P'",
    );
}
