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
    /**
     * How the EVENTS were chosen, which is a separate question from how each
     * CAR was measured. The detector behind them is fitted on the whole loaded
     * window, so selection is not point-in-time; the market model behind each
     * CAR is. Rendered beside the main caveat, never in place of it.
     */
    selectionCaveat?: string;
  };
  earningsProximity: {
    available: boolean; tagged: number; total: number;
    share?: number; window?: number;
    dates: { date: string; earnings: string; daysApart: number }[];
  };
}

/** Engine 4 — Piotroski / Altman / Beneish. */
export interface QualitySignal { name: string; passed: boolean | null; detail: string }

/**
 * One axis on which this use of a screen does or does not match the sample the
 * screen was fitted on.
 *
 * `verdict` is NOT a colour input and there is deliberately no tone here. Both
 * directions would mislead: "outside" is the normal condition of every use of
 * these models today, and "inside" as a green tick would claim the score is
 * therefore reliable — a claim about accuracy that nothing in this app measures.
 * Colour comes from `explain["domain.<screen>.<key>"].tone`, which is always
 * neutral, decided in Python like every other tone.
 */
export interface DomainDimension {
  key: string;
  name: string;
  /** What the published study's sample actually was, on this axis. */
  sample: string;
  /** What this company is, on the same axis. */
  thisUse: string;
  verdict: "inside" | "outside" | "unknown";
  note: string;
}

/**
 * One point on the prior/posterior curve, served ALREADY COMPUTED and already
 * worded. The control selects a point; it never calculates one, because
 * arithmetic in TypeScript is arithmetic no pytest can reach.
 */
export interface PosteriorPoint {
  prior: number;
  priorText: string;
  /** Present only where this stop is a published estimate worth naming. */
  label: string | null;
  source: string | null;
  event: string | null;
  /** True where the prior counts a broader event than the sensitivity was measured on. */
  extrapolated: boolean;
  isDefault: boolean;
  givenFlag: number;
  givenFlagText: string;
  falseAlarmText: string;
  givenClean: number;
  givenCleanText: string;
}

/**
 * What a Beneish flag is worth, given how rare manipulation is.
 *
 * There is no tone here and there must not be: the M-Score already carries the
 * alarm, and this number qualifies it downward at every published prior. Colour
 * comes from `explain.manipulationPosterior`, which is always neutral.
 */
export interface ManipulationPosterior {
  screen: string;
  flagged: boolean;
  band: string;
  prior: number;
  priorText: string;
  posterior: number;
  posteriorText: string;
  givenFlag: number;
  givenClean: number;
  /** How far the test moved the estimate — the honest framing for both branches. */
  shift: { from: number; fromText: string; to: number; toText: string };
  characteristics: {
    cutoff: number; sensitivity: number; falsePositiveRate: number;
    specificity: number; citation: string; note: string;
  };
  curve: PosteriorPoint[];
  anchors: { prior: number; label: string; source: string; event: string;
             extrapolated: boolean }[];
  robustRange: { lowText: string; highText: string; sentence: string };
  partialScore: boolean;
  partialNote: string | null;
  caveat: string;
}

export interface ScreenDomain {
  label: string;
  citation: string;
  sample: string;
  dimensions: DomainDimension[];
}

/**
 * Provenance for the three accounting screens. Note what is absent: no fit
 * score, no count of matching dimensions, no overall verdict. A tally would be
 * a reliability rating, which is exactly the claim this block refuses to make.
 */
export interface ValidationDomains {
  asOf: string;
  /** The fiscal year the scores were computed on, not today's year. */
  fiscalYear: number | null;
  screens: Record<string, ScreenDomain>;
}
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
  /** What a flag is worth. Null when no M-Score could be computed. */
  manipulationPosterior?: ManipulationPosterior | null;
  /** Where the three numbers came from. Absent when the lens refused to score. */
  domains?: ValidationDomains;
  /** Machine-readable reason the lens declined, when it did. */
  cause?: "financial" | "no-statements";
  explain?: ExplainMap;
}

/* ------------------------------------------------------------------ */
/* Breadth tier — rank a universe, then deepen a shortlist            */
/* ------------------------------------------------------------------ */

export interface UniverseSummary {
  id: string; name: string; market: Market;
  note: string; count: number; asOf: string;
}

export interface RankSignalDefinition {
  key: string;
  /** Prose name, used wherever there is room. */
  label: string;
  /** Compact form for the table header, which scrolls sideways. */
  short: string;
  question: string; detail: string;
  direction: 1 | -1;
  evidence: "strong" | "moderate" | "weak";
  weight: number;
}

export interface RankSignalCell {
  raw: number | null;
  /** Position within THIS scan, 0-100. Direction is already applied. */
  percentile: number | null;
  weight: number;
}

export interface RankRow {
  rank: number;
  ticker: string;
  composite: number | null;
  /** Share of the intended weight that actually contributed. */
  coverage: number;
  signalsAvailable: number;
  signalsTotal: number;
  signals: Record<string, RankSignalCell>;
  latestClose: number;
  bars: number;
  asOf: string;
  explain: ExplainMap;
}

export interface SignalCorrelation {
  available: boolean;
  reason?: string;
  signals?: string[];
  matrix?: Record<string, Record<string, number | null>>;
  pairs?: { a: string; b: string; correlation: number }[];
  /** Participation ratio of the correlation matrix eigenvalues. */
  effectiveSignals?: number | null;
  measuredSignals?: number;
  reading?: string;
}

export interface RankResponse {
  universe: { id: string | null; name: string; market: Market;
              asOf: string | null; symbols: string[] };
  rows: RankRow[];
  signals: RankSignalDefinition[];
  weights: Record<string, number>;
  correlation: SignalCorrelation;
  requested: number;
  fetched: number;
  ranked: number;
  benchmark: string | null;
  /** Named rather than counted — a typo and a delisting look different. */
  missing: string[];
  minBars: number;
  explain: ExplainMap;
  /** Does this ranking predict anything? Measured offline; see backtest.py. */
  validation: RankValidation;
}

export interface DeepenValuation {
  engine: string; price: number; priceLabel: string; verdict: string;
  medianLabel: string; upside: number | null; probUndervalued: number;
  terminalShare: number | null;
  explain?: ExplainMap;
}

export interface DeepenRow {
  ticker: string;
  quality: { ok: true; data: QualityResponse } | { ok: false; error: unknown };
  valuation: { ok: true; data: DeepenValuation } | { ok: false; error: unknown };
}

export interface DeepenResponse {
  rows: DeepenRow[];
  caveat: string;
}

export interface UniversesResponse {
  universes: UniverseSummary[];
  asOf: string;
  maxUniverse: number;
  maxDeepen: number;
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

/**
 * One holding-period distribution.
 *
 * `usable` is false for a horizon the loaded history cannot support, and such a
 * row carries `reason` and NOTHING ELSE — no worst, no median. That is
 * deliberate: these rows used to be dropped, so a reader could not tell whether
 * a stock had never had a bad five-year stretch or whether nobody had looked.
 * Never render a figure from a row whose `usable` is false; there is none.
 */
export interface RollingReturnRow {
  years: number;
  usable?: boolean;
  reason?: string;
  windows: number;
  best?: number; worst?: number; median?: number; mean?: number;
  positiveShare?: number; p25?: number; p75?: number;
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
  /**
   * Hurst with its sampling error. The verdict is sample-size aware: the band
   * that counts as "indistinguishable from a random walk" widens when there is
   * less history, because a fixed 0.45-0.55 band is barely one standard error
   * wide and labelled genuine random walks as trending a third of the time.
   */
  hurstReading: {
    hurst: number | null;
    stderr: number | null;
    observations: number;
    randomWalkLow: number | null;
    randomWalkHigh: number | null;
    verdict: "persistent" | "meanReverting" | "indistinguishable" | "unavailable";
  };
  plainEnglish: PlainEnglish | null;
  explain: ExplainMap;
  regression: {
    slopePerYear: number | null; rSquared: number | null;
    lower: number; mid: number; upper: number; position: number;
  } | null;
  coppock: { date: string; value: number }[];
}
/** A defended price level with how many times the market actually turned there. */
export interface SwingLevel {
  price: number; touches: number;
  distancePct: number; distanceAtr: number;
  side: "support" | "resistance";
}

export interface SwingTarget {
  label: string; price: number; basis: string;
  rMultiple: number; distancePct: number;
}

export interface SwingPlan {
  usable: boolean;
  reason?: string;
  entry?: number; entryNote?: string;
  stop?: number; stopBasis?: "structure" | "volatility";
  stopWidened?: boolean; stopDistancePct?: number; stopDistanceAtr?: number;
  structuralLevel?: number | null; volatilityStop?: number;
  targets?: SwingTarget[];
  riskReward?: number;
  riskBudget?: number; positionShare?: number; positionUncapped?: number;
  atr?: number;
}

export interface PivotSet {
  usable: boolean; style?: string; period?: string;
  periodHigh?: number; periodLow?: number; periodClose?: number;
  pivot?: number; r1?: number; r2?: number; r3?: number;
  s1?: number; s2?: number; s3?: number;
}

/** One shorter-horizon readout. `usable: false` means it was withheld, not empty. */
export interface HorizonBlock {
  usable: boolean;
  horizon: "short" | "mid";
  label?: string;
  window?: string;
  reason?: string;
  price?: number; atr?: number; atrPct?: number | null;
  setup?: {
    name: string | null; direction: "long" | "short" | "none";
    evidence: "strong" | "moderate" | "weak" | null;
    reason: string; anchor: number | null; invalidation: number | null;
    consolidation?: { usable: boolean; high?: number; low?: number;
                      height?: number; heightPct?: number; bars?: number; tight?: boolean };
    trend?: { fastLength: number; slowLength: number;
              fast: number | null; slow: number | null; long: number | null;
              slowRising: boolean | null; alignment: "up" | "down" | "mixed";
              aboveLong: boolean | null; price: number };
  };
  levels?: { usable: boolean; price?: number; atr?: number;
             supports: SwingLevel[]; resistances: SwingLevel[];
             confirmationLag?: number };
  plan?: SwingPlan;
  pivots?: { classic: PivotSet; fibonacci: PivotSet };
  vwap?: { usable: boolean; price?: number; caveat?: string;
           anchors: { label: string; anchoredOn: string; vwap: number;
                      distancePct: number; above: boolean; note: string }[] };
  squeeze?: { usable: boolean; bandwidth?: number; percentile?: number;
              inSqueeze?: boolean; firedDirection?: "up" | "down" | null;
              upperBand?: number | null; lowerBand?: number | null };
  volume?: { usable: boolean; ratio?: number; average?: number;
             latest?: number; confirms?: boolean; anaemic?: boolean };
  gaps?: { usable: boolean; count?: number; unfilledCount?: number;
           gaps: { date: string; direction: string; from: number; to: number;
                   sizeAtr: number; filled: boolean; distancePct: number }[];
           unfilled: { date: string; direction: string; from: number; to: number;
                       sizeAtr: number; filled: boolean; distancePct: number }[] };
  divergence?: { usable: boolean; swingOrder?: number; caveat?: string;
                 bearish: DivergenceLeg | null; bullish: DivergenceLeg | null };
  candlesticks?: { name: string; direction: string; meaning: string;
                   date: string; evidence: string }[];
  undetectable?: { name: string; why: string }[];
  plainEnglish: PlainEnglish | null;
  explain: ExplainMap;
}

export interface DivergenceLeg {
  kind: "bullish" | "bearish";
  from: string; to: string;
  priceFrom: number; priceTo: number;
  rsiFrom: number; rsiTo: number;
}

export interface TechnicalResponse {
  ticker: string; currency: string; range: string; bars: number; hasSma200: boolean;
  /**
   * What this name moves with, among the factors whose betas survived the
   * persistence study. Estimated over its own fixed 52 weeks — the block length
   * the study measured — so it does not change when the chart range does.
   * Never carries a vote: a negative beta is not a bad beta.
   */
  exposure?: {
    usable: boolean;
    reason?: string;
    weeks?: number;
    /** Declaration order, never strength order. */
    factors?: { key: string; label: string; symbol: string; beta: number;
                rSquared: number; tStat: number; weeks: number; note: string;
                marketRemoved: boolean }[];
    /** Tested and declined, with why. An empty section is not "no exposure". */
    refused?: { key: string; label: string; reason: string }[];
    materialAt?: number;
    materialT?: number;
    /** What the stability study can and cannot say — context, never a gate. */
    persistence?: { measured: boolean; measuredOn?: string | null;
                    blockWeeks?: number;
                    rawOneYear?: Record<string, number | null> };
    explain?: ExplainMap;
  };
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
  shortTerm: HorizonBlock;
  midTerm: HorizonBlock;
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
  /** Which Yahoo endpoint the price came from, and the bar it belongs to.
   *  The valuation used to read the quote endpoint while every other lens
   *  read the chart endpoint; they do not always agree. */
  priceSource: string | null; priceAsOf: string | null;
  /** Set only when the accounts and the shares use different currencies:
   *  the statements' own currency, and the spot rate used to reconcile them. */
  reportingCurrency: string | null; fxRate: number | null;
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
  baseCase: {
    impliedPrice: number; impliedPriceLabel: string; terminalShare: number | null;
    /** The growth rate today's price implies, and the one the model was run with.
     *  `impliedGrowth` is null when the price is unreachable in the solver's
     *  bracket, and for the residual-income engine, where a single growth rate
     *  is not the lever that moves the value. */
    impliedGrowth: number | null; assumedGrowth: number;
  };
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

/**
 * What the four lenses add up to, in sentences.
 *
 * Deliberately has NO score field and never will. See `explain.for_synthesis`
 * for the reasoning: a single composite number discards every finding the app
 * works to establish (that four panels rest on two datasets, that a DCF is
 * mostly a perpetuity guess, that several readings are graded weak) and it does
 * it in the one field everybody reads.
 */
export interface SynthesisReading {
  lens: string;
  key: "flow" | "trend" | "value" | "quality";
  family: "price" | "filings";
  familyLabel: string;
  verdict: string;
  sentence: string;
  tone: string;
  vote: number;
}

export interface SynthesisNote { title: string; text: string }

/**
 * One pair of readings, and how much they agree beyond what chance supplies.
 *
 * `kappa` is null where it is genuinely undefined — two lenses that never
 * varied cannot be shown to agree beyond chance, and 0 would read as "no better
 * than chance" rather than "this sample cannot say". `usable` is decided in
 * Python against the minimum sample; never re-derive it here.
 *
 * There is deliberately no confidence field and no weight. This is a caveat
 * with a number on it, and the moment anything downstream multiplied by it the
 * app would have the composite score it refuses to have.
 */
export interface AgreementPair {
  a: string; b: string;
  n: number;
  observed: number;
  chance: number;
  kappa: number | null;
  tauB: number | null;
  low: number | null;
  high: number | null;
  excludesZero: boolean;
  usable: boolean;
}

/** The measured half of the app's central claim. Absent when never measured. */
export interface AgreementMeasurement {
  measuredOn: string;
  scope: string;
  families: AgreementPair;
  pairs: AgreementPair[];
  lenses: {
    available: boolean;
    reason?: string;
    lenses?: string[];
    measuredLenses?: number;
    effectiveLenses?: number;
    completeCases?: number;
    droppedForNoVariation?: string[];
  };
  reading: string;
}

export interface Synthesis {
  headline: string;
  tone: string;
  readings: SynthesisReading[];
  agreement: {
    text: string; tone: string;
    independentSources: number; lensesReading: number;
    /** Present only when the measurement has been run and is usable. */
    measured?: AgreementMeasurement;
  };
  /** Named conflicts. The most useful sentences on the page. */
  tensions: SynthesisNote[];
  /** Limits in force for THIS ticker, switched on by real numbers. */
  blindSpots: SynthesisNote[];
  nextChecks: string[];
  caveat: string;
}

/**
 * One condition that would give a careful buyer pause.
 *
 * `firingRate` is the whole point and is never optional: a condition true of a
 * third of the market is a description of the market, and it is indistinguishable
 * from a finding about this company without that number. `classification` is
 * decided in Python against `baseRateMax` — never re-derived here.
 *
 * There is deliberately NO severity field and no ordering weight. Three of these
 * is not a worse reading than two, and any field that implied otherwise would be
 * a composite arriving by the back door.
 */
export interface PreTradeCheck {
  id: string;
  classification: "flag" | "base";
  /** The panel that owns the underlying number, so it can be gone and checked. */
  where: string;
  family: "price" | "filings";
  firingRate: number;
  firingRateText: string;
  sampleSize: number;
  universeLabel: string;
  rateSentence: string;
  explain: Explanation;
}

/** A condition that was never tested. NOT the same as one that came back clear. */
export interface PreTradeUnchecked {
  id: string; label: string; reason: string; where: string;
}

/**
 * What would give a careful buyer pause.
 *
 * Note what is absent: no count, no score, no severity order, no overall verdict.
 * That is enforced in `api/_lib/pretrade.py` and asserted by
 * `tests/test_pretrade.py` against the payload's key set, because an aggregate
 * field is the direction any later change to this panel would drift in.
 */
export interface PreTrade {
  headline: string;
  framing: string;
  /** Keyed by the section each note describes — never matched by wording. */
  notes: { base?: string; notChecked?: string; uncalibrated?: string };
  measuredOn: string | null;
  caveat: string;
  flags: PreTradeCheck[];
  /** True here AND true of most of the market, so shown apart and uncoloured. */
  baseConditions: PreTradeCheck[];
  notChecked: PreTradeUnchecked[];
  /** Known to the app, withheld because nobody has measured its base rate. */
  uncalibrated: { id: string; label: string }[];
  calibration: {
    measuredOn: string | null;
    universeLabel: string | null;
    universes: string[] | null;
    /** Which population the rates describe — see `_rate_for` in pretrade.py. */
    market: string | null;
    baseRateMax: number;
  } | null;
}

/**
 * Where a candidate sits against a book of holdings.
 *
 * The one place in this app where a measurement informs position size, and it
 * is earned: `stability` carries the offline finding that licenses it — pairwise
 * correlations persist year to year — along with the limit the same measurement
 * found, that they run higher in bad quarters. Never render the numbers without
 * it.
 */
export interface PortfolioPair {
  ticker: string;
  correlation: number;
  band: "high" | "moderate" | "low";
  overlapDays: number;
}

export interface PortfolioRiskRow {
  ticker: string;
  weight: number;
  riskShare: number;
  volatility: number;
  /** Risk share minus money share. Positive means bigger than it looks. */
  excess: number;
}

export interface PortfolioResponse {
  candidate: string;
  market: Market;
  usable: boolean;
  reason?: string;
  missing?: string[];
  holdings?: string[];
  windowDays?: number;
  equalWeighted?: boolean;
  observations?: number;
  pairs?: PortfolioPair[];
  portfolioCorrelation?: number | null;
  independence?: {
    before: number | null; after: number | null;
    holdings: number; withCandidate: number; gain: number | null;
  };
  contributions?: {
    usable: boolean; reason?: string;
    portfolioVolatility?: number; rows?: PortfolioRiskRow[];
  };
  volatility?: Record<string, number>;
  /**
   * What the holdings have in common, once the local market is taken out.
   * Never carries a vote: a beta has no bullish or bearish direction, so this
   * never reaches the confluence rail. See `api/_lib/exposure.py`.
   */
  driver?: {
    usable: boolean;
    reason?: string;
    holdings?: string[];
    weeks?: number;
    varianceShare?: number;
    hasSharedDirection?: boolean;
    loadings?: Record<string, number>;
    marketShare?: number | null;
    indexSymbol?: string;
    /** Declaration order, never strength order. */
    matches?: { key: string; label: string; symbol: string;
                correlation: number; overlapWeeks: number; note: string }[];
    tested?: { key: string; label: string; symbol: string; available: boolean;
               correlation?: number; overlapWeeks?: number }[];
    ambiguous?: boolean;
    nameAt?: number;
    minVarianceShare?: number;
  };
  stability?: {
    measuredOn: string | null;
    headline: string | null;
    yearlyPersistence: { mean: number | null; min: number | null; max: number | null };
    stressRise: { mean: number | null; min: number | null; max: number | null };
    caveats: string[];
  } | null;
  explain?: ExplainMap;
}

export interface ConfluenceResponse {
  ticker: string;
  anomaly: Leg<AnomalyResponse>;
  technical: Leg<TechnicalResponse>;
  valuation: Leg<ValuationResponse>;
  quality: Leg<QualityResponse>;
  news: Leg<NewsResponse>;
  synthesis: Synthesis;
  preTrade: PreTrade;
}

/**
 * Where one ticker sits among its own index, on the seven price signals.
 *
 * A calibration aid, not a ranking. Every `percentile` is direction-adjusted, so
 * 100 is always the favourable end — including for the two signals where a LOW
 * raw value is the good one. Never re-derive a direction from `percentile` at a
 * call site; the sentence already carries it.
 */
export interface PeerReading {
  key: string;
  label: string;
  percentile: number | null;
  rawText: string | null;
  sentence: string;
  tone: string;
  band: string;
  evidence: string;
}

export interface PeersResponse {
  ticker: string;
  universe: {
    id: string; name: string; market: string; asOf: string;
    count: number; scanned: number; note: string;
  };
  /** Every predefined group this name belongs to, so the panel can offer a switch. */
  candidates: { id: string; name: string; market: string; count: number; asOf: string }[];
  rank: number | null;
  composite: number | null;
  coverage: number | null;
  benchmark: string | null;
  explain: {
    headline: string;
    readings: PeerReading[];
    overlap: string | null;
    caveat: string;
  };
}

/**
 * Whether the composite ranking predicts anything, measured offline.
 *
 * `universe` is absent for a custom list — a pasted set of tickers was never
 * tested and must not borrow a predefined universe's result.
 */
export interface RankValidation {
  available: boolean;
  measuredOn?: string;
  years?: number;
  tests?: number;
  rawHits?: number;
  expectedByChance?: number;
  significant?: number;
  headline?: string;
  caveats?: string[];
  universe?: {
    horizonDays: number; periods: number;
    ic: number; icT: number; icQ: number;
    spread: number; spreadQ: number;
    minimumDetectableIc: number;
  }[];
}


/**
 * A whole universe against the factors whose betas survived the persistence
 * study. One beta is uninterpretable alone, so this tier returns the
 * cross-section and lets the reader place a name in it.
 */
export interface ExposureLoading {
  beta: number; rSquared: number; tStat: number; material: boolean;
  weeks: number; marketRemoved: boolean;
}

export interface ExposureRow {
  ticker: string; weeks: number;
  loadings: Record<string, ExposureLoading>;
}

export interface ExposureScanResponse {
  universe: { id: string | null; name: string; market: Market;
              asOf: string | null; count: number };
  usable: boolean;
  reason?: string | null;
  /** Declaration order, never strength order. */
  factors: { key: string; label: string; symbol: string; note: string }[];
  /** Tested and declined, with why — an absent factor is never silently absent. */
  refused: { key: string; label: string; reason: string }[];
  rows: ExposureRow[];
  missing?: string[];
  scanned?: number;
  requested?: number;
  weeks?: number;
  materialAt?: number;
  materialT?: number;
  indexSymbol?: string;
  persistence?: { measured: boolean; measuredOn?: string | null;
                  blockWeeks?: number;
                  rawOneYear?: Record<string, number | null> };
  explain?: ExplainMap;
}
