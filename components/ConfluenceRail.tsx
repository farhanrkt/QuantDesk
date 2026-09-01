"use client";

import type {
  AnomalyResponse, Engine, ExpectationsResponse, QualityResponse, TechnicalResponse,
  ValuationResponse,
} from "@/lib/types";
import { useState } from "react";
import { ChevronRight } from "lucide-react";
import { TONE_HEX, TONE_TEXT } from "@/components/ui/explain";
import { cn, num, pct, signedPct, verdictLabel } from "@/lib/utils";

const ACC = "#35C4A8";
const DIST = "#FF6B6B";
const TECH = "#5B8DEF";
const DCF = "#E8B44C";
const DDM = "#A78BFA";
const QUAL = "#E8B44C";
const EXPECT = "#E07AC0";
const ASH = "#7A8CA0";

/**
 * WHICH BODY OF DATA A LENS READS. This is the field the agreement count is
 * built on, so it is part of the type rather than a lookup table off to one
 * side: adding a fifth lens forces you to say what it reads.
 */
type Family = "price" | "filings" | "estimates";

const FAMILY_LABEL: Record<Family, string> = {
  price: "price and volume",
  filings: "the filings",
  estimates: "the estimate record",
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
  // "Both" only when there are exactly two. This branch was written before a
  // third family existed, against the day one did — and §18 was that day. With
  // three sources reading it "Both independent readings constructive" is the
  // kind of wrong that survives review because it reads fluently.
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
 * THE VERDICT IS THE SERVER'S, AND THE TWO SILENT STATES ARE NOT THE SAME ONE.
 *
 * `applicable: false` means nobody publishes an estimate for this listing — the
 * lens declined, it does not vote, and it must not read as reassurance. QUIET
 * means analysts cover it and none of them moved, which is a real reading that
 * votes zero. Rendering either as a bare dash would merge a refusal with a
 * finding, and on this lens the refusal is the common case: analyst coverage is
 * where smaller listings stop being followed at all.
 */
function readExpectations(state: Engine<ExpectationsResponse>): Reading {
  const question = "What does everyone else expect?";
  if (state.status !== "ready") return blank("Expectations", question, "estimates", state.status);
  const d = state.data;

  if (!d.applicable)
    return {
      lens: "Expectations", question, verdict: "n/a",
      detail: d.refusal
        ?? "No analyst publishes estimates for this listing, so there is no consensus "
           + "to read. That is a coverage gap, not a clean bill of health.",
      color: ASH, vote: 0, family: "estimates",
    };

  const b = d.breadth;
  const counts = b && b.up != null && b.down != null
    ? `${b.up} raised and ${b.down} cut in the last month. `
    : "";
  const verdict = d.verdict === "RISING" ? "Rising"
    : d.verdict === "FALLING" ? "Falling"
      : d.verdict === "QUIET" ? "Quiet"
        : d.verdict === "THIN" ? "Too few moves" : "Mixed";
  const color = d.verdict === "RISING" ? ACC : d.verdict === "FALLING" ? DIST : EXPECT;

  return {
    lens: "Expectations",
    question,
    verdict,
    detail: `${counts}${d.headline}`,
    color: d.verdict === "RISING" || d.verdict === "FALLING" ? color : ASH,
    // ONLY A CLEAR DIRECTION VOTES. Quiet, thin and mixed are all real readings
    // and all of them vote zero — the app has no way to tell a settled
    // consensus from a divided one from a barely-observed one, and pretending
    // otherwise is what the MIN_REVISIONS floor in Python exists to prevent.
    vote: d.verdict === "RISING" ? 1 : d.verdict === "FALLING" ? -1 : 0,
    family: "estimates",
  };
}

/**
 * IDENTITY, NOT JUDGEMENT. Which lens is speaking is structural and always the
 * same colour; whether its reading is good or bad is `tone`, and the two are
 * never the same token. Before v2 the flow lens and the "accumulation" verdict
 * were both teal, so a lens name and a conclusion rendered identically and
 * neither read as meaningful.
 */
const LENS_HUE: Record<string, string> = {
  Flow: "#2FBFA4", Trend: "#6B9BFF", Value: "#E8B44C", Quality: "#C9A227",
  Expectations: "#E07AC0",
};

/** A vote is the SERVER's direction. This maps it to a tone and nothing else. */
const voteTone = (r: Reading): string =>
  r.verdict === "—" || r.verdict === "…" || r.verdict === "n/a" ? "none"
    : r.vote > 0 ? "good" : r.vote < 0 ? "bad" : "neutral";

const DOT: Record<string, string> = {
  good: "bg-acc", bad: "bg-dist", neutral: "bg-ash", none: "bg-faint",
};

/**
 * THE FOUR CHIPS. The one piece of at-a-glance this app allows itself.
 *
 * Five lenses, five words, five status dots, side by side. A reader takes the
 * shape of the answer in about a second — which is the entire request v2 was
 * built to satisfy — and the app still refuses to say what it adds up to.
 *
 * What makes that refusal real rather than rhetorical: there is no count, no
 * total, no average, no ordering by strength, and the chips are laid out on a
 * fixed grid so a reader cannot infer a ranking from their positions. Three
 * greens and a red stay three greens and a red. The synthesis below says in
 * sentences what they mean together, because sentences can carry "these two
 * disagree and that disagreement is the finding" and a score cannot.
 */
function LensChips({ readings }: { readings: Reading[] }) {
  return (
    <ul className="grid grid-cols-2 gap-2 lg:grid-cols-5">
      {readings.map((r) => {
        const tone = voteTone(r);
        const hue = LENS_HUE[r.lens] ?? "#8496A9";
        return (
          <li key={r.lens}
              className="flex items-start gap-2.5 rounded-lg border border-rule bg-sunken px-3 py-2.5"
              style={{ borderColor: `${hue}2E` }}>
            <span aria-hidden
                  className={cn("mt-1.5 h-2 w-2 shrink-0 rounded-full",
                                DOT[tone] ?? "bg-faint",
                                r.pending && "animate-pulseline")} />
            <span className="min-w-0">
              <span className="block text-micro font-semibold uppercase tracking-wider"
                    style={{ color: hue }}>
                {r.lens}
              </span>
              {/* WRAPS, NEVER TRUNCATES. Two of these verdicts are three words
                  long — "Above model range" came out as "Above mod…" in a
                  two-column grid on a phone, and a clipped verdict is not a
                  shorter verdict, it is a different one. The chip grows a line
                  instead; four chips of unequal height is a smaller cost than
                  one that lies. */}
              <span className={cn("block text-meta font-semibold leading-snug",
                                  TONE_TEXT[tone] ?? "text-chalk")}>
                {r.verdict}
              </span>
            </span>
          </li>
        );
      })}
    </ul>
  );
}

/**
 * The one view none of the three source apps could produce: what each lens
 * concludes, side by side, and whether they agree. Agreement is the finding —
 * methods that share no inputs landing in the same place is worth more than any
 * one of them alone, and §15 measured how much more.
 */
export function ConfluenceRail({
  ticker, anomaly, technical, valuation, quality, expectations,
}: {
  ticker: string;
  anomaly: Engine<AnomalyResponse>;
  technical: Engine<TechnicalResponse>;
  valuation: Engine<ValuationResponse>;
  quality: Engine<QualityResponse>;
  expectations: Engine<ExpectationsResponse>;
}) {
  const readings = [readAnomaly(anomaly), readTechnical(technical),
                    readValuation(valuation), readQuality(quality),
                    readExpectations(expectations)];
  const agreement = agreementOf(readings);
  const pending = readings.filter((r) => r.pending).length;
  // THE CHIPS AND THE COLUMNS ARE THE SAME FOUR VERDICTS. Side by side on a
  // wide screen that reads as summary-then-detail; stacked on a phone it reads
  // as the app saying everything twice, and it puts four paragraphs between the
  // reader and the synthesis. So below `lg` the detail is behind one control,
  // and the chips — which is what a glance wanted anyway — carry the rail.
  const [showDetail, setShowDetail] = useState(false);

  return (
    <section className="animate-rise overflow-hidden rounded-xl border border-rule bg-panel">
      {/* The ticker is the largest thing on the page, because it is the one
          fact the reader brought with them and every number below is about it. */}
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3 px-5 pb-4 pt-5">
        <div className="min-w-0">
          <h1 className="font-mono tracking-tight">{ticker}</h1>
          <p className="mt-1 text-meta text-ash">
            {pending > 0
              ? `${readings.length - pending} of ${readings.length} lenses have answered`
              : `${agreement.lenses || "No"} lenses reading · ${agreement.independent} independent `
                + `${agreement.independent === 1 ? "source" : "sources"} of data`}
          </p>
        </div>
        <div className="min-w-0 text-left sm:text-right">
          <p className="text-lead font-semibold" style={{ color: agreement.color }}>
            {agreement.headline}
          </p>
          {/* The reconciliation sits WITH the headline, not in the paragraph
              below it. A reader who takes the top line at face value and never
              reads on should still have been told what it counts. */}
          {agreement.footnote && (
            <p className="mt-0.5 text-micro text-ash">{agreement.footnote}</p>
          )}
        </div>
      </div>

      <div className="px-5 pb-4">
        <LensChips readings={readings} />
      </div>

      {/* ONE LINE, NOT NINETY-SIX WORDS. The paragraph here explained why four
          panels count as two sources, why the grouping is declared rather than
          measured, and what the ranking panel does differently — a defence of
          the method, permanently open, above every tab. The reasoning is in
          RESEARCH_ROADMAP §6 and §15; what a reader needs beside the count is
          what the count counts. */}
      <p className="border-t border-rule px-5 py-2.5 text-meta text-ash">
        Flow and Trend both read price and volume; Value and Quality both read the filings;
        Expectations reads what the analysts covering it forecast. The count is of data
        sources, not panels.
      </p>

      <button
        type="button"
        onClick={() => setShowDetail((v) => !v)}
        aria-expanded={showDetail}
        aria-controls="lens-detail"
        className="flex w-full items-center gap-2 border-t border-rule px-5 py-3 text-meta
                   text-ash transition-colors hover:text-chalk focus:outline-none
                   focus-visible:ring-2 focus-visible:ring-tech lg:hidden"
      >
        <ChevronRight aria-hidden
                      className={cn("h-4 w-4 shrink-0 transition-transform",
                                    showDetail && "rotate-90")} />
        {showDetail ? "Hide what each lens says" : "What each lens says"}
      </button>

      <div id="lens-detail"
           className={cn("divide-y divide-rule border-t border-rule",
                         "sm:grid-cols-2 sm:divide-x lg:grid lg:grid-cols-5 lg:divide-y-0",
                         showDetail ? "grid" : "hidden lg:grid")}>
        {readings.map((r) => {
          const hue = LENS_HUE[r.lens] ?? "#8496A9";
          const tone = voteTone(r);
          return (
            <div key={r.lens} className="px-5 py-4">
              <div className="mb-2 flex items-center gap-2">
                <span aria-hidden className="h-3.5 w-1 shrink-0 rounded-full"
                      style={{ background: hue, opacity: r.verdict === "—" ? 0.3 : 1 }} />
                <span className="text-micro font-semibold uppercase tracking-wider"
                      style={{ color: hue }}>{r.lens}</span>
              </div>
              {/* The QUESTION, at reading size and not in italic grey. It is the
                  most useful line in the whole rail for a newcomer, and v1 set
                  it at 10.4px at 70% opacity — the least legible text on screen. */}
              <p className="mb-2.5 text-meta text-ash">{r.question}</p>
              <p className={cn("text-h3 font-semibold leading-tight",
                               r.pending && "animate-pulseline")}
                 style={{ color: TONE_HEX[tone] ?? "#8496A9" }}>
                {r.verdict}
              </p>
              <p className="mt-2 text-meta leading-relaxed text-body">{r.detail}</p>
            </div>
          );
        })}
      </div>
    </section>
  );
}
