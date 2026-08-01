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

/** RFC 4180: quote when the value contains a delimiter, quote or newline. */
function escapeCell(value: Cell): string {
  if (value === null || value === undefined) return "";
  const text = String(value);
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
