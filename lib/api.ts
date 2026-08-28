"use client";

import { track } from "@vercel/analytics";
import { useCallback, useRef, useState } from "react";
import type {
  AnomalyResponse, ConfluenceResponse, DeepenResponse, Engine, EngineFailure,
  Leg, ManualInputs, EventStudyResponse, Market, NewsResponse, QualityResponse,
  PeersResponse, PortfolioResponse, PreTrade, RankResponse, ScreenerResponse,
  Synthesis, TechnicalResponse,
  UniversesResponse,
  ValuationResponse,
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
async function get<T>(
  path: string,
  params: Record<string, unknown>,
  signal?: AbortSignal,
): Promise<T> {
  const res = await fetch(`${path}?${queryString(params as never)}`, { signal });
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

const asFailure = (err: unknown): EngineFailure =>
  err && typeof err === "object" && "message" in err
    ? (err as EngineFailure)
    : { message: String(err) };

/** An aborted request was superseded on purpose; it is never an error to show. */
const isAbort = (err: unknown) =>
  typeof err === "object" && err !== null && (err as { name?: string }).name === "AbortError";

const fromLeg = <T,>(leg: Leg<T>): Engine<T> =>
  leg.ok
    ? { status: "ready", data: leg.data }
    : { status: "error", failure: asFailure(leg.error) };

export interface RunOptions {
  ticker: string;
  market: Market;
  period: string;   // anomaly look-back
  range: string;    // technical look-back
  mode: string;     // detection mode
  contamination: number;  // quota mode
  madK: number;           // mad mode
  scoreThreshold: number; // threshold mode
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

type Lens = "anomaly" | "technical" | "valuation" | "quality" | "news";
const ALL_LENSES: Lens[] = ["anomaly", "technical", "valuation", "quality", "news"];

/**
 * Guards against out-of-order settlement.
 *
 * Run AAPL, then immediately NVDA: the two runs are independent requests that
 * resolve at whatever speed the upstream allows, so AAPL's slower response
 * could land after NVDA's and leave one company's flow beside another's
 * valuation — with the confluence rail scoring "agreement" across two different
 * securities. Every dispatch takes a fresh token per lens it owns and aborts
 * whatever that lens had in flight; a response only applies while its token is
 * still the newest one.
 */
function useLensGuard() {
  const seq = useRef<Record<Lens, number>>({
    anomaly: 0, technical: 0, valuation: 0, quality: 0, news: 0,
  });
  const inflight = useRef<Record<Lens, AbortController | null>>({
    anomaly: null, technical: null, valuation: null, quality: null, news: null,
  });

  return useCallback((lenses: Lens[]) => {
    const controller = new AbortController();
    const tokens = new Map<Lens, number>();
    for (const lens of lenses) {
      inflight.current[lens]?.abort();
      inflight.current[lens] = controller;
      seq.current[lens] += 1;
      tokens.set(lens, seq.current[lens]);
    }
    return {
      signal: controller.signal,
      /** True only while this dispatch is still the newest for that lens. */
      current: (lens: Lens) => seq.current[lens] === tokens.get(lens),
    };
  }, []);
}

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
 */
export function useEngines() {
  const [anomaly, setAnomaly] = useState<Engine<AnomalyResponse>>({ status: "idle" });
  const [technical, setTechnical] = useState<Engine<TechnicalResponse>>({ status: "idle" });
  const [valuation, setValuation] = useState<Engine<ValuationResponse>>({ status: "idle" });
  const [quality, setQuality] = useState<Engine<QualityResponse>>({ status: "idle" });
  const [news, setNews] = useState<Engine<NewsResponse>>({ status: "idle" });
  // The synthesis arrives with the confluence payload and is the only piece of
  // state here that is not per-lens: it is a statement ABOUT the four together,
  // so a partial re-run of one lens deliberately clears it rather than leaving
  // a summary standing that describes figures no longer on screen.
  const [synthesis, setSynthesis] = useState<Synthesis | null>(null);
  // The pre-trade panel is cleared and restored on exactly the same rule, and
  // for a sharper version of the same reason: it reads the assembled payload,
  // so leaving it up beside a re-run lens would show conditions evaluated
  // against figures that are no longer the ones on screen. On this panel that
  // is worse than a stale summary — a flag nobody can reproduce from the page
  // is the one thing it must never print.
  const [preTrade, setPreTrade] = useState<PreTrade | null>(null);

  // The last options each engine ran with, so a partial re-run can reuse them.
  const lastRun = useRef<RunOptions | null>(null);
  const lastValuation = useRef<ValuationOptions>({});
  const lastTechnical = useRef<TechnicalOptions>({});

  const claim = useLensGuard();

  const settle = <T,>(
    promise: Promise<T>,
    set: (s: Engine<T>) => void,
    live: () => boolean,
  ) =>
    promise
      .then((data) => { if (live()) set({ status: "ready", data }); })
      .catch((err) => {
        if (isAbort(err) || !live()) return;   // superseded — leave the newer run alone
        set({ status: "error", failure: asFailure(err) });
      });

  const runTechnical = useCallback((o: RunOptions, t: TechnicalOptions = {}) => {
    lastTechnical.current = t;
    const { signal, current } = claim(["technical"]);
    setTechnical({ status: "loading" });
    // The synthesis quotes figures from the run it was built for. Re-running one
    // lens supersedes some of them, so it is dropped rather than left standing
    // beside numbers it no longer describes.
    setSynthesis(null);
    setPreTrade(null);
    return settle(
      get<TechnicalResponse>("/api/technical-analysis", {
        ticker: o.ticker, market: o.market, range: o.range,
        sr_window: t.srWindow, sr_levels: t.srLevels,
      }, signal),
      setTechnical,
      () => current("technical"),
    );
  }, [claim]);

  const runValuation = useCallback((o: RunOptions, v: ValuationOptions = {}) => {
    lastValuation.current = v;
    const { signal, current } = claim(["valuation"]);
    setValuation({ status: "loading" });
    setSynthesis(null);          // see runTechnical
    setPreTrade(null);
    return settle(
      get<ValuationResponse>("/api/intrinsic-value", valuationParams(o, v), signal),
      setValuation,
      () => current("valuation"),
    );
  }, [claim]);

  const run = useCallback(async (opts: RunOptions) => {
    const ticker = opts.ticker.trim().toUpperCase();
    if (!ticker) return;
    const o = { ...opts, ticker };
    lastRun.current = o;
    // A fresh ticker resets per-engine tuning; stale assumptions from the last
    // company would be applied silently to this one.
    lastValuation.current = {};
    lastTechnical.current = {};

    const { signal, current } = claim(ALL_LENSES);
    setAnomaly({ status: "loading" });
    setTechnical({ status: "loading" });
    setValuation({ status: "loading" });
    setQuality({ status: "loading" });
    setNews({ status: "loading" });
    setSynthesis(null);
    setPreTrade(null);

    let payload: ConfluenceResponse;
    try {
      payload = await get<ConfluenceResponse>("/api/confluence", confluenceParams(o), signal);
    } catch (err) {
      if (isAbort(err)) return;
      // The request itself failed (network, 4xx, a Vercel timeout), so no leg
      // has a verdict — every panel reports the same cause.
      const failure = asFailure(err);
      if (current("anomaly")) setAnomaly({ status: "error", failure });
      if (current("technical")) setTechnical({ status: "error", failure });
      if (current("valuation")) setValuation({ status: "error", failure });
      if (current("quality")) setQuality({ status: "error", failure });
      if (current("news")) setNews({ status: "error", failure });
      return;
    }

    if (current("anomaly")) setAnomaly(fromLeg(payload.anomaly));
    if (current("technical")) setTechnical(fromLeg(payload.technical));
    if (current("valuation")) setValuation(fromLeg(payload.valuation));
    if (current("quality")) setQuality(fromLeg(payload.quality));
    if (current("news")) setNews(fromLeg(payload.news));
    if (current("anomaly")) setSynthesis(payload.synthesis ?? null);
    if (current("anomaly")) setPreTrade(payload.preTrade ?? null);

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
  }, [claim]);

  /** Re-run one engine against the ticker already loaded. */
  const refineValuation = useCallback((v: ValuationOptions) => {
    if (lastRun.current) runValuation(lastRun.current, v);
  }, [runValuation]);

  const refineTechnical = useCallback((t: TechnicalOptions) => {
    if (lastRun.current) runTechnical(lastRun.current, t);
  }, [runTechnical]);

  const csvUrl = useCallback(
    () => (lastRun.current ? simulationCsvUrl(lastRun.current, lastValuation.current) : "#"),
    []
  );

  return {
    anomaly, technical, valuation, quality, news, synthesis, preTrade,
    run, refineValuation, refineTechnical, csvUrl,
    valuationOptions: lastValuation, technicalOptions: lastTechnical,
  };
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
export function useEventStudy() {
  const [state, setState] = useState<Engine<EventStudyResponse>>({ status: "idle" });
  const seq = useRef(0);
  const inflight = useRef<AbortController | null>(null);

  const validate = useCallback((o: { ticker: string; market: Market; mode: string;
                                     scoreThreshold: number }) => {
    inflight.current?.abort();
    const controller = new AbortController();
    inflight.current = controller;
    const token = (seq.current += 1);
    const live = () => seq.current === token;

    setState({ status: "loading" });
    get<EventStudyResponse>("/api/event-study", {
      ticker: o.ticker, market: o.market,
      // Walk-forward is not offered by the route; fall back to its default.
      mode: o.mode === "walkforward" ? "threshold" : o.mode,
      score_threshold: o.scoreThreshold,
    }, controller.signal)
      .then((data) => { if (live()) setState({ status: "ready", data }); })
      .catch((err) => {
        if (isAbort(err) || !live()) return;
        setState({ status: "error", failure: asFailure(err) });
      });
  }, []);

  const reset = useCallback(() => {
    inflight.current?.abort();
    seq.current += 1;
    setState({ status: "idle" });
  }, []);

  return { state, validate, reset };
}

/** The screener is a separate, on-demand tool — it is not part of a ticker run. */
export function useScreener() {
  const [state, setState] = useState<Engine<ScreenerResponse>>({ status: "idle" });
  const seq = useRef(0);
  const inflight = useRef<AbortController | null>(null);

  const scan = useCallback((params: {
    tickers: string; market: Market; period: string; mode: string; recentDays: number;
  }) => {
    // A second scan supersedes the first rather than racing it.
    inflight.current?.abort();
    const controller = new AbortController();
    inflight.current = controller;
    const token = (seq.current += 1);
    const live = () => seq.current === token;

    setState({ status: "loading" });
    get<ScreenerResponse>("/api/screener", {
      tickers: params.tickers, market: params.market, period: params.period,
      mode: params.mode, recent_days: params.recentDays,
    }, controller.signal)
      .then((data) => { if (live()) setState({ status: "ready", data }); })
      .catch((err) => {
        if (isAbort(err) || !live()) return;
        setState({ status: "error", failure: asFailure(err) });
      });
  }, []);

  return { state, scan };
}


/**
 * The breadth tier: rank a universe, then deepen a shortlist from it.
 *
 * Two hooks rather than one, because they are two requests with very different
 * costs and the user chooses whether to pay the second. A scan is a handful of
 * batched upstream calls; deepening is one fetch per name and takes seconds
 * each, which is exactly why the shortlist is small and explicit.
 */
export function useUniverses() {
  const [state, setState] = useState<Engine<UniversesResponse>>({ status: "idle" });

  const load = useCallback(() => {
    setState({ status: "loading" });
    get<UniversesResponse>("/api/rank/universes", {})
      .then((data) => setState({ status: "ready", data }))
      .catch((err) => setState({ status: "error", failure: asFailure(err) }));
  }, []);

  return { state, load };
}

export function useRanking() {
  const [state, setState] = useState<Engine<RankResponse>>({ status: "idle" });
  const seq = useRef(0);
  const inflight = useRef<AbortController | null>(null);

  const scan = useCallback((params: {
    universe?: string | null; tickers?: string; market: Market;
  }) => {
    // A second scan supersedes the first rather than racing it — the same
    // guard the single-ticker lenses use, and for the same reason: two scans
    // settling out of order would put one universe's rows under another's
    // header.
    inflight.current?.abort();
    const controller = new AbortController();
    inflight.current = controller;
    const token = (seq.current += 1);
    const live = () => seq.current === token;

    setState({ status: "loading" });
    get<RankResponse>("/api/rank", {
      universe: params.universe ?? undefined,
      tickers: params.universe ? undefined : params.tickers,
      market: params.market,
    }, controller.signal)
      .then((data) => { if (live()) setState({ status: "ready", data }); })
      .catch((err) => {
        if (isAbort(err) || !live()) return;
        setState({ status: "error", failure: asFailure(err) });
      });
  }, []);

  const reset = useCallback(() => {
    inflight.current?.abort();
    seq.current += 1;
    setState({ status: "idle" });
  }, []);

  return { state, scan, reset };
}

export function useDeepen() {
  const [state, setState] = useState<Engine<DeepenResponse>>({ status: "idle" });
  const seq = useRef(0);
  const inflight = useRef<AbortController | null>(null);

  const deepen = useCallback((tickers: string[], market: Market) => {
    inflight.current?.abort();
    const controller = new AbortController();
    inflight.current = controller;
    const token = (seq.current += 1);
    const live = () => seq.current === token;

    setState({ status: "loading" });
    get<DeepenResponse>("/api/rank/deepen", {
      tickers: tickers.join(","), market,
    }, controller.signal)
      .then((data) => { if (live()) setState({ status: "ready", data }); })
      .catch((err) => {
        if (isAbort(err) || !live()) return;
        setState({ status: "error", failure: asFailure(err) });
      });
  }, []);

  const reset = useCallback(() => {
    inflight.current?.abort();
    seq.current += 1;
    setState({ status: "idle" });
  }, []);

  return { state, deepen, reset };
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
 * `reset` exists because a peer placing belongs to the ticker it was run for.
 * Carrying one across a new company would put another firm's percentiles under
 * this firm's header — the same class of mistake `_lib/symbols.py` exists to
 * prevent, arriving through the UI instead of the API.
 */
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
 * not collected.
 */
export function usePortfolio() {
  const [state, setState] = useState<Engine<PortfolioResponse>>({ status: "idle" });
  const seq = useRef(0);
  const inflight = useRef<AbortController | null>(null);

  const compare = useCallback(
    (o: { candidate: string; market: Market; holdings: string[]; weights?: string }) => {
      inflight.current?.abort();
      const controller = new AbortController();
      inflight.current = controller;
      const token = (seq.current += 1);
      const live = () => seq.current === token;

      setState({ status: "loading" });
      get<PortfolioResponse>("/api/portfolio", {
        candidate: o.candidate, market: o.market,
        holdings: o.holdings.join(","), weights: o.weights,
      }, controller.signal)
        .then((data) => { if (live()) setState({ status: "ready", data }); })
        .catch((err) => {
          if (isAbort(err) || !live()) return;
          setState({ status: "error", failure: asFailure(err) });
        });
    }, []);

  const reset = useCallback(() => {
    inflight.current?.abort();
    seq.current += 1;
    setState({ status: "idle" });
  }, []);

  return { state, compare, reset };
}

export function usePeers() {
  const [state, setState] = useState<Engine<PeersResponse>>({ status: "idle" });
  const seq = useRef(0);
  const inflight = useRef<AbortController | null>(null);

  const compare = useCallback((o: { ticker: string; market: Market; universe?: string }) => {
    inflight.current?.abort();
    const controller = new AbortController();
    inflight.current = controller;
    const token = (seq.current += 1);
    const live = () => seq.current === token;

    setState({ status: "loading" });
    get<PeersResponse>("/api/peers", {
      ticker: o.ticker, market: o.market, universe: o.universe,
    }, controller.signal)
      .then((data) => { if (live()) setState({ status: "ready", data }); })
      .catch((err) => {
        if (isAbort(err) || !live()) return;
        setState({ status: "error", failure: asFailure(err) });
      });
  }, []);

  const reset = useCallback(() => {
    inflight.current?.abort();
    seq.current += 1;
    setState({ status: "idle" });
  }, []);

  return { state, compare, reset };
}
