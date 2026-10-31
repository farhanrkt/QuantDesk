"use client";

import { ChevronDown, ChevronUp, Link2, RefreshCw } from "lucide-react";
import { useEffect, useRef } from "react";
import { MarketSwitch, QuoteChip } from "@/components/markets/quotes";
import { useMarketBoard } from "@/components/shell/marketboard";
import { Button } from "@/components/ui/button";
import { ScrollRegion } from "@/components/ui/scroll";
import { clockText, marksFor, relatedFirst, stripFor } from "@/lib/marketboard";
import { cn } from "@/lib/utils";

/**
 * "Markets now": the bar at the foot of every page on a tablet or wider, so the
 * day's moves stay in view while a stock is being read.
 *
 * AT THE FOOT, NOT THE TOP. The top of a stock page already holds the top bar
 * and the sticky lens tabs; a third sticky row there would eat a fifth of a
 * laptop screen. A status bar at the bottom costs 44px and covers nothing,
 * because the shell adds the same height of space after the footer.
 *
 * Collapsible, and the choice is remembered in this browser. Hidden on the
 * Today view, which shows the whole board, and never printed. Phones get the
 * inline strip instead (`MarketStrip`).
 */
export function MarketDock() {
  const {
    state, market, chooseMarket, focus, fullBoard, dockOpen, setDockOpen, refresh, refreshing,
  } = useMarketBoard();

  // THE BUTTON THAT WAS PRESSED DISAPPEARS, so focus is handed to its
  // counterpart; otherwise a keyboard reader is dropped back to the top of the
  // page every time they hide or show the bar.
  const showRef = useRef<HTMLButtonElement>(null);
  const hideRef = useRef<HTMLButtonElement>(null);
  const focusNext = useRef<"show" | "hide" | null>(null);
  useEffect(() => {
    if (focusNext.current === "show") showRef.current?.focus();
    if (focusNext.current === "hide") hideRef.current?.focus();
    focusNext.current = null;
  }, [dockOpen]);
  const toggle = (open: boolean) => {
    focusNext.current = open ? "hide" : "show";
    setDockOpen(open);
  };

  if (fullBoard) return null;

  if (!dockOpen) {
    return (
      <div className="fixed bottom-3 left-3 z-40 hidden md:block print:hidden">
        <Button ref={showRef} variant="quiet" size="xs" className="bg-ink" aria-expanded={false}
                onClick={() => toggle(true)}>
          <ChevronUp aria-hidden className="h-3.5 w-3.5" /> Markets now
        </Button>
      </div>
    );
  }

  const board = state.status === "ready" ? state.data : null;
  const marks = board ? marksFor(board, focus) : {};
  const rows = board ? relatedFirst(stripFor(board, market), marks) : [];
  const related = Object.keys(marks).length > 0;
  const clock = clockText(board?.fetchedAt);

  return (
    <section aria-label="Markets now"
             className="fixed inset-x-0 bottom-0 z-40 hidden border-t border-rule bg-ink/95 backdrop-blur
                        supports-[backdrop-filter]:bg-ink/85 md:block print:hidden">
      {/* The full width of the window, like any status bar: eight quotes need it. */}
      <div className="flex h-11 items-center gap-2 px-4 sm:px-6">
        <span className="eyebrow shrink-0">Markets now</span>
        {focus ? (
          <span className="shrink-0 text-micro text-ash">{focus.market === "ID" ? "IDX" : "US"}</span>
        ) : (
          <MarketSwitch market={market} onChange={chooseMarket} className="shrink-0" />
        )}
        <ScrollRegion label="Market quotes" className="min-w-0 flex-1">
          {board ? (
            <ul className="flex items-center gap-0.5">
              {rows.map((row) => (
                <QuoteChip key={row.key} row={row} marks={marks[row.key] ?? []}
                           onOpen={() => chooseMarket(market)}
                           moveText={board.explain.rows[row.key]?.moveText ?? null} />
              ))}
            </ul>
          ) : (
            <p className="px-2 text-micro text-ash">
              {state.status === "error" ? "The market board did not load." : "Fetching quotes…"}
            </p>
          )}
        </ScrollRegion>
        {related && focus && (
          <span className="hidden shrink-0 items-center gap-1 text-micro text-ash 2xl:inline-flex">
            <Link2 aria-hidden className="h-3 w-3 text-chalk" /> related to {focus.symbol}
          </span>
        )}
        {clock && <span className="hidden shrink-0 text-micro text-ash xl:inline">as of {clock}</span>}
        <Button variant="quiet" size="icon" className="h-8 w-8" onClick={refresh} disabled={refreshing}
                aria-label="Refresh market quotes">
          <RefreshCw aria-hidden className={cn("h-3.5 w-3.5", refreshing && "animate-spin motion-reduce:animate-none")} />
        </Button>
        <Button ref={hideRef} variant="quiet" size="icon" className="h-8 w-8" aria-expanded
                aria-label="Hide the market bar" onClick={() => toggle(false)}>
          <ChevronDown aria-hidden className="h-3.5 w-3.5" />
        </Button>
      </div>
    </section>
  );
}

/** The bar's height again, after the footer, so the last line of every page clears it. */
export function DockSpacer() {
  const { fullBoard, dockOpen } = useMarketBoard();
  if (fullBoard || !dockOpen) return null;
  return <div aria-hidden className="hidden h-11 md:block print:hidden" />;
}
