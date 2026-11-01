"use client";

import { ArrowRight, PanelRightClose, PanelRightOpen } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { CalendarList } from "@/components/markets/CalendarList";
import { CalendarMonth } from "@/components/markets/CalendarWidgets";
import { ExchangeStatusLine } from "@/components/markets/ExchangeStatus";
import { NewsCompact } from "@/components/markets/NewsList";
import { MarketSwitch, PriceTile } from "@/components/markets/PriceTile";
import { useMarketBoard } from "@/components/shell/marketboard";
import { Button } from "@/components/ui/button";
import { ScrollRegion } from "@/components/ui/scroll";
import { byDay, dayHeading, earningsEvents, todayIn, upcoming } from "@/lib/calendar";
import { clockText, marksFor, relatedFirst, stripFor } from "@/lib/marketboard";
import type { CalendarEvent, Market } from "@/lib/types";
import { marketsHref } from "@/lib/url";

/** The events a reader of one market sees: every release and decision, and only that market's closures. */
export function eventsFor(
  events: CalendarEvent[], market: Market,
): CalendarEvent[] {
  return events.filter((e) => (e.kind !== "holiday" && e.kind !== "early-close") || e.market === market);
}

/**
 * The markets panel: prices, the calendar and the day's headlines, in a column
 * of its own beside every page on a screen 1280px or wider. The calendar is a
 * month with the dates written in, over the fortnight ahead as a list; choosing
 * a day in the month puts that day in the list instead.
 *
 * ON THE SIDE, CHOSEN BY THE OWNER. The first placement was a 44px bar at the
 * foot of the page, and it was too small to read. A column holds large price
 * tiles, a fortnight of dates and the news one above the other, scrolls on its
 * own, and leaves the stock page's sticky lens tabs where they were. It can be
 * hidden (remembered in this browser), it steps aside on the Today view, which
 * shows the whole board, and it is never printed. Narrower screens get the
 * band (`MarketBand`) instead.
 */
export function MarketRail() {
  const {
    state, calendar, earnings, market, chooseMarket, focus, fullBoard, railOpen, setRailOpen,
  } = useMarketBoard();

  // THE BUTTON THAT WAS PRESSED DISAPPEARS, so focus is handed to its
  // counterpart; otherwise a keyboard reader is dropped back to the top of the
  // page every time they hide or show the panel.
  const showRef = useRef<HTMLButtonElement>(null);
  const hideRef = useRef<HTMLButtonElement>(null);
  const focusNext = useRef<"show" | "hide" | null>(null);
  useEffect(() => {
    if (focusNext.current === "show") showRef.current?.focus();
    if (focusNext.current === "hide") hideRef.current?.focus();
    focusNext.current = null;
  }, [railOpen]);
  const toggle = (open: boolean) => {
    focusNext.current = open ? "hide" : "show";
    setRailOpen(open);
  };

  // The calendar moves on as the day does; a minute is fine-grained enough.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 60_000);
    return () => window.clearInterval(timer);
  }, []);

  const month = useMemo(() => {
    if (calendar.status !== "ready") return [];
    const reports = earningsEvents(
      focus?.earnings ? { symbol: focus.symbol, date: focus.earnings } : null,
      earnings.status === "ready" ? earnings.data.items : [],
    );
    return eventsFor([...calendar.data.events, ...reports], market);
  }, [calendar, earnings, focus, market]);
  const events = useMemo(() => upcoming(month, new Date(now), 14), [month, now]);
  const [picked, setPicked] = useState<string | null>(null);
  const list = picked ? byDay(month).get(picked) ?? [] : events;

  if (fullBoard) return null;

  if (!railOpen) {
    return (
      <div className="sticky top-14 hidden h-[calc(100dvh-3.5rem)] w-12 shrink-0 justify-center border-l
                      border-rule pt-4 xl:flex print:hidden">
        <Button ref={showRef} variant="quiet" size="icon" aria-expanded={false}
                aria-label="Show the markets panel" onClick={() => toggle(true)}>
          <PanelRightOpen aria-hidden className="h-4 w-4" />
        </Button>
      </div>
    );
  }

  const board = state.status === "ready" ? state.data : null;
  const marks = board ? marksFor(board, focus) : {};
  const rows = board ? relatedFirst(stripFor(board, market), marks) : [];
  const clock = clockText(board?.fetchedAt);
  const pending = calendar.status === "ready" ? calendar.data.pending : [];

  return (
    <aside aria-label="Markets"
           className="sticky top-14 hidden h-[calc(100dvh-3.5rem)] w-[22rem] shrink-0 border-l border-rule
                      xl:block print:hidden">
      <ScrollRegion label="Markets panel" vertical className="h-full">
        <div className="space-y-6 px-4 py-5">
          <div className="space-y-2">
            <div className="flex items-center justify-between gap-2">
              <h2 className="text-h3">Markets</h2>
              <div className="flex items-center gap-1.5">
                {focus ? (
                  <span className="text-micro text-ash">
                    {focus.market === "ID" ? "IDX" : "US"} · for {focus.symbol}
                  </span>
                ) : (
                  <MarketSwitch market={market} onChange={chooseMarket} />
                )}
                <Button ref={hideRef} variant="quiet" size="icon" className="h-8 w-8" aria-expanded
                        aria-label="Hide the markets panel" onClick={() => toggle(false)}>
                  <PanelRightClose aria-hidden className="h-4 w-4" />
                </Button>
              </div>
            </div>
            {calendar.status === "ready" && <ExchangeStatusLine calendar={calendar.data} />}
          </div>

          <section aria-labelledby="rail-prices" className="space-y-2">
            <div className="flex items-baseline justify-between gap-2">
              <h3 id="rail-prices" className="text-meta font-semibold text-chalk">Prices</h3>
              {clock && <span className="text-micro text-ash">as of {clock}</span>}
            </div>
            {board ? (
              <ul className="grid grid-cols-2 gap-2">
                {rows.map((row) => (
                  <PriceTile key={row.key} row={row} marks={marks[row.key] ?? []}
                             moveText={board.explain.rows[row.key]?.moveText ?? null}
                             onOpen={() => chooseMarket(market)} />
                ))}
              </ul>
            ) : (
              <p className="text-meta text-ash" role="status">
                {state.status === "error" ? "The prices did not load." : "Fetching prices…"}
              </p>
            )}
            <Link href={marketsHref("today")}
                  className="inline-flex min-h-[24px] items-center gap-1 text-meta text-tech hover:underline">
              All 22, and what moved unusually <ArrowRight aria-hidden className="h-3.5 w-3.5" />
            </Link>
          </section>

          <section aria-labelledby="rail-calendar" className="space-y-2">
            <h3 id="rail-calendar" className="text-meta font-semibold text-chalk">Calendar</h3>
            {calendar.status === "ready" ? (
              <>
                <CalendarMonth events={month} today={todayIn(new Date(now))}
                               from={calendar.data.window?.from} through={calendar.data.window?.through}
                               selected={picked} onSelect={setPicked} />
                <div className="flex min-h-[24px] items-center justify-between gap-2 border-t border-ruleSoft pt-2">
                  <p aria-live="polite" className="text-micro text-ash">
                    {picked ? `Showing ${dayHeading(picked)}` : "The next 14 days"}
                  </p>
                  {picked && (
                    <button type="button" onClick={() => setPicked(null)}
                            className="inline-flex min-h-[24px] items-center text-micro text-tech hover:underline">
                      Back to the next 14 days
                    </button>
                  )}
                </div>
                {list.length > 0
                  ? <CalendarList events={list} kinds={calendar.data.kinds} board={board} compact />
                  : <p className="text-meta text-ash">Nothing on the calendar in the next fortnight.</p>}
              </>
            ) : (
              <p className="text-meta text-ash" role="status">
                {calendar.status === "error" ? "The calendar did not load." : "Fetching the calendar…"}
              </p>
            )}
            {pending.length > 0 && (
              <p className="text-micro leading-snug text-ash">
                Not shown: {pending.map((p) => p.note.replace(/\.$/, "")).join("; ")}.
              </p>
            )}
          </section>

          <section aria-labelledby="rail-news" className="space-y-2">
            <h3 id="rail-news" className="text-meta font-semibold text-chalk">Headlines</h3>
            {board && <NewsCompact board={board} market={market} />}
          </section>
        </div>
      </ScrollRegion>
    </aside>
  );
}
