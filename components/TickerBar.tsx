"use client";

import { Search, SlidersHorizontal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useDetail } from "@/components/ui/explain";
import { Input, Select } from "@/components/ui/input";
import type { RunOptions } from "@/lib/api";

const PRESETS = ["AAPL", "NVDA", "JPM", "BBCA.JK", "TLKM.JK", "BTC-USD"];

/**
 * Controlled by the page rather than holding its own state, so that anything
 * else able to start a run — the screener's ticker buttons, a future deep
 * link — is reflected here instead of leaving the bar showing a stale symbol
 * beside results for a different one.
 *
 * THE TUNING CONTROLS COLLAPSE IN GUIDED MODE, AND ARE NAMED WHILE THEY DO IT.
 * Four expert controls used to sit above the fold — a detection algorithm, a
 * cutoff annotated "more negative = stricter", and two window pickers — and
 * they were the first thing a newcomer met, before a single number. Guided mode
 * puts them behind one disclosure that says how many there are.
 *
 * Naming the count is the load-bearing part. Silently removing controls reads
 * as "this app cannot do that", which is exactly the impression that loses the
 * expert audience; a labelled disclosure tells them at a glance that nothing
 * was taken away and it is one click back. In Full mode the row renders exactly
 * as it always has.
 */
export function TickerBar({
  opts, onChange, onRun, busy, progress,
}: {
  opts: RunOptions;
  onChange: (o: RunOptions) => void;
  onRun: (o: RunOptions) => void;
  busy: boolean;
  /** How many lenses have settled, so the wait says something while it lasts. */
  progress?: { done: number; total: number };
}) {
  const guided = useDetail() === "simple";

  const set = <K extends keyof RunOptions>(key: K, value: RunOptions[K]) =>
    onChange({ ...opts, [key]: value });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    onRun(opts);
  };

  const controls = (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
      <label className="flex items-center gap-2 text-ash">
        <span className="eyebrow">Detection</span>
        <Select value={opts.mode} onChange={(e) => set("mode", e.target.value)} className="h-8">
          <option value="threshold">Threshold</option>
          <option value="mad">Robust (MAD)</option>
          <option value="quota">Fixed quota</option>
          <option value="walkforward">Walk-forward</option>
        </Select>
      </label>

      {/* Each mode's own parameter, shown only when it does something. */}
      {opts.mode === "threshold" && (
        <label className="flex items-center gap-2 text-ash">
          <span className="eyebrow">Cutoff</span>
          <input type="number" step={0.01} min={-0.5} max={0.5}
                 value={opts.scoreThreshold}
                 onChange={(e) => set("scoreThreshold", Number(e.target.value))}
                 aria-label="Decision score cutoff"
                 className="num h-9 w-24 rounded border border-rule bg-sunken px-2.5 text-meta
                            text-chalk focus:border-tech/60 focus:outline-none
                            focus-visible:ring-2 focus-visible:ring-tech" />
          <span className="text-micro text-ash">more negative = stricter</span>
        </label>
      )}
      {opts.mode === "quota" && (
        <label className="flex items-center gap-2 text-ash">
          <span className="eyebrow">Quota</span>
          <input type="number" step={0.5} min={0.5} max={10}
                 value={+(opts.contamination * 100).toFixed(2)}
                 onChange={(e) => set("contamination", Number(e.target.value) / 100)}
                 aria-label="Anomaly quota percent"
                 className="num h-9 w-24 rounded border border-rule bg-sunken px-2.5 text-meta
                            text-chalk focus:border-tech/60 focus:outline-none
                            focus-visible:ring-2 focus-visible:ring-tech" />
          <span className="text-micro text-ash">% of days, forced</span>
        </label>
      )}
      {opts.mode === "mad" && (
        <label className="flex items-center gap-2 text-ash">
          <span className="eyebrow">Tolerance</span>
          <input type="number" step={0.5} min={1} max={6}
                 value={opts.madK}
                 onChange={(e) => set("madK", Number(e.target.value))}
                 aria-label="MAD tolerance"
                 className="num h-9 w-24 rounded border border-rule bg-sunken px-2.5 text-meta
                            text-chalk focus:border-tech/60 focus:outline-none
                            focus-visible:ring-2 focus-visible:ring-tech" />
          <span className="text-micro text-ash">MADs below rolling median</span>
        </label>
      )}

      <label className="flex items-center gap-2 text-ash">
        <span className="eyebrow">Anomaly window</span>
        <Select value={opts.period} onChange={(e) => set("period", e.target.value)} className="h-8">
          {["6mo", "1y", "2y", "5y", "max"].map((p) => <option key={p} value={p}>{p}</option>)}
        </Select>
      </label>
      <label className="flex items-center gap-2 text-ash">
        <span className="eyebrow">Chart range</span>
        <Select value={opts.range} onChange={(e) => set("range", e.target.value)} className="h-8">
          {["3mo", "6mo", "1y", "2y", "5y", "10y", "max"].map((p) => <option key={p} value={p}>{p}</option>)}
        </Select>
      </label>
    </div>
  );

  return (
    <form onSubmit={submit} className="space-y-3">
      <div className="flex flex-col gap-2 sm:flex-row">
        <div className="relative flex-1">
          <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ash" />
          <Input
            value={opts.ticker}
            onChange={(e) => set("ticker", e.target.value)}
            placeholder="Ticker — AAPL, BBCA.JK, BTC-USD"
            aria-label="Ticker symbol"
            className="pl-9"
          />
        </div>
        <Select value={opts.market} aria-label="Market"
                onChange={(e) => set("market", e.target.value as "US" | "ID")}>
          <option value="US">US market</option>
          <option value="ID">IDX (.JK)</option>
        </Select>
        <Button type="submit" disabled={busy || !opts.ticker.trim()}>
          {busy
            ? progress ? `Running ${progress.done}/${progress.total}` : "Running"
            : "Run all lenses"}
        </Button>
      </div>

      {/* The market selector now applies to every engine, not just valuation. */}
      {opts.market === "ID" && !opts.ticker.trim().toUpperCase().endsWith(".JK")
        && opts.ticker.trim() && (
        <p className="text-meta text-ash">
          Will resolve to{" "}
          <span className="num rounded bg-sunken px-1.5 py-0.5 font-semibold text-chalk">
            {opts.ticker.trim().toUpperCase()}.JK
          </span>{" "}
          for every engine.
        </p>
      )}

      {guided ? (
        <details className="group">
          <summary className="inline-flex cursor-pointer list-none items-center gap-2 rounded
                              py-1 text-meta text-ash transition-colors hover:text-chalk
                              focus-visible:outline-none focus-visible:ring-2
                              focus-visible:ring-tech">
            <SlidersHorizontal aria-hidden className="h-4 w-4 shrink-0" />
            Advanced settings (4)
          </summary>
          <div className="mt-4 rounded-lg border border-ruleSoft bg-sunken px-4 py-3.5">
            {controls}
          </div>
        </details>
      ) : controls}

      {/* Presets stay OUT of the disclosure in both modes. They are how a
          newcomer gets a first result without already knowing a ticker. */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-meta text-faint">Try:</span>
        {PRESETS.map((preset) => (
          <button key={preset} type="button"
                  onClick={() => { const next = { ...opts, ticker: preset,
                                     market: preset.endsWith(".JK") ? "ID" as const : "US" as const };
                                   onChange(next); onRun(next); }}
                  className="num inline-flex h-8 items-center rounded-lg border border-rule
                             bg-sunken px-3 text-meta font-medium text-ash transition-colors
                             hover:border-tech/50 hover:bg-tech/10 hover:text-tech
                             focus:outline-none focus-visible:ring-2 focus-visible:ring-tech">
            {preset}
          </button>
        ))}
      </div>
    </form>
  );
}
