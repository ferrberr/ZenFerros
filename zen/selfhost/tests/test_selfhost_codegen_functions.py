"""TASK-902I: verificacion del generador C selfhost con funciones.

El test compila `zen/selfhost/codegen_functions.zen` como objeto freestanding
con el compilador `zen`, lo enlaza con `zen/selfhost/codegen_functions_driver.c`
y, programa a programa:

1. ejecuta el codegen y obtiene el programa C emitido;
2. lo compila con `cc -std=c11 -O2 -Wall -Wextra -Werror`;
3. lo ejecuta y compara la salida exacta con un interprete de referencia
   independiente escrito aqui (lexer + parser recursivo + evaluador con
   funciones, recursion, ambitos lexicos y return temprano, sin `eval` y sin
   compartir codigo con Zen).

Cubre: funciones con parametros/retorno u64, recursion (factorial, fibonacci,
mutua), llamadas anidadas y como argumento, returns tempranos, funciones no
usadas, orden libre de definicion, funciones sin return (devuelven 0),
asignacion a parametros, bool interno en funciones, cero parametros, nombres
saneados (funciones/parametros llamados como palabras clave de C), prototipos
antes de main, codigos exactos de error (sintaxis, tipos/aridad, limite),
limites de funciones/parametros, capacidad de salida, driver a stdout/fichero,
determinismo, ausencia de imports de libc en el objeto Zen (`nm -u` vacio) y
ausencia de rastros de wrapper o de texto C preexistente copiado.
"""

import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
ZEN = ROOT / "zen/compiler/target/release/zen"
SOURCE = ROOT / "zen/selfhost/codegen_functions.zen"
DRIVER = ROOT / "zen/selfhost/codegen_functions_driver.c"

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
    "fn": "fn",
    "return": "return",
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
    ",": "comma",
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
            tokens.append((TWO_CHAR_OPERATORS[text[pos:pos + 2]],
                           text[pos:pos + 2]))
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
        items = []
        while self.peek() is not None:
            items.append(self.item())
        return items

    def item(self):
        if self.kind() == "fn":
            return self.function()
        return self.statement()

    def function(self):
        self.take("fn")
        name = self.take("ident")[1]
        self.take("lparen")
        params = []
        if self.kind() != "rparen":
            params.append(self.take("ident")[1])
            while self.kind() == "comma":
                self.take("comma")
                params.append(self.take("ident")[1])
        self.take("rparen")
        body = self.block()
        return ("fn", name, params, body)

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
        if kind == "return":
            self.take("return")
            value = self.expression()
            self.take("semi")
            return ("return", value)
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
            name = self.take("ident")[1]
            if self.kind() == "lparen":
                self.take("lparen")
                arguments = []
                if self.kind() != "rparen":
                    arguments.append(self.expression())
                    while self.kind() == "comma":
                        self.take("comma")
                        arguments.append(self.expression())
                self.take("rparen")
                return ("call", name, arguments)
            return ("var", name)
        raise RefError(f"operando inesperado {kind!r}")


# ---------------------------------------------------------------------------
# Referencia: evaluador con funciones, recursion y ambitos lexicos
# ---------------------------------------------------------------------------
def u64(value):
    return value & U64_MAX


class ReturnSignal(Exception):
    def __init__(self, value):
        super().__init__("return")
        self.value = value


class RefInterpreter:
    def __init__(self, functions):
        self.functions = functions
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

    def call(self, name, arguments):
        if name not in self.functions:
            raise RefError(f"funcion no definida: {name}")
        params, body = self.functions[name]
        if len(params) != len(arguments):
            raise RefError(f"aridad incorrecta en {name}")
        args = [u64(self.evaluate(argument)) for argument in arguments]
        saved = self.scopes
        self.scopes = [dict(zip(params, args))]
        value = 0
        try:
            try:
                self.execute_statements(body)
            except ReturnSignal as signal:
                value = signal.value
        finally:
            self.scopes = saved
        return u64(value)

    def evaluate(self, node):
        kind = node[0]
        if kind == "num":
            return u64(node[1])
        if kind == "var":
            return self.lookup(node[1])
        if kind == "call":
            return self.call(node[1], node[2])
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
        elif kind == "return":
            raise ReturnSignal(u64(self.evaluate(statement[1])))
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
    """Salida stdout esperada del lenguaje de TASK-902I."""
    items = RefParser(tokenize(program)).program()
    functions = {}
    for item in items:
        if item[0] == "fn":
            functions[item[1]] = (item[2], item[3])
    interpreter = RefInterpreter(functions)
    for item in items:
        if item[0] != "fn":
            interpreter.execute(item)
    if not interpreter.output:
        return ""
    return "\n".join(interpreter.output) + "\n"


# ---------------------------------------------------------------------------
# Programas validos: codegen -> C -> ejecutable -> stdout
# ---------------------------------------------------------------------------
PROGRAMS = [
    ("factorial_recursive", """
fn fact(n) {
    if n < 2 { return 1; }
    return n * fact(n - 1);
}
print fact(0);
print fact(1);
print fact(5);
print fact(10);
"""),
    ("fibonacci_recursive", """
fn fib(n) {
    if n < 2 { return n; }
    return fib(n - 1) + fib(n - 2);
}
print fib(0);
print fib(1);
print fib(2);
print fib(7);
print fib(12);
"""),
    ("params_and_returns", """
fn add(a, b) { return a + b; }
fn mul(a, b, c) { return a * b * c; }
print add(2, 3);
print mul(2, 3, 4);
print add(mul(1, 2, 3), add(4, 5));
"""),
    ("early_returns", """
fn classify(n) {
    if n < 10 { return 1; }
    if n < 100 { return 2; }
    return 3;
}
print classify(0);
print classify(9);
print classify(10);
print classify(99);
print classify(100);
print classify(12345);
"""),
    ("nested_calls", """
fn inc(x) { return x + 1; }
fn double(x) { return x * 2; }
fn compose(a, b) { return double(inc(a)) + inc(double(b)); }
print compose(1, 2);
print double(double(double(1)));
print inc(inc(inc(inc(0))));
"""),
    ("unused_functions", """
fn used(x) { return x + 1; }
fn unused_one(a, b) { let t = a + b; return t * 2; }
fn unused_two() { let z = 99; return z; }
fn unused_three(a) { return 0; }
print used(41);
"""),
    ("definition_order", """
print later(3);
fn earlier(x) { return later(x) + 1; }
print earlier(4);
fn later(x) { return x * 10; }
"""),
    ("zero_parameters", """
fn one() { return 1; }
fn answer() { return 42; }
print one();
print answer();
print answer() + one();
"""),
    ("parameter_assignment", """
fn countdown(n) {
    let acc = 0;
    while n > 0 {
        acc = acc + n;
        n = n - 1;
    }
    return acc;
}
print countdown(5);
print countdown(10);
"""),
    ("locals_and_shadowing", """
fn shadow(x) {
    let y = x + 1;
    if y > 2 { let y = 100; print y; }
    y = y * 2;
    return y;
}
print shadow(1);
print shadow(2);
print shadow(3);
"""),
    ("bool_inside_function", """
fn is_even(n) {
    let even = n % 2 == 0;
    if even { return 1; }
    return 0;
}
fn both_positive(a, b) {
    let ok = 0 < a && 0 < b;
    if ok { return 1; }
    return 0;
}
print is_even(4);
print is_even(7);
print both_positive(1, 2);
print both_positive(0, 2);
"""),
    ("mutual_recursion", """
fn is_even(n) {
    if n == 0 { return 1; }
    return is_odd(n - 1);
}
fn is_odd(n) {
    if n == 0 { return 0; }
    return is_even(n - 1);
}
print is_even(10);
print is_odd(10);
print is_even(7);
print is_odd(7);
"""),
    ("call_precedence", """
fn id(x) { return x; }
fn inc(x) { return x + 1; }
print 1 + id(2) * 3;
print (1 + id(2)) * 3;
print inc(1) + inc(2) * inc(3);
print id(1) < id(2);
print (id(1) < id(2)) == (id(3) < id(4));
print !(id(5) < id(4));
if id(3) < inc(3) { print 1; } else { print 2; }
"""),
    ("nested_call_arguments", """
fn add(a, b) { return a + b; }
fn inc(x) { return x + 1; }
print add(add(1, 2), add(3, add(4, 5)));
print add(inc(1), inc(add(2, 3)));
"""),
    ("return_direct_call", """
fn square(x) { return x * x; }
fn fourth(x) { return square(square(x)); }
fn forward(x) { return fourth(x) + 1; }
print square(9);
print fourth(3);
print forward(2);
"""),
    ("top_level_mix", """
print triple(2);
let t = 1;
print t;
fn triple(x) { return x * 3; }
let u = triple(t);
print u;
fn quad(x) { return triple(x) + x; }
print quad(4);
"""),
    ("recursion_sum", """
fn sum_to(n) {
    if n == 0 { return 0; }
    return n + sum_to(n - 1);
}
print sum_to(0);
print sum_to(1);
print sum_to(10);
print sum_to(100);
"""),
    ("implicit_zero_return", """
fn nothing() { let x = 1; }
fn maybe(x) { if x == 0 { return 5; } }
print nothing();
print maybe(0);
print maybe(1);
"""),
    ("many_functions", """
fn f0(x) { return x + 1; }
fn f1(x) { return f0(x) * 2; }
fn f2(x) { return f1(x) + 3; }
fn f3(x) { return f2(x) * 4; }
fn f4(x) { return f3(x) - 5; }
fn f5(x) { return f4(x) / 2; }
fn f6(x) { return f5(x) % 1000; }
fn f7(x) { return f6(x) + f0(x); }
print f0(1);
print f3(1);
print f7(1);
"""),
    ("while_with_calls", """
fn step(x) { return x + 2; }
fn limit() { return 10; }
let i = 0;
let s = 0;
while i < limit() {
    s = s + step(i);
    i = i + 1;
}
print s;
print i;
"""),
    ("comparison_chains_with_calls", """
fn one() { return 1; }
fn two() { return 2; }
fn three() { return 3; }
print one() < two();
print one() < two() == (two() < three());
print one() < two() == (three() < two());
print one() + two() < three() * two();
print (one() < two()) == (three() < two());
"""),
    ("tautological_comparisons", """
fn one() { return 1; }
print one() < 0;
print 0 <= one();
print one() >= 0;
print 0 > one();
print one() <= 0;
print 0 >= one();
"""),
    ("without_functions", """
let i = 0;
let s = 0;
while i < 4 {
    s = s + i;
    i = i + 1;
}
print s;
print i;
if 2 < i { print 1; } else { print 0; }
"""),
    ("parameter_shadowing", """
fn f(x) {
    if 0 < x { let x = 10; print x; }
    return x;
}
print f(1);
print f(0);
"""),
    ("return_from_loop", """
fn first_over(limit) {
    let i = 0;
    while i < 1000 {
        if limit < i { return i; }
        i = i + 1;
    }
    return 0;
}
print first_over(0);
print first_over(5);
print first_over(50);
"""),
]


# ---------------------------------------------------------------------------
# Programas invalidos: codigo exacto devuelto por zen_codegen_fns
# ---------------------------------------------------------------------------
def _many_functions(count):
    return "\n".join(
        "fn f%d(a) { return a + %d; }" % (index, index)
        for index in range(count)
    ) + "\nprint f0(1);\n"


def _many_parameters(count):
    params = ",".join("p%d" % index for index in range(count))
    values = ",".join("1" for _ in range(count))
    return "fn f(%s) { return p0; }\nprint f(%s);\n" % (params, values)


ERROR_PROGRAMS = [
    ("syntax_missing_semicolon",
     "fn f(a) { return a }\nprint f(1);", CG_SYNTAX),
    ("syntax_return_top_level", "return 1;", CG_SYNTAX),
    ("syntax_duplicate_function",
     "fn f(a) { return a; } fn f(b) { return b; } print f(1);",
     CG_SYNTAX),
    ("syntax_duplicate_parameter",
     "fn f(a, a) { return a; } print f(1);", CG_SYNTAX),
    ("syntax_nested_function",
     "fn f(a) { fn g() { return 1; } return a; } print f(1);",
     CG_SYNTAX),
    ("syntax_call_statement",
     "fn f(a) { return a; } f(1);", CG_SYNTAX),
    ("syntax_trailing_comma",
     "fn f(a, b) { return a; } print f(1,);", CG_SYNTAX),
    ("syntax_leading_comma",
     "fn f(a, b) { return a; } print f(, 1);", CG_SYNTAX),
    ("syntax_missing_comma",
     "fn f(a, b) { return a; } print f(1 2);", CG_SYNTAX),
    ("syntax_missing_body", "fn f(a); print 1;", CG_SYNTAX),
    ("syntax_unclosed_body",
     "fn f(a) { return a;", CG_SYNTAX),
    ("syntax_unclosed_call",
     "fn f(a) { return a; } print f(1;", CG_SYNTAX),
    ("syntax_missing_parameter_list", "fn f { return 1; }", CG_SYNTAX),
    ("type_arity_more",
     "fn f(a) { return a; } print f(1, 2);", CG_TYPES),
    ("type_arity_less",
     "fn f(a, b) { return a; } print f(1);", CG_TYPES),
    ("type_arity_zero",
     "fn f(a) { return a; } print f();", CG_TYPES),
    ("type_unknown_function", "print missing(1);", CG_TYPES),
    ("type_bool_argument",
     "fn f(a) { return a; } print f(1 < 2);", CG_TYPES),
    ("type_bool_return",
     "fn f(a) { return 1 < 2; } print f(1);", CG_TYPES),
    ("type_bool_return_nested",
     "fn f(a) { if a < 2 { return a < 1; } return a; } print f(1);",
     CG_TYPES),
    ("type_undefined_variable",
     "fn f(a) { return a + b; } print f(1);", CG_TYPES),
    ("type_redeclare_parameter",
     "fn f(a) { let a = 1; return a; } print f(1);", CG_TYPES),
    ("type_redeclare_local",
     "fn f() { let x = 1; let x = 2; return x; } print f();", CG_TYPES),
    ("type_if_condition_u64",
     "fn f(a) { if 1 { return a; } return 0; } print f(1);", CG_TYPES),
    ("type_assignment_bool",
     "fn f(a) { a = 1 < 2; return a; } print f(1);", CG_TYPES),
    ("type_variable_as_function",
     "fn f(a) { let g = 1; return g(2); } print f(1);", CG_TYPES),
    ("limit_functions", _many_functions(65), CG_LIMIT),
    ("limit_parameters", _many_parameters(17), CG_LIMIT),
]


# ---------------------------------------------------------------------------
# Harness C auxiliar: llama a zen_codegen_fns y muestra el valor bruto.
# Es solo un fichero temporal del test; no forma parte de la entrega.
# ---------------------------------------------------------------------------
RAW_HARNESS = r"""
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

extern uint64_t zen_codegen_fns(uint64_t source, uint64_t length, uint64_t out,
                                uint64_t cap);

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "usage: raw_codegen_fns FILE [CAP]\n");
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
    uint64_t written = zen_codegen_fns((uint64_t)(uintptr_t)source,
                                       (uint64_t)size,
                                       (uint64_t)(uintptr_t)out, cap);
    printf("%llu\n", (unsigned long long)written);
    free(out);
    free(source);
    return 0;
}
"""


class SelfHostCodegenFunctionsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ZEN.is_file():
            raise RuntimeError(
                f"falta el compilador {ZEN}; construyelo con: "
                "CARGO_HOME=\"$PWD/.cargo\" cargo build --release --offline "
                "--manifest-path zen/compiler/Cargo.toml"
            )
        cls._tmpdir = tempfile.TemporaryDirectory(prefix="zen-selfhost-cgf-")
        cls.tmp = pathlib.Path(cls._tmpdir.name)
        cls.obj = cls.tmp / "codegen_functions.o"
        cls.exe = cls.tmp / "codegen_functions_driver"
        cls.raw = cls.tmp / "raw_codegen_fns"
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
            [self.cc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
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
            "fn f(n) { if n < 2 { return 1; } return n * f(n - 1); } "
            "print f(5);": "120\n",
            "fn fib(n) { if n < 2 { return n; } "
            "return fib(n - 1) + fib(n - 2); } print fib(7);": "13\n",
            "fn a(n) { if n == 0 { return 1; } return b(n - 1); } "
            "fn b(n) { if n == 0 { return 0; } return a(n - 1); } "
            "print a(8); print b(8);": "1\n0\n",
            "fn nothing() { let x = 1; } print nothing();": "0\n",
            "fn add(a, b) { return a + b; } "
            "print add(1, 2) + add(3, 4);": "10\n",
            "print later(4); fn later(x) { return x + 1; }": "5\n",
            "fn f(n) { let b = n % 2 == 0; if b { return 1; } "
            "return 0; } print f(4);": "1\n",
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

    def test_empty_program_and_functions_only(self):
        c_source = self.emit("")
        self.assertTrue(c_source.startswith("#include <stdio.h>\n"))
        self.assertIn("#include <stdint.h>\n", c_source)
        self.assertIn("int main(void) {\n", c_source)
        self.assertTrue(c_source.endswith("    return 0;\n}\n"))
        self.assertEqual(self.run_generated(""), "")

        only = "fn f(a) { return a; }"
        self.assertEqual(self.run_generated(only), "")
        self.assertIn("static uint64_t fn_0", self.emit(only))

    def test_emission_has_prototypes_before_bodies_and_main(self):
        program = """
fn add(a, b) { return a + b; }
fn fact(n) { if n < 2 { return 1; } return n * fact(n - 1); }
print add(1, 2);
print fact(5);
"""
        c_source = self.emit(program)
        proto_add = c_source.index("static uint64_t fn_0(uint64_t p_0, uint64_t p_1);")
        proto_fact = c_source.index("static uint64_t fn_1(uint64_t p_0);")
        body_add = c_source.index(
            "static uint64_t fn_0(uint64_t p_0, uint64_t p_1) {")
        body_fact = c_source.index("static uint64_t fn_1(uint64_t p_0) {")
        main = c_source.index("int main(void) {")
        self.assertLess(proto_add, body_add)
        self.assertLess(proto_fact, body_fact)
        self.assertLess(proto_add, main)
        self.assertLess(proto_fact, main)
        self.assertLess(body_add, main)
        self.assertLess(body_fact, main)
        self.assertIn("(void)&fn_0;", c_source)
        self.assertIn("(void)&fn_1;", c_source)
        self.assertIn(
            'printf("%llu\\n", (unsigned long long)(fn_0(1ULL, 2ULL)));',
            c_source)
        self.assertIn("return (p_0 + p_1);", c_source)
        self.assertIn("return (p_0 * fn_1((p_0 - 1ULL)));", c_source)
        self.assertIn("static inline int zn_cmp", c_source)
        self.assertIn("zn_cmp(p_0, 2ULL, 12ULL)", c_source)
        self.assertIn("return 0;", c_source)
        self.assertTrue(c_source.endswith("}\n"))
        exe = self.compile_c(program, c_source)
        proc = subprocess.run([str(exe)], capture_output=True, text=True,
                              timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, "3\n120\n")

    def test_function_names_are_sanitized(self):
        program = """
fn printf(x) { return x + 1; }
fn main(y) { return printf(y) * 2; }
fn int(uint64_t) { return uint64_t + 3; }
let main = 5;
print main(20);
print int(main);
"""
        c_source = self.emit(program)
        # Los nombres fuente no aparecen como identificadores C.
        self.assertEqual(c_source.count("main"), 1)
        self.assertEqual(c_source.count("printf"), 2)
        self.assertNotIn("int int", c_source)
        self.assertIn("static uint64_t fn_0", c_source)
        self.assertIn("static uint64_t fn_2", c_source)
        self.assertIn("uint64_t v_0 = 5ULL;", c_source)
        self.assertEqual(self.run_generated(program), "42\n8\n")

    def test_unused_parameters_and_variables_do_not_break_werror(self):
        program = """
fn unused(a, b) { let z = 1; return 0; }
fn used(x) { let y = x + 1; return y; }
let q = 1;
let r = q + 2;
print used(r);
"""
        c_source = self.emit(program)
        self.assertIn("(void)p_0;", c_source)
        self.assertIn("(void)v_2;", c_source)
        self.assertEqual(self.run_generated(program), "4\n")

    def test_emitted_c_has_no_wrapper_trace_or_copied_text(self):
        program = "fn inc(x) { return x + 1; } print inc(41);"
        c_source = self.emit(program)
        lowered = c_source.lower()
        for forbidden in (
            "zen_codegen",
            "zen_codegen_fns",
            "codegen_functions.zen",
            "codegen_functions_driver",
            "task-902",
            "extern",
            "rust",
            "#include <stdlib.h>",
        ):
            self.assertNotIn(forbidden, lowered, forbidden)
        self.assertNotIn(program, c_source)

        generator_source = SOURCE.read_text(encoding="utf-8")
        self.assertNotIn(program, generator_source)
        self.assertNotIn(
            'printf("%llu\\n", (unsigned long long)(42ULL));',
            generator_source)
        self.assertNotIn(
            "#include <stdio.h>\n#include <stdint.h>\n\nint main(void) {",
            generator_source,
        )

        # El helper de comparaciones solo aparece si hay comparaciones.
        self.assertNotIn("zn_cmp", self.emit("print 42;"))
        self.assertIn("static inline int zn_cmp", self.emit("print 1 < 2;"))

        first = self.emit("fn f(x) { return x; } print f(1);")
        second = self.emit("fn f(x) { return x; } print f(2);")
        self.assertNotEqual(first, second)

    def test_deterministic(self):
        program = """
fn fib(n) { if n < 2 { return n; } return fib(n - 1) + fib(n - 2); }
print fib(10);
"""
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
                self.assertEqual(self.raw_codegen(program), expected, name)

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
        programs = [
            "fn inc(x) { return x + 1; } print inc(41);",
            "fn add(a, b) { return a + b; } print add(1, 2);",
            "fn f(a) { if a < 2 { return 0; } return 1; } print f(1);",
        ]
        for program in programs:
            with self.subTest(program=program):
                expected = self.emit(program)
                size = len(expected.encode("ascii"))
                self.assertGreater(size, 0)
                self.assertEqual(self.raw_codegen(program, cap=size), size)
                self.assertEqual(self.raw_codegen(program, cap=size - 1),
                                 CG_LIMIT)
                self.assertEqual(self.raw_codegen(program, cap=0), CG_LIMIT)
                self.assertEqual(self.raw_codegen(program, cap=1), CG_LIMIT)

    def test_function_and_parameter_limits_at_the_boundary(self):
        # 64 funciones y 16 parametros son validos y generan C compilable.
        functions = "\n".join(
            "fn f%d(a) { return a + %d; }" % (index, index)
            for index in range(64)
        ) + "\nprint f0(1);\nprint f63(1);\n"
        self.assertEqual(self.run_generated(functions), "1\n64\n")

        params = ",".join("p%d" % index for index in range(16))
        values = ",".join(str(index + 1) for index in range(16))
        total = " + ".join("p%d" % index for index in range(16))
        program = "fn f(%s) { return %s; } print f(%s);" % (
            params, total, values)
        self.assertEqual(self.run_generated(program), "136\n")

        # 65 funciones o 17 parametros exceden el limite (0xFFFFFFFF).
        too_many_functions = "\n".join(
            "fn f%d(a) { return a + %d; }" % (index, index)
            for index in range(65)
        ) + "\nprint f0(1);\n"
        self.assertEqual(self.raw_codegen(too_many_functions), CG_LIMIT)
        too_many_params = "fn f(%s) { return p0; }\nprint f(%s);\n" % (
            ",".join("p%d" % index for index in range(17)),
            ",".join("1" for _ in range(17)))
        self.assertEqual(self.raw_codegen(too_many_params), CG_LIMIT)

        # 17 argumentos exceden el limite de 16 por llamada.
        seventeen = "fn f(%s) { return p0; }\nprint f(%s);\n" % (
            ",".join("p%d" % index for index in range(16)),
            ",".join("1" for _ in range(17)))
        self.assertEqual(self.raw_codegen(seventeen), CG_LIMIT)

    def test_raw_and_driver_agree_on_bytes(self):
        for program in (
            "",
            "fn f(a) { return a; } print f(1);",
            "fn a(x) { return x; } fn b(y) { return a(y) + 1; } print b(2);",
        ):
            with self.subTest(program=program):
                c_source = self.emit(program)
                self.assertEqual(self.raw_codegen(program),
                                 len(c_source.encode("ascii")))

    # -- driver -------------------------------------------------------------
    def test_driver_writes_output_file(self):
        program = "fn inc(x) { return x + 1; } print inc(1); print inc(2);"
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
            "pub fn zen_codegen_fns(source:u64,length:u64,out:u64,cap:u64)->u64",
            "fg_putc",
            "fg_move_right",
            "fg_apply_bin",
            "fg_put_fn",
            "volatile_store",
            "static uint64_t ",
            "#include <stdio.h>",
            "printf(",
            "return ",
            "zn_cmp",
            "fg_wrap_cmp",
        ):
            self.assertIn(token, source,
                          f"falta {token!r} en codegen_functions.zen")
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
