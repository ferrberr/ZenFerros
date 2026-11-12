"""TASK-925: real-file Zen -> Zen CLI -> C11 versus Rust bootstrap.

The identical source bytes are checked/compiled by both implementations.
Invalid-program comparisons require both to reject and no C on stdout;
unsupported but valid Zen is tracked separately as a subset boundary.
"""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
ZEN = Path(os.environ.get("ZEN", ROOT / "zen/compiler/target/release/zen"))
SPEC = importlib.util.spec_from_file_location("build_selfhost_cli", ROOT / "zen/selfhost/build_cli.py")
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)

POSITIVES = {
    "empty": ("", ""),
    "print": ("print_uint(42u64);", "42"),
    "arithmetic": ("print_uint((2u64 + 3u64) * 4u64 - 1u64);", "19"),
    "wrap": ("print_uint(18446744073709551615u64 + 1u64);", "0"),
    "multiply_wrap": ("print_uint(9223372036854775808u64 * 2u64);", "0"),
    "bool": ("let flag:bool = true; if flag { print_uint(1u64); } "
             "else { print_uint(2u64); }", "1"),
    "false": ("let mut flag:bool = false; flag = !flag; "
              "if flag { print_uint(7u64); }", "7"),
    "comparison": ("let test:bool = 8u64 >= 3u64; "
                   "if test { print_uint(8u64); }", "8"),
    "logic": ("let a:bool=true; let b:bool=false; "
              "if a && !b || b { print_uint(1u64); }", "1"),
    "while": ("let mut n:u64=0u64; while n < 4u64 { print_uint(n); n=n+1u64; }", "0123"),
    "nested": ("let mut i:u64=0u64; while i<3u64 { if i==1u64 { "
               "print_uint(9u64); } else { print_uint(i); } i=i+1u64; }", "092"),
    "shadow": ("let x:u64=1u64; if true { let x:u64=2u64; print_uint(x); } "
               "print_uint(x);", "21"),
    "c_names": ("let printf:u64=3u64; let int:u64=4u64; print_uint(printf+int);", "7"),
    "comments": ("/* outer /* nested */ end */ let n:u64=5u64; // line\nprint_uint(n);", "5"),
    "wrap_subtract": ("print_uint(0u64 - 1u64);", "18446744073709551615"),
    "mut_shadow": ("let mut n:u64=1u64; if true { let mut n:u64=2u64; "
                   "n=3u64; print_uint(n); } n=4u64; print_uint(n);", "34"),
    "bool_eq": ("let a:bool=true; let b:bool=false; if a != b { print_uint(5u64); }", "5"),
    "one_comparison": ("let b:bool=(1u64<2u64); if b == true { print_uint(3u64); }", "3"),
}
INVALID = {
    "unary_minus_u64": "print_uint(-1u64);",
    "shadow_same_scope": "let n:u64=1u64; let n:u64=2u64; print_uint(n);",
    "u64_annotation": "let n:u64=true;",
    "bool_annotation": "let n:bool=1u64;",
    "undefined": "print_uint(missing);",
    "immutable": "let n:u64=1u64; n=2u64;",
    "immutable_shadow": "let mut n:u64=1u64; if true { let n:u64=2u64; n=3u64; }",
    "immutable_outer": "let n:u64=1u64; if true { n=2u64; }",
    "assignment_type": "let mut n:u64=1u64; n=false;",
    "condition": "if 1u64 { print_uint(1u64); }",
    "bool_arithmetic": "print_uint(true+1u64);",
    "print_bool": "print_uint(true);",
    "print_void": "print_uint(1u64)+2u64;",
    "print_nested": "print_uint(print_uint(1u64));",
    "print_empty": "print_uint();",
    "scope": "if true { let n:u64=1u64; } print_uint(n);",
    "missing_semi": "let n:u64=1u64 print_uint(n);",
    "extra_brace": "}",
    "bad_token": "@;",
    "integer_overflow": "let n:u64=18446744073709551616u64;",
    "broken_comment": "/*",
    "ordered_bool_literals": "if false < true { print_uint(1u64); }",
    "ordered_bool_locals": "let a:bool=true; let b:bool=false; if a>=b { print_uint(1u64); }",
    "ordered_bool_parentheses": "let b:bool=(true || false) <= (!false);",
    "comparison_types": "let b:bool=1u64 == true;",
}
UNSUPPORTED = {
    "inferred_local": "let n=1u64; print_uint(n);",
    "unsuffixed": "let n:u64=1; print_uint(n);",
    "division": "print_uint(6u64 / 2u64);",
    "remainder": "print_uint(6u64 % 2u64);",
    "array": "let a:[u64;2]=[1u64,2u64]; print_uint(a[0u64]);",
    "string": 'print("hello");',
    "multiple_comparisons": "if 1u64<2u64 && 3u64<4u64 { print_uint(1u64); }",
    "nondecimal": "print_uint(0xffu64);",
}


def program(body):
    return "fn main() -> i32 {\n" + body + "\nreturn 0;\n}\n"


@unittest.skipUnless(ZEN.is_file() and shutil.which("cc"), "requires bootstrap ZEN and cc")
class SelfhostCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="selfhost-cli-test-")
        cls.tmp = Path(cls.temp.name)
        cls.exe = BUILDER.build(ZEN, cls.tmp / "zen-selfhost")

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def source(self, text):
        path = self.tmp / "source with spaces.zen"
        path.write_text(text)
        return path

    def run_cli(self, path, env=None):
        return subprocess.run([str(self.exe), str(path)], capture_output=True,
                              timeout=30, env=env)

    def rust(self, *args):
        return subprocess.run([str(ZEN), *map(str, args)], capture_output=True, timeout=30)

    def compare(self, path, expected):
        emitted = self.run_cli(path)
        self.assertEqual(emitted.returncode, 0, emitted.stderr.decode())
        self.assertEqual(emitted.stderr, b"")
        cfile = self.tmp / "generated.c"
        cfile.write_bytes(emitted.stdout)
        self.assertTrue(emitted.stdout.startswith(b"#include <stdio.h>"))
        # Both normal and optimized generated C must have identical behavior.
        for opt in ("-O0", "-O2"):
            exe = self.tmp / ("generated" + opt)
            cc = subprocess.run(["cc", "-std=c11", opt, "-Wall", "-Wextra", "-Werror",
                                 str(cfile), "-o", str(exe)], capture_output=True, timeout=30)
            self.assertEqual(cc.returncode, 0, cc.stderr.decode())
            actual = subprocess.run([str(exe)], capture_output=True, timeout=5)
            self.assertEqual((actual.returncode, actual.stdout, actual.stderr),
                             (0, expected.encode(), b""))
        rustexe = self.tmp / "rust-reference"
        built = self.rust("build", path, "-o", rustexe)
        self.assertEqual(built.returncode, 0, built.stderr.decode())
        reference = subprocess.run([str(rustexe)], capture_output=True, timeout=5)
        self.assertEqual((reference.returncode, reference.stdout, reference.stderr),
                         (0, expected.encode(), b""))
        self.assertEqual(self.run_cli(path).stdout, emitted.stdout)

    def test_real_fixture_matches_rust(self):
        self.compare(ROOT / "zen/selfhost/tests/fixtures/cli/sum.zen", "45")

    def test_positive_same_source_differential(self):
        for name, (body, expected) in POSITIVES.items():
            with self.subTest(name=name):
                self.compare(self.source(program(body)), expected)

    def test_invalid_same_source_both_reject(self):
        for name, body in INVALID.items():
            with self.subTest(name=name):
                path = self.source(program(body))
                result = self.run_cli(path)
                self.assertIn(result.returncode, (5, 6), result.stderr)
                self.assertEqual(result.stdout, b"")
                self.assertTrue(result.stderr)
                rust = self.rust("check", path)
                self.assertNotEqual(rust.returncode, 0, (name, rust.stdout))

    def test_valid_rust_outside_subset_rejected(self):
        for name, body in UNSUPPORTED.items():
            with self.subTest(name=name):
                path = self.source(program(body))
                rust = self.rust("check", path)
                self.assertEqual(rust.returncode, 0, rust.stderr)
                result = self.run_cli(path)
                self.assertIn(result.returncode, (5, 6))
                self.assertEqual(result.stdout, b"")

    def test_missing_or_wrong_entrypoint_rejected(self):
        for text in ("", "fn main()->u64{return 0u64;}",
                     "fn main()->i32{return 1;}", "fn other()->i32{return 0;}",
                     "fn main()->i32{return 0;} fn extra()->u64{return 1u64;}",
                     "fn main()->i32{if true{return 0;}return 0;}"):
            with self.subTest(text=text):
                result = self.run_cli(self.source(text))
                self.assertEqual(result.returncode, 5)
                self.assertEqual(result.stdout, b"")

    def test_usage_io_and_input_capacity(self):
        for args in ([], ["a", "b"], [str(self.tmp / "missing")]):
            result = subprocess.run([str(self.exe), *args], capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, b"")
        text = program("")
        exact = text + " " * (65536 - len(text))
        self.assertEqual(self.run_cli(self.source(exact)).returncode, 0)
        result = self.run_cli(self.source(exact + " "))
        self.assertEqual((result.returncode, result.stdout), (2, b""))

    def test_backend_capacity_no_partial_stdout(self):
        body = " ".join("print_uint(1u64);" for _ in range(600))
        result = self.run_cli(self.source(program(body)))
        self.assertIn(result.returncode, (4, 5))
        self.assertEqual(result.stdout, b"")

    def test_compiler_does_not_spawn_bootstrap_or_cc(self):
        path = self.source(program("print_uint(9u64);"))
        result = self.run_cli(path, env={"PATH": "/nonexistent"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b"int main(void)", result.stdout)


if __name__ == "__main__":
    unittest.main()
