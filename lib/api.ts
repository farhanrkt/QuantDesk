"use client";

import { track } from "@vercel/analytics";
import { useCallback, useEffect, useRef } from "react";
import { createTtlCache } from "./cache";
import { readSession, useSessionState, writeSession } from "./session";
import type { RunTuning } from "./url";
import type {
  AnomalyResponse, CompanyResponse, ConfluenceResponse, DeepenResponse, Engine, EngineFailure,
  ExposureScanResponse,
  Leg, ManualInputs, EventStudyResponse, Market, MarketBoard, MarketHeadlines, NewsResponse,
  QualityResponse,
  PeersResponse, PortfolioResponse, PreTrade, RankResponse, ScanResponse,
  ScreenerResponse, SymbolSearch,
  Synthesis, TechnicalResponse,
  UniversesResponse,
  ValuationResponse,
  VerdictResponse,
} from "./types";

/** Drops undefined/null/empty/NaN so optional params never reach the API as "". */
export function queryString(params: Record<string, string | number | boolean | null | undefined>) {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    // A NaN would serialise as the literal "NaN" and come back as an opaque 422.
    if (typeof value === "number" && !Number.isFinite(value)) continue;
    qs.set(key, String(value));
  }
  return qs.toString();
}

/**
 * FastAPI puts the payload under `detail`. The valuation engine sends an object
 * there (with `manualRequired`), every other route sends a string — normalise
 * both into one shape so callers never branch on it.
 *
 * No `cache: "no-store"`: the API sets `s-maxage=60` for the Vercel edge and
 * `max-age=0` for the browser, so every request still revalidates but repeats
 * within a minute are served by the CDN instead of re-hitting yfinance. The
 * old `no-store` was a REQUEST directive, which shared caches are specified to
 * honour — it was suppressing the very edge cache the API asks for.
 */
async function unwrap<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let failure: EngineFailure = { message: `Request failed (${res.status})` };
    try {
      const detail = (await res.json())?.detail;
      if (typeof detail === "string") failure = { message: detail };
      else if (detail && typeof detail === "object") failure = detail as EngineFailure;
    } catch {
      /* non-JSON error body — keep the status message */
    }
    throw failure;
  }
  return res.json() as Promise<T>;
}

async function get<T>(
  path: string,
  params: Record<string, unknown>,
  signal?: AbortSignal,
): Promise<T> {
  return unwrap<T>(await fetch(`${path}?${queryString(params as never)}`, { signal }));
}

/**
 * POST, for the routes whose input is personal, and the reason is the INPUT
 * rather than the size. There are two: holdings (/api/portfolio) and a reader's
 * own list to rank (/api/rank/list).
 *
 * Every other request here asks about a company, and a company name in a URL is
 * not a fact about anybody. A holdings list is — and URLs are logged by every
 * hop that handles them: the platform's access log, any proxy in between, the
 * browser's own history. None of that is reachable by a response header. A body
 * is not logged by default anywhere in that chain.
 *
 * The cost is honest and small: this app's stated shape was that everything the
 * UI does is a plain GET, and it is now "everything except the two routes whose
 * input is personal", which also means a CORS preflight on those calls. Cheaper
 * than putting somebody's portfolio, or their watchlist, in a log file.
 */
async function post<T>(
  path: string,
  body: unknown,
  signal?: AbortSignal,
): Promise<T> {
  return unwrap<T>(await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  }));
}

const asFailure = (err: unknown): EngineFailure =>
  err && typeof err === "object" && "message" in err
    ? (err as EngineFailure)
    : { message: String(err) };

/** An aborted request was superseded on purpose; it is never an error to show. */
const isAbort = (err: unknown) =>
  typeof err === "object" && err !== null && (err as { name?: string }).name === "AbortError";

/**
 * ONE SUPERSEDE GUARD PER KEY, AT MODULE SCOPE.
 *
 * Each request hook used to carry its own sequence counter and abort
 * controller in refs, which died with the component. Results now outlive the
 * component (lib/session.ts), so the guard has to as well: a peer comparison
 * started on the Trend tab must still be able to supersede itself after the
 * reader has switched tabs and back. The key is the same one the result is
 * stored under, so "newest request for peers:AAPL" is a question with one answer
 * however many components ask it.
 */
const guardSeq = new Map<string, number>();
const guardInflight = new Map<string, AbortController>();

function claimKey(key: string) {
  guardInflight.get(key)?.abort();
  const controller = new AbortController();
  guardInflight.set(key, controller);
  const token = (guardSeq.get(key) ?? 0) + 1;
  guardSeq.set(key, token);
  return { signal: controller.signal, live: () => guardSeq.get(key) === token };
}

function releaseKey(key: string) {
  guardInflight.get(key)?.abort();
  guardSeq.set(key, (guardSeq.get(key) ?? 0) + 1);
}

const IDLE = { status: "idle" } as const;

/**
 * An on-demand request whose result belongs to `key` — `peers:AAPL`, not "the
 * ticker on screen". Started with `run`, superseded by a newer `run` on the
 * same key, and written back under the key it was STARTED with, so a late
 * answer can never land under another company's header.
 */
function useRequest<P, T>(key: string, fetcher: (params: P, signal: AbortSignal) => Promise<T>) {
  const [state] = useSessionState<Engine<T>>(key, IDLE);
  const fetchRef = useRef(fetcher);
  fetchRef.current = fetcher;

  const run = useCallback((params: P) => {
    const k = key;
    const { signal, live } = claimKey(k);
    writeSession<Engine<T>>(k, { status: "loading" });
    fetchRef.current(params, signal)
      .then((data) => { if (live()) writeSession<Engine<T>>(k, { status: "ready", data, at: Date.now() }); })
      .catch((err) => {
        if (isAbort(err) || !live()) return;
        writeSession<Engine<T>>(k, { status: "error", failure: asFailure(err) });
      });
  }, [key]);

  const reset = useCallback(() => {
    releaseKey(key);
    writeSession<Engine<T>>(key, IDLE);
  }, [key]);

  return { state, run, reset };
}

const fromLeg = <T,>(leg: Leg<T>): Engine<T> =>
  leg.ok
    ? { status: "ready", data: leg.data }
    : { status: "error", failure: asFailure(leg.error) };

export interface RunOptions extends RunTuning {
  ticker: string;
  market: Market;
}

/** Everything the valuation engine will accept, all optional. */
export interface ValuationOptions {
  engine?: string;
  growth?: number;
  terminal?: number;
  rate?: number | null;
  nSims?: number;
  sdGrowth?: number;
  sdRate?: number;
  sdTerminal?: number;
  seed?: number;
  basis?: string;
  manual?: ManualInputs;
}

export interface TechnicalOptions {
  srWindow?: number;
  srLevels?: number;
}

const valuationParams = (o: RunOptions, v: ValuationOptions) => ({
  ticker: o.ticker, market: o.market,
  engine: v.engine ?? "auto",
  growth: v.growth, terminal: v.terminal, rate: v.rate,
  n_sims: v.nSims, sd_growth: v.sdGrowth, sd_rate: v.sdRate, sd_terminal: v.sdTerminal,
  seed: v.seed,
  // The engine picks the right one for the routed model and ignores the other.
  fcf_basis: v.basis, dps_basis: v.basis,
  manual_base: v.manual?.base, manual_net_debt: v.manual?.netDebt,
  manual_shares: v.manual?.shares, manual_price: v.manual?.price,
  manual_payout: v.manual?.payout,
});

/**
 * Every tuning knob the ticker bar exposes, forwarded to the one-shot endpoint.
 * Sending them is not optional: omit them and the server silently runs its
 * DEFAULT detection mode while the UI reports the mode the user selected.
 */
const confluenceParams = (o: RunOptions) => ({
  ticker: o.ticker, market: o.market,
  period: o.period, range: o.range,
  mode: o.mode, contamination: o.contamination,
  mad_k: o.madK, score_threshold: o.scoreThreshold,
});

/** Same query the JSON endpoint used, but the CSV of every Monte Carlo draw. */
export function simulationCsvUrl(o: RunOptions, v: ValuationOptions) {
  return `/api/intrinsic-value/simulation?${queryString(valuationParams(o, v) as never)}`;
}

// "company" rides in the same request and settles with it, so it is guarded
// like a leg; it is not a lens and nothing counts it as one.
type Lens = "anomaly" | "technical" | "valuation" | "quality" | "news" | "company";
const ALL_LENSES: Lens[] = ["anomaly", "technical", "valuation", "quality", "news", "company"];

/**
 * Every confluence payload this tab has already fetched, keyed by the exact
 * query string. A compare column and a stock page asking about the same company
 * with the same tuning share one entry — and one request if both ask at once.
 * See lib/cache.ts for what it deliberately does not do.
 */
const confluenceCache = createTtlCache<ConfluenceResponse>({ ttlMs: 300_000, max: 8 });

export function confluenceKey(o: RunOptions): string {
  return queryString(confluenceParams({ ...o, ticker: o.ticker.trim().toUpperCase() }));
}

/** One company's full read, through the shared cache. Used by the compare view. */
export function fetchConfluence(o: RunOptions) {
  const key = confluenceKey(o);
  return confluenceCache.getOrFetch(key, () => get<ConfluenceResponse>("/api/confluence",
    confluenceParams({ ...o, ticker: o.ticker.trim().toUpperCase() })));
}

/** A settled payload for these options, if this tab already holds a fresh one. */
export function peekConfluence(o: RunOptions) {
  return confluenceCache.peek(confluenceKey(o));
}

/** Everything one company's workspace shows, held per symbol in the session. */
export interface EngineSet {
  anomaly: Engine<AnomalyResponse>;
  technical: Engine<TechnicalResponse>;
  valuation: Engine<ValuationResponse>;
  quality: Engine<QualityResponse>;
  news: Engine<NewsResponse>;
  company: Engine<CompanyResponse>;
  // The synthesis arrives with the confluence payload and is the only piece of
  // state here that is not per-lens: it is a statement ABOUT the four together,
  // so a partial re-run of one lens deliberately clears it rather than leaving
  // a summary standing that describes figures no longer on screen.
  synthesis: Synthesis | null;
  // The pre-trade panel is cleared and restored on exactly the same rule, and
  // for a sharper version of the same reason: it reads the assembled payload,
  // so leaving it up beside a re-run lens would show conditions evaluated
  // against figures that are no longer the ones on screen. On this panel that
  // is worse than a stale summary — a flag nobody can reproduce from the page
  // is the one thing it must never print.
  preTrade: PreTrade | null;
  /** The confluence query this set was built from; a different one means re-run. */
  runKey: string | null;
  /** When the confluence payload behind this set was fetched. */
  at: number | null;
  /** Assumptions the reader applied to one lens since, so a CSV link can match them. */
  valuationOptions: ValuationOptions;
  technicalOptions: TechnicalOptions;
}

const EMPTY_SET: EngineSet = {
  anomaly: IDLE, technical: IDLE, valuation: IDLE, quality: IDLE, news: IDLE, company: IDLE,
  synthesis: null, preTrade: null, runKey: null, at: null,
  valuationOptions: {}, technicalOptions: {},
};

const LOADING_SET = (runKey: string): EngineSet => ({
  ...EMPTY_SET,
  anomaly: { status: "loading" }, technical: { status: "loading" },
  valuation: { status: "loading" }, quality: { status: "loading" }, news: { status: "loading" },
  company: { status: "loading" },
  runKey,
});

const setFromPayload = (payload: ConfluenceResponse, runKey: string, at: number): EngineSet => ({
  ...EMPTY_SET,
  anomaly: fromLeg(payload.anomaly),
  technical: fromLeg(payload.technical),
  valuation: fromLeg(payload.valuation),
  quality: fromLeg(payload.quality),
  news: fromLeg(payload.news),
  // An older cached payload (or an API without the leg) simply has no company
  // block; that is "not asked", not a failure.
  company: payload.company ? fromLeg(payload.company) : IDLE,
  synthesis: payload.synthesis ?? null,
  preTrade: payload.preTrade ?? null,
  runKey, at,
});

/**
 * A full run is ONE request to /api/confluence, which runs all four lenses
 * concurrently in a single serverless invocation. Four separate fetches meant
 * four cold starts, each paying the numpy + pandas + scipy + scikit-learn
 * import and each re-resolving the same symbol.
 *
 * Failure is still scoped to a single card — each leg reports its own outcome,
 * so a ticker with no dividend history renders its anomaly and technical panels
 * as usual.
 *
 * The valuation and technical engines can additionally be re-run ALONE against
 * the loaded ticker, so changing an assumption or a support/resistance window
 * does not re-fetch the others.
 *
 * KEYED BY SYMBOL. The whole set lives in the session under `engines:AAPL`, so
 * leaving for the compare view and coming back restores the page — refined
 * assumptions included — instead of running four engines again, and a response
 * for AAPL that lands after the reader has moved to NVDA writes to AAPL's slot
 * rather than NVDA's screen. Out-of-order settlement within one symbol is still
 * guarded per lens, exactly as before.
 */
export function useEngines(symbol: string) {
  const key = `engines:${symbol.trim().toUpperCase()}`;
  const [set] = useSessionState<EngineSet>(key, EMPTY_SET);

  const patch = useCallback((k: string, update: Partial<EngineSet>) => {
    writeSession<EngineSet>(k, (prev) => ({ ...(prev ?? EMPTY_SET), ...update }));
  }, []);

  const run = useCallback(async (opts: RunOptions) => {
    const ticker = opts.ticker.trim().toUpperCase();
    if (!ticker) return;
    const o = { ...opts, ticker };
    const k = `engines:${ticker}`;
    const runKey = confluenceKey(o);

    // Already fetched this exact read in the last few minutes: show it at once,
    // with no skeleton flash, and say when it was fetched.
    const hit = confluenceCache.peek(runKey);
    if (hit) { writeSession<EngineSet>(k, setFromPayload(hit.value, runKey, hit.at)); return; }

    // NO ABORT SIGNAL ON THE SHARED FETCH. The request goes through the cache,
    // where a compare column may be waiting on the same promise; aborting it
    // because this page was superseded would fail that column too. A late
    // answer still fills the cache for the next visit, and `live()` keeps it
    // off this screen.
    const { live } = claimKey(`${k}:run`);
    const lensTokens = ALL_LENSES.map((lens) => [lens, claimKey(`${k}:${lens}`)] as const);
    const current = (lens: Lens) => lensTokens.find(([l]) => l === lens)![1].live();
    writeSession<EngineSet>(k, LOADING_SET(runKey));

    let payload: ConfluenceResponse;
    let at: number;
    try {
      const result = await confluenceCache.getOrFetch(runKey, () =>
        get<ConfluenceResponse>("/api/confluence", confluenceParams(o)));
      payload = result.value;
      at = result.at;
    } catch (err) {
      if (isAbort(err) || !live()) return;
      // The request itself failed (network, 4xx, a Vercel timeout), so no leg
      // has a verdict — every panel reports the same cause.
      const failure = asFailure(err);
      const update: Partial<EngineSet> = {};
      for (const lens of ALL_LENSES) {
        if (current(lens)) update[lens] = { status: "error", failure };
      }
      patch(k, update);
      return;
    }
    if (!live()) return;

    const next = setFromPayload(payload, runKey, at);
    const update: Partial<EngineSet> = { synthesis: next.synthesis, preTrade: next.preTrade, runKey, at };
    for (const lens of ALL_LENSES) if (current(lens)) update[lens] = next[lens] as never;
    patch(k, update);

    // ONE AGGREGATE EVENT, AND DELIBERATELY NOT THE TICKER.
    //
    // "How many analyses has this run?" is a fair thing to measure and a far
    // better description of the app than a page-view count. "Which companies is
    // this person looking up?" is a different question, it is behavioural data
    // about an individual, and this app has no business collecting it — a
    // watchlist is one of the more revealing things someone can tell you.
    //
    // So the event carries the MARKET (US or ID, which says something about
    // reach) and HOW MANY LENSES SUCCEEDED (which is really a measure of how
    // often the upstream data source lets us down). Neither identifies anyone
    // or anything they looked at. `track` is a no-op off Vercel, so local runs
    // and self-hosted copies send nothing at all.
    const succeeded = [payload.anomaly, payload.technical,
                       payload.valuation, payload.quality].filter((leg) => leg?.ok).length;
    track("analysis", { market: o.market, lenses: succeeded });
  }, [patch]);

  /** Re-run one engine against the ticker already loaded. */
  const refine = useCallback(<T,>(lens: "technical" | "valuation", o: RunOptions,
                                  request: (signal: AbortSignal) => Promise<T>,
                                  options: Partial<EngineSet>) => {
    const k = `engines:${o.ticker.trim().toUpperCase()}`;
    const { signal, live } = claimKey(`${k}:${lens}`);
    // The synthesis quotes figures from the run it was built for. Re-running one
    // lens supersedes some of them, so it is dropped rather than left standing
    // beside numbers it no longer describes.
    patch(k, { [lens]: { status: "loading" }, synthesis: null, preTrade: null, ...options });
    request(signal)
      .then((data) => { if (live()) patch(k, { [lens]: { status: "ready", data, at: Date.now() } }); })
      .catch((err) => {
        if (isAbort(err) || !live()) return;   // superseded — leave the newer run alone
        patch(k, { [lens]: { status: "error", failure: asFailure(err) } });
      });
  }, [patch]);

  const refineValuation = useCallback((o: RunOptions, v: ValuationOptions) => {
    refine("valuation", o,
           (signal) => get<ValuationResponse>("/api/intrinsic-value", valuationParams(o, v), signal),
           { valuationOptions: v });
  }, [refine]);

  const refineTechnical = useCallback((o: RunOptions, t: TechnicalOptions) => {
    refine("technical", o,
           (signal) => get<TechnicalResponse>("/api/technical-analysis", {
             ticker: o.ticker, market: o.market, range: o.range,
             sr_window: t.srWindow, sr_levels: t.srLevels,
           }, signal),
           { technicalOptions: t });
  }, [refine]);

  return { ...set, run, refineValuation, refineTechnical };
}

/**
 * Signal validation, on demand.
 *
 * Deliberately NOT part of a ticker run: it needs five years of history plus the
 * benchmark index and is far slower than the other engines. It is also the one
 * result a user should ask for consciously — the answer is frequently "this
 * signal does not predict anything on this ticker", and that deserves a
 * deliberate click rather than arriving unbidden beside the chart.
 */
export function useEventStudy(symbol: string) {
  const { state, run, reset } = useRequest(`eventStudy:${symbol}`,
    (o: { ticker: string; market: Market; mode: string; scoreThreshold: number },
     signal: AbortSignal) =>
      get<EventStudyResponse>("/api/event-study", {
        ticker: o.ticker, market: o.market,
        // Walk-forward is not offered by the route; fall back to its default.
        mode: o.mode === "walkforward" ? "threshold" : o.mode,
        score_threshold: o.scoreThreshold,
      }, signal));
  return { state, validate: run, reset };
}

/** The screener is a separate, on-demand tool — it is not part of a ticker run. */
export function useScreener() {
  const { state, run } = useRequest("markets:screener",
    (params: { tickers: string; market: Market; period: string; mode: string; recentDays: number },
     signal: AbortSignal) =>
      get<ScreenerResponse>("/api/screener", {
        tickers: params.tickers, market: params.market, period: params.period,
        mode: params.mode, recent_days: params.recentDays,
      }, signal));
  return { state, scan: run };
}

/**
 * The breadth tier: rank a universe, then deepen a shortlist from it.
 *
 * Two hooks rather than one, because they are two requests with very different
 * costs and the user chooses whether to pay the second. A scan is a handful of
 * batched upstream calls; deepening is one fetch per name and takes seconds
 * each, which is exactly why the shortlist is small and explicit.
 *
 * THE CATALOGUE LOADS ITSELF, ONCE. It used to need a `load()` call, which the
 * ranking panel made and the page's own copy never did — so the exposure
 * panel's universe picker was empty for as long as it existed and every
 * exposure scan quietly ran the hidden default list.
 */
export function useUniverses() {
  const { state, run } = useRequest("universes",
    (_: void, signal: AbortSignal) => get<UniversesResponse>("/api/rank/universes", {}, signal));
  useEffect(() => {
    const current = readSession<Engine<UniversesResponse>>("universes");
    if (!current || current.status === "idle" || current.status === "error") run(undefined);
  }, [run]);
  return { state, load: () => run(undefined) };
}

export function useRanking() {
  // A second scan supersedes the first rather than racing it — the same guard
  // the single-ticker lenses use, and for the same reason: two scans settling
  // out of order would put one universe's rows under another's header.
  //
  // A READER'S OWN LIST GOES IN A BODY. A named index travels as its id; a list
  // somebody typed or keeps is a fact about them, so it goes to the POST route
  // for the same reason holdings do — see `post`, and RankListRequest in
  // api/index.py.
  const { state, run, reset } = useRequest("markets:rank",
    (params: { universe?: string | null; tickers?: string; market: Market }, signal: AbortSignal) =>
      params.universe
        ? get<RankResponse>("/api/rank", { universe: params.universe, market: params.market }, signal)
        : post<RankResponse>("/api/rank/list", {
            tickers: (params.tickers ?? "").split(/[\s,]+/).filter(Boolean),
            market: params.market,
          }, signal));
  return { state, scan: run, reset };
}

export function useExposureScan() {
  // Same supersede-rather-than-race guard as the ranking scan: two scans
  // settling out of order would put one universe's points under another's axis.
  const { state, run, reset } = useRequest("markets:exposure",
    (params: { universe?: string | null; tickers?: string; market: Market }, signal: AbortSignal) =>
      get<ExposureScanResponse>("/api/exposure", {
        universe: params.universe ?? undefined,
        tickers: params.universe ? undefined : params.tickers,
        market: params.market,
      }, signal));
  return { state, scan: run, reset };
}

export function useDeepen() {
  const { state, run, reset } = useRequest("markets:deepen",
    (params: { tickers: string[]; market: Market }, signal: AbortSignal) =>
      get<DeepenResponse>("/api/rank/deepen", {
        tickers: params.tickers.join(","), market: params.market,
      }, signal));
  return {
    state,
    deepen: (tickers: string[], market: Market) => run({ tickers, market }),
    reset,
  };
}

/**
 * Where the loaded ticker sits against a book of holdings.
 *
 * A SEPARATE, DELIBERATE REQUEST, like the peer comparison and for a sharper
 * reason. It costs a batch download of the whole book, most readers will not
 * have entered one, and — unlike every other route here — its input is personal.
 * Firing it automatically on every ticker run would send somebody's holdings to
 * the server on the strength of them having typed a symbol.
 *
 * The holdings themselves never reach the analytics event. `track` has always
 * carried a market code and a count of successful lenses and nothing else; a
 * portfolio is the single most revealing thing this app can be told, and it is
 * not collected. It travels in a POST body rather than a query string for the
 * same reason — see `post`.
 */
export function usePortfolio(symbol: string) {
  const { state, run, reset } = useRequest(`portfolio:${symbol}`,
    (o: { candidate: string; market: Market; holdings: string[]; weights?: Record<string, number> },
     signal: AbortSignal) =>
      // POST, so the holdings travel in a body rather than a URL. See `post`.
      post<PortfolioResponse>("/api/portfolio", {
        candidate: o.candidate, market: o.market,
        holdings: o.holdings, weights: o.weights ?? {},
      }, signal));
  return { state, compare: run, reset };
}

/**
 * Peer comparison, on demand.
 *
 * NOT part of a ticker run, and that is a cost decision rather than a taste one:
 * placing a name against the Nasdaq-100 means scanning the Nasdaq-100, which is
 * about six seconds and shares the ranking tier's 3-per-minute cap. Attaching
 * that to `/api/confluence` would multiply the cost of the app's most-used route
 * for something most readers will not open.
 *
 * Keyed by symbol, so a placing belongs to the ticker it was run for and can
 * never appear under another firm's header — the same class of mistake
 * `_lib/symbols.py` exists to prevent, arriving through the UI instead.
 */
export function usePeers(symbol: string) {
  const { state, run, reset } = useRequest(`peers:${symbol}`,
    (o: { ticker: string; market: Market; universe?: string }, signal: AbortSignal) =>
      get<PeersResponse>("/api/peers", {
        ticker: o.ticker, market: o.market, universe: o.universe,
      }, signal));
  return { state, compare: run, reset };
}

/**
 * The latest market scan that was run on THIS machine.
 *
 * READS A FILE, RUNS NOTHING. A whole-exchange sweep is about an hour; the
 * route serves the report the script already wrote. It therefore has no busy
 * state worth showing beyond a moment's fetch, and it comes back
 * `available: false` wherever no scan has been run — a fresh checkout, or the
 * deployed app, where `reports/` does not exist.
 */
export function useScan(market: Market) {
  const key = `scan:${market}`;
  const { state, run } = useRequest(key,
    (m: Market, signal: AbortSignal) => get<ScanResponse>("/api/scan/latest", { market: m }, signal));
  // Loaded on mount and whenever the market changes, because it costs one read
  // of a local file and the alternative is a button nobody presses — which is
  // how the scan results went unseen for a week.
  useEffect(() => {
    const current = readSession<Engine<ScanResponse>>(key);
    if (!current || current.status === "idle") run(market);
  }, [key, market, run]);
  return { state, reload: () => run(market) };
}

/**
 * The private scanner's verdict for one name.
 *
 * A SEPARATE, DELIBERATE REQUEST, for the same reason `usePeers` is one: the
 * route runs a whole universe scan for the percentile AND four per-symbol
 * lenses on top, about eight seconds, sharing the ranking tier's per-IP cap.
 * That cost belongs to a reader who asked for it rather than to every ticker
 * run — and it is a question most readers of the single-company view are not
 * asking, which is the more important half.
 *
 * It is kept for the session under its symbol and stamped with when it was
 * computed, because a stale verdict is the failure mode this app is least
 * equipped to notice — it looks identical to a fresh one — and the panel shows
 * the stamp beside the score.
 */
export function useVerdict(symbol: string) {
  const { state, run, reset } = useRequest(`verdict:${symbol}`,
    (o: { ticker: string; market: Market; universe?: string }, signal: AbortSignal) =>
      get<VerdictResponse>("/api/verdict", {
        ticker: o.ticker, market: o.market, universe: o.universe,
      }, signal));
  return { state, score: run, reset };
}

/**
 * Listings matching what is typed into the command palette. A plain function,
 * not a hook: the palette debounces and supersedes its own requests, and the
 * answer is never worth keeping beyond the moment it was asked.
 */
export function searchSymbols(q: string, market: Market | null, signal?: AbortSignal) {
  return get<SymbolSearch>("/api/symbols", { q, market: market ?? undefined, limit: 8 }, signal);
}

/**
 * The board of what moved the markets. TAKES NOTHING, deliberately: the board is
 * the same for every reader, so it is one edge-cache entry, and which of these a
 * stock moves with is matched in the browser from the Trend tab's exposure
 * figures — no ticker is ever sent for it (check_frontend.mjs holds this).
 */
export function fetchMarketBoard(signal?: AbortSignal) {
  return get<MarketBoard>("/api/markets/today", {}, signal);
}

/** The past day's headlines mentioning a market. Topics are keys from a declared list. */
export function fetchMarketHeadlines(market: Market, topics: string[], signal?: AbortSignal) {
  return get<MarketHeadlines>("/api/markets/headlines",
                              { market, topics: topics.join(","), limit: 4 }, signal);
}
