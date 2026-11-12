"""TASK-902J: verificacion del generador C selfhost con arrays fijos de u64.

El test compila `zen/selfhost/codegen_arrays.zen` como objeto freestanding con
el compilador `zen`, lo enlaza con `zen/selfhost/codegen_arrays_driver.c` y,
programa a programa:

1. ejecuta el codegen y obtiene el programa C emitido;
2. lo compila con `cc -std=c11 -O2 -Wall -Wextra -Werror`;
3. lo ejecuta y compara la salida exacta con un interprete de referencia
   independiente escrito aqui (lexer + parser recursivo + evaluador con
   funciones, recursion, ambitos lexicos, return temprano y arrays fijos,
   sin `eval` y sin compartir codigo con Zen).

Cubre: inicializacion de arrays `[e0, ..., eN-1]`, lectura y escritura por
indice, expresiones de indice (aritmetica, parentesis, modulo), indices
anidados, bucles que recorren/escriben arrays, arrays locales en funciones,
recursion con arrays locales, sombreado en bloques y funciones, arrays no
usados (sin romper -Werror), arrays de un elemento y de 64 elementos,
precedencia de operadores alrededor del indice, errores exactos de sintaxis y
tipos (indice no u64, indice sobre no-array, array como parametro/argumento,
array completo en print/aritmetica/comparacion/asignacion/return/condicion,
elemento no u64), limites (65 elementos, 33 arrays, profundidad 33, 65
funciones, 17 parametros), capacidad de salida, driver a stdout/fichero,
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
SOURCE = ROOT / "zen/selfhost/codegen_arrays.zen"
DRIVER = ROOT / "zen/selfhost/codegen_arrays_driver.c"

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
    "[": "lbracket",
    "]": "rbracket",
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
            if self.kind() == "lbracket":
                self.take("lbracket")
                elements = [self.expression()]
                while self.kind() == "comma":
                    self.take("comma")
                    elements.append(self.expression())
                self.take("rbracket")
                self.take("semi")
                return ("let_arr", name, elements)
            value = self.expression()
            self.take("semi")
            return ("let", name, value)
        if kind == "ident":
            name = self.take("ident")[1]
            if self.kind() == "lbracket":
                self.take("lbracket")
                index = self.expression()
                self.take("rbracket")
                self.take("assign")
                value = self.expression()
                self.take("semi")
                return ("assign_index", name, index, value)
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
            if self.kind() == "lbracket":
                self.take("lbracket")
                index = self.expression()
                self.take("rbracket")
                return ("index", name, index)
            return ("var", name)
        raise RefError(f"operando inesperado {kind!r}")


# ---------------------------------------------------------------------------
# Referencia: evaluador con funciones, recursion, ambitos y arrays fijos
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

    def lookup_array(self, name):
        value = self.lookup(name)
        if not isinstance(value, list):
            raise RefError(f"{name} no es un array")
        return value

    def element(self, name, index_node):
        array = self.lookup_array(name)
        index = u64(self.evaluate(index_node))
        if index >= len(array):
            raise RefError(f"indice fuera de rango en {name}: {index}")
        return array[index]

    def evaluate(self, node):
        kind = node[0]
        if kind == "num":
            return u64(node[1])
        if kind == "var":
            return self.lookup(node[1])
        if kind == "array":
            return [u64(self.evaluate(element)) for element in node[1]]
        if kind == "index":
            return self.element(node[1], node[2])
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
            if isinstance(value, list):
                raise RefError("un array solo nace de un literal")
            self.scopes[-1][statement[1]] = value
        elif kind == "let_arr":
            self.scopes[-1][statement[1]] = self.evaluate(
                ("array", statement[2]))
        elif kind == "assign":
            value = self.evaluate(statement[2])
            if isinstance(value, list):
                raise RefError("un array no es asignable")
            self.scopes[self.find_scope(statement[1])][statement[1]] = value
        elif kind == "assign_index":
            array = self.lookup_array(statement[1])
            index = u64(self.evaluate(statement[2]))
            if index >= len(array):
                raise RefError(
                    f"indice fuera de rango en {statement[1]}: {index}")
            value = self.evaluate(statement[3])
            if isinstance(value, list):
                raise RefError("un array no es asignable")
            array[index] = u64(value)
        elif kind == "print":
            value = self.evaluate(statement[1])
            if isinstance(value, bool):
                self.output.append("1" if value else "0")
            elif isinstance(value, list):
                raise RefError("un array no se imprime")
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
    """Salida stdout esperada del lenguaje de TASK-902J."""
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


def _array_sequence(count):
    return ", ".join(str(index + 1) for index in range(count))


# ---------------------------------------------------------------------------
# Programas validos: codegen -> C -> ejecutable -> stdout
# ---------------------------------------------------------------------------
PROGRAMS = [
    # -- TASK-902I: funciones (regresion) -----------------------------------
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
    ("implicit_zero_return", """
fn nothing() { let x = 1; }
fn maybe(x) { if x == 0 { return 5; } }
print nothing();
print maybe(0);
print maybe(1);
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
    ("tautological_comparisons", """
fn one() { return 1; }
print one() < 0;
print 0 <= one();
print one() >= 0;
print 0 > one();
print one() <= 0;
print 0 >= one();
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
    # -- TASK-902J: arrays fijos de u64 -------------------------------------
    ("array_init_read", """
let a = [10, 20, 30];
print a[0];
print a[1];
print a[2];
"""),
    ("array_single_element", """
let a = [42];
print a[0];
a[0] = a[0] + 1;
print a[0];
"""),
    ("array_write", """
let a = [1, 2, 3];
a[0] = 7;
a[2] = 9;
print a[0];
print a[1];
print a[2];
"""),
    ("array_loop_sum", """
let a = [1, 2, 3, 4, 5];
let i = 0;
let s = 0;
while i < 5 { s = s + a[i]; i = i + 1; }
print s;
"""),
    ("array_loop_write", """
let a = [0, 0, 0, 0];
let i = 0;
while i < 4 { a[i] = i * i; i = i + 1; }
print a[0];
print a[1];
print a[2];
print a[3];
"""),
    ("array_index_precedence", """
let a = [10, 20, 30, 40, 50];
let i = 1;
print a[i + 2];
print a[(i + 1) * 2];
print a[i] + 1;
print a[i * 2] * 2;
print a[(i + 2) % 4] - a[0];
print a[0] + a[1] * a[2];
print (a[0] + a[1]) * a[2];
"""),
    ("array_nested_index", """
let a = [10, 20, 30];
let b = [2, 0, 1];
print a[b[0]];
print a[b[1] + 1];
print a[b[2] + 1];
print a[a[1] / 20];
"""),
    ("array_nested_same", """
let a = [1, 0, 2];
print a[a[0]];
print a[a[a[0]]];
"""),
    ("array_function_local", """
fn sum3(x) {
    let a = [x, x + 1, x + 2];
    return a[0] + a[1] + a[2];
}
print sum3(10);
print sum3(0);
"""),
    ("array_function_write", """
fn build(n) {
    let a = [0, 0, 0];
    a[0] = n;
    a[1] = a[0] + 1;
    a[2] = a[0] * a[1];
    return a[0] + a[1] + a[2];
}
print build(2);
print build(5);
"""),
    ("array_shadowing_block", """
let a = [1, 2];
if 0 < 1 { let a = [9, 8]; print a[0]; print a[1]; }
print a[0];
print a[1];
"""),
    ("array_shadowing_function", """
fn f(x) {
    let a = [x, x + 1];
    if 0 < x { let x = 99; print a[0]; print x; }
    return a[1];
}
print f(5);
print f(0);
"""),
    ("array_while_redeclare", """
let i = 0;
let s = 0;
while i < 3 {
    let a = [i, i + 1];
    s = s + a[0] + a[1];
    i = i + 1;
}
print s;
"""),
    ("array_condition_compare", """
let a = [1, 2];
let ok = a[0] < a[1];
if ok { print 1; } else { print 0; }
print a[0] == 1;
print a[1] != 2;
print !(a[0] < a[1]);
"""),
    ("array_calls_in_literal", """
fn sq(x) { return x * x; }
let a = [sq(1), sq(2), sq(3)];
print a[0];
print a[1];
print a[2];
print a[2] - a[0];
"""),
    ("array_element_in_call", """
fn add(x, y) { return x + y; }
let a = [4, 5];
print add(a[0], a[1]);
print add(a[1], add(a[0], 1));
"""),
    ("array_target_expressions", """
let a = [0, 0, 0];
let i = 1;
a[i + 1] = 5;
a[i - 1] = 6;
print a[0];
print a[1];
print a[2];
"""),
    ("array_target_call_index", """
fn one() { return 1; }
let a = [0, 0, 0];
a[one()] = 42;
a[one() + 1] = 7;
print a[0];
print a[1];
print a[2];
"""),
    ("array_recursion_local", """
fn fib(n) {
    let a = [0, 1];
    if n < 2 { return a[n]; }
    return fib(n - 1) + fib(n - 2);
}
print fib(0);
print fib(1);
print fib(10);
"""),
    ("array_unused_locals", """
fn unused(x) { let a = [1, 2]; return 0; }
let b = [3];
print unused(1);
"""),
    ("array_64_elements",
     "let a = [%s];\n"
     "let i = 0;\n"
     "let s = 0;\n"
     "while i < 64 { s = s + a[i]; i = i + 1; }\n"
     "print s;\n"
     "print a[63];\n" % _array_sequence(64)),
    ("array_reference_elements", """
let a = [1, 2];
let b = [a[0], a[1] + 1, a[0] + a[1]];
print b[0];
print b[1];
print b[2];
"""),
    ("array_let_from_element", """
let a = [5, 6];
let b = a[0];
let c = a[1] + 1;
print b;
print c;
"""),
    ("array_write_from_block", """
fn f() {
    let a = [1];
    if 0 < 1 { a[0] = 5; }
    return a[0];
}
print f();
"""),
    ("array_while_element_condition", """
let a = [1, 2];
let i = 0;
while i < a[1] { print i; i = i + 1; }
"""),
    ("array_modular_index", """
let a = [5, 10, 15, 20];
let i = 0;
while i < 8 { print a[i % 4]; i = i + 1; }
"""),
    ("array_mixed_functions", """
fn scale(x) { return x * 2; }
fn total(n) {
    let a = [scale(n), scale(n + 1), scale(n + 2)];
    let s = 0;
    let i = 0;
    while i < 3 { s = s + a[i]; i = i + 1; }
    return s;
}
let base = [1, 2, 3];
print total(base[0]);
print total(base[2]);
print total(scale(2));
"""),
]


# ---------------------------------------------------------------------------
# Programas invalidos: codigo exacto devuelto por zen_codegen_arrays
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


def _many_arrays(count):
    lines = "\n".join("let a%d = [%d];" % (index, index)
                      for index in range(count))
    return lines + "\nprint a0[0];\n"


def _nested_index(depth):
    return ("let a = [0, 1];\nprint " + "a[" * depth + "0" + "]" * depth
            + ";\n")


ERROR_PROGRAMS = [
    # -- sintaxis -----------------------------------------------------------
    ("syntax_array_empty", "let a = []; print 1;", CG_SYNTAX),
    ("syntax_array_missing_semicolon", "let a = [1, 2] print 1;", CG_SYNTAX),
    ("syntax_array_missing_bracket", "let a = [1, 2; print 1;", CG_SYNTAX),
    ("syntax_array_trailing_comma", "let a = [1, 2,]; print 1;", CG_SYNTAX),
    ("syntax_array_leading_comma", "let a = [, 1]; print 1;", CG_SYNTAX),
    ("syntax_array_missing_comma", "let a = [1 2]; print 1;", CG_SYNTAX),
    ("syntax_array_nested", "let a = [[1]]; print 1;", CG_SYNTAX),
    ("syntax_array_in_expression", "let a = 1 + [2]; print 1;", CG_SYNTAX),
    ("syntax_index_empty", "let a = [1]; print a[];", CG_SYNTAX),
    ("syntax_index_unclosed", "let a = [1]; print a[0;", CG_SYNTAX),
    ("syntax_index_extra", "let a = [1]; print a[0]];", CG_SYNTAX),
    ("syntax_index_statement", "let a = [1]; a[0];", CG_SYNTAX),
    ("syntax_index_no_assignment", "let a = [1]; a[0] + 1;", CG_SYNTAX),
    ("syntax_truncated_expression", "let a = [1, 2]; print 1", CG_SYNTAX),
    ("syntax_truncated_index", "let a = [1]; a[0]", CG_SYNTAX),
    ("syntax_missing_semicolon", "fn f(a) { return a }\nprint f(1);",
     CG_SYNTAX),
    ("syntax_return_top_level", "return 1;", CG_SYNTAX),
    ("syntax_duplicate_function",
     "fn f(a) { return a; } fn f(b) { return b; } print f(1);",
     CG_SYNTAX),
    ("syntax_duplicate_parameter",
     "fn f(a, a) { return a; } print f(1);", CG_SYNTAX),
    ("syntax_nested_function",
     "fn f(a) { fn g() { return 1; } return a; } print f(1);", CG_SYNTAX),
    ("syntax_call_statement", "fn f(a) { return a; } f(1);", CG_SYNTAX),
    # -- tipos --------------------------------------------------------------
    ("type_index_bool", "let a = [1]; print a[1 < 2];", CG_TYPES),
    ("type_index_non_array", "let x = 1; print x[0];", CG_TYPES),
    ("type_index_of_element", "let a = [1]; print a[0][0];", CG_SYNTAX),
    ("type_parameter_is_not_array",
     "fn f(x) { return x[0]; } print f(1);", CG_TYPES),
    ("type_array_argument",
     "fn f(x) { return x; } let a = [1]; print f(a);", CG_TYPES),
    ("type_array_print", "let a = [1]; print a;", CG_TYPES),
    ("type_array_arithmetic", "let a = [1]; print a + 1;", CG_TYPES),
    ("type_array_let_copy", "let a = [1]; let b = a; print 1;", CG_TYPES),
    ("type_array_assignment", "let a = [1]; let b = [2]; a = b; print 1;",
     CG_TYPES),
    ("type_array_literal_assignment", "let a = [1]; a = [2]; print 1;",
     CG_TYPES),
    ("type_array_comparison",
     "let a = [1]; let b = [2]; print a < b;", CG_TYPES),
    ("type_array_return",
     "fn f() { let a = [1]; return a; } print 1;", CG_TYPES),
    ("type_array_condition",
     "fn f() { let a = [1]; if a { return 1; } return 0; } print 1;",
     CG_TYPES),
    ("type_array_element_value", "let a = [1 < 2]; print 1;", CG_TYPES),
    ("type_element_assignment_bool",
     "let a = [1]; a[0] = 1 < 2; print 1;", CG_TYPES),
    ("type_element_assignment_array",
     "let a = [1]; a[0] = a; print 1;", CG_TYPES),
    ("type_array_as_index",
     "let a = [1]; let b = [2]; a[b] = 1; print 1;", CG_TYPES),
    ("type_undefined_target", "a[0] = 1; print 1;", CG_TYPES),
    ("type_undefined_variable",
     "fn f(a) { return a + b; } print f(1);", CG_TYPES),
    ("type_redeclare_local",
     "fn f() { let x = 1; let x = 2; return x; } print f();", CG_TYPES),
    ("type_redeclare_array", "let a = [1]; let a = [2]; print 1;", CG_TYPES),
    ("type_if_condition_u64",
     "fn f(a) { if 1 { return a; } return 0; } print f(1);", CG_TYPES),
    ("type_arity_more", "fn f(a) { return a; } print f(1, 2);", CG_TYPES),
    ("type_arity_less", "fn f(a, b) { return a; } print f(1);", CG_TYPES),
    ("type_unknown_function", "print missing(1);", CG_TYPES),
    ("type_bool_argument",
     "fn f(a) { return a; } print f(1 < 2);", CG_TYPES),
    ("type_bool_return", "fn f(a) { return 1 < 2; } print f(1);", CG_TYPES),
    # -- limites ------------------------------------------------------------
    ("limit_array_size", "let a = [%s]; print 1;\n" % _array_sequence(65),
     CG_LIMIT),
    ("limit_array_depth_33", _nested_index(33), CG_LIMIT),
    ("limit_variables_33_arrays", _many_arrays(33), CG_LIMIT),
    ("limit_functions", _many_functions(65), CG_LIMIT),
    ("limit_parameters", _many_parameters(17), CG_LIMIT),
]


# ---------------------------------------------------------------------------
# Harness C auxiliar: llama a zen_codegen_arrays y muestra el valor bruto.
# Es solo un fichero temporal del test; no forma parte de la entrega.
# ---------------------------------------------------------------------------
RAW_HARNESS = r"""
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

extern uint64_t zen_codegen_arrays(uint64_t source, uint64_t length,
                                   uint64_t out, uint64_t cap);

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "usage: raw_codegen_arrays FILE [CAP]\n");
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
    uint64_t written = zen_codegen_arrays((uint64_t)(uintptr_t)source,
                                          (uint64_t)size,
                                          (uint64_t)(uintptr_t)out, cap);
    printf("%llu\n", (unsigned long long)written);
    free(out);
    free(source);
    return 0;
}
"""


class SelfHostCodegenArraysTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ZEN.is_file():
            raise RuntimeError(
                f"falta el compilador {ZEN}; construyelo con: "
                "CARGO_HOME=\"$PWD/.cargo\" cargo build --release --offline "
                "--manifest-path zen/compiler/Cargo.toml"
            )
        cls._tmpdir = tempfile.TemporaryDirectory(prefix="zen-selfhost-cga-")
        cls.tmp = pathlib.Path(cls._tmpdir.name)
        cls.obj = cls.tmp / "codegen_arrays.o"
        cls.exe = cls.tmp / "codegen_arrays_driver"
        cls.raw = cls.tmp / "raw_codegen_arrays"
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
            "fn nothing() { let x = 1; } print nothing();": "0\n",
            "let a = [1, 2, 3]; print a[1];": "2\n",
            "let a = [1, 2]; a[0] = 9; print a[0]; print a[1];": "9\n2\n",
            "let a = [1, 0]; print a[a[0]];": "0\n",
            "fn f() { let a = [5, 6]; return a[0] + a[1]; } print f();":
            "11\n",
            "let a = [1, 2]; if 0 < 1 { let a = [7]; print a[0]; } "
            "print a[1];": "7\n2\n",
            "let a = [1, 2]; let i = 0; let s = 0; "
            "while i < 2 { s = s + a[i]; i = i + 1; } print s;": "3\n",
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
        self.assertIn("#include <stddef.h>\n", c_source)
        self.assertIn("int main(void) {\n", c_source)
        self.assertTrue(c_source.endswith("    return 0;\n}\n"))
        self.assertEqual(self.run_generated(""), "")

        only = "fn f(a) { return a; }"
        self.assertEqual(self.run_generated(only), "")
        self.assertIn("static uint64_t fn_0", self.emit(only))

    def test_emission_has_array_declarations_and_indices(self):
        program = """
let a = [10, 20, 30];
print a[0];
a[1] = a[2];
"""
        c_source = self.emit(program)
        self.assertIn("uint64_t v_0[3] = { 10ULL, 20ULL, 30ULL };", c_source)
        self.assertIn("(void)v_0;", c_source)
        self.assertIn(
            'printf("%llu\\n", (unsigned long long)(v_0[(size_t)(0ULL)]));',
            c_source)
        self.assertIn(
            "v_0[(size_t)(1ULL)] = v_0[(size_t)(2ULL)];", c_source)
        self.assertEqual(self.run_generated(program), "10\n")

        function_program = """
fn f(x) { let a = [x, x + 1]; return a[1]; }
print f(2);
"""
        c_source = self.emit(function_program)
        self.assertIn("static uint64_t fn_0(uint64_t p_0) {", c_source)
        self.assertIn("uint64_t v_1[2] = { p_0, (p_0 + 1ULL) };", c_source)
        self.assertIn("return v_1[(size_t)(1ULL)];", c_source)
        self.assertEqual(self.run_generated(function_program), "3\n")

    def test_index_operands_keep_parentheses(self):
        program = """
let a = [10, 20, 30, 40];
let i = 1;
print a[i + 2];
print a[i] + 1;
"""
        c_source = self.emit(program)
        self.assertIn("v_0[(size_t)((v_1 + 2ULL))]", c_source)
        self.assertIn("(v_0[(size_t)(v_1)] + 1ULL)", c_source)
        self.assertEqual(self.run_generated(program), "40\n21\n")

    def test_array_names_are_sanitized(self):
        program = """
let int = [1, 2];
let printf = [3];
print int[1];
print printf[0];
"""
        c_source = self.emit(program)
        self.assertIn("uint64_t v_0[2] = { 1ULL, 2ULL };", c_source)
        self.assertIn("uint64_t v_1[1] = { 3ULL };", c_source)
        self.assertNotIn("int int", c_source)
        self.assertNotIn("int printf", c_source)
        self.assertEqual(self.run_generated(program), "2\n3\n")

    def test_unused_arrays_do_not_break_werror(self):
        program = """
fn unused(x) { let a = [1, 2]; return 0; }
let b = [3];
print unused(1);
"""
        c_source = self.emit(program)
        self.assertIn("(void)p_0;", c_source)
        self.assertIn("(void)v_1;", c_source)
        self.assertIn("(void)v_0;", c_source)
        self.assertEqual(self.run_generated(program), "0\n")

    def test_emitted_c_has_no_wrapper_trace_or_copied_text(self):
        program = "let a = [31, 47]; print a[0]; a[1] = 3;"
        c_source = self.emit(program)
        lowered = c_source.lower()
        for forbidden in (
            "zen_codegen",
            "codegen_arrays",
            "codegen_arrays.zen",
            "codegen_arrays_driver",
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
            "uint64_t v_0[2] = { 31ULL, 47ULL };", generator_source)
        self.assertNotIn(
            "#include <stdio.h>\n#include <stdint.h>\n#include <stddef.h>\n\n"
            "int main(void) {",
            generator_source,
        )

        # El helper de comparaciones solo aparece si hay comparaciones.
        self.assertNotIn("zn_cmp", self.emit("let a = [1]; print a[0];"))
        self.assertIn("static inline int zn_cmp",
                      self.emit("let a = [1]; print a[0] < 1;"))

        first = self.emit("let a = [1]; print a[0];")
        second = self.emit("let a = [1]; print a[1];")
        self.assertNotEqual(first, second)

    def test_deterministic(self):
        program = """
fn total(x) { let b = [x, x + 1]; return b[0] + b[1]; }
let a = [1, 2, 3];
print total(a[2]);
a[1] = total(4);
print a[1];
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

    def test_array_limits_at_the_boundary(self):
        # 1 y 64 elementos son validos.
        self.assertEqual(self.run_generated("let a = [7]; print a[0];"), "7\n")
        self.assertEqual(
            self.run_generated(
                "let a = [%s]; print a[63];\n" % _array_sequence(64)),
            "64\n")

        # Profundidad 32 de indices anidados es valida; 33 excede el limite.
        self.assertEqual(self.run_generated(_nested_index(32)), "0\n")
        self.assertEqual(self.raw_codegen(_nested_index(33)), CG_LIMIT)

        # 32 arrays activos son validos; 33 exceden el limite.
        self.assertEqual(
            self.run_generated(_many_arrays(32)), "0\n")
        self.assertEqual(self.raw_codegen(_many_arrays(33)), CG_LIMIT)

    def test_function_and_parameter_limits_at_the_boundary(self):
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

        self.assertEqual(self.raw_codegen(_many_functions(65)), CG_LIMIT)
        self.assertEqual(self.raw_codegen(_many_parameters(17)), CG_LIMIT)

    def test_output_capacity_boundary(self):
        programs = [
            "let a = [10, 20, 30]; print a[0]; a[1] = 7; print a[1];",
            "fn f(x) { let a = [x, x + 1]; return a[0] + a[1]; } print f(3);",
            "let a = [1, 2, 3]; let i = 0; "
            "while i < 3 { a[i] = a[i] * 2; i = i + 1; } print a[2];",
            "",
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

    def test_raw_and_driver_agree_on_bytes(self):
        for program in (
            "",
            "let a = [1, 2]; print a[0];",
            "fn f(x) { let a = [x]; return a[0] + 1; } print f(2);",
        ):
            with self.subTest(program=program):
                c_source = self.emit(program)
                self.assertEqual(self.raw_codegen(program),
                                 len(c_source.encode("ascii")))

    # -- driver -------------------------------------------------------------
    def test_driver_writes_output_file(self):
        program = "let a = [1, 2]; print a[0]; a[1] = 4; print a[1];"
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
            "pub fn zen_codegen_arrays(source:u64,length:u64,out:u64,cap:u64)->u64",
            "fg_putc",
            "fg_move_right",
            "fg_apply_bin",
            "volatile_store",
            "static uint64_t ",
            "#include <stdio.h>",
            "#include <stddef.h>",
            "printf(",
            "return ",
            "zn_cmp",
            "fg_wrap_cmp",
            "[(size_t)(",
            "uint64_t ",
            "velems",
            "osub",
        ):
            self.assertIn(token, source,
                          f"falta {token!r} en codegen_arrays.zen")
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
