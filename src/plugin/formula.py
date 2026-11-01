"""Formulas: a regular-expression tokenizer and a precedence-climbing parser into a small syntax tree.

The grammar (the text after a cell's leading ``=``; spaces between tokens are ignored)::

    expression := unary (binary-operator unary)*      grouped by precedence, every operator left to right
    unary      := ("-" | "+") unary | primary
    primary    := NUMBER | STRING | NAME "(" [argument ("," argument)*] ")" | NAME | "(" expression ")"
    argument   := CELL ":" CELL | expression          a range only as a whole function argument
    NUMBER     := digits ["." digits]                  no exponent, no sign (a sign is the unary operator)
    STRING     := '"' (a character other than '"' | '""')* '"'
    NAME       := letter (letter | digit | "_" | ".")*

Binary operators, highest precedence first: ``^``; ``*`` ``/``; ``+`` ``-``; ``=`` ``<>`` ``<`` ``<=`` ``>`` ``>=``.
Unary ``-`` and ``+`` bind tighter than ``^`` (``-2^2`` is ``(-2)^2``). A bare NAME is TRUE or FALSE (any case), a
cell reference A1 to Z99 (any case), or else an unknown name (#NAME? when evaluated). Function names are matched
in upper case.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction

CELL = re.compile(r"[A-Z][1-9][0-9]?")
TOKEN = re.compile(
    r"""\s*(?:
        (?P<number>[0-9]+(?:\.[0-9]+)?)
      | (?P<string>"(?:[^"]|"")*")
      | (?P<name>[A-Za-z][A-Za-z0-9_.]*)
      | (?P<operator><>|<=|>=|[-+*/^=<>(),:])
    )""",
    re.VERBOSE,
)
# Binary operators and their precedence: a higher number binds tighter.
PRECEDENCE = {"=": 1, "<>": 1, "<": 1, "<=": 1, ">": 1, ">=": 1, "+": 2, "-": 2, "*": 3, "/": 3, "^": 4}
COMPARISONS = frozenset({"=", "<>", "<", "<=", ">", ">="})


@dataclass(frozen=True)
class Number:
    value: Fraction


@dataclass(frozen=True)
class String:
    value: str


@dataclass(frozen=True)
class Boolean:
    value: bool


@dataclass(frozen=True)
class Ref:
    cell: str


@dataclass(frozen=True)
class Range:
    first: str
    last: str

    def cells(self) -> list[str]:
        """Every cell of the rectangle between the two corners (in either order), row by row, left to right."""
        left, right = sorted((self.first[0], self.last[0]))
        top, bottom = sorted((int(self.first[1:]), int(self.last[1:])))
        return [f"{chr(column)}{row}" for row in range(top, bottom + 1) for column in range(ord(left), ord(right) + 1)]


@dataclass(frozen=True)
class Name:
    name: str


@dataclass(frozen=True)
class Unary:
    operator: str
    operand: Node


@dataclass(frozen=True)
class Binary:
    operator: str
    left: Node
    right: Node


@dataclass(frozen=True)
class Call:
    name: str  # upper case
    arguments: tuple[Node, ...]


Node = Number | String | Boolean | Ref | Range | Name | Unary | Binary | Call


def tokenize(text: str) -> list[tuple[str, str]]:
    """(kind, text) pairs: number, string, name or operator; ValueError at the first character that starts none."""
    tokens = []
    at = 0
    while text[at:].strip():
        match = TOKEN.match(text, at)
        if match is None or match.lastgroup is None:
            spot = len(text) - len(text[at:].lstrip())
            raise ValueError(f"unexpected {text[spot]!r} at position {spot + 1}")
        tokens.append((match.lastgroup, match.group(match.lastgroup)))
        at = match.end()
    return tokens


class _Parser:
    def __init__(self, text: str) -> None:
        self.tokens = tokenize(text)
        self.at = 0

    def peek(self, ahead: int = 0) -> tuple[str, str] | None:
        index = self.at + ahead
        return self.tokens[index] if index < len(self.tokens) else None

    def take(self) -> tuple[str, str]:
        token = self.peek()
        if token is None:
            raise ValueError("the formula ends too early")
        self.at += 1
        return token

    def expect(self, operator: str) -> None:
        token = self.peek()
        if token != ("operator", operator):
            found = "the end" if token is None else repr(token[1])
            raise ValueError(f"expected {operator!r} but found {found}")
        self.at += 1

    def expression(self, minimum: int = 1) -> Node:
        left = self.unary()
        while True:
            token = self.peek()
            if token is None or token[0] != "operator" or PRECEDENCE.get(token[1], 0) < minimum:
                return left
            self.at += 1
            # Every binary operator groups left to right, so its right side binds one level tighter.
            left = Binary(token[1], left, self.expression(PRECEDENCE[token[1]] + 1))

    def unary(self) -> Node:
        token = self.peek()
        if token in (("operator", "-"), ("operator", "+")):
            self.at += 1
            return Unary(token[1], self.unary())
        return self.primary()

    def primary(self) -> Node:
        kind, text = self.take()
        if kind == "number":
            return Number(Fraction(text))
        if kind == "string":
            return String(text[1:-1].replace('""', '"'))
        if kind == "name":
            upper = text.upper()
            if self.peek() == ("operator", "("):
                self.at += 1
                return Call(upper, self.arguments())
            if upper in ("TRUE", "FALSE"):
                return Boolean(upper == "TRUE")
            if CELL.fullmatch(upper):
                return Ref(upper)
            return Name(text)
        if text == "(":
            inner = self.expression()
            self.expect(")")
            return inner
        raise ValueError(f"unexpected {text!r}")

    def arguments(self) -> tuple[Node, ...]:
        if self.peek() == ("operator", ")"):
            self.at += 1
            return ()
        found = [self.argument()]
        while self.peek() == ("operator", ","):
            self.at += 1
            found.append(self.argument())
        self.expect(")")
        return tuple(found)

    def argument(self) -> Node:
        first, colon, last = self.peek(), self.peek(1), self.peek(2)
        if colon == ("operator", ":"):
            corners = [token[1].upper() for token in (first, last) if token is not None and token[0] == "name"]
            if len(corners) != 2 or not all(CELL.fullmatch(corner) for corner in corners):
                raise ValueError("a range is two cell addresses joined by ':', e.g. A1:C3")
            self.at += 3
            return Range(*corners)
        return self.expression()


def parse(text: str) -> Node:
    """The formula ``text`` (without its leading =) as a syntax tree, or ValueError saying why it is malformed."""
    try:
        parser = _Parser(text)
        if not parser.tokens:
            raise ValueError("it is empty")
        tree = parser.expression()
        if parser.peek() is not None:
            raise ValueError(f"unexpected {parser.peek()[1]!r} after a complete expression")
    except ValueError as error:
        raise ValueError(f"malformed formula ={text}: {error}") from None
    return tree


def references(node: Node) -> set[str]:
    """Every cell the formula mentions: references, every cell of every range, in every branch."""
    if isinstance(node, Ref):
        return {node.cell}
    if isinstance(node, Range):
        return set(node.cells())
    if isinstance(node, Unary):
        return references(node.operand)
    if isinstance(node, Binary):
        return references(node.left) | references(node.right)
    if isinstance(node, Call):
        return set().union(*(references(argument) for argument in node.arguments))
    return set()
