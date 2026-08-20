"use client";

import { useCallback, useRef, useState } from "react";
import type {
  AnomalyResponse, ConfluenceResponse, Engine, EngineFailure, Leg, ManualInputs,
  Market, NewsResponse, ScreenerResponse, TechnicalResponse, ValuationResponse,
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

type Lens = "anomaly" | "technical" | "valuation" | "news";
const ALL_LENSES: Lens[] = ["anomaly", "technical", "valuation", "news"];

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
    anomaly: 0, technical: 0, valuation: 0, news: 0,
  });
  const inflight = useRef<Record<Lens, AbortController | null>>({
    anomaly: null, technical: null, valuation: null, news: null,
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
  const [news, setNews] = useState<Engine<NewsResponse>>({ status: "idle" });

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
    setNews({ status: "loading" });

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
      if (current("news")) setNews({ status: "error", failure });
      return;
    }

    if (current("anomaly")) setAnomaly(fromLeg(payload.anomaly));
    if (current("technical")) setTechnical(fromLeg(payload.technical));
    if (current("valuation")) setValuation(fromLeg(payload.valuation));
    if (current("news")) setNews(fromLeg(payload.news));
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
    anomaly, technical, valuation, news,
    run, refineValuation, refineTechnical, csvUrl,
    valuationOptions: lastValuation, technicalOptions: lastTechnical,
  };
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
