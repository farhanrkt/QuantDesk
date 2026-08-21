/** Wire shapes returned by api/index.py. Keep in sync with the FastAPI handlers. */

export type Market = "US" | "ID";

/**
 * One metric explained in plain English, built by `api/_lib/explain.py`.
 *
 * `tone` is the ONLY thing the UI may colour from. It already accounts for
 * metrics where a low number is the good one (drawdown, volatility, Ulcer
 * index, Beneish), so no component should ever look at the raw value's sign to
 * pick a colour — that is the bug this whole layer exists to make impossible.
 * `goodDirection` is for the arrow glyph and for reading comprehension, never
 * for the colour.
 */
export interface Explanation {
  label: string;
  /** What is this measuring, in one jargon-free sentence. */
  what: string;
  /** What THIS value means — the number quoted back and interpreted. */
  reading: string;
  /** What would make you act differently, or an admission that nothing would. */
  action: string;
  band: string;
  tone: "good" | "bad" | "warn" | "neutral" | "none";
  goodDirection: "high" | "low" | "none";
  /** How well the published evidence supports acting on it. */
  evidence: "strong" | "moderate" | "weak" | "none" | null;
  valueText: string | null;
}

export type ExplainMap = Record<string, Explanation | undefined>;

/** The long-horizon evidence retold as sentences a person would say aloud. */
export interface PlainEnglish {
  ticker: string;
  paragraphs: string[];
  /** The handful of metric keys Simple mode keeps, in the order to show them. */
  simpleMetrics: string[];
}

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
/** Amihud/Corwin-Schultz/Abdi-Ranaldo/Yang-Zhang, from the same OHLCV frame. */
export interface LiquidityProfile {
  amihud: number | null;
  spread: number | null;
  warningSpread: number | null;
  spreadDetail: {
    primary: number | null; primarySource: string;
    corwinSchultz: number | null; abdiRanaldo: number | null;
    disagreement: number | null; observations: number;
  };
  yangZhangVol: number | null;
  medianDollarVolume: number | null;
  latestMove: number | null;
  moveVsSpread: number | null;
  insideSpreadNoise: boolean;
  window: number;
}

/** A multi-week flow regime, which the point detector cannot see. */
export interface AccumulationEpisode {
  direction: "Accumulation" | "Distribution";
  start: string; detected: string; end: string;
  days: number; peakStatistic: number;
  priceChangePct: number | null; avgRvol: number | null;
  ongoing: boolean;
}
export interface AccumulationResponse {
  episodes: AccumulationEpisode[];
  current: AccumulationEpisode | null;
  config: { slack: number; threshold: number; minDays: number; winsor: number };
}

export interface AnomalyResponse {
  ticker: string;
  liquidity: LiquidityProfile;
  accumulation: AccumulationResponse;
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
  explain?: ExplainMap;
}

export interface ScreenerRow {
  ticker: string; recentAnomalies: number; dominantFlow: string;
  topStrength: number; latestSignal: string; latestTag: string;
  latestClose: number; topRvol: number;
  /** The ticker's own long-run flag rate — the null each hit is tested against. */
  anomalyRate?: number; totalDays?: number;
  pValue?: number; qValue?: number; significant?: boolean;
}
export interface ScreenerResponse {
  scanned: number; universe: string[]; recentDays: number;
  config: { period: string; mode: string };
  rows: ScreenerRow[];
  significance?: {
    available: boolean; tested?: number; discoveries?: number;
    expectedByChance?: number; alpha?: number; reading?: string; reason?: string;
  };
}

/** Cumulative abnormal returns after each detected anomaly. */
export interface CarSummary {
  meanCar: number; medianCar: number; sd: number; n: number;
  tStat: number | null; pValue: number | null; hitRate: number;
}
export interface EventStudyResponse {
  ticker: string; benchmark: string; period: string; anomalies: number;
  study: {
    events: number; usable: boolean; reason?: string;
    horizons: Record<string, CarSummary | null>;
    byDirection: Record<string, Record<string, CarSummary | null>>;
    config?: { estimationWindow: number; gap: number; horizons: number[] };
    caveat?: string;
  };
  earningsProximity: {
    available: boolean; tagged: number; total: number;
    share?: number; window?: number;
    dates: { date: string; earnings: string; daysApart: number }[];
  };
}

/** Engine 4 — Piotroski / Altman / Beneish. */
export interface QualitySignal { name: string; passed: boolean | null; detail: string }
export interface QualityResponse {
  applicable: boolean;
  reason?: string;
  sector: string | null;
  industry: string | null;
  verdict?: "SOUND" | "NEUTRAL" | "CONCERNS";
  tone?: string;
  headline?: string;
  piotroski: {
    score: number; maxScore: number; signalsAvailable: number; signalsTotal: number;
    band: string; reading: string; signals: QualitySignal[];
  } | null;
  altman: {
    score: number | null; band: string; reading: string;
    components: Record<string, number | null>;
  } | null;
  beneish: {
    score: number | null; band: string; reading: string;
    indices: Record<string, number | null>;
    indicesAvailable: number; indicesTotal: number;
  } | null;
  explain?: ExplainMap;
}

export interface NewsItem {
  title: string; source: string; link: string; published: string;
}
export interface NewsResponse { ticker: string; items: NewsItem[] }

export interface TechPoint {
  date: string; open: number; high: number; low: number; close: number; volume: number;
  sma20: number | null; sma50: number | null; sma100: number | null; sma200: number | null;
  bbUpper: number | null; bbMid: number | null; bbLower: number | null;
  kcUpper: number | null; kcLower: number | null;
  dcUpper: number | null; dcLower: number | null;
  ichiSpanA: number | null; ichiSpanB: number | null;
  rsi: number | null; macd: number | null; macdSignal: number | null;
  macdHist: number | null;
  adx: number | null; plusDi: number | null; minusDi: number | null;
  drawdown: number | null; atrPct: number | null;
  cmf: number | null; obv: number | null;
  signal: "Buy" | "Sell" | null;
}

/** One line of the long-horizon checklist. */
export interface LongTermCheck {
  label: string; passed: boolean | null; detail: string;
  tone: string; horizon: string;
}

export interface RollingReturnRow {
  years: number; windows: number; best: number; worst: number;
  median: number; mean: number; positiveShare: number; p25: number; p75: number;
}

export interface LongTermBlock {
  view: {
    verdict: string; tone: string; headline: string;
    passed: number; scored: number; checks: LongTermCheck[]; caveat: string;
  };
  drawdown: {
    usable: boolean;
    maxDrawdown?: number; maxDrawdownPeak?: string; maxDrawdownTrough?: string;
    maxDrawdownRecovered?: string | null; maxDrawdownRecoveryDays?: number | null;
    currentDrawdown?: number; currentUnderWaterDays?: number;
    timeUnderWaterDays?: number; ulcerIndex?: number;
    series?: { date: string; drawdown: number }[];
  };
  risk: {
    usable: boolean;
    cagr?: number | null; volatility?: number | null;
    downsideDeviation?: number | null; sharpe?: number | null;
    sortino?: number | null; calmar?: number | null;
    var95?: number | null; cvar95?: number | null;
    skew?: number | null; kurtosis?: number | null;
    positiveDays?: number | null; bestDay?: number | null; worstDay?: number | null;
    observations?: number;
  };
  rollingReturns: RollingReturnRow[];
  calendarReturns: { year: number; return: number | null }[];
  seasonality: {
    usable: boolean; yearsCovered?: number; caveat?: string;
    months: { month: string; mean: number | null; median?: number;
              count: number; positiveShare: number | null }[];
  };
  momentum: Record<string, number | string | null>;
  position: {
    usable: boolean; price?: number; high52w?: number; low52w?: number;
    rangePosition?: number | null; fromHigh52w?: number | null;
    fromLow52w?: number | null; allTimeHigh?: number; fromAllTimeHigh?: number | null;
  };
  faber: {
    usable: boolean; signal?: string; monthlyClose?: number; movingAverage?: number;
    distance?: number; monthsInStance?: number; sharOfTimeInvested?: number;
  };
  relativeStrength: {
    usable: boolean; benchmark: string | null;
    periods?: Record<string, { stock: number; benchmark: number; excess: number } | null>;
    ratioTrend?: number | null; outperforming?: boolean; correlation?: number | null;
    series?: { date: string; ratio: number }[];
  };
  hurst: number | null;
  plainEnglish: PlainEnglish | null;
  explain: ExplainMap;
  regression: {
    slopePerYear: number | null; rSquared: number | null;
    lower: number; mid: number; upper: number; position: number;
  } | null;
  coppock: { date: string; value: number }[];
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
  hasLongTerm: boolean;
  longTerm: LongTermBlock;
  indicators: Record<string, number | null>;
  indicatorsExplain: ExplainMap;
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
  engine: "DCF" | "DDM" | "RI"; autoEngine: "DCF" | "DDM"; routeReason: string;
  rateName: string; price: number; priceLabel: string;
  discountRate: number; riskFree: number; riskFreeSource: string;
  erp: number; beta: number;
  /** Vasicek-shrunk beta with the error bars that justify the shrinkage. */
  betaEstimate: {
    raw: number | null; adjusted: number | null; stderr: number | null;
    rSquared: number | null; observations: number; method: string;
    indexSymbol: string; priorWeight: number | null; notes: string[];
    /** The beta that actually reached the cost of equity, after the sanity clip. */
    used: number; clipped: boolean;
  };
  assumptions: { growth: number; terminalGrowth: number; terminalRequested: number;
                 sdGrowth: number; sdRate: number; sdTerminal: number;
                 iterations: number; seed: number; basis: string;
                 basisOptions: string[]; rateOverridden: boolean;
                 manualApplied: Record<string, boolean>;
                 manualDefaults: ManualInputs;
                 sdGrowthCalibration: {
                   sd: number; sampleSd: number | null; predictiveSd: number | null;
                   horizon: number; observations: number; skipped: number;
                   priorSd: number; priorWeight: number; source: string;
                 } | null };
  baseCase: { impliedPrice: number; impliedPriceLabel: string; terminalShare: number | null };
  monteCarlo: {
    p05: number; p25: number; p50: number; p75: number; p95: number;
    p05Label: string; p25Label: string; p50Label: string; p75Label: string; p95Label: string;
    probUndervalued: number; upside: number | null;
    histogram: { value: number; count: number }[];
  };
  verdict: "UNDERVALUED" | "OVERVALUED" | "FAIRLY VALUED";
  schedule: { year: string; stream: string; streamRaw: number;
              discountFactor: string; presentValue: string; presentValueRaw: number;
              /** Residual income only: the book value the year's excess return is earned on. */
              openingBook?: string }[];
  streamLabel: string;
  bridge: { component: string; amount: string }[];
  diagnostics: { metric: string; value: string }[];
  history: Record<string, string>[];
  notices: { tone: string; text: string }[];
  explain?: ExplainMap;
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
  /**
   * Which engine produced the failure, stated by the server.
   *
   * The rescue form used to infer this from which keys `suggested` carried,
   * which read a residual-income failure as a DDM one and would have valued a
   * book value per share as a dividend.
   */
  engine?: "DCF" | "DDM" | "RI";
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
  quality: Leg<QualityResponse>;
  news: Leg<NewsResponse>;
}
