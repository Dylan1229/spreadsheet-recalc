"""The bundled workbooks (src/plugin/data/workbooks.json): cell addresses, literal contents, loading and checks.

A cell's content is what was typed into it: ``=`` starts a formula; a leading ``'`` marks text (``'12`` is the
text ``12``); ``TRUE`` and ``FALSE`` are booleans; a decimal such as ``12``, ``-3.5`` or ``0.125`` is a number;
anything else is text. A cell that is not listed is empty.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from fractions import Fraction
from functools import cache
from pathlib import Path

from plugin.formula import parse

DATA = Path(__file__).with_name("data") / "workbooks.json"
ADDRESS = re.compile(r"[A-Z]([1-9][0-9]?)")  # A1 to Z99
NUMBER_LITERAL = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?")
# What a reader could take for a number or boolean although NUMBER_LITERAL and TRUE/FALSE do not match it: the
# data writes such text with a leading ' instead.
NUMBER_LIKE = re.compile(r"[+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
BOOLEANS = {"TRUE": True, "FALSE": False}
MAX_TARGETS = 8
MAX_CELLS = 30  # non-empty cells per workbook
LAST_COLUMN, LAST_ROW = "H", 30  # every non-empty cell lies in A1:H30
MAX_FORMULA = 200  # characters


@dataclass(frozen=True)
class Workbook:
    id: str
    title: str
    cells: dict[str, str]  # address -> content, row by row, left to right

    @property
    def used_range(self) -> str:
        columns = sorted({cell[0] for cell in self.cells})
        rows = sorted(row_of(cell) for cell in self.cells)
        return f"{columns[0]}{rows[0]}:{columns[-1]}{rows[-1]}"


def row_of(cell: str) -> int:
    return int(cell[1:])


def reading_order(cell: str) -> tuple[int, str]:
    """Sort key: row by row, left to right."""
    return row_of(cell), cell[0]


def is_address(text: str) -> bool:
    return ADDRESS.fullmatch(text) is not None


def literal(content: str) -> tuple[str, object]:
    """A literal content's kind and value: ("number", Fraction), ("text", str) or ("boolean", bool)."""
    if content.startswith("'"):
        return "text", content[1:]
    if content in BOOLEANS:
        return "boolean", BOOLEANS[content]
    if NUMBER_LITERAL.fullmatch(content):
        return "number", Fraction(content)
    return "text", content


def content_problem(content: str) -> str | None:
    """Why a content is not one the bundled data may hold (unambiguous, printable ASCII), or None."""
    if not content or content != content.strip() or not content.isascii() or not content.isprintable():
        return "is blank, has surrounding spaces or is not printable ASCII"
    if content.startswith("="):
        if len(content) > MAX_FORMULA:
            return f"is a formula over {MAX_FORMULA} characters"
        try:
            parse(content[1:])
        except ValueError as error:
            return str(error)
        return None
    if content == "'":
        return "is an empty text"
    if not content.startswith("'"):
        if content.upper() in BOOLEANS and content not in BOOLEANS:
            return "reads as a boolean in another case: write TRUE or FALSE, or 'text"
        if NUMBER_LIKE.fullmatch(content) and not NUMBER_LITERAL.fullmatch(content):
            return "looks like a number but is not a plain decimal: write it as one, or as 'text"
    return None


def data_sha256() -> str:
    return hashlib.sha256(DATA.read_bytes()).hexdigest()


def _workbook(raw: dict) -> Workbook:
    where = f"workbook {raw.get('id')!r}"
    cells = raw["cells"]
    if not 1 <= len(cells) <= MAX_CELLS:
        raise ValueError(f"{where}: it must hold 1 to {MAX_CELLS} non-empty cells")
    for cell, content in cells.items():
        if not is_address(cell) or cell[0] > LAST_COLUMN or row_of(cell) > LAST_ROW:
            raise ValueError(f"{where}: {cell!r} is not a cell of A1:{LAST_COLUMN}{LAST_ROW}")
        problem = content_problem(content)
        if problem:
            raise ValueError(f"{where}: {cell} {content!r} {problem}")
    if list(cells) != sorted(cells, key=reading_order):
        raise ValueError(f"{where}: cells must be listed row by row, left to right")
    return Workbook(raw["id"], raw["title"], dict(cells))


@cache
def workbooks() -> dict[str, Workbook]:
    """Every bundled workbook by id, each checked as it loads."""
    raw = json.loads(DATA.read_text(encoding="utf-8"))
    found: dict[str, Workbook] = {}
    for entry in raw["workbooks"]:
        if entry["id"] in found:
            raise ValueError(f"workbook id {entry['id']!r} is used twice")
        found[entry["id"]] = _workbook(entry)
    return found


def find_workbook(workbook: str) -> Workbook:
    """The workbook, or a ValueError naming those that exist."""
    known = workbooks()
    if workbook not in known:
        raise ValueError(f"unknown workbook {workbook!r}: one of {', '.join(sorted(known))}")
    return known[workbook]


def check_targets(targets: list[str]) -> None:
    """1 to 8 different addresses of A1:Z99, or a ValueError saying what is wrong."""
    if not 1 <= len(targets) <= MAX_TARGETS:
        raise ValueError(f"targets must hold 1 to {MAX_TARGETS} cell addresses, not {len(targets)}")
    for target in targets:
        if not is_address(target):
            raise ValueError(
                f"target {target!r} is not a cell address of A1:Z99 (a column letter A-Z, then a row 1-99 without a"
                " leading zero, no $ and no spaces)"
            )
    repeated = sorted({target for target in targets if targets.count(target) > 1}, key=reading_order)
    if repeated:
        raise ValueError(f"targets name {', '.join(repeated)} more than once")
