"""The tools, called as the MCP server calls them, and the bundled data's own checks."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from helpers import CIRCULAR, TRIP, answer, pinned, saved
from slimconfig import build_output, plain_output

from contract import (
    ListWorkbooksInput,
    PinnedValuesOutput,
    RecalcInput,
    SaveValuesInput,
    SheetInput,
    ValuesOutput,
    WorkbooksOutput,
)
from plugin import get_sheet, list_workbooks, pin_values, save_values
from plugin.pin import exact_text
from plugin.workbook import DATA, content_problem, data_sha256, workbooks

ROOT = Path(__file__).resolve().parent.parent


def test_correct_list_workbooks(tmp_path: Path) -> None:
    made = list_workbooks(ListWorkbooksInput(), tmp_path)
    assert [book.id for book in made.workbooks] == sorted(workbooks())
    assert len(made.workbooks) == 10
    trip = next(book for book in made.workbooks if book.id == "trip-budget")
    assert (trip.title, trip.used_range, trip.cells) == ("Trip budget", "A1:D15", 29)
    assert build_output(plain_output(made), WorkbooksOutput) == made


@pytest.mark.parametrize("book", sorted(workbooks()))
def test_correct_get_sheet_is_compact_and_in_reading_order(tmp_path: Path, book: str) -> None:
    made = get_sheet(SheetInput(workbook=book), tmp_path)
    cells = [entry.cell for entry in made.cells]
    assert cells == sorted(cells, key=lambda cell: (int(cell[1:]), cell[0]))
    assert len(cells) <= 30 and all(cell[0] <= "H" and int(cell[1:]) <= 30 for cell in cells)
    # at most about 1,500 tokens for a model with 2,048-token replies
    assert len(json.dumps(plain_output(made))) < 2_000


def test_correct_get_sheet_shows_contents_as_typed(tmp_path: Path) -> None:
    made = get_sheet(SheetInput(workbook="rounding"), tmp_path)
    content = {entry.cell: entry.content for entry in made.cells}
    assert content["A13"] == "'2.5" and content["B9"] == "=ROUND(A9,2.9)" and "A11" not in content


def test_malformed_get_sheet_unknown_workbook(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown workbook 'budget': one of circular-refs, error-showcase"):
        get_sheet(SheetInput(workbook="budget"), tmp_path)


def test_correct_pin_values(tmp_path: Path) -> None:
    key = pin_values(build_output(TRIP, RecalcInput), tmp_path)
    assert [(row.cell, row.kind.value, row.exact) for row in key.values] == [
        ("B8", "number", "757.2"),
        ("B12", "number", "3786/35"),
        ("B13", "number", "108.17"),
        ("B5", "empty", ""),
        ("B14", "boolean", ""),
        ("A2", "text", ""),
    ]
    assert key.values[1].number == 3786 / 35 and key.values[4].text == "TRUE" and key.values[5].text == "Flights"
    assert key.values[0].content == "=SUM(B2:B6)" and key.values[3].content == ""
    assert key.cycle_cells == [] and key.data_sha256 == hashlib.sha256(DATA.read_bytes()).hexdigest()
    assert build_output(plain_output(key), PinnedValuesOutput) == key
    assert not list(tmp_path.iterdir())  # the answer key writes nothing


def test_correct_pin_values_cycles_in_reading_order() -> None:
    assert pinned(CIRCULAR)["cycle_cells"] == ["A1", "B1", "C1", "A2", "B2", "C2", "B3", "E4"]


@pytest.mark.parametrize(
    ("value", "text"),
    [("757.2", "757.2"), ("-12.45", "-12.45"), ("1200", "1200"), ("0.5", "0.5"), ("1/3", "1/3"),
     ("-535/12", "-535/12"), ("0", "0"), ("0.0001", "0.0001"), ("1/16", "0.0625")],
)  # fmt: skip
def test_correct_exact_text(value: str, text: str) -> None:
    from fractions import Fraction

    assert exact_text(Fraction(value)) == text


def test_correct_save_values_writes_what_it_returns(tmp_path: Path) -> None:
    made = saved(TRIP, tmp_path)
    digest = hashlib.sha256(b"B8,B12,B13,B5,B14,A2").hexdigest()[:10]
    assert made["path"] == f"values/trip-budget-{digest}.json"
    assert json.loads((tmp_path / made["path"]).read_text(encoding="utf-8")) == made
    assert build_output(made, ValuesOutput) == build_output(made, ValuesOutput)
    again = saved(TRIP, tmp_path, {"B8": {"number": 757}})
    assert again["path"] == made["path"]  # saving again replaces the file
    assert json.loads((tmp_path / made["path"]).read_text(encoding="utf-8"))["values"][0]["number"] == 757.0


def test_correct_save_values_takes_an_integer_as_a_number(tmp_path: Path) -> None:
    """A model may write 2 for 2.0: the contract builds it into a float, saved as 2.0."""
    made = saved({"workbook": "operator-precedence", "targets": ["B2"]}, tmp_path, {"B2": {"number": 4}})
    assert made["values"][0]["number"] == 4.0 and isinstance(made["values"][0]["number"], float)


SHAPES = [
    ({"B8": {"text": "757.2"}}, "text must be empty for a number"),
    ({"B5": {"number": 1.0}}, "number must be 0 unless kind is number"),
    ({"B5": {"text": "x"}}, "text must be empty for an empty cell"),
    ({"B14": {"text": "true"}}, "text must be TRUE or FALSE"),
    ({"B14": {"kind": "error", "text": "#N/A"}}, "text must be one of #DIV/0!"),
    ({"B8": {"number": float("nan")}}, "finite number"),
    ({"B8": {"number": float("inf")}}, "finite number"),
    ({"A2": {"number": 1.0}}, "number must be 0 unless kind is number"),
]


@pytest.mark.parametrize(("changes", "message"), SHAPES)
def test_malformed_save_values_refuses_a_misshapen_value(tmp_path: Path, changes: dict, message: str) -> None:
    with pytest.raises(ValueError, match=message.replace("!", "\\!").replace("(", "\\(")):
        save_values(build_output(answer(TRIP, changes), SaveValuesInput), tmp_path)
    assert not (tmp_path / "values").exists()


@pytest.mark.parametrize(
    ("values", "message"),
    [
        (lambda rows: rows[1:], "one value per target"),
        (lambda rows: [rows[1], rows[0], *rows[2:]], "in the order of targets"),
        (lambda rows: [*rows, rows[0]], "one value per target"),
        (lambda rows: [], "one value per target"),
    ],
)
def test_malformed_save_values_refuses_values_not_one_per_target(tmp_path: Path, values, message: str) -> None:
    given = answer(TRIP)
    given["values"] = values(given["values"])
    with pytest.raises(ValueError, match=message):
        save_values(build_output(given, SaveValuesInput), tmp_path)


@pytest.mark.parametrize(
    ("task", "message"),
    [
        ({"workbook": "nope", "targets": ["A1"]}, "unknown workbook 'nope'"),
        ({"workbook": "../trip-budget", "targets": ["A1"]}, "unknown workbook"),
        ({"workbook": "trip-budget", "targets": []}, "1 to 8 cell addresses, not 0"),
        ({"workbook": "trip-budget", "targets": [f"A{row}" for row in range(1, 10)]}, "1 to 8 cell addresses, not 9"),
        ({"workbook": "trip-budget", "targets": ["A0"]}, "'A0' is not a cell address"),
        ({"workbook": "trip-budget", "targets": ["A100"]}, "'A100' is not a cell address"),
        ({"workbook": "trip-budget", "targets": ["a1"]}, "'a1' is not a cell address"),
        ({"workbook": "trip-budget", "targets": ["$A$1"]}, "'\\$A\\$1' is not a cell address"),
        ({"workbook": "trip-budget", "targets": ["AA1"]}, "'AA1' is not a cell address"),
        ({"workbook": "trip-budget", "targets": ["A01"]}, "'A01' is not a cell address"),
        ({"workbook": "trip-budget", "targets": [" B8"]}, "is not a cell address"),
        ({"workbook": "trip-budget", "targets": ["B8", "B9", "B8"]}, "targets name B8 more than once"),
    ],
)
def test_malformed_tasks_are_refused_by_the_tools(tmp_path: Path, task: dict, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        pin_values(build_output(task, RecalcInput), tmp_path)
    with pytest.raises(ValueError, match=message):
        save_values(build_output(task | {"values": []}, SaveValuesInput), tmp_path)


@pytest.mark.parametrize(
    ("content", "problem"),
    [
        ("=SUM(A1:", "malformed formula"),
        ("true", "reads as a boolean"),
        ("007", "looks like a number"),
        ("+5", "looks like a number"),
        ("1e3", "looks like a number"),
        (".5", "looks like a number"),
        ("'", "empty text"),
        (" padded", "surrounding spaces"),
        ("café", "printable ASCII"),
    ],
)
def test_malformed_data_contents_are_refused(content: str, problem: str) -> None:
    assert problem in content_problem(content)


@pytest.mark.parametrize("content", ["12", "-3.5", "0.125", "TRUE", "'12", "'TRUE", "n/a", "-2^2", "=1+1"])
def test_correct_data_contents_are_accepted(content: str) -> None:
    assert content_problem(content) is None


def test_correct_readme_states_the_data_sha256() -> None:
    assert f"`{data_sha256()}`" in (ROOT / "README.md").read_text(encoding="utf-8")
