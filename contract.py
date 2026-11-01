"""Each tool's and task's typed input and output (see nanoagent.plugin.v0001.contract): declarations only."""

from dataclasses import dataclass
from enum import Enum
from typing import Annotated

from slimconfig import Output


class Tool(Enum):
    LIST_WORKBOOKS = "list_workbooks"
    GET_SHEET = "get_sheet"
    SAVE_VALUES = "save_values"
    PIN_VALUES = "pin_values"


class Task(Enum):
    RECALC_CELLS = "recalc-cells"
    GET_SHEET = "get-sheet"


class Kind(Enum):
    NUMBER = "number"
    TEXT = "text"
    BOOLEAN = "boolean"
    EMPTY = "empty"
    ERROR = "error"


WORKBOOK = "The workbook id, as list_workbooks gives it, e.g. trip-budget"
TARGETS = (
    "1 to 8 different cell addresses whose values are asked for, each a column letter A-Z and a row 1-99 with no"
    " leading zero and no $, e.g. B12"
)
USED_RANGE = "The smallest rectangle holding every non-empty cell, e.g. A1:D16"
CONTENT = (
    "The cell's content as typed: = starts a formula; a leading ' marks text ('12 is the text 12, the ' not part of"
    " it); TRUE and FALSE are booleans; a decimal such as 12, -3.5 or 0.125 is a number; anything else is text"
)
VALUES = "One value per target, in the order of targets"
KIND = "The value's kind: number, text, boolean, empty (a cell with no content) or error"
NUMBER = "The number when kind is number (at least 8 significant figures); 0 for every other kind"
TEXT = (
    "The text when kind is text, exactly, case as computed; TRUE or FALSE when kind is boolean; the code when kind"
    " is error (#DIV/0!, #VALUE!, #NAME?, #NUM! or #CIRC!); empty for number and empty"
)
VALUES_PATH = "The saved file, values/<workbook>-<first 10 hex digits of sha256 of the targets joined by ','>.json"


@dataclass
class ListWorkbooksInput(Output):
    """list_workbooks takes nothing."""


@dataclass
class WorkbookSummary(Output):
    id: Annotated[str, "The workbook id"]
    title: Annotated[str, "Its title"]
    used_range: Annotated[str, USED_RANGE]
    cells: Annotated[int, "How many non-empty cells it has"]


@dataclass
class WorkbooksOutput(Output):
    workbooks: Annotated[list[WorkbookSummary], "Every bundled workbook (all fictional), by id"]


@dataclass
class SheetInput(Output):
    workbook: Annotated[str, WORKBOOK]


@dataclass
class SheetCell(Output):
    cell: Annotated[str, "The cell's address, e.g. B12"]
    content: Annotated[str, CONTENT]


@dataclass
class SheetOutput(Output):
    workbook: Annotated[str, WORKBOOK]
    title: Annotated[str, "The workbook's title"]
    used_range: Annotated[str, USED_RANGE]
    cells: Annotated[list[SheetCell], "Every non-empty cell, row by row, left to right; a cell not listed is empty"]


@dataclass
class RecalcInput(Output):
    workbook: Annotated[str, WORKBOOK]
    targets: Annotated[list[str], TARGETS]


@dataclass
class CellValue(Output):
    cell: Annotated[str, "The target's address, as in targets"]
    kind: Annotated[Kind, KIND]
    number: Annotated[float, NUMBER]
    text: Annotated[str, TEXT]


@dataclass
class SaveValuesInput(Output):
    workbook: Annotated[str, "The task's workbook, exactly as given"]
    targets: Annotated[list[str], "The task's targets, exactly as given, in its order"]
    values: Annotated[list[CellValue], VALUES]


@dataclass
class ValuesOutput(Output):
    workbook: Annotated[str, "The task's workbook"]
    targets: Annotated[list[str], "The task's targets, in its order"]
    values: Annotated[list[CellValue], VALUES]
    path: Annotated[str, VALUES_PATH]


@dataclass
class PinnedValue(Output):
    cell: Annotated[str, "The target's address"]
    content: Annotated[str, "The target's content as typed; empty for an empty cell"]
    kind: Annotated[Kind, KIND]
    number: Annotated[float, "The number as a float when kind is number; 0 otherwise"]
    text: Annotated[str, TEXT]
    exact: Annotated[
        str, "The exact number when kind is number: a terminating decimal (-12.45) or else a fraction p/q (1/3)"
    ]


@dataclass
class PinnedValuesOutput(Output):
    workbook: Annotated[str, WORKBOOK]
    targets: Annotated[list[str], "The task's targets, in its order"]
    values: Annotated[list[PinnedValue], "The correct value of each target, in the order of targets"]
    cycle_cells: Annotated[
        list[str],
        "Every cell of the workbook on a circular reference (it can reach itself by following the references its"
        " formula mentions), row by row, left to right",
    ]
    data_sha256: Annotated[str, "The sha256 of the bundled workbooks.json the values were computed from"]


TOOLS = {
    Tool.LIST_WORKBOOKS: (ListWorkbooksInput, WorkbooksOutput),
    Tool.GET_SHEET: (SheetInput, SheetOutput),
    Tool.SAVE_VALUES: (SaveValuesInput, ValuesOutput),
    Tool.PIN_VALUES: (RecalcInput, PinnedValuesOutput),
}
TASKS = {
    Task.RECALC_CELLS: (RecalcInput, ValuesOutput),
    Task.GET_SHEET: (SheetInput, SheetOutput),
}
