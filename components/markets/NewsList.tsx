"use client";

import { useEffect, useMemo, useState } from "react";
import { Card, CardBody, CardHeader, CardTitle, Note } from "@/components/ui/card";
import { HeadlineList } from "@/components/ui/headlines";
import { fetchMarketHeadlines } from "@/lib/api";
import { TOPIC_LABEL, headlineTopics } from "@/lib/marketboard";
import type { Engine, Market, MarketBoard, MarketHeadlines } from "@/lib/types";

/**
 * The past day's headlines that mention this market and each unusual mover.
 *
 * Fetched after the board, so the prices never wait on a news feed, and
 * labelled as MENTIONING a market: the app cannot tell which story, if any,
 * moved a price. US stories come from Yahoo Finance with a thumbnail; the
 * Indonesian press comes from Google News as text, because Yahoo has none of it.
 */
export function useMarketHeadlines(market: Market, topics: string[]): Engine<MarketHeadlines> {
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
  return state;
}

function Feeds({
  state, market, limit, compact,
}: { state: Engine<MarketHeadlines>; market: Market; limit?: number; compact?: boolean }) {
  const now = Date.now();
  const pad = compact ? "text-meta text-ash" : "px-5 text-meta text-ash";
  if (state.status === "error") {
    return (
      <p className={pad}>
        {state.failure.message} Nothing else here reads the news, so every figure is unaffected.
      </p>
    );
  }
  if (state.status !== "ready") {
    return <p className={pad} role="status">Fetching headlines…</p>;
  }
  return (
    <div className="space-y-3">
      {state.data.topics.map((feed) => (
        <section key={feed.topic} aria-label={`Headlines mentioning ${TOPIC_LABEL[feed.topic]?.[market] ?? feed.topic}`}>
          <h4 className={compact ? "mb-1 text-meta font-semibold text-chalk"
                                 : "px-5 pb-1 text-meta font-semibold text-chalk"}>
            Mentioning {TOPIC_LABEL[feed.topic]?.[market] ?? feed.topic}
            <span className="ml-1.5 font-normal text-ash">· {feed.source}</span>
          </h4>
          {feed.items.length > 0
            ? <HeadlineList items={limit ? feed.items.slice(0, limit) : feed.items} now={now} compact={compact} />
            : <p className={compact ? "text-meta text-ash" : "px-5 text-meta text-ash"}>{feed.reason}</p>}
        </section>
      ))}
    </div>
  );
}

/** Headlines for the side panel and the band: no card of their own, small thumbnails. */
export function NewsCompact({
  board, market, limit = 4,
}: { board: MarketBoard; market: Market; limit?: number }) {
  const topics = useMemo(() => headlineTopics(board, market, 2), [board, market]);
  const state = useMarketHeadlines(market, topics);
  return <Feeds state={state} market={market} limit={limit} compact />;
}

/** Headlines as a card, for the Today view and the landing. */
export function NewsCard({
  board, market, topics: only, limit,
}: { board: MarketBoard; market: Market; topics?: string[]; limit?: number }) {
  const topics = useMemo(() => only ?? headlineTopics(board, market), [only, board, market]);
  const state = useMarketHeadlines(market, topics);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Headlines from the past day</CardTitle>
      </CardHeader>
      <CardBody className="space-y-4 px-0">
        <Feeds state={state} market={market} limit={limit} />
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
