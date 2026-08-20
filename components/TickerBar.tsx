"use client";

import { Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import type { RunOptions } from "@/lib/api";

const PRESETS = ["AAPL", "NVDA", "JPM", "BBCA.JK", "TLKM.JK", "BTC-USD"];

/**
 * Controlled by the page rather than holding its own state, so that anything
 * else able to start a run — the screener's ticker buttons, a future deep
 * link — is reflected here instead of leaving the bar showing a stale symbol
 * beside results for a different one.
 */
export function TickerBar({
  opts, onChange, onRun, busy,
}: {
  opts: RunOptions;
  onChange: (o: RunOptions) => void;
  onRun: (o: RunOptions) => void;
  busy: boolean;
}) {
  const set = <K extends keyof RunOptions>(key: K, value: RunOptions[K]) =>
    onChange({ ...opts, [key]: value });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    onRun(opts);
  };

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
          {busy ? "Running" : "Run all three"}
        </Button>
      </div>

      {/* The market selector now applies to every engine, not just valuation. */}
      {opts.market === "ID" && !opts.ticker.trim().toUpperCase().endsWith(".JK")
        && opts.ticker.trim() && (
        <p className="text-[0.7rem] text-ash">
          Will resolve to{" "}
          <span className="font-mono text-chalk/80">
            {opts.ticker.trim().toUpperCase()}.JK
          </span>{" "}
          for all three engines.
        </p>
      )}

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-[0.68rem]">
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
                   className="h-8 w-20 rounded border border-rule bg-panel px-2 font-mono text-xs text-chalk" />
            <span className="text-[0.65rem]">more negative = stricter</span>
          </label>
        )}
        {opts.mode === "quota" && (
          <label className="flex items-center gap-2 text-ash">
            <span className="eyebrow">Quota</span>
            <input type="number" step={0.5} min={0.5} max={10}
                   value={+(opts.contamination * 100).toFixed(2)}
                   onChange={(e) => set("contamination", Number(e.target.value) / 100)}
                   aria-label="Anomaly quota percent"
                   className="h-8 w-20 rounded border border-rule bg-panel px-2 font-mono text-xs text-chalk" />
            <span className="text-[0.65rem]">% of days, forced</span>
          </label>
        )}
        {opts.mode === "mad" && (
          <label className="flex items-center gap-2 text-ash">
            <span className="eyebrow">Tolerance</span>
            <input type="number" step={0.5} min={1} max={6}
                   value={opts.madK}
                   onChange={(e) => set("madK", Number(e.target.value))}
                   aria-label="MAD tolerance"
                   className="h-8 w-20 rounded border border-rule bg-panel px-2 font-mono text-xs text-chalk" />
            <span className="text-[0.65rem]">MADs below rolling median</span>
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
            {["3mo", "6mo", "1y", "2y", "5y"].map((p) => <option key={p} value={p}>{p}</option>)}
          </Select>
        </label>
        <div className="flex flex-wrap items-center gap-1.5">
          {PRESETS.map((preset) => (
            <button key={preset} type="button"
                    onClick={() => { const next = { ...opts, ticker: preset,
                                       market: preset.endsWith(".JK") ? "ID" as const : "US" as const };
                                     onChange(next); onRun(next); }}
                    className="rounded border border-rule px-2 py-1 font-mono text-[0.65rem] text-ash transition-colors hover:border-tech/60 hover:text-chalk">
              {preset}
            </button>
          ))}
        </div>
      </div>
    </form>
  );
}
