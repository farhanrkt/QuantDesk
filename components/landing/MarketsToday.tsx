"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { NewsCard } from "@/components/markets/NewsList";
import { useMarketBoard } from "@/components/shell/marketboard";
import { StateCard } from "@/components/ui/state";
import { marketsHref } from "@/lib/url";

const MARKET_ONLY = ["market"];

/**
 * The day's market context on the first screen: one sentence on what moved
 * unusually, the market's own headlines, and the way to the whole board.
 * The prices themselves are in the markets panel beside the page, or the band
 * above it on a narrower screen. If the board cannot load, the landing simply goes without it;
 * the bar says so.
 */
export function MarketsToday() {
  const { state, market } = useMarketBoard();
  if (state.status === "error") return null;
  const board = state.status === "ready" ? state.data : null;

  return (
    <section aria-labelledby="today-title" className="space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="today-title">Markets today</h2>
        <Link href={marketsHref("today")}
              className="inline-flex min-h-[24px] items-center gap-1.5 text-meta text-tech hover:underline">
          The whole board <ArrowRight aria-hidden className="h-3.5 w-3.5" />
        </Link>
      </div>
      {board ? (
        <>
          <p className="max-w-measureWide text-lead leading-snug text-body">
            {board.explain.markets[market]?.summary}
          </p>
          <NewsCard board={board} market={market} topics={MARKET_ONLY} limit={3} />
        </>
      ) : (
        <StateCard kind="loading" shape="lines" title="Fetching the day's markets" />
      )}
    </section>
  );
}
