"""Recalculation: every cell's value under the stated semantics, exactly (numbers are Fractions).

Circular references are decided before anything is evaluated: each formula cell points at every cell its
formula mentions (ranges expanded, every IF branch and IFERROR argument included), and every cell of a strongly
connected component of more than one cell, or that points at itself, is #CIRC! (Tarjan's algorithm). Every other
cell is evaluated recursively, each once (memoized); following references from it never loops, because a
reference to a #CIRC! cell stops there.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction

from plugin.formula import Binary, Boolean, Call, Name, Node, Number, Range, Ref, String, Unary, parse, references
from plugin.workbook import literal

DIV0, VALUE, NAME, NUM, CIRC = "#DIV/0!", "#VALUE!", "#NAME?", "#NUM!", "#CIRC!"
ERRORS = (DIV0, VALUE, NAME, NUM, CIRC)
# Each function's (fewest, most) arguments; None is no upper limit.
ARITY = {
    "SUM": (1, None),
    "AVERAGE": (1, None),
    "MIN": (1, None),
    "MAX": (1, None),
    "COUNT": (1, None),
    "ROUND": (2, 2),
    "ABS": (1, 1),
    "IF": (2, 3),
    "AND": (1, None),
    "OR": (1, None),
    "NOT": (1, 1),
    "IFERROR": (2, 2),
}
# Across kinds a comparison orders number < text < boolean; an empty side becomes the other side's zero.
RANK = {"number": 0, "text": 1, "boolean": 2}
ZERO = {"number": Fraction(0), "text": "", "boolean": False}


@dataclass(frozen=True)
class Value:
    kind: str  # number, text, boolean, empty or error
    payload: Fraction | str | bool | None  # the number, the text, the boolean, None, or the error code


EMPTY = Value("empty", None)
FALSE = Value("boolean", False)


def number(value: Fraction | int) -> Value:
    return Value("number", Fraction(value))


def error(code: str) -> Value:
    return Value("error", code)


def as_number(value: Value) -> Value:
    """An operand coerced to a number: empty is 0, TRUE 1, FALSE 0; text is #VALUE!; an error stays."""
    if value.kind == "boolean":
        return number(int(value.payload))
    if value.kind == "empty":
        return number(0)
    if value.kind == "text":
        return error(VALUE)
    return value


def as_boolean(value: Value) -> Value:
    """A condition coerced to a boolean: a number is TRUE unless 0, empty is FALSE; text is #VALUE!."""
    if value.kind == "number":
        return Value("boolean", value.payload != 0)
    if value.kind == "empty":
        return FALSE
    if value.kind == "text":
        return error(VALUE)
    return value


def compare(left: Value, right: Value) -> int:
    """-1, 0 or 1 as ``left`` is below, equal to or above ``right`` (neither an error)."""
    if left.kind == "empty" and right.kind == "empty":
        return 0
    if left.kind == "empty":
        left = Value(right.kind, ZERO[right.kind])
    if right.kind == "empty":
        right = Value(left.kind, ZERO[left.kind])
    if left.kind != right.kind:
        return -1 if RANK[left.kind] < RANK[right.kind] else 1
    mine, theirs = left.payload, right.payload
    if left.kind == "text":
        mine, theirs = mine.lower(), theirs.lower()
    return (mine > theirs) - (mine < theirs)


def arithmetic(operator: str, left: Fraction, right: Fraction) -> Value:
    if operator == "+":
        return number(left + right)
    if operator == "-":
        return number(left - right)
    if operator == "*":
        return number(left * right)
    if operator == "/":
        return error(DIV0) if right == 0 else number(left / right)
    if right.denominator != 1:
        return error(NUM)
    if left == 0 and right == 0:
        return error(NUM)
    if left == 0 and right < 0:
        return error(DIV0)
    return number(left ** int(right))


def round_half_away(value: Fraction, digits: Fraction) -> Fraction:
    """ROUND: half away from zero, to ``digits`` truncated toward zero (negative: tens, hundreds, ...)."""
    scale = Fraction(10) ** math.trunc(digits)
    magnitude = Fraction(math.floor(abs(value) * scale + Fraction(1, 2))) / scale
    return magnitude if value >= 0 else -magnitude


def cycle_cells(graph: dict[str, set[str]]) -> set[str]:
    """The cells on a circular reference: Tarjan's strongly connected components of more than one cell, and
    every cell that points at itself."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    cyclic: set[str] = set()

    def visit(cell: str) -> None:
        index[cell] = low[cell] = len(index)
        stack.append(cell)
        for target in sorted(graph.get(cell, ())):
            if target not in index:
                visit(target)
                low[cell] = min(low[cell], low[target])
            elif target in stack:
                low[cell] = min(low[cell], index[target])
        if low[cell] == index[cell]:
            component = stack[stack.index(cell) :]
            del stack[stack.index(cell) :]
            if len(component) > 1 or cell in graph.get(cell, ()):
                cyclic.update(component)

    for cell in sorted(graph):
        if cell not in index:
            visit(cell)
    return cyclic


class Sheet:
    """One workbook's cells, evaluated on demand."""

    def __init__(self, cells: dict[str, str]) -> None:
        self.cells = cells
        self.trees = {cell: parse(content[1:]) for cell, content in cells.items() if content.startswith("=")}
        self.cycles = cycle_cells({cell: references(tree) for cell, tree in self.trees.items()})
        self.memo: dict[str, Value] = {}

    def value(self, cell: str) -> Value:
        """The cell's value: its literal, its formula's result (an empty result shows as 0), or empty."""
        if cell not in self.memo:
            content = self.cells.get(cell)
            if content is None:
                found = EMPTY
            elif cell in self.cycles:
                found = error(CIRC)
            elif cell in self.trees:
                found = self.evaluate(self.trees[cell])
                if found.kind == "empty":
                    found = number(0)
            else:
                found = Value(*literal(content))
            self.memo[cell] = found
        return self.memo[cell]

    def evaluate(self, node: Node) -> Value:
        if isinstance(node, Number):
            return number(node.value)
        if isinstance(node, String):
            return Value("text", node.value)
        if isinstance(node, Boolean):
            return Value("boolean", node.value)
        if isinstance(node, Ref):
            return self.value(node.cell)
        if isinstance(node, Range):
            return error(VALUE)  # a range where one value is expected
        if isinstance(node, Name):
            return error(NAME)
        if isinstance(node, Unary):
            operand = as_number(self.evaluate(node.operand))
            if operand.kind == "error" or node.operator == "+":
                return operand
            return number(-operand.payload)
        if isinstance(node, Binary):
            return self.binary(node)
        return self.call(node)

    def binary(self, node: Binary) -> Value:
        if node.operator in ("=", "<>", "<", "<=", ">", ">="):
            left = self.evaluate(node.left)
            if left.kind == "error":
                return left
            right = self.evaluate(node.right)
            if right.kind == "error":
                return right
            order = compare(left, right)
            holds = {
                "=": order == 0,
                "<>": order != 0,
                "<": order < 0,
                "<=": order <= 0,
                ">": order > 0,
                ">=": order >= 0,
            }
            return Value("boolean", holds[node.operator])
        left = as_number(self.evaluate(node.left))
        if left.kind == "error":
            return left
        right = as_number(self.evaluate(node.right))
        if right.kind == "error":
            return right
        return arithmetic(node.operator, left.payload, right.payload)

    def numbers(self, arguments: tuple[Node, ...]) -> list[Fraction] | Value:
        """The numbers SUM, AVERAGE, MIN, MAX and COUNT take: a reference or range argument gives the numbers in its
        cells (text, booleans and empty cells skipped), any other argument its value coerced; or the first error."""
        found: list[Fraction] = []
        for argument in arguments:
            if isinstance(argument, Ref | Range):
                for cell in [argument.cell] if isinstance(argument, Ref) else argument.cells():
                    value = self.value(cell)
                    if value.kind == "error":
                        return value
                    if value.kind == "number":
                        found.append(value.payload)
            else:
                value = as_number(self.evaluate(argument))
                if value.kind == "error":
                    return value
                found.append(value.payload)
        return found

    def scalars(self, arguments: tuple[Node, ...], coerce) -> list[Fraction | bool] | Value:
        """Each argument evaluated and coerced, left to right; or the first error."""
        found = []
        for argument in arguments:
            value = coerce(self.evaluate(argument))
            if value.kind == "error":
                return value
            found.append(value.payload)
        return found

    def call(self, node: Call) -> Value:
        if node.name not in ARITY:
            return error(NAME)
        fewest, most = ARITY[node.name]
        if len(node.arguments) < fewest or (most is not None and len(node.arguments) > most):
            return error(VALUE)
        name, arguments = node.name, node.arguments
        if name == "IF":
            condition = as_boolean(self.evaluate(arguments[0]))
            if condition.kind == "error":
                return condition
            if condition.payload:
                return self.evaluate(arguments[1])
            return self.evaluate(arguments[2]) if len(arguments) == 3 else FALSE
        if name == "IFERROR":
            first = self.evaluate(arguments[0])
            return self.evaluate(arguments[1]) if first.kind == "error" else first
        if name in ("SUM", "AVERAGE", "MIN", "MAX", "COUNT"):
            found = self.numbers(arguments)
            if isinstance(found, Value):
                return found
            if name == "SUM":
                return number(sum(found, Fraction(0)))
            if name == "COUNT":
                return number(len(found))
            if name == "AVERAGE":
                return number(sum(found, Fraction(0)) / len(found)) if found else error(DIV0)
            if not found:
                return number(0)
            return number(min(found) if name == "MIN" else max(found))
        if name in ("AND", "OR", "NOT"):
            found = self.scalars(arguments, as_boolean)
            if isinstance(found, Value):
                return found
            if name == "NOT":
                return Value("boolean", not found[0])
            return Value("boolean", all(found) if name == "AND" else any(found))
        found = self.scalars(arguments, as_number)
        if isinstance(found, Value):
            return found
        if name == "ABS":
            return number(abs(found[0]))
        return number(round_half_away(found[0], found[1]))
