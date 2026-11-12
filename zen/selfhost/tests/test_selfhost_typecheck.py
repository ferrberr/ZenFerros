"""TASK-902G: verificacion del typechecker selfhost escrito en Zen.

El test compila `zen/selfhost/typecheck.zen` como objeto freestanding con el
compilador `zen`, lo enlaza con `zen/selfhost/typecheck_driver.c` y compara,
programa a programa, la salida del typechecker Zen con una implementacion de
referencia independiente escrita aqui (scanner + parser recursivo +
comprobacion de tipos con ambitos lexicos, sin `eval` y sin compartir codigo
con la implementacion Zen).

Cubre:
* >=30 programas: inferencia, ambitos y sombreado, asignacion entre tipos,
  condiciones no bool, aritmetica/logica con bool, comparaciones de tipos
  distintos, variables no definidas, errores de sintaxis y limites;
* el resumen textual estable y su FNV-1a32 (posicion linea:columna + mensaje),
  el primer error detiene y los contadores out[1..2];
* determinismo, formato exacto del driver y ausencia de imports de libc
  (`nm -u` vacio).
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
SOURCE = ROOT / "zen/selfhost/typecheck.zen"
DRIVER = ROOT / "zen/selfhost/typecheck_driver.c"

FNV_OFFSET = 2166136261
FNV_PRIME = 16777619
MAX_TOKENS = 1024
MAX_NODES = 512
MAX_DEPTH = 32
MAX_VARS = 32

U64 = 1
BOOL = 2
TYPE_NAMES = {U64: "u64", BOOL: "bool"}

OUTPUT_LINE = re.compile(
    r"status=([0-9]+) checked=([0-9]+) errors=([0-9]+) hash=([0-9]+)"
)


def fnv1a32(data):
    """FNV-1a de 32 bits sobre bytes; independiente del typechecker Zen."""
    value = FNV_OFFSET
    for byte in data:
        value = ((value ^ byte) * FNV_PRIME) & 0xFFFFFFFF
    return value


def line_col(text, pos):
    """Linea/columna 1-based sobre bytes (misma regla que Zen)."""
    line = 1
    col = 1
    for index in range(min(pos, len(text))):
        if text[index] == "\n":
            line += 1
            col = 1
        else:
            col += 1
    return line, col


class RefError(Exception):
    """Error del typechecker de referencia con estado y posicion."""

    def __init__(self, status, pos=None, message=None):
        super().__init__(status)
        self.status = status
        self.pos = pos
        self.message = message


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
    "&&": "and",
    "||": "or",
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
    "!": "not",
    "(": "lparen",
    ")": "rparen",
    "{": "lbrace",
    "}": "rbrace",
    ";": "semi",
}
WHITESPACE = " \t\r\n\v\f"
COMPARISONS = frozenset(("eq", "ne", "lt", "le", "gt", "ge"))


def _is_digit(char):
    return "0" <= char <= "9"


def _is_alpha(char):
    return ("a" <= char <= "z") or ("A" <= char <= "Z")


def _is_ident(char):
    return _is_alpha(char) or _is_digit(char) or char == "_"


class RefLexer:
    """Scanner independiente con el tope de 1024 tokens del contrato."""

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
                start = pos
                while pos < length and _is_digit(text[pos]):
                    pos += 1
                tokens.append(("num", start, pos - start, text[start:pos]))
                self._check_limit(tokens)
            elif _is_alpha(char) or char == "_":
                start = pos
                pos += 1
                while pos < length and _is_ident(text[pos]):
                    pos += 1
                word = text[start:pos]
                kind = KEYWORDS.get(word, "ident")
                tokens.append((kind, start, pos - start, word))
                self._check_limit(tokens)
            else:
                pair = text[pos:pos + 2]
                if pair in TWO_CHAR_OPERATORS:
                    tokens.append((TWO_CHAR_OPERATORS[pair], pos, 2, pair))
                    pos += 2
                elif char in ONE_CHAR_OPERATORS:
                    tokens.append((ONE_CHAR_OPERATORS[char], pos, 1, char))
                    pos += 1
                else:
                    raise RefError(1)
                self._check_limit(tokens)
        return tokens

    @staticmethod
    def _check_limit(tokens):
        if len(tokens) > MAX_TOKENS:
            raise RefError(4)


class Token:
    __slots__ = ("kind", "pos", "len", "text")

    def __init__(self, kind, pos, length, text):
        self.kind = kind
        self.pos = pos
        self.len = length
        self.text = text


# ---------------------------------------------------------------------------
# Referencia: parser recursivo + comprobacion de tipos con ambitos
# ---------------------------------------------------------------------------
class RefParser:
    def __init__(self, text, tokens):
        self.text = text
        self.tokens = [Token(*token) for token in tokens]
        self.pos = 0
        self.nodes = 0
        self.completed = 0
        self.variables = []       # lista de (nombre, tipo) activos
        self.scopes = [0]         # base de cada ambito abierto
        self.blocks = 1           # nivel superior incluido

    # -- utilidades ---------------------------------------------------------
    def peek(self):
        if self.pos >= len(self.tokens):
            return None
        return self.tokens[self.pos]

    def kind(self):
        token = self.peek()
        return None if token is None else token.kind

    def take(self):
        token = self.peek()
        if token is None:
            raise RefError(1)
        self.pos += 1
        return token

    def expect(self, kind):
        token = self.take()
        if token.kind != kind:
            raise RefError(1)
        return token

    def fail(self, status, pos=None, message=None):
        raise RefError(status, pos, message)

    def add_node(self):
        if self.nodes >= MAX_NODES:
            self.fail(4)
        self.nodes += 1

    # -- ambitos ------------------------------------------------------------
    def enter_scope(self):
        self.scopes.append(len(self.variables))

    def leave_scope(self):
        base = self.scopes.pop()
        self.variables = self.variables[:base]

    def open_block(self):
        if self.blocks >= 33:
            self.fail(4)
        self.blocks += 1
        self.enter_scope()

    def close_block(self):
        self.leave_scope()
        self.blocks -= 1

    def declared_here(self, name):
        base = self.scopes[-1]
        for index in range(base, len(self.variables)):
            if self.variables[index][0] == name:
                return True
        return False

    def lookup(self, name):
        for index in range(len(self.variables) - 1, -1, -1):
            if self.variables[index][0] == name.text:
                return self.variables[index][1]
        self.fail(3, name.pos, f"undefined variable: {name.text}")

    # -- programa y sentencias ---------------------------------------------
    def parse_program(self):
        while self.peek() is not None:
            if self.kind() == "rbrace":
                self.fail(1)
            self.statement()
        return (0, self.completed, 0, 0)

    def parse_block(self):
        self.open_block()
        while self.peek() is not None and self.kind() != "rbrace":
            self.statement()
        self.expect("rbrace")
        self.close_block()

    def statement(self):
        kind = self.kind()
        if kind == "let":
            self.statement_let()
        elif kind == "ident":
            self.statement_assign()
        elif kind == "print":
            self.statement_print()
        elif kind == "if":
            self.statement_if()
        elif kind == "while":
            self.statement_while()
        else:
            self.fail(1)

    def statement_let(self):
        self.expect("let")
        name = self.expect("ident")
        self.expect("assign")
        if self.declared_here(name.text):
            self.fail(2, name.pos, f"redeclaration of variable: {name.text}")
        ty = self.expression(0)
        self.expect("semi")
        self.add_node()
        if len(self.variables) >= MAX_VARS:
            self.fail(4)
        self.variables.append((name.text, ty))
        self.completed += 1

    def statement_assign(self):
        name = self.take()
        self.expect("assign")
        ty = self.lookup(name)
        rhs = self.expression(0)
        self.expect("semi")
        self.add_node()
        if rhs != ty:
            self.fail(
                2,
                name.pos,
                "assignment type mismatch: "
                f"{TYPE_NAMES[ty]} = {TYPE_NAMES[rhs]}",
            )
        self.completed += 1

    def statement_print(self):
        self.expect("print")
        self.expression(0)
        self.expect("semi")
        self.add_node()
        self.completed += 1

    def statement_if(self):
        keyword = self.expect("if")
        condition = self.expression(0)
        self.expect("lbrace")
        self.add_node()
        if condition != BOOL:
            self.fail(
                2,
                keyword.pos,
                f"if condition is not bool: {TYPE_NAMES[condition]}",
            )
        self.parse_block()
        if self.kind() == "else":
            self.take()
            self.expect("lbrace")
            self.parse_block()
        self.completed += 1

    def statement_while(self):
        keyword = self.expect("while")
        condition = self.expression(0)
        self.expect("lbrace")
        self.add_node()
        if condition != BOOL:
            self.fail(
                2,
                keyword.pos,
                f"while condition is not bool: {TYPE_NAMES[condition]}",
            )
        self.parse_block()
        self.completed += 1

    # -- expresiones --------------------------------------------------------
    def expression(self, depth):
        return self.parse_or(depth)

    def parse_or(self, depth):
        left = self.parse_and(depth)
        while self.kind() == "or":
            operator = self.take()
            right = self.parse_and(depth)
            self.add_node()
            left = self.check_binary(operator, left, right)
        return left

    def parse_and(self, depth):
        left = self.parse_cmp(depth)
        while self.kind() == "and":
            operator = self.take()
            right = self.parse_cmp(depth)
            self.add_node()
            left = self.check_binary(operator, left, right)
        return left

    def parse_cmp(self, depth):
        left = self.parse_add(depth)
        while self.kind() in COMPARISONS:
            operator = self.take()
            right = self.parse_add(depth)
            self.add_node()
            left = self.check_binary(operator, left, right)
        return left

    def parse_add(self, depth):
        left = self.parse_mul(depth)
        while self.kind() in ("plus", "minus"):
            operator = self.take()
            right = self.parse_mul(depth)
            self.add_node()
            left = self.check_binary(operator, left, right)
        return left

    def parse_mul(self, depth):
        left = self.parse_unary(depth)
        while self.kind() in ("star", "slash", "percent"):
            operator = self.take()
            right = self.parse_unary(depth)
            self.add_node()
            left = self.check_binary(operator, left, right)
        return left

    def parse_unary(self, depth):
        kind = self.kind()
        if kind in ("minus", "not"):
            if depth + 1 > MAX_DEPTH:
                self.fail(4)
            operator = self.take()
            operand = self.parse_unary(depth + 1)
            self.add_node()
            return self.check_unary(operator, operand)
        if kind == "lparen":
            if depth + 1 > MAX_DEPTH:
                self.fail(4)
            self.take()
            ty = self.expression(depth + 1)
            self.expect("rparen")
            return ty
        if kind == "num":
            self.take()
            self.add_node()
            return U64
        if kind == "ident":
            name = self.take()
            self.add_node()
            return self.lookup(name)
        self.fail(1)

    # -- reglas de tipos ----------------------------------------------------
    def check_binary(self, operator, left, right):
        kind = operator.kind
        if kind in ("plus", "minus", "star", "slash", "percent"):
            if left != U64:
                self.fail(
                    2,
                    operator.pos,
                    f"arithmetic operand is not u64: {TYPE_NAMES[left]}",
                )
            if right != U64:
                self.fail(
                    2,
                    operator.pos,
                    f"arithmetic operand is not u64: {TYPE_NAMES[right]}",
                )
            return U64
        if kind in COMPARISONS:
            if left != right:
                self.fail(
                    2,
                    operator.pos,
                    "comparison operands differ: "
                    f"{TYPE_NAMES[left]} != {TYPE_NAMES[right]}",
                )
            return BOOL
        if left != BOOL:
            self.fail(
                2,
                operator.pos,
                f"logical operand is not bool: {TYPE_NAMES[left]}",
            )
        if right != BOOL:
            self.fail(
                2,
                operator.pos,
                f"logical operand is not bool: {TYPE_NAMES[right]}",
            )
        return BOOL

    def check_unary(self, operator, operand):
        if operator.kind == "not":
            if operand != BOOL:
                self.fail(
                    2,
                    operator.pos,
                    f"unary ! operand is not bool: {TYPE_NAMES[operand]}",
                )
            return BOOL
        if operand != U64:
            self.fail(
                2,
                operator.pos,
                f"unary - operand is not u64: {TYPE_NAMES[operand]}",
            )
        return U64


def reference(program):
    """Ejecuta el typechecker de referencia; misma semantica que zen_typecheck."""
    try:
        tokens = RefLexer(program).tokenize()
    except RefError as error:
        return (error.status, 0, 0, 0)
    parser = RefParser(program, tokens)
    try:
        parser.parse_program()
    except RefError as error:
        if error.status in (2, 3):
            line, col = line_col(program, error.pos)
            summary = f"E{error.status} {line}:{col} {error.message}"
            return (
                error.status,
                parser.completed,
                1,
                fnv1a32(summary.encode("ascii")),
            )
        return (error.status, parser.completed, 0, 0)
    return (0, parser.completed, 0, 0)


# ---------------------------------------------------------------------------
# Programas de prueba
# ---------------------------------------------------------------------------
PROGRAMS = [
    ("empty", ""),
    ("whitespace_only", " \t\r\n\v\f "),
    ("print_literal", "print 42;"),
    ("inference", "let x=1; let y=x+2; print y;"),
    ("infer_bool", "let b=1<2; print b;"),
    ("if_else", "let x=5; if x<10 { print x; } else { print 0; }"),
    ("if_bool_var", "let b=1<2; if b { print 1; }"),
    ("while_bool", "let i=0; while i<3 { i=i+1; } print i;"),
    ("shadowing",
     "let x=1; if 1<2 { let x=2; print x; } print x;"),
    ("inner_scope_assignment",
     "let x=1; if 1<2 { let y=2; x=x+y; } print x;"),
    ("outer_loop_assignment",
     "let x=1; while x<3 { x=x+1; } print x;"),
    ("scope_reuse",
     "if 1<2 { let a=1; } if 1<2 { let a=2; }"),
    ("nested_if",
     "let x=1; if x<2 { if x==1 { print 1; } else { print 2; } } "
     "else { print 3; }"),
    ("arithmetic", "print (1+2)*3-4/2%3;"),
    ("unary_minus", "print -1; print -(2+3);"),
    ("not_bool", "let b=1<2; if !b { print 1; } else { print 2; }"),
    ("logic",
     "let a=1<2; let b=2<3; if a && b || !a { print 1; }"),
    ("comparisons",
     "print 1==1; print 1!=2; print 1<2; print 1<=1; "
     "print 2>1; print 2>=2;"),
    ("bool_comparison", "print (1<2)==(2<3);"),
    ("print_bool", "print 1<2;"),
    ("precedence_arithmetic", "print 1+2*3; print (1+2)*3;"),
    ("precedence_logic", "print 1<2 && 2<3;"),
    ("precedence_or_and", "let a=1<2; let b=2<3; print a || b && a;"),
    ("if_without_else", "if 1<2 { print 1; }"),
    ("while_false", "while 1>2 { print 1; }"),
    ("let_chain", "let a=1; let b=a+1; let c=b*2; print c;"),
    ("bool_assign_same",
     "let b=1<2; b=2<3; if b { print 1; }"),
    ("shadow_three_levels",
     "let x=1; if x<2 { let x=2; if x<3 { let x=3; print x; } "
     "print x; } print x;"),
    ("assign_from_outer_block",
     "let x=0; if 1<2 { if 2<3 { x=7; } } print x;"),
    ("comparison_in_condition",
     "let a=2; if a==2 { print 1; } while a>0 { a=a-1; }"),
    ("print_expression_mix", "print (1<2)==(3<4); print 1+2<4;"),
    ("unary_chain", "print - - -1; print !!1<2;"),
    ("underscore_names", "let _a1=1; let _b=2; print _a1+_b;"),
    ("wrap_number", "print 18446744073709551615+1;"),
    ("nested_while_if",
     "let i=0; while i<3 { if i<2 { print i; } else { print 9; } "
     "i=i+1; }"),
    ("else_only_body", "if 1<2 { } else { let x=1; } print 2;"),
    ("bool_not_condition", "let b=1<2; while !b { b=1<2; } print b;"),
    ("many_operators", "print 1+2-3+4-5+6;"),
    ("deep_compare_chain", "print (1<2)==(2<3)==(3<4);"),
]

TYPE_ERROR_PROGRAMS = [
    ("assign_bool_to_u64", "let x=1; x=1<2;"),
    ("assign_u64_to_bool", "let b=1<2; b=1;"),
    ("if_u64_condition", "if 1 { print 1; }"),
    ("while_u64_condition", "while 0 { print 1; }"),
    ("while_bool_comparison_mixed", "let b=1<2; while b==1 { print 1; }"),
    ("arithmetic_bool_left", "let b=1<2; print b+1;"),
    ("arithmetic_bool_right", "let b=1<2; print 1+b;"),
    ("arithmetic_bool_both", "let a=1<2; let b=2<3; print a*b;"),
    ("comparison_mixed_right", "let b=1<2; print b==1;"),
    ("comparison_mixed_left", "let b=1<2; print 1<b;"),
    ("logical_u64_left", "print 1 && 2;"),
    ("logical_u64_right", "let b=1<2; print b && 1;"),
    ("logical_or_u64", "print 1 || 1<2;"),
    ("unary_not_u64", "print !1;"),
    ("unary_minus_bool", "let b=1<2; print -b;"),
    ("redeclaration", "let x=1; let x=2;"),
    ("shadow_assign_wrong_type",
     "let x=1; if 1<2 { let x=1<2; x=2; }"),
    ("first_type_error_wins", "let x=1; x=1<2; print y;"),
    ("redeclaration_before_rhs", "let x=1; let x=1<2;"),
    ("cond_after_checked_statements", "print 1; if 1 { print 2; }"),
]

UNDEFINED_PROGRAMS = [
    ("undefined_print", "print x;"),
    ("undefined_assignment", "x=1;"),
    ("undefined_rhs", "let x=y+1;"),
    ("undefined_after_block", "if 1<2 { let y=1; } print y;"),
    ("undefined_in_condition", "if x { print 1; }"),
    ("undefined_later_statement",
     "let x=1; print x; if 1<2 { print z; }"),
    ("undefined_shadow_scope",
     "let x=1; if 1<2 { let y=2; } y=3;"),
]

SYNTAX_PROGRAMS = [
    ("empty_let_expr", "let x = ;"),
    ("let_without_name", "let = 1;"),
    ("let_without_assign", "let x 1;"),
    ("print_missing_semi", "print 1"),
    ("empty_print", "print ;"),
    ("if_without_brace", "if 1<2 print 1;"),
    ("if_unclosed", "if 1<2 {"),
    ("else_without_brace", "if 1<2 { } else print 1;"),
    ("else_unclosed", "if 1<2 { } else {"),
    ("stray_else", "else { print 1; }"),
    ("stray_rbrace", "}"),
    ("stray_lbrace", "{"),
    ("assign_missing_semi", "let x=1; x=2"),
    ("number_statement", "1;"),
    ("empty_statement", "let x=1; ;"),
    ("missing_rparen", "print (1;"),
    ("unmatched_rparen", "print 1);"),
    ("two_operands", "print 1 2;"),
    ("unary_plus", "print +1;"),
    ("operator_without_operand", "print 1 && ;"),
    ("unknown_char", "print @;"),
    ("single_ampersand", "print 1 & 2;"),
    ("single_pipe", "print 1 | 2;"),
    ("assign_in_expression", "print 1 = 2;"),
    ("double_else", "if 1<2 { } else { } else { }"),
    ("while_without_brace", "while 1>2 print 1;"),
    ("unclosed_group", "let x = (1+2;"),
    ("let_keyword_as_name", "let let=1;"),
]

LIMIT_PROGRAMS = [
    ("nodes_512_ok", "print 1+1;" * 128),
    ("nodes_516_limit", "print 1+1;" * 129),
    ("parens_32_ok", "print " + "(" * 32 + "1" + ")" * 32 + ";"),
    ("parens_33_limit", "print " + "(" * 33 + "1" + ")" * 33 + ";"),
    ("unary_32_ok", "print " + "-" * 32 + "1;"),
    ("unary_33_limit", "print " + "-" * 33 + "1;"),
    ("blocks_32_ok", "if 1<2 { " * 32 + "print 1; " + "} " * 32),
    ("blocks_33_limit", "if 1<2 { " * 33 + "print 1; " + "} " * 33),
    ("vars_32_ok",
     "".join("let v%d=1;" % i for i in range(32)) + "print v31;"),
    ("vars_33_limit",
     "".join("let v%d=1;" % i for i in range(32)) + "let v32=1;"),
    ("vars_shadow_33_limit",
     "".join("let v%d=1;" % i for i in range(32)) +
     "if 1<2 { let z=1; }"),
    ("scope_reuse_33_ok",
     "".join("if 1<2 { let v%d=1; }" % i for i in range(33))),
    ("tokens_1024_syntax", ";" * 1024),
    ("tokens_1025_limit", ";" * 1025),
    ("token_limit_with_valid_prefix", "print 1;" * 256 + ";" * 300),
]


class SelfHostTypecheckTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ZEN.is_file():
            raise RuntimeError(
                f"falta el compilador {ZEN}; construyelo con: "
                "CARGO_HOME=\"$PWD/.cargo\" cargo build --release --offline "
                "--manifest-path zen/compiler/Cargo.toml"
            )
        cls._tmpdir = tempfile.TemporaryDirectory(prefix="zen-selfhost-tc-")
        cls.tmp = pathlib.Path(cls._tmpdir.name)
        cls.obj = cls.tmp / "typecheck.o"
        cls.exe = cls.tmp / "typecheck_driver"
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
            capture_output=True, text=True, timeout=120,
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
        self.assertEqual(reference("let x=1; print x;"), (0, 2, 0, 0))
        self.assertEqual(reference(""), (0, 0, 0, 0))
        self.assertEqual(reference("print x;"), (
            3, 0, 1, fnv1a32(b"E3 1:7 undefined variable: x")))
        self.assertEqual(reference("let x=1; x=1<2;"), (
            2, 1, 1,
            fnv1a32(b"E2 1:10 assignment type mismatch: u64 = bool")))
        self.assertEqual(reference("if 1 { print 1; }"), (
            2, 0, 1, fnv1a32(b"E2 1:1 if condition is not bool: u64")))
        self.assertEqual(reference("print (1;"), (1, 0, 0, 0))

    def test_programs_match_reference(self):
        self.assertGreaterEqual(len(PROGRAMS), 30)
        for name, program in PROGRAMS:
            with self.subTest(name=name):
                self.check_against_reference(program)

    def test_type_errors_match_reference(self):
        for name, program in TYPE_ERROR_PROGRAMS:
            with self.subTest(name=name):
                result = self.check_against_reference(program)
                self.assertEqual(result[0], 2, name)
                self.assertEqual(result[2], 1, name)

    def test_undefined_variables_match_reference(self):
        for name, program in UNDEFINED_PROGRAMS:
            with self.subTest(name=name):
                result = self.check_against_reference(program)
                self.assertEqual(result[0], 3, name)
                self.assertEqual(result[2], 1, name)

    def test_syntax_errors_have_zeroed_error_fields(self):
        for name, program in SYNTAX_PROGRAMS:
            with self.subTest(name=name):
                result = self.check_against_reference(program)
                self.assertEqual(result[0], 1, f"{name}: {result}")
                self.assertEqual(result[2:], (0, 0), name)

    def test_limit_programs_match_reference(self):
        for name, program in LIMIT_PROGRAMS:
            with self.subTest(name=name):
                self.check_against_reference(program)

    def test_explicit_results(self):
        cases = {
            "let x=1; print x;": (0, 2, 0, 0),
            "print 42;": (0, 1, 0, 0),
            "let b=1<2; if b { print 1; }":
                (0, 3, 0, 0),
            "print x;":
                (3, 0, 1, fnv1a32(b"E3 1:7 undefined variable: x")),
            "let x=1; x=1<2;":
                (2, 1, 1,
                 fnv1a32(b"E2 1:10 assignment type mismatch: u64 = bool")),
            "if 1 { print 1; }":
                (2, 0, 1,
                 fnv1a32(b"E2 1:1 if condition is not bool: u64")),
            "let b=1<2; print b+1;":
                (2, 1, 1,
                 fnv1a32(
                     b"E2 1:19 arithmetic operand is not u64: bool")),
            "print !1;":
                (2, 0, 1,
                 fnv1a32(b"E2 1:7 unary ! operand is not bool: u64")),
            "let b=1<2; print b==1;":
                (2, 1, 1,
                 fnv1a32(
                     b"E2 1:19 comparison operands differ: bool != u64")),
            "print (1;": (1, 0, 0, 0),
        }
        for program, expected in cases.items():
            with self.subTest(program=program):
                self.assertEqual(self.run_zen(program), expected)

    def test_error_summary_hash_is_positioned_and_stable(self):
        cases = [
            ("print x;", "E3 1:7 undefined variable: x"),
            ("let x=1; x=1<2;",
             "E2 1:10 assignment type mismatch: u64 = bool"),
            ("if 1 { print 1; }",
             "E2 1:1 if condition is not bool: u64"),
            ("let x=1;\nprint y;",
             "E3 2:7 undefined variable: y"),
            ("let x=1;\n\tprint 1 && 2;",
             "E2 2:10 logical operand is not bool: u64"),
        ]
        for program, summary in cases:
            with self.subTest(summary=summary):
                result = self.run_zen(program)
                self.assertEqual(result[0], int(summary[1]))
                self.assertEqual(result[2], 1)
                self.assertEqual(result[3],
                                 fnv1a32(summary.encode("ascii")))
                self.assertEqual(result, reference(program))
        # El mismo error en otra posicion produce otro hash.
        first = self.run_zen("print x;")
        second = self.run_zen(" print x;")
        self.assertNotEqual(first[3], second[3])

    def test_first_error_stops(self):
        result = self.run_zen("let x=1; x=1<2; print y;")
        self.assertEqual(result, (2, 1, 1, reference(
            "let x=1; x=1<2; print y;")[3]))
        self.assertEqual(result[0], 2)
        self.assertEqual(result[1], 1)

    def test_scopes(self):
        self.assertEqual(
            self.run_zen(
                "let x=1; if 1<2 { let x=2; print x; } print x;")[0], 0)
        self.assertEqual(
            self.run_zen("if 1<2 { let y=1; } print y;")[0], 3)
        self.assertEqual(
            self.run_zen("let x=1; if 1<2 { x=2; } print x;")[0], 0)
        self.assertEqual(
            self.run_zen("if 1<2 { let a=1; } let a=2;")[0], 0)
        # El ambito interno no filtra su tipo: asignar u64 a la x externa
        # sigue siendo valido tras sombrearla dentro.
        self.assertEqual(
            self.run_zen("let x=1; if 1<2 { let x=1<2; } x=3;")[0], 0)

    def test_limit_boundaries_explicit(self):
        # Cada limite deja out[1] con las sentencias ya completas.
        cases = [
            ("print 1+1;" * 128, (0, 128, 0, 0)),
            ("print 1+1;" * 129, (4, 128, 0, 0)),
            ("print " + "(" * 32 + "1" + ")" * 32 + ";", (0, 1, 0, 0)),
            ("print " + "(" * 33 + "1" + ")" * 33 + ";", (4, 0, 0, 0)),
            ("print " + "-" * 32 + "1;", (0, 1, 0, 0)),
            ("print " + "-" * 33 + "1;", (4, 0, 0, 0)),
            ("if 1<2 { " * 32 + "print 1; " + "} " * 32, (0, 33, 0, 0)),
            ("if 1<2 { " * 33 + "print 1; " + "} " * 33, (4, 0, 0, 0)),
            ("".join("let v%d=1;" % i for i in range(32)) + "print v31;",
             (0, 33, 0, 0)),
            ("".join("let v%d=1;" % i for i in range(32)) + "let v32=1;",
             (4, 32, 0, 0)),
            ("".join("let v%d=1;" % i for i in range(32)) +
             "if 1<2 { let z=1; }", (4, 32, 0, 0)),
            ("".join("if 1<2 { let v%d=1; }" % i for i in range(33)),
             (0, 66, 0, 0)),
            (";" * 1024, (1, 0, 0, 0)),
            (";" * 1025, (4, 0, 0, 0)),
        ]
        for program, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(self.run_zen(program), expected)
                self.assertEqual(reference(program), expected)

    def test_deterministic(self):
        program = ("let x=1; while x<3 { x=x+1; } "
                   "if x==3 { print 1; } else { print 0; }")
        first = self.run_zen(program)
        second = self.run_zen(program)
        self.assertEqual(first, second)
        self.assertEqual(first, reference(program))

    def test_driver_missing_file(self):
        proc = subprocess.run(
            [str(self.exe), str(self.tmp / "missing.zen")],
            capture_output=True, text=True, timeout=60,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, "")

    def test_output_format_is_exact(self):
        fixture = self.tmp / "format.zen"
        fixture.write_text("print 1<2;\n", encoding="utf-8")
        proc = subprocess.run(
            [str(self.exe), str(fixture)],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(
            proc.stdout,
            "status=0 checked=1 errors=0 hash=0\n",
        )

    def test_source_uses_local_fixed_arrays(self):
        source = SOURCE.read_text(encoding="utf-8")
        for token in (
            "pub fn zen_typecheck(source:u64,length:u64,out:u64)->u64",
            "[u32;1024]", "[u32;128]",
            "[u32;32]", "[u32;64]", "[u8;20]", "volatile_store",
        ):
            self.assertIn(token, source,
                          f"falta {token!r} en typecheck.zen")
        self.assertNotIn("extern fn", source)
        self.assertNotIn("#include", source)
        # Se comprueba la fuente, no se construye AST ni se reparsea.
        for token in ("tk_kind[", "ts[", "vtype[", "f_sbase["):
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
