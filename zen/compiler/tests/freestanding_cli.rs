//! Freestanding objects, ABI and no-libc linkage verified with real toolchain tools.
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
            "zen-free-{}-{}",
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
    fn object(&self, release: bool) {
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
        ok(&self.cli(&args));
    }
    fn harness(&self, c: &str) -> Output {
        fs::write(self.0.join("harness.c"), c).unwrap();
        ok(&self.tool(
            "cc",
            &[
                "-std=c11",
                "-no-pie",
                "harness.c",
                "program.o",
                "-o",
                "harness",
            ],
        ));
        self.tool("sh", &["-c", "ulimit -c 0; exec ./harness"])
    }
}
impl Drop for Case {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}
fn ok(out: &Output) {
    assert!(
        out.status.success(),
        "{}\nstdout={}\nstderr={}",
        out.status,
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
}
fn both(source: &str, c: &str) {
    let case = Case::new(source);
    for release in [false, true] {
        case.object(release);
        ok(&case.harness(c));
    }
}
#[test]
fn freestanding_object_and_libc_free_execution() {
    let case = Case::new(include_str!("../../examples/freestanding.zen"));
    fs::write(
        case.0.join("start.S"),
        include_str!("../../../infrastructure/freestanding/linux_start.S"),
    )
    .unwrap();
    fs::write(
        case.0.join("link.ld"),
        include_str!("../../../infrastructure/freestanding/linux_test.ld"),
    )
    .unwrap();
    ok(&case.tool(
        "cc",
        &["-c", "-m64", "-fno-pie", "start.S", "-o", "start.o"],
    ));
    for release in [false, true] {
        case.object(release);
        let header = case.tool("readelf", &["-h", "program.o"]);
        ok(&header);
        let header = String::from_utf8_lossy(&header.stdout);
        assert!(
            header.contains("REL (Relocatable file)")
                && header.contains("ELF64")
                && header.contains("X86-64"),
            "{header}"
        );
        let undefined = case.tool("nm", &["-u", "program.o"]);
        ok(&undefined);
        let symbols = String::from_utf8_lossy(&undefined.stdout);
        assert_eq!(
            symbols.split_whitespace().collect::<Vec<_>>(),
            ["U", "emit_byte"]
        );
        let sections = case.tool("readelf", &["-SW", "program.o"]);
        ok(&sections);
        assert!(!String::from_utf8_lossy(&sections.stdout).contains(".eh_frame"));
        ok(&case.tool(
            "ld",
            &[
                "-nostdlib",
                "-static",
                "-z",
                "noexecstack",
                "-T",
                "link.ld",
                "start.o",
                "program.o",
                "-o",
                "standalone",
            ],
        ));
        let dynamic = case.tool("readelf", &["-d", "standalone"]);
        ok(&dynamic);
        assert!(!String::from_utf8_lossy(&dynamic.stdout).contains("NEEDED"));
        let segments = case.tool("readelf", &["-lW", "standalone"]);
        ok(&segments);
        assert!(!String::from_utf8_lossy(&segments.stdout).contains("INTERP"));
        let undefined = case.tool("nm", &["-u", "standalone"]);
        ok(&undefined);
        assert!(undefined.stdout.is_empty());
        let out = case.tool(case.0.join("standalone").to_str().unwrap(), &[]);
        ok(&out);
        assert_eq!(out.stdout, b"Zen freestanding OK\n");
    }
}
#[test]
fn abi_small_integers_casts_and_bitwise() {
    both(
        r#"
extern "C" { fn observe(value: u8) -> u64; }
pub fn small(a:u8,b:u16,c:u32)->u64 {
    let wrapped:u8 = a + 1;
    let product:u16 = b * 65535u16;
    let masked:u32 = (c & 255u32) | (1u32 << 8);
    let bits:u32 = (masked ^ 3u32) >> 1;
    unsafe { return observe(wrapped) + (product as u64) + (bits as u64); }
}
pub fn invert(value:u8)->u8 { return ~value; }
pub fn signed(value:i64)->i32 { return value as i32; }
pub fn shift(value:i32,n:u64)->i32 { return value >> n; }
pub fn switch(value:u64)->u64 { return value + 1; }
"#,
        r#"
#include <stdint.h>
extern uint64_t small(uint8_t,uint16_t,uint32_t);
extern uint8_t invert(uint8_t);
extern int32_t signed_value(int64_t) __asm__("signed");
extern int32_t shift(int32_t,uint64_t);
extern uint64_t c_keyword(uint64_t) __asm__("switch");
uint64_t observe(uint8_t value) { return value == 0 ? 1000 : 0; }
int main(void) {
    if (small(255,65535,0xffffffffu) != 1255) return 1;
    if (invert(0) != 255 || signed_value(4294967295LL) != -1) return 2;
    if (shift(-8,2) != -2 || c_keyword(41) != 42) return 3;
    return 0;
}
"#,
    );
}
#[test]
fn unsafe_volatile_memory_and_pointer_abi() {
    both(
        r#"
pub fn touch(pointer:*mut u32)->u32 {
    unsafe { volatile_store(pointer,0x12345678u32); return volatile_load(pointer); }
}
pub fn touch_address(address:u64)->u64 {
    unsafe {
        let pointer:*mut u64 = address as *mut u64;
        volatile_store(pointer,18446744073709551615u64);
        return pointer as u64;
    }
}
pub fn read(pointer:*u8)->u8 { unsafe { return volatile_load(pointer); } }
"#,
        r#"
#include <stdint.h>
extern uint32_t touch(uint32_t*);
extern uint64_t touch_address(uint64_t);
extern uint8_t read(const uint8_t*);
int main(void) {
    uint32_t cell=0; uint64_t wide=0; const uint8_t byte=219;
    if (touch(&cell) != 0x12345678 || cell != 0x12345678) return 1;
    if (touch_address((uint64_t)(uintptr_t)&wide) != (uint64_t)(uintptr_t)&wide || wide != UINT64_MAX) return 2;
    return read(&byte) == 219 ? 0 : 3;
}
"#,
    );
}
#[test]
fn pure_object_has_no_implicit_runtime_symbols() {
    let case = Case::new(
        r#"
pub fn compute(a:i64,b:i64)->i64 { return (a * b + 1) / 2; }
pub fn message_len()->u64 { return str_len("a\0é"); }
pub fn message_byte()->u8 { return str_byte("a\0é",2); }
"#,
    );
    for release in [false, true] {
        case.object(release);
        let out = case.tool("nm", &["-u", "program.o"]);
        ok(&out);
        assert!(
            out.stdout.is_empty(),
            "{}",
            String::from_utf8_lossy(&out.stdout)
        );
        ok(&case.harness("#include <stdint.h>\nextern int64_t compute(int64_t,int64_t); extern uint64_t message_len(void); extern uint8_t message_byte(void); int main(void) { return compute(-7,3)==-10 && message_len()==4 && message_byte()==195 ? 0 : 1; }"));
    }
}
#[test]
fn invalid_freestanding_programs_have_located_diagnostics() {
    for source in [
        "pub fn f() { print(\"hosted\"); }",
        "pub fn f(p:*u8)->u8 { return volatile_load(p); }",
        "pub fn f(p:*mut u8) { volatile_store(p,0u8); }",
        "pub fn f(p:*u8) { unsafe { volatile_store(p,0u8); } }",
        "pub fn f(p:*mut u8) { unsafe { volatile_store(p,true); } }",
        "pub fn f(a:u64)->u8 { let p = a as *u8; unsafe { return volatile_load(p); } }",
        "pub fn f(p:*u8)->u64 { return p as u64; }",
        "pub fn f(a:u64)->u64 { return volatile_load(a); }",
        "pub fn f(a:bool)->bool { return a << 1; }",
        "pub fn f()->u8 { return 256u8; }",
        "pub fn f()->u16 { return 65536u16; }",
        "pub fn f()->u32 { return 4294967296u32; }",
        "pub fn f()->str { return \"invalid boundary\"; }",
        "extern \"C\" { fn foreign(s:str); } pub fn f() {}",
        "extern \"system\" { fn foreign(); } pub fn f() {}",
        "extern \"C\" { fn foreign(); } pub fn f() { foreign(); }",
        "pub fn __zen_fail() {}",
        "extern \"C\" { fn __zen_fail(); } pub fn f() {}",
    ] {
        let case = Case::new(source);
        let out = case.cli(&["check", "input.zen", "--target", TARGET]);
        assert!(!out.status.success(), "invalid source accepted: {source}");
        let stderr = String::from_utf8_lossy(&out.stderr);
        assert!(
            stderr.contains("error") && stderr.contains("input.zen:"),
            "{source}\n{stderr}"
        );
        assert!(!stderr.contains("panicked"));
    }
}
#[test]
fn invalid_runtime_operations_trap_without_libc() {
    for (source, return_type) in [
        ("pub fn failure()->u8 { return 1u8 << 8; }", "uint8_t"),
        ("pub fn failure()->u8 { return 1u8 << -1i32; }", "uint8_t"),
        ("pub fn failure()->i64 { return 1i64 >> 64; }", "int64_t"),
        ("pub fn failure()->u64 { return 1u64 / 0; }", "uint64_t"),
        (
            "pub fn failure()->u8 { return str_byte(\"x\",1); }",
            "uint8_t",
        ),
    ] {
        let case = Case::new(source);
        for release in [false, true] {
            case.object(release);
            let out =
                case.harness(&format!("#include <stdint.h>\nextern {return_type} failure(void); int main(void) {{ (void)failure(); return 0; }}"));
            assert!(
                !out.status.success(),
                "invalid operation succeeded: {source}"
            );
        }
    }
}
#[test]
fn check_and_c_emission_need_no_native_compiler() {
    let case = Case::new("pub fn answer()->u64 { return 42; }");
    for args in [
        vec!["check", "input.zen", "--target", TARGET],
        vec!["build", "input.zen", "--target", TARGET, "--emit", "c"],
    ] {
        let out = Command::new(env!("CARGO_BIN_EXE_zen"))
            .current_dir(&case.0)
            .env("CC", "/missing-zen-cc")
            .args(args)
            .output()
            .unwrap();
        ok(&out);
    }
    assert!(!case.0.join("input.o").exists());
    let c = fs::read_to_string(case.0.join("input.c")).unwrap();
    for forbidden in [
        "<stdio.h>",
        "<stdlib.h>",
        "<string.h>",
        "memcpy(",
        "int main(",
    ] {
        assert!(
            !c.contains(forbidden),
            "contains hosted dependency {forbidden}"
        );
    }
    assert!(!case
        .cli(&["build", "input.zen", "--target", TARGET])
        .status
        .success());
}
#[test]
fn freestanding_compile_flags_and_failure_preserve_output() {
    use std::os::unix::fs::PermissionsExt;
    let case = Case::new("pub fn answer()->u64 { return 42; }");
    let wrapper = case.0.join("cc-wrapper");
    fs::write(
        &wrapper,
        "#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$ZEN_CC_ARGS\"\nexec cc \"$@\"\n",
    )
    .unwrap();
    fs::set_permissions(&wrapper, fs::Permissions::from_mode(0o700)).unwrap();
    let out = Command::new(env!("CARGO_BIN_EXE_zen"))
        .current_dir(&case.0)
        .env("CC", &wrapper)
        .env("ZEN_CC_ARGS", case.0.join("args"))
        .args(["build", "input.zen", "--target", TARGET, "--emit", "obj"])
        .output()
        .unwrap();
    ok(&out);
    let args = fs::read_to_string(case.0.join("args")).unwrap();
    for flag in [
        "-ffreestanding",
        "-fno-builtin",
        "-fno-stack-protector",
        "-mno-red-zone",
        "-mgeneral-regs-only",
        "-mcmodel=kernel",
        "-fno-pie",
        "-fno-pic",
        "-c",
    ] {
        assert!(args.lines().any(|s| s == flag), "missing {flag}: {args}");
    }
    let original = fs::read(case.0.join("input.o")).unwrap();
    let out = Command::new(env!("CARGO_BIN_EXE_zen"))
        .current_dir(&case.0)
        .env("CC", "false")
        .args(["build", "input.zen", "--target", TARGET, "--emit", "obj"])
        .output()
        .unwrap();
    assert!(!out.status.success());
    assert_eq!(fs::read(case.0.join("input.o")).unwrap(), original);
    assert!(!case
        .cli(&[
            "build",
            "input.zen",
            "--target",
            TARGET,
            "--emit",
            "obj",
            "-o",
            "input.zen"
        ])
        .status
        .success());
}
