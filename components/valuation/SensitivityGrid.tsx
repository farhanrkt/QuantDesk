"use client";

import { Grid3x3 } from "lucide-react";
import { Card, CardBody, CardHeader, CardTitle, Explainer, Note } from "@/components/ui/card";
import { useDetail } from "@/components/ui/explain";
import type { ValuationSensitivity } from "@/lib/types";
import { cn, pct } from "@/lib/utils";

/**
 * The base case across a grid of growth and discount rate.
 *
 * NUMBERS, NOT A HEAT MAP — and that is enforced (check_frontend.mjs rule 14),
 * not intended. Every cell is mono text on the same ground: no fill, no weight
 * change, no tone, and nothing anywhere in this file compares a cell with the
 * price. A grid of fair values coloured green above the price and red below it
 * is a buy/sell signal with extra steps, which PRODUCT.md constraint 1 refuses.
 * The price is printed BESIDE the grid so the reader can make that comparison
 * themselves, with the assumptions in front of them.
 *
 * The assumed cell is outlined in the engine's identity colour — identity, not
 * judgement — and equals the base case above it exactly (a server test pins
 * that). A refused cell is a dash with the reason, never the clamped number the
 * model would otherwise produce.
 */
export function SensitivityGrid({
  data, accent,
}: { data: ValuationSensitivity; accent: string }) {
  const guided = useDetail() === "simple";
  const { rowAxis, colAxis, cells, assumed, impliedRow } = data;
  // "WACC" is an acronym and stays one inside a sentence; "Cost of equity" is not.
  const lower = (label: string) => (label === label.toUpperCase() ? label : label.toLowerCase());
  const anyRefused = cells.some((row) => row.some((c) => c.refused === "spread"));
  const anyUnreachable = impliedRow?.some((e) => e.reason === "unreachable") ?? false;

  const table = (
    <div className="overflow-x-auto rounded-lg border border-ruleSoft">
      <table className="w-full min-w-[30rem] text-meta">
        <caption className="sr-only">
          Base-case value per share by {lower(rowAxis.label)} (rows) and{" "}
          {lower(colAxis.label)} (columns). The assumed case is row{" "}
          {pct(rowAxis.values[assumed.row])}, column {pct(colAxis.values[assumed.col])}.
        </caption>
        <thead>
          <tr className="border-b border-rule bg-sunken">
            <th scope="col" className="px-3 py-2 text-left font-normal">
              <span className="eyebrow">{rowAxis.label}</span>
              <span className="block text-micro text-faint">by {colAxis.label}</span>
            </th>
            {colAxis.values.map((r, j) => (
              <th key={r} scope="col"
                  className={cn("num px-3 py-2 text-right font-medium",
                                j === assumed.col ? "text-chalk" : "text-ash")}>
                {pct(r)}
                {j === assumed.col && <span className="block text-micro font-normal text-faint">assumed</span>}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {cells.map((row, i) => (
            <tr key={rowAxis.values[i]} className="border-b border-ruleSoft last:border-0">
              <th scope="row"
                  className={cn("num px-3 py-1.5 text-left font-medium",
                                i === assumed.row ? "text-chalk" : "text-ash")}>
                {pct(rowAxis.values[i])}
                {i === assumed.row && <span className="ml-2 text-micro font-normal text-faint">assumed</span>}
              </th>
              {row.map((cell, j) => {
                const isAssumed = i === assumed.row && j === assumed.col;
                return (
                  <td key={colAxis.values[j]}
                      title={cell.refused === "spread" ? data.refusals.spread : undefined}
                      className={cn("num px-3 py-1.5 text-right",
                                    cell.value == null ? "text-faint" : "text-body")}
                      style={isAssumed ? { outline: `1px solid ${accent}`, outlineOffset: "-3px" } : undefined}>
                    {cell.label ?? "—"}
                    {isAssumed && <span className="sr-only"> (the assumed case)</span>}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
        {impliedRow && (
          <tfoot>
            <tr className="border-t border-rule bg-sunken">
              <th scope="row" className="px-3 py-2 text-left font-normal">
                <span className="eyebrow">Growth the price implies</span>
              </th>
              {impliedRow.map((entry) => (
                <td key={entry.rate} className="num px-3 py-2 text-right text-body"
                    title={entry.reason ? data.refusals[entry.reason] : undefined}>
                  {entry.impliedGrowth == null ? "—" : pct(entry.impliedGrowth)}
                </td>
              ))}
            </tr>
          </tfoot>
        )}
      </table>
    </div>
  );

  return (
    <Card accent={accent}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Grid3x3 aria-hidden className="h-4 w-4" />
          If the two biggest assumptions were different
        </CardTitle>
        <span className="font-mono text-micro text-ash">base case · value per share</span>
      </CardHeader>
      <CardBody className="space-y-3">
        {data.priceLabel && (
          <p className="text-meta text-ash">
            Market price <span className="num text-body">{data.priceLabel}</span> — beside the
            grid, not inside it. Perpetual growth held at {pct(data.terminalGrowth)}.
          </p>
        )}
        {guided ? (
          <Explainer summary="How far the value moves if growth or the discount rate is a few points off — the assumed case is outlined">
            {table}
          </Explainer>
        ) : table}
        <p className="prose-col text-meta leading-relaxed text-ash">{data.reading}</p>
        {anyRefused && <Note>A dash in the grid: {data.refusals.spread}</Note>}
        {anyUnreachable && <Note>A dash in the bottom row: {data.refusals.unreachable}</Note>}
        {data.impliedRowReason && <Note>{data.impliedRowReason}</Note>}
      </CardBody>
    </Card>
  );
}
