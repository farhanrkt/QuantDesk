"use client";

import { RefreshCw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { MarketSwitch } from "@/components/markets/quotes";
import { useFullBoard, useMarketBoard } from "@/components/shell/marketboard";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle, Note } from "@/components/ui/card";
import { Explain } from "@/components/ui/explain";
import { HeadlineList } from "@/components/ui/headlines";
import { ScrollRegion } from "@/components/ui/scroll";
import { Sparkline } from "@/components/ui/sparkline";
import { StateCard } from "@/components/ui/state";
import { fetchMarketHeadlines } from "@/lib/api";
import {
  TOPIC_LABEL, clockText, dayText, headlineTopics, levelText, rowsFor, sinceText,
} from "@/lib/marketboard";
import type { BoardRow, Engine, Market, MarketBoard, MarketHeadlines } from "@/lib/types";
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
      <BoardHeadlines board={board} market={market} />

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

/**
 * The past day's headlines that mention this market and each unusual mover.
 * Fetched after the board, so the quotes never wait on a news feed, and
 * labelled as MENTIONING a market: the app cannot tell which story, if any,
 * moved a price.
 */
export function BoardHeadlines({
  board, market, topics: only, limit,
}: { board: MarketBoard; market: Market; topics?: string[]; limit?: number }) {
  const topics = useMemo(() => only ?? headlineTopics(board, market), [only, board, market]);
  const key = `${market}:${topics.join(",")}`;
  const [state, setState] = useState<Engine<MarketHeadlines>>({ status: "idle" });

  // Keyed by a string, and the request rebuilt from it, so a new array with
  // the same topics on a re-render does not refetch.
  useEffect(() => {
    const [asked, list] = key.split(":");
    const controller = new AbortController();
    setState({ status: "loading" });
    fetchMarketHeadlines(asked as Market, list.split(","), controller.signal)
      .then((data) => { if (!controller.signal.aborted) setState({ status: "ready", data }); })
      .catch((failure) => {
        if (!controller.signal.aborted) {
          setState({ status: "error", failure: { message: failure?.message ?? "Headlines did not load." } });
        }
      });
    return () => controller.abort();
  }, [key]);

  const now = Date.now();
  return (
    <Card>
      <CardHeader>
        <CardTitle>Headlines from the past day</CardTitle>
        <span className="font-mono text-micro text-ash">Google News</span>
      </CardHeader>
      <CardBody className="space-y-4 px-0">
        {state.status === "error" && (
          <p className="px-5 text-meta text-ash">
            {state.failure.message} The board above does not read the news, so nothing on it is affected.
          </p>
        )}
        {(state.status === "idle" || state.status === "loading") && (
          <p className="px-5 text-meta text-ash" role="status">Fetching headlines…</p>
        )}
        {state.status === "ready" && state.data.topics.map((feed) => (
          <section key={feed.topic} aria-labelledby={`headlines-${feed.topic}`}>
            <h3 id={`headlines-${feed.topic}`} className="px-5 pb-1 text-meta font-semibold text-chalk">
              Mentioning {TOPIC_LABEL[feed.topic]?.[market] ?? feed.topic}
            </h3>
            {feed.items.length > 0
              ? <HeadlineList items={limit ? feed.items.slice(0, limit) : feed.items} now={now} />
              : <p className="px-5 text-meta text-ash">{feed.reason}</p>}
          </section>
        ))}
        <div className="px-5">
          <Note>
            Third-party headlines, matched by search and unverified. A headline that mentions oil
            on a day oil fell is not evidence of why it fell.
          </Note>
        </div>
      </CardBody>
    </Card>
  );
}
