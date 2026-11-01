"""The verifier's own spreadsheet engine, written apart from src/: a character-by-character tokenizer, a
recursive-descent parser with one function per precedence level, and an evaluator over plain tuples. It never
calls eval or compile. The answer key must agree with it on every value it states.

Values are tuples: ("number", Fraction), ("text", str), ("boolean", bool), ("empty", None), ("error", code).
A cell is on a circular reference when, following the cells each formula mentions (ranges expanded, every
branch included), it can reach itself; such a cell is #CIRC! without being evaluated.
"""

import re
import string
from fractions import Fraction

DIGITS = "0123456789"
LETTERS = string.ascii_letters
NAME_REST = LETTERS + DIGITS + "_."
TWO_CHAR = ("<>", "<=", ">=")
ONE_CHAR = "-+*/^=<>(),:"
COMPARISONS = ("=", "<>", "<", "<=", ">", ">=")
CELL = re.compile(r"[A-Z][1-9][0-9]?")
DECIMAL = re.compile(r"-?(0|[1-9][0-9]*)(\.[0-9]+)?")
DIV0, VALUE, NAME, NUM, CIRC = "#DIV/0!", "#VALUE!", "#NAME?", "#NUM!", "#CIRC!"
AGGREGATES = ("SUM", "AVERAGE", "MIN", "MAX", "COUNT")
# name -> the argument counts it accepts (None: any count from the lower bound up)
COUNTS = {
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
EMPTY = ("empty", None)


class FormulaError(ValueError):
    """A formula the grammar does not accept."""


def tokens(text):
    """[(kind, text)] with kind number, string, name or op; FormulaError at a character that starts no token."""
    found = []
    at = 0
    while at < len(text):
        char = text[at]
        if char.isspace():
            at += 1
        elif char in DIGITS:
            end = at
            while end < len(text) and text[end] in DIGITS:
                end += 1
            if end + 1 < len(text) and text[end] == "." and text[end + 1] in DIGITS:
                end += 1
                while end < len(text) and text[end] in DIGITS:
                    end += 1
            found.append(("number", text[at:end]))
            at = end
        elif char == '"':
            end = at + 1
            pieces = []
            while True:
                if end >= len(text):
                    raise FormulaError(f"the text starting at position {at + 1} is never closed")
                if text[end] == '"':
                    if end + 1 < len(text) and text[end + 1] == '"':
                        pieces.append('"')
                        end += 2
                        continue
                    break
                pieces.append(text[end])
                end += 1
            found.append(("string", "".join(pieces)))
            at = end + 1
        elif char in LETTERS:
            end = at + 1
            while end < len(text) and text[end] in NAME_REST:
                end += 1
            found.append(("name", text[at:end]))
            at = end
        elif text[at : at + 2] in TWO_CHAR:
            found.append(("op", text[at : at + 2]))
            at += 2
        elif char in ONE_CHAR:
            found.append(("op", char))
            at += 1
        else:
            raise FormulaError(f"unexpected {char!r} at position {at + 1}")
    return found


class Reader:
    """Recursive descent: comparison < additive < multiplicative < power < unary < primary."""

    def __init__(self, text):
        self.items = tokens(text)
        self.at = 0

    def look(self, ahead=0):
        index = self.at + ahead
        return self.items[index] if index < len(self.items) else ("end", "")

    def is_op(self, symbols, ahead=0):
        kind, text = self.look(ahead)
        return kind == "op" and text in symbols

    def need(self, symbol):
        if not self.is_op((symbol,)):
            raise FormulaError(f"expected {symbol!r}, found {self.look()[1] or 'the end'!r}")
        self.at += 1

    def comparison(self):
        tree = self.additive()
        while self.is_op(COMPARISONS):
            symbol = self.look()[1]
            self.at += 1
            tree = ("compare", symbol, tree, self.additive())
        return tree

    def additive(self):
        tree = self.multiplicative()
        while self.is_op(("+", "-")):
            symbol = self.look()[1]
            self.at += 1
            tree = ("arith", symbol, tree, self.multiplicative())
        return tree

    def multiplicative(self):
        tree = self.power()
        while self.is_op(("*", "/")):
            symbol = self.look()[1]
            self.at += 1
            tree = ("arith", symbol, tree, self.power())
        return tree

    def power(self):
        tree = self.unary()
        while self.is_op(("^",)):
            self.at += 1
            tree = ("arith", "^", tree, self.unary())
        return tree

    def unary(self):
        if self.is_op(("-", "+")):
            symbol = self.look()[1]
            self.at += 1
            return ("sign", symbol, self.unary())
        return self.primary()

    def primary(self):
        kind, text = self.look()
        self.at += 1
        if kind == "number":
            return ("literal", ("number", Fraction(text)))
        if kind == "string":
            return ("literal", ("text", text))
        if kind == "name":
            upper = text.upper()
            if self.is_op(("(",)):
                self.at += 1
                return ("call", upper, self.arguments())
            if upper == "TRUE" or upper == "FALSE":
                return ("literal", ("boolean", upper == "TRUE"))
            if CELL.fullmatch(upper):
                return ("cell", upper)
            return ("name", text)
        if kind == "op" and text == "(":
            tree = self.comparison()
            self.need(")")
            return tree
        raise FormulaError(f"unexpected {text or 'end of formula'!r}")

    def arguments(self):
        found = []
        if self.is_op((")",)):
            self.at += 1
            return found
        while True:
            found.append(self.argument())
            if self.is_op((",",)):
                self.at += 1
                continue
            self.need(")")
            return found

    def argument(self):
        if self.is_op((":",), 1):
            first, last = self.look(), self.look(2)
            if first[0] != "name" or last[0] != "name":
                raise FormulaError("a range joins two cell addresses with ':'")
            corners = (first[1].upper(), last[1].upper())
            if not (CELL.fullmatch(corners[0]) and CELL.fullmatch(corners[1])):
                raise FormulaError("a range joins two cell addresses with ':'")
            self.at += 3
            return ("range", block(corners[0], corners[1]))
        return self.comparison()


def block(first, last):
    """The cells of the rectangle with corners ``first`` and ``last``: by row, then by column."""
    columns = sorted((first[0], last[0]))
    rows = sorted((int(first[1:]), int(last[1:])))
    found = []
    for row in range(rows[0], rows[1] + 1):
        for code in range(ord(columns[0]), ord(columns[1]) + 1):
            found.append(chr(code) + str(row))
    return found


def read(formula):
    """A formula's text (after its =) as a tree, or FormulaError."""
    reader = Reader(formula)
    if not reader.items:
        raise FormulaError("the formula is empty")
    tree = reader.comparison()
    if reader.look()[0] != "end":
        raise FormulaError(f"unexpected {reader.look()[1]!r} after the formula")
    return tree


def mentions(tree):
    """Every cell a tree mentions, in any branch."""
    kind = tree[0]
    if kind == "cell":
        return {tree[1]}
    if kind == "range":
        return set(tree[1])
    if kind == "sign":
        return mentions(tree[2])
    if kind in ("arith", "compare"):
        return mentions(tree[2]) | mentions(tree[3])
    if kind == "call":
        found = set()
        for argument in tree[2]:
            found |= mentions(argument)
        return found
    return set()


def literal(content):
    """A non-formula content's value."""
    if content.startswith("'"):
        return ("text", content[1:])
    if content == "TRUE" or content == "FALSE":
        return ("boolean", content == "TRUE")
    if DECIMAL.fullmatch(content):
        return ("number", Fraction(content))
    return ("text", content)


def circular(graph):
    """The cells that reach themselves along the graph's edges (each formula cell -> the cells it mentions)."""
    found = set()
    for start in graph:
        seen = set()
        todo = list(graph[start])
        while todo:
            cell = todo.pop()
            if cell == start:
                found.add(start)
                break
            if cell not in seen:
                seen.add(cell)
                todo.extend(graph.get(cell, ()))
    return found


def to_number(value):
    kind = value[0]
    if kind == "number" or kind == "error":
        return value
    if kind == "boolean":
        return ("number", Fraction(1 if value[1] else 0))
    if kind == "empty":
        return ("number", Fraction(0))
    return ("error", VALUE)


def to_boolean(value):
    kind = value[0]
    if kind == "boolean" or kind == "error":
        return value
    if kind == "number":
        return ("boolean", value[1] != 0)
    if kind == "empty":
        return ("boolean", False)
    return ("error", VALUE)


def order(left, right):
    """Comparison order of two non-error values: -1, 0 or 1."""
    kinds = ("number", "text", "boolean")
    zeros = {"number": Fraction(0), "text": "", "boolean": False}
    if left[0] == "empty":
        left = ("number", Fraction(0)) if right[0] == "empty" else (right[0], zeros[right[0]])
    if right[0] == "empty":
        right = (left[0], zeros[left[0]])
    if left[0] != right[0]:
        return -1 if kinds.index(left[0]) < kinds.index(right[0]) else 1
    a, b = left[1], right[1]
    if left[0] == "text":
        a, b = a.lower(), b.lower()
    if a == b:
        return 0
    return -1 if a < b else 1


def rounded(number, digits):
    """Half away from zero; digits truncated toward zero, may be negative."""
    whole = digits.numerator // digits.denominator
    if whole < 0 and whole * digits.denominator != digits.numerator:
        whole += 1  # floor division went below a negative non-integer: truncate toward zero instead
    factor = Fraction(10) ** whole
    shifted = abs(number) * factor + Fraction(1, 2)
    kept = Fraction(shifted.numerator // shifted.denominator) / factor
    return -kept if number < 0 else kept


class Book:
    """One workbook's contents and the values computed from them, each cell's value computed once."""

    def __init__(self, cells):
        self.cells = cells
        self.trees = {}
        for cell, content in cells.items():
            if content.startswith("="):
                try:
                    self.trees[cell] = read(content[1:])
                except FormulaError as problem:
                    raise FormulaError(f"{cell} {content!r}: {problem}") from None
        self.circular = circular({cell: mentions(tree) for cell, tree in self.trees.items()})
        self.known = {}

    def value(self, cell):
        if cell not in self.known:
            if cell not in self.cells:
                self.known[cell] = EMPTY
            elif cell in self.circular:
                self.known[cell] = ("error", CIRC)
            elif cell in self.trees:
                result = self.run(self.trees[cell])
                self.known[cell] = ("number", Fraction(0)) if result[0] == "empty" else result
            else:
                self.known[cell] = literal(self.cells[cell])
        return self.known[cell]

    def run(self, tree):
        kind = tree[0]
        if kind == "literal":
            return tree[1]
        if kind == "cell":
            return self.value(tree[1])
        if kind == "range":
            return ("error", VALUE)
        if kind == "name":
            return ("error", NAME)
        if kind == "sign":
            operand = to_number(self.run(tree[2]))
            if operand[0] == "error" or tree[1] == "+":
                return operand
            return ("number", -operand[1])
        if kind == "compare":
            left = self.run(tree[2])
            if left[0] == "error":
                return left
            right = self.run(tree[3])
            if right[0] == "error":
                return right
            way = order(left, right)
            symbol = tree[1]
            truth = (
                (symbol == "=" and way == 0)
                or (symbol == "<>" and way != 0)
                or (symbol == "<" and way < 0)
                or (symbol == "<=" and way <= 0)
                or (symbol == ">" and way > 0)
                or (symbol == ">=" and way >= 0)
            )
            return ("boolean", truth)
        if kind == "arith":
            left = to_number(self.run(tree[2]))
            if left[0] == "error":
                return left
            right = to_number(self.run(tree[3]))
            if right[0] == "error":
                return right
            return operate(tree[1], left[1], right[1])
        return self.function(tree[1], tree[2])

    def gather(self, arguments):
        """(the numbers an aggregate takes, None) or (None, the first error)."""
        numbers = []
        for argument in arguments:
            if argument[0] == "cell" or argument[0] == "range":
                cells = [argument[1]] if argument[0] == "cell" else argument[1]
                for cell in cells:
                    value = self.value(cell)
                    if value[0] == "error":
                        return None, value
                    if value[0] == "number":
                        numbers.append(value[1])
                continue
            value = to_number(self.run(argument))
            if value[0] == "error":
                return None, value
            numbers.append(value[1])
        return numbers, None

    def function(self, name, arguments):
        if name not in COUNTS:
            return ("error", NAME)
        low, high = COUNTS[name]
        if len(arguments) < low or (high is not None and len(arguments) > high):
            return ("error", VALUE)
        if name == "IF":
            test = to_boolean(self.run(arguments[0]))
            if test[0] == "error":
                return test
            if test[1]:
                return self.run(arguments[1])
            if len(arguments) == 3:
                return self.run(arguments[2])
            return ("boolean", False)
        if name == "IFERROR":
            first = self.run(arguments[0])
            if first[0] == "error":
                return self.run(arguments[1])
            return first
        if name in AGGREGATES:
            numbers, problem = self.gather(arguments)
            if problem is not None:
                return problem
            total = Fraction(0)
            for number in numbers:
                total += number
            if name == "SUM":
                return ("number", total)
            if name == "COUNT":
                return ("number", Fraction(len(numbers)))
            if name == "AVERAGE":
                if not numbers:
                    return ("error", DIV0)
                return ("number", total / len(numbers))
            if not numbers:
                return ("number", Fraction(0))
            pick = numbers[0]
            for number in numbers[1:]:
                if (name == "MIN" and number < pick) or (name == "MAX" and number > pick):
                    pick = number
            return ("number", pick)
        convert = to_boolean if name in ("AND", "OR", "NOT") else to_number
        values = []
        for argument in arguments:
            value = convert(self.run(argument))
            if value[0] == "error":
                return value
            values.append(value[1])
        if name == "NOT":
            return ("boolean", not values[0])
        if name == "AND":
            return ("boolean", False not in values)
        if name == "OR":
            return ("boolean", True in values)
        if name == "ABS":
            return ("number", values[0] if values[0] >= 0 else -values[0])
        return ("number", rounded(values[0], values[1]))


def operate(symbol, left, right):
    if symbol == "+":
        return ("number", left + right)
    if symbol == "-":
        return ("number", left - right)
    if symbol == "*":
        return ("number", left * right)
    if symbol == "/":
        if right == 0:
            return ("error", DIV0)
        return ("number", left / right)
    if right.denominator != 1:
        return ("error", NUM)
    if left == 0:
        if right == 0:
            return ("error", NUM)
        if right < 0:
            return ("error", DIV0)
        return ("number", Fraction(0))
    result = left ** abs(right.numerator)
    return ("number", result if right >= 0 else 1 / result)


def evaluate(cells, targets):
    """(each target's value, in order; the sorted circular cells) for a workbook's contents ``cells``."""
    book = Book(cells)
    values = [book.value(target) for target in targets]
    return values, sorted(book.circular, key=lambda cell: (int(cell[1:]), cell[0]))
