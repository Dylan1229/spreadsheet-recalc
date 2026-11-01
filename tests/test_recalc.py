"""Both engines (the answer key's src/plugin/recalc.py and the verifier's verifier/sheet.py) against golden values
worked out by hand from the stated rules, never by running either engine: every formula cell of every bundled
workbook, then each rule on small sheets made for it."""

from __future__ import annotations

import pytest
from helpers import EMPTY, boolean, both, error, number, text

from plugin.recalc import Sheet
from plugin.workbook import workbooks
from verifier.sheet import evaluate

DIV0, VALUE, NAME, NUM, CIRC = "#DIV/0!", "#VALUE!", "#NAME?", "#NUM!", "#CIRC!"

GOLDEN = {
    "trip-budget": {
        "B3": number("269.7"),  # 89.9 x 3
        "B6": number(75),  # 25 x 3
        "B8": number("757.2"),  # 412.5 + 269.7 + 75; B4 'included' (text) and B5 (empty) skipped
        "B9": number(3),  # B2, B3, B6 are the range's numbers
        "B10": number("252.4"),  # 757.2 / 3
        "B12": number("3786/35"),  # 757.2 / 7 = 108.171428...
        "B13": number("108.17"),  # 108.1714... to 2 places
        "B14": boolean(True),  # 757.2 > 750
        "B15": number(0),  # empty B5 is 0: 0 / 7
        "B5": EMPTY,
        "B4": text("included"),
        "B2": number("412.5"),
    },
    "invoice": {
        "D2": number(50),  # 4 x 12.5
        "D3": number("59.97"),  # 3 x 19.99
        "D4": number("14.5"),  # 2 x 7.25
        "D6": number("124.47"),  # 50 + 59.97 + 14.5
        "D7": number("-12.45"),  # 124.47 > 100: -ROUND(12.447, 2)
        "D8": number("112.02"),  # 124.47 - 12.45
        "D10": number("9.24"),  # 112.02 x 0.0825 = 9.24165 -> 9.24
        "D11": number("121.26"),  # 112.02 + 9.24
        "D12": text("yes"),  # 121.26 >= 120
    },
    "inventory-reorder": {
        "D2": text("ok"),  # 120 < 100 is FALSE
        "D3": text("REORDER"),  # 40 < 50
        "D4": text("REORDER"),  # empty B4 compared with a number is 0: 0 < 25
        "D5": text("ok"),  # 'n/a' < 10: text sorts above numbers, so FALSE
        "D6": text("ok"),  # 75 < 75 is FALSE
        "B8": number(235),  # 120 + 40 + 75; empty B4 and text B5 skipped
        "B9": number(3),
        "B10": number(40),
        "B11": boolean(False),  # B4 > 0 is 0 > 0, FALSE
    },
    "simple-interest": {
        "B4": number(35),  # 1000 x 0.035 x 1
        "C4": number(1035),
        "D4": number("86.25"),  # 1035 / 12
        "B5": number(70),
        "C5": number(1070),
        "D5": number("535/12"),  # 1070 / 24 = 44.58333...
        "B6": number(175),
        "C6": number(1175),
        "D6": number("235/12"),  # 1175 / 60 = 19.58333...
        "B8": number(280),  # 35 + 70 + 175
        "B9": number("1187.69"),  # 1000 x 1.035^5 = 1187.686305646875 -> 1187.69
        "B10": error(NUM),  # exponent 1/12 is not a whole number
    },
    "operator-precedence": {
        "A2": text("-2^2"),
        "B2": number(4),  # (-2)^2
        "B3": number(64),  # (2^3)^2
        "B4": number(-4),
        "B5": number(-4),  # 0 - (2^2)
        "B6": number(14),
        "B7": number(20),
        "B8": number(3),  # (10-4)-3
        "B9": number(1),  # (12/4)/3
        "B10": number("0.5"),  # 2^(-1)
        "B11": number(18),  # 2 x 9
        "B12": number(-8),  # (-2)^3
        "B13": boolean(True),  # (1+2) = 3
        "B14": boolean(False),  # (1<2) is TRUE; TRUE < 3 is FALSE since booleans sort above numbers
        "B15": error(NUM),
    },
    "rounding": {
        "B2": number(3),  # 2.5 -> 3
        "B3": number(-3),  # -2.5 -> -3, away from zero
        "B4": number(1200),  # 12.345 hundreds -> 12
        "B5": number("0.13"),  # 12.5 hundredths -> 13
        "B6": number("-0.13"),
        "B7": number(1300),  # 12.5 hundreds -> 13
        "B8": number(0),  # 0.49 hundreds -> 0
        "B9": number("2.35"),  # digits 2.9 -> 2; 234.5 hundredths -> 235
        "B10": number(-10),  # digits -1.7 -> -1; 0.745 tens -> 1
        "B11": number(0),  # empty A11 is 0
        "A11": EMPTY,
        "A12": number("1/3"),
        "B12": number("0.3333"),  # 3333.33 ten-thousandths -> 3333
        "A13": text("2.5"),
        "B13": error(VALUE),  # text '2.5 in arithmetic
        "B14": number("3.13"),  # |-3| + |-0.13|
        "B15": error(VALUE),  # SUM meets B13's error in its range
    },
    "error-showcase": {
        "B1": error(DIV0),  # 10 / 0
        "B2": error(VALUE),  # 10 + 'abc'
        "B3": error(VALUE),  # '12 is text
        "B4": error(NAME),  # SQRT is not a function here
        "B5": error(NUM),  # 10^0.5
        "B6": error(NUM),  # 0^0
        "B7": error(DIV0),  # 0^-1
        "B8": error(VALUE),  # 'abc' + (10/0): the left operand fails first
        "B9": error(DIV0),  # (10/0) + 'abc': the left operand fails first
        "B10": number(-1),  # IFERROR catches B1
        "B11": text("n/a"),  # A2 = 0, so the division is never evaluated
        "B12": boolean(False),  # no else
        "B13": error(DIV0),  # no numbers among two texts
        "B14": error(VALUE),  # ROUND needs 2 arguments
        "B15": error(VALUE),  # text condition
        "B16": text("no sqrt"),  # IFERROR catches #NAME?
        "B17": number(10),  # 10 + 0; texts and TRUE in the range skipped
        "B18": number(11),  # 10 + TRUE
        "B19": number(0),  # MIN of no numbers
        "B20": error(VALUE),  # a range where one value is expected
        "B21": error(NAME),  # Rate is no cell and no function
        "B22": error(NUM),  # SUM meets B5's #NUM! before B1's #DIV/0!
        "B23": number(20),
    },
    "circular-refs": {
        "A1": error(CIRC),  # A1 <-> A2
        "A2": error(CIRC),
        "B1": error(CIRC),  # B1 -> B2 -> B3 -> B1
        "B2": error(CIRC),
        "B3": error(CIRC),
        "C1": error(CIRC),  # mentions itself
        "C2": error(CIRC),  # mentions itself in the branch not taken: still a cycle
        "D1": error(CIRC),  # not on a cycle, but mentions A1
        "D2": number(-1),  # IFERROR catches A1's #CIRC!
        "D3": number(7),  # mentions B1 only in the branch not taken, and is on no cycle
        "D4": error(CIRC),  # the range B1:B3 holds cycle cells
        "E4": error(CIRC),  # its range E1:E4 holds E4 itself
        "D5": error(CIRC),  # D1 + 1
        "E5": number(8),  # 5 + 1 + 2
        "D6": number(0),  # IFERROR catches D5
        "E1": number(5),  # A2 mentions it, but it is no formula
    },
    "text-and-booleans": {
        "B1": boolean(True),  # 'Apple' = 'APPLE' ignoring case
        "B2": boolean(True),  # 'banana' > 'apple'
        "B3": boolean(True),  # 7 < 'Apple': numbers sort below text
        "B4": boolean(True),  # 'Apple' < TRUE: text sorts below booleans
        "B5": number(2),  # TRUE + TRUE
        "B6": boolean(True),  # empty against text is ""
        "B7": boolean(True),  # empty against a number is 0
        "B8": boolean(True),  # empty against a boolean is FALSE
        "B9": boolean(False),  # text '12 is not the number 12
        "B10": error(VALUE),
        "B11": number(7),  # only A7 is a number
        "B12": number(1),
        "B13": number(7),  # references: TRUE and FALSE in them are skipped
        "B14": number(8),  # literals: TRUE is 1, FALSE 0, plus A7
        "B15": boolean(False),  # NOT(7): 7 is TRUE
        "B16": boolean(True),
        "B17": boolean(False),  # FALSE, empty
        "B18": text("big"),
        "B19": text('say "hi"'),
        "B20": boolean(True),
        "B21": text("blank"),  # an empty condition is FALSE
        "B22": error(VALUE),  # AND of text
        "B23": number(0),  # a formula showing an empty cell gives 0
        "A6": text("12"),
        "A8": EMPTY,
    },
    "gradebook": {
        "D2": number("90.7"),  # (88 + 184) / 3 = 90.666... -> 90.7
        "E2": text("A"),
        "D3": number(83),  # (79 + 170) / 3
        "E3": text("B"),
        "D4": number("46.7"),  # (0 + 140) / 3 = 46.666... -> 46.7
        "E4": text("C"),
        "D5": error(VALUE),  # B5 'excused' is text
        "E5": error(VALUE),  # the condition D5 >= 90 is an error
        "D7": number("1102/15"),  # (90.7 + 83 + 46.7) / 3 = 220.4 / 3
        "B8": number("83.5"),  # (88 + 79) / 2: empty B4 and text B5 skipped
        "D9": number("272/3"),
    },
}
CYCLES = {"circular-refs": ["A1", "B1", "C1", "A2", "B2", "C2", "B3", "E4"]}


@pytest.mark.parametrize("book", sorted(GOLDEN))
def test_boundary_golden_values_by_hand(book: str) -> None:
    cells = workbooks()[book].cells
    targets = sorted(GOLDEN[book])
    assert both(cells, targets) == [GOLDEN[book][target] for target in targets]
    _values, circular = evaluate(cells, targets)
    assert circular == CYCLES.get(book, [])


def test_correct_every_formula_cell_has_a_golden_value() -> None:
    """The table above covers every formula of every workbook, so no bundled value goes unchecked by hand."""
    assert set(GOLDEN) == set(workbooks())
    for book in workbooks().values():
        formulas = {cell for cell, content in book.cells.items() if content.startswith("=")}
        assert formulas <= set(GOLDEN[book.id]), book.id


def test_correct_the_engines_agree_on_every_cell_of_a1_to_h30() -> None:
    cells_of_grid = [f"{column}{row}" for row in range(1, 31) for column in "ABCDEFGH"]
    for book in workbooks().values():
        both(book.cells, cells_of_grid)


def one(formula: str, cells: dict[str, str] | None = None) -> tuple:
    """The value of a formula put in Z99 of a sheet holding ``cells``, by both engines."""
    return both({**(cells or {}), "Z99": formula}, ["Z99"])[0]


SHEET = {"A1": "5", "A2": "TRUE", "A3": "abc", "A4": "'7", "A5": "=1/0", "A6": "FALSE"}  # A7 to A9 are empty

RULES = [
    # coercion in arithmetic
    ("=A7+1", number(1)),
    ("=A2*3", number(3)),
    ("=A6-1", number(-1)),
    ("=A4+0", error(VALUE)),
    ("=-A3", error(VALUE)),
    ("=+A3", error(VALUE)),  # unary + coerces too (Excel would keep the text)
    ("=+A2", number(1)),
    ("=--A2", number(1)),
    # first error, left to right, each operand coerced as it is evaluated
    ("=A3+A5", error(VALUE)),
    ("=A5+A3", error(DIV0)),
    ("=SUM(A3*1,A5)", error(VALUE)),
    ("=SUM(A5,A3*1)", error(DIV0)),
    ("=A5=1", error(DIV0)),
    ("=1=FOO()", error(NAME)),
    # comparisons
    ('="a"<"B"', boolean(True)),
    ('="b"<"A"', boolean(False)),
    ('="abc"="ABC"', boolean(True)),
    ('="ab"<"abc"', boolean(True)),
    ("=TRUE>1000", boolean(True)),
    ('="zzz"<FALSE', boolean(True)),
    ("=FALSE<TRUE", boolean(True)),
    ("=A7=A8", boolean(True)),  # two empties
    ("=A7<-1", boolean(False)),  # empty is 0
    ('="a">A7', boolean(True)),  # empty is ""
    ("=FALSE=A7", boolean(True)),  # empty is FALSE
    ("=TRUE>A7", boolean(True)),
    ("=1<>1", boolean(False)),
    ("=2>=2", boolean(True)),
    ("=2<=1", boolean(False)),
    # power
    ("=(-2)^3", number(-8)),
    ("=2^-2^2", number("1/16")),  # (2^-2)^2
    ("=0^2", number(0)),
    ("=0^0.5", error(NUM)),  # the exponent is checked first
    ("=(-8)^(1/3)", error(NUM)),
    ("=2^A2", number(2)),
    ("=A2^0", number(1)),
    ("=A7^0", error(NUM)),  # empty is 0: 0^0
    ("=0^-2", error(DIV0)),
    # division
    ("=1/A7", error(DIV0)),
    ("=7/2*2", number(7)),
    # ROUND
    ("=ROUND(-0.5,0)", number(-1)),
    ("=ROUND(0.5,0)", number(1)),
    ("=ROUND(15,-1)", number(20)),
    ("=ROUND(-15,-1)", number(-20)),
    ("=ROUND(1.005,2)", number("1.01")),  # exact: 1.005 is a true half
    ("=ROUND(5,-1.9)", number(10)),  # digits -1
    ("=ROUND(2.25,A2)", number("2.3")),  # digits TRUE = 1
    ("=ROUND(A4,0)", error(VALUE)),
    ("=ROUND(1234.5678,-5)", number(0)),
    # ABS, NOT, AND, OR
    ("=ABS(-3.5)", number("3.5")),
    ("=ABS(A2)", number(1)),
    ("=ABS(A3)", error(VALUE)),
    ("=NOT(A7)", boolean(True)),
    ("=NOT(A3)", error(VALUE)),
    ("=NOT(0.1)", boolean(False)),
    ("=AND(FALSE,A5)", error(DIV0)),  # no short-circuit
    ("=OR(TRUE,A3)", error(VALUE)),
    ("=OR(0,A7,FALSE)", boolean(False)),
    ("=AND(A1,A2,-1)", boolean(True)),
    ("=AND(A1:A2)", error(VALUE)),  # a range outside the aggregates
    # IF and IFERROR
    ("=IF(TRUE,1,A5)", number(1)),
    ("=IF(FALSE,A5)", boolean(False)),
    ("=IF(A5,1,2)", error(DIV0)),
    ('=IF(0.5,"y","n")', text("y")),
    ('=IF(A7,"y","n")', text("n")),
    ("=IF(TRUE,A1:A2)", error(VALUE)),
    ('=IFERROR("x",1)', text("x")),
    ("=IFERROR(A3+1,A5)", error(DIV0)),  # the alternative's own error stands
    ("=IFERROR(FOO(1),2)", number(2)),
    # aggregates
    ("=SUM(A1:A4)", number(5)),  # TRUE, 'abc' and '7 skipped
    ("=SUM(A4:A1)", number(5)),  # corners in either order
    ("=COUNT(A1:A4)", number(1)),
    ("=COUNT(A6:A9)", number(0)),  # FALSE and empties
    ("=SUM(A1:A9)", error(DIV0)),  # A5 holds =1/0
    ("=SUM(A2,A1)", number(5)),  # a reference argument skips booleans
    ("=SUM((A2),A1)", number(5)),  # parentheses keep it a reference
    ("=SUM(A2*1,A1)", number(6)),  # an expression argument is coerced
    ('=SUM("3")', error(VALUE)),
    ("=SUM(TRUE)", number(1)),
    ("=COUNT(TRUE,FALSE)", number(2)),
    ("=COUNT(A7)", number(0)),
    ("=COUNT(A7+0)", number(1)),
    ("=AVERAGE(A7)", error(DIV0)),
    ("=AVERAGE(A1,2,A7)", number("3.5")),
    ("=MAX(-5,-2)", number(-2)),
    ("=MIN(A7:A9)", number(0)),
    ("=MAX(A1:A6)", error(DIV0)),  # A5's error in the range
    ("=SUM(A1:A4,A5)", error(DIV0)),
    # argument counts and names
    ("=IF(TRUE)", error(VALUE)),
    ("=NOT(1,2)", error(VALUE)),
    ("=SUM()", error(VALUE)),
    ("=IFERROR(1)", error(VALUE)),
    ("=ROUND(1,2,3)", error(VALUE)),
    ("=ROUND(A5)", error(VALUE)),  # counted before any argument is evaluated
    ("=FOO()", error(NAME)),
    ("=FOO(A5)", error(NAME)),
    ("=sum(1,2)", number(3)),  # names are case-insensitive
    ("=true", boolean(True)),
    ("=a1*2", number(10)),
    ("=Total", error(NAME)),
    ("=AA1", error(NAME)),
    ("=A100", error(NAME)),
    # literals and results
    ('=""', text("")),
    ('="a""b"', text('a"b')),
    ("=A9", number(0)),  # a formula showing an empty cell gives 0
    ("=IF(TRUE,A9)", number(0)),
    ("=IFERROR(A9,5)", number(0)),
    ("=A3", text("abc")),
    ("= 1 +  2 ", number(3)),  # spaces between tokens
    ("=SUM( A1 , 2 )", number(7)),
]


@pytest.mark.parametrize(("formula", "expected"), RULES, ids=[formula for formula, _ in RULES])
def test_boundary_each_rule_by_hand(formula: str, expected: tuple) -> None:
    assert one(formula, SHEET) == expected


@pytest.mark.parametrize(
    ("cells", "cyclic", "circ"),
    [
        ({"A1": "=SUM(A1:A2)", "A2": "1"}, ["A1"], ["A1"]),  # a range holding its own cell
        # a cycle only through branches that are never taken is still a cycle
        ({"A1": "=IF(TRUE,1,B1)", "B1": "=IF(FALSE,A1,2)"}, ["A1", "B1"], ["A1", "B1"]),
        ({"A1": "=IFERROR(A2,0)", "A2": "=A1"}, ["A1", "A2"], ["A1", "A2"]),  # IFERROR cannot rescue its own cycle
        # a 4-cell cycle, and E1 which only mentions it
        (
            {"A1": "=B1", "B1": "=C1", "C1": "=D1", "D1": "=A1", "E1": "=D1+1"},
            ["A1", "B1", "C1", "D1"],
            ["A1", "B1", "C1", "D1", "E1"],
        ),
        ({"A1": "=B1", "B1": "=C1", "C1": "5"}, [], []),  # a chain is no cycle
        ({"A1": "=FOO(A1)"}, ["A1"], ["A1"]),  # an unknown function's arguments still count
        ({"A1": "=ROUND(A1)"}, ["A1"], ["A1"]),  # so do a wrong count's
    ],
)
def test_boundary_cycles_are_static(cells: dict[str, str], cyclic: list[str], circ: list[str]) -> None:
    targets = sorted(cells)
    values = both(cells, targets)
    assert [target for target, value in zip(targets, values, strict=True) if value == error(CIRC)] == circ
    assert evaluate(cells, targets)[1] == cyclic
    assert sorted(Sheet(cells).cycles) == cyclic
