"use client";

/**
 * Client-side CSV export for data the page already holds.
 *
 * The anomaly log and the technical series are fully present in the JSON the
 * panels render, so downloading them needs no round trip. The Monte Carlo draws
 * are the exception — 10,000 rows never cross the wire, so that one download
 * hits `/api/intrinsic-value/simulation` instead.
 */

type Cell = string | number | boolean | null | undefined;

/**
 * RFC 4180 quoting, plus a guard against spreadsheet formula injection.
 *
 * A cell whose text begins with `=`, `+`, `-`, `@`, or a leading tab is
 * interpreted as a FORMULA by Excel, Sheets and Numbers rather than as text.
 * This app's ticker pattern deliberately allows `=` — FX symbols look like
 * `EURUSD=X` — so `=HYPERLINK` passes validation, reaches the Ticker column of
 * the screener and ranking exports, and executes when the file is opened.
 *
 * THE GUARD IS RESTRICTED TO STRINGS, WHICH IS THE WHOLE DIFFICULTY. Numeric
 * cells legitimately begin with a minus sign, and prefixing those would turn
 * every negative return in every export into text that no spreadsheet will sum.
 * A `number` is therefore never escaped; only text that arrived as text is.
 */
const FORMULA_LEAD = /^[=+\-@\t\r]/;

function escapeCell(value: Cell): string {
  if (value === null || value === undefined) return "";
  let text = String(value);
  if (typeof value === "string" && FORMULA_LEAD.test(text)) {
    // A leading apostrophe is the conventional "treat as text" marker and is
    // not displayed by the spreadsheet that consumes it.
    text = `'${text}`;
  }
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

/**
 * `T` is deliberately unconstrained. Declared interfaces have no implicit index
 * signature, so constraining to `Record<string, Cell>` would reject every wire
 * type we actually export from here. `keyof T` still checks each column key
 * against the row shape, which is the guarantee worth having.
 */
export function toCsv<T>(
  rows: T[],
  columns: { key: keyof T; label: string }[]
): string {
  const header = columns.map((c) => escapeCell(c.label)).join(",");
  const body = rows.map((row) =>
    columns.map((c) => escapeCell(row[c.key] as Cell)).join(",")
  );
  return [header, ...body].join("\r\n");
}

export function downloadCsv(filename: string, contents: string) {
  // A BOM so Excel reads UTF-8 rather than guessing at the ° and · characters.
  const blob = new Blob([`﻿${contents}`], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
