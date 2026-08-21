"use client";

import { AlertTriangle } from "lucide-react";
import { useState } from "react";
import { AnomalyPanel } from "@/components/AnomalyPanel";
import { ConfluenceRail } from "@/components/ConfluenceRail";
import { EventStudyPanel } from "@/components/EventStudyPanel";
import { NewsPanel } from "@/components/NewsPanel";
import { QualityPanel } from "@/components/QualityPanel";
import { RankingPanel } from "@/components/RankingPanel";
import { ScreenerPanel } from "@/components/ScreenerPanel";
import { TechnicalPanel } from "@/components/TechnicalPanel";
import { TickerBar } from "@/components/TickerBar";
import { ManualRescue } from "@/components/ValuationControls";
import { ValuationPanel } from "@/components/ValuationPanel";
import { Card } from "@/components/ui/card";
import { DetailProvider, DetailToggle, useDetailLevel } from "@/components/ui/explain";
import { PanelSkeleton } from "@/components/ui/skeleton";
import { Tabs } from "@/components/ui/tabs";
import { useEngines, useEventStudy, type RunOptions } from "@/lib/api";
import type { Engine, EngineFailure } from "@/lib/types";

const INITIAL: RunOptions = {
  // `range` drives the technical lens. 5y is the shortest window where
  // drawdown depth and rolling multi-year returns mean anything.
  ticker: "", market: "US", period: "2y", range: "5y", mode: "threshold",
  contamination: 0.02, madK: 3.0, scoreThreshold: -0.10,
};

const TABS = [
  { id: "flow", label: "Flow · anomalies", accent: "#35C4A8" },
  { id: "trend", label: "Technicals", accent: "#5B8DEF" },
  { id: "value", label: "Intrinsic value", accent: "#E8B44C" },
  { id: "quality", label: "Quality", accent: "#F2C14E" },
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
      <Card className="border-dist/40 bg-dist/5">
        <div className="flex gap-3 p-5">
          <AlertTriangle aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-dist" />
          <div className="min-w-0 flex-1">
            <div className="eyebrow mb-1 text-dist">This engine could not run</div>
            <p className="text-sm leading-relaxed text-chalk/80">{failure.message}</p>
            {/* A data gap the user can close is a different problem from a
                business the model cannot value. Only the former gets a form —
                and the form has to be here, because the panel that normally
                holds it never rendered. */}
            {failure.manualRequired && (
              <>
                <p className="mt-2 text-xs leading-relaxed text-warn">
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
    anomaly, technical, valuation, quality, news,
    run, refineValuation, refineTechnical, csvUrl,
  } = useEngines();
  const { state: eventStudy, validate, reset: resetEventStudy } = useEventStudy();
  // The ticker bar is controlled from here so the screener can drive it too.
  const [opts, setOpts] = useState<RunOptions>(INITIAL);
  // The last SUBMITTED symbol, which is not what is currently typed in the box.
  const [ticker, setTicker] = useState("");
  const [tab, setTab] = useState("flow");
  // Simple/Detailed is app-wide rather than per-panel. Someone who wants the
  // short version of the technical lens wants the short version of the quality
  // lens too, and a per-panel switch makes them say so four times.
  const [detail, setDetail] = useDetailLevel();

  const busy = [anomaly, technical, valuation].some((s) => s.status === "loading");
  const started = anomaly.status !== "idle";

  const handleRun = (next: RunOptions) => {
    const cleaned = { ...next, ticker: next.ticker.trim().toUpperCase() };
    setOpts(cleaned);
    setTicker(cleaned.ticker);
    // A study belongs to the ticker it was run for; carrying one across would
    // put another company's abnormal returns under this company's header.
    resetEventStudy();
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
    setTab("flow");
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
    <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <header className="mb-8 border-b border-rule pb-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="font-mono text-2xl font-semibold tracking-[0.22em]">QUANTDESK</h1>
            <p className="eyebrow mt-2">
              Flow · Trend · Value · Quality — US &amp; IDX
            </p>
          </div>
          <div className="flex flex-col items-end gap-3">
            <DetailToggle level={detail} onChange={setDetail} />
            <p className="max-w-sm text-xs leading-relaxed text-ash">
              Four models read the same ticker from different data. Where they agree is more
              interesting than what any one of them says alone — with the caveat that they are
              not equally independent. Every number has an{" "}
              <span className="text-chalk/80">i</span> beside it explaining what it means.
            </p>
          </div>
        </div>
      </header>

      <div className="mb-8">
        <TickerBar opts={opts} onChange={setOpts} onRun={handleRun} busy={busy} />
      </div>

      {!started ? (
        <div className="space-y-6">
          <div className="rounded border border-dashed border-rule px-6 py-16 text-center">
            <p className="eyebrow mb-2">No ticker loaded</p>
            <p className="mx-auto max-w-md text-sm leading-relaxed text-ash">
              Enter a symbol above, or pick one of the presets. Indonesian listings take the{" "}
              <code className="font-mono text-chalk/80">.JK</code> suffix; crypto takes a pair such
              as <code className="font-mono text-chalk/80">BTC-USD</code>.
            </p>
          </div>
          <RankingPanel onSelect={handleSelect} />
        </div>
      ) : (
        <div className="space-y-6">
          <ConfluenceRail ticker={resolvedTicker} anomaly={anomaly}
                          technical={technical} valuation={valuation}
                          quality={quality} />

          <div>
            <Tabs tabs={TABS} active={tab} onChange={setTab} />
            <div className="pt-5">
              {tab === "flow" && (
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
              )}
              {tab === "trend" && (
                <Panel state={technical}>
                  {(d) => (
                    <TechnicalPanel data={d} onApply={refineTechnical}
                                    busy={technical.status === "loading"} />
                  )}
                </Panel>
              )}
              {tab === "value" && (
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
              )}
              {tab === "quality" && (
                <Panel state={quality}>{(d) => <QualityPanel data={d} />}</Panel>
              )}
              {tab === "screen" && (
                <div className="space-y-8">
                  <RankingPanel onSelect={handleSelect} />
                  {/* The anomaly screener still answers a question the ranking
                      cannot: "has anything UNUSUAL just happened here?" — a
                      one-off event rather than a standing characteristic. It
                      keeps its own multiple-testing correction, so it stays. */}
                  <div>
                    <h2 className="eyebrow mb-3">
                      Or scan for fresh unusual activity instead
                    </h2>
                    <ScreenerPanel onSelect={handleSelect} />
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      <footer className="hairline mt-16 pt-5 text-xs leading-relaxed text-ash">
        Prices and filings from Yahoo Finance, unaudited and occasionally incomplete for IDX
        listings. Educational and research use only — not investment advice.
      </footer>
    </main>
    </DetailProvider>
  );
}
