"""TASK-902E: verificacion del interprete de sentencias escrito en Zen.

El test compila `zen/selfhost/interp.zen` como objeto freestanding con el
compilador `zen`, lo enlaza con `zen/selfhost/interp_driver.c` y compara,
programa a programa, la salida del interprete Zen con una implementacion de
referencia independiente escrita aqui (scanner + parser recursivo + evaluador,
sin la funcion `eval` de Python).

Cubre:
* >=30 programas validos (variables, if/else anidados, while, precedencia,
  comparaciones encadenadas, envolvente u64, impresion decimal);
* errores de ejecucion (division/resto por cero, variable desconocida) con
  contador de sentencias, hash y bytes ya producidos;
* errores de sintaxis (siempre out[1..3] a cero);
* limites fijos: 256 nodos AST, profundidad 32 (parentesis/unarios y bloques),
  16 variables, 256 bytes impresos;
* que el objeto Zen no importa simbolos de libc (`nm -u` vacio) y que el
  estado vive en arrays fijos locales.
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
SOURCE = ROOT / "zen/selfhost/interp.zen"
DRIVER = ROOT / "zen/selfhost/interp_driver.c"

MASK = (1 << 64) - 1
FNV_OFFSET = 2166136261
FNV_PRIME = 16777619
OUTPUT_LINE = re.compile(
    r"status=([0-9]+) statements=([0-9]+) hash=([0-9]+) bytes=([0-9]+)"
)


def fnv1a32(data):
    """FNV-1a de 32 bits sobre bytes; independiente del interprete Zen."""
    value = FNV_OFFSET
    for byte in data:
        value = ((value ^ byte) * FNV_PRIME) & 0xFFFFFFFF
    return value


class RefError(Exception):
    """Error del interprete de referencia con el estado del contrato."""

    def __init__(self, status):
        super().__init__(status)
        self.status = status


# ---------------------------------------------------------------------------
# Referencia: scanner
# ---------------------------------------------------------------------------
KEYWORDS = {
    "let": "let",
    "print": "print",
    "if": "if",
    "else": "else",
    "while": "while",
}
TWO_CHAR_OPERATORS = {
    "==": "eq",
    "!=": "ne",
    "<=": "le",
    ">=": "ge",
}
ONE_CHAR_OPERATORS = {
    "=": "assign",
    "<": "lt",
    ">": "gt",
    "+": "plus",
    "-": "minus",
    "*": "star",
    "/": "slash",
    "%": "percent",
    "(": "lparen",
    ")": "rparen",
    "{": "lbrace",
    "}": "rbrace",
    ";": "semi",
}
WHITESPACE = " \t\r\n\v\f"


def _is_digit(char):
    return "0" <= char <= "9"


def _is_alpha(char):
    return ("a" <= char <= "z") or ("A" <= char <= "Z")


def _is_ident(char):
    return _is_alpha(char) or _is_digit(char) or char == "_"


class RefLexer:
    """Scanner independiente; devuelve tokens (kind, valor) y aplica el tope
    defensivo de 1024 tokens del contrato."""

    def __init__(self, text):
        self.text = text

    def tokenize(self):
        tokens = []
        text = self.text
        pos = 0
        length = len(text)
        while pos < length:
            char = text[pos]
            if char in WHITESPACE:
                pos += 1
            elif _is_digit(char):
                value = 0
                while pos < length and _is_digit(text[pos]):
                    value = (value * 10 + int(text[pos])) & MASK
                    pos += 1
                self._push(tokens, "num", value)
            elif _is_alpha(char) or char == "_":
                start = pos
                pos += 1
                while pos < length and _is_ident(text[pos]):
                    pos += 1
                word = text[start:pos]
                kind = KEYWORDS.get(word, "ident")
                self._push(tokens, kind, word if kind == "ident" else None)
            else:
                pair = text[pos:pos + 2]
                if pair in TWO_CHAR_OPERATORS:
                    self._push(tokens, TWO_CHAR_OPERATORS[pair], None)
                    pos += 2
                elif char in ONE_CHAR_OPERATORS:
                    self._push(tokens, ONE_CHAR_OPERATORS[char], None)
                    pos += 1
                else:
                    raise RefError(1)
        return tokens

    @staticmethod
    def _push(tokens, kind, value):
        if len(tokens) >= 1024:
            raise RefError(4)
        tokens.append((kind, value))


# ---------------------------------------------------------------------------
# Referencia: parser recursivo (sin recursion compartida con el Zen)
# ---------------------------------------------------------------------------
COMPARISONS = frozenset(("lt", "le", "gt", "ge", "eq", "ne"))
ADDITIVE = frozenset(("plus", "minus"))
MULTIPLICATIVE = frozenset(("star", "slash", "percent"))
MAX_NODES = 256
MAX_DEPTH = 32


class RefParser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0
        self.nodes = 0

    # -- utilidades de tokens ------------------------------------------------
    def peek(self):
        if self.pos >= len(self.tokens):
            return (None, None)
        return self.tokens[self.pos]

    def take(self):
        token = self.peek()
        if token[0] is None:
            raise RefError(1)
        self.pos += 1
        return token

    def expect(self, kind):
        token = self.take()
        if token[0] != kind:
            raise RefError(1)
        return token

    def add_node(self):
        if self.nodes >= MAX_NODES:
            raise RefError(4)
        self.nodes += 1

    # -- programa / sentencias ----------------------------------------------
    def parse_program(self):
        statements = []
        while self.pos < len(self.tokens):
            if self.peek()[0] == "rbrace":
                raise RefError(1)
            statements.append(self.statement(0))
        return statements

    def parse_body(self, depth):
        if depth > MAX_DEPTH:
            raise RefError(4)
        statements = []
        while True:
            kind = self.peek()[0]
            if kind is None or kind == "rbrace":
                return statements
            statements.append(self.statement(depth))

    def statement(self, depth):
        kind = self.peek()[0]
        if kind == "let":
            self.take()
            name = self.expect("ident")[1]
            self.expect("assign")
            expression = self.expression(depth)
            self.expect("semi")
            self.add_node()
            return ("let", name, expression)
        if kind == "ident":
            name = self.take()[1]
            self.expect("assign")
            expression = self.expression(depth)
            self.expect("semi")
            self.add_node()
            return ("assign", name, expression)
        if kind == "print":
            self.take()
            expression = self.expression(depth)
            self.expect("semi")
            self.add_node()
            return ("print", expression)
        if kind == "if":
            self.take()
            condition = self.expression(depth)
            self.expect("lbrace")
            self.add_node()
            body = self.parse_body(depth + 1)
            self.expect("rbrace")
            other = []
            if self.peek()[0] == "else":
                self.take()
                self.expect("lbrace")
                other = self.parse_body(depth + 1)
                self.expect("rbrace")
            return ("if", condition, body, other)
        if kind == "while":
            self.take()
            condition = self.expression(depth)
            self.expect("lbrace")
            self.add_node()
            body = self.parse_body(depth + 1)
            self.expect("rbrace")
            return ("while", condition, body)
        raise RefError(1)

    # -- expresiones --------------------------------------------------------
    def expression(self, depth):
        node = self.additive(depth)
        while self.peek()[0] in COMPARISONS:
            operator = self.take()[0]
            right = self.additive(depth)
            self.add_node()
            node = ("bin", operator, node, right)
        return node

    def additive(self, depth):
        node = self.multiplicative(depth)
        while self.peek()[0] in ADDITIVE:
            operator = self.take()[0]
            right = self.multiplicative(depth)
            self.add_node()
            node = ("bin", operator, node, right)
        return node

    def multiplicative(self, depth):
        node = self.unary(depth)
        while self.peek()[0] in MULTIPLICATIVE:
            operator = self.take()[0]
            right = self.unary(depth)
            self.add_node()
            node = ("bin", operator, node, right)
        return node

    def unary(self, depth):
        if depth > MAX_DEPTH:
            raise RefError(4)
        kind = self.peek()[0]
        if kind == "minus":
            self.take()
            child = self.unary(depth + 1)
            self.add_node()
            return ("un", child)
        if kind == "lparen":
            self.take()
            node = self.expression(depth + 1)
            self.expect("rparen")
            return node
        if kind == "num":
            value = self.take()[1]
            self.add_node()
            return ("num", value)
        if kind == "ident":
            name = self.take()[1]
            self.add_node()
            return ("var", name)
        raise RefError(1)


# ---------------------------------------------------------------------------
# Referencia: evaluador
# ---------------------------------------------------------------------------
class RefRuntime:
    def __init__(self):
        self.variables = {}
        self.executed = 0
        self.hash = FNV_OFFSET
        self.outbytes = 0

    def run(self, statements):
        status = 0
        try:
            self.exec_block(statements)
        except RefError as error:
            status = error.status
        return (status, self.executed, self.hash, self.outbytes)

    def exec_block(self, statements):
        for statement in statements:
            self.exec_statement(statement)

    def exec_statement(self, statement):
        self.executed += 1
        kind = statement[0]
        if kind == "let":
            name = statement[1]
            value = self.value_of(statement[2])
            if name in self.variables:
                self.variables[name] = value
            elif len(self.variables) >= 16:
                raise RefError(4)
            else:
                self.variables[name] = value
        elif kind == "assign":
            name = statement[1]
            value = self.value_of(statement[2])
            if name not in self.variables:
                raise RefError(3)
            self.variables[name] = value
        elif kind == "print":
            value = self.value_of(statement[1])
            text = str(value).encode("ascii")
            if self.outbytes + len(text) + 1 > 256:
                raise RefError(4)
            for byte in text:
                self.hash = ((self.hash ^ byte) * FNV_PRIME) & 0xFFFFFFFF
            self.hash = ((self.hash ^ 10) * FNV_PRIME) & 0xFFFFFFFF
            self.outbytes += len(text) + 1
        elif kind == "if":
            if self.value_of(statement[1]) != 0:
                self.exec_block(statement[2])
            else:
                self.exec_block(statement[3])
        elif kind == "while":
            while True:
                if self.value_of(statement[1]) != 0:
                    self.exec_block(statement[2])
                    self.executed += 1
                else:
                    break
        else:  # pragma: no cover - el parser solo produce estos kinds
            raise RefError(1)

    def value_of(self, node):
        kind = node[0]
        if kind == "num":
            return node[1]
        if kind == "var":
            if node[1] not in self.variables:
                raise RefError(3)
            return self.variables[node[1]]
        if kind == "un":
            return (-self.value_of(node[1])) & MASK
        operator = node[1]
        left = self.value_of(node[2])
        right = self.value_of(node[3])
        if operator == "plus":
            return (left + right) & MASK
        if operator == "minus":
            return (left - right) & MASK
        if operator == "star":
            return (left * right) & MASK
        if operator == "slash":
            if right == 0:
                raise RefError(2)
            return left // right
        if operator == "percent":
            if right == 0:
                raise RefError(2)
            return left % right
        if operator == "lt":
            return 1 if left < right else 0
        if operator == "le":
            return 1 if left <= right else 0
        if operator == "gt":
            return 1 if left > right else 0
        if operator == "ge":
            return 1 if left >= right else 0
        if operator == "eq":
            return 1 if left == right else 0
        if operator == "ne":
            return 1 if left != right else 0
        raise RefError(1)  # pragma: no cover


def reference(program):
    """Ejecuta `program` con la referencia; devuelve (status, sentencias,
    hash, bytes) con la misma semantica que zen_interp."""
    try:
        tokens = RefLexer(program).tokenize()
        statements = RefParser(tokens).parse_program()
    except RefError as error:
        return (error.status, 0, 0, 0)
    return RefRuntime().run(statements)


# ---------------------------------------------------------------------------
# Programas de prueba
# ---------------------------------------------------------------------------
PROGRAMS = [
    ("empty", ""),
    ("whitespace", " \t\r\n\v\f "),
    ("print_literal", "print 42;"),
    ("print_zero", "print 0;"),
    ("print_multi", "print 1; print 2; print 3;"),
    ("precedence", "print 2+3*4; print (2+3)*4;"),
    ("associativity", "print 10-3-2; print 100/7/2; print 8%3*2;"),
    ("modulo", "print 100%7; print 18446744073709551615%10;"),
    ("comparisons_true",
     "print 1<2; print 1<=1; print 2>1; print 2>=2; print 3==3; print 3!=4;"),
    ("comparisons_false",
     "print 2<1; print 2<=1; print 1>2; print 1>=2; print 3==4; print 3!=3;"),
    ("comparison_precedence",
     "print 1+2<4; print 2*3==6; print 1<2==1;"),
    ("unary_minus",
     "print -5; print -2*3; print 2*-3; print --5; print -(2+3);"),
    ("wrapping",
     "print 18446744073709551615+1; print 0-1; "
     "print 18446744073709551615*2; print 4294967296*4294967296;"),
    ("big_literal", "print 99999999999999999999;"),
    ("let_print", "let x = 5; print x;"),
    ("let_expr", "let x = 2+3*4; print x*2;"),
    ("reassign", "let x = 1; x = x + 2; print x; x = x * 10; print x;"),
    ("relet", "let x = 1; let x = 7; print x;"),
    ("let_chain", "let a = 2; let b = a*3; let c = b-a; print a+b+c;"),
    ("if_true", "if 1<2 { print 10; }"),
    ("if_false", "if 1>2 { print 10; } print 20;"),
    ("if_else_true", "if 1==1 { print 10; } else { print 20; }"),
    ("if_else_false", "if 1==2 { print 10; } else { print 20; }"),
    ("if_nested",
     "if 1 { if 2>1 { print 7; } else { print 8; } } else { print 9; }"),
    ("if_empty_body", "if 1 { } print 5;"),
    ("empty_if_else", "if 0 { } else { } print 1;"),
    ("while_count", "let i=0; while i<5 { print i; i=i+1; }"),
    ("while_zero", "let i=9; while i<3 { print i; i=i+1; } print 0;"),
    ("while_compare", "let i=0; while i<3 { i=i+1; } print i;"),
    ("while_nested",
     "let i=0; while i<2 { let j=0; while j<3 { print i*10+j; j=j+1; } "
     "i=i+1; }"),
    ("while_if",
     "let i=0; while i<4 { if i%2==0 { print i; } else { print 99; } "
     "i=i+1; }"),
    ("while_let_body", "let i=0; while i<3 { let a = i*2; print a; i=i+1; }"),
    ("while_wrap_print", "let i=0; while i<3 { print -1; i=i+1; }"),
    ("div_by_zero", "print 1/0;"),
    ("mod_by_zero", "print 5%0;"),
    ("div_zero_after_print", "print 1; print 1/(2-2);"),
    ("div_zero_cond", "if 1/0 { print 1; }"),
    ("unknown_read", "print nope;"),
    ("unknown_read_after_print", "print 7; print nope;"),
    ("unknown_assign", "nope = 1;"),
    ("unknown_in_if", "if 1 { print 3; print nope; }"),
    ("unknown_in_while",
     "let i=0; while i<2 { print i; i=i+1; } print nope;"),
    ("print_expression", "let x=6; print x*x+1; print (x+1)*(x-1);"),
    ("division", "print 100/7; print 100/(7/2); print 7/2*2;"),
    ("mixed", "let a=5; let b=2; print a*b+a/b; print a%b;"),
    ("single_variable_program", "let x=1;"),
    ("let_negative", "let x=-1; print x;"),
    ("underscore_names", "let _a1 = 4; let b_2 = _a1+1; print b_2;"),
    ("if_scope_defined", "if 1 { let x=1; } print x;"),
    ("if_scope_unknown", "if 0 { let x=1; } print x;"),
    ("while_scope_after", "let i=0; while i<2 { let a=i; i=i+1; } print a;"),
    ("unary_modulo", "print -7%3;"),
    ("if_arithmetic_cond", "if 2-2 { print 1; } else { print 2; }"),
    ("all_comparisons_expr",
     "let a=3; let b=4; print a<b; print a<=b; print b>a; "
     "print b>=a; print a==b; print a!=b;"),
    ("dangling_else", "if 1 { if 0 { print 1; } } else { print 2; }"),
    ("nested_else_binding",
     "if 1 { if 0 { print 1; } else { print 2; } }"),
    ("many_statements", "print 1;" * 100),
]

SYNTAX_PROGRAMS = [
    ("missing_semi", "print 1"),
    ("empty_print", "print ;"),
    ("let_missing_semi", "let x = 1"),
    ("let_missing_name", "let = 1;"),
    ("let_missing_assign", "let x 1;"),
    ("assign_missing_assign", "x 1;"),
    ("assign_without_name", "= 1;"),
    ("unclosed_paren", "print (1+2;"),
    ("trailing_operator", "print 1+;"),
    ("two_operands", "print 1 2;"),
    ("call_syntax", "print 1(2);"),
    ("empty_parens", "print ();"),
    ("if_without_brace", "if 1 print 1;"),
    ("if_unclosed_brace", "if 1 { print 1;"),
    ("extra_brace", "print 1; }"),
    ("stray_rbrace", "}"),
    ("stray_else", "else { print 1; }"),
    ("else_without_brace", "if 1 { } else print 2;"),
    ("while_without_brace", "while 1 ;"),
    ("while_unclosed_brace", "while 1 { print 1;"),
    ("unknown_char", "print @;"),
    ("bang", "print 1!2;"),
    ("dot", "print 1..2;"),
    ("slash_end", "print 1/;"),
    ("let_double_assign", "let x == 1;"),
    ("double_semi", "print 1;;"),
]

LIMIT_PROGRAMS = [
    ("nodes_256_ok", "print " + "+".join(["1"] * 128) + ";"),
    ("nodes_258_limit", "print " + "+".join(["1"] * 129) + ";"),
    ("parens_32_ok", "print " + "(" * 32 + "1" + ")" * 32 + ";"),
    ("parens_33_limit", "print " + "(" * 33 + "1" + ")" * 33 + ";"),
    ("unary_32_ok", "print " + "-" * 32 + "7;"),
    ("unary_33_limit", "print " + "-" * 33 + "7;"),
    ("blocks_32_ok", "if 1 { " * 32 + "print 1; " + "} " * 32),
    ("blocks_33_limit", "if 1 { " * 33 + "print 1; " + "} " * 33),
    ("vars_16_ok",
     "".join("let v%d=%d;" % (i, i) for i in range(16)) + "print v15;"),
    ("vars_17_limit",
     "".join("let v%d=%d;" % (i, i) for i in range(16)) + "let v16=16;"),
    ("output_256_ok",
     "print 18446744073709551615;" * 12 + "print 999;"),
    ("output_257_limit",
     "print 18446744073709551615;" * 12 + "print 999; print 1;"),
    ("output_overflow_first",
     "print 18446744073709551615;" * 13),
    ("output_limit_in_loop",
     "let i=0; while 1 { print 18446744073709551615; i=i+1; }"),
]


class SelfHostInterpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ZEN.is_file():
            raise RuntimeError(
                f"falta el compilador {ZEN}; construyelo con: "
                "CARGO_HOME=\"$PWD/.cargo\" cargo build --release --offline "
                "--manifest-path zen/compiler/Cargo.toml"
            )
        cls._tmpdir = tempfile.TemporaryDirectory(prefix="zen-selfhost-interp-")
        cls.tmp = pathlib.Path(cls._tmpdir.name)
        cls.obj = cls.tmp / "interp.o"
        cls.exe = cls.tmp / "interp_driver"
        cls.cc = os.environ.get("CC", "cc")
        cls.counter = 0

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

    def run_zen(self, program):
        type(self).counter += 1
        path = self.tmp / f"case_{self.counter:04d}.zen"
        path.write_text(program, encoding="utf-8")
        proc = subprocess.run(
            [str(self.exe), str(path)],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        lines = proc.stdout.splitlines()
        self.assertEqual(len(lines), 1, f"salida inesperada:\n{proc.stdout}")
        match = OUTPUT_LINE.fullmatch(lines[0])
        self.assertIsNotNone(match, f"formato inesperado: {lines[0]!r}")
        return tuple(int(match.group(index)) for index in range(1, 5))

    def check_against_reference(self, program):
        expected = reference(program)
        actual = self.run_zen(program)
        self.assertEqual(actual, expected, f"programa:\n{program}\n")
        return actual

    # -- pruebas ------------------------------------------------------------
    def test_reference_is_independent_and_correct(self):
        self.assertEqual(reference("print 2+3*4;"),
                         (0, 1, fnv1a32(b"14\n"), 3))
        self.assertEqual(reference(""), (0, 0, FNV_OFFSET, 0))
        self.assertEqual(reference("print 1/0;"), (2, 1, FNV_OFFSET, 0))
        self.assertEqual(reference("print 1; print nope;"),
                         (3, 2, fnv1a32(b"1\n"), 2))
        self.assertEqual(reference("print ;"), (1, 0, 0, 0))
        self.assertEqual(
            reference("let i=0; while i<3 { print i; i=i+1; }"),
            (0, 11, fnv1a32(b"0\n1\n2\n"), 6),
        )

    def test_programs_match_reference(self):
        self.assertGreaterEqual(len(PROGRAMS), 30)
        for name, program in PROGRAMS:
            with self.subTest(name=name):
                self.check_against_reference(program)

    def test_syntax_errors_have_zeroed_counters(self):
        for name, program in SYNTAX_PROGRAMS:
            with self.subTest(name=name):
                actual = self.run_zen(program)
                self.assertEqual(actual[0], 1, f"{name}: {actual}")
                self.assertEqual(actual[1:], (0, 0, 0), name)

    def test_limit_programs_match_reference(self):
        for name, program in LIMIT_PROGRAMS:
            with self.subTest(name=name):
                self.check_against_reference(program)

    def test_explicit_results(self):
        cases = {
            "print 42;": (0, 1, fnv1a32(b"42\n"), 3),
            "print -1;": (0, 1, fnv1a32(b"18446744073709551615\n"), 21),
            "print 18446744073709551615+1;": (0, 1, fnv1a32(b"0\n"), 2),
            "if 1 { print 1; } else { print 2; }":
                (0, 2, fnv1a32(b"1\n"), 2),
            "if 0 { print 1; } else { print 2; }":
                (0, 2, fnv1a32(b"2\n"), 2),
            "if 0 { print 1; }": (0, 1, FNV_OFFSET, 0),
            "let i=0; while i<3 { i=i+1; }": (0, 8, FNV_OFFSET, 0),
            "print 1; print 1/0;": (2, 2, fnv1a32(b"1\n"), 2),
            "print 7; print nope;": (3, 2, fnv1a32(b"7\n"), 2),
            "nope = 1;": (3, 1, FNV_OFFSET, 0),
        }
        for program, expected in cases.items():
            with self.subTest(program=program):
                self.assertEqual(self.run_zen(program), expected)

    def test_statement_counter_semantics(self):
        # Cada evaluacion de la condicion de un while cuenta; la rama no
        # tomada de un if no cuenta.
        self.assertEqual(
            self.run_zen("let i=0; while i<3 { print i; i=i+1; }")[1], 11)
        self.assertEqual(
            self.run_zen("let i=0; while i<0 { print i; }")[1], 2)
        self.assertEqual(
            self.run_zen("if 0 { print 1; print 2; }")[1], 1)
        self.assertEqual(
            self.run_zen("if 0 { } else { print 2; }")[1], 2)

    def test_division_by_zero_keeps_prior_output(self):
        actual = self.run_zen("print 1; print 2; print 5%0;")
        self.assertEqual(actual[0], 2)
        self.assertEqual(actual[1], 3)
        self.assertEqual(actual[2:], (fnv1a32(b"1\n2\n"), 4))

    def test_unknown_variable_keeps_prior_output(self):
        actual = self.run_zen("print 3; x = 4;")
        self.assertEqual(actual[0], 3)
        self.assertEqual(actual[1], 2)
        self.assertEqual(actual[2:], (fnv1a32(b"3\n"), 2))

    def test_boundaries(self):
        self.assertEqual(
            self.run_zen("print " + "+".join(["1"] * 128) + ";")[0], 0)
        self.assertEqual(
            self.run_zen("print " + "+".join(["1"] * 129) + ";")[0], 4)
        self.assertEqual(
            self.run_zen("print " + "(" * 32 + "1" + ")" * 32 + ";")[0], 0)
        self.assertEqual(
            self.run_zen("print " + "(" * 33 + "1" + ")" * 33 + ";")[0], 4)
        self.assertEqual(
            self.run_zen("if 1 { " * 32 + "print 1; " + "} " * 32)[0], 0)
        self.assertEqual(
            self.run_zen("if 1 { " * 33 + "print 1; " + "} " * 33)[0], 4)
        self.assertEqual(
            self.run_zen("".join("let v%d=%d;" % (i, i) for i in range(16)))[0],
            0)
        self.assertEqual(
            self.run_zen("".join("let v%d=%d;" % (i, i)
                                 for i in range(17)))[0], 4)

    def test_output_limit_boundary(self):
        ok = self.run_zen(
            "print 18446744073709551615;" * 12 + "print 999;")
        self.assertEqual((ok[0], ok[3]), (0, 256))
        over = self.run_zen(
            "print 18446744073709551615;" * 12 + "print 999; print 1;")
        self.assertEqual((over[0], over[3]), (4, 256))
        self.assertEqual(over[1], 14)

    def test_output_format_is_exact(self):
        fixture = self.tmp / "format.zen"
        fixture.write_text("print 42;\n", encoding="utf-8")
        proc = subprocess.run(
            [str(self.exe), str(fixture)],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertRegex(
            proc.stdout,
            r"\Astatus=0 statements=1 hash=1948989099 bytes=3\n\Z",
        )

    def test_driver_missing_file(self):
        proc = subprocess.run(
            [str(self.exe), str(self.tmp / "missing.zen")],
            capture_output=True, text=True, timeout=60,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, "")

    def test_step_limit_stops_infinite_loop(self):
        status, executed, _hash, bytes_out = self.run_zen("while 1 {}")
        self.assertEqual(status, 4, "an infinite loop must stop with the step limit")
        self.assertLessEqual(executed, 1000002)
        self.assertEqual(bytes_out, 0)

    def test_deterministic(self):
        program = ("let i=0; while i<3 { print i*7; i=i+1; } "
                   "if i==3 { print 99; } else { print 100; }")
        self.assertEqual(self.run_zen(program), self.run_zen(program))

    def test_source_uses_local_fixed_arrays(self):
        source = SOURCE.read_text(encoding="utf-8")
        for token in ("pub fn zen_interp(source:u64,length:u64,out:u64)->u64",
                      "[u32;1024]", "[u32;256]", "[u64;256]", "[u32;16]",
                      "volatile_store"):
            self.assertIn(token, source, f"falta {token!r} en interp.zen")
        self.assertNotIn("extern fn", source)
        self.assertNotIn("#include", source)
        # La ejecucion recorre la RPN del AST, no la fuente original.
        for token in ("ek[ei]", "ev[ei]", "ea[ei]", "vals["):
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
