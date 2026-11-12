"""TASK-902H: verificacion del generador de codigo C selfhost escrito en Zen.

El test compila `zen/selfhost/codegen.zen` como objeto freestanding con el
compilador `zen`, lo enlaza con `zen/selfhost/codegen_driver.c` y, programa a
programa:

1. ejecuta el codegen y obtiene el programa C emitido;
2. lo compila con `cc -std=c11 -O2`;
3. lo ejecuta y compara la salida exacta con un interprete de referencia
   independiente escrito aqui (lexer + parser recursivo + evaluador con
   ambitos lexicos, sin `eval` y sin compartir codigo con Zen).

Cubre: let/asignacion/print/if-else/while, u64/bool, comparaciones, aritmetica
envolvente mod 2^64, &&/||/!, booleanos impresos como 0/1, programa vacio,
sombreado de variables y nombres saneados; los codigos exactos de error
(sintaxis, tipos/no definida, limite) y el limite de capacidad de salida; el
driver escribiendo por stdout y a fichero; determinismo; ausencia de imports de
libc en el objeto Zen (`nm -u` vacio) y ausencia de rastros de wrapper o de
texto C preexistente copiado en el C emitido.
"""

import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
ZEN = ROOT / "zen/compiler/target/release/zen"
SOURCE = ROOT / "zen/selfhost/codegen.zen"
DRIVER = ROOT / "zen/selfhost/codegen_driver.c"

U64_MAX = (1 << 64) - 1
CG_LIMIT = 0xFFFFFFFF
CG_SYNTAX = 0xFFFFFFFE
CG_TYPES = 0xFFFFFFFD

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


class RefError(Exception):
    """Programa invalido para el interprete de referencia."""


def tokenize(text):
    """Scanner independiente del de Zen; solo cubre programas validos."""
    tokens = []
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
            tokens.append(("num", text[start:pos]))
        elif _is_alpha(char) or char == "_":
            start = pos
            pos += 1
            while pos < length and _is_ident(text[pos]):
                pos += 1
            word = text[start:pos]
            tokens.append((KEYWORDS.get(word, "ident"), word))
        elif text[pos:pos + 2] in TWO_CHAR_OPERATORS:
            tokens.append((TWO_CHAR_OPERATORS[text[pos:pos + 2]], text[pos:pos + 2]))
            pos += 2
        elif char in ONE_CHAR_OPERATORS:
            tokens.append((ONE_CHAR_OPERATORS[char], char))
            pos += 1
        else:
            raise RefError(f"caracter inesperado {char!r} en {pos}")
    return tokens


# ---------------------------------------------------------------------------
# Referencia: parser recursivo -> AST
# ---------------------------------------------------------------------------
class RefParser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def peek(self):
        if self.pos >= len(self.tokens):
            return None
        return self.tokens[self.pos]

    def kind(self):
        token = self.peek()
        return None if token is None else token[0]

    def take(self, kind=None):
        token = self.peek()
        if token is None:
            raise RefError("fin de programa inesperado")
        if kind is not None and token[0] != kind:
            raise RefError(f"se esperaba {kind}, llego {token[0]}")
        self.pos += 1
        return token

    def program(self):
        statements = []
        while self.peek() is not None:
            statements.append(self.statement())
        return statements

    def block(self):
        self.take("lbrace")
        statements = []
        while self.peek() is not None and self.kind() != "rbrace":
            statements.append(self.statement())
        self.take("rbrace")
        return statements

    def statement(self):
        kind = self.kind()
        if kind == "let":
            self.take("let")
            name = self.take("ident")[1]
            self.take("assign")
            value = self.expression()
            self.take("semi")
            return ("let", name, value)
        if kind == "ident":
            name = self.take("ident")[1]
            self.take("assign")
            value = self.expression()
            self.take("semi")
            return ("assign", name, value)
        if kind == "print":
            self.take("print")
            value = self.expression()
            self.take("semi")
            return ("print", value)
        if kind == "if":
            self.take("if")
            condition = self.expression()
            then_body = self.block()
            else_body = None
            if self.kind() == "else":
                self.take("else")
                else_body = self.block()
            return ("if", condition, then_body, else_body)
        if kind == "while":
            self.take("while")
            condition = self.expression()
            body = self.block()
            return ("while", condition, body)
        raise RefError(f"sentencia inesperada {kind!r}")

    def expression(self):
        return self.parse_or()

    def parse_or(self):
        node = self.parse_and()
        while self.kind() == "or":
            self.take("or")
            node = ("bin", "or", node, self.parse_and())
        return node

    def parse_and(self):
        node = self.parse_cmp()
        while self.kind() == "and":
            self.take("and")
            node = ("bin", "and", node, self.parse_cmp())
        return node

    def parse_cmp(self):
        node = self.parse_add()
        while self.kind() in COMPARISONS:
            operator = self.take()[0]
            node = ("bin", operator, node, self.parse_add())
        return node

    def parse_add(self):
        node = self.parse_mul()
        while self.kind() in ("plus", "minus"):
            operator = self.take()[0]
            node = ("bin", operator, node, self.parse_mul())
        return node

    def parse_mul(self):
        node = self.parse_unary()
        while self.kind() in ("star", "slash", "percent"):
            operator = self.take()[0]
            node = ("bin", operator, node, self.parse_unary())
        return node

    def parse_unary(self):
        kind = self.kind()
        if kind in ("minus", "not"):
            self.take()
            return ("un", kind, self.parse_unary())
        if kind == "lparen":
            self.take("lparen")
            node = self.expression()
            self.take("rparen")
            return node
        if kind == "num":
            return ("num", int(self.take("num")[1]))
        if kind == "ident":
            return ("var", self.take("ident")[1])
        raise RefError(f"operando inesperado {kind!r}")


# ---------------------------------------------------------------------------
# Referencia: evaluador con ambitos lexicos y aritmetica modular u64
# ---------------------------------------------------------------------------
def u64(value):
    return value & U64_MAX


class RefInterpreter:
    def __init__(self):
        self.scopes = [{}]
        self.output = []

    def lookup(self, name):
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        raise RefError(f"variable no definida: {name}")

    def find_scope(self, name):
        for index in range(len(self.scopes) - 1, -1, -1):
            if name in self.scopes[index]:
                return index
        raise RefError(f"variable no definida: {name}")

    def evaluate(self, node):
        kind = node[0]
        if kind == "num":
            return u64(node[1])
        if kind == "var":
            return self.lookup(node[1])
        if kind == "un":
            value = self.evaluate(node[2])
            if node[1] == "minus":
                return u64(-value)
            return not value
        operator = node[1]
        left = self.evaluate(node[2])
        right = self.evaluate(node[3])
        if operator == "plus":
            return u64(left + right)
        if operator == "minus":
            return u64(left - right)
        if operator == "star":
            return u64(left * right)
        if operator == "slash":
            if right == 0:
                raise RefError("division por cero")
            return u64(left // right)
        if operator == "percent":
            if right == 0:
                raise RefError("resto por cero")
            return u64(left % right)
        if operator == "eq":
            return left == right
        if operator == "ne":
            return left != right
        if operator == "lt":
            return left < right
        if operator == "le":
            return left <= right
        if operator == "gt":
            return left > right
        if operator == "ge":
            return left >= right
        if operator == "and":
            return bool(left) and bool(right)
        if operator == "or":
            return bool(left) or bool(right)
        raise RefError(f"operador desconocido {operator!r}")

    def execute_statements(self, statements):
        for statement in statements:
            self.execute(statement)

    def execute_block(self, statements):
        self.scopes.append({})
        try:
            self.execute_statements(statements)
        finally:
            self.scopes.pop()

    def execute(self, statement):
        kind = statement[0]
        if kind == "let":
            value = self.evaluate(statement[2])
            self.scopes[-1][statement[1]] = value
        elif kind == "assign":
            value = self.evaluate(statement[2])
            self.scopes[self.find_scope(statement[1])][statement[1]] = value
        elif kind == "print":
            value = self.evaluate(statement[1])
            if isinstance(value, bool):
                self.output.append("1" if value else "0")
            else:
                self.output.append(str(value))
        elif kind == "if":
            if self.evaluate(statement[1]):
                self.execute_block(statement[2])
            elif statement[3] is not None:
                self.execute_block(statement[3])
        elif kind == "while":
            while self.evaluate(statement[1]):
                self.execute_block(statement[2])
        else:
            raise RefError(f"sentencia desconocida {kind!r}")


def reference(program):
    """Salida stdout esperada del programa segun el lenguaje de TASK-902G."""
    ast = RefParser(tokenize(program)).program()
    interpreter = RefInterpreter()
    interpreter.execute_statements(ast)
    if not interpreter.output:
        return ""
    return "\n".join(interpreter.output) + "\n"


# ---------------------------------------------------------------------------
# Programas validos: codegen -> C -> ejecutable -> stdout
# ---------------------------------------------------------------------------
PROGRAMS = [
    ("empty", ""),
    ("print_literal", "print 42;"),
    ("print_bool_true", "print 1<2;"),
    ("print_bool_false", "print 2<1;"),
    ("arithmetic", "print 1+2*3-4/2%3;"),
    ("precedence_parens", "print (1+2)*3; print 1+2*3;"),
    ("wrapping_add", "print 18446744073709551615+1;"),
    ("wrapping_sub", "print 0-1;"),
    ("wrapping_mul", "print 18446744073709551615*2;"),
    ("literal_modulo", "print 18446744073709551617;"),
    ("unary_minus", "print -1; print - -2;"),
    ("comparisons",
     "print 1==1; print 1!=2; print 1<2; print 1<=1; "
     "print 2>1; print 2>=2;"),
    ("bool_comparison", "print (1<2)==(2<3);"),
    ("logic",
     "let a=1<2; let b=2<3; print a && b; print a || b; print !a;"),
    ("logic_false", "let b=1<2; print b && (2<1); print b || (2<1);"),
    ("if_else_true", "if 1<2 { print 10; } else { print 20; }"),
    ("if_else_false", "if 2<1 { print 10; } else { print 20; }"),
    ("if_no_else", "if 1<2 { print 7; } print 8;"),
    ("nested_if",
     "let x=2; if 1<x { if x<3 { print 1; } else { print 2; } } "
     "else { print 3; }"),
    ("while_count", "let i=0; while i<5 { print i; i=i+1; }"),
    ("while_sum", "let i=1; let s=0; while i<=10 { s=s+i; i=i+1; } print s;"),
    ("while_nested_if",
     "let i=0; while i<4 { if i%2==0 { print i; } else { print 100+i; } "
     "i=i+1; }"),
    ("while_false", "let x=9; while x<5 { print x; x=x+1; } print x;"),
    ("shadowing", "let x=1; if 1<2 { let x=2; print x; } print x;"),
    ("shadow_three",
     "let x=1; if 1<2 { let x=2; if 2<3 { let x=3; print x; } "
     "print x; } print x;"),
    ("assign_outer_from_inner",
     "let x=1; if 1<2 { let y=2; x=x+y; } print x;"),
    ("scope_reuse",
     "if 1<2 { let a=11; print a; } if 1<2 { let a=22; print a; }"),
    ("bool_variable",
     "let b=1<2; b=2<3; if b { print 1; } else { print 0; }"),
    ("sanitized_names",
     "let int=1; let for=2; let main=3; let printf=4; "
     "let uint64_t=5; print int+for+main+printf+uint64_t;"),
    ("comparison_chain",
     "print 1<2; print (1<2)==(2<3); print (1<2)!=(3<2);"),
    ("bool_comparison_chain",
     "print (1<2) == (2<3) == (3<2);"),
    ("logical_precedence",
     "let a=1<2; let b=2<3; let c=3<4; "
     "if a && b || !c { print 1; } else { print 0; }"),
    ("empty_blocks", "if 1<2 { } else { print 1; } print 2;"),
    ("u64_division", "print 20/3; print 20%3; print 7/7;"),
    ("u64_large_division",
     "print 18446744073709551615/3; print 18446744073709551615%3;"),
    ("assignment_same_expr", "let x=10; x=x*x; print x;"),
    ("bool_from_not",
     "let b=1<2; if !b { print 1; } else { print 2; }"),
    ("double_not", "print !! (1<2);"),
    ("deep_expression", "print ((((1+2)*3)-4)/5)%6;"),
    ("nested_unary_binary", "print -(2+3)*4;"),
    ("mixed_comparison_precedence",
     "let a=2<1; let b=1<2; let c=2<1; print a == b < c;"),
    ("many_prints", "print 1; print 2; print 3; print 4; print 5;"),
    ("bool_print_after_assign",
     "let b=2<1; print b; b=1<2; print b;"),
    ("while_bool_condition",
     "let b=1<2; let i=0; while b { print i; i=i+1; "
     "if 2<i { b=2<1; } }"),
]

ERROR_PROGRAMS = [
    ("syntax_empty_expr", "let x = ;", CG_SYNTAX),
    ("syntax_missing_semi", "print 1", CG_SYNTAX),
    ("syntax_unknown_char", "print @;", CG_SYNTAX),
    ("syntax_stray_rbrace", "}", CG_SYNTAX),
    ("syntax_else_without_if", "else { print 1; }", CG_SYNTAX),
    ("type_assignment", "let x=1; x=1<2;", CG_TYPES),
    ("type_if_condition", "if 1 { print 1; }", CG_TYPES),
    ("type_while_condition", "while 0 { print 1; }", CG_TYPES),
    ("type_arithmetic_bool", "let b=1<2; print b+1;", CG_TYPES),
    ("type_logical_u64", "print 1 && 2;", CG_TYPES),
    ("undefined_print", "print y;", CG_TYPES),
    ("undefined_assign", "y=1;", CG_TYPES),
    ("redeclaration", "let x=1; let x=2;", CG_TYPES),
    ("syntax_at_token_limit", ";" * 1024, CG_SYNTAX),
    ("limit_tokens", ";" * 1025, CG_LIMIT),
    ("limit_nodes", "print 1+1;" * 129, CG_LIMIT),
    ("limit_variables",
     "".join("let v%d=1;" % i for i in range(32)) + "let v32=1;",
     CG_LIMIT),
]


# ---------------------------------------------------------------------------
# Harness C auxiliar: llama a zen_codegen y muestra el valor bruto devuelto.
# Es solo un fichero temporal del test; no forma parte de la entrega.
# ---------------------------------------------------------------------------
RAW_HARNESS = r"""
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

extern uint64_t zen_codegen(uint64_t source, uint64_t length, uint64_t out,
                            uint64_t cap);

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "usage: raw_codegen FILE [CAP]\n");
        return 2;
    }
    FILE *file = fopen(argv[1], "rb");
    if (file == NULL) {
        return 2;
    }
    if (fseek(file, 0, SEEK_END) != 0) {
        fclose(file);
        return 2;
    }
    long size = ftell(file);
    if (size < 0) {
        fclose(file);
        return 2;
    }
    rewind(file);
    unsigned char *source = (unsigned char *)malloc((size_t)size + 1u);
    if (source == NULL) {
        fclose(file);
        return 2;
    }
    if (fread(source, 1, (size_t)size, file) != (size_t)size) {
        fclose(file);
        free(source);
        return 2;
    }
    fclose(file);
    uint64_t cap = 1048576u;
    if (argc >= 3) {
        cap = strtoull(argv[2], NULL, 10);
    }
    unsigned char *out = (unsigned char *)malloc((size_t)cap + 1u);
    if (out == NULL) {
        free(source);
        return 2;
    }
    uint64_t written = zen_codegen((uint64_t)(uintptr_t)source,
                                   (uint64_t)size,
                                   (uint64_t)(uintptr_t)out, cap);
    printf("%llu\n", (unsigned long long)written);
    free(out);
    free(source);
    return 0;
}
"""


class SelfHostCodegenTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ZEN.is_file():
            raise RuntimeError(
                f"falta el compilador {ZEN}; construyelo con: "
                "CARGO_HOME=\"$PWD/.cargo\" cargo build --release --offline "
                "--manifest-path zen/compiler/Cargo.toml"
            )
        cls._tmpdir = tempfile.TemporaryDirectory(prefix="zen-selfhost-cg-")
        cls.tmp = pathlib.Path(cls._tmpdir.name)
        cls.obj = cls.tmp / "codegen.o"
        cls.exe = cls.tmp / "codegen_driver"
        cls.raw = cls.tmp / "raw_codegen"
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
            raise RuntimeError(f"enlace del driver fallo:\n{link.stderr}")

        harness = cls.tmp / "raw_harness.c"
        harness.write_text(RAW_HARNESS, encoding="utf-8")
        raw_link = subprocess.run(
            [cls.cc, "-std=c11", "-O2", "-fno-pie", "-no-pie",
             str(harness), str(cls.obj), "-o", str(cls.raw)],
            cwd=str(ROOT), capture_output=True, text=True, timeout=120,
        )
        if raw_link.returncode != 0:
            raise RuntimeError(f"enlace del harness fallo:\n{raw_link.stderr}")

    @classmethod
    def tearDownClass(cls):
        cls._tmpdir.cleanup()

    # -- utilidades ---------------------------------------------------------
    def write_source(self, program):
        type(self).counter += 1
        path = self.tmp / f"case_{self.counter:04d}.zen"
        path.write_text(program, encoding="utf-8")
        return path

    def run_driver(self, program, output_path=None):
        path = self.write_source(program)
        args = [str(self.exe), str(path)]
        if output_path is not None:
            args.append(str(output_path))
        return subprocess.run(args, capture_output=True, text=True, timeout=120)

    def emit(self, program):
        proc = self.run_driver(program)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(proc.stdout.isascii(), "el C emitido no es ASCII")
        return proc.stdout

    def compile_c(self, program, c_source):
        type(self).counter += 1
        path = self.tmp / f"emit_{self.counter:04d}.c"
        exe = self.tmp / f"emit_{self.counter:04d}"
        path.write_text(c_source, encoding="ascii")
        proc = subprocess.run(
            [self.cc, "-std=c11", "-O2", "-Wall", "-Wextra",
             str(path), "-o", str(exe)],
            capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(
            proc.returncode, 0,
            f"el C emitido no compila para {program!r}:\n"
            f"{c_source}\n{proc.stderr}",
        )
        return exe

    def run_generated(self, program):
        c_source = self.emit(program)
        exe = self.compile_c(program, c_source)
        proc = subprocess.run([str(exe)], capture_output=True, text=True,
                              timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout

    def raw_codegen(self, program, cap=1 << 20):
        path = self.write_source(program)
        proc = subprocess.run(
            [str(self.raw), str(path), str(cap)],
            capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return int(proc.stdout.strip())

    # -- referencia ---------------------------------------------------------
    def test_reference_interpreter_is_independent_and_correct(self):
        cases = {
            "": "",
            "print 42;": "42\n",
            "let x=1; x=x+1; print x;": "2\n",
            "print 1<2;": "1\n",
            "print 2<1;": "0\n",
            "print 1<2 && 2<3;": "1\n",
            "print 18446744073709551615+1;": "0\n",
            "print 0-1;": "18446744073709551615\n",
            "print 18446744073709551617;": "1\n",
            "let i=0; while i<3 { print i; i=i+1; }": "0\n1\n2\n",
            "let x=1; if 1<2 { let x=2; print x; } print x;": "2\n1\n",
            "let x=1; if 1<2 { let y=2; x=x+y; } print x;": "3\n",
            "print (1<2)==(2<3);": "1\n",
        }
        for program, expected in cases.items():
            with self.subTest(program=program):
                self.assertEqual(reference(program), expected)

    # -- programas completos ------------------------------------------------
    def test_programs_compile_and_match_reference(self):
        self.assertGreaterEqual(len(PROGRAMS), 15)
        for name, program in PROGRAMS:
            with self.subTest(name=name):
                expected = reference(program)
                actual = self.run_generated(program)
                self.assertEqual(
                    actual, expected,
                    f"salida distinta para {name}:\nprograma: {program}\n"
                    f"C:\n{self.emit(program)}",
                )

    def test_empty_program(self):
        c_source = self.emit("")
        self.assertTrue(c_source.startswith("#include <stdio.h>\n"))
        self.assertIn("#include <stdint.h>\n", c_source)
        self.assertIn("int main(void) {\n", c_source)
        self.assertTrue(c_source.endswith("    return 0;\n}\n"))
        exe = self.compile_c("", c_source)
        proc = subprocess.run([str(exe)], capture_output=True, text=True,
                              timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, "")
        self.assertEqual(reference(""), "")

    def test_emission_is_readable_and_sanitized(self):
        c_source = self.emit(
            "let x=1; while x<3 { print x; x=x+1; }")
        for expected in (
            "#include <stdio.h>",
            "#include <stdint.h>",
            "int main(void) {",
            "uint64_t v_0 = 1ULL;",
            "while ((v_0 < 3ULL)) {",
            'printf("%llu\\n", (unsigned long long)(v_0));',
            "v_0 = (v_0 + 1ULL);",
            "return 0;",
            "}\n",
        ):
            self.assertIn(expected, c_source)

        bool_source = self.emit("let b=1<2; print b;")
        self.assertIn("int v_0 = (1ULL < 2ULL);", bool_source)
        self.assertIn('printf("%llu\\n", (unsigned long long)(v_0));',
                      bool_source)

        # Un lenguaje con un solo nivel de comparacion obliga a parentesis
        # explicitos: C separa ==/!= de </<=/>/>=.
        mixed = self.emit(
            "let a=2<1; let b=1<2; let c=2<1; print a == b < c;")
        self.assertIn("((v_0 == v_1) < v_2)", mixed)

        # Nombres que son palabras clave de C quedan saneados a v_<n>.
        names_program = (
            "let int=1; let main=2; let printf=3; "
            "let uint64_t=4; print int+main+printf+uint64_t;")
        names_c = self.emit(names_program)
        self.assertIn("uint64_t v_0 = 1ULL;", names_c)
        self.assertIn("uint64_t v_1 = 2ULL;", names_c)
        self.assertIn("uint64_t v_2 = 3ULL;", names_c)
        self.assertIn("uint64_t v_3 = 4ULL;", names_c)
        self.assertEqual(names_c.count("main"), 1)
        self.assertEqual(names_c.count("printf"), 1)
        self.assertNotIn("int int", names_c)
        self.assertNotIn("uint64_t uint64_t", names_c)

    def test_emitted_c_has_no_wrapper_trace_or_copied_text(self):
        program = "let x=1; while x<2 { print x; x=x+1; }"
        c_source = self.emit(program)
        lowered = c_source.lower()
        for forbidden in (
            "zen_codegen",
            "zen_typecheck",
            "zen_interp",
            "codegen_driver",
            "typecheck_driver",
            "interp_driver",
            "codegen.zen",
            "task-902",
            "extern",
            "rust",
            "#include <stdlib.h>",
        ):
            self.assertNotIn(forbidden, lowered, forbidden)
        self.assertNotIn(program, c_source)

        # El texto C completo de un fixture no esta copiado en el generador:
        # se emite por piezas y depende del programa de entrada.
        generator_source = SOURCE.read_text(encoding="utf-8")
        self.assertNotIn(
            'printf("%llu\\n", (unsigned long long)(42ULL));',
            generator_source,
        )
        self.assertNotIn(
            "#include <stdio.h>\n#include <stdint.h>\n\nint main(void) {",
            generator_source,
        )
        self.assertNotIn(program, generator_source)

        # Programas distintos producen C distinto (no es una plantilla fija).
        first = self.emit("print 1;")
        second = self.emit("print 2;")
        self.assertNotEqual(first, second)
        self.assertIn("(1ULL)", first)
        self.assertIn("(2ULL)", second)

    def test_deterministic(self):
        program = ("let x=1; while x<3 { x=x+1; } "
                   "if x==3 { print 1; } else { print 0; }")
        first = self.emit(program)
        second = self.emit(program)
        self.assertEqual(first, second)
        self.assertEqual(self.raw_codegen(program),
                         self.raw_codegen(program))
        self.assertEqual(first.encode("ascii"), second.encode("ascii"))

    # -- contrato de error y limites ---------------------------------------
    def test_error_codes_are_exact(self):
        for name, program, expected in ERROR_PROGRAMS:
            with self.subTest(name=name):
                self.assertEqual(
                    self.raw_codegen(program), expected,
                    f"{name}: {program!r}",
                )

    def test_driver_fails_cleanly_on_errors(self):
        exit_codes = {
            CG_SYNTAX: 5,
            CG_TYPES: 6,
            CG_LIMIT: 4,
        }
        for name, program, expected in ERROR_PROGRAMS:
            with self.subTest(name=name):
                proc = self.run_driver(program)
                self.assertEqual(proc.returncode, exit_codes[expected],
                                 proc.stderr)
                self.assertEqual(proc.stdout, "")
                self.assertNotEqual(proc.stderr, "")

    def test_output_capacity_boundary(self):
        for program in ("print 42;", "let x=1+2*3; print x;"):
            with self.subTest(program=program):
                expected = self.emit(program)
                size = len(expected.encode("ascii"))
                self.assertGreater(size, 0)
                self.assertEqual(self.raw_codegen(program, cap=size), size)
                self.assertEqual(self.raw_codegen(program, cap=size - 1),
                                 CG_LIMIT)
                self.assertEqual(self.raw_codegen(program, cap=0), CG_LIMIT)
                self.assertEqual(self.raw_codegen(program, cap=1), CG_LIMIT)

    def test_language_limits_at_the_boundary(self):
        ok_programs = [
            ("parens_32",
             "print " + "(" * 32 + "1" + ")" * 32 + ";"),
            ("unary_32", "print " + "-" * 32 + "1;"),
            ("blocks_32", "if 1<2 { " * 32 + "print 1; " + "} " * 32),
            ("variables_32",
             "".join("let v%d=1;" % i for i in range(32)) + "print v31;"),
            ("nodes_512", "print 1+1;" * 128),
        ]
        for name, program in ok_programs:
            with self.subTest(name=name):
                self.assertNotEqual(self.raw_codegen(program), CG_LIMIT)
                proc = self.run_driver(program)
                self.assertEqual(proc.returncode, 0, proc.stderr)

        limit_programs = [
            ("parens_33",
             "print " + "(" * 33 + "1" + ")" * 33 + ";"),
            ("unary_33", "print " + "-" * 33 + "1;"),
            ("blocks_33", "if 1<2 { " * 33 + "print 1; " + "} " * 33),
            ("variables_33",
             "".join("let v%d=1;" % i for i in range(32)) + "let v32=1;"),
            ("nodes_516", "print 1+1;" * 129),
        ]
        for name, program in limit_programs:
            with self.subTest(name=name):
                self.assertEqual(self.raw_codegen(program), CG_LIMIT)
                proc = self.run_driver(program)
                self.assertEqual(proc.returncode, 4, proc.stderr)
                self.assertEqual(proc.stdout, "")

    def test_raw_and_driver_agree_on_bytes(self):
        for program in ("", "print 42;", "let b=1<2; print b;"):
            with self.subTest(program=program):
                c_source = self.emit(program)
                self.assertEqual(self.raw_codegen(program),
                                 len(c_source.encode("ascii")))

    # -- driver -------------------------------------------------------------
    def test_driver_writes_output_file(self):
        program = "print 1; print 2<3;"
        expected = self.emit(program)
        out_path = self.tmp / "written.c"
        proc = self.run_driver(program, out_path)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, "")
        self.assertEqual(out_path.read_bytes(), expected.encode("ascii"))

    def test_driver_missing_file(self):
        proc = subprocess.run(
            [str(self.exe), str(self.tmp / "missing.zen")],
            capture_output=True, text=True, timeout=60,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, "")
        self.assertNotEqual(proc.stderr, "")

    def test_driver_usage(self):
        proc = subprocess.run([str(self.exe)], capture_output=True, text=True,
                              timeout=60)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")

    # -- objeto y fuente ----------------------------------------------------
    def test_source_is_a_real_generator(self):
        source = SOURCE.read_text(encoding="utf-8")
        for token in (
            "pub fn zen_codegen(source:u64,length:u64,out:u64,cap:u64)->u64",
            "cg_putc",
            "cg_move_right",
            "cg_apply_bin",
            "volatile_store",
            "uint64_t ",
            "#include <stdio.h>",
            "printf(",
        ):
            self.assertIn(token, source, f"falta {token!r} en codegen.zen")
        self.assertNotIn("extern fn", source)
        self.assertNotIn("fn main", source)

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
