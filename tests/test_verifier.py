"""The verifier on contract instances, as NanoAgent's sandbox builds them from JSON: correct answers pass; wrong,
missing and malformed ones fail a named check (and never raise); boundary cases are judged exactly."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from helpers import CIRCULAR, ERRORS, INVOICE, PRECEDENCE, TRIP, answer, failing, judge, pinned, saved, unchecked
from helpers import verify_input as tool_input
from helpers import verify_output as tool_output
from slimconfig import build_output, plain_output

import verifier
from contract import ListWorkbooksInput, SheetInput, SheetOutput
from plugin import get_sheet, list_workbooks
from plugin.workbook import workbooks

CHECKS = ["task-input", "reference", "echo", "saved", "file-matches", "targets", "shape", "kinds", "numbers", "texts"]


# --- correct -------------------------------------------------------------------------------------------------


def test_correct_trip_values_hold_every_check(tmp_path: Path) -> None:
    verdict = judge(TRIP, saved(TRIP, tmp_path), tmp_path)
    assert verdict["valid"] is True and verdict["score"] == 1.0
    assert [entry["id"] for entry in verdict["details"]["checks"]] == CHECKS
    assert verdict["message"] == (
        "All 10 checks hold for trip-budget: B8 = 757.2, B12 = 3786/35 (= 108.17142857142858), B13 = 108.17,"
        " B5 = empty, B14 = TRUE, A2 = 'Flights'"
    )
    assert verdict["details"]["values_correct"] == "6/6"
    assert verdict["details"]["expected"][1] == {"cell": "B12", "kind": "number", "exact": "3786/35", "text": ""}


def chunks(cells: list[str]) -> list[list[str]]:
    return [cells[start : start + 8] for start in range(0, len(cells), 8)]


@pytest.mark.parametrize("book", sorted(workbooks()))
def test_correct_every_cell_of_every_workbook(tmp_path: Path, book: str) -> None:
    """The answer key's values, saved as an agent would, pass for every non-empty cell and an empty one."""
    for targets in chunks([*workbooks()[book].cells, "H30"]):
        arguments = {"workbook": book, "targets": targets}
        verdict = judge(arguments, saved(arguments, tmp_path), tmp_path)
        assert verdict["valid"] is True, verdict["message"]


def test_correct_hand_rounded_numbers_within_the_tolerance(tmp_path: Path) -> None:
    """|reported - exact| <= 1e-6 x max(1, |exact|): 1/3 as 0.333333, 3786/35 as 108.1714, 535/12 as 44.58333."""
    rounding = {"workbook": "rounding", "targets": ["A12"]}
    assert judge(rounding, saved(rounding, tmp_path, {"A12": {"number": 0.333333}}), tmp_path)["valid"] is True
    trip = saved(TRIP, tmp_path, {"B12": {"number": 108.1714}})
    assert judge(TRIP, trip, tmp_path)["valid"] is True
    interest = {"workbook": "simple-interest", "targets": ["D5", "B9"]}
    output = saved(interest, tmp_path, {"D5": {"number": 44.58333}, "B9": {"number": 1187.6905}})
    assert judge(interest, output, tmp_path)["valid"] is True


def test_correct_verdict_is_deterministic(tmp_path: Path) -> None:
    output = saved(CIRCULAR, tmp_path)
    first, second = judge(CIRCULAR, output, tmp_path), judge(CIRCULAR, output, tmp_path)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_correct_a_second_save_is_the_answer(tmp_path: Path) -> None:
    saved(TRIP, tmp_path, {"B8": {"number": 1.0}})
    assert judge(TRIP, saved(TRIP, tmp_path), tmp_path)["valid"] is True


def test_correct_tool_outputs_pass_their_checks(tmp_path: Path) -> None:
    assert tool_input("list_workbooks", {})["valid"] is True
    listed = plain_output(list_workbooks(ListWorkbooksInput(), tmp_path))
    assert tool_output("list_workbooks", {}, listed, tmp_path)["valid"] is True
    for book in workbooks():
        sheet = plain_output(get_sheet(SheetInput(workbook=book), tmp_path))
        assert tool_input("get_sheet", {"workbook": book})["valid"] is True
        assert tool_output("get_sheet", {"workbook": book}, sheet, tmp_path)["valid"] is True
        task = verifier.verify_task(
            "get-sheet", SheetInput(workbook=book), build_output(sheet, SheetOutput), None, str(tmp_path)
        )
        assert task["valid"] is True and "cells shown as the bundled data holds them" in task["message"]
    assert tool_input("save_values", answer(TRIP))["valid"] is True
    assert tool_output("save_values", answer(TRIP), saved(TRIP, tmp_path), tmp_path)["valid"] is True
    assert tool_input("pin_values", TRIP)["valid"] is True
    assert tool_output("pin_values", TRIP, pinned(TRIP), tmp_path)["valid"] is True


# --- incorrect -----------------------------------------------------------------------------------------------

WRONG = [
    # (a change to the saved values, the checks that fail, the score)
    ({"B12": {"number": 108.17}}, ["numbers"], 5 / 6),  # the rounded value for the unrounded cell
    ({"B8": {"number": 757.3}}, ["numbers"], 5 / 6),
    ({"B8": {"number": -757.2}}, ["numbers"], 5 / 6),
    ({"B5": {"kind": "number"}}, ["kinds"], 5 / 6),  # an empty cell is not the number 0
    ({"B14": {"kind": "number", "number": 1.0, "text": ""}}, ["kinds"], 5 / 6),
    ({"A2": {"text": "flights"}}, ["texts"], 5 / 6),  # text is exact, case included
    ({"B14": {"text": "FALSE"}}, ["texts"], 5 / 6),
    ({"B12": {"number": 108.17}, "A2": {"text": "Flight"}, "B14": {"text": "FALSE"}}, ["numbers", "texts"], 3 / 6),
]


@pytest.mark.parametrize(("changes", "fails", "score"), WRONG)
def test_incorrect_values_fail_their_check(tmp_path: Path, changes: dict, fails: list, score: float) -> None:
    verdict = judge(TRIP, saved(TRIP, tmp_path, changes), tmp_path)
    assert verdict["valid"] is False and failing(verdict) == fails
    assert verdict["message"].startswith(fails[0] + ": ")
    assert verdict["score"] == pytest.approx(score)


def test_incorrect_messages_name_the_cell_and_both_values(tmp_path: Path) -> None:
    verdict = judge(TRIP, saved(TRIP, tmp_path, {"B12": {"number": 108.17}}), tmp_path)
    assert verdict["message"] == (
        "numbers: a number is outside the tolerance: B12 is 108.17, expected 3786/35 (= 108.17142857142858): off by"
        " 0.00143, more than the 0.000108 allowed"
    )
    verdict = judge(TRIP, saved(TRIP, tmp_path, {"B5": {"kind": "number"}}), tmp_path)
    assert verdict["message"] == "kinds: a value has the wrong kind: B5 is number, expected empty"


def test_incorrect_first_error_and_wrong_codes(tmp_path: Path) -> None:
    changes = {"B8": {"text": "#DIV/0!"}, "B9": {"text": "#VALUE!"}}  # the right errors in the wrong cells
    verdict = judge(ERRORS, saved(ERRORS, tmp_path, changes), tmp_path)
    assert failing(verdict) == ["texts"] and verdict["score"] == pytest.approx(6 / 8)
    assert "B8 is '#DIV/0!', expected '#VALUE!'; B9 is '#VALUE!', expected '#DIV/0!'" in verdict["message"]


def test_incorrect_submission_differs_from_the_saved_file(tmp_path: Path) -> None:
    output = saved(TRIP, tmp_path)
    output["values"][0]["number"] = 757.3
    verdict = judge(TRIP, output, tmp_path)
    assert failing(verdict) == ["file-matches", "numbers"] and verdict["score"] == 0.0
    assert "differs from the submission in values" in verdict["message"]


def test_incorrect_tampered_file(tmp_path: Path) -> None:
    output = saved(TRIP, tmp_path)
    file = tmp_path / output["path"]
    file.write_text(json.dumps(output | {"targets": ["B8"]}), encoding="utf-8")
    verdict = judge(TRIP, output, tmp_path)
    assert failing(verdict) == ["file-matches"] and verdict["score"] == 0.0


def test_incorrect_values_in_the_wrong_order(tmp_path: Path) -> None:
    output = saved(TRIP, tmp_path)
    output["values"][0], output["values"][1] = output["values"][1], output["values"][0]
    verdict = judge(TRIP, output, tmp_path)
    assert failing(verdict) == ["file-matches", "targets"]
    assert "in the order of targets ['B8', 'B12', 'B13', 'B5', 'B14', 'A2']" in failing_message(verdict, "targets")


def failing_message(verdict: dict, identifier: str) -> str:
    return next(entry["message"] for entry in verdict["details"]["checks"] if entry["id"] == identifier)


def test_incorrect_extra_and_repeated_rows(tmp_path: Path) -> None:
    output = saved(TRIP, tmp_path)
    extra = output | {"values": [*output["values"], {"cell": "B9", "kind": "number", "number": 3.0, "text": ""}]}
    assert failing(judge(TRIP, extra, tmp_path)) == ["file-matches", "targets"]
    repeated = output | {"values": [*output["values"], output["values"][0]]}
    verdict = judge(TRIP, repeated, tmp_path)
    assert "B8 is given 2 times" in failing_message(verdict, "targets")


def test_incorrect_echo_of_the_task(tmp_path: Path) -> None:
    output = saved(TRIP, tmp_path) | {"workbook": "invoice"}
    assert failing(judge(TRIP, output, tmp_path)) == ["echo", "file-matches"]
    output = saved(TRIP, tmp_path) | {"targets": ["B12", "B8", "B13", "B5", "B14", "A2"]}
    assert failing(judge(TRIP, output, tmp_path))[:2] == ["echo", "file-matches"]


def test_incorrect_values_of_another_task(tmp_path: Path) -> None:
    other = {"workbook": "trip-budget", "targets": ["B8", "B12"]}
    output = saved(other, tmp_path)
    verdict = judge(TRIP, output, tmp_path)
    assert failing(verdict)[:2] == ["echo", "saved"]
    assert "where save_values saves this task's values" in failing_message(verdict, "saved")


# --- missing -------------------------------------------------------------------------------------------------


def test_missing_saved_file(tmp_path: Path) -> None:
    output = saved(TRIP, tmp_path / "elsewhere")  # saved in another workspace: none here
    verdict = judge(TRIP, output, tmp_path)
    assert failing(verdict) == ["saved"] and unchecked(verdict) == ["file-matches"]
    assert verdict["message"].startswith("saved: no file at values/trip-budget-") and verdict["score"] == 0.0


def test_missing_reference(tmp_path: Path) -> None:
    verdict = judge(TRIP, saved(TRIP, tmp_path), tmp_path, reference=None)
    assert verdict["valid"] is False and failing(verdict) == ["reference"] and verdict["score"] == 0.0
    assert verdict["message"] == "reference: no answer key: pin_values was not pinned for this task"


def test_missing_workspace(tmp_path: Path) -> None:
    output = saved(TRIP, tmp_path)
    verdict = judge(TRIP, output, tmp_path / "never-made")
    assert failing(verdict) == ["saved"] and "no file at values/" in verdict["message"]


def test_missing_a_target_row(tmp_path: Path) -> None:
    output = saved(TRIP, tmp_path)
    output["values"] = output["values"][:-1]
    verdict = judge(TRIP, output, tmp_path)
    assert failing(verdict) == ["file-matches", "targets"] and "A2 is missing" in failing_message(verdict, "targets")


def test_missing_every_value(tmp_path: Path) -> None:
    output = saved(TRIP, tmp_path) | {"values": []}
    verdict = judge(TRIP, output, tmp_path)
    assert failing(verdict) == ["file-matches", "targets"] and verdict["score"] == 0.0
    assert verdict["details"]["values_correct"] == "0/6"


# --- malformed -----------------------------------------------------------------------------------------------

REFUSED = [
    ({"workbook": "budget", "targets": ["A1"]}, "unknown workbook 'budget'"),
    ({"workbook": "", "targets": ["A1"]}, "unknown workbook ''"),
    ({"workbook": "trip-budget", "targets": []}, "1 to 8 cell addresses, not 0"),
    ({"workbook": "trip-budget", "targets": [f"B{row}" for row in range(1, 10)]}, "not 9"),
    ({"workbook": "trip-budget", "targets": ["B0"]}, "'B0' is not a cell address"),
    ({"workbook": "trip-budget", "targets": ["Z100"]}, "'Z100' is not a cell address"),
    ({"workbook": "trip-budget", "targets": ["b8"]}, "'b8' is not a cell address"),
    ({"workbook": "trip-budget", "targets": ["B8:B9"]}, "'B8:B9' is not a cell address"),
    ({"workbook": "trip-budget", "targets": ["$B$8"]}, "is not a cell address"),
    ({"workbook": "trip-budget", "targets": ["B8", "B8"]}, "targets name B8 more than once"),
]


@pytest.mark.parametrize(("arguments", "message"), REFUSED)
def test_malformed_task_inputs_are_refused_before_any_agent(arguments: dict, message: str) -> None:
    """verify_input on pin_values refuses them, so the task never starts; the answer key refuses them too."""
    verdict = tool_input("pin_values", arguments)
    assert verdict["valid"] is False and message in verdict["message"]
    assert tool_input("save_values", arguments | {"values": []})["valid"] is False
    with pytest.raises(ValueError):
        pinned(arguments)


def test_malformed_task_input_reaches_verify_task_without_raising(tmp_path: Path) -> None:
    arguments = {"workbook": "../trip-budget", "targets": ["B8", "B8"]}
    output = {"workbook": "../trip-budget", "targets": ["B8", "B8"], "values": [], "path": "values/x.json"}
    verdict = judge(arguments, output, tmp_path, reference=None)
    assert failing(verdict) == ["task-input", "reference", "targets"] and verdict["score"] == 0.0
    assert unchecked(verdict) == ["saved", "file-matches", "kinds", "numbers", "texts"]


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"B8": {"text": "757.2"}}, "text must be empty for a number"),
        ({"B5": {"number": 2.0}}, "number must be 0 unless kind is number"),
        ({"B14": {"text": "yes"}}, "text must be TRUE or FALSE"),
        ({"B14": {"kind": "error", "text": "#REF!"}}, "text must be one of"),
        ({"B8": {"number": math.nan}}, "finite number"),
    ],
)
def test_malformed_save_values_inputs_are_refused(changes: dict, message: str) -> None:
    verdict = tool_input("save_values", answer(TRIP, changes))
    assert verdict["valid"] is False and message in verdict["message"]


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_malformed_non_finite_numbers_fail_without_raising(tmp_path: Path, value: float) -> None:
    output = saved(TRIP, tmp_path)
    output["values"][0]["number"] = value
    verdict = judge(TRIP, output, tmp_path)
    assert failing(verdict) == ["file-matches", "shape", "numbers"]
    json.dumps(verdict, allow_nan=False)  # the verdict is plain JSON, no NaN


def test_malformed_shape_fails_even_when_kind_and_value_hold(tmp_path: Path) -> None:
    output = saved(TRIP, tmp_path)
    output["values"][3]["number"] = 5.0  # B5 is empty: kind right, but its number must be 0
    (tmp_path / output["path"]).write_text(json.dumps(output), encoding="utf-8")
    verdict = judge(TRIP, output, tmp_path)
    assert failing(verdict) == ["shape"] and verdict["score"] == pytest.approx(5 / 6)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("not json", "is not UTF-8 JSON"),
        ("[1, 2]", "holds no JSON object"),
        ("[" * 12_000 + "]" * 12_000, "nests too deeply"),
        ("x" * 70_000, "more than any saved values file"),
    ],
)
def test_malformed_saved_files(tmp_path: Path, content: str, message: str) -> None:
    output = saved(TRIP, tmp_path)
    (tmp_path / output["path"]).write_text(content, encoding="utf-8")
    verdict = judge(TRIP, output, tmp_path)
    assert failing(verdict) == ["saved"] and message in verdict["message"]


def test_malformed_saved_file_not_utf8_a_folder_or_a_link_out(tmp_path: Path) -> None:
    output = saved(TRIP, tmp_path)
    file = tmp_path / output["path"]
    file.write_bytes(b"\xff\xfe{")
    assert "is not UTF-8 JSON" in judge(TRIP, output, tmp_path)["message"]
    file.unlink()
    file.mkdir()
    assert "no file at" in judge(TRIP, output, tmp_path)["message"]
    file.rmdir()
    outside = tmp_path.parent / "outside.json"
    outside.write_text(json.dumps(output), encoding="utf-8")
    file.symlink_to(outside)
    assert "leads outside the workspace" in judge(TRIP, output, tmp_path)["message"]


@pytest.mark.parametrize("path", ["../outside.json", "/etc/passwd", "", "values/../../x.json", "answer.json"])
def test_malformed_paths_never_leave_the_workspace(tmp_path: Path, path: str) -> None:
    verdict = judge(TRIP, saved(TRIP, tmp_path) | {"path": path}, tmp_path)
    assert failing(verdict)[:1] == ["saved"] and verdict["valid"] is False and verdict["score"] == 0.0


def tampered(arguments: dict, cell_index: int, **fields) -> dict:
    key = pinned(arguments)
    key["values"][cell_index].update(fields)
    return key


@pytest.mark.parametrize(
    ("key", "message"),
    [
        (tampered(TRIP, 1, exact="108.17"), "B12: 108.17"),
        (tampered(TRIP, 1, number=108.17), "B12: 3786/35 (108.17)"),
        (tampered(TRIP, 3, kind="number"), "B5 is number in the answer key but empty"),
        (tampered(TRIP, 5, text="flights"), "A2: text 'flights' is not 'Flights'"),
        (tampered(TRIP, 4, text="FALSE"), "B14: text 'FALSE' is not 'TRUE'"),
        (tampered(TRIP, 0, content="=SUM(B2:B5)"), "B8: content '=SUM(B2:B5)' is not the bundled"),
        (tampered(TRIP, 0, exact="abc"), "B8: abc (757.2) is not 757.2"),
        (tampered(TRIP, 3, exact="0"), "B5: a empty value has number 0 and no exact number"),
        (pinned(TRIP) | {"cycle_cells": ["B8"]}, "its cycle cells ['B8'] are not []"),
        (pinned(TRIP) | {"data_sha256": "0" * 64}, "pinned from other data"),
        (pinned(TRIP) | {"targets": ["B8"]}, "for another task"),
        (pinned(TRIP) | {"values": pinned(TRIP)["values"][:-1]}, "does not give one value per target"),
        (pinned(CIRCULAR) | {"cycle_cells": ["A1", "A2"]}, "its cycle cells ['A1', 'A2'] are not"),
    ],
)
def test_malformed_reference_is_caught_by_rederiving_it(tmp_path: Path, key: dict, message: str) -> None:
    """A wrong answer key is never trusted: the verifier's own engine re-derives every value it states."""
    arguments = CIRCULAR if key["workbook"] == "circular-refs" else TRIP
    verdict = judge(arguments, saved(arguments, tmp_path), tmp_path, reference=key)
    assert failing(verdict) == ["reference"] and message in verdict["message"] and verdict["score"] == 0.0
    assert tool_output("pin_values", arguments, key, tmp_path)["valid"] is False


def test_malformed_tool_outputs_are_refused(tmp_path: Path) -> None:
    listed = plain_output(list_workbooks(ListWorkbooksInput(), tmp_path))
    listed["workbooks"][0]["cells"] += 1
    assert tool_output("list_workbooks", {}, listed, tmp_path)["valid"] is False
    sheet = plain_output(get_sheet(SheetInput(workbook="invoice"), tmp_path))
    sheet["cells"][5]["content"] = "=B2*C2+1"
    verdict = tool_output("get_sheet", {"workbook": "invoice"}, sheet, tmp_path)
    assert verdict["valid"] is False and "differs from the bundled data in cells" in verdict["message"]
    output = saved(TRIP, tmp_path)
    (tmp_path / output["path"]).write_text("{}", encoding="utf-8")
    assert tool_output("save_values", answer(TRIP), output, tmp_path)["valid"] is False
    changed = saved(TRIP, tmp_path) | {"path": "values/elsewhere.json"}
    assert tool_output("save_values", answer(TRIP), changed, tmp_path)["valid"] is False
    other = saved(TRIP, tmp_path)
    other["values"][0]["number"] = 1.0
    assert "differ from the ones given" in tool_output("save_values", answer(TRIP), other, tmp_path)["message"]


# --- boundary ------------------------------------------------------------------------------------------------

BOUNDARY = [
    # (task, a change to the right values or None, the checks that fail): every rule the task states
    (PRECEDENCE, None, []),  # -2^2 = 4, 2^3^2 = 64, 2^-1 = 0.5, 1<2<3 FALSE, 2^0.5 #NUM!
    (PRECEDENCE, {"B2": {"number": -4.0}}, ["numbers"]),  # -(2^2): unary minus binds tighter in this sheet
    (PRECEDENCE, {"B3": {"number": 512.0}}, ["numbers"]),  # 2^(3^2): ^ groups left to right
    (PRECEDENCE, {"B14": {"text": "TRUE"}}, ["texts"]),  # TRUE < 3 is FALSE: booleans sort above numbers
    (PRECEDENCE, {"B15": {"kind": "number", "number": 1.4142135624, "text": ""}}, ["kinds"]),  # whole exponents
    ({"workbook": "rounding", "targets": ["B3", "B4", "B6", "B9", "B10"]}, None, []),
    ({"workbook": "rounding", "targets": ["B3"]}, {"B3": {"number": -2.0}}, ["numbers"]),  # half away from zero
    ({"workbook": "rounding", "targets": ["B9"]}, {"B9": {"number": 2.34}}, ["numbers"]),  # 2.345 is a true half
    ({"workbook": "rounding", "targets": ["B10"]}, {"B10": {"number": -7.0}}, ["numbers"]),  # digits -1.7 is -1
    ({"workbook": "rounding", "targets": ["B11", "A11"]}, None, []),  # an empty cell is 0 in ROUND, empty itself
    ({"workbook": "rounding", "targets": ["A11"]}, {"A11": {"kind": "number"}}, ["kinds"]),
    ({"workbook": "rounding", "targets": ["A12"]}, {"A12": {"number": 0.333}}, ["numbers"]),  # outside 1e-6
    ({"workbook": "rounding", "targets": ["B15"]}, None, []),  # SUM meets #VALUE! in its range
    ({"workbook": "simple-interest", "targets": ["B9"]}, {"B9": {"number": 1187.692}}, ["numbers"]),
    ({"workbook": "simple-interest", "targets": ["B10"]}, None, []),  # (1.035)^(1/12) is #NUM!
    ({"workbook": "trip-budget", "targets": ["B15", "B9", "B10"]}, None, []),  # empty as 0; ranges skip text
    ({"workbook": "inventory-reorder", "targets": ["D4", "D5", "B8", "B11"]}, None, []),
    ({"workbook": "inventory-reorder", "targets": ["D5"]}, {"D5": {"text": "REORDER"}}, ["texts"]),  # text > 10
    ({"workbook": "text-and-booleans", "targets": ["B1", "B3", "B5", "B9", "B13", "B14", "B19", "B23"]}, None, []),
    ({"workbook": "text-and-booleans", "targets": ["B13"]}, {"B13": {"number": 8.0}}, ["numbers"]),
    ({"workbook": "text-and-booleans", "targets": ["B23"]}, {"B23": {"kind": "empty", "number": 0.0}}, ["kinds"]),
    ({"workbook": "text-and-booleans", "targets": ["B19"]}, {"B19": {"text": 'say ""hi""'}}, ["texts"]),
    (ERRORS, None, []),  # first error; lazy IF; missing else; AVERAGE of text; #NAME? caught; Rate; SUM's first error
    ({"workbook": "error-showcase", "targets": ["B13"]}, {"B13": {"text": "#VALUE!"}}, ["texts"]),
    ({"workbook": "error-showcase", "targets": ["B11"]}, {"B11": {"text": "#DIV/0!", "kind": "error"}}, ["kinds"]),
    (CIRCULAR, None, []),  # 2- and 3-cell cycles, a self-reference, a mention vs IFERROR, a branch not taken
    (CIRCULAR, {"C2": {"kind": "number", "number": 5.0, "text": ""}}, ["kinds"]),  # the cycle is static
    (CIRCULAR, {"D3": {"kind": "error", "number": 0.0, "text": "#CIRC!"}}, ["kinds"]),  # D3 is on no cycle
    ({"workbook": "gradebook", "targets": ["D2", "E2", "D4", "E5", "D7", "B8", "D9"]}, None, []),
    ({"workbook": "gradebook", "targets": ["D9"]}, {"D9": {"number": 90.67}}, ["numbers"]),
    (INVOICE, None, []),
    ({"workbook": "invoice", "targets": ["H30"]}, None, []),  # a cell outside the used range is empty
]


@pytest.mark.parametrize(("arguments", "changes", "fails"), BOUNDARY)
def test_boundary_rules_are_judged_exactly(tmp_path: Path, arguments: dict, changes: dict | None, fails: list) -> None:
    verdict = judge(arguments, saved(arguments, tmp_path, changes), tmp_path)
    assert failing(verdict) == fails, verdict["message"]
    assert verdict["valid"] is (not fails)


def test_boundary_one_target_and_eight_targets(tmp_path: Path) -> None:
    one = {"workbook": "invoice", "targets": ["D12"]}
    assert judge(one, saved(one, tmp_path), tmp_path)["score"] == 1.0
    eight = {"workbook": "invoice", "targets": ["D2", "D3", "D4", "D6", "D7", "D8", "D10", "D11"]}
    assert len(eight["targets"]) == 8 and judge(eight, saved(eight, tmp_path), tmp_path)["valid"] is True


def test_boundary_tolerance_edges(tmp_path: Path) -> None:
    """At |exact| <= 1 the tolerance is 1e-6 absolute; above, 1e-6 relative."""
    half = {"workbook": "operator-precedence", "targets": ["B10"]}  # exactly 0.5
    assert failing(judge(half, saved(half, tmp_path, {"B10": {"number": 0.5 + 0.9e-6}}), tmp_path)) == []
    assert failing(judge(half, saved(half, tmp_path, {"B10": {"number": 0.5 + 1.1e-6}}), tmp_path)) == ["numbers"]
    big = {"workbook": "simple-interest", "targets": ["C6"]}  # exactly 1175
    assert failing(judge(big, saved(big, tmp_path, {"C6": {"number": 1175.00117}}), tmp_path)) == []
    assert failing(judge(big, saved(big, tmp_path, {"C6": {"number": 1175.0012}}), tmp_path)) == ["numbers"]
