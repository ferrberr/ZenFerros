"""TASK-902K: verificacion del generador C selfhost con structs nominales.

El test compila `zen/selfhost/codegen_structs.zen` como objeto freestanding con
el compilador `zen`, lo enlaza con `zen/selfhost/codegen_structs_driver.c` y,
programa a programa:

1. ejecuta el codegen y obtiene el programa C emitido;
2. lo compila con `cc -std=c11 -O2 -Wall -Wextra -Werror`;
3. lo ejecuta y compara la salida exacta con un interprete de referencia
   independiente escrito aqui (lexer + parser recursivo + evaluador con
   funciones, recursion, ambitos lexicos, return temprano, arrays fijos y
   structs nominales, sin `eval` y sin compartir codigo con Zen).

Cubre: declaracion de structs con 1..8 campos u64, literales de struct solo en
`let` (campos en cualquier orden, coma final), lectura y escritura de campos
(`let mut` obligatorio para escribir), varios structs y varios campos, structs
locales en funciones, sombreado en bloques y funciones, structs declarados
despues de la funcion que los usa, campos como indices de array y como
argumentos, nombres fuente que son palabras clave de C, structs y variables no
usados (sin romper -Werror), errores exactos de sintaxis y tipos (campo
faltante/extra/repetido/desconocido, tipo no u64, copia, asignacion completa,
parametro, retorno, comparacion, condicion, print, array de structs, campo de
struct, struct vacio, >8 campos, >16 structs), limites (8/9 campos, 16/17
structs, 32/33 variables, capacidad de salida), determinismo, driver a
stdout/fichero, ausencia de imports de libc en el objeto Zen (`nm -u` vacio) y
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
SOURCE = ROOT / "zen/selfhost/codegen_structs.zen"
DRIVER = ROOT / "zen/selfhost/codegen_structs_driver.c"

U64_MAX = (1 << 64) - 1
CG_LIMIT = 0xFFFFFFFF
CG_SYNTAX = 0xFFFFFFFE
CG_TYPES = 0xFFFFFFFD

# ---------------------------------------------------------------------------
# Referencia: scanner
# ---------------------------------------------------------------------------
KEYWORDS = {
    "let": "let",
    "mut": "mut",
    "print": "print",
    "if": "if",
    "else": "else",
    "while": "while",
    "fn": "fn",
    "return": "return",
    "struct": "struct",
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
    ".": "dot",
    ":": "colon",
}
WHITESPACE = " \t\r\n\v\f"


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

    def kind_at(self, offset):
        index = self.pos + offset
        if index >= len(self.tokens):
            return None
        return self.tokens[index][0]

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
        if self.kind() == "struct":
            return self.struct_decl()
        if self.kind() == "fn":
            return self.function()
        return self.statement()

    def struct_decl(self):
        self.take("struct")
        name = self.take("ident")[1]
        self.take("lbrace")
        fields = []
        while self.kind() != "rbrace":
            field_name = self.take("ident")[1]
            self.take("colon")
            field_type = self.take("ident")[1]
            if field_type != "u64":
                raise RefError(f"campo {field_name} no es u64")
            fields.append(field_name)
            if self.kind() == "comma":
                self.take("comma")
            else:
                break
        self.take("rbrace")
        if not fields:
            raise RefError(f"struct {name} vacio")
        if len(fields) > 8:
            raise RefError(f"struct {name} con mas de 8 campos")
        return ("struct", name, fields)

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

    def struct_literal(self):
        type_name = self.take("ident")[1]
        self.take("lbrace")
        fields = []
        while self.kind() != "rbrace":
            field_name = self.take("ident")[1]
            self.take("colon")
            fields.append((field_name, self.expression()))
            if self.kind() == "comma":
                self.take("comma")
            else:
                break
        self.take("rbrace")
        return type_name, fields

    def statement(self):
        kind = self.kind()
        if kind == "let":
            self.take("let")
            mutable = False
            if self.kind() == "mut":
                self.take("mut")
                mutable = True
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
                return ("let_arr", mutable, name, elements)
            if self.kind() == "ident" and self.kind_at(1) == "lbrace":
                type_name, fields = self.struct_literal()
                self.take("semi")
                return ("let_struct", mutable, name, type_name, fields)
            value = self.expression()
            self.take("semi")
            return ("let", mutable, name, value)
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
            body = self.block()
            other = None
            if self.kind() == "else":
                self.take("else")
                other = self.block()
            return ("if", condition, body, other)
        if kind == "while":
            self.take("while")
            condition = self.expression()
            body = self.block()
            return ("while", condition, body)
        if kind == "ident":
            name = self.take("ident")[1]
            if self.kind() == "dot":
                self.take("dot")
                field = self.take("ident")[1]
                self.take("assign")
                value = self.expression()
                self.take("semi")
                return ("assign_field", name, field, value)
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
        raise RefError(f"sentencia inesperada {kind!r}")

    # -- expresiones --------------------------------------------------------
    def expression(self):
        return self.or_expr()

    def or_expr(self):
        node = self.and_expr()
        while self.kind() == "or":
            self.take("or")
            node = ("bin", "or", node, self.and_expr())
        return node

    def and_expr(self):
        node = self.cmp_expr()
        while self.kind() == "and":
            self.take("and")
            node = ("bin", "and", node, self.cmp_expr())
        return node

    def cmp_expr(self):
        node = self.sum_expr()
        while self.kind() in ("eq", "ne", "lt", "le", "gt", "ge"):
            operator = self.take()[0]
            node = ("bin", operator, node, self.sum_expr())
        return node

    def sum_expr(self):
        node = self.prod_expr()
        while self.kind() in ("plus", "minus"):
            operator = self.take()[0]
            node = ("bin", operator, node, self.prod_expr())
        return node

    def prod_expr(self):
        node = self.unary()
        while self.kind() in ("star", "slash", "percent"):
            operator = self.take()[0]
            node = ("bin", operator, node, self.unary())
        return node

    def unary(self):
        if self.kind() in ("minus", "not"):
            operator = self.take()[0]
            return ("un", operator, self.unary())
        return self.primary()

    def primary(self):
        kind = self.kind()
        if kind == "num":
            return ("num", int(self.take("num")[1]))
        if kind == "lparen":
            self.take("lparen")
            node = self.expression()
            self.take("rparen")
            return node
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
            if self.kind() == "dot":
                self.take("dot")
                field = self.take("ident")[1]
                return ("field", name, field)
            return ("var", name)
        raise RefError(f"expresion inesperada {kind!r}")


# ---------------------------------------------------------------------------
# Referencia: interprete
# ---------------------------------------------------------------------------
def u64(value):
    return value & U64_MAX


class ReturnSignal(Exception):
    def __init__(self, value):
        super().__init__("return")
        self.value = value


class RefStruct:
    """Valor de un struct nominal: nombre de tipo y campos u64."""

    __slots__ = ("typename", "fields")

    def __init__(self, typename, fields):
        self.typename = typename
        self.fields = fields


class RefInterpreter:
    def __init__(self, structs, functions):
        self.structs = structs
        self.functions = functions
        # Cada variable se guarda como (mutable, valor).
        self.scopes = [{}]
        self.output = []

    def lookup(self, name):
        return self.lookup_entry(name)[1]

    def lookup_entry(self, name):
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
        args = [u64(self.scalar(argument)) for argument in arguments]
        saved = self.scopes
        self.scopes = [dict(zip(params, [(False, value) for value in args]))]
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

    def lookup_struct(self, name):
        mutable, value = self.lookup_entry(name)
        if not isinstance(value, RefStruct):
            raise RefError(f"{name} no es un struct")
        return mutable, value

    def element(self, name, index_node):
        array = self.lookup_array(name)
        index = u64(self.evaluate(index_node))
        if index >= len(array):
            raise RefError(f"indice fuera de rango en {name}: {index}")
        return array[index]

    def scalar(self, node):
        value = self.evaluate(node)
        if isinstance(value, (list, RefStruct)):
            raise RefError("se esperaba un u64")
        return value

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
        if kind == "field":
            _, value = self.lookup_struct(node[1])
            if node[2] not in value.fields:
                raise RefError(f"campo desconocido {node[2]}")
            return value.fields[node[2]]
        if kind == "call":
            return self.call(node[1], node[2])
        if kind == "un":
            value = self.scalar(node[2])
            if node[1] == "minus":
                return u64(-value)
            return not value
        operator = node[1]
        left = self.scalar(node[2])
        right = self.scalar(node[3])
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

    def evaluate_struct(self, type_name, fields):
        if type_name not in self.structs:
            raise RefError(f"struct no definido: {type_name}")
        declared = self.structs[type_name]
        values = {}
        for field_name, expression in fields:
            if field_name not in declared:
                raise RefError(f"campo extra {field_name} en {type_name}")
            if field_name in values:
                raise RefError(f"campo repetido {field_name} en {type_name}")
            value = self.evaluate(expression)
            if isinstance(value, (list, RefStruct)):
                raise RefError(f"campo {field_name} no es u64")
            values[field_name] = u64(value)
        if len(values) != len(declared):
            raise RefError(f"faltan campos en {type_name}")
        return RefStruct(type_name, values)

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
            value = self.evaluate(statement[3])
            if isinstance(value, (list, RefStruct)):
                raise RefError("solo el literal crea arrays y structs")
            self.scopes[-1][statement[2]] = (statement[1], value)
        elif kind == "let_arr":
            elements = [self.scalar(element) for element in statement[3]]
            self.scopes[-1][statement[2]] = (False, elements)
        elif kind == "let_struct":
            mutable = statement[1]
            value = self.evaluate_struct(statement[3], statement[4])
            self.scopes[-1][statement[2]] = (mutable, value)
        elif kind == "assign":
            value = self.evaluate(statement[2])
            if isinstance(value, (list, RefStruct)):
                raise RefError("no asignable")
            scope = self.find_scope(statement[1])
            mutable, _ = self.scopes[scope][statement[1]]
            self.scopes[scope][statement[1]] = (mutable, u64(value))
        elif kind == "assign_index":
            array = self.lookup_array(statement[1])
            index = u64(self.evaluate(statement[2]))
            if index >= len(array):
                raise RefError(
                    f"indice fuera de rango en {statement[1]}: {index}")
            value = self.evaluate(statement[3])
            if isinstance(value, (list, RefStruct)):
                raise RefError("no asignable")
            array[index] = u64(value)
        elif kind == "assign_field":
            mutable, value = self.lookup_struct(statement[1])
            if not mutable:
                raise RefError(f"{statement[1]} no es mut")
            if statement[2] not in value.fields:
                raise RefError(f"campo desconocido {statement[2]}")
            field_value = self.evaluate(statement[3])
            if isinstance(field_value, (list, RefStruct)):
                raise RefError("campo no asignable")
            value.fields[statement[2]] = u64(field_value)
        elif kind == "print":
            value = self.evaluate(statement[1])
            if isinstance(value, bool):
                self.output.append("1" if value else "0")
            elif isinstance(value, (list, RefStruct)):
                raise RefError("no imprimible")
            else:
                self.output.append(str(value))
        elif kind == "return":
            raise ReturnSignal(u64(self.scalar(statement[1])))
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
    """Salida stdout esperada del lenguaje de TASK-902K."""
    items = RefParser(tokenize(program)).program()
    structs = {}
    functions = {}
    for item in items:
        if item[0] == "struct":
            structs[item[1]] = item[2]
        elif item[0] == "fn":
            functions[item[1]] = (item[2], item[3])
    interpreter = RefInterpreter(structs, functions)
    for item in items:
        if item[0] not in ("struct", "fn"):
            interpreter.execute(item)
    if not interpreter.output:
        return ""
    return "\n".join(interpreter.output) + "\n"


def _fields(count):
    return ", ".join("f%d: u64" % index for index in range(count))


def _field_values(count):
    return ", ".join("f%d: %d" % (index, index + 1) for index in range(count))


def _many_structs(count):
    return "\n".join(
        "struct S%d { x: u64, y: u64 }" % index for index in range(count)
    )


def _many_struct_locals(count):
    lines = ["struct P { x: u64 }"]
    for index in range(count):
        lines.append("let v%d = P { x: %d };" % (index, index))
    lines.append("print v%d.x;" % (count - 1))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Programas validos: codegen -> C -> ejecutable -> stdout
# ---------------------------------------------------------------------------
PROGRAMS = [
    ("literal_and_read", """
struct P { x: u64, y: u64 }
let p = P { x: 3, y: 4 };
print p.x;
print p.y;
print p.x + p.y;
"""),
    ("field_write", """
struct P { x: u64, y: u64 }
let mut p = P { x: 1, y: 2 };
p.x = 10;
p.y = p.x * 3;
print p.x;
print p.y;
"""),
    ("several_fields", """
struct Five { a: u64, b: u64, c: u64, d: u64, e: u64 }
let mut v = Five { e: 5, c: 3, a: 1, d: 4, b: 2 };
print v.a + v.b + v.c + v.d + v.e;
v.a = v.e - v.d;
print v.a;
"""),
    ("struct_local_in_function", """
struct P { x: u64, y: u64 }
fn sum(a, b) {
    let p = P { x: a, y: b };
    return p.x + p.y;
}
print sum(4, 9);
"""),
    ("function_before_struct", """
fn bump(n) { let p = P { x: n }; return p.x + 1; }
struct P { x: u64 }
print bump(6);
"""),
    ("shadowing_in_block", """
struct P { x: u64, y: u64 }
let p = P { x: 1, y: 2 };
if 0 < 1 {
    let p = P { x: 10, y: 20 };
    print p.x;
    print p.y;
}
print p.x;
print p.y;
"""),
    ("shadowing_in_function", """
struct P { x: u64 }
let p = P { x: 7 };
fn get() { let p = P { x: 8 }; return p.x; }
print p.x;
print get();
"""),
    ("while_updates", """
struct Acc { n: u64, sum: u64 }
let mut a = Acc { n: 0, sum: 0 };
while a.n < 6 {
    a.sum = a.sum + a.n * a.n;
    a.n = a.n + 1;
}
print a.n;
print a.sum;
"""),
    ("multiple_struct_types", """
struct Point { x: u64, y: u64 }
struct Size { w: u64, h: u64 }
let mut p = Point { x: 2, y: 3 };
let s = Size { w: p.x * 4, h: p.y * 5 };
p.y = s.h - s.w;
print p.x;
print p.y;
print s.w;
print s.h;
"""),
    ("out_of_order_trailing_commas", """
struct R { a: u64, b: u64, c: u64, }
let r = R { c: 3, a: 1, b: 2, };
print r.a;
print r.b;
print r.c;
"""),
    ("field_init_calls_and_arrays", """
struct Box { lo: u64, hi: u64 }
fn twice(n) { return n * 2; }
let src = [4, 7, 9];
let b = Box { lo: twice(src[0]), hi: twice(src[2]) };
print b.lo;
print b.hi;
"""),
    ("eight_fields", """
struct Eight { a: u64, b: u64, c: u64, d: u64, e: u64, f: u64, g: u64, h: u64 }
let v = Eight { h: 8, g: 7, f: 6, e: 5, d: 4, c: 3, b: 2, a: 1 };
print v.a + v.h;
print v.b * v.c;
print v.d + v.e + v.f + v.g;
"""),
    ("unused_struct_and_local", """
struct Unused { a: u64, b: u64 }
fn nothing(n) { let u = Unused { a: n, b: n + 1 }; return 0; }
print nothing(5);
"""),
    ("nested_control_blocks", """
struct C { v: u64 }
let mut c = C { v: 0 };
let mut i = 0;
while i < 3 {
    if i == 1 {
        let mut d = C { v: 50 };
        d.v = d.v + i;
        c.v = d.v;
    } else {
        c.v = c.v + i;
    }
    i = i + 1;
}
print c.v;
"""),
    ("recursion_with_struct", """
struct Pair { a: u64, b: u64 }
fn fib(n) {
    if n < 2 { return n; }
    let p = Pair { a: fib(n - 1), b: fib(n - 2) };
    return p.a + p.b;
}
print fib(10);
"""),
    ("c_keyword_names", """
struct int { static: u64, printf: u64, uint64_t: u64 }
let main = int { printf: 2, uint64_t: 3, static: 1, };
print main.static;
print main.printf;
print main.uint64_t;
"""),
    ("field_as_index_and_bound", """
struct Idx { pos: u64, val: u64 }
let a = [10, 20, 30];
let mut i = Idx { pos: 1, val: 99 };
print a[i.pos];
a[i.pos] = i.val;
i.val = a[2] + a[1];
print a[1];
print i.val;
"""),
    ("conditional_fields", """
struct Limits { lo: u64, hi: u64 }
let l = Limits { lo: 3, hi: 9 };
if l.lo < l.hi { print 1; } else { print 0; }
if l.hi == 9 { print l.hi - l.lo; }
"""),
]


# ---------------------------------------------------------------------------
# Programas invalidos: codigos exactos del contrato
# ---------------------------------------------------------------------------
ERROR_PROGRAMS = [
    ("literal_missing_field",
     "struct P { x: u64, y: u64 } let p = P { x: 1 };", CG_TYPES),
    ("literal_extra_field",
     "struct P { x: u64 } let p = P { x: 1, z: 2 };", CG_TYPES),
    ("literal_duplicate_field",
     "struct P { x: u64 } let p = P { x: 1, x: 2 };", CG_TYPES),
    ("literal_field_not_u64",
     "struct P { x: u64 } let p = P { x: 1 < 2 };", CG_TYPES),
    ("copy_struct",
     "struct P { x: u64 } let p = P { x: 1 }; let q = p;", CG_TYPES),
    ("assign_whole_struct",
     "struct P { x: u64 } let mut p = P { x: 1 }; "
     "let q = P { x: 2 }; p = q;", CG_TYPES),
    ("struct_argument",
     "struct P { x: u64 } fn f(v) { return v; } "
     "let p = P { x: 1 }; print f(p);", CG_TYPES),
    ("struct_return",
     "struct P { x: u64 } fn f() { let p = P { x: 1 }; return p; }",
     CG_TYPES),
    ("struct_comparison",
     "struct P { x: u64 } let p = P { x: 1 }; let q = P { x: 1 }; "
     "print p == q;", CG_TYPES),
    ("struct_condition",
     "struct P { x: u64 } let p = P { x: 1 }; if p { print 1; }", CG_TYPES),
    ("struct_print",
     "struct P { x: u64 } let p = P { x: 1 }; print p;", CG_TYPES),
    ("array_of_structs",
     "struct P { x: u64 } let p = P { x: 1 }; let a = [p];", CG_TYPES),
    ("unknown_struct_literal", "let p = Q { x: 1 };", CG_TYPES),
    ("unknown_field_read",
     "struct P { x: u64 } let p = P { x: 1 }; print p.y;", CG_TYPES),
    ("field_on_u64", "let x = 1; print x.y;", CG_TYPES),
    ("nested_field", "struct P { x: u64 } let p = P { x: 1 }; print p.x.y;",
     CG_TYPES),
    ("immutable_field_write",
     "struct P { x: u64 } let p = P { x: 1 }; p.x = 2;", CG_TYPES),
    ("field_write_bool",
     "struct P { x: u64 } let mut p = P { x: 1 }; p.x = 1 < 2;", CG_TYPES),
    ("empty_struct", "struct S {}", CG_SYNTAX),
    ("field_type_not_u64", "struct P { x: bool }", CG_SYNTAX),
    ("duplicate_struct", "struct P { x: u64 } struct P { y: u64 }",
     CG_SYNTAX),
    ("duplicate_decl_field", "struct P { x: u64, x: u64 }", CG_SYNTAX),
    ("struct_as_field",
     "struct Q { x: u64 } struct P { q: Q }", CG_SYNTAX),
    ("struct_in_function_body",
     "fn f() { struct P { x: u64 } return 0; } print f();", CG_SYNTAX),
    ("too_many_fields", "struct P { %s }" % _fields(9), CG_LIMIT),
    ("too_many_structs", _many_structs(17), CG_LIMIT),
]


# ---------------------------------------------------------------------------
# Harness C auxiliar: llama a zen_codegen_structs y muestra el valor bruto.
# Es solo un fichero temporal del test; no forma parte de la entrega.
# ---------------------------------------------------------------------------
RAW_HARNESS = r"""
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

extern uint64_t zen_codegen_structs(uint64_t source, uint64_t length,
                                    uint64_t out, uint64_t cap);

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "usage: raw_codegen_structs FILE [CAP]\n");
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
    uint64_t written = zen_codegen_structs((uint64_t)(uintptr_t)source,
                                           (uint64_t)size,
                                           (uint64_t)(uintptr_t)out, cap);
    printf("%llu\n", (unsigned long long)written);
    free(out);
    free(source);
    return 0;
}
"""


class SelfHostCodegenStructsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ZEN.is_file():
            raise RuntimeError(
                f"falta el compilador {ZEN}; construyelo con: "
                "CARGO_HOME=\"$PWD/.cargo\" cargo build --release --offline "
                "--manifest-path zen/compiler/Cargo.toml"
            )
        cls._tmpdir = tempfile.TemporaryDirectory(prefix="zen-selfhost-cgs-")
        cls.tmp = pathlib.Path(cls._tmpdir.name)
        cls.obj = cls.tmp / "codegen_structs.o"
        cls.exe = cls.tmp / "codegen_structs_driver"
        cls.raw = cls.tmp / "raw_codegen_structs"
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
            "struct P { x: u64, y: u64 } "
            "let p = P { x: 3, y: 4 }; print p.x + p.y;": "7\n",
            "struct P { x: u64 } let mut p = P { x: 1 }; p.x = 9; "
            "print p.x;": "9\n",
            "struct P { x: u64, y: u64 } let p = P { y: 2, x: 1 }; "
            "print p.x; print p.y;": "1\n2\n",
            "struct P { x: u64 } fn f(n) { let p = P { x: n }; "
            "return p.x * 2; } print f(5);": "10\n",
            "struct P { x: u64 } let p = P { x: 1 }; "
            "if 0 < 1 { let p = P { x: 2 }; print p.x; } print p.x;":
            "2\n1\n",
            "let a = [1, 2]; struct P { i: u64 } let mut p = P { i: 1 }; "
            "print a[p.i];": "2\n",
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

    def test_empty_program_and_struct_only(self):
        c_source = self.emit("")
        self.assertTrue(c_source.startswith("#include <stdio.h>\n"))
        self.assertIn("#include <stdint.h>\n", c_source)
        self.assertIn("#include <stddef.h>\n", c_source)
        self.assertIn("int main(void) {\n", c_source)
        self.assertTrue(c_source.endswith("    return 0;\n}\n"))
        self.assertEqual(self.run_generated(""), "")

        only = "struct S { x: u64, y: u64 }"
        c_only = self.emit(only)
        self.assertIn(
            "typedef struct { uint64_t f0; uint64_t f1; } zn_0;", c_only)
        self.assertNotIn("static uint64_t ", c_only)
        self.assertEqual(self.run_generated(only), "")

    def test_emission_has_typedef_and_field_access(self):
        program = """
struct P { x: u64, y: u64 }
let mut p = P { x: 10, y: 20 };
print p.x;
p.y = p.x + 1;
print p.y;
"""
        c_source = self.emit(program)
        self.assertIn(
            "typedef struct { uint64_t f0; uint64_t f1; } zn_0;", c_source)
        self.assertLess(c_source.index("typedef struct"),
                        c_source.index("int main(void)"))
        self.assertIn("zn_0 v_0;", c_source)
        self.assertIn("(void)v_0;", c_source)
        self.assertIn("v_0.f0 = 10ULL;", c_source)
        self.assertIn("v_0.f1 = 20ULL;", c_source)
        self.assertIn(
            'printf("%llu\\n", (unsigned long long)(v_0.f0));', c_source)
        self.assertIn("v_0.f1 = (v_0.f0 + 1ULL);", c_source)
        self.assertEqual(self.run_generated(program), "10\n11\n")

        function_program = """
struct P { x: u64 }
fn f(x) { let p = P { x: x + 1 }; return p.x; }
print f(2);
"""
        c_source = self.emit(function_program)
        self.assertIn("static uint64_t fn_0(uint64_t p_0) {", c_source)
        self.assertIn("zn_0 v_1;", c_source)
        self.assertIn("v_1.f0 = (p_0 + 1ULL);", c_source)
        self.assertEqual(self.run_generated(function_program), "3\n")

    def test_field_operands_keep_parentheses(self):
        program = """
struct P { x: u64, y: u64 }
let p = P { x: 2, y: 3 };
print p.x + p.y * 4;
print (p.x + p.y) * 5;
"""
        c_source = self.emit(program)
        self.assertIn("(v_0.f0 + (v_0.f1 * 4ULL))", c_source)
        self.assertIn("(((v_0.f0 + v_0.f1)) * 5ULL)", c_source)
        self.assertEqual(self.run_generated(program), "14\n25\n")

    def test_struct_and_field_names_are_sanitized(self):
        program = """
struct int { static: u64, printf: u64, uint64_t: u64 }
let main = int { printf: 2, uint64_t: 3, static: 1, };
print main.static;
print main.printf;
print main.uint64_t;
"""
        c_source = self.emit(program)
        self.assertIn(
            "typedef struct { uint64_t f0; uint64_t f1; uint64_t f2; } zn_0;",
            c_source)
        for forbidden in ("int main =", "int main;", " static;",
                          " printf;", " uint64_t;"):
            self.assertNotIn(forbidden, c_source)
        self.assertEqual(self.run_generated(program), "1\n2\n3\n")

    def test_unused_structs_do_not_break_werror(self):
        program = """
struct Unused { a: u64, b: u64 }
fn unused(x) {
    let p = Unused { a: x, b: x + 1 };
    let q = Unused { b: 2, a: 1 };
    return 0;
}
print unused(1);
"""
        c_source = self.emit(program)
        self.assertIn("(void)p_0;", c_source)
        self.assertIn("(void)v_1;", c_source)
        self.assertIn("(void)v_2;", c_source)
        self.assertEqual(self.run_generated(program), "0\n")

    def test_emitted_c_has_no_wrapper_trace_or_copied_text(self):
        program = "struct P { x: u64 } let mut p = P { x: 31 }; p.x = 47;"
        c_source = self.emit(program)
        lowered = c_source.lower()
        for forbidden in (
            "zen_codegen",
            "codegen_structs",
            "codegen_structs.zen",
            "codegen_structs_driver",
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
            "typedef struct { uint64_t f0; } zn_0;", generator_source)
        self.assertNotIn(
            "#include <stdio.h>\n#include <stdint.h>\n#include <stddef.h>\n\n"
            "int main(void) {",
            generator_source,
        )

        # El helper de comparaciones solo aparece si hay comparaciones.
        self.assertNotIn(
            "zn_cmp",
            self.emit("struct P { x: u64 } let p = P { x: 1 }; print p.x;"))
        self.assertIn(
            "static inline int zn_cmp",
            self.emit("struct P { x: u64 } let p = P { x: 1 }; "
                      "print p.x < 1;"))

    def test_deterministic(self):
        program = """
struct P { x: u64, y: u64 }
fn total(a, b) { let p = P { x: a, y: b }; return p.x + p.y; }
let mut q = P { x: 1, y: 2 };
q.x = total(q.y, 4);
print q.x;
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

    def test_struct_limits_at_the_boundary(self):
        # 1 y 8 campos son validos; 9 excede el limite.
        self.assertEqual(
            self.run_generated(
                "struct P { x: u64 } let p = P { x: 7 }; print p.x;"),
            "7\n")
        self.assertEqual(
            self.run_generated(
                "struct P { %s } let p = P { %s }; print p.f7;\n"
                % (_fields(8), _field_values(8))),
            "8\n")
        self.assertEqual(self.raw_codegen("struct P { %s }" % _fields(9)),
                         CG_LIMIT)

        # 16 structs son validos; 17 exceden el limite.
        many = _many_structs(16) + (
            "\nlet v = S15 { x: 42, y: 0 };\nprint v.x;\n")
        self.assertEqual(self.run_generated(many), "42\n")
        self.assertEqual(self.raw_codegen(_many_structs(17)), CG_LIMIT)

        # 32 variables activas son validas; 33 exceden el limite.
        self.assertEqual(self.run_generated(_many_struct_locals(32)), "31\n")
        self.assertEqual(self.raw_codegen(_many_struct_locals(33)), CG_LIMIT)

    def test_output_capacity_boundary(self):
        programs = [
            "struct P { x: u64, y: u64 } "
            "let mut p = P { x: 10, y: 20 }; print p.x; p.y = 7; print p.y;",
            "struct P { x: u64 } fn f(x) { let p = P { x: x + 1 }; "
            "return p.x; } print f(3);",
            "",
            "struct S { x: u64 }",
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
            "struct S { x: u64 }",
            "struct P { x: u64 } let p = P { x: 1 }; print p.x;",
            "struct P { x: u64 } fn f(x) { let p = P { x: x }; "
            "return p.x + 1; } print f(2);",
        ):
            with self.subTest(program=program):
                c_source = self.emit(program)
                self.assertEqual(self.raw_codegen(program),
                                 len(c_source.encode("ascii")))

    # -- driver -------------------------------------------------------------
    def test_driver_writes_output_file(self):
        program = ("struct P { x: u64, y: u64 } "
                   "let mut p = P { x: 1, y: 2 }; p.x = 4; print p.x;")
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
            "pub fn zen_codegen_structs(source:u64,length:u64,out:u64,cap:u64)->u64",
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
            "st_nfields",
            "st_fstart",
            "typedef struct { ",
            "v_",
            ".f",
            "sl_fields",
            "pstate=9u64",
            "pstate=10u64",
        ):
            self.assertIn(token, source,
                          f"falta {token!r} en codegen_structs.zen")
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
