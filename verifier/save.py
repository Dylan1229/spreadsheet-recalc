"""save_values: well-shaped values for a valid task, and a file that holds exactly what the tool returned."""

from . import data
from .checks import differences, read_saved, result, values_path
from .values import plain_values, shape_problem


def input_problem(value):
    """Why a SaveValuesInput is not a well-shaped answer to a valid task, or None. Its values are not judged."""
    problem = data.input_problem(value.workbook, value.targets)
    if problem:
        return problem
    given = plain_values(value)
    cells = [entry["cell"] for entry in given["values"]]
    if cells != given["targets"]:
        return f"values must give one value per target, in the order of targets {given['targets']}, not {cells}"
    for entry in given["values"]:
        problem = shape_problem(entry)
        if problem:
            return problem
    return None


def verify_input(value):
    problem = input_problem(value)
    return result(False, problem) if problem else result(True, "input is valid")


def verify_output(input_value, output_value, workspace):
    problem = input_problem(input_value)
    if problem:
        return result(False, problem)
    if plain_values(output_value) != plain_values(input_value):
        return result(False, "the returned workbook, targets or values differ from the ones given")
    expected = values_path(input_value.workbook, input_value.targets)
    saved, problem = read_saved(workspace, output_value.path, expected)
    if problem:
        return result(False, problem)
    differ = differences(saved, plain_values(output_value, output_value.path))
    if differ:
        return result(False, f"{expected} does not hold what save_values returned: it differs in {', '.join(differ)}")
    return result(True, f"the values are saved in {expected}", path=expected)
