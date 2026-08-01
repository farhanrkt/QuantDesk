"use client";

import { AlertTriangle } from "lucide-react";
import { useState } from "react";
import { AnomalyPanel } from "@/components/AnomalyPanel";
import { ConfluenceRail } from "@/components/ConfluenceRail";
import { NewsPanel } from "@/components/NewsPanel";
import { ScreenerPanel } from "@/components/ScreenerPanel";
import { TechnicalPanel } from "@/components/TechnicalPanel";
import { TickerBar } from "@/components/TickerBar";
import { ManualRescue } from "@/components/ValuationControls";
import { ValuationPanel } from "@/components/ValuationPanel";
import { Card } from "@/components/ui/card";
import { PanelSkeleton } from "@/components/ui/skeleton";
import { Tabs } from "@/components/ui/tabs";
import { useEngines, type RunOptions } from "@/lib/api";
import type { Engine, EngineFailure } from "@/lib/types";

const INITIAL: RunOptions = {
  ticker: "", market: "US", period: "2y", range: "1y", mode: "threshold",
  contamination: 0.02, madK: 3.0, scoreThreshold: -0.10,
};

const TABS = [
  { id: "flow", label: "Flow · anomalies", accent: "#35C4A8" },
  { id: "trend", label: "Technicals", accent: "#5B8DEF" },
  { id: "value", label: "Intrinsic value", accent: "#E8B44C" },
  { id: "screen", label: "Screener", accent: "#A78BFA" },
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
    anomaly, technical, valuation, news,
    run, refineValuation, refineTechnical, csvUrl,
  } = useEngines();
  const [ticker, setTicker] = useState("");
  const [tab, setTab] = useState("flow");

  const busy = [anomaly, technical, valuation].some((s) => s.status === "loading");
  const started = anomaly.status !== "idle";

  const handleRun = (opts: RunOptions) => {
    setTicker(opts.ticker.trim().toUpperCase());
    run(opts);
  };

  // What the engines actually resolved to, which may carry a suffix the user
  // did not type. Showing the resolved symbol is the point of the fix.
  const resolvedTicker =
    anomaly.status === "ready" ? anomaly.data.ticker
      : technical.status === "ready" ? technical.data.ticker
        : valuation.status === "ready" ? valuation.data.ticker
          : ticker;

  return (
    <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <header className="mb-8 border-b border-rule pb-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="font-mono text-2xl font-semibold tracking-[0.22em]">QUANTDESK</h1>
            <p className="eyebrow mt-2">
              Anomaly detection · Technical analysis · Intrinsic value — US &amp; IDX
            </p>
          </div>
          <p className="max-w-sm text-xs leading-relaxed text-ash">
            Three independent models read the same ticker. Where they agree is more interesting
            than what any one of them says on its own.
          </p>
        </div>
      </header>

      <div className="mb-8">
        <TickerBar onRun={handleRun} busy={busy} initial={INITIAL} />
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
          <ScreenerPanel />
        </div>
      ) : (
        <div className="space-y-6">
          <ConfluenceRail ticker={resolvedTicker} anomaly={anomaly}
                          technical={technical} valuation={valuation} />

          <div>
            <Tabs tabs={TABS} active={tab} onChange={setTab} />
            <div className="pt-5">
              {tab === "flow" && (
                <div className="space-y-4">
                  <Panel state={anomaly}>{(d) => <AnomalyPanel data={d} />}</Panel>
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
              {tab === "screen" && <ScreenerPanel />}
            </div>
          </div>
        </div>
      )}

      <footer className="hairline mt-16 pt-5 text-xs leading-relaxed text-ash">
        Prices and filings from Yahoo Finance, unaudited and occasionally incomplete for IDX
        listings. Educational and research use only — not investment advice.
      </footer>
    </main>
  );
}
