"""The recalc-cells verdict: 10 named checks, in order. Valid only when all hold.

Checks 8 to 10 judge each target's value against the value the verifier computes itself (sheet.py, from the
bundled file it reads itself); check 2 requires the pinned answer key to state exactly those values. The score
is the share of targets whose value is right (kind, the number within the tolerance, the text exactly, the
fields well shaped), and 0 unless the submission is this task's, saved and unchanged: checks 1 to 5 all hold.
"""

import math
from fractions import Fraction

from . import data
from .checks import check, differences, not_checked, read_saved, values_path, verdict
from .pin import answer_key, computed
from .values import TOLERANCE, described, exact_text, expected_text, is_correct, plain_values, shape_problem, shown

GATES = ("task-input", "reference", "echo", "saved", "file-matches")
MOST = 3  # problems a message names before "(+N more)"


def listed(problems):
    shown_part = "; ".join(problems[:MOST])
    return shown_part + (f" (+{len(problems) - MOST} more)" if len(problems) > MOST else "")


def saved_checks(arguments, submitted, workspace, input_ok):
    """saved and file-matches: the file save_values wrote for this task, equal to the submission."""
    if not input_ok:
        return [not_checked("saved", "task-input"), not_checked("file-matches", "task-input")]
    expected = values_path(arguments.workbook, list(arguments.targets))
    saved, problem = read_saved(workspace, submitted["path"], expected)
    entries = [check("saved", saved is not None, expected, submitted["path"], problem)]
    if saved is None:
        return entries + [not_checked("file-matches", "saved")]
    differ = differences(saved, submitted)
    message = (
        f"the saved file differs from the submission in {', '.join(differ)}: submit exactly what save_values returned"
    )
    return entries + [check("file-matches", not differ, [], differ, message)]


def targets_check(targets, cells):
    if cells == targets:
        return check("targets", True, targets, cells)
    problems = [f"{cell} is missing" for cell in targets if cell not in cells]
    problems += [f"{cell} is not a target" for cell in sorted(set(cells) - set(targets), key=data.position)]
    problems += [f"{cell} is given {cells.count(cell)} times" for cell in targets if cells.count(cell) > 1]
    if not problems:
        problems = [f"the values are in the order {cells}"]
    message = f"values must give each target once, in the order of targets {targets}: {listed(problems)}"
    return check("targets", False, targets, cells, message)


def number_problem(cell, reported, exact):
    if not math.isfinite(reported):
        return f"{cell} is {reported!r}, not a finite number; expected {shown(('number', exact))}"
    off = abs(Fraction(reported) - exact)
    allowed = TOLERANCE * max(1, abs(exact))
    if off <= allowed:
        return None
    return (
        f"{cell} is {reported!r}, expected {shown(('number', exact))}: off by {float(off):.3g}, more than the"
        f" {float(allowed):.3g} allowed"
    )


def value_checks(targets, entries, values):
    """shape, kinds, numbers and texts; and each target's entry (None when missing or repeated)."""
    shape = [problem for entry in entries if (problem := shape_problem(entry))]
    shape_entry = check("shape", not shape, [], shape, f"a value's fields do not fit its kind: {listed(shape)}")
    if values is None:
        return [shape_entry] + [not_checked(name, "task-input") for name in ("kinds", "numbers", "texts")]
    kinds, numbers, texts = [], [], []
    for target, value in zip(targets, values, strict=True):
        found = [entry for entry in entries if entry["cell"] == target]
        if len(found) != 1:
            continue
        entry = found[0]
        if entry["kind"] != value[0]:
            kinds.append(f"{target} is {entry['kind']}, expected {described(value)}")
        elif value[0] == "number":
            problem = number_problem(target, entry["number"], value[1])
            if problem:
                numbers.append(problem)
        elif entry["text"] != expected_text(value):
            texts.append(f"{target} is {entry['text']!r}, expected {expected_text(value)!r}")
    return [
        shape_entry,
        check("kinds", not kinds, [], kinds, f"a value has the wrong kind: {listed(kinds)}"),
        check("numbers", not numbers, [], numbers, f"a number is outside the tolerance: {listed(numbers)}"),
        check("texts", not texts, [], texts, f"a text, boolean or error is not exact: {listed(texts)}"),
    ]


def expected_rows(targets, values):
    rows = []
    for target, value in zip(targets, values, strict=True):
        exact = exact_text(value[1]) if value[0] == "number" else ""
        rows.append({"cell": target, "kind": value[0], "exact": exact, "text": expected_text(value)})
    return rows


def verify_task(arguments, output, reference, workspace):
    """``output``: a contract ValuesOutput; ``reference``: pin_values's PinnedValuesOutput, or None."""
    targets = list(arguments.targets)
    input_problem = data.input_problem(arguments.workbook, targets)
    found, _problem = computed(arguments)
    values = None if found is None else found[0]
    _key, key_problem = answer_key(arguments, reference)
    submitted = plain_values(output, output.path)
    entries = submitted["values"]
    asked = {"workbook": arguments.workbook, "targets": targets}
    echoed = {"workbook": output.workbook, "targets": list(output.targets)}
    checks = [
        check("task-input", input_problem is None, None, None, f"the task input is invalid: {input_problem}"),
        check("reference", key_problem is None, None, None, key_problem),
        check(
            "echo",
            echoed == asked,
            asked,
            echoed,
            "the submission's workbook and targets are not the task's, in its order",
        ),
        *saved_checks(arguments, submitted, workspace, input_problem is None),
        targets_check(targets, [entry["cell"] for entry in entries]),
        *value_checks(targets, entries, values),
    ]
    correct = 0
    if values is not None:
        for target, value in zip(targets, values, strict=True):
            found_entries = [entry for entry in entries if entry["cell"] == target]
            correct += len(found_entries) == 1 and is_correct(found_entries[0], value)
    gated = all(entry["ok"] is True for entry in checks if entry["id"] in GATES)
    score = correct / len(targets) if gated and targets else 0.0
    details = {"values_correct": f"{correct}/{len(targets)}", "tolerance": "1e-6 x max(1, |exact|)"}
    if values is not None:
        details["expected"] = expected_rows(targets, values)
    summary = ", ".join(f"{target} = {shown(value)}" for target, value in zip(targets, values or [], strict=False))
    success = f"All {len(checks)} checks hold for {arguments.workbook}: {summary}"
    return verdict(checks, success, score, **details)
