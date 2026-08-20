/** Wire shapes returned by api/index.py. Keep in sync with the FastAPI handlers. */

export type Market = "US" | "ID";

export interface AnomalyPoint {
  date: string; close: number; volume: number; obv: number; mfi: number;
  rvol: number; anomalyScore: number | null; isAnomaly: boolean;
  flow: "Accumulation" | "Distribution" | "Neutral" | null;
  strength: number | null;
}
export interface AnomalyEvent {
  date: string; close: number; flow: string; tag: string; strength: number;
  rvol: number; priceChangePct: number; mfi: number; anomalyScore: number | null;
}
export interface AnomalyResponse {
  ticker: string;
  config: { period: string; mode: string; contamination: number; madK: number;
            scoreThreshold: number; rollingWindow: number; mfiWindow: number };
  stats: {
    totalDays: number; anomalyCount: number; anomalyRate: number;
    /** Bias across the WHOLE look-back — a two-year verdict on a 2y period. */
    netFlowBias: string;
    /** Bias over `recentDays` only. This is the current-state reading. */
    recentFlowBias: string;
    maxStrength: number; recentCount: number; recentDays: number;
    latestClose: number; latestMfi: number;
  };
  series: AnomalyPoint[];
  anomalies: AnomalyEvent[];
}

export interface ScreenerRow {
  ticker: string; recentAnomalies: number; dominantFlow: string;
  topStrength: number; latestSignal: string; latestTag: string;
  latestClose: number; topRvol: number;
}
export interface ScreenerResponse {
  scanned: number; universe: string[]; recentDays: number;
  config: { period: string; mode: string };
  rows: ScreenerRow[];
}

export interface NewsItem {
  title: string; source: string; link: string; published: string;
}
export interface NewsResponse { ticker: string; items: NewsItem[] }

export interface TechPoint {
  date: string; open: number; high: number; low: number; close: number; volume: number;
  sma50: number | null; sma200: number | null;
  bbUpper: number | null; bbMid: number | null; bbLower: number | null;
  rsi: number | null; macd: number | null; macdSignal: number | null;
  macdHist: number | null; signal: "Buy" | "Sell" | null;
}
export interface TechnicalResponse {
  ticker: string; currency: string; range: string; bars: number; hasSma200: boolean;
  latest: { date: string; close: number; change: number; changePct: number;
            high: number; low: number; volume: number };
  summary: {
    headline: string;
    chips: { label: string; value: string; tone: string }[];
    trend: string; trend_tone: string;
    resistance: number | null; support: number | null;
  };
  levels: number[];
  series: TechPoint[];
  signals: { date: string; type: "Buy" | "Sell"; description: string;
             price: number; changeSince: number }[];
}

/** Figures the user can supply when Yahoo's filings have a gap. */
export interface ManualInputs {
  base?: number | null;
  netDebt?: number | null;
  shares?: number | null;
  price?: number | null;
  payout?: number | null;
}

export interface ValuationResponse {
  ticker: string; name: string; sector: string | null; industry: string | null;
  market: { code: string; name: string; symbol: string };
  engine: "DCF" | "DDM"; autoEngine: "DCF" | "DDM"; routeReason: string;
  rateName: string; price: number; priceLabel: string;
  discountRate: number; riskFree: number; riskFreeSource: string;
  erp: number; beta: number;
  assumptions: { growth: number; terminalGrowth: number; terminalRequested: number;
                 sdGrowth: number; sdRate: number; sdTerminal: number;
                 iterations: number; seed: number; basis: string;
                 basisOptions: string[]; rateOverridden: boolean;
                 manualApplied: Record<string, boolean>;
                 manualDefaults: ManualInputs };
  baseCase: { impliedPrice: number; impliedPriceLabel: string; terminalShare: number | null };
  monteCarlo: {
    p05: number; p25: number; p50: number; p75: number; p95: number;
    p05Label: string; p25Label: string; p50Label: string; p75Label: string; p95Label: string;
    probUndervalued: number; upside: number | null;
    histogram: { value: number; count: number }[];
  };
  verdict: "UNDERVALUED" | "OVERVALUED" | "FAIRLY VALUED";
  schedule: { year: string; stream: string; streamRaw: number;
              discountFactor: string; presentValue: string; presentValueRaw: number }[];
  streamLabel: string;
  bridge: { component: string; amount: string }[];
  diagnostics: { metric: string; value: string }[];
  history: Record<string, string>[];
  notices: { tone: string; text: string }[];
}

/**
 * A 422 from the valuation engine distinguishes "Yahoo has a gap you can fill
 * in" from "this business cannot be valued this way". Only the former should
 * put a manual-input form in front of the user.
 */
export interface EngineFailure {
  message: string;
  manualRequired?: boolean;
  missing?: string[];
  suggested?: ManualInputs;
}

export type Engine<T> =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "error"; failure: EngineFailure }
  | { status: "ready"; data: T };

/**
 * One leg of a /api/confluence response. Each engine reports its own outcome,
 * so a ticker with no dividend history still returns its anomaly and technical
 * panels. `error` is a plain string for most failures and the structured
 * EngineFailure for a valuation data gap the user can close.
 */
export type Leg<T> =
  | { ok: true; data: T }
  | { ok: false; error: string | EngineFailure };

export interface ConfluenceResponse {
  ticker: string;
  anomaly: Leg<AnomalyResponse>;
  technical: Leg<TechnicalResponse>;
  valuation: Leg<ValuationResponse>;
  news: Leg<NewsResponse>;
}
