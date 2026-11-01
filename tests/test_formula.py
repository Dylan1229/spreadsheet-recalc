"""The two formula parsers (src/plugin/formula.py's precedence climbing and verifier/sheet.py's recursive descent):
the trees they build, the formulas they refuse, and agreement with each other on random formulas and sheets."""

from __future__ import annotations

import random
import re
from fractions import Fraction

import pytest

from plugin.formula import Binary, Call, Number, Range, Ref, Unary, parse, references
from plugin.recalc import Sheet
from verifier.sheet import FormulaError, evaluate, mentions, read


def test_correct_precedence_trees() -> None:
    assert parse("-2^2") == Binary("^", Unary("-", Number(Fraction(2))), Number(Fraction(2)))
    assert parse("2^3^2") == Binary("^", Binary("^", Number(Fraction(2)), Number(Fraction(3))), Number(Fraction(2)))
    assert parse("1+2*3") == Binary("+", Number(Fraction(1)), Binary("*", Number(Fraction(2)), Number(Fraction(3))))
    assert parse("1<2<3") == Binary("<", Binary("<", Number(Fraction(1)), Number(Fraction(2))), Number(Fraction(3)))
    assert parse("SUM(a1:B2,C3)") == Call("SUM", (Range("A1", "B2"), Ref("C3")))
    assert read("-2^2") == (
        "arith",
        "^",
        ("sign", "-", ("literal", ("number", Fraction(2)))),
        ("literal", ("number", 2)),
    )
    assert read("2^3^2")[2][0] == "arith"  # the left operand is 2^3: ^ groups left to right


def test_correct_references_include_every_branch_and_range() -> None:
    formula = "IF(A1>0,SUM(B1:C2),IFERROR(D4,FOO(E5)))"
    expected = {"A1", "B1", "C1", "B2", "C2", "D4", "E5"}
    assert references(parse(formula)) == expected
    assert mentions(read(formula)) == expected


MALFORMED = [
    "",
    "   ",
    "1+",
    "(1",
    "1)",
    "A1:B2",
    "(A1:B2)",
    "SUM(A1:)",
    "SUM(:A1)",
    "SUM(A1:B)",
    "SUM(A1::B2)",
    "SUM(1,)",
    "SUM(,1)",
    "IF(",
    "1..2",
    "1.",
    ".5",
    "1e5",
    '"abc',
    '"a""',
    "1 2",
    "$A$1",
    "A1&B1",
    "=1",
    "1%",
    "{1}",
]


@pytest.mark.parametrize("formula", MALFORMED)
def test_malformed_formulas_are_refused_by_both_parsers(formula: str) -> None:
    with pytest.raises(ValueError, match="malformed formula"):
        parse(formula)
    with pytest.raises(FormulaError):
        read(formula)


PIECES = [
    "1", "2", "0", "0.5", "10", "A1", "B2", "C1", "b1", "A1:B2", "C2:A1", "+", "-", "*", "/", "^", "=", "<>", "<",
    ">=", "(", ")", ",", ":", '"x"', '""', '"X"', "SUM(", "AVERAGE(", "MIN(", "COUNT(", "IF(", "ROUND(", "IFERROR(",
    "AND(", "OR(", "NOT(", "ABS(", "FOO(", "TRUE", "false", "Rate", " ", '"', ".",
]  # fmt: skip
LITERALS = ["2", "-3.5", "0", "'7", "TRUE", "FALSE", "abc", "ABC"]
CELLS = ["A1", "B1", "C1", "A2", "B2", "C2"]


def formula_of(generator: random.Random) -> str:
    while True:
        text = "".join(generator.choice(PIECES) for _ in range(generator.randint(1, 9)))
        # keep powers small: no number of three digits or more, at most two ^
        if not re.search(r"[0-9]{3}", text) and text.count("^") <= 2:
            return text


def test_boundary_both_parsers_agree_on_random_formulas() -> None:
    """20,000 random formulas: the two parsers accept exactly the same ones and find the same references."""
    generator = random.Random(580)
    accepted = 0
    for _ in range(20_000):
        text = formula_of(generator)
        try:
            tree = parse(text)
        except ValueError:
            with pytest.raises(FormulaError):
                read(text)
            continue
        accepted += 1
        assert references(tree) == mentions(read(text)), text
    assert accepted > 1_000


def test_boundary_both_engines_agree_on_random_sheets() -> None:
    """3,000 random sheets of six cells, literals and formulas mixed, some with cycles: every cell, and the cycle
    cells, come out the same from both engines."""
    generator = random.Random(480)
    sheets = cyclic = 0
    while sheets < 3_000:
        cells = {}
        for cell in CELLS:
            if generator.random() < 0.6:
                cells[cell] = "=" + formula_of(generator)
            elif generator.random() < 0.8:
                cells[cell] = generator.choice(LITERALS)
        try:
            for content in cells.values():
                if content.startswith("="):
                    parse(content[1:])
        except ValueError:
            continue
        sheets += 1
        sheet = Sheet(cells)
        targets = CELLS + ["D9"]
        mine = [(value.kind, value.payload) for value in (sheet.value(target) for target in targets)]
        theirs, circular = evaluate(cells, targets)
        assert mine == theirs, cells
        assert sorted(sheet.cycles) == sorted(circular), cells
        cyclic += bool(circular)
    assert cyclic > 50
