"use client";

import type {
  AnomalyResponse, Engine, QualityResponse, TechnicalResponse, ValuationResponse,
} from "@/lib/types";
import { cn, num, pct, signedPct, verdictLabel } from "@/lib/utils";

const ACC = "#35C4A8";
const DIST = "#FF6B6B";
const TECH = "#5B8DEF";
const DCF = "#E8B44C";
const DDM = "#A78BFA";
const QUAL = "#E8B44C";
const ASH = "#7A8CA0";

/**
 * WHICH BODY OF DATA A LENS READS. This is the field the agreement count is
 * built on, so it is part of the type rather than a lookup table off to one
 * side: adding a fifth lens forces you to say what it reads.
 */
type Family = "price" | "filings";

const FAMILY_LABEL: Record<Family, string> = {
  price: "price and volume",
  filings: "the filings",
};

interface Reading {
  lens: string;
  /** The question this lens answers, in the reader's own words. */
  question: string;
  verdict: string;
  detail: string;
  color: string;
  /** Still running, as opposed to failed or absent. Drives the pulse only. */
  pending?: boolean;
  /** -1 bearish, 0 neutral, +1 bullish. Used only for the agreement count. */
  vote: number;
  family: Family;
}

export interface Agreement {
  /** Lenses with a reading — the raw headcount, kept because it is honest. */
  lenses: number;
  /** Distinct data sources behind them. The number the headline speaks in. */
  independent: number;
  headline: string;
  color: string;
  /** The sentence reconciling the two counts, or null when they are equal. */
  footnote: string | null;
}

/**
 * AGREEMENT IS COUNTED IN DATA SOURCES, NOT IN PANELS.
 *
 * This used to be `bulls === live.length` over four lenses, printing "All 4
 * lenses constructive" directly beneath the paragraph explaining that flow and
 * trend are both functions of the same OHLCV series and are therefore not two
 * opinions. The caveat and the arithmetic contradicted each other, and the
 * arithmetic was the part in large type.
 *
 * So each family collapses to ONE vote before anything is tallied. Four
 * agreeing lenses over two sources is "both independent readings constructive,
 * across 4 lenses" — the same facts, without the inflation. A family whose
 * members disagree votes zero and is named as split, because two readings of
 * one dataset pointing opposite ways is a real finding and averaging it away
 * would be the same sin in the other direction.
 *
 * WHAT THIS IS NOT: a measurement. `ranking.signal_correlation` computes its
 * overlap from the scan's own cross-section; there is no cross-section here, so
 * the grouping is a DECLARED assumption about what shares a source. It is
 * deliberately coarse and it is stated on the panel.
 */
export function agreementOf(readings: Reading[]): Agreement {
  const live = readings.filter((r) => r.verdict !== "—" && r.verdict !== "n/a");
  if (live.length === 0) {
    return { lenses: 0, independent: 0, headline: "Awaiting data",
             color: ASH, footnote: null };
  }

  const families = new Map<Family, number[]>();
  for (const r of live) families.set(r.family, [...(families.get(r.family) ?? []), r.vote]);

  const split: Family[] = [];
  const votes: number[] = [];
  for (const [family, member] of families) {
    const up = member.filter((v) => v > 0).length;
    const down = member.filter((v) => v < 0).length;
    if (up > 0 && down > 0) split.push(family);
    votes.push(up > down ? 1 : down > up ? -1 : 0);
  }

  const total = votes.length;
  const bulls = votes.filter((v) => v > 0).length;
  const bears = votes.filter((v) => v < 0).length;
  const noun = total === 1 ? "reading" : "readings";
  // "Both" only when there are exactly two. There are two families today, so
  // `total` cannot exceed two — but the Family type is meant to be extended,
  // and "Both independent readings" over three sources is the kind of wrong
  // that survives review because it reads fluently.
  const all = total === 2 ? "Both" : "All";

  let headline = "Mixed signals";
  let color = ASH;
  if (bulls === total && total > 1) {
    headline = `${all} independent ${noun} constructive`;
    color = ACC;
  } else if (bears === total && total > 1) {
    headline = `${all} independent ${noun} negative`;
    color = DIST;
  } else if (bulls > bears) {
    headline = `${bulls} of ${total} independent ${noun} constructive`;
    color = ACC;
  } else if (bears > bulls) {
    headline = `${bears} of ${total} independent ${noun} negative`;
    color = DIST;
  }

  const notes: string[] = [];
  if (live.length > total) {
    notes.push(`${live.length} lenses, ${total} independent ${total === 1 ? "source" : "sources"}`);
  }
  for (const family of split) notes.push(`split on ${FAMILY_LABEL[family]}`);

  return { lenses: live.length, independent: total, headline, color,
           footnote: notes.length ? notes.join(" · ") : null };
}

/**
 * THE RAIL IS THE FIRST THING ANYONE READS, so it is the last place that should
 * be speaking in acronyms. It used to summarise the quality lens as
 * "F-Score 8/9 · Z'' 5.6 (grey) · M -2.29" — three published scores compressed
 * into eleven characters of jargon, above the fold, before the reader has met
 * any of them. Each line now says what the score MEANS; the numbers themselves
 * are one click away in the lens that owns them.
 */
/**
 * A lens with nothing to show yet. `state` separates the two reasons for that,
 * because they deserve different treatment: a lens still fetching gets a pulsing
 * rule and the word "running", one that failed or never started stays inert. A
 * ten-to-sixteen-second first run behind four identical dashes gave a reader no
 * way to tell a slow engine from a broken one.
 */
const blank = (lens: string, question: string, family: Family,
               state?: string): Reading => ({
  lens, question, family, color: ASH, vote: 0,
  pending: state === "loading",
  verdict: state === "loading" ? "…" : "—",
  detail: state === "loading" ? "running" : "no reading",
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
  if (state.status !== "ready") return blank("Flow", question, "price", state.status);
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
    family: "price",
  };
}

function readTechnical(state: Engine<TechnicalResponse>): Reading {
  const question = "What has the price been doing?";
  if (state.status !== "ready") return blank("Trend", question, "price", state.status);
  const { summary, latest, longTerm, hasLongTerm } = state.data;
  const tone = summary.trend_tone;
  const color = tone === "bull" ? ACC : tone === "bear" ? DIST : TECH;
  // Prefer the long-horizon verdict when there is enough history for one — it
  // is the sentence a holder asked for. The 50/200-day trend label is a
  // description of the last few months wearing the same word.
  const context = hasLongTerm
    ? longTerm.view.headline
    // `num` rather than `toFixed`: these are typed non-null, but `jsonsafe`
    // turns any NaN into a null on the wire, and `.toFixed` on a null throws —
    // which would take down the rail that sits above every other panel. The
    // shared formatters render "—" for missing data and are asserted to.
    : `Last close ${num(latest.close)} (${signedPct(latest.changePct / 100)} on the day)`;
  return {
    lens: "Trend",
    question,
    verdict: summary.trend,
    detail: context,
    color,
    vote: tone === "bull" ? 1 : tone === "bear" ? -1 : 0,
    family: "price",
  };
}

const ENGINE_NAMES: Record<string, string> = {
  DCF: "cash-flow model",
  DDM: "dividend model",
  RI: "book-value model",
};

function readValuation(state: Engine<ValuationResponse>): Reading {
  const question = "What is the business worth?";
  if (state.status !== "ready") return blank("Value", question, "filings", state.status);
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
    verdict: verdictLabel(d.verdict),
    detail: `The ${ENGINE_NAMES[d.engine] ?? d.engine} puts it near ${d.monteCarlo.p50Label}; ${direction}. `
      + `${pct(d.monteCarlo.probUndervalued, 0)} of simulated runs came out cheap.`,
    color,
    vote: d.verdict === "UNDERVALUED" ? 1 : d.verdict === "OVERVALUED" ? -1 : 0,
    family: "filings",
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
  if (state.status !== "ready") return blank("Quality", question, "filings", state.status);
  const d = state.data;
  if (!d.applicable)
    return {
      lens: "Quality", question, verdict: "n/a",
      detail: "These three accounting models were built on non-financial firms and do not "
        + "transfer to banks or insurers, so no score is reported.",
      color: ASH, vote: 0, family: "filings",
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
    family: "filings",
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
  const agreement = agreementOf(readings);
  const pending = readings.filter((r) => r.pending).length;

  return (
    <section className="animate-rise rounded border border-rule bg-panel">
      <div className="flex flex-wrap items-baseline justify-between gap-3 border-b border-rule px-5 py-3">
        <div className="flex items-baseline gap-3">
          <h2 className="font-mono text-lg font-semibold tracking-[0.14em]">{ticker}</h2>
          <span className="eyebrow">
            {pending > 0
              ? `${readings.length - pending} of ${readings.length} lenses in`
              : `${agreement.lenses || "no"} lenses reading`}
          </span>
        </div>
        <div className="text-right">
          <span className="num block text-xs font-semibold"
                style={{ color: agreement.color }}>
            {agreement.headline}
          </span>
          {/* The reconciliation sits WITH the headline, not in the paragraph
              below it. A reader who takes the top line at face value and never
              reads on should still have been told what it counts. */}
          {agreement.footnote && (
            <span className="mt-0.5 block text-[0.6rem] text-ash">{agreement.footnote}</span>
          )}
        </div>
      </div>
      <div className="border-b border-rule px-5 py-2">
        {/* Agreement is the product's headline claim, so its main weakness
            belongs next to it rather than in a footnote. */}
        <p className="text-[0.68rem] leading-relaxed text-ash">
          These lenses are not fully independent: flow and trend are both functions of the same
          price and volume series, while value and quality both read the filings — so four
          panels rest on two bodies of data. The verdict above counts those two rather than the
          four, which is why it can say &ldquo;both&rdquo; where the grid shows four. The
          grouping is a stated assumption about what shares a source, not a measured
          correlation; the ranking panel measures its own overlap because a scan gives it a
          cross-section to measure from, and a single ticker does not.
        </p>
      </div>

      <div className="grid divide-y divide-rule sm:grid-cols-2 sm:divide-x lg:grid-cols-4 lg:divide-y-0">
        {readings.map((r) => (
          <div key={r.lens} className="relative px-5 py-4">
            {/* Same `animate-pulseline` the panel skeletons use, so a lens that
                is still fetching pulses in the rail and in its own panel at the
                same rate rather than inventing a second idea of "loading". */}
            <span aria-hidden
                  className={cn("absolute left-0 top-4 h-[calc(100%-2rem)] w-[2px]",
                                r.pending && "animate-pulseline")}
                  style={{ background: r.pending ? TECH : r.color,
                           opacity: r.verdict === "—" ? 0.25 : 1 }} />
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
