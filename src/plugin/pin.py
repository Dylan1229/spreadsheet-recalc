"""pin_values, the answer key: each target's exact value, the workbook's cycle cells and the data's sha256."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

from contract import Kind, PinnedValue, PinnedValuesOutput, RecalcInput
from plugin.recalc import Sheet, Value
from plugin.workbook import check_targets, data_sha256, find_workbook, reading_order


def exact_text(value: Fraction) -> str:
    """A number exactly: its decimal when it terminates (-12.45, 1200), else the fraction p/q (1/3, -535/12)."""
    rest, places = value.denominator, 0
    for prime in (2, 5):
        count = 0
        while rest % prime == 0:
            rest //= prime
            count += 1
        places = max(places, count)
    if rest != 1:
        return f"{value.numerator}/{value.denominator}"
    digits = str(abs(value.numerator * 10**places // value.denominator)).rjust(places + 1, "0")
    shown = f"{digits[:-places]}.{digits[-places:]}" if places else digits
    return f"-{shown}" if value < 0 else shown


def pinned(cell: str, content: str, value: Value) -> PinnedValue:
    if value.kind == "number":
        return PinnedValue(cell, content, Kind.NUMBER, float(value.payload), "", exact_text(value.payload))
    if value.kind == "boolean":
        return PinnedValue(cell, content, Kind.BOOLEAN, 0.0, "TRUE" if value.payload else "FALSE", "")
    if value.kind == "empty":
        return PinnedValue(cell, content, Kind.EMPTY, 0.0, "", "")
    return PinnedValue(cell, content, Kind(value.kind), 0.0, value.payload, "")


def pin_values(given: RecalcInput, workspace: Path) -> PinnedValuesOutput:
    book = find_workbook(given.workbook)
    check_targets(given.targets)
    sheet = Sheet(book.cells)
    return PinnedValuesOutput(
        workbook=book.id,
        targets=list(given.targets),
        values=[pinned(cell, book.cells.get(cell, ""), sheet.value(cell)) for cell in given.targets],
        cycle_cells=sorted(sheet.cycles, key=reading_order),
        data_sha256=data_sha256(),
    )
