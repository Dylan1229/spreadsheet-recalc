// How this plugin's page draws its tasks' outputs: a recalc result as a table of each target's kind and
// value (errors marked), with the file it was saved to; a sheet as a table of its cells and their contents.
import { dataTable, h, icon, statusPill } from "./kit/components.js";

const TONE = { number: "neutral", text: "info", boolean: "info", empty: "neutral", error: "bad" };

/** What a value shows: the number, the text in quotes, TRUE/FALSE, the error code, or "(empty)". */
const shown = ({ kind, number, text }) => {
  if (kind === "number") return String(number);
  if (kind === "text") return `"${text}"`;
  if (kind === "empty") return "(empty)";
  return text;
};

export default {
  ValuesOutput: ({ workbook, values, path }) =>
    h(
      "div",
      { class: "recalc" },
      dataTable({
        columns: [
          { key: "cell", label: "Cell", primary: true },
          { key: "kind", label: "Kind", render: (row) => statusPill(row.kind, TONE[row.kind] ?? "neutral") },
          { key: "shown", label: "Value", render: (row) => h("code", { text: row.shown }) },
        ],
        rows: values.map((row) => ({ ...row, shown: shown(row) })),
        caption: `Values in ${workbook}`,
      }).element,
      h("p", { class: "recalc-path muted" }, icon("file", { size: 14 }), h("code", { text: path })),
    ),
  SheetOutput: ({ title, used_range, cells }) =>
    h(
      "div",
      { class: "recalc" },
      h("p", { class: "muted" }, `${title}, ${used_range}`),
      dataTable({
        columns: [
          { key: "cell", label: "Cell", primary: true },
          { key: "content", label: "Content", render: (row) => h("code", { text: row.content }) },
        ],
        rows: cells,
        caption: title,
      }).element,
    ),
};
