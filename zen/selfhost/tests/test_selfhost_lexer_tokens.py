"""TASK-902D: differential test of the materializing self-hosted Zen lexer.

For every fixture the test builds ``zen/selfhost/lexer_tokens.zen`` as a
freestanding ELF64 REL object, checks that it imports nothing, links it with
``zen/selfhost/lexer_tokens_driver.c`` and compares the whole token sequence
with the Rust reference lexer (``zen lex``):

* ``kind``  -> numeric id of the Rust ``TokenKind`` variant (KIND_IDS below).
* ``start``/``end`` -> byte span, identical to Rust.
* ``value`` -> FNV-1a 32 of the raw lexeme bytes for Ident/String/Char, the
  u32-saturated numeric value for Integer, 0 for everything else.

Documented exclusions (never silently skipped):

* ``Float``: only kind and span are compared; ``value`` is 0 because the Rust
  lexer prints an f64 and the contract stores a u32. The test still asserts
  that the driver writes 0 for float records.
* Escapes are NOT excluded: Ident/String/Char values hash the raw source
  bytes, so ``"\\n"`` (two bytes) and ``"\\x41"`` are compared exactly; the
  hash deliberately does not decode the literal.
* Integers that do not fit in u32: the C contract stores 0xFFFFFFFF
  (saturation), so both the test and the Zen lexer clamp. The literal
  ``4294967295`` and any larger integer therefore share ``value``.
* Integer literals above u128 are an Error token in Rust; the Zen lexer does
  not detect the u128 overflow and saturates instead. No fixture contains one.
* Unicode whitespace outside literals: Rust uses ``char::is_whitespace``; the
  Zen lexer only skips ASCII whitespace. Fixtures are ASCII outside string
  literals.
* ``Bool``, ``Null`` and ``Pipe2`` are never emitted by the Rust scanner.
  They are mapped in KIND_IDS so the table is total, but no fixture can
  exercise them.
* ``Error`` tokens: ``zen lex`` stops on the first Error token (non-zero
  exit), while the Zen lexer returns 0xFFFFFFFF and materializes nothing.
  Invalid inputs are tested for the 0xFFFFFFFF path only.

Run from the repository root:

    python3 -m unittest discover -s zen/selfhost/tests -p 'test_selfhost_lexer_tokens.py' -v
"""

import re
import struct
import subprocess
import tempfile
import unittest
from collections import namedtuple
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ZEN = ROOT / "zen" / "compiler" / "target" / "release" / "zen"
LEXER = ROOT / "zen" / "selfhost" / "lexer_tokens.zen"
DRIVER = ROOT / "zen" / "selfhost" / "lexer_tokens_driver.c"
TOKEN_RS = ROOT / "zen" / "compiler" / "src" / "lexer" / "token.rs"

MAX_TOKENS = 8192
U32_MAX = 0xFFFFFFFF

FIXTURES = [
    ROOT / "zen" / "examples" / "hello.zen",
    ROOT / "zen" / "examples" / "factorial.zen",
    ROOT / "zen" / "examples" / "structs.zen",
    ROOT / "zen" / "examples" / "arrays.zen",
    ROOT / "ferros" / "kernel" / "vfs.zen",
]

# Authoritative, stable mapping Rust TokenKind variant -> numeric kind.
# Must match the table documented in zen/selfhost/lexer_tokens.zen.
KIND_IDS = {
    # Literals, identifiers, special.
    "Integer": 1, "Float": 2, "Bool": 3, "Char": 4, "String": 5,
    "Null": 6, "Ident": 7,
    # Keywords.
    "Fn": 8, "Let": 9, "Mut": 10, "Const": 11, "If": 12, "Else": 13,
    "While": 14, "For": 15, "Return": 16, "Break": 17, "Continue": 18,
    "Struct": 19, "Impl": 20, "Mod": 21, "Use": 22, "Pub": 23, "As": 24,
    "Type": 25, "Enum": 26, "Match": 27, "Loop": 28, "Unsafe": 29,
    "Extern": 30, "Sizeof": 31, "Alignof": 32, "Offsetof": 33, "Cast": 34,
    "Transmute": 35, "True": 36, "False": 37,
    # Primitive types.
    "Void": 38, "Bool_": 39, "Char_": 40, "I8": 41, "I16": 42, "I32": 43,
    "I64": 44, "I128": 45, "Isize": 46, "U8": 47, "U16": 48, "U32": 49,
    "U64": 50, "U128": 51, "Usize": 52, "F32": 53, "F64": 54, "Never": 55,
    # Operators.
    "Plus": 56, "Minus": 57, "Star": 58, "Slash": 59, "Percent": 60,
    "StarStar": 61, "EqEq": 62, "NotEq": 63, "Lt": 64, "Gt": 65,
    "LtEq": 66, "GtEq": 67, "AndAnd": 68, "OrOr": 69, "Not": 70,
    "Amp": 71, "Pipe": 72, "Caret": 73, "Tilde": 74, "Shl": 75, "Shr": 76,
    "Assign": 77, "PlusEq": 78, "MinusEq": 79, "StarEq": 80,
    "SlashEq": 81, "PercentEq": 82, "AmpEq": 83, "PipeEq": 84,
    "CaretEq": 85, "ShlEq": 86, "ShrEq": 87, "Dot": 88, "DotDot": 89,
    "DotDotDot": 90, "Arrow": 91, "FatArrow": 92, "DoubleColon": 93,
    "Colon": 94, "Semi": 95, "Comma": 96, "LParen": 97, "RParen": 98,
    "LBracket": 99, "RBracket": 100, "LBrace": 101, "RBrace": 102,
    "Pipe2": 103, "Question": 104, "At": 105,
    # Special.
    "Eof": 106, "Error": 107,
    # Implemented only in the formatter's comment-preserving lexer mode; the
    # default scanner used by this comparison never emits it.
    "Comment": 108,
}
KIND_NAME = {value: name for name, value in KIND_IDS.items()}

# Synthetic lexemes-only fixture: exercises every reachable TokenKind (except
# Pipe2/Bool/Null, unreachable in the Rust scanner), all integer bases and
# suffixes, floats, simple/malformed-free escapes, UTF-8 string and char
# literals, and the full operator table. It is only lexed, never parsed.
SYNTHETIC = r'''// TASK-902D synthetic lexical fixture (lexed, never compiled).
/* block /* nested */ comment */
fn synthetic_tokens(a:u64, b:u8) -> u64 {
    let plain_ident = a;
    let _underscore = b;
    let keywords = fn let mut const if else while for return break continue;
    let keywords2 = struct impl mod use pub as type enum match loop unsafe extern;
    let keywords3 = sizeof alignof offsetof cast transmute true false;
    let types = void bool char i8 i16 i32 i64 i128 isize u8 u16 u32 u64 u128 usize f32 f64 never;
    let dec = 1_000u64;
    let dec_max = 4294967295;
    let dec_big = 4294967296u64;
    let hex = 0xDEAD_BEEFu64;
    let hex_big = 0x1_0000_0000u64;
    let bin = 0b1010u16;
    let oct = 0o755i32;
    let suffixed = 1i8 2i16 3i32 4i64 5i128 6isize 7u8 8u16 9u32 10u64 11u128 12usize;
    let flt = 3.5f64;
    let flt2 = 1e10;
    let flt3 = 0.5;
    let flt4 = 1E-3f32;
    let escaped = "quote:\" slash:\\ newline:\n tab:\t zero:\0 hex:\x41";
    let utf8 = "snowman:☃";
    let ch = 'x';
    let ch_escape = '\n';
    let ch_hex = '\x41';
    let ch_utf8 = 'é';
    let multi = ... <<= >>= == != <= >= && || += -= ** *= /= %= &= |= ^= << >> .. -> => ::;
    let single = + - * / % < > ! & | ^ ~ = . : ; , ( ) [ ] { } ? @;
    let ops = a ** 2 << 3 >> 1;
    let shl = a <<= 1;
    let path = a::b;
    if a == b as u64 && a != 0 || a <= 3 { return a; }
    return b;
}
'''

RustToken = namedtuple("RustToken", "kind start end line")
ZenToken = namedtuple("ZenToken", "kind start end value")

SPAN_RE = re.compile(r" (\d+)\.\.(\d+)$")
KIND_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)")
INTEGER_RE = re.compile(r"value: (\d+), base: (Binary|Octal|Decimal|Hex)")
DRIVER_RE = re.compile(
    r"^kind=(\d+) start=(\d+) end=(\d+) value=0x([0-9a-fA-F]{8})$"
)
TOKENS_STDERR_RE = re.compile(r"^tokens=(\d+)$", re.MULTILINE)


def fnv1a32(data):
    """FNV-1a 32-bit, same constants as zen/selfhost/lexer_tokens.zen."""
    value = 2166136261
    for byte in data:
        value = ((value ^ byte) * 16777619) & U32_MAX
    return value


def digit_for(byte):
    if 48 <= byte <= 57:
        return byte - 48
    if 97 <= byte <= 102:
        return byte - 87
    if 65 <= byte <= 70:
        return byte - 55
    return None


def integer_lexeme_value(lexeme):
    """Numeric value of an Integer token, saturated to u32.

    Mirrors the Zen lexer: base prefixes, '_' separators, stop at the suffix
    (the first byte that is not a digit of the base), clamp to 0xFFFFFFFF.
    """
    base = 10
    index = 0
    lowered = lexeme[:2].lower()
    if lowered == b"0x":
        base, index = 16, 2
    elif lowered == b"0b":
        base, index = 2, 2
    elif lowered == b"0o":
        base, index = 8, 2
    value = 0
    while index < len(lexeme):
        byte = lexeme[index]
        if byte == 95:  # '_'
            index += 1
            continue
        digit = digit_for(byte)
        if digit is None or digit >= base:
            break
        value = value * base + digit
        if value > U32_MAX:
            value = U32_MAX
        index += 1
    return value


def rust_enum_variants():
    """Variant names of `pub enum TokenKind` in the Rust lexer (read-only)."""
    text = TOKEN_RS.read_text(encoding="utf-8")
    text = "\n".join(line.split("//", 1)[0] for line in text.splitlines())
    marker = "pub enum TokenKind {"
    if marker not in text:
        raise AssertionError(f"cannot find {marker!r} in {TOKEN_RS}")
    body = text.split(marker, 1)[1]

    depth = 0
    end = None
    for index, char in enumerate(body):
        if char in "{([":
            depth += 1
        elif char in "})]":
            if depth == 0:
                end = index
                break
            depth -= 1
    if end is None:
        raise AssertionError("unterminated TokenKind enum")

    segments = []
    depth = 0
    start = 0
    for index, char in enumerate(body[:end]):
        if char in "{([":
            depth += 1
        elif char in "})]":
            depth -= 1
        elif char == "," and depth == 0:
            segments.append(body[start:index])
            start = index + 1
    segments.append(body[start:end])

    names = []
    for segment in segments:
        match = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)", segment)
        if match is not None:
            names.append(match.group(1))
    return names


def run_zen_lex(path):
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
    return result.stdout


def rust_tokens(path):
    tokens = []
    eof_seen = False
    for line in run_zen_lex(path).splitlines():
        kind_match = KIND_RE.match(line)
        span_match = SPAN_RE.search(line)
        if kind_match is None or span_match is None:
            raise AssertionError(f"cannot parse zen lex line: {line!r}")
        kind = kind_match.group(1)
        if kind not in KIND_IDS:
            raise AssertionError(f"unmapped Rust TokenKind {kind!r} in {line!r}")
        if kind == "Eof":
            eof_seen = True
            break
        tokens.append(
            RustToken(kind, int(span_match.group(1)), int(span_match.group(2)), line)
        )
    if not eof_seen:
        raise AssertionError(f"{path}: zen lex output has no Eof token")
    return tokens


def driver_tokens(driver, path, max_tokens=MAX_TOKENS):
    result = subprocess.run(
        [str(driver), str(path), str(max_tokens)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"lexer_tokens_driver failed on {path} (exit {result.returncode}):\n"
            f"{result.stderr}"
        )
    tokens = []
    for line in result.stdout.splitlines():
        match = DRIVER_RE.match(line)
        if match is None:
            raise AssertionError(f"cannot parse driver line: {line!r}")
        tokens.append(
            ZenToken(
                int(match.group(1)),
                int(match.group(2)),
                int(match.group(3)),
                int(match.group(4), 16),
            )
        )
    count_match = TOKENS_STDERR_RE.search(result.stderr)
    if count_match is None:
        raise AssertionError(f"driver did not report tokens=: {result.stderr!r}")
    reported = int(count_match.group(1))
    if reported != len(tokens):
        raise AssertionError(
            f"driver returned {reported} tokens but printed {len(tokens)} lines"
        )
    return tokens


def expected_value(source, token):
    """Expected record value for a Rust token, or None when excluded."""
    if token.kind == "Ident":
        return fnv1a32(source[token.start:token.end])
    if token.kind in ("String", "Char"):
        inner = source[token.start + 1:token.end - 1]
        return fnv1a32(inner)
    if token.kind == "Integer":
        return integer_lexeme_value(source[token.start:token.end])
    if token.kind == "Float":
        return None
    return 0


class SelfhostLexerTokensTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ZEN.is_file():
            raise unittest.SkipTest(f"missing prebuilt compiler: {ZEN}")
        cls.scratch = tempfile.TemporaryDirectory(prefix="zen-selfhost-lexer-tokens-")
        cls.addClassCleanup(cls.scratch.cleanup)
        work = Path(cls.scratch.name)

        object_path = work / "lexer_tokens.o"
        build = subprocess.run(
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
        if build.returncode != 0:
            raise AssertionError(
                f"zen build failed (exit {build.returncode}):\n"
                f"{build.stdout}\n{build.stderr}"
            )
        cls.object_path = object_path

        driver = work / "lexer_tokens_driver"
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

        synthetic = work / "synthetic_tokens.zen"
        synthetic.write_text(SYNTHETIC, encoding="utf-8")
        cls.synthetic = synthetic

    def check_fixture(self, path):
        source = path.read_bytes()
        rust = rust_tokens(path)
        zen = driver_tokens(self.driver, path)
        self.assertEqual(
            len(zen), len(rust),
            f"{path}: token count (driver vs zen lex)",
        )
        for index, (reference, actual) in enumerate(zip(rust, zen)):
            with self.subTest(fixture=path.name, index=index, kind=reference.kind):
                self.assertEqual(
                    actual.kind, KIND_IDS[reference.kind],
                    f"{path}: token {index} kind {reference.kind!r} "
                    f"({reference.line!r})",
                )
                self.assertEqual(
                    (actual.start, actual.end),
                    (reference.start, reference.end),
                    f"{path}: token {index} span ({reference.line!r})",
                )
                self.assertLessEqual(actual.start, actual.end)
                self.assertLessEqual(actual.end, len(source))
                expected = expected_value(source, reference)
                if reference.kind == "Integer":
                    match = INTEGER_RE.search(reference.line)
                    self.assertIsNotNone(
                        match, f"{path}: no integer value in {reference.line!r}"
                    )
                    rust_value = int(match.group(1))
                    self.assertEqual(
                        expected, min(rust_value, U32_MAX),
                        f"{path}: Python integer parse disagrees with Rust "
                        f"for {reference.line!r}",
                    )
                if expected is None:
                    # Float: value excluded, but the contract still mandates 0.
                    self.assertEqual(
                        actual.value, 0,
                        f"{path}: float token {index} must store value 0",
                    )
                else:
                    self.assertEqual(
                        actual.value, expected,
                        f"{path}: token {index} value ({reference.line!r})",
                    )
        return len(rust)

    def test_hello(self):
        self.assertGreater(self.check_fixture(FIXTURES[0]), 0)

    def test_factorial(self):
        self.assertGreater(self.check_fixture(FIXTURES[1]), 0)

    def test_structs(self):
        self.assertGreater(self.check_fixture(FIXTURES[2]), 0)

    def test_arrays(self):
        self.assertGreater(self.check_fixture(FIXTURES[3]), 0)

    def test_vfs_thousands_of_tokens(self):
        count = self.check_fixture(FIXTURES[4])
        self.assertGreater(count, 2000, "vfs.zen must exercise thousands of tokens")

    def test_synthetic_all_reachable_kinds(self):
        count = self.check_fixture(self.synthetic)
        self.assertGreater(count, 150)
        kinds = {token.kind for token in driver_tokens(self.driver, self.synthetic)}
        # Every reachable variant of the Rust scanner appears at least once.
        expected = set(KIND_IDS.values()) - {
            KIND_IDS["Bool"], KIND_IDS["Null"], KIND_IDS["Pipe2"],
            KIND_IDS["Eof"], KIND_IDS["Error"], KIND_IDS["Comment"],
        }
        missing = sorted(KIND_NAME[kind] for kind in expected - kinds)
        self.assertEqual(missing, [], f"synthetic fixture misses kinds: {missing}")

    def test_kind_table_matches_rust_enum(self):
        variants = rust_enum_variants()
        self.assertIn("Integer", variants)
        self.assertIn("Pipe2", variants)
        self.assertEqual(
            set(KIND_IDS), set(variants),
            "KIND_IDS must map every TokenKind variant (and nothing else)",
        )
        self.assertEqual(
            len(set(KIND_IDS.values())), len(KIND_IDS),
            "KIND_IDS numeric ids must be unique",
        )
        self.assertEqual(KIND_IDS["Eof"], 106)
        self.assertEqual(KIND_IDS["Error"], 107)

    def test_object_is_elf64_rel_without_imports(self):
        data = self.object_path.read_bytes()
        self.assertEqual(data[:4], b"\x7fELF", "object must be ELF")
        self.assertEqual(data[4], 2, "ELFCLASS64")
        self.assertEqual(data[5], 1, "ELFDATA2LSB")
        self.assertEqual(struct.unpack_from("<H", data, 16)[0], 1, "ET_REL")
        self.assertEqual(struct.unpack_from("<H", data, 18)[0], 62, "EM_X86_64")

        undefined = subprocess.run(
            ["nm", "-u", str(self.object_path)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(undefined.returncode, 0, undefined.stderr)
        self.assertEqual(
            undefined.stdout.strip(), "",
            f"lexer_tokens.o must not import symbols:\n{undefined.stdout}",
        )

    def test_capacity_boundary(self):
        path = FIXTURES[0]
        reference = rust_tokens(path)
        # Exactly the token count fits; one less overflows with 0xFFFFFFFF.
        self.assertEqual(
            len(driver_tokens(self.driver, path, max_tokens=len(reference))),
            len(reference),
        )
        result = subprocess.run(
            [str(self.driver), str(path), str(len(reference) - 1)],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertIn("error=0xffffffff", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_empty_and_comment_only_sources(self):
        work = Path(self.scratch.name)
        cases = {
            "empty.zen": b"",
            "comments.zen": b"// line\n/* block /* nested */ */\n\n",
        }
        for name, content in cases.items():
            with self.subTest(fixture=name):
                path = work / name
                path.write_bytes(content)
                self.assertEqual(driver_tokens(self.driver, path), [])

    def test_unrecoverable_lexical_errors(self):
        work = Path(self.scratch.name)
        cases = {
            "unexpected.zen": b"$",
            "string.zen": b'let x = "unterminated',
            "comment.zen": b"/* unterminated",
            "suffix.zen": b"let x = 1z;",
            "escape.zen": b'let x = "bad\\q";',
        }
        for name, content in cases.items():
            with self.subTest(fixture=name):
                path = work / name
                path.write_bytes(content)
                result = subprocess.run(
                    [str(self.driver), str(path), str(MAX_TOKENS)],
                    capture_output=True,
                    text=True,
                    cwd=ROOT,
                )
                self.assertEqual(result.returncode, 3, result.stderr)
                self.assertIn("error=0xffffffff", result.stderr)
                self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
