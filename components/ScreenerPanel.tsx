"use client";

import { useState } from "react";
import { AlertTriangle } from "lucide-react";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ApplyButton, DownloadButton, Field, NumberField, SelectField,
} from "@/components/ui/controls";
import { PanelSkeleton } from "@/components/ui/skeleton";
import { useScreener } from "@/lib/api";
import { downloadCsv, toCsv } from "@/lib/csv";
import type { Market } from "@/lib/types";
import { cn, num, pct } from "@/lib/utils";

const ACC = "#35C4A8";
const DIST = "#FF6B6B";
const NEU = "#7A8CA0";

const flowColor = (flow: string) =>
  flow === "Accumulation" ? ACC : flow === "Distribution" ? DIST : NEU;

const DEFAULT_UNIVERSE = "AAPL, NVDA, TSLA, JPM, KO, BBCA.JK, BBRI.JK, TLKM.JK";

/**
 * The cross-asset screener from the Whale Tracker app. `scan_watchlist` was
 * ported into the engine but no route reached it, so the screener existed in
 * the codebase without being usable. This is the missing surface.
 *
 * WHY THE MARKET SELECTOR IS LOCAL AND DEFAULTS TO US
 * --------------------------------------------------
 * The suffix rule is applied per symbol, so the market setting decides what
 * happens to BARE codes only — anything already carrying `.JK` keeps it. That
 * makes "US" the correct default for a screener: a mixed universe like
 * "AAPL, BBCA.JK" resolves both correctly. This deliberately does NOT inherit
 * the market of the loaded ticker; when it did, selecting IDX for one company
 * turned every bare US code in the universe into AAPL.JK, TSLA.JK and so on,
 * which fetch nothing and are skipped silently — a full watchlist quietly
 * collapsed to its .JK members with no error. Switch to IDX only when the
 * whole list is bare Indonesian codes.
 */
export function ScreenerPanel({ onSelect }: { onSelect?: (ticker: string) => void }) {
  const { state, scan } = useScreener();
  const [tickers, setTickers] = useState(DEFAULT_UNIVERSE);
  const [recentDays, setRecentDays] = useState(10);
  const [period, setPeriod] = useState("2y");
  const [mode, setMode] = useState("threshold");
  const [market, setMarket] = useState<Market>("US");

  const bareCodes = tickers
    .replace(/\n/g, ",")
    .split(",")
    .map((t) => t.trim())
    .filter((t) => t && !t.includes("."));
  const suffixWarning = market === "ID" && bareCodes.length > 0;

  const rows = state.status === "ready" ? state.data.rows : [];

  const download = () =>
    downloadCsv(
      "whale_screener_extract.csv",
      toCsv(rows, [
        { key: "ticker", label: "Ticker" },
        { key: "recentAnomalies", label: "Recent Anomalies" },
        { key: "dominantFlow", label: "Dominant Flow" },
        { key: "topStrength", label: "Top Strength" },
        { key: "latestSignal", label: "Latest Signal" },
        { key: "latestTag", label: "Latest Tag" },
        { key: "latestClose", label: "Latest Close" },
        { key: "topRvol", label: "RVOL (top)" },
      ])
    );

  return (
    <div className="space-y-4 animate-rise">
      <Card>
        <CardHeader><CardTitle>Cross-asset screener</CardTitle></CardHeader>
        <CardBody className="space-y-4">
          <p className="text-xs leading-relaxed text-ash">
            Scan a universe and surface only the names showing fresh whale activity. Symbols
            carrying their own suffix keep it, so a mixed list works on the US setting — up to
            20 at a time, since each symbol costs an upstream fetch and a model fit.
          </p>
          <Field label="Universe" hint="Comma or newline separated.">
            <textarea
              value={tickers}
              onChange={(e) => setTickers(e.target.value)}
              rows={3}
              className={cn(
                "w-full rounded border border-rule bg-raised px-3 py-2",
                "font-mono text-xs text-chalk transition-colors focus:border-tech/60",
              )}
            />
          </Field>
          <div className="flex flex-wrap items-end gap-3">
            <Field label="Bare codes are" hint="Suffixed symbols are left alone.">
              <SelectField value={market} onChange={(v) => setMarket(v as Market)}
                           options={[
                             { value: "US", label: "US symbols" },
                             { value: "ID", label: "IDX (add .JK)" },
                           ]} />
            </Field>
            <Field label="Look-back window (days)">
              <NumberField value={recentDays} onChange={(v) => setRecentDays(v ?? 10)}
                           min={1} max={60} />
            </Field>
            <Field label="History">
              <SelectField value={period} onChange={setPeriod}
                           options={["6mo", "1y", "2y", "5y", "max"]} />
            </Field>
            <Field label="Detection">
              <SelectField value={mode} onChange={setMode}
                           options={[
                             { value: "threshold", label: "Threshold" },
                             { value: "mad", label: "Robust (MAD)" },
                             { value: "quota", label: "Fixed quota" },
                             { value: "walkforward", label: "Walk-forward" },
                           ]} />
            </Field>
            <ApplyButton
              busy={state.status === "loading"}
              onClick={() => scan({ tickers, market, period, mode, recentDays })}
            >
              Execute scan
            </ApplyButton>
          </div>
          {suffixWarning && (
            <p className="text-[0.7rem] leading-relaxed text-warn">
              {bareCodes.length} bare code{bareCodes.length === 1 ? "" : "s"} (
              <span className="font-mono">{bareCodes.slice(0, 4).join(", ")}
              {bareCodes.length > 4 ? "…" : ""}</span>) will get{" "}
              <span className="font-mono">.JK</span> appended. Symbols that do not exist on the
              IDX fetch nothing and are dropped from the results without an error.
            </p>
          )}
          {mode === "walkforward" && (
            <p className="text-[0.7rem] text-warn">
              Walk-forward refits per step, so the server caps it at 5 symbols per scan. Use
              Threshold or Robust to screen a full universe.
            </p>
          )}
        </CardBody>
      </Card>

      {state.status === "loading" && <Card><PanelSkeleton /></Card>}

      {state.status === "error" && (
        <Card className="border-dist/40 bg-dist/5">
          <div className="flex gap-3 p-5">
            <AlertTriangle aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-dist" />
            <div>
              <div className="eyebrow mb-1 text-dist">The scan could not run</div>
              <p className="text-sm leading-relaxed text-chalk/80">{state.failure.message}</p>
            </div>
          </div>
        </Card>
      )}

      {state.status === "ready" && (
        <Card>
          <CardHeader>
            <CardTitle>
              {rows.length} of {state.data.scanned} with activity in the last{" "}
              {state.data.recentDays} days
            </CardTitle>
            <div className="flex items-center gap-3">
              {state.data.significance?.available && (
                <span className="num text-[0.65rem] text-ash">
                  {state.data.significance.discoveries} significant
                </span>
              )}
              {rows.length > 0 && onSelect && (
                <span className="text-[0.65rem] text-ash">Select a ticker to load it</span>
              )}
              {rows.length > 0 && <DownloadButton onClick={download}>CSV</DownloadButton>}
            </div>
          </CardHeader>
          <CardBody className="px-0">
            {rows.length === 0 ? (
              <p className="px-5 text-sm text-ash">
                No institutional activity detected across this universe in the window. Widen the
                look-back, lengthen the history, or loosen the detection mode.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="eyebrow border-b border-rule [&>th]:px-5 [&>th]:py-2 [&>th]:font-normal">
                      <th>Ticker</th><th className="text-right">Events</th>
                      <th>Dominant flow</th><th>Latest signal</th><th>Tag</th>
                      <th className="text-right">Close</th>
                      <th className="text-right">Max RVOL</th>
                      <th className="text-right">q-value</th>
                      <th className="w-32">Strength</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.ticker} className="border-b border-rule/60 last:border-0 hover:bg-raised/60">
                        <td className="num px-5 py-2 font-semibold">
                          {/* The point of a screener is to find a name worth
                              looking at. Having found one, retyping it into the
                              ticker bar was the only way through. */}
                          {onSelect ? (
                            <button
                              type="button"
                              onClick={() => onSelect(r.ticker)}
                              title={`Load ${r.ticker} into every lens`}
                              className={cn(
                                "underline decoration-dotted decoration-rule underline-offset-4",
                                "transition-colors hover:text-tech hover:decoration-tech",
                                "focus:outline-none focus-visible:ring-1 focus-visible:ring-tech",
                              )}
                            >
                              {r.ticker}
                            </button>
                          ) : (
                            r.ticker
                          )}
                        </td>
                        <td className="num px-5 py-2 text-right">{r.recentAnomalies}</td>
                        <td className="px-5 py-2" style={{ color: flowColor(r.dominantFlow) }}>
                          {r.dominantFlow}
                        </td>
                        <td className="num px-5 py-2 text-ash">{r.latestSignal}</td>
                        <td className="px-5 py-2 text-ash">{r.latestTag}</td>
                        <td className="num px-5 py-2 text-right">{num(r.latestClose)}</td>
                        <td className="num px-5 py-2 text-right">{num(r.topRvol)}x</td>
                        <td className={cn("num px-5 py-2 text-right",
                                          r.significant ? "text-acc" : "text-ash")}
                            title={r.anomalyRate == null ? undefined
                              : `Tested against this ticker's own ${pct(r.anomalyRate)} long-run flag rate`}>
                          {r.qValue == null ? "—" : r.qValue.toFixed(3)}
                        </td>
                        <td className="px-5 py-2">
                          <div className="flex items-center gap-2">
                            <div className="h-1 flex-1 rounded bg-rule">
                              <div className="h-full rounded"
                                   style={{ width: `${r.topStrength}%`,
                                            background: flowColor(r.dominantFlow) }} />
                            </div>
                            <span className="num w-6 text-right text-[0.7rem] text-ash">
                              {r.topStrength}
                            </span>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardBody>
        </Card>
      )}

      {state.status === "ready" && state.data.significance?.available && (
        <div className="rounded border border-rule bg-panel px-4 py-3">
          <div className="eyebrow mb-1">Multiple testing</div>
          <p className="text-xs leading-relaxed text-chalk/80">
            {state.data.significance.reading}
          </p>
          <p className="mt-2 text-[0.7rem] leading-relaxed text-ash">
            Scanning many names produces hits by construction. Each ticker&apos;s recent count is
            tested against its OWN long-run flag rate — so a chronically noisy stock needs far
            more activity to qualify than a normally quiet one — and the q-value column applies a
            Benjamini-Hochberg false-discovery-rate correction across the whole scan.
          </p>
        </div>
      )}

      <p className="text-xs leading-relaxed text-ash">
        Symbols that fail to fetch are skipped rather than aborting the scan, so a shorter result
        list can mean a bad symbol as easily as a quiet one. Educational and research use only.
      </p>
    </div>
  );
}
