"""TASK-902: verify the self-hosted Zen lexer against the Rust reference lexer.

For every fixture the test builds `zen/selfhost/lexer.zen` as a freestanding
ELF object, links it with `zen/selfhost/lexer_driver.c`, runs the driver and
compares its eight counters with the token stream printed by `zen lex`.

Run from the repository root:

    python3 -m unittest discover -s zen/selfhost/tests -v
"""

import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ZEN = ROOT / "zen" / "compiler" / "target" / "release" / "zen"
LEXER = ROOT / "zen" / "selfhost" / "lexer.zen"
DRIVER = ROOT / "zen" / "selfhost" / "lexer_driver.c"

FIXTURES = [
    ROOT / "zen" / "examples" / "hello.zen",
    ROOT / "zen" / "examples" / "factorial.zen",
    ROOT / "zen" / "examples" / "structs.zen",
    ROOT / "ferros" / "kernel" / "vfs.zen",
]

# Synthetic lexemes-only fixture: exercises nested block comments, escapes,
# all integer bases and suffixes, floats, chars and the operator table. It is
# never parsed or compiled, only lexed by both implementations.
SYNTHETIC = r'''// TASK-902 synthetic lexical fixture (lexed, never compiled).
/* block /* nested */ comment */
fn synthetic(a:u64, b:u8) -> u64 {
    let dec = 1_000u64;
    let hex = 0xFFu8;
    let bin = 0b1010u16;
    let oct = 0o755i32;
    let flt = 3.5f64 + 1e10 + 0.5;
    let escaped = "quote:\" slash:\\ newline:\n tab:\t hex:\x41";
    let ch = '\n';
    let ops = a ** 2 << 3 >> 1;
    let seen = true;
    let absent = false;
    a += 1; a -= 1; a *= 2; a /= 2; a %= 2;
    a &= b as u64; a |= 1; a ^= 1; a <<= 1; a >>= 1;
    let path = a::b;
    let pair = a => b;
    let range = a..b;
    let spread = a...b;
    let tilde = ~a;
    let question = a ? b : a;
    if a == b as u64 && a != 0 || a <= 3 { return a; }
    return a;
}
'''

KEYWORDS = {
    # TokenKind keyword and primitive-type variants.
    "Fn", "Let", "Mut", "Const", "If", "Else", "While", "For", "Return",
    "Break", "Continue", "Struct", "Impl", "Mod", "Use", "Pub", "As", "Type",
    "Enum", "Match", "Loop", "Unsafe", "Extern", "Sizeof", "Alignof",
    "Offsetof", "Cast", "Transmute", "True", "False", "Null", "Bool",
    "Void", "Bool_", "Char_", "I8", "I16", "I32", "I64", "I128", "Isize",
    "U8", "U16", "U32", "U64", "U128", "Usize", "F32", "F64", "Never",
}
NUMBERS = {"Integer", "Float"}
STRINGS = {"String", "Char"}
COUNTERS = ("tokens", "idents", "numbers", "strings", "keywords", "punct", "errors", "bytes")
TOKEN_LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)")


def categorize(kind):
    """Map a Rust TokenKind debug name to a lexer report category."""
    if kind in KEYWORDS:
        return "keywords"
    if kind == "Ident":
        return "idents"
    if kind in NUMBERS:
        return "numbers"
    if kind in STRINGS:
        return "strings"
    if kind == "Error":
        return "errors"
    return "punct"


def reference_counts(path):
    """Count categories in the real `zen lex` output (excluding Eof)."""
    result = subprocess.run(
        [str(ZEN), "lex", str(path)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"zen lex failed on {path} (exit {result.returncode}):\n{result.stderr}"
        )
    counts = {name: 0 for name in COUNTERS if name != "bytes"}
    for line in result.stdout.splitlines():
        match = TOKEN_LINE.match(line)
        if match is None:
            raise AssertionError(f"cannot parse zen lex line: {line!r}")
        kind = match.group(1)
        if kind == "Eof":
            continue
        counts["tokens"] += 1
        counts[categorize(kind)] += 1
    counts["bytes"] = path.stat().st_size
    return counts


def driver_counts(driver, path):
    result = subprocess.run(
        [str(driver), str(path)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"lexer_driver failed on {path} (exit {result.returncode}):\n{result.stderr}"
        )
    counts = {}
    for field in result.stdout.split():
        name, _, value = field.partition("=")
        if name in COUNTERS:
            counts[name] = int(value)
    missing = [name for name in COUNTERS if name not in counts]
    if missing:
        raise AssertionError(f"driver output misses {missing}: {result.stdout!r}")
    return counts


class SelfhostLexerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ZEN.is_file():
            raise unittest.SkipTest(f"missing prebuilt compiler: {ZEN}")
        cls.scratch = tempfile.TemporaryDirectory(prefix="zen-selfhost-lexer-")
        cls.addClassCleanup(cls.scratch.cleanup)
        work = Path(cls.scratch.name)

        object_path = work / "lexer.o"
        archive = subprocess.run(
            [
                str(ZEN), "build", str(LEXER),
                "--target", "x86_64-unknown-none",
                "--emit", "obj",
                "-o", str(object_path),
            ],
            capture_output=True,
            text=True,
            cwd=work,
        )
        if archive.returncode != 0:
            raise AssertionError(
                f"zen build failed (exit {archive.returncode}):\n"
                f"{archive.stdout}\n{archive.stderr}"
            )
        undefined = subprocess.run(
            ["nm", "-u", str(object_path)], capture_output=True, text=True, cwd=work
        )
        if undefined.returncode != 0 or undefined.stdout.strip():
            raise AssertionError(
                "self-hosted lexer object must not import libc: "
                f"{undefined.stdout}; {undefined.stderr}"
            )
        cls.object_path = object_path

        driver = work / "lexer_driver"
        link = subprocess.run(
            [
                "cc", "-std=c11", "-O2", "-fno-pie", "-no-pie",
                str(DRIVER), str(object_path), "-o", str(driver),
            ],
            capture_output=True,
            text=True,
            cwd=work,
        )
        if link.returncode != 0:
            raise AssertionError(
                f"cc failed (exit {link.returncode}):\n{link.stdout}\n{link.stderr}"
            )
        cls.driver = driver

    def check_fixture(self, path):
        expected = reference_counts(path)
        actual = driver_counts(self.driver, path)
        self.assertEqual(actual["errors"], 0, f"{path}: reference fixture must be lexically valid")
        for name in COUNTERS:
            with self.subTest(fixture=path.name, counter=name):
                self.assertEqual(actual[name], expected[name], f"{path}: {name}")

    def test_hello(self):
        self.check_fixture(FIXTURES[0])

    def test_factorial(self):
        self.check_fixture(FIXTURES[1])

    def test_structs(self):
        self.check_fixture(FIXTURES[2])

    def test_vfs(self):
        self.check_fixture(FIXTURES[3])

    def test_synthetic_lexemes(self):
        work = Path(self.scratch.name)
        path = work / "synthetic_lexemes.zen"
        path.write_text(SYNTHETIC, encoding="utf-8")
        self.check_fixture(path)

    def test_object_has_no_libc_imports(self):
        self.assertTrue(self.object_path.is_file())
        result = subprocess.run(
            ["nm", "-u", str(self.object_path)], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "", "lexer.o must not import symbols")

    def test_error_counter(self):
        # `zen lex` stops on the first Error token, so these cases check the
        # report field directly instead of comparing with the reference.
        work = Path(self.scratch.name)
        cases = {
            "unexpected.zen": (b"$", {"tokens": 1, "errors": 1, "bytes": 1}),
            "comment.zen": (b"/* x", {"tokens": 1, "errors": 1, "bytes": 4}),
        }
        for name, (content, expected) in cases.items():
            with self.subTest(fixture=name):
                path = work / name
                path.write_bytes(content)
                actual = driver_counts(self.driver, path)
                for field, value in expected.items():
                    self.assertEqual(actual[field], value, f"{name}: {field}")


if __name__ == "__main__":
    unittest.main()
