"""get_sheet: a known workbook, every non-empty cell shown exactly as the bundled data holds it, by row."""

from . import data
from .checks import result


def verify_input(value):
    problem = data.workbook_problem(value.workbook)
    return result(False, problem) if problem else result(True, "input is valid")


def verify_output(input_value, output_value, workspace):
    problem = data.workbook_problem(input_value.workbook)
    if problem:
        return result(False, problem)
    expected = data.sheet_view(input_value.workbook)
    shown = {
        "workbook": output_value.workbook,
        "title": output_value.title,
        "used_range": output_value.used_range,
        "cells": [{"cell": entry.cell, "content": entry.content} for entry in output_value.cells],
    }
    differ = sorted(key for key in expected if shown[key] != expected[key])
    if differ:
        return result(False, f"the sheet differs from the bundled data in {', '.join(differ)}", differing=differ)
    count = len(expected["cells"])
    return result(True, f"{count} cells shown as the bundled data holds them", data_sha256=data.sha256())
