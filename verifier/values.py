"""Cell values as the task reports them ({cell, kind, number, text}), their shape rules, and how a reported value
is judged against a value the verifier computed (a tuple from sheet.py)."""

import math
import re
from decimal import Decimal
from fractions import Fraction

ERRORS = ("#DIV/0!", "#VALUE!", "#NAME?", "#NUM!", "#CIRC!")
TOLERANCE = Fraction(1, 10**6)  # a number passes when |reported - exact| <= TOLERANCE x max(1, |exact|)
EXACT = re.compile(r"-?[0-9]+(\.[0-9]+)?|-?[0-9]+/[1-9][0-9]*")


def plain_value(entry):
    """A contract CellValue (or PinnedValue) as JSON."""
    return {"cell": entry.cell, "kind": entry.kind.value, "number": entry.number, "text": entry.text}


def plain_values(value, path=None):
    """A ValuesOutput (pass its path) or SaveValuesInput as JSON, as save_values writes it."""
    found = {
        "workbook": value.workbook,
        "targets": list(value.targets),
        "values": [plain_value(entry) for entry in value.values],
    }
    if path is not None:
        found["path"] = path
    return found


def shape_problem(entry):
    """What is wrong with one reported value's fields for its kind, or None (whether it is right is not asked)."""
    where = f"{entry['cell']} ({entry['kind']})"
    number, text = entry["number"], entry["text"]
    if not math.isfinite(number):
        return f"{where}: number must be a finite number, not {number!r}"
    if entry["kind"] == "number":
        return f"{where}: text must be empty for a number" if text else None
    if number != 0:
        return f"{where}: number must be 0 unless kind is number"
    if entry["kind"] == "boolean" and text not in ("TRUE", "FALSE"):
        return f"{where}: text must be TRUE or FALSE, not {text!r}"
    if entry["kind"] == "error" and text not in ERRORS:
        return f"{where}: text must be one of {', '.join(ERRORS)}, not {text!r}"
    if entry["kind"] == "empty" and text:
        return f"{where}: text must be empty for an empty cell"
    return None


def exact_of(text):
    """An exact number as the answer key writes it (-12.45 or 1/3), or None when it is not one."""
    return Fraction(text) if EXACT.fullmatch(text) else None


def expected_text(value):
    """The text a computed value is reported with."""
    if value[0] == "text" or value[0] == "error":
        return value[1]
    if value[0] == "boolean":
        return "TRUE" if value[1] else "FALSE"
    return ""


def exact_text(exact):
    """A number written exactly: 757.2 when its decimal ends (within 30 places), else 3786/35."""
    for places in range(31):
        scaled = exact * 10**places
        if scaled.denominator == 1:
            return format(Decimal(scaled.numerator).scaleb(-places), "f")
    return f"{exact.numerator}/{exact.denominator}"


def shown(value):
    """A computed value for a message: 757.2, 3786/35 (= 108.17142857142858), 'yes', TRUE, #DIV/0! or empty."""
    if value[0] == "number":
        text = exact_text(value[1])
        return text if "/" not in text else f"{text} (= {float(value[1])!r})"
    if value[0] == "text":
        return repr(value[1])
    if value[0] == "empty":
        return "empty"
    return expected_text(value)


def described(value):
    """A computed value with its kind, for a message: number 757.2, text 'yes', error #DIV/0!, empty."""
    return "empty" if value[0] == "empty" else f"{value[0]} {shown(value)}"


def within(reported, exact):
    return math.isfinite(reported) and abs(Fraction(reported) - exact) <= TOLERANCE * max(1, abs(exact))


def is_correct(entry, value):
    """Whether a well-shaped reported value is the computed one: same kind, the number within the tolerance,
    the text exactly."""
    if shape_problem(entry) or entry["kind"] != value[0]:
        return False
    if value[0] == "number":
        return within(entry["number"], value[1])
    return entry["text"] == expected_text(value)
