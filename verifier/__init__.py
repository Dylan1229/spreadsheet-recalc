"""The deterministic verifier: each tool's checks live in its own module, on contract instances."""

from contract import Task, Tool

from . import listing, lookup, pin, save, task

TOOLS = {
    Tool.LIST_WORKBOOKS: listing,
    Tool.GET_SHEET: lookup,
    Tool.SAVE_VALUES: save,
    Tool.PIN_VALUES: pin,
}


def _tool_output(module):
    """A tool task's check: its output judged as its one tool's verify_output judges it."""
    return lambda arguments, output, reference, workspace: module.verify_output(arguments, output, workspace)


# task -> its output's check, verify_task(arguments, output, reference, workspace)
TASKS = {
    Task.RECALC_CELLS: task.verify_task,
    Task.GET_SHEET: _tool_output(lookup),
}


def verify_input(tool, value):
    return TOOLS[Tool(tool)].verify_input(value)


def verify_output(tool, input_value, output_value, workspace):
    return TOOLS[Tool(tool)].verify_output(input_value, output_value, workspace)


def verify_task(task, arguments, output, reference, workspace):
    return TASKS[Task(task)](arguments, output, reference, workspace)
