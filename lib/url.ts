/**
 * What the address bar carries, and nothing more.
 * ===============================================
 *
 * A refresh used to lose everything — the ticker, the tab, the detection mode —
 * because none of it lived anywhere but React state, and a link could not say
 * "look at the Value tab for BBCA.JK". Now the path names the company and the
 * query names the tab and any tuning that differs from the defaults.
 *
 * ONLY NON-DEFAULT VALUES ARE WRITTEN. `/stock/AAPL` and
 * `/stock/AAPL?tab=trend&period=2y&range=5y&mode=threshold` describe the same
 * page; writing the second form would make every shared link a wall of
 * parameters nobody chose, and would make two links to one page look different.
 *
 * WHAT NEVER GOES IN A URL: holdings, the journal, the watchlist. A ticker is
 * not a fact about anybody; a list of them that someone keeps is. Those travel
 * in a POST body or stay in the browser (see lib/api.ts and lib/watchlist.ts).
 * A compare set of up to four tickers is the one list that does appear, because
 * it is a research question typed in the moment rather than a record kept — the
 * same status as a single ticker — and analytics redact it (lib/redact.ts).
 *
 * Pure: compiled into the frontend assertions and pinned there.
 */
import { isTicker, resolveSymbol } from "./symbols";

/** Detection and look-back knobs a run can carry, beside the ticker itself. */
export interface RunTuning {
  period: string;          // anomaly look-back
  range: string;           // technical look-back
  mode: string;            // detection mode
  contamination: number;   // quota mode
  madK: number;            // mad mode
  scoreThreshold: number;  // threshold mode
}

export const RUN_DEFAULTS: RunTuning = {
  // `range` drives the technical lens. 5y is the shortest window where drawdown
  // depth and rolling multi-year returns mean anything.
  period: "2y", range: "5y", mode: "threshold",
  contamination: 0.02, madK: 3.0, scoreThreshold: -0.10,
};

/** Accepted values, mirroring the API's own validation so a link cannot 422. */
const PERIODS = ["6mo", "1y", "2y", "5y", "max"];
const RANGES = ["3mo", "6mo", "1y", "2y", "5y", "10y", "max"];
const MODES = ["threshold", "mad", "quota", "walkforward"];

/**
 * The stock workspace's tabs, in the order they are drawn. `score` is the
 * private tier and comes last for the reason given where the tabs are defined.
 */
export const STOCK_TABS = [
  "company", "flow", "trend", "value", "quality", "portfolio", "exposure", "thesis", "score",
] as const;
export type StockTab = (typeof STOCK_TABS)[number];
/**
 * TREND, NOT FLOW, AND NOT COMPANY. The first drill-down should land on the
 * strongest evidence in the app; Flow is the weakest. Company sits first in the
 * order because it is orientation, but a compact company header on every tab
 * already answers "what does it do" without a click.
 */
export const DEFAULT_TAB: StockTab = "trend";

export const MARKET_VIEWS = ["rank", "screener", "scan", "exposure"] as const;
export type MarketView = (typeof MARKET_VIEWS)[number];

export const MAX_COMPARE = 4;

/**
 * The tickers offered to a newcomer who does not know one yet — and the stock
 * pages rendered at build time. Here rather than beside the ticker bar because
 * the server route needs the list itself, and a "use client" module hands a
 * server component a client reference, not an array.
 */
export const PRESETS = ["AAPL", "NVDA", "JPM", "BBCA.JK", "TLKM.JK", "BTC-USD"];

const num = (raw: string | null, lo: number, hi: number): number | undefined => {
  if (raw === null || raw.trim() === "") return undefined;
  const v = Number(raw);
  return Number.isFinite(v) && v >= lo && v <= hi ? v : undefined;
};

/** Parse a stock page's query string. Anything unrecognised is dropped, never trusted. */
export function parseStockQuery(search: string): { tab: StockTab; run: RunTuning } {
  const q = new URLSearchParams(search.startsWith("?") ? search.slice(1) : search);
  const tab = q.get("tab");
  const period = q.get("period");
  const range = q.get("range");
  const mode = q.get("mode");
  return {
    tab: (STOCK_TABS as readonly string[]).includes(tab ?? "") ? (tab as StockTab) : DEFAULT_TAB,
    run: {
      period: period && PERIODS.includes(period) ? period : RUN_DEFAULTS.period,
      range: range && RANGES.includes(range) ? range : RUN_DEFAULTS.range,
      mode: mode && MODES.includes(mode) ? mode : RUN_DEFAULTS.mode,
      contamination: num(q.get("q"), 0.001, 0.499) ?? RUN_DEFAULTS.contamination,
      madK: num(q.get("k"), 0.5, 10) ?? RUN_DEFAULTS.madK,
      scoreThreshold: num(q.get("t"), -0.5, 0.5) ?? RUN_DEFAULTS.scoreThreshold,
    },
  };
}

/** The query string for a stock page, writing only what differs from the defaults. */
export function stockQuery(tab: StockTab = DEFAULT_TAB, run: Partial<RunTuning> = {}): string {
  const q = new URLSearchParams();
  if (tab !== DEFAULT_TAB) q.set("tab", tab);
  const r = { ...RUN_DEFAULTS, ...run };
  if (r.period !== RUN_DEFAULTS.period) q.set("period", r.period);
  if (r.range !== RUN_DEFAULTS.range) q.set("range", r.range);
  if (r.mode !== RUN_DEFAULTS.mode) q.set("mode", r.mode);
  if (r.contamination !== RUN_DEFAULTS.contamination) q.set("q", String(r.contamination));
  if (r.madK !== RUN_DEFAULTS.madK) q.set("k", String(r.madK));
  if (r.scoreThreshold !== RUN_DEFAULTS.scoreThreshold) q.set("t", String(r.scoreThreshold));
  const s = q.toString();
  return s ? `?${s}` : "";
}

/** `/stock/BBCA.JK?tab=value` — the symbol is encoded, so `^GSPC` survives a path. */
export function stockHref(symbol: string, tab?: StockTab, run?: Partial<RunTuning>): string {
  return `/stock/${encodeURIComponent(symbol.trim().toUpperCase())}${stockQuery(tab, run)}`;
}

/** The symbol a path segment names, or null when it is not a ticker at all. */
export function symbolFromSegment(segment: string): string | null {
  let decoded: string;
  try { decoded = decodeURIComponent(segment); } catch { return null; }
  return isTicker(decoded) ? decoded.trim().toUpperCase() : null;
}

/**
 * A compare list from free text or a query value: resolved, de-duplicated,
 * order kept, at most four. Order is the reader's, and is never changed here —
 * see lib/compare.ts for why a compare view must not sort.
 */
export function parseSymbolList(raw: string | null | undefined,
                                market: "US" | "ID" = "US"): string[] {
  const out: string[] = [];
  for (const part of (raw ?? "").split(/[\s,]+/)) {
    if (!part || !isTicker(part)) continue;
    const symbol = resolveSymbol(part, market);
    if (!out.includes(symbol)) out.push(symbol);
    if (out.length === MAX_COMPARE) break;
  }
  return out;
}

export function compareHref(symbols: string[]): string {
  const list = parseSymbolList(symbols.join(","));
  return list.length ? `/compare?symbols=${list.map(encodeURIComponent).join(",")}` : "/compare";
}

export function marketsHref(view: MarketView = "rank"): string {
  return view === "rank" ? "/markets" : `/markets?view=${view}`;
}

export function parseMarketView(raw: string | null): MarketView {
  return (MARKET_VIEWS as readonly string[]).includes(raw ?? "") ? (raw as MarketView) : "rank";
}
