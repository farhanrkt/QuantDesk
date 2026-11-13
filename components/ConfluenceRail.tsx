"use client";

import type {
  AnomalyResponse, Engine, QualityResponse, TechnicalResponse, ValuationResponse,
} from "@/lib/types";
import { useState } from "react";
import { ChevronRight } from "lucide-react";
import { TONE_HEX, TONE_TEXT } from "@/components/ui/explain";
import { cn, num, pct, signedPct, verdictLabel } from "@/lib/utils";
import { LENS_HUE, palette } from "@/lib/palette";
import { msg, t, useT } from "@/lib/i18n";

const ACC = palette.acc;
const DIST = palette.dist;
const TECH = palette.tech;
const DCF = palette.dcf;
const DDM = palette.ddm;
const QUAL = palette.value;
const ASH = palette.ash;

/**
 * WHICH BODY OF DATA A LENS READS. This is the field the agreement count is
 * built on, so it is part of the type rather than a lookup table off to one
 * side: adding a fifth lens forces you to say what it reads.
 */
type Family = "price" | "filings";

const FAMILY_LABEL: Record<Family, string> = {
  price: msg("price and volume"),
  filings: msg("the filings"),
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
  /** The lens was asked and did not answer — not the same as not yet asked. */
  failed?: boolean;
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
  // A lens still running has not voted. Counting its "…" as a live neutral
  // reading headlined a half-loaded rail "Mixed signals", or "1 of 2
  // independent readings constructive" with one of the two not yet asked.
  const live = readings.filter((r) => !r.pending && r.verdict !== "…"
                                      && r.verdict !== "—" && r.verdict !== "n/a");
  if (live.length === 0) {
    // NOT "AWAITING" ONCE EVERYTHING HAS SETTLED. This said "Awaiting data"
    // above four failed lenses, which reads as a page still loading when it
    // has finished and found nothing. Pending or never asked still awaits.
    const settledEmpty = readings.some((r) => r.failed) && !readings.some((r) => r.pending);
    return { lenses: 0, independent: 0,
             headline: settledEmpty ? t("No lens returned a reading") : t("Awaiting data"),
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
  // "Both" only when there are exactly two. There are two families today, so
  // `total` cannot exceed two — but the Family type is meant to be extended,
  // and "Both independent readings" over three sources is the kind of wrong
  // that survives review because it reads fluently.
  const both = total === 2;

  let headline = t("Mixed signals");
  let color = ASH;
  if (bulls === total && total > 1) {
    headline = both ? t("Both independent readings constructive")
      : t("All independent readings constructive");
    color = ACC;
  } else if (bears === total && total > 1) {
    headline = both ? t("Both independent readings negative")
      : t("All independent readings negative");
    color = DIST;
  } else if (bulls > bears) {
    headline = total === 1
      ? t("{count} of {total} independent reading constructive", { count: bulls, total })
      : t("{count} of {total} independent readings constructive", { count: bulls, total });
    color = ACC;
  } else if (bears > bulls) {
    headline = total === 1
      ? t("{count} of {total} independent reading negative", { count: bears, total })
      : t("{count} of {total} independent readings negative", { count: bears, total });
    color = DIST;
  }

  const notes: string[] = [];
  if (live.length > total) {
    notes.push(total === 1
      ? t("{lenses} lenses, {total} independent source", { lenses: live.length, total })
      : t("{lenses} lenses, {total} independent sources", { lenses: live.length, total }));
  }
  for (const family of split) notes.push(t("split on {family}", { family: t(FAMILY_LABEL[family]) }));

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
  failed: state === "error",
  verdict: state === "loading" ? "…" : "—",
  detail: state === "loading" ? t("running") : state === "error" ? t("did not run") : t("no reading"),
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
  const question = t("Is anyone unusual trading this?");
  if (state.status !== "ready") return blank(msg("Flow"), question, "price", state.status);
  const { stats } = state.data;
  const bias = stats.recentFlowBias;
  const color = bias === "Accumulation" ? ACC : bias === "Distribution" ? DIST : ASH;
  const drift =
    stats.netFlowBias !== bias
      ? t(", leaning {bias} over the full window",
          { bias: t(BIAS_WORD[stats.netFlowBias] ?? stats.netFlowBias.toLowerCase()) })
      : "";
  return {
    lens: msg("Flow"),
    question,
    verdict: stats.recentCount === 0 ? t("Quiet") : bias === "Accumulation" ? t("Buying")
      : bias === "Distribution" ? t("Selling") : t("Mixed"),
    detail:
      stats.recentCount === 0
        ? t("Nothing unusual in the last {days} days ({count} odd days across the whole window)",
            { days: stats.recentDays, count: stats.anomalyCount })
        : stats.recentCount === 1
          ? t("{count} unusual day in the last {days}{drift}",
              { count: stats.recentCount, days: stats.recentDays, drift })
          : t("{count} unusual days in the last {days}{drift}",
              { count: stats.recentCount, days: stats.recentDays, drift }),
    color: stats.recentCount === 0 ? ASH : color,
    vote:
      stats.recentCount === 0 ? 0 : bias === "Accumulation" ? 1 : bias === "Distribution" ? -1 : 0,
    family: "price",
  };
}

function readTechnical(state: Engine<TechnicalResponse>): Reading {
  const question = t("What has the price been doing?");
  if (state.status !== "ready") return blank(msg("Trend"), question, "price", state.status);
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
    : t("Last close {close} ({change} on the day)",
        { close: num(latest.close), change: signedPct(latest.changePct / 100) });
  return {
    lens: msg("Trend"),
    question,
    verdict: summary.trend,
    detail: context,
    color,
    vote: tone === "bull" ? 1 : tone === "bear" ? -1 : 0,
    family: "price",
  };
}

const ENGINE_NAMES: Record<string, string> = {
  DCF: msg("cash-flow model"),
  DDM: msg("dividend model"),
  RI: msg("book-value model"),
};

// The flow bias codes as words; the codes themselves are compared above.
const BIAS_WORD: Record<string, string> = {
  Accumulation: msg("accumulation"), Distribution: msg("distribution"),
  Mixed: msg("mixed"), Neutral: msg("neutral"),
};

function readValuation(state: Engine<ValuationResponse>): Reading {
  const question = t("What is the business worth?");
  if (state.status !== "ready") return blank(msg("Value"), question, "filings", state.status);
  const d = state.data;
  const color =
    d.verdict === "UNDERVALUED" ? ACC : d.verdict === "OVERVALUED" ? DIST
      : d.engine === "DDM" ? DDM : DCF;
  const gap = d.monteCarlo.upside;
  const direction = gap == null ? "" : gap >= 0
    ? t("the market price is {gap} below that", { gap: pct(Math.abs(gap), 0) })
    : t("the market price is {gap} above that", { gap: pct(Math.abs(gap), 0) });
  return {
    lens: msg("Value"),
    question,
    verdict: verdictLabel(d.verdict),
    detail: t("The {engine} puts it near {fair}; {direction}. ",
              { engine: ENGINE_NAMES[d.engine] ? t(ENGINE_NAMES[d.engine]) : d.engine,
                fair: d.monteCarlo.p50Label, direction })
      + t("{share} of simulated runs came out cheap.", { share: pct(d.monteCarlo.probUndervalued, 0) }),
    color,
    vote: d.verdict === "UNDERVALUED" ? 1 : d.verdict === "OVERVALUED" ? -1 : 0,
    family: "filings",
  };
}

const DISTRESS_WORDS: Record<string, string> = {
  safe: msg("balance sheet comfortably clear of distress"),
  grey: msg("balance sheet neither clearly safe nor distressed"),
  distress: msg("balance sheet in the distress zone"),
};

const MANIPULATION_WORDS: Record<string, string> = {
  clean: msg("no sign of massaged earnings"),
  borderline: msg("accruals close to the manipulation threshold"),
  flagged: msg("accounting pattern flags for a closer look"),
};

function readQuality(state: Engine<QualityResponse>): Reading {
  const question = t("Are the numbers real?");
  if (state.status !== "ready") return blank(msg("Quality"), question, "filings", state.status);
  const d = state.data;
  // THE REFUSAL SAYS WHICH REFUSAL. This printed the bank sentence for every
  // `applicable: false`, so a throttled fetch that returned no sector for
  // Microsoft read "built on non-financial firms ... do not transfer to banks"
  // — a confident statement that Microsoft is a lender. The server sends the
  // cause and a sentence for each; only the designed refusal gets the short one.
  if (!d.applicable)
    return {
      lens: msg("Quality"), question, verdict: "n/a",
      detail: d.cause === "financial" || (!d.cause && !d.reason)
        ? t("These three accounting models were built on non-financial firms and do not transfer to banks or insurers, so no score is reported.")
        : d.reason ?? t("No score could be computed for this listing."),
      color: ASH, vote: 0, family: "filings",
    };

  const parts: string[] = [];
  if (d.piotroski) {
    parts.push(t("{score} of {max} health checks passed",
                 { score: d.piotroski.score, max: d.piotroski.maxScore }));
  }
  if (d.altman?.band) parts.push(DISTRESS_WORDS[d.altman.band] ? t(DISTRESS_WORDS[d.altman.band]) : d.altman.band);
  if (d.beneish?.band) {
    parts.push(MANIPULATION_WORDS[d.beneish.band] ? t(MANIPULATION_WORDS[d.beneish.band]) : d.beneish.band);
  }

  return {
    lens: msg("Quality"),
    question,
    verdict: d.verdict === "SOUND" ? t("Sound")
      : d.verdict === "CONCERNS" ? t("Concerns") : t("Neutral"),
    detail: parts.length ? `${parts.join(", ")}.` : (d.headline ?? ""),
    color: d.verdict === "SOUND" ? ACC : d.verdict === "CONCERNS" ? DIST : QUAL,
    vote: d.verdict === "SOUND" ? 1 : d.verdict === "CONCERNS" ? -1 : 0,
    family: "filings",
  };
}

/**
 * IDENTITY, NOT JUDGEMENT. Which lens is speaking is structural and always the
 * same colour; whether its reading is good or bad is `tone`, and the two are
 * never the same token. Before v2 the flow lens and the "accumulation" verdict
 * were both teal, so a lens name and a conclusion rendered identically and
 * neither read as meaningful.
 */
// The lens hues come from lib/palette.ts, shared with the tab bar.

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
 * Four lenses, four words, four status dots, side by side. A reader takes the
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
    <ul className="grid grid-cols-2 gap-2 lg:grid-cols-4">
      {readings.map((r) => {
        const tone = voteTone(r);
        const hue = LENS_HUE[r.lens] ?? palette.ash;
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
                {t(r.lens)}
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
  ticker, anomaly, technical, valuation, quality, subtitle, actions,
}: {
  ticker: string;
  anomaly: Engine<AnomalyResponse>;
  technical: Engine<TechnicalResponse>;
  valuation: Engine<ValuationResponse>;
  quality: Engine<QualityResponse>;
  /** Who the ticker is — the company header, drawn under the symbol. */
  subtitle?: React.ReactNode;
  /** Watch, compare, share, print: things to do WITH this page, beside its name. */
  actions?: React.ReactNode;
}) {
  const t = useT();
  const readings = [readAnomaly(anomaly), readTechnical(technical),
                    readValuation(valuation), readQuality(quality)];
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
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
            <h1 className="font-mono tracking-tight">{ticker}</h1>
            {actions}
          </div>
          {subtitle}
          <p className="mt-1 text-meta text-ash">
            {pending > 0
              ? t("{answered} of {total} lenses have answered",
                  { answered: readings.length - pending, total: readings.length })
              : agreement.independent === 1
                ? t("{lenses} lenses reading · {independent} independent source of data",
                    { lenses: agreement.lenses || t("No"), independent: agreement.independent })
                : t("{lenses} lenses reading · {independent} independent sources of data",
                    { lenses: agreement.lenses || t("No"), independent: agreement.independent })}
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
        {t("Flow and Trend both read price and volume; Value and Quality both read the filings. The count is of data sources, not panels.")}
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
        {showDetail ? t("Hide what each lens says") : t("What each lens says")}
      </button>

      <div id="lens-detail"
           className={cn("divide-y divide-rule border-t border-rule",
                         "sm:grid-cols-2 sm:divide-x lg:grid lg:grid-cols-4 lg:divide-y-0",
                         showDetail ? "grid" : "hidden lg:grid")}>
        {readings.map((r) => {
          const hue = LENS_HUE[r.lens] ?? palette.ash;
          const tone = voteTone(r);
          return (
            <div key={r.lens} className="px-5 py-4">
              <div className="mb-2 flex items-center gap-2">
                <span aria-hidden className="h-3.5 w-1 shrink-0 rounded-full"
                      style={{ background: hue, opacity: r.verdict === "—" ? 0.3 : 1 }} />
                <span className="text-micro font-semibold uppercase tracking-wider"
                      style={{ color: hue }}>{t(r.lens)}</span>
              </div>
              {/* The QUESTION, at reading size and not in italic grey. It is the
                  most useful line in the whole rail for a newcomer, and v1 set
                  it at 10.4px at 70% opacity — the least legible text on screen. */}
              <p className="mb-2.5 text-meta text-ash">{r.question}</p>
              <p className={cn("text-h3 font-semibold leading-tight",
                               r.pending && "animate-pulseline")}
                 style={{ color: TONE_HEX[tone] ?? palette.ash }}>
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

// THE COMPARE VIEW READS EACH COMPANY THROUGH THE SAME FOUR SENTENCES. Exported
// here, in one statement at the end, rather than by prefixing the functions:
// the lens-family drift check in check_frontend.mjs splits this file on lines
// that START with `function`, and an `export` in front would merge the blocks
// it reads. `agreementOf` is deliberately not used there — see lib/compare.ts.
export { readAnomaly, readQuality, readTechnical, readValuation, voteTone };
