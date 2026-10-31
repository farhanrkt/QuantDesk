"use client";

import { Link2 } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { levelText, type Mark } from "@/lib/marketboard";
import type { BoardRow, Market } from "@/lib/types";
import { marketsHref } from "@/lib/url";
import { cn } from "@/lib/utils";

/**
 * One instrument in the compact strip: what it is, where it is, how far it
 * moved. Shared by the bar at the foot of every page and the phone strip, so
 * the two cannot disagree about how a quote reads.
 *
 * Emphasis is for a move that was UNUSUAL FOR THAT INSTRUMENT, never for a
 * direction. A row the stock on screen is related to — its market, a reference
 * it has measurably moved with — carries a link icon, and the full sentence is
 * in its accessible name and its tooltip.
 */
export function QuoteChip({
  row, moveText, marks, onOpen,
}: {
  row: BoardRow; moveText: string | null; marks: Mark[];
  /** Called before following the link, so the board opens on the market the chip came from. */
  onOpen?: () => void;
}) {
  const related = marks.length > 0;
  const said = [
    `${row.name}: ${row.available ? levelText(row) : "no recent price"}`,
    row.available && moveText ? moveText : null,
    row.unusual ? "unusual for it" : null,
    ...marks.map((m) => m.text),
  ].filter(Boolean).join(", ");
  return (
    <li className="shrink-0">
      <Link href={`${marketsHref("today")}#board-${row.key}`} aria-label={said} title={said}
            onClick={onOpen}
            className={cn("flex min-h-[32px] items-baseline gap-1.5 rounded px-2 py-1 transition-colors",
                          "hover:bg-raised focus:outline-none focus-visible:ring-2 focus-visible:ring-tech",
                          related && "ring-1 ring-inset ring-ruleStrong")}>
        {related && <Link2 aria-hidden className="h-3 w-3 shrink-0 self-center text-chalk" />}
        <span className={cn("text-micro", related ? "text-chalk" : "text-ash")}>{row.short}</span>
        {row.available ? (
          <>
            <span className="num text-meta text-body">{levelText(row)}</span>
            <span className={cn("num text-meta", row.unusual ? "font-semibold text-chalk" : "text-ash")}>
              {moveText}
            </span>
            {row.unusual && (
              <span className="self-center rounded-sm border border-ruleStrong px-1 text-micro leading-tight text-chalk">
                unusual
              </span>
            )}
          </>
        ) : (
          <span className="text-micro text-ash">no price</span>
        )}
      </Link>
    </li>
  );
}

/** US or IDX, for the pages that are not about one stock. Two toggles, not a radiogroup. */
export function MarketSwitch({
  market, onChange, className,
}: { market: Market; onChange: (market: Market) => void; className?: string }) {
  return (
    <div role="group" aria-label="Which market's board" className={cn("flex gap-1", className)}>
      {(["US", "ID"] as const).map((code) => (
        <Button key={code} variant="chip" size="xs" aria-pressed={market === code}
                onClick={() => onChange(code)}>
          {code === "ID" ? "IDX" : "US"}
        </Button>
      ))}
    </div>
  );
}
