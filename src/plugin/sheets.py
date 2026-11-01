"""The lookups the agent reads the bundled workbooks with: list_workbooks and get_sheet."""

from __future__ import annotations

from pathlib import Path

from contract import ListWorkbooksInput, SheetCell, SheetInput, SheetOutput, WorkbooksOutput, WorkbookSummary
from plugin.workbook import find_workbook, workbooks


def list_workbooks(given: ListWorkbooksInput, workspace: Path) -> WorkbooksOutput:
    """Every bundled workbook's id, title, used range and number of non-empty cells, by id."""
    return WorkbooksOutput(
        workbooks=[
            WorkbookSummary(id=book.id, title=book.title, used_range=book.used_range, cells=len(book.cells))
            for _id, book in sorted(workbooks().items())
        ]
    )


def get_sheet(given: SheetInput, workspace: Path) -> SheetOutput:
    """Every non-empty cell of one workbook with its content as typed, row by row, left to right."""
    book = find_workbook(given.workbook)
    return SheetOutput(
        workbook=book.id,
        title=book.title,
        used_range=book.used_range,
        cells=[SheetCell(cell=cell, content=content) for cell, content in book.cells.items()],
    )
