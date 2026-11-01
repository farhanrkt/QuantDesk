"use client";

import { Link2 } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Sparkline } from "@/components/ui/sparkline";
import { levelText, relationLabel, type Mark } from "@/lib/marketboard";
import type { BoardRow, Market } from "@/lib/types";
import { marketsHref } from "@/lib/url";
import { cn } from "@/lib/utils";

/**
 * One instrument as a tile: what it is, where it is, how far it moved, and the
 * shape of its last three months. Shared by the side panel and the band, so the
 * two cannot disagree about how a quote reads.
 *
 * LARGE ON PURPOSE. The first version of this was a 44px bar of 13px chips at the
 * foot of the page, and the owner's verdict was that it was too small to read;
 * the level is now set at the lead size and the tile gives it room.
 *
 * Emphasis is for a move that was UNUSUAL FOR THAT INSTRUMENT, never for a
 * direction, and nothing here is coloured. A tile the stock on screen is related
 * to — its market, a reference it measurably moved with, the rate its valuation
 * discounts from — says so in words and carries a hairline ring.
 */
export function PriceTile({
  row, moveText, marks, onOpen, className,
}: {
  row: BoardRow;
  moveText: string | null;
  marks: Mark[];
  /** Called before following the link, so the board opens on the market the tile came from. */
  onOpen?: () => void;
  className?: string;
}) {
  const related = marks.length > 0;
  const said = [
    `${row.name}: ${row.available ? levelText(row) : "no recent price"}`,
    row.available && moveText ? moveText : null,
    row.unusual ? "unusual for it" : null,
    ...marks.map((m) => m.text),
  ].filter(Boolean).join(", ");
  return (
    <li className={cn("min-w-0", className)}>
      <Link href={`${marketsHref("today")}#board-${row.key}`} aria-label={said} title={said} onClick={onOpen}
            className={cn("flex h-full flex-col rounded-lg border border-ruleSoft bg-sunken px-3 py-2.5",
                          "transition-colors hover:border-ruleStrong",
                          "focus:outline-none focus-visible:ring-2 focus-visible:ring-tech",
                          related && "ring-1 ring-inset ring-ruleStrong")}>
        <div className="flex items-baseline justify-between gap-2">
          <span className={cn("truncate text-meta", related ? "text-chalk" : "text-ash")}>{row.short}</span>
          {row.unusual && (
            <span className="shrink-0 rounded-sm border border-ruleStrong px-1 text-micro leading-tight text-chalk">
              unusual
            </span>
          )}
        </div>
        {row.available ? (
          <>
            <div className="num mt-1 text-lead font-semibold leading-tight text-chalk">{levelText(row)}</div>
            <div className="mt-1 flex items-end justify-between gap-2">
              <span className={cn("num text-meta", row.unusual ? "font-semibold text-chalk" : "text-body")}>
                {moveText}
              </span>
              <Sparkline values={row.spark} width={64} height={22} className="shrink-0" />
            </div>
          </>
        ) : (
          <div className="mt-1 text-micro text-ash">No recent price</div>
        )}
        {related && (
          <div className="mt-1.5 flex items-center gap-1 text-micro text-ash">
            <Link2 aria-hidden className="h-3 w-3 shrink-0 text-chalk" />
            <span className="truncate">{marks.map(relationLabel).join(" · ")}</span>
          </div>
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
