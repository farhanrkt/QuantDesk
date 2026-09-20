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


/* --------------------------------------------------------------------------- *
 * The private scanner's verdict
 *
 * ONE SCORE AND ONE ACTION PER NAME — the composite the published
 * single-company view refuses. It is a separate surface answering a separate
 * question, and `PRODUCT.md` constraint 1 records why the two coexist. Nothing
 * here is read by the confluence rail, the synthesis or the pre-trade panel.
 *
 * `provenance` is not optional and must not be rendered away. It carries the
 * measured finding that this app's price ranking shows no detectable
 * relationship to subsequent returns, which is what calibrates every number
 * beside it.
 * --------------------------------------------------------------------------- */

export type VerdictAction =
  | "STRONG_BUY" | "BUY" | "HOLD" | "REDUCE" | "AVOID" | "NO_ACTION";

export interface VerdictComponent {
  key: string;
  label: string;
  /** "price" or "filings" — which body of data this reads. */
  family: string;
  evidence: string;
  detail: string;
  baseWeight: number;
  /** Zero when the component did not read. Never imputed. */
  effectiveWeight: number;
  score: number | null;
  available: boolean;
  /** True only for a DESIGNED refusal, never for a coverage gap. */
  refused: boolean;
  reason: string | null;
  reading: string | null;
}

export interface VerdictFamily {
  family: string;
  label: string;
  score: number;
  /** +1, -1 or 0. Zero is the neutral band, not a missing reading. */
  side: number;
  members: string[];
  weight: number;
  /** Share of this family's intended evidence that actually read. */
  coverage: number;
  /** How much of a whole vote it casts. Its own coverage, floored. */
  vote: number;
}

/** The heavy-session reading — the readable shadow of bandarmology. */
export interface VerdictTape {
  available: boolean;
  reason?: string;
  direction?: "accumulation" | "distribution" | "unreadable";
  score?: number;
  /** Mean close-location gap between heavy and ordinary sessions. */
  lift?: number;
  /** The market's own median lift — the null this is tested against. */
  liftBaseline?: number;
  excessLift?: number;
  tStat?: number | null;
  pValue?: number | null;
  significant?: boolean;
  alpha?: number;
  /** False when this market has no measured baseline. No direction is reported. */
  calibrated?: boolean;
  market?: string | null;
  measuredOn?: string | null;
  heavySessions?: number;
  ordinarySessions?: number;
  wick?: number | null;
  spanRatio?: number | null;
  concentration?: {
    available: boolean;
    topFiveShare: number | null;
    effectiveDays: number | null;
    sessions: number;
    band?: string | null;
    caution?: number | null;
    severe?: number | null;
    calibrated?: boolean;
  };
  reading?: string;
  /** What a broker summary would settle and this cannot. Always rendered. */
  missing?: string;
}

/** The share register — ownership concentration and share count. */
export interface VerdictRegister {
  available: boolean;
  reason?: string;
  float?: {
    available: boolean;
    reason?: string;
    freeFloat?: number;
    insidersHeld?: number;
    band?: string;
    score?: number;
    reading?: string;
    institutionsHeld?: number | null;
    institutionsCount?: number | null;
  };
  /** Scheduled reporting date. Context only — it scores nothing. */
  earnings?: {
    available: boolean;
    reason?: string;
    date?: string;
    calendarDays?: number;
    soon?: boolean;
    reading?: string;
  };
  issuance?: {
    available: boolean;
    reason?: string;
    annualised?: number | null;
    total?: number | null;
    years?: number;
    observations?: number;
    largestStep?: number | null;
    largestStepAt?: string | null;
    band?: string;
    score?: number;
    reading?: string;
  };
  floatShares?: number | null;
  sharesOutstanding?: number | null;
  floatTurnover?: number | null;
  daysToTradeFloat?: number | null;
  reading?: string;
  /** Reported and deliberately never scored. */
  institutions?: { percentHeld: number | null; count: number | null; note: string };
}

/** A chart formation found by the Lo-Mamaysky-Wang method, with its measurement. */
export interface VerdictPatternDetection {
  pattern: string;
  label: string;
  /** The direction a chart book attaches to the shape. Measured, it carries no
   *  information — a formation and its mirror image predicted the same thing —
   *  so it is carried for display and never scored. */
  bias: string;
  note: string;
  completedAt: string;
  detectedAt: string;
  priceAtDetection: number;
  /** Share of names showing this in a quarter, on the measured population. */
  firingRate?: number | null;
  observations?: number | null;
  /** Null unless this formation's forward return survived correction. */
  forward?: { horizonDays: number; meanExcess: number; qValue: number;
              months?: number } | null;
  significant: boolean;
  verdict?: string | null;
}

export interface VerdictPatterns {
  available: boolean;
  reason?: string;
  bandwidth?: number;
  window?: number;
  sessions?: number;
  detections?: VerdictPatternDetection[];
  /** False where this market has never been measured. Nothing scores then. */
  calibrated?: boolean;
  measuredOn?: string | null;
  /** True only where at least one detection survived correction. */
  usable?: boolean;
  score?: number | null;
  survivors?: string[];
  lookback?: number;
  reading?: string;
  /** Named and declined, with the reason. An absent pattern is never silent. */
  refused?: { name: string; reason: string }[];
}

/**
 * Where the year's trade happened — the full histogram, beside the bands the
 * chart draws from it.
 *
 * DESCRIPTION, NEVER SUPPORT, unless `usable` says the measurement licensed it.
 * On IDX it did not: shelves held no better than ordinary bands at the same
 * distance once corrected across distance buckets.
 */
export interface VerdictVolumeProfile {
  available: boolean;
  reason?: string;
  sessions?: number;
  price?: number;
  binWidth?: number;
  binWidthAtr?: number;
  bins?: number;
  profile?: { low: number; high: number; mid: number; share: number }[];
  pointOfControl?: { low: number; high: number; mid: number; share: number };
  valueArea?: { low: number; high: number; share: number };
  insideValueArea?: boolean;
  shelves?: { low: number; high: number; mid: number; share: number; bins: number;
              peakMultiple: number; side: string; distanceAtr: number;
              distancePct: number }[];
  market?: string | null;
  /** False where this market has never been measured. Nothing reads a shelf then. */
  calibrated?: boolean;
  measuredOn?: string | null;
  /** True only where a shelf was shown to hold better than an ordinary band. */
  usable?: boolean;
  calibrationReading?: string | null;
  reading?: string;
}

/** Where the price sits against defended levels — the entry, not the asset. */
export interface VerdictStructure {
  available: boolean;
  reason?: string;
  horizon?: string;
  price?: number;
  atr?: number | null;
  support?: number | null;
  resistance?: number | null;
  riskToSupport?: number | null;
  rewardToResistance?: number | null;
  /** Null when `ratioWithheld` — a ratio whose denominator is inside the
   *  daily noise is not a smaller number, it is not a number. */
  rewardRisk?: number | null;
  /** The arithmetic that was refused, for anyone who wants to see it. Never render
   *  this as the ratio; that is the mistake the withholding exists to prevent. */
  rewardRiskRaw?: number | null;
  ratioWithheld?: boolean;
  unboundedUpside?: boolean;
  noSupport?: boolean;
  atSupport?: boolean;
  atResistance?: boolean;
  band?: "fine" | "poor" | "bad" | "unbounded" | "noSupport" | "riskTooWide"
       | "riskInsideNoise" | "unmeasured";
  reading?: string;
}

/** Where the index itself is. Context: it scores nothing and gates nothing. */
export interface MarketRegime {
  available: boolean;
  reason?: string;
  symbol?: string | null;
  state?: string;
  tone?: string;
  aboveSlow?: boolean;
  slowRising?: boolean | null;
  distanceToSlow?: number | null;
  drawdownFromYearHigh?: number | null;
  scores?: boolean;
  reading?: string;
}

/**
 * The walk-forward on the BLEND, from `verdict_backtest.json`.
 *
 * Distinct from `provenance`, which measures the seven-signal price composite —
 * one component of nine. This measures the blend, on the four components that
 * can be reconstructed without reading the future, and carries its own coverage
 * so that partial scope is never mistaken for the whole score.
 */
export interface BlendBacktest {
  available: boolean;
  reason?: string;
  measuredOn?: string | null;
  scope?: string;
  headline?: string;
  components?: string[];
  /** Share of the score's intended evidence this covers. Around 0.4. */
  coverage?: number | null;
  /** Why each excluded component could not be reconstructed. */
  excluded?: Record<string, string>;
  observations?: number;
  dates?: number;
  survived?: number;
  /** Survivors whose IC and quintile spread point opposite ways. */
  contradicted?: number;
  /**
   * Median round trip across the names whose spread RESOLVED. The estimator
   * clears its noise floor on the widest spreads and almost nowhere else, so
   * this is an upper bound on a typical cost, never a measurement of one —
   * `roundTripResolved` over `roundTripAttempted` says how selected it is.
   */
  medianRoundTrip?: number | null;
  roundTripResolved?: number;
  roundTripAttempted?: number;
  roundTripResolvedShare?: number | null;
  roundTripIsUpperBound?: boolean;
  /** Surviving spreads still positive at that upper bound. */
  survivesUpperBound?: number;
  tests?: {
    horizonDays: number;
    icMean: number; icT: number; icQ: number; icSurvived: boolean;
    spreadMean: number; spreadQ: number; spreadSurvived: boolean;
    signsAgree: boolean;
    /** The round trip at which this spread reaches zero — the number to compare
     *  against your own dealing costs. */
    breakevenRoundTrip?: number | null;
    rebalancesPerHorizon?: number;
    costUpperBound?: number; spreadNetUpperBound?: number;
    survivesUpperBound?: boolean;
    dates: number; observations: number;
  }[];
}

/** What one buy and one sell cost, from the estimated spread. */
export interface RoundTripCost {
  available: boolean;
  reason?: string;
  /** False when the estimate sits at the estimator's own noise floor. */
  resolved?: boolean;
  spread?: number;
  roundTrip?: number;
  reading?: string;
}

/** One market's measured tape baselines, from `tape_calibration.json`. */
export interface TapeCalibration {
  names: number;
  population: string;
  measuredOn: string;
  liftMedian: number;
  liftSd: number;
  wickSd: number | null;
  /** Share of this market where the test fires. Compare against `alpha`. */
  significantShare: number | null;
  significantCount: number;
  tested: number;
  concentration: { caution: number | null; severe: number | null; median: number | null };
}

export interface VerdictGate {
  id: string;
  /** The ceiling this gate imposes. Never a promotion. */
  action: VerdictAction;
  label: string;
  detail: string;
}

export interface VerdictPenalty {
  id: string;
  label: string;
  band: string;
  where?: string;
  firingRate: number;
  points: number;
  reading?: string | null;
  why: string;
}

/**
 * One session, with every overlay already positioned.
 *
 * `heavy` is the tape test's OWN classification, not a redefinition of it —
 * this name's top fifth of relative volume inside its own year. A chart that
 * recomputed it would circle sessions the significance test never counted.
 */
export interface ChartBar {
  date: string;
  open: number | null; high: number | null; low: number | null;
  close: number | null; volume: number | null;
  sma20: number | null; sma50: number | null; sma200: number | null;
  bbUpper: number | null; bbLower: number | null;
  relativeVolume: number | null;
  heavy: boolean;
  /** -1 closed at the low, +1 at the high. Null on a zero-range session. */
  closeLocation: number | null;
}

/** One end of a construction line, in both chart coordinates. */
export interface ChartAnchor { index: number; date: string | null; price: number }

/**
 * A detected formation, positioned.
 *
 * `path` is refitted on the window available when the shape completed — never
 * smoothed over the whole series, which would trace a curve built partly out of
 * prices that came after it. `points` sit at the CLOSES the classifier compared;
 * `smoothed` is carried separately and is not where the marker goes.
 */
export interface ChartPattern {
  pattern: string;
  label: string;
  completedAt: string;
  detectedAt: string;
  fromDate: string | null;
  toDate: string | null;
  path: { date: string | null; price: number }[];
  points: { index: number; date: string | null; price: number;
            smoothed: number; kind: "peak" | "trough" }[];
  /** Necklines and boundaries only. Never a projected target — see the caption. */
  guides: { role: "neckline" | "upper" | "lower"; label: string;
            from: ChartAnchor; to: ChartAnchor }[];
  /** What the chart books claim. Carried for display, never scored. */
  textbookBias: string | null;
  /** Whether this formation's forward return survived a false-discovery correction. */
  significant: boolean;
  /** What it actually did on this market. Disagrees with `textbookBias`, by design. */
  measuredExcess: number | null;
  measuredHorizon: number | null;
  /** Every detection the study saw. */
  measuredObservations: number | null;
  /** How many calendar months those fell into — the effective sample size. */
  measuredMonths: number | null;
  firingRate: number | null;
}

/** A defended level. `nearest` marks the two the reward-risk ratio used. */
export interface ChartLevel {
  price: number;
  side: "support" | "resistance";
  touches: number;
  distancePct: number | null;
  nearest: boolean;
}

/** The trade as a shape: where it is wrong, where it is entered, what is overhead. */
export interface ChartTrade {
  entry: number;
  stop: number | null;
  target: number | null;
  riskPct: number | null;
  rewardPct: number | null;
  rewardRisk: number | null;
  /** True where the ratio was withheld because the stop sits inside the noise. */
  ratioWithheld?: boolean;
  band: string | null;
  unboundedUpside: boolean;
  noSupport: boolean;
  atr: number | null;
  /** How close counts as "at" a level, in price. Half an average daily range. */
  levelTolerance: number | null;
  horizon: string | null;
}

/**
 * Where the year's trade actually happened, as bands on the price axis.
 *
 * DESCRIPTION, NOT SUPPORT. `scripts/calibrate_volume_profile.py` tested whether
 * price arriving at a high-volume band behaves differently from price arriving
 * at an ordinary band the same distance away, and `structure.py` reads the
 * answer. Never treat a shelf as a stop unless that artifact says so.
 */
export interface ChartVolumeProfile {
  pointOfControl: { low: number | null; high: number | null; share: number | null };
  valueArea: { low: number | null; high: number | null; share: number | null };
  insideValueArea: boolean;
  shelves: { low: number | null; high: number | null; share: number | null;
             side: string; distanceAtr: number | null }[];
  binWidth: number | null;
  sessions?: number;
  reading?: string;
}

/**
 * Every reading the scanner took, positioned for drawing.
 *
 * NOTHING HERE IS NEW ANALYSIS. Each layer was decided by the module that owns
 * it; this payload only says where to put it. `legend` ships with the data
 * rather than living in the component, so a client cannot draw a layer without
 * having been handed what that layer is not.
 */
export interface VerdictChart {
  available: boolean;
  reason?: string;
  ticker?: string | null;
  currency?: string | null;
  sessions?: number;
  from?: string;
  to?: string;
  bars?: ChartBar[];
  levels?: ChartLevel[];
  trade?: ChartTrade | null;
  patterns?: ChartPattern[];
  /** Null where the profile could not be built, never an empty shape. */
  volumeProfile?: ChartVolumeProfile | null;
  crossovers?: { date: string; type: string; price: number | null;
                 description: string }[];
  extremes?: {
    window: number;
    high: { date: string; price: number | null; inWindow: boolean };
    low: { date: string; price: number | null; inWindow: boolean };
  };
  tape?: { available: boolean; reason?: string | null; rvolCutoff?: number | null;
           heavyQuantile?: number | null; drawn?: number;
           /** The two means the Welch test compared, so the test can be drawn. */
           heavyMeanLocation?: number | null; ordinaryMeanLocation?: number | null;
           significant?: boolean };
  legend?: { key: string; label: string; note: string }[];
  caption?: string;
}

/** One row of a completed market scan, trimmed to what a table needs. */
export interface ScanRow {
  ticker: string;
  name: string | null;
  score: number | null;
  action: VerdictAction;
  actionLabel: string;
  tone: string;
  conviction: string;
  coverage: number;
  crossChecked: boolean;
  rank: number | null;
  sectorRank: number | null;
  sector: string | null;
  /** The narrower label. A rank inside "Thermal Coal" says what one inside
   *  "Energy" does not. */
  industry: string | null;
  /** The provider's own description of the business, trimmed. Never a judgement
   *  about it — see `api/_lib/field.py`. */
  summary: string | null;
  /** `described` | `none published` | `not fetched`. The last two are NOT the
   *  same: one is a fact about the data, the other a gap a refetch fills. */
  summaryState: string | null;
  /** Where it stands among the scanned names sharing its industry label. This
   *  is NOT market share; `ScanResponse.fields.basis` carries the caveat and
   *  must be rendered wherever a rank is. */
  field: {
    rank: number | null; peers: number | null; share: number | null;
    margin: number | null; leads: boolean; leader: string | null;
    /** The only scanned name carrying this industry label. Its own state, not a
     *  weaker `leads` — a specialist with no listed competition. */
    soleListing: boolean; reading: string | null;
  } | null;
  /**
   * What the filings say the business has done. Description, never a score.
   *
   * `everyYearProfitable` IS TRUE OF 67% OF THIS EXCHANGE. Render it with the
   * base rate or not at all; on its own it is not a distinction.
   */
  record: {
    years: number | null; yearsProfitable: number | null;
    everyYearProfitable: boolean; operatingCashFlowPositive: boolean;
    revenueCagr: number | null; netMargin: number | null;
    growing: boolean; reading: string | null;
  } | null;
  latestClose: number | null;
  turnover: number | null;
  held: boolean;
  gates: { id: string; label: string }[];
  entry: { band: string | null; rewardRisk: number | null; ratioWithheld: boolean };
  /** Cheap, solid and uncovered — the screen the blend cannot reach. */
  neglected: boolean;
}

/**
 * A scan that already ran, read off disk.
 *
 * NEVER RUN FROM THE BROWSER. A whole-exchange sweep is about an hour and the
 * serverless function has sixty seconds. This reads the report the script
 * wrote, so `available` is false on the deployed app — `reports/` is local and
 * gitignored — and the panel says so rather than erroring.
 */
export interface ScanResponse {
  available: boolean;
  market: string;
  reason?: string;
  file?: string;
  generatedAt?: string;
  /**
   * The funnel's tallies, guaranteed scalar by the route.
   *
   * The report's own version nests `rejectedByReason` inside this block. A
   * client that believed this type and rendered every value handed React an
   * object, which throws and blanks the page behind an error boundary — so the
   * route now splits it out rather than the client guarding against it.
   */
  counts?: Record<string, number>;
  /** Why names never reached a score, by reason. */
  rejectedByReason?: Record<string, number>;
  settings?: Record<string, unknown>;
  universe?: { label?: string; asOf?: string; count?: number } | null;
  /** The measured null result. Never render the ordering without it. */
  provenance?: VerdictResponse["provenance"];
  blendBacktest?: BlendBacktest | null;
  regime?: MarketRegime | null;
  concentration?: { reading?: string; bets?: number; names?: number } | null;
  signalOverlap?: { reading?: string } | null;
  neglected?: {
    selected: number;
    /** How many of the selected names are the largest in their own field. A
     *  count, never a filter — leading a field is not a selection criterion. */
    leadTheirField?: number;
    tradeable: {
      ticker: string; name: string | null; score: number | null; action: string;
      value: number | null; quality: number | null;
      institutionsHeld: number | null; analysts: number | null;
      industry?: string | null; summary?: string | null;
      leadsField?: boolean; fieldRank?: number | null; fieldPeers?: number | null;
      soleListing?: boolean; profitableEveryYear?: boolean; growing?: boolean;
      revenueCagr?: number | null;
      gates: string[]; reading: string;
    }[];
    gated: { ticker: string; name: string | null; score: number | null }[];
    note: string;
  } | null;
  /**
   * The largest — or only — scanned name in its field, profitable every year
   * with cash behind it, growing in the market's top quartile, and uncovered.
   *
   * `baseRates` IS NOT DECORATION. The intersection reads as three demanding
   * tests and one of them (uncovered) admits most of a small exchange. Render
   * the shares with the list.
   */
  specialists?: {
    selected: number;
    baseRates: { scanned: number; specialist: number; compounding: number;
                 unattended: number };
    tradeable: {
      ticker: string; name: string | null; score: number | null; action: string;
      industry: string | null; summary: string | null;
      soleListing: boolean; leadsField: boolean; fieldPeers: number | null;
      revenueCagr: number | null; netMargin: number | null;
      yearsProfitable: number | null; yearsAvailable: number | null;
      analysts: number | null; institutionsHeld: number | null;
      gates: string[]; recordReading: string | null; fieldReading: string | null;
    }[];
    gated: { ticker: string; name: string | null; industry: string | null }[];
    note: string;
  } | null;
  /**
   * Standings among the scanned names sharing an industry label.
   *
   * `basis` IS NOT OPTIONAL COPY. A rank of 1 rendered without it reads as
   * market share, which nothing in this app measures: private companies,
   * companies listed elsewhere and names whose filings did not arrive are all
   * missing from the denominator. `unplaced` says how many of the last kind
   * there were.
   */
  fields?: {
    measured: number; unplaced: number; count: number;
    basis: string;
    thresholds?: { minPeers: number; leadMargin: number };
    leaders: { industry: string; ticker: string | null;
               peers: number | null; margin: number | null }[];
    /** Fields holding exactly one scanned name. A large count is a thin scan,
     *  not a market of specialists — read it against `unplaced`. */
    soleListings?: number;
  } | null;
  rows?: ScanRow[];
}

export interface VerdictResponse {
  ticker: string;
  name: string;
  market: string;
  action: VerdictAction;
  actionLabel: string;
  /** `explain.tone`. The only permitted input to colour. */
  tone: string;
  score: number | null;
  rawScore: number | null;
  shrunkScore: number | null;
  conviction: "high" | "medium" | "low" | "none";
  /** Whether BOTH bodies of data returned a reading at all. */
  crossChecked: boolean;
  familiesRead: number;
  coverage: number;
  componentsRead: number;
  componentsTotal: number;
  components: VerdictComponent[];
  families: {
    price: VerdictFamily | null;
    filings: VerdictFamily | null;
    /** The third body of data: who holds it and how many shares there are. */
    register: VerdictFamily | null;
  };
  tape: VerdictTape | null;
  register: VerdictRegister | null;
  patterns: VerdictPatterns | null;
  /** Where the trade is wrong. Deliberately not a scoring component. */
  structure: VerdictStructure | null;
  /** The same readings, positioned for drawing. Never a separate analysis. */
  chart: VerdictChart | null;
  /** Where the trade happened. Scores nothing, gates nothing — see `usable`. */
  volumeProfile: VerdictVolumeProfile | null;
  regime: MarketRegime | null;
  costs: RoundTripCost | null;
  /** The measurement that is about this score, not just its price component. */
  blendBacktest: BlendBacktest | null;
  /** Null where this market has never been calibrated. */
  tapeCalibration: TapeCalibration | null;
  agreement: { state: string; shrink: number; conviction: string; text: string };
  shrink: { agreement: number; coverage: number; combined: number; text: string };
  penalties: VerdictPenalty[];
  penaltyTotal: number;
  penaltyCapped: boolean;
  gates: VerdictGate[];
  gatedBy: string[];
  latestClose: number | null;
  turnover: number | null;
  sizing: {
    applicable: boolean;
    reason?: string;
    annualVolatility?: number;
    riskBudget?: number;
    uncappedWeight?: number;
    weight?: number;
    capped?: boolean;
    basis?: string;
  };
  reasons: string[];
  caveat: string;
  rank: number | null;
  universe: {
    id: string; name: string; asOf: string; count: number;
    scanned: number; ranked: boolean; note: string;
  } | null;
  /** The measured null result. Never render the score without it. */
  provenance: {
    available: boolean;
    headline: string;
    measuredOn?: string | null;
    years?: number | null;
    tests?: number | null;
    significant?: number | null;
    appliesTo?: string;
  };
}
