"""save_values: writes the agent's values to the workspace as they are given. It checks their shape (one value
per target, in order; each value's fields fit its kind) and computes nothing: whether a value is right is the
verifier's."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from slimconfig import plain_output

from contract import CellValue, Kind, SaveValuesInput, ValuesOutput
from plugin.recalc import ERRORS
from plugin.workbook import check_targets, find_workbook

FOLDER = "values"


def values_path(workbook: str, targets: list[str]) -> str:
    """values/<workbook>-<the first 10 hex digits of the sha256 of the targets joined by ','>.json."""
    digest = hashlib.sha256(",".join(targets).encode()).hexdigest()[:10]
    return f"{FOLDER}/{workbook}-{digest}.json"


def value_problem(entry: CellValue) -> str | None:
    """What is wrong with one value's fields for its kind, or None. Nothing here judges the value right."""
    where = f"{entry.cell} ({entry.kind.value})"
    if not math.isfinite(entry.number):
        return f"{where}: number must be a finite number, not {entry.number!r}"
    if entry.kind is Kind.NUMBER:
        return f"{where}: text must be empty for a number" if entry.text else None
    if entry.number != 0:
        return f"{where}: number must be 0 unless kind is number"
    if entry.kind is Kind.BOOLEAN and entry.text not in ("TRUE", "FALSE"):
        return f"{where}: text must be TRUE or FALSE, not {entry.text!r}"
    if entry.kind is Kind.ERROR and entry.text not in ERRORS:
        return f"{where}: text must be one of {', '.join(ERRORS)}, not {entry.text!r}"
    if entry.kind is Kind.EMPTY and entry.text:
        return f"{where}: text must be empty for an empty cell"
    return None


def shape_problem(given: SaveValuesInput) -> str | None:
    cells = [entry.cell for entry in given.values]
    if cells != list(given.targets):
        return f"values must give one value per target, in the order of targets {list(given.targets)}, not {cells}"
    for entry in given.values:
        problem = value_problem(entry)
        if problem:
            return problem
    return None


def save_values(given: SaveValuesInput, workspace: Path) -> ValuesOutput:
    """Write the values to values/<workbook>-<digest>.json, replacing an earlier save of the same task."""
    find_workbook(given.workbook)
    check_targets(given.targets)
    problem = shape_problem(given)
    if problem:
        raise ValueError(problem)
    relative = values_path(given.workbook, given.targets)
    root = workspace.resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"{relative} would leave the plugin workspace")
    output = ValuesOutput(
        workbook=given.workbook, targets=list(given.targets), values=list(given.values), path=relative
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plain_output(output), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output
