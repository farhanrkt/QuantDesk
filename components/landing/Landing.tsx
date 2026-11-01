"use client";

import {
  ArrowRight, BookOpen, Clock, Columns3, Compass, Layers, Radar, ScanSearch, Star, Trash2,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { TickerBar } from "@/components/TickerBar";
import { useWorkspace } from "@/components/shell/workspace";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Kbd } from "@/components/ui/kbd";
import { useScan, type RunOptions } from "@/lib/api";
import { palette } from "@/lib/palette";
import { marketOf, resolveSymbol } from "@/lib/symbols";
import { RUN_DEFAULTS, compareHref, marketsHref, stockHref } from "@/lib/url";
import { MarketsToday } from "@/components/landing/MarketsToday";
import { WatchlistRank } from "@/components/landing/WatchlistRank";

/**
 * The first screen, before a ticker.
 *
 * WHAT IT REPLACED. A dashed box reading "Enter a ticker to begin", then three
 * full market-wide panels stacked underneath — the scanner, a ranking form and
 * an exposure scan — each with its own controls and its own paragraph, so the
 * first thing a newcomer met was the densest part of the app and the second
 * was a decision about which index to scan. And once a ticker was entered there
 * was no way back to any of it.
 *
 * WHAT IT IS NOW. One question — which company? — answered three ways: type
 * it, pick a preset, or open one you have looked at before. Then what the app
 * does, in three lines, with the field manual for anyone who wants the rest.
 * The market tools are one click away as named destinations rather than
 * expanded in place.
 *
 * NO NUMBERS. The landing shows nothing about any company or market: there is
 * no "today's movers", no index strip, no featured stock. A number on this page
 * would be a number nobody asked about, presented without the four lenses this
 * app exists to put around every figure.
 */
const STEPS = [
  {
    title: "Four models, two kinds of data",
    body: "Order flow and price trend read the trading record; intrinsic value and accounting "
      + "quality read the filings. Agreement between those two families is worth more than "
      + "four lenses saying the same thing twice.",
  },
  {
    title: "Where they disagree is the finding",
    body: "Nothing here adds the four up. The summary names what they agree on, where they "
      + "pull against each other, and what none of them can see about this company.",
  },
  {
    title: "Then what would stop a careful buyer",
    body: "Conditions that argue against acting, each beside how often it fires across a real "
      + "market — so a warning true of a third of all companies reads as the base rate it is.",
  },
];

const TOOLS = [
  { href: marketsHref("rank"), icon: Layers, hue: palette.trend, title: "Rank a universe",
    body: "Seven price signals across the Dow, Nasdaq-100, IDX30 or LQ45 — a shortlist, with the "
      + "published finding that the order predicts nothing." },
  { href: marketsHref("screener"), icon: Radar, hue: palette.flow, title: "Scan for unusual activity",
    body: "Up to twenty names, each against its own history, with the number of hits you would "
      + "expect from noise." },
  { href: marketsHref("exposure"), icon: Compass, hue: palette.drivers, title: "What a market moves with",
    body: "Every name in a list against the factors whose betas were measured to persist." },
  { href: compareHref([]), icon: Columns3, hue: palette.thesis, title: "Compare companies",
    body: "Two to four names read lens by lens in parallel columns. Nothing is summed." },
];

export function Landing() {
  const router = useRouter();
  const { watchlist, recent, toggleWatch, clearRecent } = useWorkspace();
  const [opts, setOpts] = useState<RunOptions>({ ticker: "", market: "US", ...RUN_DEFAULTS });
  // The local scan report, if this machine has one. On the deployed app the
  // route answers `available: false` and the card simply does not appear.
  const { state: scan } = useScan("ID");
  const scanAvailable = scan.status === "ready" && scan.data.available;

  const open = (next: RunOptions) => {
    const symbol = resolveSymbol(next.ticker, next.market);
    if (symbol) router.push(stockHref(symbol));
  };

  return (
    <div className="space-y-12">
      {/* --------------------------------------------------------------- hero */}
      <section className="mx-auto max-w-3xl pt-4 text-center sm:pt-10">
        <p className="eyebrow mb-4">US and Indonesian listings · research, not advice</p>
        <h1 className="text-balance sm:text-display">
          Read one company through four models that share no data.
        </h1>
        <p className="mx-auto mt-4 max-w-measure text-lead text-body">
          See where they agree, where they disagree, and what none of them can tell you.
        </p>
        <div className="mx-auto mt-8 max-w-2xl text-left">
          <TickerBar opts={opts} onChange={setOpts} onRun={open} busy={false} autoFocus />
        </div>
        <p className="mt-4 text-meta text-ash">
          Know the company but not the ticker? Press <Kbd keys={["mod", "K"]} className="mx-1 align-middle" />
          and type its name.
        </p>
      </section>

      {/* ------------------------------------------------------ markets today */}
      <MarketsToday />

      {/* ---------------------------------------------------------- your desk */}
      {(watchlist.length > 0 || recent.length > 0) && (
        <section aria-labelledby="desk-title" className="space-y-3">
          <h2 id="desk-title">Your desk</h2>
          <p className="max-w-measure text-meta text-ash">
            Kept in this browser only. Nothing here is sent anywhere unless you press a button
            that says so.
          </p>
          <div className="grid gap-4 lg:grid-cols-2">
            {watchlist.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Star aria-hidden className="h-4 w-4 text-ash" /> Watchlist
                  </CardTitle>
                  <span className="font-mono text-micro text-ash">{watchlist.length} of 50</span>
                </CardHeader>
                <CardBody className="space-y-4">
                  <SymbolList symbols={watchlist}
                              onRemove={(s) => toggleWatch(s)} removeLabel="Remove from watchlist" />
                  <WatchlistRank symbols={watchlist} />
                </CardBody>
              </Card>
            )}
            {recent.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Clock aria-hidden className="h-4 w-4 text-ash" /> Recently opened
                  </CardTitle>
                  <button type="button" onClick={clearRecent}
                          className="inline-flex min-h-[24px] items-center rounded px-1.5 text-micro text-ash
                                     hover:text-chalk focus:outline-none focus-visible:ring-2 focus-visible:ring-tech">
                    Clear
                  </button>
                </CardHeader>
                <CardBody>
                  <SymbolList symbols={recent} />
                  {recent.length >= 2 && (
                    <Link href={compareHref(recent.slice(0, 4))}
                          className="mt-4 inline-flex items-center gap-1.5 text-meta text-tech hover:underline">
                      Compare the last {Math.min(4, recent.length)} side by side
                      <ArrowRight aria-hidden className="h-3.5 w-3.5" />
                    </Link>
                  )}
                </CardBody>
              </Card>
            )}
          </div>
        </section>
      )}

      {/* ------------------------------------------------------- how to read */}
      <section aria-labelledby="how-title" className="space-y-4">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 id="how-title">How to read it</h2>
          <a href="/docs/field-manual.html"
             className="inline-flex items-center gap-1.5 text-meta text-tech hover:underline">
            <BookOpen aria-hidden className="h-4 w-4" />
            The field manual assumes no finance at all
          </a>
        </div>
        <ol className="grid gap-4 md:grid-cols-3">
          {STEPS.map((step, i) => (
            <li key={step.title} className="rounded-lg border border-rule bg-panel p-5">
              <span className="num text-meta text-faint">0{i + 1}</span>
              <h3 className="mt-2">{step.title}</h3>
              <p className="mt-2 text-meta leading-relaxed text-body">{step.body}</p>
            </li>
          ))}
        </ol>
      </section>

      {/* --------------------------------------------------------- the tools */}
      <section aria-labelledby="tools-title" className="space-y-4">
        <h2 id="tools-title">Across a whole market</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {scanAvailable && (
            <ToolCard href={marketsHref("scan")} icon={ScanSearch} hue={palette.private}
                      title="Latest local scan"
                      body="The private whole-market sweep run on this machine. Every score ships with the null result above it." />
          )}
          {TOOLS.map((tool) => <ToolCard key={tool.title} {...tool} />)}
        </div>
      </section>
    </div>
  );
}

function ToolCard({
  href, icon: Icon, hue, title, body,
}: { href: string; icon: typeof Layers; hue: string; title: string; body: string }) {
  return (
    <Link href={href}
          className="group flex flex-col rounded-lg border border-rule bg-panel p-5 transition-colors
                     hover:border-ruleStrong hover:bg-raised focus:outline-none focus-visible:ring-2
                     focus-visible:ring-tech">
      <Icon aria-hidden className="h-5 w-5" style={{ color: hue }} />
      <span className="mt-3 text-h3 font-semibold text-chalk">{title}</span>
      <span className="mt-1.5 flex-1 text-meta leading-relaxed text-ash">{body}</span>
      <span className="mt-4 inline-flex items-center gap-1 text-meta text-tech">
        Open <ArrowRight aria-hidden className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
      </span>
    </Link>
  );
}

function SymbolList({
  symbols, onRemove, removeLabel,
}: { symbols: string[]; onRemove?: (s: string) => void; removeLabel?: string }) {
  return (
    <ul className="flex flex-wrap gap-2">
      {symbols.map((s) => (
        <li key={s} className="inline-flex items-center rounded-lg border border-rule bg-sunken">
          <Link href={stockHref(s)}
                className="num inline-flex h-9 items-center gap-2 rounded-lg px-3 text-meta font-medium
                           text-body hover:text-chalk focus:outline-none focus-visible:ring-2
                           focus-visible:ring-tech">
            {s}
            <span className="text-micro text-faint">{marketOf(s) === "ID" ? "IDX" : "US"}</span>
          </Link>
          {onRemove && (
            <button type="button" onClick={() => onRemove(s)} aria-label={`${removeLabel} ${s}`}
                    className="mr-1 inline-flex h-7 w-7 items-center justify-center rounded text-faint
                               hover:text-dist focus:outline-none focus-visible:ring-2 focus-visible:ring-tech">
              <Trash2 aria-hidden className="h-3.5 w-3.5" />
            </button>
          )}
        </li>
      ))}
    </ul>
  );
}
