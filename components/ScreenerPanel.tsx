"use client";

import { Card, CardBody, CardHeader, CardTitle, Explainer, Note } from "@/components/ui/card";
import {
  ApplyButton, DownloadButton, Field, NumberField, SelectField,
} from "@/components/ui/controls";
import { PanelSkeleton } from "@/components/ui/skeleton";
import { useScreener } from "@/lib/api";
import { downloadCsv, toCsv } from "@/lib/csv";
import type { Market } from "@/lib/types";
import { cn, num, pct } from "@/lib/utils";
import { palette } from "@/lib/palette";
import { Textarea } from "@/components/ui/input";
import { StateCard } from "@/components/ui/state";
import { useSessionState } from "@/lib/session";
import { ScrollRegion } from "@/components/ui/scroll";
import { useT } from "@/lib/i18n";

const ACC = palette.acc;
const DIST = palette.dist;
const NEU = palette.ash;

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
  const t = useT();
  const { state, scan } = useScreener();
  const [tickers, setTickers] = useSessionState("screener:tickers", DEFAULT_UNIVERSE);
  const [recentDays, setRecentDays] = useSessionState("screener:recentDays", 10);
  const [period, setPeriod] = useSessionState("screener:period", "2y");
  const [mode, setMode] = useSessionState("screener:mode", "threshold");
  const [market, setMarket] = useSessionState<Market>("screener:market", "US");

  const bareCodes = tickers
    .replace(/\n/g, ",")
    .split(",")
    .map((item) => item.trim())
    .filter((item) => item && !item.includes("."));
  const suffixWarning = market === "ID" && bareCodes.length > 0;

  const rows = state.status === "ready" ? state.data.rows : [];

  const download = () =>
    downloadCsv(
      "whale_screener_extract.csv",
      toCsv(rows, [
        { key: "ticker", label: t("Ticker") },
        { key: "recentAnomalies", label: t("Recent Anomalies") },
        { key: "dominantFlow", label: t("Dominant Flow") },
        { key: "topStrength", label: t("Top Strength") },
        { key: "latestSignal", label: t("Latest Signal") },
        { key: "latestTag", label: t("Latest Tag") },
        { key: "latestClose", label: t("Latest Close") },
        { key: "topRvol", label: t("RVOL (top)") },
      ])
    );

  return (
    <div className="space-y-4 animate-rise">
      <Card>
        <CardHeader><CardTitle>{t("Cross-asset screener")}</CardTitle></CardHeader>
        <CardBody className="space-y-4">
          <Explainer summary={t("Scans a list and shows only the names with fresh unusual trading")}>
            {t("Symbols keep their own suffix, so a mixed US and IDX list works on either setting. Capped at 20 a scan: each symbol costs one download and one model fit.")}
          </Explainer>
          <Field label={t("Universe")} hint={t("Comma or newline separated.")}>
            <Textarea mono value={tickers} onChange={(e) => setTickers(e.target.value)} rows={3} />
          </Field>
          <div className="flex flex-wrap items-end gap-3">
            <Field label={t("Bare codes are")} hint={t("Suffixed symbols are left alone.")}>
              <SelectField value={market} onChange={(v) => setMarket(v as Market)}
                           options={[
                             { value: "US", label: t("US symbols") },
                             { value: "ID", label: t("IDX (add .JK)") },
                           ]} />
            </Field>
            <Field label={t("Look-back window (days)")}>
              <NumberField value={recentDays} onChange={(v) => setRecentDays(v ?? 10)}
                           min={1} max={60} />
            </Field>
            <Field label={t("History")}>
              <SelectField value={period} onChange={setPeriod}
                           options={["6mo", "1y", "2y", "5y", "max"]} />
            </Field>
            <Field label={t("Detection")}>
              <SelectField value={mode} onChange={setMode}
                           options={[
                             { value: "threshold", label: t("Threshold") },
                             { value: "mad", label: t("Robust (MAD)") },
                             { value: "quota", label: t("Fixed quota") },
                             { value: "walkforward", label: t("Walk-forward") },
                           ]} />
            </Field>
            <ApplyButton
              busy={state.status === "loading"}
              onClick={() => scan({ tickers, market, period, mode, recentDays })}
            >
              {t("Execute scan")}
            </ApplyButton>
          </div>
          {suffixWarning && (
            <p className="text-meta leading-relaxed text-warn">
              {t("{length} bare code{value} (", { length: bareCodes.length, value: bareCodes.length === 1 ? "" : "s" })}
              <span className="font-mono">{bareCodes.slice(0, 4).join(", ")}
              {bareCodes.length > 4 ? "…" : ""}</span>{t(") will get")}{" "}
              <span className="font-mono">{t(".JK")}</span>{" "}{t("appended. Symbols that do not exist on the IDX fetch nothing and are dropped from the results without an error.")}
            </p>
          )}
          {mode === "walkforward" && (
            <Note tone="warn">
              {t("Walk-forward refits the model at every step, so it is capped at 5 symbols. Use Threshold or Robust for a whole list.")}
            </Note>
          )}
        </CardBody>
      </Card>

      {state.status === "loading" && <Card><PanelSkeleton /></Card>}

      {state.status === "error" && (
        <StateCard kind="error" title={t("The scan could not run")}>{state.failure.message}</StateCard>
      )}

      {state.status === "ready" && (
        <Card>
          <CardHeader>
            <CardTitle>
              {t("{length} of {scanned} with activity in the last {recentDays} days", { length: rows.length, scanned: state.data.scanned, recentDays: state.data.recentDays })}
            </CardTitle>
            <div className="flex items-center gap-3">
              {state.data.significance?.available && (
                <span className="num text-micro text-ash">
                  {t("{discoveries} significant", { discoveries: state.data.significance.discoveries })}
                </span>
              )}
              {rows.length > 0 && onSelect && (
                <span className="text-micro text-ash">{t("Select a ticker to load it")}</span>
              )}
              {rows.length > 0 && <DownloadButton onClick={download}>{t("CSV")}</DownloadButton>}
            </div>
          </CardHeader>
          <CardBody className="px-0">
            {rows.length === 0 ? (
              <p className="prose-col px-5 text-base text-ash">
                {t("Nothing unusual traded in any of these names over this window. Try a longer look-back or a looser detection setting — and note that finding nothing is a result, not a failure.")}
              </p>
            ) : (
              <ScrollRegion label={t("Screener results")}>
                <table className="w-full text-left text-meta">
                  <thead>
                    <tr className="eyebrow border-b border-rule [&>th]:px-5 [&>th]:py-2 [&>th]:font-normal">
                      <th>{t("Ticker")}</th><th className="text-right">{t("Events")}</th>
                      <th>{t("Dominant flow")}</th><th>{t("Latest signal")}</th><th>{t("Tag")}</th>
                      <th className="text-right">{t("Close")}</th>
                      <th className="text-right">{t("Max RVOL")}</th>
                      <th className="text-right">{t("q-value")}</th>
                      <th className="w-32">{t("Strength")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.ticker} className="border-b border-ruleSoft last:border-0 hover:bg-raised/60">
                        <td className="num px-5 py-2 font-semibold">
                          {/* The point of a screener is to find a name worth
                              looking at. Having found one, retyping it into the
                              ticker bar was the only way through. */}
                          {onSelect ? (
                            <button
                              type="button"
                              onClick={() => onSelect(r.ticker)}
                              title={t("Load {ticker} into every lens", { ticker: r.ticker })}
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
                              : t("Tested against this ticker's own {rate} long-run flag rate",
                                  { rate: pct(r.anomalyRate) })}>
                          {r.qValue == null ? "—" : r.qValue.toFixed(3)}
                        </td>
                        <td className="px-5 py-2">
                          <div className="flex items-center gap-2">
                            <div className="h-1 flex-1 rounded bg-rule">
                              <div className="h-full rounded"
                                   style={{ width: `${r.topStrength}%`,
                                            background: flowColor(r.dominantFlow) }} />
                            </div>
                            <span className="num w-6 text-right text-micro text-ash">
                              {r.topStrength}
                            </span>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </ScrollRegion>
            )}
          </CardBody>
        </Card>
      )}

      {state.status === "ready" && state.data.significance?.available && (
        <div className="rounded border border-rule bg-panel px-4 py-3">
          <div className="eyebrow mb-1">{t("Multiple testing")}</div>
          <p className="text-meta leading-relaxed text-body">
            {state.data.significance.reading}
          </p>
          <Explainer summary={t("Scan enough names and some will look unusual by chance — this corrects for that")}>
            {t("Each ticker is measured against")}{" "}<em>{t("its own")}</em>{" "}{t("normal flag rate, so a habitually noisy stock has to do much more to qualify than a quiet one. The q-value column then corrects across the whole scan for the number of names tested (Benjamini-Hochberg).")}
          </Explainer>
        </div>
      )}

      <Note>
        {t("A symbol that fails to download is skipped rather than stopping the scan, so a short list can mean a bad ticker as easily as a quiet market. Research use only.")}
      </Note>
    </div>
  );
}
