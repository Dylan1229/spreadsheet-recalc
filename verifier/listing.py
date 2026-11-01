"""list_workbooks: it takes nothing, and must list every bundled workbook as the data holds it."""

from . import data
from .checks import result


def verify_input(value):
    return result(True, "list_workbooks takes nothing")


def verify_output(input_value, output_value, workspace):
    listed = [
        {"id": book.id, "title": book.title, "used_range": book.used_range, "cells": book.cells}
        for book in output_value.workbooks
    ]
    if listed != data.listing():
        return result(False, "the workbooks listed differ from the bundled data")
    return result(True, f"{len(listed)} workbooks listed as the bundled data holds them", data_sha256=data.sha256())
