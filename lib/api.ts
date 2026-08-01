"use client";

import { useCallback, useRef, useState } from "react";
import type {
  AnomalyResponse, Engine, EngineFailure, ManualInputs, Market,
  NewsResponse, ScreenerResponse, TechnicalResponse, ValuationResponse,
} from "./types";

/** Drops undefined/null/empty so optional params never reach the API as "". */
export function queryString(params: Record<string, string | number | boolean | null | undefined>) {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    qs.set(key, String(value));
  }
  return qs.toString();
}

/**
 * FastAPI puts the payload under `detail`. The valuation engine sends an object
 * there (with `manualRequired`), every other route sends a string — normalise
 * both into one shape so callers never branch on it.
 */
async function get<T>(path: string, params: Record<string, unknown>): Promise<T> {
  const res = await fetch(`${path}?${queryString(params as never)}`, { cache: "no-store" });
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

const anomalyParams = (o: RunOptions) => ({
  ticker: o.ticker, market: o.market, period: o.period, mode: o.mode,
  contamination: o.contamination, mad_k: o.madK, score_threshold: o.scoreThreshold,
});

/** Same query the JSON endpoint used, but the CSV of every Monte Carlo draw. */
export function simulationCsvUrl(o: RunOptions, v: ValuationOptions) {
  return `/api/intrinsic-value/simulation?${queryString(valuationParams(o, v) as never)}`;
}

/**
 * The three engines are independent: a ticker with no dividend history should
 * still render its anomaly and technical panels. So each one settles on its
 * own and failure is scoped to a single card.
 *
 * Each engine can also be re-run alone, so changing a valuation assumption or a
 * support/resistance window does not re-fetch the other two.
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

  const settle = <T,>(promise: Promise<T>, set: (s: Engine<T>) => void) =>
    promise
      .then((data) => set({ status: "ready", data }))
      .catch((err) => set({ status: "error", failure: asFailure(err) }));

  const runAnomaly = useCallback((o: RunOptions) => {
    setAnomaly({ status: "loading" });
    return settle(get<AnomalyResponse>("/api/isolation-forest", anomalyParams(o)), setAnomaly);
  }, []);

  const runTechnical = useCallback((o: RunOptions, t: TechnicalOptions = {}) => {
    lastTechnical.current = t;
    setTechnical({ status: "loading" });
    return settle(
      get<TechnicalResponse>("/api/technical-analysis", {
        ticker: o.ticker, market: o.market, range: o.range,
        sr_window: t.srWindow, sr_levels: t.srLevels,
      }),
      setTechnical
    );
  }, []);

  const runValuation = useCallback((o: RunOptions, v: ValuationOptions = {}) => {
    lastValuation.current = v;
    setValuation({ status: "loading" });
    return settle(
      get<ValuationResponse>("/api/intrinsic-value", valuationParams(o, v)),
      setValuation
    );
  }, []);

  const runNews = useCallback((o: RunOptions) => {
    setNews({ status: "loading" });
    return settle(
      get<NewsResponse>("/api/news", { ticker: o.ticker, market: o.market }),
      setNews
    );
  }, []);

  const run = useCallback(async (opts: RunOptions) => {
    const ticker = opts.ticker.trim().toUpperCase();
    if (!ticker) return;
    const o = { ...opts, ticker };
    lastRun.current = o;
    // A fresh ticker resets per-engine tuning; stale assumptions from the last
    // company would be applied silently to this one.
    lastValuation.current = {};
    lastTechnical.current = {};
    await Promise.all([runAnomaly(o), runTechnical(o), runValuation(o), runNews(o)]);
  }, [runAnomaly, runTechnical, runValuation, runNews]);

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

  const scan = useCallback((params: {
    tickers: string; market: Market; period: string; mode: string; recentDays: number;
  }) => {
    setState({ status: "loading" });
    get<ScreenerResponse>("/api/screener", {
      tickers: params.tickers, market: params.market, period: params.period,
      mode: params.mode, recent_days: params.recentDays,
    })
      .then((data) => setState({ status: "ready", data }))
      .catch((err) => setState({ status: "error", failure: asFailure(err) }));
  }, []);

  return { state, scan };
}
