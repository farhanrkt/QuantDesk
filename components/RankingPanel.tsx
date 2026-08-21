"use client";

import { Fragment, useEffect, useMemo, useState } from "react";
import { AlertTriangle, ChevronDown, ChevronRight } from "lucide-react";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ApplyButton, Field, SelectField,
} from "@/components/ui/controls";
import {
  Explain, ExplanationBody, TONE_TEXT, useDetail,
} from "@/components/ui/explain";
import { PanelSkeleton } from "@/components/ui/skeleton";
import { useDeepen, useRanking, useUniverses } from "@/lib/api";
import { downloadCsv, toCsv } from "@/lib/csv";
import { DownloadButton } from "@/components/ui/controls";
import type {
  DeepenRow, Market, RankRow, RankSignalDefinition,
} from "@/lib/types";
import { cn, num, pct, signedPct } from "@/lib/utils";

const CUSTOM = "__custom__";
const DEFAULT_CUSTOM = "AAPL, NVDA, TSLA, JPM, KO, BBCA.JK, BBRI.JK, TLKM.JK";

/** Percentiles get a heat colour, not a verdict colour — they are positions. */
function heat(percentile: number | null): string {
  if (percentile == null) return "text-ash/50";
  if (percentile >= 80) return "text-acc";
  if (percentile >= 60) return "text-acc/70";
  if (percentile >= 40) return "text-chalk/70";
  if (percentile >= 20) return "text-warn/80";
  return "text-dist/80";
}

const HEAT_FILL = (percentile: number) =>
  percentile >= 80 ? "#35C4A8" : percentile >= 60 ? "#35C4A899"
    : percentile >= 40 ? "#7A8CA0" : percentile >= 20 ? "#F2C14E99" : "#FF6B6B99";

/**
 * One percentile cell: the number, over a bar as long as the number.
 *
 * A hundred bare figures in a twelve-column grid is a spreadsheet, and reading
 * it means comparing three-digit strings by eye. The bar makes the shape of a
 * row legible at a glance — which is the entire job of a shortlisting table —
 * without adding a single fact the number did not already carry.
 */
function PercentileCell({ value }: { value: number | null }) {
  return (
    <td className="relative px-3 py-1.5 text-right">
      {value != null && (
        <>
          {/* The empty track matters as much as the fill. Without it a reading
              of 12 is a sliver floating in blank space and reads as "nothing
              here" rather than "near the bottom of the range". */}
          <span aria-hidden
                className="absolute inset-y-[0.3rem] left-1 right-1 rounded-sm bg-rule/40" />
          <span aria-hidden
                className="absolute inset-y-[0.3rem] left-1 rounded-sm opacity-30"
                style={{ width: `calc((100% - 0.5rem) * ${Math.max(value, 1.5) / 100})`,
                         background: HEAT_FILL(value) }} />
        </>
      )}
      <span className={cn("num relative font-medium", heat(value))}>
        {value == null ? "—" : value.toFixed(0)}
      </span>
    </td>
  );
}

const EVIDENCE_DOT: Record<string, string> = {
  strong: "bg-acc", moderate: "bg-acc/50", weak: "bg-warn/70",
};

/**
 * The breadth half of the two-tier workflow.
 *
 * WHY THIS IS A RANKING AND NOT A SCREEN. The old screener answered "which of
 * these twenty names tripped an anomaly detector?" — a filter, returning
 * whoever happened to cross a line. A ranking answers "of these hundred, which
 * few are worth opening four lenses on?", which is the question the second tier
 * actually exists to serve. Everything gets a position; nothing is silently
 * dropped for being unremarkable.
 *
 * TWO THINGS THIS PANEL REFUSES TO HIDE.
 *
 * The composite is a weighted mean of CROSS-SECTIONAL RANKS, so every figure in
 * the table is a statement about this universe on this date. The header says so
 * rather than leaving "82" to look like a score on some absolute scale.
 *
 * And the signals are not independent. Momentum, nearness to the 52-week high
 * and relative strength are three phrasings of "it went up". The overlap card
 * reports the measured rank correlation between every pair and the effective
 * number of independent signals behind the composite — on a typical scan seven
 * columns carry about three and a half signals' worth of information, and the
 * reader is told that in the data rather than in a footnote.
 */
export function RankingPanel({ onSelect }: { onSelect?: (ticker: string) => void }) {
  const { state: universeState, load } = useUniverses();
  const { state, scan } = useRanking();
  const { state: deepState, deepen, reset: resetDeepen } = useDeepen();
  const detail = useDetail();
  const simple = detail === "simple";

  const [choice, setChoice] = useState<string>("dow30");
  const [custom, setCustom] = useState(DEFAULT_CUSTOM);
  const [customMarket, setCustomMarket] = useState<Market>("US");
  const [sortKey, setSortKey] = useState<string>("composite");
  const [ascending, setAscending] = useState(false);
  const [filter, setFilter] = useState("");
  const [minComposite, setMinComposite] = useState(0);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [picked, setPicked] = useState<string[]>([]);

  useEffect(() => { load(); }, [load]);

  const catalogue = universeState.status === "ready" ? universeState.data.universes : [];
  const maxDeepen = universeState.status === "ready" ? universeState.data.maxDeepen : 8;
  const selected = catalogue.find((u) => u.id === choice);
  const data = state.status === "ready" ? state.data : null;
  const allSignals: RankSignalDefinition[] = data?.signals ?? [];
  // Twelve columns is a spreadsheet, not a shortlist. Simple mode keeps the
  // signals carrying the most weight — which is the same thing as the ones with
  // the best-supported evidence, since weight follows evidence grade.
  const signals = simple
    ? [...allSignals].sort((a, b) => b.weight - a.weight).slice(0, 3)
        .sort((a, b) => allSignals.indexOf(a) - allSignals.indexOf(b))
    : allSignals;

  const deepByTicker = useMemo(() => {
    const map = new Map<string, DeepenRow>();
    if (deepState.status === "ready") {
      for (const row of deepState.data.rows) map.set(row.ticker, row);
    }
    return map;
  }, [deepState]);

  const rows = useMemo(() => {
    if (!data) return [];
    const needle = filter.trim().toUpperCase();
    const kept = data.rows.filter((row) =>
      (!needle || row.ticker.includes(needle))
      && (row.composite ?? 0) >= minComposite);
    const value = (row: RankRow) =>
      sortKey === "composite" ? (row.composite ?? -1)
        : sortKey === "ticker" ? row.ticker
          : sortKey === "close" ? row.latestClose
            : (row.signals[sortKey]?.percentile ?? -1);
    return [...kept].sort((a, b) => {
      const left = value(a);
      const right = value(b);
      if (typeof left === "string" && typeof right === "string") {
        return ascending ? left.localeCompare(right) : right.localeCompare(left);
      }
      return ascending ? (left as number) - (right as number)
                       : (right as number) - (left as number);
    });
  }, [data, filter, minComposite, sortKey, ascending]);

  const toggleSort = (key: string) => {
    if (sortKey === key) { setAscending((v) => !v); return; }
    setSortKey(key);
    // Rank-like columns read best highest-first; a ticker column reads A-Z.
    setAscending(key === "ticker");
  };

  const togglePick = (ticker: string) => {
    setPicked((current) => current.includes(ticker)
      ? current.filter((t) => t !== ticker)
      : current.length >= maxDeepen ? current : [...current, ticker]);
  };

  const runScan = () => {
    setPicked([]);
    setExpanded(null);
    resetDeepen();
    scan(choice === CUSTOM
      ? { universe: null, tickers: custom, market: customMarket }
      : { universe: choice, market: (selected?.market ?? "US") });
  };

  const scanMarket: Market = choice === CUSTOM ? customMarket : (selected?.market ?? "US");

  // What the picker currently says, versus what the loaded table actually is.
  const pendingName = choice === CUSTOM ? "your own list" : (selected?.name ?? choice);
  const stale = data != null
    && (choice === CUSTOM ? data.universe.id !== null : data.universe.id !== choice);

  const download = () => {
    if (!data) return;
    // The signal columns are only known at runtime, so the export rows are
    // typed as an open record — `toCsv` checks `keyof T`, and a fixed interface
    // would reject the spread of whatever signals this scan returned.
    const flat: Record<string, string | number>[] = rows.map((row) => ({
      rank: row.rank,
      ticker: row.ticker,
      composite: row.composite == null ? "" : row.composite.toFixed(1),
      close: row.latestClose,
      coverage: row.coverage,
      ...Object.fromEntries(signals.map((s) => [
        s.key, row.signals[s.key]?.percentile?.toFixed(0) ?? "",
      ])),
    }));
    downloadCsv(
      `quantdesk_ranking_${data.universe.id ?? "custom"}.csv`,
      toCsv(flat, [
        { key: "rank", label: "Rank" }, { key: "ticker", label: "Ticker" },
        { key: "composite", label: "Composite (percentile)" },
        { key: "close", label: "Close" },
        { key: "coverage", label: "Signal coverage" },
        ...signals.map((s) => ({ key: s.key, label: `${s.label} (percentile)` })),
      ])
    );
  };

  return (
    <div className="space-y-4 animate-rise">
      {/* ---------------- what this is ---------------- */}
      <Card>
        <CardHeader>
          <CardTitle>Scan a universe, then inspect the best few</CardTitle>
          {data && (
            <span className="font-mono text-[0.65rem] text-ash">
              {data.ranked} of {data.requested} ranked
            </span>
          )}
        </CardHeader>
        <CardBody className="space-y-4">
          <p className="text-[0.82rem] leading-relaxed text-ash">
            This ranks every name in a list against the others on seven signals built from price
            and volume, then orders them. It is a shortlisting tool: its job is to decide which
            three or four names are worth opening the four lenses on, not to tell you what to
            buy. Every figure is a POSITION WITHIN THIS SCAN — a name at 90 is ahead of its peers
            here, which is not the same as going up.
          </p>

          <div className="flex flex-wrap items-end gap-3">
            <Field label="Universe"
                   hint={selected ? `${selected.count} names · list as of ${selected.asOf}`
                                  : "Your own list"}>
              <SelectField
                value={choice}
                onChange={setChoice}
                options={[
                  ...catalogue.map((u) => ({ value: u.id, label: `${u.name} (${u.count})` })),
                  { value: CUSTOM, label: "My own list" },
                ]}
              />
            </Field>
            {choice === CUSTOM && (
              <Field label="Bare codes are" hint="Suffixed symbols are left alone.">
                <SelectField value={customMarket} onChange={(v) => setCustomMarket(v as Market)}
                             options={[
                               { value: "US", label: "US symbols" },
                               { value: "ID", label: "IDX (add .JK)" },
                             ]} />
              </Field>
            )}
            <ApplyButton busy={state.status === "loading"} onClick={runScan}>
              Rank them
            </ApplyButton>
          </div>

          {choice === CUSTOM && (
            <Field label="Your list" hint="Comma or newline separated.">
              <textarea
                value={custom}
                onChange={(e) => setCustom(e.target.value)}
                rows={3}
                className={cn(
                  "w-full rounded border border-rule bg-raised px-3 py-2",
                  "font-mono text-xs text-chalk transition-colors focus:border-tech/60",
                )}
              />
            </Field>
          )}

          {selected && (
            <p className="text-[0.7rem] leading-relaxed text-ash">
              {selected.note}{" "}
              <span className="text-warn/90">
                This membership list was transcribed on {selected.asOf} and is not updated
                automatically — index constituents change, and a name that has since been
                dropped will still be scanned while a newly added one will be missing. There is
                deliberately no S&amp;P 500 list: five hundred symbols is the length at which
                transcription goes wrong, and a mistyped ticker produces a plausible row for a
                company nobody asked about rather than an error.
              </span>
            </p>
          )}
        </CardBody>
      </Card>

      {state.status === "loading" && (
        <Card>
          <CardBody>
            <p className="mb-3 text-sm leading-relaxed text-ash">
              Fetching {choice === CUSTOM ? "your list" : `${selected?.count ?? ""} symbols`} in
              batches of fifty and ranking them against each other. This takes a few seconds —
              one request per fifty names rather than one per name is what makes a universe
              this size possible at all.
            </p>
            <PanelSkeleton />
          </CardBody>
        </Card>
      )}

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

      {data && (
        <>
          {/* ---------------- the honest overlap card ---------------- */}
          {data.correlation.available && (
            <Card accent="#F2C14E">
              <CardHeader>
                <CardTitle>How independent are these signals?</CardTitle>
                {data.correlation.effectiveSignals != null && (
                  <span className="num text-xs font-semibold text-warn">
                    {num(data.correlation.effectiveSignals, 1)} of{" "}
                    {data.correlation.measuredSignals} independent
                  </span>
                )}
              </CardHeader>
              <CardBody className="space-y-3">
                <p className="text-[0.85rem] leading-relaxed text-chalk/85">
                  {data.correlation.reading}
                </p>
                {!simple && (data.correlation.pairs?.length ?? 0) > 0 && (
                  <div className="space-y-1.5">
                    {data.correlation.pairs!.slice(0, 4).map((pair) => {
                      const key = `signalOverlap.${pair.a}.${pair.b}`;
                      const labels = (k: string) =>
                        signals.find((s) => s.key === k)?.label ?? k;
                      return (
                        <div key={key}
                             className="flex items-baseline justify-between gap-3 border-b border-rule/40 pb-1 text-xs last:border-0">
                          <span className="flex items-center gap-1.5 text-ash">
                            {labels(pair.a)} vs {labels(pair.b)}
                            <Explain explain={data.explain?.[key]} />
                          </span>
                          <span className={cn("num font-semibold",
                                              Math.abs(pair.correlation) > 0.7
                                                ? "text-warn" : "text-chalk/70")}>
                            {pair.correlation >= 0 ? "+" : ""}{num(pair.correlation)}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                )}
                <p className="text-[0.7rem] leading-relaxed text-ash">
                  Seven columns look like seven tests. Where two of them correlate above 0.7 they
                  are one test wearing two labels, and the composite gives that single fact
                  double weight. The figure in the header is the participation ratio of the
                  correlation matrix — how many genuinely independent signals the composite is
                  actually averaging. It is measured from this scan, not asserted.
                </p>
              </CardBody>
            </Card>
          )}

          {/* ---------------- the table ---------------- */}
          <Card>
            <CardHeader>
              <CardTitle className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              {data.universe.name}
              {/* Changing the picker does not re-scan, so the dropdown can say
                  one universe while the table below shows another. Reading a
                  Dow ranking as a Nasdaq one is exactly the class of quiet
                  misattribution this codebase has been bitten by before. */}
              {stale && (
                <span className="font-mono text-[0.65rem] font-normal normal-case text-warn">
                  showing the previous scan — press Rank them for {pendingName}
                </span>
              )}
            </CardTitle>
              <div className="flex flex-wrap items-center gap-3">
                <input
                  type="text"
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                  placeholder="Filter ticker"
                  aria-label="Filter by ticker"
                  className="h-7 w-28 rounded border border-rule bg-raised px-2 font-mono text-[0.7rem] text-chalk focus:border-tech/60"
                />
                <label className="flex items-center gap-1.5 text-[0.65rem] text-ash">
                  min score
                  <input
                    type="number"
                    value={minComposite}
                    min={0}
                    max={100}
                    onChange={(e) => setMinComposite(Number(e.target.value) || 0)}
                    aria-label="Minimum composite score"
                    className="h-7 w-14 rounded border border-rule bg-raised px-1.5 font-mono text-[0.7rem] text-chalk focus:border-tech/60"
                  />
                </label>
                <DownloadButton onClick={download}>CSV</DownloadButton>
              </div>
            </CardHeader>
            <CardBody className="px-0">
              {/* The ticker column stays put while the signal columns scroll,
                  because a row of seven percentiles is unreadable once you can
                  no longer see which name it belongs to. */}
              <div className="max-h-[36rem] overflow-auto">
                <table className="w-full text-left text-xs">
                  <thead className="sticky top-0 z-20 bg-panel">
                    <tr className="eyebrow border-b border-rule [&>th]:px-3 [&>th]:py-2 [&>th]:font-normal [&>th]:align-bottom">
                      <th scope="col" className="w-8 bg-panel" />
                      <th scope="col" className="w-10 bg-panel text-right">#</th>
                      <SortHeader label="Ticker" active={sortKey === "ticker"}
                                  ascending={ascending} onClick={() => toggleSort("ticker")}
                                  sticky />
                      <SortHeader label="Score" active={sortKey === "composite"}
                                  ascending={ascending} onClick={() => toggleSort("composite")}
                                  align="right" />
                      {signals.map((signal) => (
                        <SortHeader key={signal.key}
                                    label={signal.short}
                                    title={signal.label}
                                    hint={signal.evidence}
                                    active={sortKey === signal.key}
                                    ascending={ascending}
                                    onClick={() => toggleSort(signal.key)}
                                    align="right"
                                    explain={data.explain?.[`signalDefinition.${signal.key}`]} />
                      ))}
                      <SortHeader label="Close" active={sortKey === "close"}
                                  ascending={ascending} onClick={() => toggleSort("close")}
                                  align="right" />
                      <th scope="col" className="w-10 bg-panel text-center"
                          title={`Pick up to ${maxDeepen}`}>Pick</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => {
                      const open = expanded === row.ticker;
                      const deep = deepByTicker.get(row.ticker);
                      return (
                        <Fragment key={row.ticker}>
                          <tr
                              className="border-b border-rule/60 last:border-0 hover:bg-raised/60">
                            <td className="px-3 py-1.5">
                              <button
                                type="button"
                                aria-expanded={open}
                                aria-label={`Why ${row.ticker} ranked ${row.rank}`}
                                onClick={() => setExpanded(open ? null : row.ticker)}
                                className="text-ash transition-colors hover:text-chalk"
                              >
                                {open ? <ChevronDown className="h-3.5 w-3.5" />
                                      : <ChevronRight className="h-3.5 w-3.5" />}
                              </button>
                            </td>
                            <td className="num px-3 py-1.5 text-right text-ash">{row.rank}</td>
                            <td className="num sticky left-0 z-10 bg-panel px-3 py-1.5 font-semibold">
                              {onSelect ? (
                                <button
                                  type="button"
                                  onClick={() => onSelect(row.ticker)}
                                  title={`Load ${row.ticker} into every lens`}
                                  className={cn(
                                    "underline decoration-dotted decoration-rule underline-offset-4",
                                    "transition-colors hover:text-tech hover:decoration-tech",
                                    "focus:outline-none focus-visible:ring-1 focus-visible:ring-tech",
                                  )}
                                >
                                  {row.ticker}
                                </button>
                              ) : row.ticker}
                            </td>
                            <PercentileCell value={row.composite} />
                            {signals.map((signal) => (
                              <PercentileCell key={signal.key}
                                              value={row.signals[signal.key]?.percentile ?? null} />
                            ))}
                            <td className="num px-3 py-1.5 text-right text-ash">
                              {num(row.latestClose)}
                            </td>
                            <td className="px-3 py-1.5 text-center">
                              <input
                                type="checkbox"
                                checked={picked.includes(row.ticker)}
                                onChange={() => togglePick(row.ticker)}
                                disabled={!picked.includes(row.ticker) && picked.length >= maxDeepen}
                                aria-label={`Add ${row.ticker} to the shortlist`}
                                className="h-3 w-3 accent-tech"
                              />
                            </td>
                          </tr>
                          {open && (
                            <tr className="border-b border-rule/60">
                              <td colSpan={signals.length + 6} className="bg-ink/40 px-5 py-4">
                                <WhyRanked row={row} signals={allSignals} deep={deep} />
                              </td>
                            </tr>
                          )}
                        </Fragment>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {rows.length === 0 && (
                <p className="px-5 py-3 text-sm text-ash">
                  Nothing matches the filter.
                </p>
              )}

              <div className="space-y-2 px-5 pt-4">
                <p className="text-[0.7rem] leading-relaxed text-ash">
                  Every number in this table is a percentile within this scan, 0 to 100. The
                  score is a weighted mean of them — weights follow how well each signal is
                  supported in the literature, shown as a dot beside each column heading, and
                  that weighting is a judgement rather than a finding. Click a row&apos;s arrow
                  to see how it got its score; click the ticker to load it into all four lenses.
                </p>
                {data.missing.length > 0 && (
                  <p className="text-[0.7rem] leading-relaxed text-warn/90">
                    {data.missing.length} symbol{data.missing.length === 1 ? "" : "s"} could not
                    be ranked: <span className="font-mono">{data.missing.join(", ")}</span>. That
                    is either a delisting or acquisition since the list was written, or too
                    little price history — under {data.minBars} trading days a name is dropped
                    rather than ranked on whichever signals happened to compute.
                  </p>
                )}
                {data.benchmark == null && (
                  <p className="text-[0.7rem] leading-relaxed text-warn/90">
                    The benchmark index did not fetch, so the &quot;versus the index&quot; column
                    is empty for every name and each score is built from one fewer signal.
                  </p>
                )}
              </div>
            </CardBody>
          </Card>

          {/* ---------------- the deepen step ---------------- */}
          <Card accent={picked.length > 0 ? "#5B8DEF" : undefined}>
            <CardHeader>
              <CardTitle>Then look at the filings</CardTitle>
              <span className="font-mono text-[0.65rem] text-ash">
                {picked.length}/{maxDeepen} picked
              </span>
            </CardHeader>
            <CardBody className="space-y-3">
              <p className="text-[0.8rem] leading-relaxed text-ash">
                Everything above is computed from price and volume, which is the half that can be
                fetched for a hundred names at once. Accounting quality and intrinsic value need
                the filings, and those come one company at a time — a few seconds each — which is
                why they are a shortlist step rather than another column. Tick up to {maxDeepen}
                {" "}names above and run them here.
              </p>
              <div className="flex flex-wrap items-center gap-3">
                <ApplyButton
                  busy={deepState.status === "loading"}
                  onClick={() => deepen(picked, scanMarket)}
                >
                  Run quality &amp; value
                </ApplyButton>
                {picked.length === 0 && (
                  <span className="text-[0.7rem] text-ash">
                    Pick some names in the table first.
                  </span>
                )}
              </div>

              {deepState.status === "loading" && (
                <>
                  <p className="text-[0.75rem] leading-relaxed text-ash">
                    Reading the filings for {picked.length} compan
                    {picked.length === 1 ? "y" : "ies"}, one at a time — a few seconds each.
                  </p>
                  <PanelSkeleton />
                </>
              )}

              {deepState.status === "error" && (
                <p className="text-xs leading-relaxed text-dist">
                  {deepState.failure.message}
                </p>
              )}

              {deepState.status === "ready" && (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="eyebrow border-b border-rule [&>th]:px-3 [&>th]:py-2 [&>th]:font-normal">
                        <th>Ticker</th>
                        <th>Accounting quality</th>
                        <th>Health checks</th>
                        <th>Intrinsic value</th>
                        <th className="text-right">Gap to price</th>
                      </tr>
                    </thead>
                    <tbody>
                      {deepState.data.rows.map((row) => (
                        <DeepRow key={row.ticker} row={row} />
                      ))}
                    </tbody>
                  </table>
                  <p className="pt-3 text-[0.7rem] leading-relaxed text-ash">
                    {deepState.data.caveat}
                  </p>
                </div>
              )}
            </CardBody>
          </Card>
        </>
      )}

      <p className="text-xs leading-relaxed text-ash">
        Ranking is a shortlisting device. It says which names stand out against these particular
        peers on these particular measures today, which is a much weaker claim than it looks —
        and none of the signals here knows anything about the business. Educational and research
        use only.
      </p>
    </div>
  );
}

function SortHeader({
  label, active, ascending, onClick, align = "left", hint, explain, sticky, title,
}: {
  label: string; active: boolean; ascending: boolean; onClick: () => void;
  align?: "left" | "right"; hint?: string; sticky?: boolean; title?: string;
  explain?: React.ComponentProps<typeof Explain>["explain"];
}) {
  return (
    <th scope="col"
        className={cn("bg-panel", align === "right" && "text-right",
                      sticky && "sticky left-0 z-30")}
        aria-sort={active ? (ascending ? "ascending" : "descending") : "none"}>
      <span className={cn("inline-flex items-center gap-1",
                          align === "right" && "flex-row-reverse")}>
        <button type="button" onClick={onClick}
                title={`Sort by ${title ?? label}`}
                className={cn("whitespace-nowrap py-0.5 transition-colors hover:text-chalk",
                              active ? "text-chalk" : "")}>
          {label}{active && (ascending ? " ↑" : " ↓")}
        </button>
        {hint && (
          <span aria-hidden
                title={`${hint} evidence`}
                className={cn("inline-block h-1.5 w-1.5 rounded-full",
                              EVIDENCE_DOT[hint] ?? "bg-ash")} />
        )}
        {explain && <Explain explain={explain} />}
      </span>
    </th>
  );
}

/** The "why did this rank here" breakdown — the point of the whole panel. */
function WhyRanked({
  row, signals, deep,
}: { row: RankRow; signals: RankSignalDefinition[]; deep?: DeepenRow }) {
  const composite = row.explain?.compositeRank;
  return (
    <div className="space-y-3">
      {composite && (
        <div className="rounded border border-rule bg-panel px-3 py-2">
          <ExplanationBody explain={composite} />
        </div>
      )}
      <div className="grid gap-2 lg:grid-cols-2">
        {signals.map((signal) => {
          const cell = row.signals[signal.key];
          const explanation = row.explain?.[`signal.${signal.key}`];
          const definition = signal.detail;
          return (
            <div key={signal.key}
                 className="rounded border border-rule bg-panel px-3 py-2">
              <div className="mb-1 flex items-baseline justify-between gap-2">
                <span className="eyebrow">{signal.label}</span>
                <span className={cn("num text-sm font-semibold",
                                    heat(cell?.percentile ?? null))}>
                  {cell?.percentile == null ? "—" : cell.percentile.toFixed(0)}
                </span>
              </div>
              <p className="text-[0.7rem] leading-relaxed text-ash">
                {explanation?.reading ?? definition}
              </p>
              {explanation && (
                <p className={cn("mt-1 text-[0.65rem]",
                                 TONE_TEXT[explanation.tone] ?? "text-ash")}>
                  weight {signal.weight.toFixed(1)} · {signal.evidence} evidence
                </p>
              )}
            </div>
          );
        })}
      </div>
      {deep && (
        <div className="rounded border border-tech/40 bg-tech/5 px-3 py-2 text-[0.72rem] leading-relaxed">
          <span className="eyebrow mr-2">From the filings</span>
          {deep.quality.ok
            ? <span className="text-chalk/80">{deep.quality.data.headline}</span>
            : <span className="text-ash">Quality could not be computed for this listing.</span>}
        </div>
      )}
      <p className="text-[0.68rem] leading-relaxed text-ash">
        Coverage {pct(row.coverage, 0)} — {row.signalsAvailable} of {row.signalsTotal} signals
        contributed. A signal with too little history is left out and the remaining weights are
        renormalised, rather than filling the gap with the universe median and calling it a
        measurement.
      </p>
    </div>
  );
}

function DeepRow({ row }: { row: DeepenRow }) {
  const quality = row.quality.ok ? row.quality.data : null;
  const value = row.valuation.ok ? row.valuation.data : null;
  return (
    <tr className="border-b border-rule/60 last:border-0">
      <td className="num px-3 py-2 font-semibold">{row.ticker}</td>
      <td className="px-3 py-2">
        {quality == null ? <span className="text-ash">—</span>
          : !quality.applicable ? <span className="text-ash">not applicable</span>
            : <span className={quality.verdict === "SOUND" ? "text-acc"
                : quality.verdict === "CONCERNS" ? "text-dist" : "text-ash"}>
                {quality.verdict}
              </span>}
      </td>
      <td className="num px-3 py-2 text-ash">
        {quality?.piotroski
          ? `${quality.piotroski.score}/${quality.piotroski.maxScore} passed`
          : "—"}
      </td>
      <td className="px-3 py-2">
        {value == null ? <span className="text-ash">—</span>
          : <span className={value.verdict === "UNDERVALUED" ? "text-acc"
              : value.verdict === "OVERVALUED" ? "text-dist" : "text-ash"}>
              {value.medianLabel} · {value.verdict.toLowerCase()}
            </span>}
      </td>
      {/* One decimal, and signedPct rather than a hand-rolled sign. Rounding a
          -0.4% gap to zero decimals rendered it as "-0%", which reads as a bug
          rather than as "the model and the market agree". */}
      <td className={cn("num px-3 py-2 text-right",
                        (value?.upside ?? 0) >= 0 ? "text-acc" : "text-dist")}>
        {value?.upside == null ? "—" : signedPct(value.upside, 1)}
      </td>
    </tr>
  );
}
