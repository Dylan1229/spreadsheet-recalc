# Spreadsheet Recalc

A `nanoagent.plugin/v0001` plugin with the structure of NanoAgent's reference plugin,
[arxiv-source](https://github.com/zeyuyang8/arxiv-source). Its task, `recalc-cells`, gives an agent one of ten
small bundled spreadsheets and up to eight cell addresses. The agent reads the sheet, works out each target's
value by hand under precisely stated evaluation rules (modelled on Excel, simplified where noted), saves the
values and submits them. Each value is a number, a text, a boolean, an empty cell or an error code, and the
answer is unique. The answer key evaluates the sheet with exact fractions; the verifier evaluates it again with
an engine of its own (its own tokenizer, parser and evaluator, sharing no code with `src/`) and judges every value
with ten named checks. Everything runs offline; every workbook is invented.

## Tools

| Tool | Does | Code |
|---|---|---|
| `list_workbooks` | Lists the bundled workbooks: id, title, used range and number of non-empty cells | `src/plugin/sheets.py` |
| `get_sheet` | One workbook's non-empty cells as `{cell, content}`, row by row, left to right, contents as typed | `src/plugin/sheets.py` |
| `save_values` | Writes the agent's values to `values/<workbook>-<digest>.json` (saving again replaces it) and returns them with that `path`. It checks only their shape and computes nothing | `src/plugin/save.py` |
| `pin_values` | The answer key, never an agent's tool: each target's exact value, the workbook's cycle cells and the sha256 of the data | `src/plugin/pin.py` (engine: `src/plugin/recalc.py`, `src/plugin/formula.py`) |

### Tasks

| Task | Does | Runner |
|---|---|---|
| `recalc-cells` | Computes the values of 1 to 8 cells of a bundled workbook under the stated rules | `agent`, with `list_workbooks`, `get_sheet` and `save_values`; reference `pin_values` |
| `get-sheet` | Shows every non-empty cell of a workbook with its content (for chat) | `tool` (`get_sheet`), judged as that tool's output |

## The task

**Input** (`RecalcInput`): `workbook` (an id from `list_workbooks`, e.g. `trip-budget`) and `targets`, 1 to 8
different cell addresses of A1:Z99 (a column letter A-Z, a row 1-99 with no leading zero, no `$`, upper case).
Before the agent starts, NanoAgent runs `pin_values` on the input in a scratch workspace; `verify_input` refuses an
unknown workbook, a malformed or out-of-range address, a repeated target and 0 or more than 8 targets, so a
malformed task never reaches an agent. Example: `{"workbook": "trip-budget", "targets": ["B8", "B12", "B13",
"B5", "B14", "A2"]}`.

**Output** (`ValuesOutput`, exactly what `save_values` returns): `workbook` and `targets` echoed; `values`, one
`{cell, kind, number, text}` per target in target order; and `path`, the saved file. `kind` is `number`, `text`,
`boolean`, `empty` or `error`; `number` is the value for a number and 0 otherwise; `text` is the text for a text,
`TRUE` or `FALSE` for a boolean, the code for an error, and `""` for a number or an empty cell. For the example:
`757.2`, `108.1714286` (exactly 3786/35), `108.17`, empty, `TRUE`, `"Flights"`, saved in
`values/trip-budget-0f82f93cfc.json` (the digest is the first 10 hex digits of the sha256 of the targets joined by
`,`).

**The plan** the instructions prescribe fits RUSH Lab's limits for agent runs (6 model turns, 2,048 tokens per
reply, reasoning included): turn 1 `get_sheet`; turn 2 evaluate the targets (one short line per cell) and call
`save_values`; turn 3 `submit` exactly what `save_values` returned; three turns spare to fix a refused save.
`get_sheet` returns at most 1,400 characters of JSON (30 cells), and the submission for 8 targets is about 600
characters. Every workbook is small enough that any 8 targets are a few lines of hand arithmetic each.

**Success**: the verdict is valid only when all 10 checks below hold. The score is the share of targets whose
value is right, and 0 unless the submission is this task's, saved and unchanged (checks 1 to 5 hold).

## Rules

Every rule below is stated in the task's instructions; the examples are cells of the bundled workbooks.

**Contents.** A content starting with `=` is a formula. A leading `'` marks text and is not part of it (`'12` is
the text `12`, as in Excel). `TRUE` and `FALSE` are booleans. A plain decimal (`12`, `-3.5`, `0.125`; no exponent,
no leading `+`, no leading zero) is a number. Anything else is text. A cell not listed is empty.

**Values.** A cell's value is a number (exact: `fractions.Fraction`), a text, a boolean, empty, or an error:
`#DIV/0!`, `#VALUE!`, `#NAME?`, `#NUM!` or `#CIRC!`. A formula's value is its result, except that a result that
is an empty cell gives the number 0, as Excel shows it: `=A8` with A8 empty is 0 (text-and-booleans B23). Only a
cell with no content is `empty`.

**Grammar** (the text after `=`; spaces between tokens are ignored; names, functions and cell references are
case-insensitive):

```text
expression := comparison
comparison := additive (("=" | "<>" | "<" | "<=" | ">" | ">=") additive)*
additive   := multiplicative (("+" | "-") multiplicative)*
multiplicative := power (("*" | "/") power)*
power      := unary ("^" unary)*
unary      := ("-" | "+") unary | primary
primary    := NUMBER | STRING | NAME "(" [argument ("," argument)*] ")" | NAME | "(" expression ")"
argument   := CELL ":" CELL | expression        (a range only as a whole function argument)
NUMBER     := digits ["." digits]                (a sign is the unary operator; no exponent)
STRING     := '"' (any character but '"', or '""' for a quote) '"'
NAME       := letter (letter | digit | "_" | ".")*
```

A bare NAME is `TRUE` or `FALSE`, a cell reference `A1` to `Z99`, or else an unknown name (`#NAME?`). There is no
`&`, `%`, `$` or array syntax. A range's corners may come in either order; its cells are read by row, then column.

**Operators**, highest precedence first: unary `-` and `+`; `^`; `*` and `/`; `+` and `-`; the comparisons. Every
binary operator groups left to right. So `-2^2` = `(-2)^2` = 4 and `0-2^2` = -4, `2^3^2` = `(2^3)^2` = 64,
`2^-1` = 0.5, `10-4-3` = 3, `12/4/3` = 1, and `1<2<3` = `(1<2)<3` = `TRUE<3` = FALSE (operator-precedence B2 to B14).

**Arithmetic** (`+ - * / ^` and unary `-` `+`) coerces each operand: empty is 0, `TRUE` 1, `FALSE` 0, a number
stays, and any text is `#VALUE!`, even numeric-looking text (`=A4*2` with A4 holding `'12` is `#VALUE!`). `TRUE+TRUE` = 2. Division by
0 is `#DIV/0!`. In `x^y` the exponent must be a whole number, else `#NUM!` (`2^0.5`, `(1+B2)^(1/12)`); then `0^0`
is `#NUM!` and 0 to a negative power `#DIV/0!`.

**Comparisons** give `TRUE` or `FALSE`. Numbers compare by value; texts ignoring case (`"Apple"="APPLE"`,
`"banana">"Apple"`; by their lower-case forms, character by character in code-point order);
`FALSE < TRUE`; across kinds `number < text < boolean` (`7<"Apple"`, `"Apple"<TRUE`). An empty operand takes the
other side's zero: 0 against a number, `""` against a text, `FALSE` against a boolean; two empties are equal.

**Errors** propagate. Operands and arguments are evaluated left to right, each coerced as it is evaluated, and the
first error met (an error value or a coercion that fails) is the result: `="abc"+10/0` is `#VALUE!` and
`=10/0+"abc"` is `#DIV/0!` (error-showcase B8, B9); `=SUM(A1,B5,B1)` meets B5's `#NUM!` before B1's `#DIV/0!`
(B22). Only an IF branch not taken and IFERROR escape this.

**Functions.** Any other function name gives `#NAME?` (`SQRT`), as does a bare unknown name (`Rate`). A wrong
number of arguments gives `#VALUE!`, checked before any argument is evaluated (`ROUND(A1)`).

| Function | Rule |
|---|---|
| `SUM`, `AVERAGE`, `MIN`, `MAX`, `COUNT` (1 or more arguments) | An argument that is a range or a cell reference (parentheses around it change nothing) counts only the numbers in its cells; text, booleans and empty cells there are skipped, an error there is the result. Any other argument (a literal or an expression) is coerced like an operand and counts. `AVERAGE` of no numbers is `#DIV/0!`, `MIN`/`MAX` of no numbers 0, `COUNT` counts the numbers. `SUM(A4,A5,A7)` with `TRUE`, `FALSE`, 7 is 7; `SUM(TRUE,FALSE,A7)` is 8 |
| `ROUND(x, digits)` | Half away from zero. `digits` is truncated toward zero to a whole number and may be negative: `ROUND(2.5,0)` = 3, `ROUND(-2.5,0)` = -3, `ROUND(1234.5,-2)` = 1200, `ROUND(2.345,2.9)` = 2.35 (2.345 is an exact decimal, so a true half) |
| `ABS(x)` | The absolute value of `x` coerced to a number |
| `AND(...)`, `OR(...)` (1 or more), `NOT(x)` | Each argument becomes a boolean: a number is TRUE unless 0, empty is FALSE, text is `#VALUE!`. Every argument is evaluated: `AND(FALSE,1/0)` is `#DIV/0!` |
| `IF(cond, then[, else])` | `cond` becomes a boolean as for `AND`; only the chosen branch is evaluated (`IF(A2=0,"n/a",A1/A2)` is `"n/a"`); with no else a false cond gives `FALSE` |
| `IFERROR(value, alternative)` | `alternative` (evaluated only then) if `value` is an error, else `value` |

A range anywhere but as an argument of the five aggregates is `#VALUE!` (`ABS(A1:A2)`, `AND(A1:A2)`).

**Circular references** are decided before anything is evaluated, so no value depends on evaluation order. Each
formula cell points at every cell its formula mentions, ranges expanded, both IF branches and IFERROR's arguments
included. Every cell of a strongly connected component of more than one cell, and every cell that points at
itself, is `#CIRC!` without being evaluated: a 2-cell cycle (circular-refs A1, A2), a 3-cell cycle (B1 to B3), a
self-reference (C1), a self-reference in an IF branch never taken (C2), a total whose range holds itself (E4).
Every other cell evaluates normally: one that mentions a cycle cell gets `#CIRC!` like any error (D1), which
IFERROR catches (D2 = -1); one that mentions a cycle cell only in a branch not taken is fine (D3 = 7).

**Reporting and tolerance.** The agent reports numbers as decimals it worked out by hand. A reported number passes
when `|reported - exact| <= 1e-6 x max(1, |exact|)`: 1/3 as `0.333333` passes, `0.333` does not; 1175 accepts
1175.00117 but not 1175.0012. Texts must match exactly, case included; booleans and error codes exactly; an empty
cell is its own kind, not the number 0.

### Where this differs from Excel

These rules are the definition; where Excel differs or is unclear, this plugin chose:

- `x^y` with a non-whole exponent is `#NUM!` (Excel computes `4^0.5` = 2).
- Unary `+` coerces like unary `-` (Excel's `=+"a"` is `"a"`; here `#VALUE!`).
- `COUNT` coerces literal arguments and propagates errors (Excel's `COUNT("a", 1/0)` is 0; here `#VALUE!`).
- `AND`, `OR` and `NOT` coerce references too (Excel skips text and empty cells in a referenced cell or range and
  accepts ranges); a range there is `#VALUE!`.
- The order of operand evaluation and coercion is fixed (left to right, each coerced at once), so the first error
  is well defined.
- Circular references are static and give `#CIRC!`, which is not an Excel error code (Excel warns and keeps the
  last value).
- Arithmetic is exact (no 15-digit floating point): `ROUND(2.345,2)` is 2.35, and `0.1+0.2=0.3` is TRUE.
- Text comparison is by lower-case code point, not Excel's locale collation (the data compares letters only).

## Data

`src/plugin/data/workbooks.json`: ten fictional single-sheet workbooks, written by hand for this plugin, each with
at most 30 non-empty cells in A1:H30 (280 cells in all, 140 of them formulas). Every name, price and score is
invented.

| Workbook | What it exercises |
|---|---|
| `trip-budget` | SUM/COUNT/AVERAGE over a range with text and an empty cell, a repeating quotient (757.2/7), ROUND, empty as 0 |
| `invoice` | Line totals, a conditional discount `-ROUND(...)`, tax rounding, a text result |
| `inventory-reorder` | IF on comparisons with an empty cell and with text against a number, MIN, AND |
| `simple-interest` | Repeating decimals (535/12), a whole-number power, a non-whole power (`#NUM!`) |
| `operator-precedence` | `-2^2`, `2^3^2`, `2^-1`, `1<2<3` and other precedence cases, each beside its formula as text |
| `rounding` | Half away from zero, negative and fractional digits, an empty cell, `'2.5` text, an error inside a SUM range |
| `error-showcase` | Every error code, first-error order, lazy IF, IFERROR, AVERAGE of text, wrong argument counts, unknown names |
| `circular-refs` | 2- and 3-cell cycles, self-references, a cell mentioning a cycle with and without IFERROR |
| `text-and-booleans` | Case-insensitive comparison, cross-kind order, empty comparisons, TRUE+TRUE, references vs literals in SUM |
| `gradebook` | Nested IFs, weighted averages, an error flowing through a comparison |

The loader (`src/plugin/workbook.py`) refuses a file whose cells lie outside A1:H30, exceed 30, are not listed row
by row, hold a formula that does not parse, or hold content a reader could misread (a number-like text such as
`007` or `1e3`, `true` in lower case, surrounding spaces, non-ASCII) unless it is written as `'text`. To change the
data, edit the file; the answer key's `data_sha256` then changes, and `tests/test_recalc.py` must be updated with
hand-worked values for every changed formula (a test fails until it is).

sha256: `65380c116cabf224e40f181284309323c576e7c22fc708cd8d90771c03762981`

## Verifier

`verifier/task.py` judges a `recalc-cells` submission with 10 named checks, in order. Each entry of
`details.checks` is `{id, ok, expected, actual, message}`; `ok` is `true`, `false`, or `null` (not checked because
a check it needs failed). The verdict is valid only when all 10 hold; the message is the first failing check, its
reason and how many more fail.

| # | id | What it checks | Example failure message |
|---|---|---|---|
| 1 | `task-input` | The workbook is bundled; 1 to 8 different targets, each an address of A1:Z99 | `the task input is invalid: unknown workbook 'budget': one of circular-refs, error-showcase, ...` |
| 2 | `reference` | The answer key was pinned for this task, from the bundled file (`data_sha256` equals the verifier's own hash of it), and every value, content, exact number and the cycle cells equal the verifier's own evaluation | `the answer key is inconsistent: B5 is number in the answer key but empty by the verifier` |
| 3 | `echo` | The submission's workbook and targets are the task's, in order | `the submission's workbook and targets are not the task's, in its order` |
| 4 | `saved` | `path` is this task's `values/<workbook>-<digest>.json`, inside the workspace, a file of at most 64 KB holding a JSON object | `no file at values/trip-budget-0f82f93cfc.json: call save_values before submitting` |
| 5 | `file-matches` | The saved file equals the submission, field by field (as JSON, so `1` never passes for `true`) | `the saved file differs from the submission in values: submit exactly what save_values returned` |
| 6 | `targets` | The values give each target once, in target order | `values must give each target once, in the order of targets ['B8', 'B12', 'B13', 'B5', 'B14', 'A2']: A2 is missing` |
| 7 | `shape` | Each value's fields fit its kind: a finite number, 0 unless kind is number; text empty for number and empty, `TRUE`/`FALSE` for boolean, a known code for error | `a value's fields do not fit its kind: B5 (empty): number must be 0 unless kind is number` |
| 8 | `kinds` | Each target's kind is the computed kind | `a value has the wrong kind: B5 is number, expected empty` |
| 9 | `numbers` | Each number is within `1e-6 x max(1, |exact|)` of the exact value | `a number is outside the tolerance: B12 is 108.17, expected 3786/35 (= 108.17142857142858): off by 0.00143, more than the 0.000108 allowed` |
| 10 | `texts` | Each text, boolean and error code is exact | `a text, boolean or error is not exact: A2 is 'flights', expected 'Flights'` |

**Score.** If checks 1 to 5 hold, the score is the share of targets whose value is right: one entry for the cell,
well shaped, the right kind, and the number within the tolerance or the text exact. Otherwise it is 0: values that
were not saved, were changed after saving, or answer another task earn nothing. `details` holds `values_correct`
(e.g. `5/6`), `expected` (each target's kind, exact number and text) and the tolerance.

**Independence.** Checks 8 to 10 judge against values the verifier computes itself: `verifier/data.py` reads the
bundled file from the plugin folder, and `verifier/sheet.py` evaluates it with a character-by-character tokenizer,
a recursive-descent parser with one function per precedence level, an evaluator over plain tuples, and cycle
detection by reachability (each cell that can reach itself), where the answer key uses a regular-expression
tokenizer, precedence climbing, dataclass values and Tarjan's algorithm. Check 2 requires the two to agree on every
value the answer key states, so a bug in either fails the verdict rather than passing a wrong answer. Neither uses
`eval` or `compile`.

Every tool call is checked as well. `verify_input` refuses the task inputs of check 1 (`pin_values`,
`save_values`), an unknown workbook (`get_sheet`) and misshapen values (`save_values`: the rules of checks 6 and
7). `verify_output` holds `list_workbooks` and `get_sheet` to the bundled file, `save_values` to its input and to the
file it wrote at this task's path, and `pin_values` to check 2. The `get-sheet` task is judged by `get_sheet`'s
`verify_output`.

## Layout

```text
.
├── nanoagent.yaml   # manifest: id, runtime, permissions (no network), tools, tasks and the agent's instructions
├── contract.py      # each tool's and task's typed input and output: slimconfig Output classes
├── README.md
├── LICENSE
├── pyproject.toml   # no dependencies beyond the template's
├── uv.lock
├── .gitignore
├── .env             # needed environment variable names (none)
├── src/plugin/      # the MCP server (__main__.py); workbook.py (data, addresses, contents), formula.py (parser),
│                    #   recalc.py (evaluator, cycles), sheets.py (list_workbooks, get_sheet), save.py
│                    #   (save_values), pin.py (pin_values), data/workbooks.json
├── tests/           # test_recalc.py (hand-worked golden values), test_formula.py, test_tools.py,
│                    #   test_verifier.py; helpers.py
├── ui/              # renderers.js: a result as a table of cells, kinds and values; a sheet as cells and contents
├── product/         # the product page a catalog shows: product.yaml and icon.svg
└── verifier/        # deterministic verifier: data.py and sheet.py (its own reader and engine), values.py,
                     #   checks.py, one module per tool (listing, lookup, save, pin), task.py (the 10 checks)
```

## Develop and run

```bash
uv sync --extra dev
uv run pytest            # 342 tests, offline
uv run ruff check .
```

Tests are named by category: `test_correct_*` (the answer key's values accepted for every cell of every workbook;
hand-rounded numbers within the tolerance; the tools' outputs approved; deterministic verdicts),
`test_incorrect_*` (a wrong number, kind, text, boolean or error code, values in the wrong order, extra or repeated
rows, a file that disagrees with the submission or was tampered with, a submission for another task),
`test_missing_*` (no saved file, no answer key, a missing row, no values, no workspace), `test_malformed_*` (task
inputs refused before any agent, misshapen values, non-finite numbers, files that are not JSON, not UTF-8, too
large, too deep, a folder or a link out, unsafe paths, a tampered answer key, tool outputs that differ from the
data, data contents the loader refuses, formulas both parsers refuse) and `test_boundary_*` (every bundled formula
against a value worked out by hand, about 110 single rules on small sheets, static cycles, tolerance edges, one
and eight targets, and both parsers and engines agreeing on 20,000 random formulas and 3,000 random sheets).

The golden values in `tests/test_recalc.py` are derived by hand from the rules above (each with its working in a
comment, e.g. trip-budget B12 = 757.2 / 7 = 3786/35), not by running either engine; both engines are checked
against them.

From NanoAgent's checkout, inspect, pack, run the tool task, and replay the scripted agent cases (each calls
`save_values` through the real MCP server, pins the answer key as NanoAgent does, and hands the submission to the
sandboxed verifier):

```bash
uv run nanoagent plugin inspect <this folder>
uv run nanoagent plugin pack <this folder> spreadsheet-recalc.tar.gz
uv run nanoagent plugin run config=run.yaml home=runs/sheet   # run.yaml: plugin, task: get-sheet, arguments: args.json
.venv/bin/python <hw2>/evidence/replay.py <this folder> <hw2>/evidence/cases/spreadsheet-recalc
```

with `args.json` such as `{"workbook": "trip-budget"}`. The sixteen replay cases live outside the plugin, in the
course repository's `evidence/cases/spreadsheet-recalc/`. NanoAgent passes the folder the plugin may write to as
`NANOAGENT_WORKSPACE`; values go in its `values/` folder. The agent task runs with `nanoagent plugin agent` and a
model.

## Limitations

- **Stated semantics, not Excel's.** The rules follow Excel where it is clear and simplify it where noted above; a
  model that answers from memory of Excel (e.g. `4^0.5` = 2, or `COUNT` skipping text) is marked wrong. The task's
  instructions are the definition.
- **A small language.** Twelve functions, no `&`, `%`, `$`, text functions, dates, arrays, named ranges or
  multiple sheets; A1:Z99 only.
- **Small, fixed data.** Ten invented workbooks, 280 cells. The agent can only be tested on these cells (any 1 to 8
  of A1:Z99 per task, so the task space is large but the formulas are these 140).
- **Hand arithmetic tolerance.** A number within `1e-6 x max(1, |exact|)` passes, so a careless answer that happens
  to land within it passes too; the tolerance is there because the agent writes decimals for values such as 1/3.
- **Shared reading of the rules.** The two engines are written separately, but by one author from one reading of
  the rules; a rule misread the same way in both would pass. The hand-worked golden values in
  `tests/test_recalc.py` guard against that for every bundled formula.
- **One file per task input.** Saving twice replaces the file; two runs of the same task in one workspace share
  it, and the verifier cannot tell which run wrote it.
