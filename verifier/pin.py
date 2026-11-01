"""pin_values, the answer key: its input is a task, and every value it states must be the one the verifier's
own engine (sheet.py) computes from the bundled file it reads itself (data.py), so a bug in the answer key fails
the verdict instead of passing a wrong answer."""

import math
import re

from . import data
from .checks import result
from .sheet import FormulaError, evaluate
from .values import described, exact_of, expected_text, shown

SHA256 = re.compile(r"[0-9a-f]{64}")


def computed(arguments):
    """(the targets' values and the circular cells, None) or (None, why they cannot be computed)."""
    problem = data.input_problem(arguments.workbook, arguments.targets)
    if problem:
        return None, f"the task input is invalid: {problem}"
    try:
        return evaluate(data.books()[arguments.workbook]["cells"], list(arguments.targets)), None
    except FormulaError as error:
        return None, f"the bundled workbook {arguments.workbook} has a formula the verifier cannot read: {error}"


def row_problem(row, content, value):
    """Why one answer-key row is not the computed value, or None."""
    if row.content != content:
        return f"{row.cell}: content {row.content!r} is not the bundled {content!r}"
    if row.kind.value != value[0]:
        return f"{row.cell} is {row.kind.value} in the answer key but {described(value)} by the verifier"
    if row.text != expected_text(value):
        return f"{row.cell}: text {row.text!r} is not {expected_text(value)!r}"
    if value[0] == "number":
        if exact_of(row.exact) != value[1] or row.number != float(value[1]):
            return f"{row.cell}: {row.exact} ({row.number!r}) is not {shown(value)}"
    elif row.exact or row.number != 0 or not math.isfinite(row.number):
        return f"{row.cell}: a {value[0]} value has number 0 and no exact number"
    return None


def answer_key(arguments, key):
    """(each target's computed value, in order, None) or (None, why there is no answer key to judge by)."""
    found, problem = computed(arguments)
    if problem:
        return None, problem
    values, circular = found
    if key is None:
        return None, "no answer key: pin_values was not pinned for this task"
    if key.workbook != arguments.workbook or list(key.targets) != list(arguments.targets):
        return None, "the answer key is for another task: its workbook or targets are not the task's"
    if not SHA256.fullmatch(key.data_sha256) or key.data_sha256 != data.sha256():
        return None, (
            f"the answer key was pinned from other data (sha256 {key.data_sha256!r}, the bundled file's is"
            f" {data.sha256()})"
        )
    if [row.cell for row in key.values] != list(arguments.targets):
        return None, "the answer key is inconsistent: it does not give one value per target, in order"
    cells = data.books()[arguments.workbook]["cells"]
    for row, value in zip(key.values, values, strict=True):
        problem = row_problem(row, cells.get(row.cell, ""), value)
        if problem:
            return None, f"the answer key is inconsistent: {problem}"
    if list(key.cycle_cells) != circular:
        return None, f"the answer key is inconsistent: its cycle cells {list(key.cycle_cells)} are not {circular}"
    return values, None


def verify_input(value):
    problem = data.input_problem(value.workbook, value.targets)
    return result(False, problem) if problem else result(True, "input is valid")


def verify_output(input_value, output_value, workspace):
    _values, problem = answer_key(input_value, output_value)
    if problem:
        return result(False, problem)
    return result(
        True, "the answer key agrees with the verifier's own evaluation", data_sha256=output_value.data_sha256
    )
