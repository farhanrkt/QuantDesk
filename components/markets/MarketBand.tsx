"use client";

import Link from "next/link";
import { useMemo } from "react";
import { ExchangeStatusLine } from "@/components/markets/ExchangeStatus";
import { eventsFor } from "@/components/markets/MarketRail";
import { MarketSwitch, PriceTile } from "@/components/markets/PriceTile";
import { useMarketBoard } from "@/components/shell/marketboard";
import { ScrollRegion } from "@/components/ui/scroll";
import { dayHeading, dayOf, timeText, upcoming } from "@/lib/calendar";
import { marksFor, relatedFirst, stripFor } from "@/lib/marketboard";
import { marketsHref } from "@/lib/url";
import { cn } from "@/lib/utils";

/**
 * The markets panel for a screen narrower than 1280px, where a side column
 * would squeeze the page: the same large price tiles in one row that scrolls
 * sideways, whether each exchange is open, and the next two dates. The calendar
 * and the headlines in full are on Markets → Today, one tap away.
 *
 * On a stock page it also says, in words, which of these the stock has
 * measurably moved with — the sentence the tiles' rings stand for.
 */
export function MarketBand({ className }: { className?: string }) {
  const { state, calendar, market, chooseMarket, focus, fullBoard } = useMarketBoard();
  const next = useMemo(() => {
    if (calendar.status !== "ready") return [];
    return upcoming(eventsFor(calendar.data.events, market), new Date(), 14)
      .filter((e) => e.kind !== "holiday" && e.kind !== "early-close")
      .slice(0, 2);
  }, [calendar, market]);

  if (fullBoard || state.status === "error") return null;
  const board = state.status === "ready" ? state.data : null;
  const marks = board ? marksFor(board, focus) : {};
  const rows = board ? relatedFirst(stripFor(board, market), marks) : [];
  const relations = Object.values(marks).flat().filter((m) => m.kind === "movesWith").map((m) => m.text);

  return (
    <section aria-label="Markets now"
             className={cn("rounded-lg border border-rule bg-panel print:hidden", className)}>
      <div className="flex flex-wrap items-center justify-between gap-2 px-3 pt-2.5">
        <span className="text-meta font-semibold text-chalk">Markets</span>
        <div className="flex items-center gap-2">
          {!focus && <MarketSwitch market={market} onChange={chooseMarket} />}
          <Link href={marketsHref("today")}
                className="inline-flex min-h-[24px] items-center text-micro text-tech hover:underline">
            Calendar and news
          </Link>
        </div>
      </div>
      {calendar.status === "ready" && <ExchangeStatusLine className="px-3 pt-1" calendar={calendar.data} />}
      {relations.length > 0 && (
        <p className="px-3 pt-1 text-micro text-ash">{relations.join("; ")}. A record, not a forecast.</p>
      )}
      <ScrollRegion label="Market prices" className="px-1.5 pb-2 pt-2">
        {board ? (
          <ul className="flex gap-2 px-1.5">
            {rows.map((row) => (
              <PriceTile key={row.key} row={row} marks={marks[row.key] ?? []} className="w-40 shrink-0"
                         moveText={board.explain.rows[row.key]?.moveText ?? null}
                         onOpen={() => chooseMarket(market)} />
            ))}
          </ul>
        ) : (
          <p className="px-1.5 py-2 text-micro text-ash" role="status">Fetching prices…</p>
        )}
      </ScrollRegion>
      {next.length > 0 && (
        <p className="border-t border-ruleSoft px-3 py-2 text-micro text-ash">
          <span className="text-body">Next:</span>{" "}
          {next.map((e) => `${e.title}, ${dayHeading(dayOf(e))} ${timeText(e)}`).join(" · ")}
        </p>
      )}
    </section>
  );
}
