"use client";

import { AlertTriangle, ChevronRight } from "lucide-react";
import { useState } from "react";
import { AnomalyPanel } from "@/components/AnomalyPanel";
import { ConfluenceRail } from "@/components/ConfluenceRail";
import { HoldingHorizonBar } from "@/components/HoldingHorizonBar";
import { EventStudyPanel } from "@/components/EventStudyPanel";
import { NewsPanel } from "@/components/NewsPanel";
import { PeersPanel } from "@/components/PeersPanel";
import { PortfolioPanel } from "@/components/PortfolioPanel";
import { PreTradePanel } from "@/components/PreTradePanel";
import { QualityPanel } from "@/components/QualityPanel";
import { RankingPanel } from "@/components/RankingPanel";
import { ScreenerPanel } from "@/components/ScreenerPanel";
import { SynthesisPanel } from "@/components/SynthesisPanel";
import { ThesisPanel } from "@/components/ThesisPanel";
import { TechnicalPanel } from "@/components/TechnicalPanel";
import { TickerBar } from "@/components/TickerBar";
import { ManualRescue } from "@/components/ValuationControls";
import { ValuationPanel } from "@/components/ValuationPanel";
import { Card } from "@/components/ui/card";
import { DetailProvider, DetailToggle, useDetailLevel } from "@/components/ui/explain";
import { HorizonProvider, useHoldingHorizon } from "@/components/ui/horizon";
import { PanelSkeleton } from "@/components/ui/skeleton";
import { TabPanel, Tabs } from "@/components/ui/tabs";
import {
  useEngines, useEventStudy, usePeers, usePortfolio, type RunOptions,
} from "@/lib/api";
import type { Engine, EngineFailure } from "@/lib/types";

const INITIAL: RunOptions = {
  // `range` drives the technical lens. 5y is the shortest window where
  // drawdown depth and rolling multi-year returns mean anything.
  ticker: "", market: "US", period: "2y", range: "5y", mode: "threshold",
  contamination: 0.02, madK: 3.0, scoreThreshold: -0.10,
};

// LABELLED BY THE QUESTION, NOT THE METHOD. "Flow · anomalies" and "Intrinsic
// value" name the technique, which tells a newcomer nothing about whether the
// tab is worth opening. The hues are the lens identity colours from
// `ConfluenceRail.LENS_HUE`, so a chip in the rail and the tab that owns it are
// the same colour.
const TABS = [
  { id: "flow", label: "Who is trading it", accent: "#2FBFA4" },
  { id: "trend", label: "What the price did", accent: "#6B9BFF" },
  { id: "value", label: "What it is worth", accent: "#E8B44C" },
  { id: "quality", label: "Are the numbers real", accent: "#C9A227" },
  // The fourth question this app can answer — how does it sit against what I
  // already own — and the only one that needs an input other than a ticker.
  { id: "portfolio", label: "Portfolio fit", accent: "#6FD0C0" },
  // Last, because it is the only tab that asks the reader for something rather
  // than telling them something, and it is meant to be reached after the rest
  // has been read.
  { id: "thesis", label: "Thesis", accent: "#A78BFA" },
  { id: "screen", label: "Scan & rank", accent: "#A78BFA" },
];

/** One wrapper so all three panels handle loading and failure identically. */
function Panel<T>({
  state, children, rescue,
}: {
  state: Engine<T>;
  children: (data: T) => React.ReactNode;
  /** Rendered inside the error card when the failure is a fixable data gap. */
  rescue?: (failure: EngineFailure) => React.ReactNode;
}) {
  if (state.status === "loading") return <Card><PanelSkeleton /></Card>;
  if (state.status === "error") {
    const { failure } = state;
    return (
      <Card tone="bad" className="bg-dist/5">
        <div className="flex gap-3.5 p-5">
          <AlertTriangle aria-hidden className="mt-0.5 h-5 w-5 shrink-0 text-dist" />
          <div className="min-w-0 flex-1">
            <h3 className="mb-1.5 text-lead text-dist">This engine could not run</h3>
            <p className="prose-col text-base leading-relaxed text-body">{failure.message}</p>
            {/* A data gap the user can close is a different problem from a
                business the model cannot value. Only the former gets a form —
                and the form has to be here, because the panel that normally
                holds it never rendered. */}
            {failure.manualRequired && (
              <>
                <p className="prose-col mt-2.5 text-meta leading-relaxed text-warn">
                  Yahoo is missing{" "}
                  {failure.missing?.length ? failure.missing.join(", ") : "a required figure"} for
                  this listing. Enter it below to value the company anyway.
                </p>
                {rescue?.(failure)}
              </>
            )}
          </div>
        </div>
      </Card>
    );
  }
  if (state.status === "ready") return <>{children(state.data)}</>;
  return null;
}

export default function Home() {
  const {
    anomaly, technical, valuation, quality, news, synthesis, preTrade,
    run, refineValuation, refineTechnical, csvUrl,
  } = useEngines();
  const { state: eventStudy, validate, reset: resetEventStudy } = useEventStudy();
  const { state: peers, compare, reset: resetPeers } = usePeers();
  const { state: portfolio, compare: comparePortfolio,
          reset: resetPortfolio } = usePortfolio();
  // The ticker bar is controlled from here so the screener can drive it too.
  const [opts, setOpts] = useState<RunOptions>(INITIAL);
  // The last SUBMITTED symbol, which is not what is currently typed in the box.
  const [ticker, setTicker] = useState("");
  // TREND, NOT FLOW. The first drill-down a newcomer takes should land on the
  // strongest evidence in the app, and Flow is the weakest: it is the densest
  // lens to read and the one whose own event study frequently returns "no
  // significant effect". The Trend tab opens on its long-horizon section —
  // rolling returns, drawdown, relative strength — which is the most useful and
  // least misreadable surface here.
  const [tab, setTab] = useState("trend");
  // Simple/Detailed is app-wide rather than per-panel. Someone who wants the
  // short version of the technical lens wants the short version of the quality
  // lens too, and a per-panel switch makes them say so four times.
  const [detail, setDetail] = useDetailLevel();
  // How long the reader means to hold, stated once and read by the horizon bar
  // and the rolling-return table. It never reaches the API: every horizon the
  // loaded history supports is already in the technical payload, so changing it
  // selects rather than re-runs.
  const [horizon, setHorizon] = useHoldingHorizon();

  // PROGRESS, NOT JUST BUSY. One shared spinner gated on the SLOWEST lens meant a
  // ten-to-sixteen-second first run behind a dead button with nothing to say
  // which engine was holding it up. The count is reported to the ticker bar and
  // the per-lens state to the rail, so the wait is legible while it happens.
  const lenses = [anomaly, technical, valuation, quality];
  const busy = lenses.some((s) => s.status === "loading");
  const settled = lenses.filter((s) => s.status === "ready" || s.status === "error").length;
  const progress = busy ? { done: settled, total: lenses.length } : undefined;
  const started = anomaly.status !== "idle";

  const handleRun = (next: RunOptions) => {
    const cleaned = { ...next, ticker: next.ticker.trim().toUpperCase() };
    setOpts(cleaned);
    setTicker(cleaned.ticker);
    // A study belongs to the ticker it was run for; carrying one across would
    // put another company's abnormal returns under this company's header.
    resetEventStudy();
    resetPeers();
    // A comparison belongs to the candidate it was run for; carrying one across
    // would put another company's correlations under this company's header.
    resetPortfolio();
    run(cleaned);
  };

  /** A screener hit, loaded into the full three-engine view. Detection settings
   *  carry over; the market is inferred from the symbol's own suffix. */
  const handleSelect = (symbol: string) => {
    handleRun({
      ...opts,
      ticker: symbol,
      market: symbol.toUpperCase().endsWith(".JK") ? "ID" : "US",
    });
    setTab("trend");
  };

  // What the engines actually resolved to, which may carry a suffix the user
  // did not type. Showing the resolved symbol is the point of the fix.
  const resolvedTicker =
    anomaly.status === "ready" ? anomaly.data.ticker
      : technical.status === "ready" ? technical.data.ticker
        : valuation.status === "ready" ? valuation.data.ticker
          : ticker;

  return (
    <DetailProvider level={detail}>
    <HorizonProvider value={horizon}>
    <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      {/* THE HEADER STOPPED EXPLAINING ITSELF AT LENGTH. v1 spent a 68-word
          paragraph up here on how the app works, in 12px grey, above the fold,
          before the reader had entered a ticker or seen a single number — the
          worst possible moment to teach anything. The tagline says what the app
          does in one line; the mechanics moved to a disclosure that a reader
          opens when they have a reason to care, and Guided mode explains itself
          in place, beside the numbers it applies to. */}
      <header className="mb-8 border-b border-rule pb-6">
        <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-4">
          <div className="min-w-0">
            <h1 className="font-mono tracking-[0.16em]">QUANTDESK</h1>
            <p className="mt-1.5 text-base text-ash">
              Four models read the same stock from different data — and say where they
              disagree.
            </p>
          </div>
          <DetailToggle level={detail} onChange={setDetail} />
        </div>
        <details className="group mt-4">
          <summary className="inline-flex h-8 cursor-pointer list-none items-center gap-2
                              rounded text-meta text-ash transition-colors hover:text-chalk
                              focus-visible:outline-none focus-visible:ring-2
                              focus-visible:ring-tech">
            <ChevronRight aria-hidden
                          className="h-4 w-4 shrink-0 transition-transform group-open:rotate-90" />
            How to read this
          </summary>
          <div className="prose-col mt-3 space-y-2.5 pl-6 text-meta leading-relaxed text-ash">
            <p>
              Flow reads volume, Trend reads price, Value reads the cash flows, Quality reads
              the balance sheet. Where methods that share no inputs land in the same place,
              that is worth more than any one of them shouting — and the app measures how much
              more rather than assuming it.
            </p>
            <p>
              Every number carries an{" "}
              <span className="font-semibold text-body">i</span> that explains what it
              measures, whether this value is good or bad, and what would make you act
              differently — or admits that nothing would.{" "}
              <span className="font-semibold text-body">Guided</span> puts those readings on
              the page and folds the expert controls away;{" "}
              <span className="font-semibold text-body">Full</span> is every control and every
              indicator.
            </p>
          </div>
        </details>
      </header>

      <div className="mb-8">
        <TickerBar opts={opts} onChange={setOpts} onRun={handleRun} busy={busy}
                   progress={progress} />
      </div>

      {!started ? (
        <div className="space-y-6">
          <div className="rounded-xl border border-dashed border-rule px-6 py-16 text-center">
            <h2 className="mb-2">Enter a ticker to begin</h2>
            <p className="mx-auto max-w-measure text-base leading-relaxed text-ash">
              Type a symbol above, or pick one of the presets. Indonesian listings take the{" "}
              <code className="rounded bg-sunken px-1.5 py-0.5 font-mono text-meta text-body">.JK</code>{" "}
              suffix; crypto takes a pair such as{" "}
              <code className="rounded bg-sunken px-1.5 py-0.5 font-mono text-meta text-body">BTC-USD</code>.
            </p>
          </div>
          <RankingPanel onSelect={handleSelect} />
        </div>
      ) : (
        <div className="space-y-6">
          <ConfluenceRail ticker={resolvedTicker} anomaly={anomaly}
                          technical={technical} valuation={valuation}
                          quality={quality} />

          {/* The frame everything below is read through: what this length of
              ownership has historically been like. Above the synthesis because
              it is neither a summary nor an objection — the synthesis then says
              what the lenses report, and the pre-trade panel what argues
              against acting on them. */}
          <HoldingHorizonBar state={technical} horizon={horizon} onHorizon={setHorizon} />

          {/* Reads the assembled payload, so it can only appear once every leg
              has settled. That is the right coupling: a summary of four lenses
              that renders before three of them have answered would be
              describing a picture that does not exist yet. */}
          {synthesis && <SynthesisPanel data={synthesis} />}

          {/* AFTER the synthesis, deliberately. The synthesis describes what the
              four lenses reported; this names what would argue against acting on
              it. A reader should meet the description before the objections to
              it, which is the same ordering the synthesis uses internally when
              it puts its blind spots above its next steps.

              It is above the tabs rather than inside a lens because a condition
              that only appears once you open the panel that already worried you
              is not a veto — it is a footnote to a decision already made. */}
          {preTrade && <PreTradePanel data={preTrade} />}

          <div>
            <Tabs tabs={TABS} active={tab} onChange={setTab} />
            <div className="pt-6">
              <TabPanel id="flow" active={tab}>
                <div className="space-y-4">
                  <Panel state={anomaly}>{(d) => <AnomalyPanel data={d} />}</Panel>
                  <EventStudyPanel
                    state={eventStudy}
                    ticker={resolvedTicker}
                    onValidate={() => validate({
                      ticker: opts.ticker, market: opts.market,
                      mode: opts.mode, scoreThreshold: opts.scoreThreshold,
                    })}
                  />
                  <NewsPanel state={news} />
                </div>
              </TabPanel>
              <TabPanel id="trend" active={tab}>
                <div className="space-y-4">
                  <Panel state={technical}>
                    {(d) => (
                      <TechnicalPanel data={d} onApply={refineTechnical}
                                      busy={technical.status === "loading"} />
                    )}
                  </Panel>
                  {/* Sits on the Trend tab because the seven signals it compares
                      are price and volume — the same data this lens reads. It
                      would be a category error on the Value tab, where nothing
                      has a peer comparison. */}
                  <PeersPanel state={peers} ticker={resolvedTicker}
                              onCompare={(universe) => compare({
                                ticker: opts.ticker, market: opts.market, universe,
                              })} />
                </div>
              </TabPanel>
              <TabPanel id="value" active={tab}>
                <Panel
                  state={valuation}
                  rescue={(failure) => (
                    <ManualRescue suggested={failure.suggested ?? {}}
                                  engine={failure.engine}
                                  busy={valuation.status === "loading"}
                                  onApply={refineValuation} />
                  )}
                >
                  {(d) => (
                    <ValuationPanel data={d} onApply={refineValuation}
                                    busy={valuation.status === "loading"}
                                    csvUrl={csvUrl()} />
                  )}
                </Panel>
              </TabPanel>
              <TabPanel id="quality" active={tab}>
                <Panel state={quality}>{(d) => <QualityPanel data={d} />}</Panel>
              </TabPanel>
              {/* THE SNAPSHOT IS ASSEMBLED HERE, FROM WHAT IS ON SCREEN. A
                  thesis is frozen against the numbers the reader was actually
                  looking at, so these are read from the settled legs rather
                  than re-fetched — a snapshot taken from a second request
                  would record a page nobody saw. */}
              <TabPanel id="thesis" active={tab}>
                <ThesisPanel
                  ticker={resolvedTicker}
                  snapshot={{
                    impliedGrowth: valuation.status === "ready"
                      ? valuation.data.baseCase?.impliedGrowth ?? null : null,
                    assumedGrowth: valuation.status === "ready"
                      ? valuation.data.baseCase?.assumedGrowth ?? null : null,
                    price: valuation.status === "ready" ? valuation.data.price : null,
                    priceLabel: valuation.status === "ready"
                      ? valuation.data.priceLabel : null,
                    maxDrawdown: technical.status === "ready"
                      ? technical.data.longTerm?.drawdown?.maxDrawdown ?? null : null,
                    worstAtHorizon: technical.status === "ready"
                      ? (technical.data.longTerm?.rollingReturns ?? [])
                          .find((r) => r.years === horizon && r.usable !== false)?.worst ?? null
                      : null,
                    firedChecks: (preTrade?.flags ?? []).map((f) => f.explain.label),
                  }}
                />
              </TabPanel>
              <TabPanel id="portfolio" active={tab}>
                <PortfolioPanel
                  state={portfolio}
                  ticker={resolvedTicker}
                  onCompare={(holdings, weights) => comparePortfolio({
                    candidate: opts.ticker, market: opts.market, holdings, weights,
                  })}
                />
              </TabPanel>
              <TabPanel id="screen" active={tab}>
                <div className="space-y-8">
                  <RankingPanel onSelect={handleSelect} />
                  {/* The anomaly screener still answers a question the ranking
                      cannot: "has anything UNUSUAL just happened here?" — a
                      one-off event rather than a standing characteristic. It
                      keeps its own multiple-testing correction, so it stays. */}
                  <div>
                    <h2 className="mb-3">Or scan for fresh unusual activity instead</h2>
                    <ScreenerPanel onSelect={handleSelect} />
                  </div>
                </div>
              </TabPanel>
            </div>
          </div>
        </div>
      )}

      <footer className="hairline prose-col mt-16 pt-5 text-meta leading-relaxed text-faint">
        Prices and filings from Yahoo Finance, unaudited and occasionally incomplete for IDX
        listings. Educational and research use only — not investment advice.
      </footer>
    </main>
    </HorizonProvider>
    </DetailProvider>
  );
}
