"""TASK-902B: verificacion del evaluador de expresiones escrito en Zen.

El test compila `zen/selfhost/parser.zen` como objeto freestanding con el
compilador `zen`, lo enlaza con `zen/selfhost/parser_driver.c` y compara la
salida del binario con un parser recursivo de referencia implementado aqui en
Python. La referencia NO usa `eval` ni `ast`: tokeniza y evalua a mano con la
misma gramatica, la misma aritmetica modular u64 y el mismo limite de
profundidad que exige el contrato.
"""
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
ZEN = ROOT / "zen/compiler/target/release/zen"
SOURCE = ROOT / "zen/selfhost/parser.zen"
DRIVER = ROOT / "zen/selfhost/parser_driver.c"

MASK = (1 << 64) - 1
MAX_DEPTH = 64
OUTPUT_LINE = re.compile(r"status=([0-9]+) value=([0-9]+)")


class ReferenceError(Exception):
    """Error del parser de referencia con el estado del contrato."""

    def __init__(self, status):
        super().__init__(status)
        self.status = status


class ReferenceParser:
    """Parser/evaluador recursivo independiente, sin `eval`.

    Gramatica:
      expr   := term (('+'|'-') term)*
      term   := factor (('*'|'/'|'%') factor)*
      factor := number | '(' expr ')' | '-' factor
    Aritmetica u64 con envoltura en complemento a dos; '/' y '%' son enteros
    sin signo y fallan con estado 2 si el divisor es cero. Cada nivel de
    parentesis o de '-' unario incrementa la profundidad; factor falla con
    estado 3 cuando depth > 64.
    """

    WHITESPACE = " \t\r\n"

    def __init__(self, text):
        self.text = text
        self.pos = 0

    def parse(self):
        """Devuelve (estado, valor). En error el valor es 0, como el contrato."""
        try:
            value = self._expr(0)
            self._skip()
            if self.pos != len(self.text):
                raise ReferenceError(1)
            return 0, value & MASK
        except ReferenceError as exc:
            return exc.status, 0

    def _skip(self):
        while self.pos < len(self.text) and self.text[self.pos] in self.WHITESPACE:
            self.pos += 1

    def _peek(self):
        if self.pos >= len(self.text):
            return ""
        return self.text[self.pos]

    def _expr(self, depth):
        value = self._term(depth)
        while True:
            self._skip()
            op = self._peek()
            if op not in ("+", "-"):
                return value & MASK
            self.pos += 1
            rhs = self._term(depth)
            if op == "+":
                value = (value + rhs) & MASK
            else:
                value = (value - rhs) & MASK

    def _term(self, depth):
        value = self._factor(depth)
        while True:
            self._skip()
            op = self._peek()
            if op not in ("*", "/", "%"):
                return value & MASK
            self.pos += 1
            rhs = self._factor(depth)
            if op == "*":
                value = (value * rhs) & MASK
            elif op == "/":
                if rhs == 0:
                    raise ReferenceError(2)
                value = value // rhs
            else:
                if rhs == 0:
                    raise ReferenceError(2)
                value = value % rhs

    def _factor(self, depth):
        self._skip()
        if depth > MAX_DEPTH:
            raise ReferenceError(3)
        char = self._peek()
        if char.isdigit() and char.isascii():
            value = 0
            while self.pos < len(self.text) and self.text[self.pos].isascii() \
                    and self.text[self.pos].isdigit():
                value = (value * 10 + int(self.text[self.pos])) & MASK
                self.pos += 1
            return value
        if char == "(":
            self.pos += 1
            value = self._expr(depth + 1)
            self._skip()
            if self._peek() != ")":
                raise ReferenceError(1)
            self.pos += 1
            return value
        if char == "-":
            self.pos += 1
            value = self._factor(depth + 1)
            return (-value) & MASK
        raise ReferenceError(1)


def reference(expression):
    """Atajo: (estado, valor) segun la referencia independiente."""
    return ReferenceParser(expression).parse()


VALID_EXPRESSIONS = [
    "0",
    "42",
    "  7  ",
    "00042",
    "1+2",
    "1+2*3",
    "(1+2)*3",
    "2*3+4*5",
    "20-5*2",
    "10-3-2",
    "100/7",
    "100%7",
    "100/7/2",
    "100/(7/2)",
    "8%3*2",
    "8%(3*2)",
    "7/2*2",
    "1-2-3",
    "0-1",
    "2*-3",
    "-5",
    "--5",
    "-(2+3)",
    "-2*3",
    "((((1))))",
    "1 + 2 * ( 3 - 4 )",
    "\t9\t*\t9\t",
    "2*(3+4)",
    "10+20-5*2/2",
    "1+2+3+4+5",
    "2*3*4",
    "((2+3)*(4-1))",
    "1 -- 2",
    "((((((((((1))))))))))",
    "18446744073709551615",
    "18446744073709551615+1",
    "18446744073709551616",
    "99999999999999999999",
    "12345678901234567890+98765432109876543210",
    "4294967296*4294967296",
    "18446744073709551615/2",
    "18446744073709551615%10",
    "3 * ( 4 + 5 ) - 6 / 2",
]

ERROR_EXPRESSIONS = [
    "",
    "   ",
    "(1+2",
    "1+",
    "+1",
    "1 2",
    "()",
    "abc",
    "1..2",
    "1)",
    "2+*3",
    "((2)",
    "1++2",
    "1%%2",
    "1/0",
    "5%0",
    "1/(2-2)",
    "1/0+2",
    "1/2/0",
    "-(1/0)",
    "7%(3-3)",
    "18446744073709551615+1/0",
    "(((1+2))",
    "1 /",
    "1 *",
    "1 -",
]

PRECEDENCE_CASES = {
    "2+3*4": 14,
    "(2+3)*4": 20,
    "10-3-2": 5,
    "100/5/2": 10,
    "100/(5/2)": 50,
    "2*3+4*5": 26,
    "20-5*2": 10,
    "8%3*2": 4,
    "8%(3*2)": 2,
    "10+20-5*2/2": 25,
    "7/2*2": 6,
    "7%(2+1)": 1,
    "1+2+3+4+5": 15,
    "2*3*4": 24,
    "100-50-25": 25,
    "-2*3": (MASK - 5),
    "2*-3": (MASK - 5),
    "-(2+3)": (MASK - 4),
    "1-2-3": (MASK - 3),
    "2*(3+4)": 14,
}


class SelfHostParserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ZEN.is_file():
            raise RuntimeError(
                f"falta el compilador {ZEN}; construyelo con: "
                "CARGO_HOME=\"$PWD/.cargo\" cargo build --release --offline "
                "--manifest-path zen/compiler/Cargo.toml"
            )
        cls._tmpdir = tempfile.TemporaryDirectory(prefix="zen-selfhost-parser-")
        cls.tmp = pathlib.Path(cls._tmpdir.name)
        cls.obj = cls.tmp / "parser.o"
        cls.exe = cls.tmp / "parser_driver"
        cls.cc = os.environ.get("CC", "cc")

        build = subprocess.run(
            [str(ZEN), "build", str(SOURCE), "--target", "x86_64-unknown-none",
             "--emit", "obj", "-o", str(cls.obj)],
            cwd=str(ROOT), capture_output=True, text=True, timeout=120,
        )
        if build.returncode != 0:
            raise RuntimeError(f"zen build fallo:\n{build.stdout}{build.stderr}")

        link = subprocess.run(
            [cls.cc, "-std=c11", "-O2", "-fno-pie", "-no-pie",
             str(DRIVER), str(cls.obj), "-o", str(cls.exe)],
            cwd=str(ROOT), capture_output=True, text=True, timeout=120,
        )
        if link.returncode != 0:
            raise RuntimeError(f"enlace fallo:\n{link.stdout}{link.stderr}")

    @classmethod
    def tearDownClass(cls):
        cls._tmpdir.cleanup()

    def run_fixture(self, expressions):
        fixture = self.tmp / "fixture.txt"
        fixture.write_text(
            "\n".join(expressions) + ("\n" if expressions else ""),
            encoding="utf-8",
        )
        proc = subprocess.run(
            [str(self.exe), str(fixture)],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        lines = proc.stdout.splitlines()
        self.assertEqual(
            len(lines), len(expressions),
            f"se esperaban {len(expressions)} lineas, salida:\n{proc.stdout}",
        )
        results = []
        for line in lines:
            match = OUTPUT_LINE.fullmatch(line)
            self.assertIsNotNone(match, f"formato inesperado: {line!r}")
            results.append((int(match.group(1)), int(match.group(2))))
        return results

    def test_reference_parser_is_independent_and_correct(self):
        checks = {
            "2+3*4": 14,
            "10-3-2": 5,
            "100/7": 14,
            "100%7": 2,
            "2*(3+4)": 14,
            "-5": MASK - 4,
            "18446744073709551615+1": 0,
        }
        for expression, expected in checks.items():
            self.assertEqual(reference(expression), (0, expected), expression)
        self.assertEqual(reference("1/0"), (2, 0))
        self.assertEqual(reference("5%0"), (2, 0))
        self.assertEqual(reference("(1+2"), (1, 0))
        self.assertEqual(reference(""), (1, 0))

    def test_valid_expressions_match_reference(self):
        self.assertGreaterEqual(len(VALID_EXPRESSIONS), 30)
        results = self.run_fixture(VALID_EXPRESSIONS)
        for expression, (status, value) in zip(VALID_EXPRESSIONS, results):
            with self.subTest(expression=expression):
                self.assertEqual(
                    (status, value), reference(expression),
                    f"{expression!r}: Zen={status}/{value} "
                    f"referencia={reference(expression)}",
                )

    def test_error_expressions_match_reference(self):
        results = self.run_fixture(ERROR_EXPRESSIONS)
        for expression, (status, value) in zip(ERROR_EXPRESSIONS, results):
            with self.subTest(expression=expression):
                self.assertNotEqual(status, 0)
                self.assertEqual(
                    (status, value), reference(expression),
                    f"{expression!r}: Zen={status}/{value} "
                    f"referencia={reference(expression)}",
                )

    def test_precedence_and_associativity(self):
        expressions = list(PRECEDENCE_CASES)
        results = self.run_fixture(expressions)
        for expression, (status, value) in zip(expressions, results):
            with self.subTest(expression=expression):
                self.assertEqual(status, 0)
                self.assertEqual(value, PRECEDENCE_CASES[expression])
                self.assertEqual(value, reference(expression)[1])

    def test_depth_limit(self):
        cases = [
            ("(" * 64 + "1" + ")" * 64, 0),
            ("(" * 65 + "1" + ")" * 65, 3),
            ("(" * 200 + "1" + ")" * 200, 3),
            ("-" * 64 + "7", 0),
            ("-" * 65 + "7", 3),
            ("-" * 200 + "7", 3),
        ]
        results = self.run_fixture([expression for expression, _ in cases])
        for (expression, expected_status), (status, value) in zip(cases, results):
            with self.subTest(levels=len(expression), expected=expected_status):
                self.assertEqual(status, expected_status)
                self.assertEqual((status, value), reference(expression))
                self.assertEqual(value, 0 if expected_status else reference(expression)[1])

    def test_output_format_is_exact(self):
        proc = subprocess.run(
            [str(self.exe), str(self.tmp / "format.txt")],
            capture_output=True, text=True, timeout=60,
        )
        # El fichero aun no existe: el driver debe fallar sin escribir stdout.
        self.assertNotEqual(proc.returncode, 0)
        (self.tmp / "format.txt").write_text("1+2\n", encoding="utf-8")
        proc = subprocess.run(
            [str(self.exe), str(self.tmp / "format.txt")],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, "status=0 value=3\n")

    @unittest.skipUnless(shutil.which("nm"), "nm no disponible")
    def test_object_has_no_libc_imports(self):
        proc = subprocess.run(
            ["nm", "-u", str(self.obj)],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "",
                         f"simbolos sin resolver: {proc.stdout}")


if __name__ == "__main__":
    unittest.main()
