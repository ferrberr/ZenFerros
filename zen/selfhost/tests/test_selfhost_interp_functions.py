"""TASK-902F: verificacion del interprete selfhost con funciones escrito en Zen.

El test compila `zen/selfhost/interp_functions.zen` como objeto freestanding con
el compilador `zen`, lo enlaza con `zen/selfhost/interp_functions_driver.c` y
compara, programa a programa, la salida del interprete Zen con una
implementacion de referencia independiente escrita aqui (scanner + parser
recursivo + evaluador con marcos de invocacion, sin `eval` y sin compartir
codigo con el interprete Zen).

Cubre:
* >=30 programas validos: parametros, `return`, llamadas anidadas, factorial
  recursivo, fibonacci acotado, recursion mutua, ambito local, llamadas antes
  de la definicion, efectos laterales y envolvente u64;
* errores de ejecucion (funcion desconocida, variable desconocida, division por
  cero) con contador de sentencias, hash y bytes ya producidos;
* errores de sintaxis y de aridad (estado 6) con out[1..3] a cero;
* limites fijos: 512 nodos, 2048 tokens, profundidad 32 de parentesis/unarios y
  de bloques, 16 variables por marco, 16 marcos de llamada, 256 bytes
  impresos, 1.000.000 de pasos;
* que el objeto Zen no importa simbolos de libc (`nm -u` vacio), que el estado
  vive en arrays fijos locales y que la ejecucion no reparsea la fuente.
"""

import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
ZEN = ROOT / "zen/compiler/target/release/zen"
SOURCE = ROOT / "zen/selfhost/interp_functions.zen"
DRIVER = ROOT / "zen/selfhost/interp_functions_driver.c"

MASK = (1 << 64) - 1
FNV_OFFSET = 2166136261
FNV_PRIME = 16777619
MAX_TOKENS = 2048
MAX_NODES = 512
MAX_DEPTH = 32
MAX_VARS = 16
MAX_FRAMES = 16
MAX_FUNCS = 64
MAX_PARAMS = 16
MAX_OUTPUT = 256
STEP_LIMIT = 1000000
OUTPUT_LINE = re.compile(
    r"status=([0-9]+) statements=([0-9]+) hash=([0-9]+) bytes=([0-9]+)"
)

sys.setrecursionlimit(20000)


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


class ReturnSignal(Exception):
    """Salida anticipada de una funcion de referencia."""

    def __init__(self, value):
        super().__init__(value)
        self.value = value


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
    ",": "comma",
}
WHITESPACE = " \t\r\n\v\f"


def _is_digit(char):
    return "0" <= char <= "9"


def _is_alpha(char):
    return ("a" <= char <= "z") or ("A" <= char <= "Z")


def _is_ident(char):
    return _is_alpha(char) or _is_digit(char) or char == "_"


class RefLexer:
    """Scanner independiente con el tope de 2048 tokens del contrato."""

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
        if len(tokens) >= MAX_TOKENS:
            raise RefError(4)
        tokens.append((kind, value))


# ---------------------------------------------------------------------------
# Referencia: parser recursivo (independiente del shunting-yard de Zen)
# ---------------------------------------------------------------------------
COMPARISONS = frozenset(("lt", "le", "gt", "ge", "eq", "ne"))
ADDITIVE = frozenset(("plus", "minus"))
MULTIPLICATIVE = frozenset(("star", "slash", "percent"))


class Function:
    def __init__(self, name, params, body):
        self.name = name
        self.params = params
        self.body = body


class RefParser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0
        self.nodes = 0
        self.functions = {}
        self.order = []

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

    # -- programa / funciones ------------------------------------------------
    def parse_program(self):
        statements = []
        while self.pos < len(self.tokens):
            if self.peek()[0] == "fn":
                self.parse_function()
            else:
                if self.peek()[0] == "rbrace":
                    raise RefError(1)
                statements.append(self.statement(0, False))
        self.validate_calls(statements, [f.body for f in self.order])
        return statements

    def parse_function(self):
        self.expect("fn")
        name = self.expect("ident")[1]
        if name in self.functions:
            raise RefError(1)
        if len(self.functions) >= MAX_FUNCS:
            raise RefError(4)
        self.add_node()
        self.expect("lparen")
        params = []
        if self.peek()[0] != "rparen":
            while True:
                params.append(self.expect("ident")[1])
                if len(params) > MAX_PARAMS:
                    raise RefError(4)
                if self.peek()[0] == "comma":
                    self.take()
                    continue
                break
        self.expect("rparen")
        self.expect("lbrace")
        body = self.parse_body(0, True)
        self.expect("rbrace")
        if len(set(params)) != len(params):
            raise RefError(1)
        function = Function(name, params, body)
        self.functions[name] = function
        self.order.append(function)

    def validate_calls(self, statements, bodies):
        for body in [statements] + bodies:
            for statement in body:
                self._validate_statement(statement)

    def _validate_statement(self, statement):
        kind = statement[0]
        if kind in ("let", "assign"):
            self._validate_expr(statement[2])
        elif kind == "print":
            self._validate_expr(statement[1])
        elif kind == "return":
            self._validate_expr(statement[1])
        elif kind == "if":
            self._validate_expr(statement[1])
            self.validate_calls(statement[2], [])
            self.validate_calls(statement[3], [])
        elif kind == "while":
            self._validate_expr(statement[1])
            self.validate_calls(statement[2], [])

    def _validate_expr(self, node):
        kind = node[0]
        if kind in ("num", "var"):
            return
        if kind == "un":
            self._validate_expr(node[1])
            return
        if kind == "call":
            for argument in node[2]:
                self._validate_expr(argument)
            function = self.functions.get(node[1])
            if function is not None and len(function.params) != len(node[2]):
                raise RefError(6)
            return
        self._validate_expr(node[2])
        self._validate_expr(node[3])

    def parse_body(self, depth, in_function):
        if depth > MAX_DEPTH:
            raise RefError(4)
        statements = []
        while True:
            kind = self.peek()[0]
            if kind is None or kind == "rbrace":
                return statements
            statements.append(self.statement(depth, in_function))

    def statement(self, depth, in_function):
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
            body = self.parse_body(depth + 1, in_function)
            self.expect("rbrace")
            other = []
            if self.peek()[0] == "else":
                self.take()
                self.expect("lbrace")
                other = self.parse_body(depth + 1, in_function)
                self.expect("rbrace")
            return ("if", condition, body, other)
        if kind == "while":
            self.take()
            condition = self.expression(depth)
            self.expect("lbrace")
            self.add_node()
            body = self.parse_body(depth + 1, in_function)
            self.expect("rbrace")
            return ("while", condition, body)
        if kind == "return":
            if not in_function:
                raise RefError(1)
            self.take()
            expression = self.expression(depth)
            self.expect("semi")
            self.add_node()
            return ("return", expression)
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
            if self.peek()[0] == "lparen":
                self.take()
                arguments = []
                if self.peek()[0] != "rparen":
                    while True:
                        arguments.append(self.expression(depth + 1))
                        if self.peek()[0] == "comma":
                            if len(arguments) >= MAX_PARAMS:
                                raise RefError(4)
                            self.take()
                            if self.peek()[0] == "rparen":
                                raise RefError(1)
                            continue
                        break
                self.expect("rparen")
                self.add_node()
                return ("call", name, arguments)
            self.add_node()
            return ("var", name)
        raise RefError(1)


# ---------------------------------------------------------------------------
# Referencia: evaluador con marcos de invocacion
# ---------------------------------------------------------------------------
class Frame:
    def __init__(self, depth):
        self.depth = depth
        self.variables = {}


class RefRuntime:
    def __init__(self, functions):
        self.functions = functions
        self.executed = 0
        self.steps = 0
        self.hash = FNV_OFFSET
        self.outbytes = 0

    def check_step(self):
        self.steps += 1
        if self.steps > STEP_LIMIT:
            raise RefError(4)

    def run(self, statements):
        status = 0
        try:
            self.exec_block(statements, Frame(0))
        except RefError as error:
            status = error.status
        except ReturnSignal:  # pragma: no cover - el parser lo prohibe
            status = 1
        return (status, self.executed, self.hash, self.outbytes)

    def exec_block(self, statements, frame):
        for statement in statements:
            self.exec_statement(statement, frame)

    def exec_statement(self, statement, frame):
        self.executed += 1
        self.check_step()
        kind = statement[0]
        if kind == "let":
            name = statement[1]
            value = self.value_of(statement[2], frame)
            if name in frame.variables:
                frame.variables[name] = value
            elif len(frame.variables) >= MAX_VARS:
                raise RefError(4)
            else:
                frame.variables[name] = value
        elif kind == "assign":
            name = statement[1]
            value = self.value_of(statement[2], frame)
            if name not in frame.variables:
                raise RefError(3)
            frame.variables[name] = value
        elif kind == "print":
            value = self.value_of(statement[1], frame)
            text = str(value).encode("ascii")
            if self.outbytes + len(text) + 1 > MAX_OUTPUT:
                raise RefError(4)
            for byte in text:
                self.hash = ((self.hash ^ byte) * FNV_PRIME) & 0xFFFFFFFF
            self.hash = ((self.hash ^ 10) * FNV_PRIME) & 0xFFFFFFFF
            self.outbytes += len(text) + 1
        elif kind == "if":
            if self.value_of(statement[1], frame) != 0:
                self.exec_block(statement[2], frame)
            else:
                self.exec_block(statement[3], frame)
        elif kind == "while":
            while True:
                if self.value_of(statement[1], frame) != 0:
                    self.exec_block(statement[2], frame)
                    self.executed += 1
                    self.check_step()
                else:
                    break
        elif kind == "return":
            value = self.value_of(statement[1], frame)
            raise ReturnSignal(value)
        else:  # pragma: no cover
            raise RefError(1)

    def value_of(self, node, frame):
        kind = node[0]
        if kind == "num":
            return node[1]
        if kind == "var":
            if node[1] not in frame.variables:
                raise RefError(3)
            return frame.variables[node[1]]
        if kind == "un":
            return (-self.value_of(node[1], frame)) & MASK
        if kind == "call":
            name = node[1]
            arguments = [self.value_of(argument, frame) for argument in node[2]]
            return self.call_function(name, arguments, frame)
        operator = node[1]
        left = self.value_of(node[2], frame)
        right = self.value_of(node[3], frame)
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

    def call_function(self, name, arguments, caller):
        self.check_step()
        if caller.depth >= MAX_FRAMES:
            raise RefError(4)
        function = self.functions.get(name)
        if function is None:
            raise RefError(5)
        if len(arguments) != len(function.params):
            raise RefError(6)
        frame = Frame(caller.depth + 1)
        for parameter, value in zip(function.params, arguments):
            frame.variables[parameter] = value
        try:
            self.exec_block(function.body, frame)
        except ReturnSignal as signal:
            return signal.value
        return 0


def reference(program):
    """Ejecuta `program` con la referencia; misma semantica que zen_interp_fns."""
    try:
        tokens = RefLexer(program).tokenize()
        parser = RefParser(tokens)
        statements = parser.parse_program()
    except RefError as error:
        return (error.status, 0, 0, 0)
    return RefRuntime(parser.functions).run(statements)


# ---------------------------------------------------------------------------
# Programas de prueba
# ---------------------------------------------------------------------------
PROGRAMS = [
    ("empty", ""),
    ("whitespace_only", " \t\r\n\v\f "),
    ("only_function", "fn f(a){ return a+1; }"),
    ("print_literal", "print 42;"),
    ("add", "fn add(a,b){ return a+b; } print add(2,3);"),
    ("add_nested",
     "fn add(a,b){return a+b;} print add(add(1,2),add(3,4));"),
    ("factorial5",
     "fn fac(n){ if n<=1 { return 1; } return n*fac(n-1); } print fac(5);"),
    ("factorial1",
     "fn fac(n){ if n<=1 { return 1; } return n*fac(n-1); } print fac(1);"),
    ("factorial0",
     "fn fac(n){ if n<=1 { return 1; } return n*fac(n-1); } print fac(0);"),
    ("factorial21_wrap",
     "fn fac(n){ if n<=1 { return 1; } return n*fac(n-1); } print fac(21);"),
    ("fib10",
     "fn fib(n){ if n<2 { return n; } return fib(n-1)+fib(n-2); } "
     "print fib(10);"),
    ("fib1",
     "fn fib(n){ if n<2 { return n; } return fib(n-1)+fib(n-2); } "
     "print fib(1);"),
    ("params_mutable",
     "fn f(a,b,c){ a=a+1; b=b*2; return a+b+c; } print f(1,2,3);"),
    ("local_scope",
     "fn f(){ let x=1; return x; } let x=9; print f(); print x;"),
    ("implicit_return", "fn z(){} print z();"),
    ("implicit_return_expr", "fn z(a){ a+1; } print z(4);"),
    ("early_return_if",
     "fn f(n){ if n { return 1; } return 2; } print f(0); print f(1);"),
    ("early_return_while",
     "fn f(){ let i=0; while 1 { i=i+1; if i==3 { return i*10; } } "
     "return 0; } print f();"),
    ("mutual_recursion",
     "fn even(n){ if n==0 { return 1; } return odd(n-1); } "
     "fn odd(n){ if n==0 { return 0; } return even(n-1); } "
     "print even(10); print odd(10);"),
    ("call_in_condition",
     "fn t(){ return 1; } if t() { print 7; } print 8;"),
    ("call_in_while",
     "fn lt(a,b){ return a<b; } let i=0; "
     "while lt(i,3) { print i; i=i+1; }"),
    ("call_in_let",
     "fn double(a){ return a*2; } let x=double(21); print x;"),
    ("call_in_print",
     "fn double(a){ return a*2; } print double(double(3));"),
    ("forward_declaration", "print f(3); fn f(a){ return a*2; }"),
    ("interspersed",
     "print 1; fn f(){return 2;} print f(); print 3;"),
    ("empty_args",
     "fn f(){return 7;} fn g(a,b){return a+b;} print g(f(),f());"),
    ("zero_arg_chain",
     "fn a(){ return 1; } fn b(){ return a()+a(); } print b();"),
    ("function_zero",
     "fn zero(){ return 0; } print zero();"),
    ("wrap_param",
     "fn inc(a){ return a+1; } "
     "print inc(18446744073709551615);"),
    ("wrap_inside",
     "fn neg(a){ return 0-a; } print neg(1);"),
    ("unary_minus_return",
     "fn neg(a){ return -a; } print neg(5); print -neg(5);"),
    ("big_literal",
     "fn id(a){ return a; } print id(99999999999999999999);"),
    ("precedence_call",
     "fn f(a){ return a+1; } print 2*f(3)+1; print (f(2)+1)*3;"),
    ("return_comparison",
     "fn lt(a,b){ return a<b; } print lt(1,2); print lt(2,1);"),
    ("call_side_effects",
     "fn f(){ print 1; return 2; } print f(); print 3;"),
    ("nested_if_return",
     "fn f(n){ if n { if n>1 { return 2; } else { return 3; } } "
     "else { return 4; } } print f(0); print f(1); print f(2);"),
    ("function_sum_while",
     "fn f(n){ let i=0; let s=0; while i<n { s=s+i; i=i+1; } "
     "return s; } print f(5);"),
    ("while_zero_function",
     "fn f(){ let i=9; while i<3 { i=i+1; } return i; } print f();"),
    ("function_empty_if", "fn f(){ if 1 { } else { } return 5; } print f();"),
    ("function_if_false",
     "fn f(){ if 0 { print 1; } else { print 2; } return 3; } print f();"),
    ("sixteen_params",
     "fn f(a,b,c,d,e,g,h,i,j,k,l,m,n,o,p,q){ return q; } "
     "print f(1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16);"),
    ("sixteen_vars",
     "fn f(){ let a1=1; let a2=1; let a3=1; let a4=1; let a5=1; "
     "let a6=1; let a7=1; let a8=1; let a9=1; let a10=1; let a11=1; "
     "let a12=1; let a13=1; let a14=1; let a15=1; let a16=1; "
     "return a16; } print f();"),
    ("gcd",
     "fn gcd(a,b){ while b!=0 { let t=b; b=a%b; a=t; } return a; } "
     "print gcd(48,18);"),
    ("power",
     "fn pow(a,n){ if n==0 { return 1; } return a*pow(a,n-1); } "
     "print pow(3,4);"),
    ("sum_digits",
     "fn sd(n){ if n<10 { return n; } return n%10+sd(n/10); } "
     "print sd(98765);"),
    ("ackermann_small",
     "fn ack(m,n){ if m==0 { return n+1; } "
     "if n==0 { return ack(m-1,1); } return ack(m-1,ack(m,n-1)); } "
     "print ack(2,3);"),
    ("call_argument_order",
     "fn sub(a,b){ return a-b; } print sub(10,3);"),
    ("underscore_names",
     "fn _f1(a_2){ return a_2+1; } let _x=4; print _f1(_x);"),
    ("division", "fn d(a,b){ return a/b; } print d(100,7); print d(7,2);"),
    ("modulo", "fn m(a,b){ return a%b; } print m(100,7);"),
    ("nested_calls_deep",
     "fn f(a){ return a+1; } print f(f(f(f(f(0)))));"),
    ("function_uses_let_chain",
     "fn f(a){ let b=a*2; let c=b+1; return c; } print f(5);"),
    ("two_functions_order",
     "fn first(){ return 1; } fn second(){ return first()+1; } "
     "print second();"),
    ("whitespace", "fn  f ( a , b ) { return  a + b ; } print f ( 1 , 2 ) ;"),
    ("u64_compare", "fn ge(a,b){ return a>=b; } "
                    "print ge(18446744073709551615,1); print ge(1,2);"),
    ("return_nested_call",
     "fn inc(a){ return a+1; } fn twice(a){ return inc(inc(a)); } "
     "print twice(5);"),
    ("unary_call",
     "fn one(){ return 1; } print -one(); print -(one()+2);"),
    ("nested_empty_calls",
     "fn z(){ return 2; } fn add(a,b){ return a+b; } "
     "print add(z(),z()*3);"),
    ("call_depth_resets_in_loop",
     "fn f(){ return 1; } let i=0; while i<20 { print f(); i=i+1; }"),
    ("recursive_with_loop",
     "fn f(n){ let i=0; while i<n { i=i+1; } if n==0 { return 1; } "
     "return f(n-1)+i; } print f(3);"),
    ("return_in_nested_blocks",
     "fn f(n){ if n { while 1 { if n>5 { return 7; } n=n+1; } } "
     "return 3; } print f(0); print f(9);"),
    ("call_in_comparison_chain",
     "fn f(a){ return a; } print f(1)<f(2); print f(3)==f(3);"),
    ("call_in_else",
     "fn f(){ return 9; } if 0 { print 1; } else { print f(); }"),
]

SYNTAX_PROGRAMS = [
    ("top_level_return", "return 1;"),
    ("return_missing_semi", "fn f(){ return 1 }"),
    ("return_without_expr", "fn f(){ return; }"),
    ("fn_without_name", "fn (){ return 1; }"),
    ("fn_without_lparen", "fn f){ return 1; }"),
    ("fn_without_rparen", "fn f(a { return a; }"),
    ("fn_without_lbrace", "fn f() return 1;"),
    ("fn_unclosed", "fn f(){ return 1;"),
    ("nested_fn_top", "if 1 { fn f(){ return 1; } }"),
    ("nested_fn_body", "fn f(){ fn g(){ return 1; } return 2; }"),
    ("duplicate_fn", "fn f(){ return 1; } fn f(){ return 2; } print f();"),
    ("duplicate_params", "fn f(a,a){ return a; } f(1);"),
    ("extra_brace", "fn f(){ return 1; } }"),
    ("call_trailing_comma", "fn f(a){ return a; } print f(1,);"),
    ("call_leading_comma", "fn f(a){ return a; } print f(,1);"),
    ("call_double_comma", "fn f(a,b){ return a; } print f(1,,2);"),
    ("comma_outside_call", "print 1,2;"),
    ("call_two_operands", "fn f(a){ return a; } print f(1 2);"),
    ("call_unclosed", "fn f(a){ return a; } print f(1;"),
    ("call_statement", "fn f(a){ return a; } f(1);"),
    ("call_then_paren", "fn f(a){ return a; } print f(1)(2);"),
    ("empty_group", "print ();"),
    ("let_missing_semi", "fn f(){ let a=1 return a; }"),
    ("assign_missing_semi", "fn f(){ let a=1; a=2 return a; }"),
    ("if_without_brace", "fn f(){ if 1 return 1; }"),
    ("while_without_brace", "fn f(){ while 1 return 0; }"),
    ("unknown_char", "fn f(){ return @; }"),
    ("bang", "fn f(){ return 1!2; }"),
    ("fn_keyword_name", "fn print(){ return 1; }"),
    ("param_missing_comma", "fn f(a b){ return a; }"),
    ("stray_else", "fn f(){ else { return 1; } }"),
    ("missing_call_rparen", "fn f(a){ return a; } print f(1;"),
    ("empty_print", "print ;"),
    ("assign_without_name", "= 1;"),
]

ARITY_PROGRAMS = [
    ("too_many", "fn f(a){ return a; } print f(1,2);"),
    ("too_few_zero", "fn f(a){ return a; } print f();"),
    ("too_many_zero", "fn f(){ return 1; } print f(1);"),
    ("two_params_three_args",
     "fn f(a,b){ return a+b; } print f(1,2,3);"),
    ("forward_mismatch", "print f(1,2); fn f(a){ return a; }"),
    ("inside_uncalled_function",
     "fn g(a){ return h(1,2); } fn h(a){ return a; } print g(1);"),
    ("nested_argument_mismatch",
     "fn f(a){ return a; } fn g(a,b){ return a+b; } print g(f(1,2),3);"),
]

RUNTIME_PROGRAMS = [
    ("unknown_function",
     "print 7; print nope(1);"),
    ("unknown_function_in_function",
     "fn f(){ return nope(1); } print 7; print f();"),
    ("unknown_function_uncalled",
     "fn f(){ return nope(1); } print 8;"),
    ("unknown_variable_in_function",
     "print 3; fn f(){ return nope; } print f();"),
    ("top_level_invisible",
     "let x=5; fn f(){ return x; } print f();"),
    ("local_invisible_top",
     "fn f(){ let y=2; return y; } print f(); print y;"),
    ("div0_in_function",
     "print 5; fn f(a){ return 10/a; } print f(0);"),
    ("mod0_in_function",
     "fn f(a){ return 10%a; } print f(0);"),
    ("div0_in_argument",
     "fn f(a){ return a; } print f(1/0);"),
    ("unknown_in_argument",
     "fn f(a){ return a; } print f(nope);"),
    ("error_inside_if",
     "fn f(n){ if n { print 1; print nope; } return 0; } print f(1);"),
    ("error_after_loop",
     "fn f(){ let i=0; while i<2 { print i; i=i+1; } return nope; } "
     "print f();"),
]

LIMIT_PROGRAMS = [
    ("tokens_2049", ";" * 2049),
    ("depth_before_unknown", "fn f1(){return f2();} fn f2(){return f3();} fn f3(){return f4();} fn f4(){return f5();} fn f5(){return f6();} fn f6(){return f7();} fn f7(){return f8();} fn f8(){return f9();} fn f9(){return f10();} fn f10(){return f11();} fn f11(){return f12();} fn f12(){return f13();} fn f13(){return f14();} fn f14(){return f15();} fn f15(){return f16();} fn f16(){return nope();} f1();"),
    ("nodes_512_ok", "let a=1;" * 256),
    ("nodes_514_limit", "let a=1;" * 257),
    ("nodes_400_ok", "let a=1;" * 200),
    ("nodes_600_limit", "let a=1;" * 300),
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
    ("frame_vars_17_limit",
     "fn f(){ " + "".join("let v%d=%d;" % (i, i) for i in range(17)) +
     " return v16; } print f();"),
    ("output_256_ok",
     "print 18446744073709551615;" * 12 + "print 999;"),
    ("output_257_limit",
     "print 18446744073709551615;" * 12 + "print 999; print 1;"),
    ("output_in_function_limit",
     "fn f(){ " + "print 18446744073709551615;" * 13 + " } "
     "print 1; f();"),
    ("frame_vars_16_with_params_ok",
     "fn f(a){ " + "".join("let v%d=%d;" % (i, i) for i in range(15)) +
     " return v14; } print f(1);"),
    ("frame_vars_17_with_params_limit",
     "fn f(a){ " + "".join("let v%d=%d;" % (i, i) for i in range(16)) +
     " return v15; } print f(1);"),
    ("recursion_limit",
     "fn f(){ return f(); } print f();"),
    ("recursion_limit_with_output",
     "fn f(){ print 1; return f(); } print f();"),
    ("step_limit", "while 1 {}"),
    ("params_16_ok",
     "fn f(a,b,c,d,e,g,h,i,j,k,l,m,n,o,p,q){ return q; } "
     "print f(1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16);"),
    ("params_17_limit",
     "fn f(a,b,c,d,e,g,h,i,j,k,l,m,n,o,p,q,r){ return q; } print f(1);"),
    ("functions_64_ok",
     "".join("fn f%d(){ return %d; }" % (i, i) for i in range(64)) +
     "print f63();"),
    ("functions_65_limit",
     "".join("fn f%d(){ return %d; }" % (i, i) for i in range(65)) +
     "print f64();"),
]


def chain_program(count):
    """Cadena f1 -> f2 -> ... -> fcount; ejercicio puro de profundidad."""
    parts = []
    for index in range(1, count):
        parts.append("fn f%d(){ return f%d(); }" % (index, index + 1))
    parts.append("fn f%d(){ return 99; }" % count)
    parts.append("print f1();")
    return "".join(parts)


class SelfHostInterpFunctionsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ZEN.is_file():
            raise RuntimeError(
                f"falta el compilador {ZEN}; construyelo con: "
                "CARGO_HOME=\"$PWD/.cargo\" cargo build --release --offline "
                "--manifest-path zen/compiler/Cargo.toml"
            )
        cls._tmpdir = tempfile.TemporaryDirectory(prefix="zen-selfhost-fns-")
        cls.tmp = pathlib.Path(cls._tmpdir.name)
        cls.obj = cls.tmp / "interp_functions.o"
        cls.exe = cls.tmp / "interp_functions_driver"
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
        self.assertEqual(reference("fn f(a){ return a+1; } print f(2);"),
                         (0, 2, fnv1a32(b"3\n"), 2))
        self.assertEqual(reference(""), (0, 0, FNV_OFFSET, 0))
        self.assertEqual(reference("print 1/0;"), (2, 1, FNV_OFFSET, 0))
        self.assertEqual(reference("print nope(1);"), (5, 1, FNV_OFFSET, 0))
        self.assertEqual(reference("fn f(a){} print f(1,2);"), (6, 0, 0, 0))
        self.assertEqual(reference("return 1;"), (1, 0, 0, 0))
        self.assertEqual(
            reference("fn fac(n){ if n<=1 { return 1; } "
                      "return n*fac(n-1); } print fac(5);"),
            (0, 11, fnv1a32(b"120\n"), 4),
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

    def test_arity_errors_have_zeroed_counters(self):
        for name, program in ARITY_PROGRAMS:
            with self.subTest(name=name):
                actual = self.run_zen(program)
                self.assertEqual(actual[0], 6, f"{name}: {actual}")
                self.assertEqual(actual[1:], (0, 0, 0), name)

    def test_runtime_errors_match_reference(self):
        for name, program in RUNTIME_PROGRAMS:
            with self.subTest(name=name):
                self.check_against_reference(program)

    def test_limit_programs_match_reference(self):
        for name, program in LIMIT_PROGRAMS:
            with self.subTest(name=name):
                self.check_against_reference(program)

    def test_explicit_results(self):
        cases = {
            "fn f(a){ return a+1; } print f(41);":
                (0, 2, fnv1a32(b"42\n"), 3),
            "fn fac(n){ if n<=1 { return 1; } return n*fac(n-1); } "
            "print fac(5);": (0, 11, fnv1a32(b"120\n"), 4),
            "fn f(){ print 9; } print f();":
                (0, 2, fnv1a32(b"9\n0\n"), 4),
            "print 7; print nope(1);":
                (5, 2, fnv1a32(b"7\n"), 2),
            "fn f(){ return nope; } print f();":
                (3, 2, FNV_OFFSET, 0),
            "fn f(a){ return 10/a; } print f(0);":
                (2, 2, FNV_OFFSET, 0),
            "fn f(a){ return a; } print f(1,2);": (6, 0, 0, 0),
        }
        for program, expected in cases.items():
            with self.subTest(program=program):
                self.assertEqual(self.run_zen(program), expected)

    def test_statement_counter_semantics(self):
        # La llamada no cuenta como sentencia; el cuerpo de la funcion si.
        self.assertEqual(
            self.run_zen("fn f(){ return 1; } print f();")[1], 2)
        self.assertEqual(
            self.run_zen("fn f(){ print 1; return 2; } print f();")[1], 3)
        # Cada re-evaluacion de la condicion de un while cuenta.
        self.assertEqual(
            self.run_zen("fn f(n){ let i=0; while i<n { i=i+1; } "
                         "return i; } print f(3);")[1], 10)

    def test_unknown_function_keeps_prior_output(self):
        actual = self.run_zen("print 1; print 2; print nope(3);")
        self.assertEqual(actual[0], 5)
        self.assertEqual(actual[1], 3)
        self.assertEqual(actual[2:], (fnv1a32(b"1\n2\n"), 4))

    def test_arity_checked_for_later_declaration(self):
        self.assertEqual(
            self.run_zen("print f(1,2); fn f(a){ return a; }"), (6, 0, 0, 0))
        self.assertEqual(
            self.run_zen("print f(1); fn f(a){ return a; }")[0], 0)

    def test_local_scope_is_isolated(self):
        # El nivel superior no ve los locales de la funcion y viceversa.
        self.assertEqual(
            self.run_zen("fn f(){ let y=2; return y; } print f(); print y;"),
            (3, 4, fnv1a32(b"2\n"), 2))
        self.assertEqual(
            self.run_zen("let x=5; fn f(){ return x; } print f();"),
            (3, 3, FNV_OFFSET, 0))
        # Un parametro es mutable por asignacion y no afecta al llamante.
        self.assertEqual(
            self.run_zen("fn f(a){ a=a+1; return a; } let a=1; "
                         "print f(a); print a;"),
            (0, 5, fnv1a32(b"2\n1\n"), 4))

    def test_recursive_functions(self):
        self.assertEqual(
            self.run_zen("fn fac(n){ if n<=1 { return 1; } "
                         "return n*fac(n-1); } print fac(6);"),
            (0, 13, fnv1a32(b"720\n"), 4))
        self.assertEqual(
            self.run_zen("fn fib(n){ if n<2 { return n; } "
                         "return fib(n-1)+fib(n-2); } print fib(12);")[0], 0)

    def test_call_depth_boundary(self):
        self.assertEqual(self.run_zen(chain_program(16))[0], 0)
        self.assertEqual(self.run_zen(chain_program(16))[1], 17)
        self.assertEqual(self.run_zen(chain_program(17))[0], 4)
        self.assertEqual(self.run_zen(chain_program(17))[1], 17)

    def test_infinite_recursion_stops(self):
        status, executed, _hash, bytes_out = self.run_zen(
            "fn f(){ return f(); } print f();")
        self.assertEqual(status, 4)
        self.assertEqual(executed, 17)
        self.assertEqual(bytes_out, 0)

    def test_step_limit_stops_infinite_loop(self):
        status, executed, _hash, bytes_out = self.run_zen("while 1 {}")
        self.assertEqual(status, 4)
        self.assertGreater(executed, STEP_LIMIT)
        self.assertLessEqual(executed, STEP_LIMIT + 2)
        self.assertEqual(bytes_out, 0)

    def test_variable_limit_per_frame(self):
        ok = ("fn f(){ " +
              "".join("let v%d=%d;" % (i, i) for i in range(16)) +
              " return v15; } print f();")
        self.assertEqual(self.run_zen(ok)[0], 0)
        overflow = ("fn f(){ " +
                    "".join("let v%d=%d;" % (i, i) for i in range(17)) +
                    " return v16; } print f();")
        self.assertEqual(self.run_zen(overflow)[0], 4)

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

    def test_deterministic(self):
        program = ("fn fac(n){ if n<=1 { return 1; } return n*fac(n-1); } "
                   "print fac(7); let i=0; while i<3 { print i; i=i+1; }")
        first = self.run_zen(program)
        second = self.run_zen(program)
        self.assertEqual(first, second)
        self.assertEqual(first, reference(program))

    def test_source_uses_local_fixed_arrays(self):
        source = SOURCE.read_text(encoding="utf-8")
        for token in (
            "pub fn zen_interp_fns(source:u64,length:u64,out:u64)->u64",
            "[u32;2048]", "[u32;512]", "[u64;512]", "[u32;272]",
            "[u64;8704]", "volatile_store",
        ):
            self.assertIn(token, source, f"falta {token!r} en interp_functions.zen")
        self.assertNotIn("extern fn", source)
        self.assertNotIn("#include", source)
        # La ejecucion recorre la RPN del AST, no la fuente original.
        for token in ("ek[ei]", "ev[ei]", "ea[ei]", "vals["):
            self.assertIn(token, source, f"falta el recorrido {token!r}")
        # Hay marcos explicitos y no recursion del interprete en Zen.
        for token in ("fr_eval[", "fr_vcount[", "nframes", "return_pending"):
            self.assertIn(token, source, f"falta el marco {token!r}")

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
