"use client";

import { RefreshCw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { CalendarList } from "@/components/markets/CalendarList";
import { CalendarMonth } from "@/components/markets/CalendarWidgets";
import { eventsFor } from "@/components/markets/MarketRail";
import { NewsCard } from "@/components/markets/NewsList";
import { MarketSwitch } from "@/components/markets/PriceTile";
import { useFullBoard, useMarketBoard } from "@/components/shell/marketboard";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle, Note } from "@/components/ui/card";
import { Explain } from "@/components/ui/explain";
import { ScrollRegion } from "@/components/ui/scroll";
import { Sparkline } from "@/components/ui/sparkline";
import { StateCard } from "@/components/ui/state";
import { byDay, dayHeading, earningsEvents, todayIn, upcoming } from "@/lib/calendar";
import { clockText, dayText, levelText, rowsFor, sinceText } from "@/lib/marketboard";
import type { BoardRow, CalendarKind, Market, MarketBoard } from "@/lib/types";
import { cn, ordinal } from "@/lib/utils";

/**
 * What moved the markets: the whole board, for one market's readers.
 *
 * THE SENTENCE FIRST, THE TABLE SECOND. A newcomer needs to be told which moves
 * were unusual for the thing that made them; the table is there to check it
 * against. Both come from the server — the summary is written by
 * `explain.for_market_board` from the same rows the table draws.
 *
 * NO COLOUR FROM DIRECTION, NO ORDER FROM SIZE. Rows sit in fixed groups in a
 * declared order, every row's tone is neutral, and a move is emphasised only
 * when it was unusual for its own instrument (api/_lib/marketboard.py). Rule 19
 * in scripts/check_frontend.mjs fails the build on a sort or a tone class here.
 */
export function TodayView() {
  useFullBoard();
  const { state, market, chooseMarket, refresh, refreshing } = useMarketBoard();

  if (state.status === "idle" || state.status === "loading") {
    return <StateCard kind="loading" shape="table" title="Fetching the board" />;
  }
  if (state.status === "error") {
    return (
      <StateCard kind="error" title="The market board did not load"
                 action={<Button variant="secondary" size="sm" onClick={refresh}>Try again</Button>}>
        {state.failure.message}
      </StateCard>
    );
  }

  const board = state.data;
  const said = board.explain.markets[market];
  const clock = clockText(board.fetchedAt);

  return (
    <div className="space-y-6">
      <Card>
        <CardBody className="space-y-3 py-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <MarketSwitch market={market} onChange={chooseMarket} />
            <div className="flex items-center gap-3 text-micro text-ash">
              {clock && <span>Fetched at {clock}</span>}
              <Button variant="quiet" size="xs" onClick={refresh} disabled={refreshing}>
                <RefreshCw aria-hidden
                           className={cn("h-3.5 w-3.5", refreshing && "animate-spin motion-reduce:animate-none")} />
                Refresh
              </Button>
            </div>
          </div>
          <p className="max-w-measureWide text-lead leading-snug text-chalk">{said?.summary}</p>
          {said?.baseRate && <p className="prose-col text-meta leading-relaxed text-ash">{said.baseRate}</p>}
          <p className="prose-col text-micro text-ash">
            {board.delay} Source: {board.source}. Each instrument is read on its own trading days.
          </p>
        </CardBody>
      </Card>

      <BoardTable board={board} market={market} />
      <Missing board={board} market={market} />
      <FullCalendar board={board} market={market} />
      <EventHistory board={board} />
      <NewsCard board={board} market={market} />

      <Note>
        A description of one day, not a forecast of the next, and not a reason to buy or sell
        anything. A move&apos;s size is set against its own past year; nothing here says what
        caused it, and nothing here is coloured by whether it went up or down.
      </Note>
    </div>
  );
}

function BoardTable({ board, market }: { board: MarketBoard; market: Market }) {
  const rows = rowsFor(board, market);
  return (
    <Card>
      <ScrollRegion label="Market board">
        <table className="w-full min-w-[46rem] text-meta">
          <caption className="sr-only">
            Each instrument&apos;s latest session, and how its move compares with its own daily
            moves over the past year.
          </caption>
          <thead>
            <tr className="border-b border-rule text-left">
              <th scope="col" className="eyebrow px-5 py-2.5 font-normal">Instrument</th>
              <th scope="col" className="eyebrow px-3 py-2.5 text-right font-normal">Last</th>
              <th scope="col" className="eyebrow px-3 py-2.5 text-right font-normal">Move</th>
              <th scope="col" className="eyebrow px-3 py-2.5 font-normal">Against its own year</th>
              <th scope="col" className="eyebrow px-3 py-2.5 font-normal">Past 3 months</th>
              <th scope="col" className="eyebrow px-5 py-2.5 text-right font-normal">Session</th>
            </tr>
          </thead>
          {board.groups.map((group) => {
            const members = rows.filter((row) => row.group === group.key);
            if (members.length === 0) return null;
            return (
              <tbody key={group.key}>
                <tr>
                  <th scope="rowgroup" colSpan={6}
                      className="eyebrow border-b border-ruleSoft bg-sunken px-5 py-1.5 text-left font-normal">
                    {group.label}
                  </th>
                </tr>
                {members.map((row) => (
                  <BoardRowView key={row.key} row={row} board={board} />
                ))}
              </tbody>
            );
          })}
        </table>
      </ScrollRegion>
    </Card>
  );
}

function BoardRowView({ row, board }: { row: BoardRow; board: MarketBoard }) {
  const said = board.explain.rows[row.key];
  const since = sinceText(row);
  return (
    <tr id={`board-${row.key}`}
        className={cn("scroll-mt-40 border-b border-ruleSoft last:border-0", row.unusual && "bg-raised/40")}>
      <th scope="row" className="px-5 py-2.5 text-left align-top font-normal">
        <div className="flex flex-wrap items-baseline gap-x-2">
          <span className={cn(row.unusual ? "font-semibold text-chalk" : "text-body")}>{row.name}</span>
          <span className="num text-micro text-ash">{row.symbol}</span>
        </div>
        {row.note && <div className="mt-0.5 max-w-xs text-micro leading-snug text-ash">{row.note}</div>}
      </th>
      {row.available ? (
        <>
          <td className="num px-3 py-2.5 text-right align-top">
            <div className="text-body">{levelText(row)}</div>
            <div className="text-micro text-ash">{row.unit}</div>
          </td>
          <td className={cn("num px-3 py-2.5 text-right align-top",
                            row.unusual ? "font-semibold text-chalk" : "text-body")}>
            {said?.moveText ?? "—"}
          </td>
          <td className="px-3 py-2.5 align-top">
            <Percentile row={row} board={board} />
            {since && <div className="mt-1 text-micro text-ash">{since}</div>}
          </td>
          <td className="px-3 py-2.5 align-top">
            <Sparkline values={row.spark} />
          </td>
          <td className="num px-5 py-2.5 text-right align-top text-micro text-ash">
            {dayText(row.asOf)}
          </td>
        </>
      ) : (
        <td colSpan={5} className="px-3 py-2.5 align-top text-micro text-ash">{row.reason}</td>
      )}
    </tr>
  );
}

function Percentile({ row, board }: { row: BoardRow; board: MarketBoard }) {
  const p = row.percentile;
  if (p == null) {
    return <span className="text-micro text-ash">Too little history to say</span>;
  }
  return (
    <div className="flex items-center gap-2">
      <span className="num w-11 shrink-0 text-right text-body">
        {Math.round(p)}<span className="text-ash">{ordinal(Math.round(p))}</span>
      </span>
      {/* A POSITION, NOT A SCORE: where the move sits in its own year, with a
          tick at the line where "unusual" begins. Neutral at every value. */}
      <div aria-hidden className="relative h-1.5 w-20 shrink-0 rounded-full bg-rule">
        <div className="absolute inset-y-0 left-0 rounded-full bg-ash" style={{ width: `${Math.max(2, p)}%` }} />
        <div className="absolute -inset-y-0.5 w-px bg-chalk" style={{ left: `${board.unusualAt}%` }} />
      </div>
      {row.unusual && (
        <span className="rounded-sm border border-ruleStrong px-1.5 text-micro leading-tight text-chalk">
          unusual
        </span>
      )}
      <Explain explain={board.explain.rows[row.key]?.percentile ?? undefined} />
    </div>
  );
}

function Missing({ board, market }: { board: MarketBoard; market: Market }) {
  const missing = board.missing.filter((item) => item.markets.includes(market));
  if (missing.length === 0) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Not on this board, and why</CardTitle>
      </CardHeader>
      <CardBody>
        <ul className="space-y-2">
          {missing.map((item) => (
            <li key={item.key} className="text-meta leading-relaxed">
              <span className="text-body">{item.name}.</span>{" "}
              <span className="text-ash">{item.reason}</span>
            </li>
          ))}
        </ul>
      </CardBody>
    </Card>
  );
}

/** Which kinds of date each filter shows. */
const CALENDAR_FILTERS: { key: string; label: string; kinds: CalendarKind[] }[] = [
  { key: "banks", label: "Central banks", kinds: ["fomc", "bi-rate"] },
  { key: "data", label: "Data releases", kinds: ["cpi", "jobs", "pce", "gdp"] },
  { key: "closed", label: "Exchange holidays", kinds: ["holiday", "early-close"] },
  { key: "earnings", label: "Your watchlist's reports", kinds: ["earnings"] },
];

/**
 * Sixty days of the dates that move markets, filterable by kind, each with what
 * it is and — for FOMC, CPI, jobs and Bank Indonesia — every instrument's line
 * on how its past occurrences went. Closures are the market in view's own. A
 * month beside the list shows the same dates as a calendar, and the filters
 * apply to both; choosing a day there puts that day in the list.
 */
function FullCalendar({ board, market }: { board: MarketBoard; market: Market }) {
  const { calendar, earnings } = useMarketBoard();
  const [shown, setShown] = useState<Set<string>>(() => new Set(CALENDAR_FILTERS.map((f) => f.key)));
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 60_000);
    return () => window.clearInterval(timer);
  }, []);
  const month = useMemo(() => {
    if (calendar.status !== "ready") return [];
    const kinds = new Set(CALENDAR_FILTERS.filter((f) => shown.has(f.key)).flatMap((f) => f.kinds));
    const reports = earningsEvents(null, earnings.status === "ready" ? earnings.data.items : []);
    return eventsFor([...calendar.data.events, ...reports], market).filter((e) => kinds.has(e.kind));
  }, [calendar, earnings, market, shown]);
  const events = useMemo(() => upcoming(month, new Date(now), 60), [month, now]);
  const [picked, setPicked] = useState<string | null>(null);
  const days = byDay(month);
  // A filter can take away everything on the chosen day; the list then goes
  // back to the sixty days rather than showing an empty day.
  const list = picked && days.has(picked) ? days.get(picked) ?? [] : events;
  const showing = picked && days.has(picked) ? picked : null;

  const toggle = (key: string) => setShown((current) => {
    const next = new Set(current);
    if (next.has(key)) next.delete(key); else next.add(key);
    return next;
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>The next 60 days</CardTitle>
        <div role="group" aria-label="Which dates to show" className="flex flex-wrap gap-1">
          {CALENDAR_FILTERS.map((filter) => (
            <Button key={filter.key} variant="chip" size="xs" aria-pressed={shown.has(filter.key)}
                    onClick={() => toggle(filter.key)}>
              {filter.label}
            </Button>
          ))}
        </div>
      </CardHeader>
      <CardBody className="space-y-4">
        {calendar.status === "ready" ? (
          <>
            <div className="grid gap-6 lg:grid-cols-[minmax(0,26rem)_minmax(0,1fr)]">
              <div>
                <CalendarMonth events={month} today={todayIn(new Date(now))} size="full"
                               from={calendar.data.window?.from} through={calendar.data.window?.through}
                               selected={showing} onSelect={setPicked} />
              </div>
              <div className="min-w-0 space-y-2">
                <div className="flex min-h-[24px] items-center justify-between gap-2">
                  <p aria-live="polite" className="text-micro text-ash">
                    {showing ? `Showing ${dayHeading(showing)}` : "The next 60 days"}
                  </p>
                  {showing && (
                    <button type="button" onClick={() => setPicked(null)}
                            className="inline-flex min-h-[24px] items-center text-micro text-tech hover:underline">
                      Back to the next 60 days
                    </button>
                  )}
                </div>
                {list.length > 0
                  ? <CalendarList events={list} kinds={calendar.data.kinds} board={board} />
                  : <p className="text-meta text-ash">Nothing of the kinds chosen in the next 60 days.</p>}
              </div>
            </div>
            <p className="prose-col text-micro leading-snug text-ash">
              Times are on your clock. Transcribed from the{" "}
              {Object.values(calendar.data.sources).map((source, i, all) => (
                <span key={source.url}>
                  <a href={source.url} target="_blank" rel="noopener noreferrer" className="text-tech hover:underline">
                    {source.name.split(",")[0]}
                  </a>
                  {i < all.length - 1 ? ", " : ""}
                </span>
              ))}{" "}
              schedules, checked {dayText(calendar.data.verifiedOn)} {calendar.data.verifiedOn.slice(0, 4)}.
              {calendar.data.pending.length > 0 && ` Not shown: ${calendar.data.pending
                .map((p) => p.note.replace(/\.$/, "")).join("; ")}.`}
            </p>
          </>
        ) : (
          <p className="text-meta text-ash" role="status">
            {calendar.status === "error" ? "The calendar did not load." : "Fetching the calendar…"}
          </p>
        )}
      </CardBody>
    </Card>
  );
}

const HISTORY_TITLES: Record<string, string> = {
  fomc: "FOMC decisions", cpi: "US CPI releases", jobs: "US jobs reports", "bi-rate": "Bank Indonesia decisions",
};

/**
 * How markets moved on the past occurrences of each event, over the two years
 * the board holds. Mostly about as much as on any day — which is the finding,
 * and it is said rather than implied away.
 */
function EventHistory({ board }: { board: MarketBoard }) {
  const kinds = Object.keys(board.eventHistory ?? {});
  if (kinds.length === 0) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>What past event days were like</CardTitle>
      </CardHeader>
      <CardBody className="space-y-4">
        {kinds.map((kind) => (
          <section key={kind} aria-label={HISTORY_TITLES[kind] ?? kind} className="space-y-1.5">
            <h4 className="text-meta font-semibold text-chalk">{HISTORY_TITLES[kind] ?? kind}</h4>
            {board.eventHistory[kind].map((row) => (
              <div key={row.key} className="flex items-start gap-2">
                <p className="prose-col text-meta leading-relaxed text-body">
                  {board.explain.eventHistory?.[kind]?.[row.key]?.reading ?? row.reason}
                </p>
                <Explain explain={board.explain.eventHistory?.[kind]?.[row.key]?.share ?? undefined} />
              </div>
            ))}
          </section>
        ))}
        <Note>
          History over the two years of prices this board holds, never a forecast. Each event is
          read against the session it landed in, and a release on a day the market was shut
          against the next one.
        </Note>
      </CardBody>
    </Card>
  );
}
