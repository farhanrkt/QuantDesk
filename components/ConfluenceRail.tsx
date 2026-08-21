"use client";

import type {
  AnomalyResponse, Engine, QualityResponse, TechnicalResponse, ValuationResponse,
} from "@/lib/types";
import { pct } from "@/lib/utils";

const ACC = "#35C4A8";
const DIST = "#FF6B6B";
const TECH = "#5B8DEF";
const DCF = "#E8B44C";
const DDM = "#A78BFA";
const QUAL = "#E8B44C";
const ASH = "#7A8CA0";

interface Reading {
  lens: string;
  /** The question this lens answers, in the reader's own words. */
  question: string;
  verdict: string;
  detail: string;
  color: string;
  /** -1 bearish, 0 neutral, +1 bullish. Used only for the agreement count. */
  vote: number;
}

/**
 * THE RAIL IS THE FIRST THING ANYONE READS, so it is the last place that should
 * be speaking in acronyms. It used to summarise the quality lens as
 * "F-Score 8/9 · Z'' 5.6 (grey) · M -2.29" — three published scores compressed
 * into eleven characters of jargon, above the fold, before the reader has met
 * any of them. Each line now says what the score MEANS; the numbers themselves
 * are one click away in the lens that owns them.
 */
const blank = (lens: string, question: string): Reading => ({
  lens, question, verdict: "—", detail: "no reading", color: ASH, vote: 0,
});

/**
 * Votes with the RECENT flow bias, not the all-time one.
 *
 * `netFlowBias` sums flow across every anomaly in the look-back — on the default
 * 2y period that is a two-year verdict. Setting it beside a live trend reading
 * and a current valuation implied the lenses were describing the same
 * moment, when one of them was averaging over two years. The all-time figure is
 * still shown in the anomaly panel, labelled with its horizon.
 */
function readAnomaly(state: Engine<AnomalyResponse>): Reading {
  const question = "Is anyone unusual trading this?";
  if (state.status !== "ready") return blank("Flow", question);
  const { stats } = state.data;
  const bias = stats.recentFlowBias;
  const color = bias === "Accumulation" ? ACC : bias === "Distribution" ? DIST : ASH;
  const drift =
    stats.netFlowBias !== bias
      ? `, leaning ${stats.netFlowBias.toLowerCase()} over the full window`
      : "";
  return {
    lens: "Flow",
    question,
    verdict: stats.recentCount === 0 ? "Quiet" : bias === "Accumulation" ? "Buying"
      : bias === "Distribution" ? "Selling" : "Mixed",
    detail:
      stats.recentCount === 0
        ? `Nothing unusual in the last ${stats.recentDays} days (${stats.anomalyCount} odd days across the whole window)`
        : `${stats.recentCount} unusual day${stats.recentCount === 1 ? "" : "s"} in the last ${stats.recentDays}${drift}`,
    color: stats.recentCount === 0 ? ASH : color,
    vote:
      stats.recentCount === 0 ? 0 : bias === "Accumulation" ? 1 : bias === "Distribution" ? -1 : 0,
  };
}

function readTechnical(state: Engine<TechnicalResponse>): Reading {
  const question = "What has the price been doing?";
  if (state.status !== "ready") return blank("Trend", question);
  const { summary, latest, longTerm, hasLongTerm } = state.data;
  const tone = summary.trend_tone;
  const color = tone === "bull" ? ACC : tone === "bear" ? DIST : TECH;
  // Prefer the long-horizon verdict when there is enough history for one — it
  // is the sentence a holder asked for. The 50/200-day trend label is a
  // description of the last few months wearing the same word.
  const context = hasLongTerm
    ? longTerm.view.headline
    : `Last close ${latest.close.toFixed(2)} (${latest.changePct >= 0 ? "+" : ""}${latest.changePct.toFixed(2)}% on the day)`;
  return {
    lens: "Trend",
    question,
    verdict: summary.trend,
    detail: context,
    color,
    vote: tone === "bull" ? 1 : tone === "bear" ? -1 : 0,
  };
}

const ENGINE_NAMES: Record<string, string> = {
  DCF: "cash-flow model",
  DDM: "dividend model",
  RI: "book-value model",
};

function readValuation(state: Engine<ValuationResponse>): Reading {
  const question = "What is the business worth?";
  if (state.status !== "ready") return blank("Value", question);
  const d = state.data;
  const color =
    d.verdict === "UNDERVALUED" ? ACC : d.verdict === "OVERVALUED" ? DIST
      : d.engine === "DDM" ? DDM : DCF;
  const gap = d.monteCarlo.upside;
  const direction = gap == null ? "" : gap >= 0
    ? `the market price is ${pct(Math.abs(gap), 0)} below that`
    : `the market price is ${pct(Math.abs(gap), 0)} above that`;
  return {
    lens: "Value",
    question,
    verdict: d.verdict.charAt(0) + d.verdict.slice(1).toLowerCase(),
    detail: `The ${ENGINE_NAMES[d.engine] ?? d.engine} puts it near ${d.monteCarlo.p50Label}; ${direction}. `
      + `${pct(d.monteCarlo.probUndervalued, 0)} of simulated runs came out cheap.`,
    color,
    vote: d.verdict === "UNDERVALUED" ? 1 : d.verdict === "OVERVALUED" ? -1 : 0,
  };
}

const DISTRESS_WORDS: Record<string, string> = {
  safe: "balance sheet comfortably clear of distress",
  grey: "balance sheet neither clearly safe nor distressed",
  distress: "balance sheet in the distress zone",
};

const MANIPULATION_WORDS: Record<string, string> = {
  clean: "no sign of massaged earnings",
  borderline: "accruals close to the manipulation threshold",
  flagged: "accounting pattern flags for a closer look",
};

function readQuality(state: Engine<QualityResponse>): Reading {
  const question = "Are the numbers real?";
  if (state.status !== "ready") return blank("Quality", question);
  const d = state.data;
  if (!d.applicable)
    return {
      lens: "Quality", question, verdict: "n/a",
      detail: "These three accounting models were built on non-financial firms and do not "
        + "transfer to banks or insurers, so no score is reported.",
      color: ASH, vote: 0,
    };

  const parts: string[] = [];
  if (d.piotroski) {
    parts.push(`${d.piotroski.score} of ${d.piotroski.maxScore} health checks passed`);
  }
  if (d.altman?.band) parts.push(DISTRESS_WORDS[d.altman.band] ?? d.altman.band);
  if (d.beneish?.band) parts.push(MANIPULATION_WORDS[d.beneish.band] ?? d.beneish.band);

  return {
    lens: "Quality",
    question,
    verdict: d.verdict === "SOUND" ? "Sound"
      : d.verdict === "CONCERNS" ? "Concerns" : "Neutral",
    detail: parts.length ? `${parts.join(", ")}.` : (d.headline ?? ""),
    color: d.verdict === "SOUND" ? ACC : d.verdict === "CONCERNS" ? DIST : QUAL,
    vote: d.verdict === "SOUND" ? 1 : d.verdict === "CONCERNS" ? -1 : 0,
  };
}

/**
 * The one view none of the three source apps could produce: what the flow model,
 * the trend model and the valuation model each conclude, side by side, and
 * whether they agree. Agreement is the finding — three independent methods
 * landing in the same place is worth more than any one of them alone.
 */
export function ConfluenceRail({
  ticker, anomaly, technical, valuation, quality,
}: {
  ticker: string;
  anomaly: Engine<AnomalyResponse>;
  technical: Engine<TechnicalResponse>;
  valuation: Engine<ValuationResponse>;
  quality: Engine<QualityResponse>;
}) {
  const readings = [readAnomaly(anomaly), readTechnical(technical),
                    readValuation(valuation), readQuality(quality)];
  const live = readings.filter((r) => r.verdict !== "—" && r.verdict !== "n/a");
  const votes = live.map((r) => r.vote);
  const bulls = votes.filter((v) => v > 0).length;
  const bears = votes.filter((v) => v < 0).length;

  let agreement = "Mixed signals";
  let agreementColor = ASH;
  if (live.length === 0) {
    agreement = "Awaiting data";
  } else if (bulls === live.length && bulls > 1) {
    agreement = `All ${bulls} lenses constructive`;
    agreementColor = ACC;
  } else if (bears === live.length && bears > 1) {
    agreement = `All ${bears} lenses negative`;
    agreementColor = DIST;
  } else if (bulls > bears) {
    agreement = `${bulls} of ${live.length} constructive`;
    agreementColor = ACC;
  } else if (bears > bulls) {
    agreement = `${bears} of ${live.length} negative`;
    agreementColor = DIST;
  }

  return (
    <section className="animate-rise rounded border border-rule bg-panel">
      <div className="flex flex-wrap items-baseline justify-between gap-3 border-b border-rule px-5 py-3">
        <div className="flex items-baseline gap-3">
          <h2 className="font-mono text-lg font-semibold tracking-[0.14em]">{ticker}</h2>
          <span className="eyebrow">{live.length || "no"} lenses reading</span>
        </div>
        <span className="num text-xs font-semibold" style={{ color: agreementColor }}>
          {agreement}
        </span>
      </div>
      <div className="border-b border-rule px-5 py-2">
        {/* Agreement is the product's headline claim, so its main weakness
            belongs next to it rather than in a footnote. */}
        <p className="text-[0.68rem] leading-relaxed text-ash">
          These lenses are not fully independent: flow and trend are both functions of the same
          price and volume series, so they agree more often than four unrelated tests would.
          Value and quality read the filings instead and carry most of the independent
          information.
        </p>
      </div>

      <div className="grid divide-y divide-rule sm:grid-cols-2 sm:divide-x lg:grid-cols-4 lg:divide-y-0">
        {readings.map((r) => (
          <div key={r.lens} className="relative px-5 py-4">
            <span aria-hidden className="absolute left-0 top-4 h-[calc(100%-2rem)] w-[2px]"
                  style={{ background: r.color, opacity: r.verdict === "—" ? 0.25 : 1 }} />
            <div className="eyebrow mb-0.5">{r.lens}</div>
            <div className="mb-1.5 text-[0.65rem] italic leading-snug text-ash/70">
              {r.question}
            </div>
            <div className="num text-lg font-semibold leading-tight" style={{ color: r.color }}>
              {r.verdict}
            </div>
            <p className="mt-1 text-xs leading-relaxed text-ash">{r.detail}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
