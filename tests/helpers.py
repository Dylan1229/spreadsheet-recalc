"""Building tool and verifier arguments as NanoAgent does: JSON built into contract classes."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

from slimconfig import build_output, plain_output

import verifier
from contract import TOOLS, PinnedValuesOutput, RecalcInput, SaveValuesInput, Tool, ValuesOutput
from plugin import pin_values, save_values
from plugin.recalc import Sheet
from verifier.sheet import evaluate

TRIP = {"workbook": "trip-budget", "targets": ["B8", "B12", "B13", "B5", "B14", "A2"]}
INVOICE = {"workbook": "invoice", "targets": ["D7", "D10", "D11", "D12"]}
PRECEDENCE = {"workbook": "operator-precedence", "targets": ["B2", "B3", "B10", "B14", "B15"]}
CIRCULAR = {"workbook": "circular-refs", "targets": ["A1", "B2", "C1", "C2", "D1", "D2", "D3", "E5"]}
ERRORS = {"workbook": "error-showcase", "targets": ["B8", "B9", "B11", "B12", "B13", "B16", "B21", "B22"]}


def number(value: str | int) -> tuple[str, Fraction]:
    return ("number", Fraction(value))


def text(value: str) -> tuple[str, str]:
    return ("text", value)


def boolean(value: bool) -> tuple[str, bool]:
    return ("boolean", value)


def error(code: str) -> tuple[str, str]:
    return ("error", code)


EMPTY = ("empty", None)


def both(cells: dict[str, str], targets: list[str]) -> list[tuple]:
    """Each target's value by the plugin's engine, after checking the verifier's engine gives the same."""
    sheet = Sheet(cells)
    mine = [(value.kind, value.payload) for value in (sheet.value(target) for target in targets)]
    theirs, _circular = evaluate(cells, targets)
    assert mine == theirs, (cells, targets, mine, theirs)
    return mine


def pinned(arguments: dict) -> dict:
    """pin_values's output as NanoAgent pins it: JSON."""
    return plain_output(pin_values(build_output(arguments, RecalcInput), Path(".")))


def right_values(arguments: dict) -> list[dict]:
    """The answer key's values as an agent reports them (numbers to 10 significant figures)."""
    return [
        {"cell": row["cell"], "kind": row["kind"], "number": float(f"{row['number']:.10g}"), "text": row["text"]}
        for row in pinned(arguments)["values"]
    ]


def answer(arguments: dict, changes: dict | None = None) -> dict:
    """save_values's input for the right values, with ``changes`` ({cell: {field: value}}) applied."""
    values = right_values(arguments)
    for entry in values:
        entry.update((changes or {}).get(entry["cell"], {}))
    return arguments | {"values": values}


def saved(arguments: dict, workspace: Path, changes: dict | None = None) -> dict:
    """save_values's output, as JSON, for the right values with ``changes``."""
    return plain_output(save_values(build_output(answer(arguments, changes), SaveValuesInput), workspace))


def judge(arguments: dict, output: dict, workspace: Path, reference: dict | None | str = "pin") -> dict:
    """verify_task's verdict on ``output``, against the pinned answer key unless ``reference`` is given."""
    key = pinned(arguments) if reference == "pin" else reference
    return verifier.verify_task(
        "recalc-cells",
        build_output(arguments, RecalcInput),
        build_output(output, ValuesOutput),
        None if key is None else build_output(key, PinnedValuesOutput),
        str(workspace),
    )


def verify_input(tool: str, value: dict) -> dict:
    return verifier.verify_input(tool, build_output(value, TOOLS[Tool(tool)][0]))


def verify_output(tool: str, given: dict, made: dict, workspace: Path) -> dict:
    given_class, made_class = TOOLS[Tool(tool)]
    return verifier.verify_output(
        tool, build_output(given, given_class), build_output(made, made_class), str(workspace)
    )


def failing(verdict: dict) -> list[str]:
    """The ids of the checks that fail."""
    return [entry["id"] for entry in verdict["details"]["checks"] if entry["ok"] is False]


def unchecked(verdict: dict) -> list[str]:
    return [entry["id"] for entry in verdict["details"]["checks"] if entry["ok"] is None]
