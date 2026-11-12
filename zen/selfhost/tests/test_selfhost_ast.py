"""TASK-902C: verificacion del parser con AST real escrito en Zen.

El test compila `zen/selfhost/ast_parser.zen` como objeto freestanding con el
compilador `zen`, lo enlaza con `zen/selfhost/ast_driver.c` y comprueba:

* que >=40 expresiones validas coinciden en estado/valor con un parser
  recursivo de referencia implementado aqui (sin `eval` ni `ast`);
* que el AST no es decorativo: `nodes>0`, el checksum estructural es
  determinista entre ejecuciones, distingue estructuras distintas (aunque el
  valor coincida) y no cambia con espacios ni ceros a la izquierda;
* negativos de sintaxis, division/resto por cero y limite de profundidad;
* que el fuente Zen usa arrays fijos locales para kinds/values/lefts/rights y
  que el objeto no importa simbolos de libc (`nm -u` vacio).
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
SOURCE = ROOT / "zen/selfhost/ast_parser.zen"
DRIVER = ROOT / "zen/selfhost/ast_driver.c"

MASK = (1 << 64) - 1
OUTPUT_LINE = re.compile(
    r"status=([0-9]+) value=([0-9]+) nodes=([0-9]+) ast=([0-9]+)"
)

# Sonda auxiliar: el driver solo admite lineas de <=512 bytes y con esa cota el
# numero de nodos nunca supera los bytes de entrada, asi que el desbordamiento
# de la arena de 512 nodos solo se puede provocar llamando a zen_ast_eval con
# una entrada mas larga. La sonda no sustituye al driver: solo cubre la guarda.
PROBE_SOURCE = """
#include <stdint.h>
#include <stdio.h>
extern uint64_t zen_ast_eval(uint64_t text, uint64_t length, uint64_t out);
int main(void) {
    static char text[1025];
    uint64_t out[4] = {0, 0, 0, 0};
    for (int i = 0; i < 513; i++) {
        text[2 * i] = '1';
        if (i < 512) text[2 * i + 1] = '+';
    }
    zen_ast_eval((uint64_t)(uintptr_t)text, 1025, (uint64_t)(uintptr_t)out);
    printf("%llu %llu %llu %llu\\n", (unsigned long long)out[0],
           (unsigned long long)out[1], (unsigned long long)out[2],
           (unsigned long long)out[3]);
    return 0;
}
"""


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
    Aritmetica u64 modular; '/' y '%' fallan con estado 2 si el divisor es
    cero. Solo se usa con expresiones poco profundas: los casos de limite de
    profundidad se comprueban contra el contrato, no contra esta referencia.
    """

    WHITESPACE = " \t\r\n"
    MAX_DEPTH = 64

    def __init__(self, text):
        self.text = text
        self.pos = 0

    def parse(self):
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
        if depth > self.MAX_DEPTH:
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
    return ReferenceParser(expression).parse()


# 45 expresiones con AST estructuralmente distinto entre si: sirven tanto para
# comparar valor contra la referencia como para exigir checksums unicos.
VALID_EXPRESSIONS = [
    "0",
    "42",
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
    "1 + 2 * ( 3 - 4 )",
    "2*(3+4)",
    "10+20-5*2/2",
    "1+2+3+4+5",
    "2*3*4",
    "((2+3)*(4-1))",
    "1 -- 2",
    "18446744073709551615",
    "18446744073709551615+1",
    "99999999999999999999",
    "12345678901234567890+98765432109876543210",
    "4294967296*4294967296",
    "18446744073709551615/2",
    "18446744073709551615%10",
    "3 * ( 4 + 5 ) - 6 / 2",
    "(1+2)*(3+4)",
    "1+2*3-4/2",
    "2*(3+4*5)",
    "-((2*3)+4)",
    "((1+2)*(3-4))%5",
    "7%(2+1)",
    "100-50-25",
    "8/(2+2)",
]

SYNTAX_ERRORS = [
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
    "1/",
    "1 *",
    "1 -",
    "1(2)",
    "2(3)",
    "(1)2",
    "1+2)",
    "1+*2",
    "1+2(",
    "-",
]

DIVISION_BY_ZERO = [
    "1/0",
    "5%0",
    "1/(2-2)",
    "1/0+2",
    "1/2/0",
    "-(1/0)",
    "7%(3-3)",
    "18446744073709551615+1/0",
    "1%(2-2)",
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


class SelfHostAstTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ZEN.is_file():
            raise RuntimeError(
                f"falta el compilador {ZEN}; construyelo con: "
                "CARGO_HOME=\"$PWD/.cargo\" cargo build --release --offline "
                "--manifest-path zen/compiler/Cargo.toml"
            )
        cls._tmpdir = tempfile.TemporaryDirectory(prefix="zen-selfhost-ast-")
        cls.tmp = pathlib.Path(cls._tmpdir.name)
        cls.obj = cls.tmp / "ast_parser.o"
        cls.exe = cls.tmp / "ast_driver"
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

        probe_source = cls.tmp / "arena_probe.c"
        probe_source.write_text(PROBE_SOURCE, encoding="utf-8")
        cls.probe = cls.tmp / "arena_probe"
        probe_build = subprocess.run(
            [cls.cc, "-std=c11", "-O2", "-fno-pie", "-no-pie",
             str(probe_source), str(cls.obj), "-o", str(cls.probe)],
            cwd=str(ROOT), capture_output=True, text=True, timeout=120,
        )
        if probe_build.returncode != 0:
            raise RuntimeError(
                f"enlace de la sonda fallo:\n{probe_build.stdout}{probe_build.stderr}"
            )

    @classmethod
    def tearDownClass(cls):
        cls._tmpdir.cleanup()

    def run_fixture(self, expressions, name="fixture.txt"):
        fixture = self.tmp / name
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
            results.append(tuple(int(match.group(i)) for i in range(1, 5)))
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
        self.assertGreaterEqual(len(VALID_EXPRESSIONS), 40)
        results = self.run_fixture(VALID_EXPRESSIONS, "valid.txt")
        for expression, (status, value, nodes, ast) in zip(
                VALID_EXPRESSIONS, results):
            with self.subTest(expression=expression):
                self.assertEqual(
                    (status, value), reference(expression),
                    f"{expression!r}: Zen={status}/{value} "
                    f"referencia={reference(expression)}",
                )
                self.assertGreater(nodes, 0, f"{expression!r} no construyo AST")
                self.assertNotEqual(ast, 0, f"{expression!r} sin checksum")

    def test_ast_is_deterministic_and_distinct(self):
        first = self.run_fixture(VALID_EXPRESSIONS, "det-a.txt")
        second = self.run_fixture(VALID_EXPRESSIONS, "det-b.txt")
        self.assertEqual(first, second, "el AST no es determinista")
        asts = [ast for _, _, _, ast in first]
        self.assertEqual(
            len(set(asts)), len(asts),
            "dos expresiones con AST distinto comparten checksum: "
            f"{sorted(asts)}",
        )

    def test_ast_distinguishes_structure_with_equal_value(self):
        pairs = [
            ("1+2", "2+1"),
            ("1*2", "2*1"),
            ("10-3", "3-10"),
            ("1/2", "2/1"),
            ("(1+2)*3", "1+2*3"),
        ]
        flat = [expression for pair in pairs for expression in pair]
        results = self.run_fixture(flat, "structure.txt")
        for index, (left, right) in enumerate(pairs):
            left_result = results[2 * index]
            right_result = results[2 * index + 1]
            with self.subTest(pair=(left, right)):
                self.assertEqual(left_result[0], 0)
                self.assertEqual(right_result[0], 0)
                self.assertNotEqual(
                    left_result[3], right_result[3],
                    f"{left!r} y {right!r} comparten checksum",
                )

    def test_ast_ignores_whitespace_and_leading_zeros(self):
        expressions = [
            "1+2*3",
            " 1 + 2 * 3 ",
            "\t1\t+\t2\t*\t3\t",
            "01+002*0003",
        ]
        results = self.run_fixture(expressions, "formatting.txt")
        self.assertEqual(results[0][0], 0)
        self.assertEqual(results[0][1], 7)
        for expression, result in zip(expressions, results):
            with self.subTest(expression=expression):
                self.assertEqual(result, results[0])

    def test_precedence_and_associativity(self):
        expressions = list(PRECEDENCE_CASES)
        results = self.run_fixture(expressions, "precedence.txt")
        for expression, (status, value, nodes, _) in zip(expressions, results):
            with self.subTest(expression=expression):
                self.assertEqual(status, 0)
                self.assertEqual(value, PRECEDENCE_CASES[expression])
                self.assertGreater(nodes, 0)
                self.assertEqual(value, reference(expression)[1])

    def test_syntax_errors(self):
        results = self.run_fixture(SYNTAX_ERRORS, "syntax.txt")
        for expression, (status, value, nodes, ast) in zip(
                SYNTAX_ERRORS, results):
            with self.subTest(expression=expression):
                self.assertEqual(status, 1, f"{expression!r}: {status}")
                self.assertEqual(value, 0)
                self.assertEqual(nodes, 0)
                self.assertEqual(ast, 0)

    def test_division_by_zero(self):
        results = self.run_fixture(DIVISION_BY_ZERO, "div0.txt")
        for expression, (status, value, nodes, ast) in zip(
                DIVISION_BY_ZERO, results):
            with self.subTest(expression=expression):
                self.assertEqual(status, 2, f"{expression!r}: {status}")
                self.assertEqual(value, 0)
                # El AST se construyo antes de evaluar: el error es de eval y
                # el checksum estructural sigue disponible.
                self.assertGreater(nodes, 0)
                self.assertNotEqual(ast, 0)

    def test_depth_limit(self):
        cases = [
            ("("*128 + "1" + ")"*128, 0, 1),
            ("("*129 + "1" + ")"*129, 3, 0),
            ("("*200 + "1" + ")"*200, 3, 0),
            ("("*64 + "1+2" + ")"*64, 0, 3),
            ("("*128 + "1+2" + ")"*128, 3, 0),
            ("-"*128 + "7", 0, 7),
            ("-"*129 + "7", 3, 0),
            ("-"*300 + "7", 3, 0),
        ]
        self.assertTrue(all(len(case[0]) <= 512 for case in cases))
        results = self.run_fixture([case[0] for case in cases], "depth.txt")
        for (expression, expected_status, expected_value), result in zip(
                cases, results):
            with self.subTest(length=len(expression), expected=expected_status):
                self.assertEqual(result[0], expected_status)
                self.assertEqual(result[1], expected_value)
                self.assertLessEqual(len(expression), 512)

    def test_arena_boundary_512_nodes(self):
        # 512 bytes exactos: 256 unos, 255 '+' y un '-' unario => 512 nodos.
        # El unario solo afecta al primer operando: -1+1+...+1 = 254.
        expression = "-" + "+".join(["1"] * 256)
        self.assertEqual(len(expression), 512)
        results = self.run_fixture([expression], "arena.txt")
        status, value, nodes, ast = results[0]
        self.assertEqual(status, 0)
        self.assertEqual(nodes, 512)
        self.assertEqual(value, 254)
        self.assertNotEqual(ast, 0)
        # La referencia tambien evalua la expresion sin problemas.
        self.assertEqual((status, value), reference(expression))

    def test_arena_overflow_status_three(self):
        proc = subprocess.run(
            [str(self.probe)], capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.split(), ["3", "0", "0", "0"])

    def test_output_format_is_exact(self):
        proc = subprocess.run(
            [str(self.exe), str(self.tmp / "missing.txt")],
            capture_output=True, text=True, timeout=60,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, "")
        fixture = self.tmp / "format.txt"
        fixture.write_text("1+2\n", encoding="utf-8")
        proc = subprocess.run(
            [str(self.exe), str(fixture)],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertRegex(
            proc.stdout,
            r"\Astatus=0 value=3 nodes=3 ast=[1-9][0-9]*\n\Z",
        )

    def test_source_uses_local_fixed_arrays_and_traversal(self):
        source = SOURCE.read_text(encoding="utf-8")
        for token in ("[u8;", "[u64;", "[u32;", "kinds[", "values[",
                      "lefts[", "rights["):
            self.assertIn(token, source, f"falta {token!r} en ast_parser.zen")
        # El valor final debe salir del recorrido de la arena, no de reevaluar
        # la fuente: la fase de evaluacion indexa kinds/lefts/rights/values.
        for token in ("kinds[eval_index]", "lefts[eval_index]",
                      "rights[eval_index]", "values[eval_index]"):
            self.assertIn(token, source, f"falta el recorrido {token!r}")

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
