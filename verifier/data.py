"""The bundled workbooks as the verifier reads them, independently of src/: the file itself, read from the
plugin folder, and the views the tools must give of it."""

import hashlib
import json
import re
from functools import cache
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "src" / "plugin" / "data" / "workbooks.json"
ADDRESS = re.compile(r"[A-Z][1-9][0-9]?")
MAX_TARGETS = 8


@cache
def raw_bytes():
    return DATA.read_bytes()


def sha256():
    return hashlib.sha256(raw_bytes()).hexdigest()


def position(cell):
    """Sort key of an address: by row, then by column."""
    return int(cell[1:]), cell[0]


@cache
def books():
    """workbook id -> {"title", "cells": {address: content}} as the file lists them."""
    found = {}
    for book in json.loads(raw_bytes().decode("utf-8"))["workbooks"]:
        found[book["id"]] = {"title": book["title"], "cells": dict(book["cells"])}
    return found


def used_range(cells):
    columns = sorted(cell[0] for cell in cells)
    rows = sorted(int(cell[1:]) for cell in cells)
    return f"{columns[0]}{rows[0]}:{columns[-1]}{rows[-1]}"


def sheet_view(book_id):
    """What get_sheet must return for a known workbook: its cells by row, then column."""
    book = books()[book_id]
    cells = sorted(book["cells"], key=position)
    return {
        "workbook": book_id,
        "title": book["title"],
        "used_range": used_range(cells),
        "cells": [{"cell": cell, "content": book["cells"][cell]} for cell in cells],
    }


def listing():
    """What list_workbooks must return: every workbook by id."""
    return [
        {
            "id": book_id,
            "title": books()[book_id]["title"],
            "used_range": used_range(books()[book_id]["cells"]),
            "cells": len(books()[book_id]["cells"]),
        }
        for book_id in sorted(books())
    ]


def workbook_problem(book_id):
    if book_id not in books():
        return f"unknown workbook {book_id!r}: one of {', '.join(sorted(books()))}"
    return None


def targets_problem(targets):
    if not 1 <= len(targets) <= MAX_TARGETS:
        return f"targets must hold 1 to {MAX_TARGETS} cell addresses, not {len(targets)}"
    for target in targets:
        if not ADDRESS.fullmatch(target):
            return f"target {target!r} is not a cell address of A1:Z99"
    twice = sorted({target for target in targets if targets.count(target) > 1}, key=position)
    if twice:
        return f"targets name {', '.join(twice)} more than once"
    return None


def input_problem(book_id, targets):
    """Why a workbook and targets cannot be a task, or None."""
    return workbook_problem(book_id) or targets_problem(list(targets))
