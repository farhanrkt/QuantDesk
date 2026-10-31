"use client";

import Link from "next/link";
import { MarketSwitch, QuoteChip } from "@/components/markets/quotes";
import { useMarketBoard } from "@/components/shell/marketboard";
import { ScrollRegion } from "@/components/ui/scroll";
import { marksFor, relatedFirst, stripFor } from "@/lib/marketboard";
import { marketsHref } from "@/lib/url";
import { cn } from "@/lib/utils";

/**
 * "Markets now" inline, for a phone, where a bar fixed to the foot of the
 * screen would sit on top of the browser's own toolbar and the page's last
 * line. The same quotes as `MarketDock`, scrolling sideways in one row.
 *
 * On a stock page it also says, in words, which of these the stock is
 * related to — the sentence a tooltip carries on a wider screen.
 */
export function MarketStrip({ className }: { className?: string }) {
  const { state, market, chooseMarket, focus } = useMarketBoard();
  const board = state.status === "ready" ? state.data : null;
  if (state.status === "error") return null;
  const marks = board ? marksFor(board, focus) : {};
  const rows = board ? relatedFirst(stripFor(board, market), marks) : [];
  const sentences = Object.values(marks).flat()
    .filter((m) => m.kind === "movesWith").map((m) => m.text);

  return (
    <section aria-label="Markets now" className={cn("rounded-lg border border-rule bg-panel print:hidden", className)}>
      <div className="flex items-center justify-between gap-2 px-3 pt-2">
        <span className="eyebrow">Markets now</span>
        <div className="flex items-center gap-2">
          {!focus && <MarketSwitch market={market} onChange={chooseMarket} />}
          <Link href={marketsHref("today")}
                className="inline-flex min-h-[24px] items-center text-micro text-tech hover:underline">
            All markets
          </Link>
        </div>
      </div>
      {sentences.length > 0 && (
        <p className="px-3 pt-1 text-micro text-ash">{sentences.join("; ")}. A record, not a forecast.</p>
      )}
      <ScrollRegion label="Market quotes" className="px-1 pb-1.5 pt-1">
        {board ? (
          <ul className="flex items-center gap-0.5">
            {rows.map((row) => (
              <QuoteChip key={row.key} row={row} marks={marks[row.key] ?? []}
                         onOpen={() => chooseMarket(market)}
                         moveText={board.explain.rows[row.key]?.moveText ?? null} />
            ))}
          </ul>
        ) : (
          <p className="px-2 py-1.5 text-micro text-ash">Fetching quotes…</p>
        )}
      </ScrollRegion>
    </section>
  );
}
