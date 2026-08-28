"use client";

import { useState } from "react";
import { Check, Minus, X } from "lucide-react";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Explain, ExplainedStat, TONE_HEX, useDetail,
} from "@/components/ui/explain";
import { RangeField } from "@/components/ui/controls";
import type {
  DomainDimension, ExplainMap, ManipulationPosterior, QualityResponse,
} from "@/lib/types";
import { cn, num } from "@/lib/utils";

const ASH = "#7A8CA0";

/**
 * Where each score came from, beside the score.
 *
 * NOTHING IN HERE IS COLOURED, and both directions are the reason.
 *
 * "Outside" is not a warning. Every practical use of Piotroski, Altman and
 * Beneish today is outside their samples — they ended between 1965 and 1996 —
 * so painting it amber would cry wolf on all three scores for every company
 * forever, which is how a reader learns to ignore a colour.
 *
 * "Inside" is not reassurance, and that is the trap. A green tick against
 * "period: inside" tells a reader the number can be trusted here, which is a
 * claim about the model's accuracy on this company that nothing in this app
 * measures. Same rule as the pre-trade panel: absence of a mismatch is not
 * evidence of fit.
 *
 * So the emphasis is typographic, never chromatic. A mismatch is brighter
 * because it is the line worth reading first, and that is all it means.
 */
const VERDICT_WORD: Record<string, string> = {
  inside: "inside", outside: "outside", unknown: "cannot tell",
};

/**
 * What a Beneish flag is actually worth.
 *
 * THE PRIOR IS THE FEATURE, WHICH IS WHY IT MOVES. The posterior is Bayes on
 * two published constants and one number nobody can measure exactly — how
 * common manipulation is — so presenting a single figure would hide the input
 * the answer is most sensitive to. Drag it and the point is made: across every
 * prevalence the literature supports, a flag never becomes more likely true
 * than false.
 *
 * THE CONTROL SELECTS, IT DOES NOT CALCULATE. Every stop arrives from the
 * server already computed and already worded. Recomputing here would put the
 * arithmetic — and the judgement about what the number means — in TypeScript,
 * which is the one place this codebase refuses to keep either.
 *
 * NOTHING HERE IS COLOURED. The M-Score above already carries the alarm; this
 * number qualifies it downward. A second warning colour would count one fact
 * twice and make the deflating figure look like a second flag.
 */
function FlagWorth({ data, explain }: {
  data: ManipulationPosterior; explain?: ExplainMap[string];
}) {
  const defaultIndex = Math.max(0, data.curve.findIndex((p) => p.isDefault));
  const [index, setIndex] = useState(defaultIndex);
  const point = data.curve[Math.min(index, data.curve.length - 1)] ?? data.curve[0];
  const shown = data.flagged ? point.givenFlagText : point.givenCleanText;

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          {data.flagged ? "What this flag is worth" : "What a clean reading is worth"}
        </CardTitle>
        <span className="flex items-center gap-1.5 font-mono text-[0.65rem] text-ash">
          Beneish, cutoff {num(data.characteristics.cutoff)}
          <Explain explain={explain} />
        </span>
      </CardHeader>
      <CardBody className="space-y-4">
        {/* The shift, not the level. A bare "0.84%" beside a clean score reads
            as a clean bill of health; the pair reads as what the test did. */}
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="num text-sm text-ash">{point.priorText}</span>
          <span className="text-ash">&rarr;</span>
          <span className="num text-2xl font-semibold text-chalk">{shown}</span>
          <span className="text-[0.78rem] leading-relaxed text-ash">
            {data.flagged
              ? `likely to be a real manipulator, so about ${point.falseAlarmText} of flags
                 like this are false alarms`
              : "chance of manipulation anyway — the screen moved a number that was already small"}
          </span>
        </div>

        <div className="rounded border border-rule bg-raised px-4 py-3">
          <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
            <span className="eyebrow">
              How common is manipulation? {point.priorText} of companies
            </span>
            {index !== defaultIndex && (
              <button type="button" onClick={() => setIndex(defaultIndex)}
                      className="eyebrow text-ash hover:text-chalk focus:outline-none
                                 focus-visible:ring-1 focus-visible:ring-tech">
                reset
              </button>
            )}
          </div>
          <RangeField index={index} count={data.curve.length} onChange={setIndex}
                      label="Assumed rate of earnings manipulation" />
          <p className="mt-2 text-[0.72rem] leading-relaxed text-ash">
            {point.label
              ? <>
                  <span className="text-chalk/80">{point.label}</span> — {point.source}
                  {point.event ? `, counting ${point.event}` : ""}.
                  {point.extrapolated && (
                    <span className="text-warn/90">
                      {" "}Beneish&apos;s error rates were never measured against that
                      broader definition, so this stop brackets the range rather than
                      answering the same question.
                    </span>
                  )}
                </>
              : "Between the published estimates. Move it to a labelled stop to see whose."}
          </p>
        </div>

        <p className="text-[0.78rem] leading-relaxed text-chalk/80">
          {data.robustRange.sentence}
        </p>

        {data.partialNote && (
          <p className="text-[0.72rem] leading-relaxed text-warn/90">{data.partialNote}</p>
        )}

        <p className="text-[0.7rem] leading-relaxed text-ash">
          {data.characteristics.note} {data.caveat} Source: {data.characteristics.citation}.
        </p>
      </CardBody>
    </Card>
  );
}

function Dimension({
  dimension, explain, guided,
}: { dimension: DomainDimension; explain?: ExplainMap[string]; guided: boolean }) {
  return (
    <li className="border-b border-rule/40 px-5 py-2 last:border-0">
      <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-0.5">
        <span className="flex items-center gap-1.5 text-xs text-chalk/90">
          {dimension.name}
          <Explain explain={explain} />
        </span>
        <span className={cn("num text-[0.65rem] uppercase tracking-[0.1em]",
                            dimension.verdict === "outside" ? "text-chalk/70" : "text-ash")}>
          {VERDICT_WORD[dimension.verdict] ?? dimension.verdict}
        </span>
        <span className="ml-auto num text-[0.68rem] text-ash">{dimension.thisUse}</span>
      </div>
      {guided && (
        <p className="mt-1 text-[0.7rem] leading-relaxed text-ash">{dimension.note}</p>
      )}
    </li>
  );
}

/**
 * Engine 4 — the lens that opens the filings.
 *
 * The other three read the company from the outside: price, volume, cash flow
 * projections. None of them asks whether the business is solvent or whether the
 * earnings are real. A DCF on a company sliding toward insolvency is arithmetic,
 * and this is the panel that says so before the reader acts on it.
 *
 * THE COLOUR TRAP THIS PANEL SITS ON. Piotroski and Altman reward a HIGH number;
 * Beneish punishes one. All three are "accounting quality scores" and they sit
 * in the same row of tiles, so colouring them the same way would tell a reader
 * that an earnings-manipulation flag is good news. The direction now comes from
 * `explain[key].tone`, decided in Python with a test named after exactly that
 * mistake (`test_beneish_and_altman_point_opposite_ways`).
 */
export function QualityPanel({ data }: { data: QualityResponse }) {
  const detail = useDetail();
  const simple = detail === "simple";
  const ex: ExplainMap = data.explain ?? {};

  if (!data.applicable) {
    return (
      <Card className="animate-rise">
        <CardHeader><CardTitle>Accounting quality</CardTitle></CardHeader>
        <CardBody>
          <p className="text-sm leading-relaxed text-ash">{data.reason}</p>
          {data.sector && (
            <p className="mt-3 font-mono text-[0.65rem] uppercase tracking-[0.1em] text-ash">
              {data.sector}{data.industry ? ` · ${data.industry}` : ""}
            </p>
          )}
        </CardBody>
      </Card>
    );
  }

  const { piotroski, altman, beneish } = data;
  const verdictColor = TONE_HEX[
    data.verdict === "SOUND" ? "good" : data.verdict === "CONCERNS" ? "bad" : "neutral"
  ] ?? ASH;

  return (
    <div className="space-y-4 animate-rise">
      {/* ---------------- the summary in plain English ---------------- */}
      <Card accent={verdictColor}>
        <CardHeader>
          <CardTitle>What the filings say</CardTitle>
          <span className="num text-xs font-semibold" style={{ color: verdictColor }}>
            {data.verdict ?? "—"}
          </span>
        </CardHeader>
        <CardBody className="space-y-3">
          <p className="text-[0.95rem] leading-relaxed text-chalk/90">{data.headline}</p>
          <p className="text-[0.78rem] leading-relaxed text-ash">
            Three published tests, each asking something different: is the business improving
            (Piotroski), is it far from running out of money (Altman), and do the numbers look
            like they have been massaged (Beneish). They read the accounts, not the share price,
            which is what makes them worth putting beside the other three lenses.
          </p>
        </CardBody>
      </Card>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
        {piotroski && <ExplainedStat explain={ex.piotroski} sub={piotroski.reading} />}
        {altman && <ExplainedStat explain={ex.altman} sub={altman.reading} />}
        {beneish && <ExplainedStat explain={ex.beneish} sub={beneish.reading} />}
      </div>

      {/* ---------------- what a flag is worth ---------------- */}
      {data.manipulationPosterior && (
        <FlagWorth data={data.manipulationPosterior} explain={ex.manipulationPosterior} />
      )}

      {/* ---------------- where the three numbers came from ---------------- */}
      {data.domains && (
        <Card>
          <CardHeader>
            <CardTitle>Where these numbers come from</CardTitle>
            <span className="font-mono text-[0.65rem] text-ash">
              scored on {data.domains.fiscalYear ?? "undated"} filings
            </span>
          </CardHeader>
          <CardBody className="px-0">
            <p className="px-5 pb-3 text-[0.78rem] leading-relaxed text-ash">
              Each of these three was fitted on a particular set of companies, in a
              particular market, in particular years. Every practical use today is outside
              those samples — they ended between 1965 and 1996 — so this is provenance
              rather than a warning. It is here because a number carried a long way from
              where it was tested should say so, and because matching the sample would not
              make a score right any more than missing it makes one wrong.
            </p>
            {Object.entries(data.domains.screens).map(([key, screen]) => (
              <div key={key} className="border-t border-rule">
                <div className="flex flex-wrap items-baseline justify-between gap-2 px-5 pb-1 pt-3">
                  <span className="eyebrow">{screen.label}</span>
                  <span className="text-[0.62rem] text-ash">{screen.citation}</span>
                </div>
                <p className="px-5 pb-2 text-[0.68rem] leading-relaxed text-ash">
                  Fitted on {screen.sample}.
                </p>
                <ul>
                  {screen.dimensions.map((dimension) => (
                    <Dimension key={dimension.key} dimension={dimension} guided={simple}
                               explain={ex[`domain.${key}.${dimension.key}`]} />
                  ))}
                </ul>
              </div>
            ))}
            <p className="border-t border-rule px-5 pt-3 text-[0.7rem] leading-relaxed text-ash">
              There is no fit score here on purpose. Counting how many axes match would be a
              reliability rating, and none of these papers reports how their model behaves
              on a company like this one — which is the whole reason the axes are listed
              separately.
            </p>
          </CardBody>
        </Card>
      )}

      {piotroski && piotroski.signals.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>The nine health checks</CardTitle>
            <span className="font-mono text-[0.65rem] text-ash">
              {piotroski.signalsAvailable} of {piotroski.signalsTotal} computable
            </span>
          </CardHeader>
          <CardBody className="px-0">
            <ul>
              {(simple ? piotroski.signals.filter((s) => s.passed !== null)
                       : piotroski.signals).map((signal) => (
                <li key={signal.name}
                    className="flex items-baseline gap-3 border-b border-rule/60 px-5 py-2 last:border-0">
                  <span className="mt-0.5 shrink-0">
                    {signal.passed === null
                      ? <Minus aria-label="not computable" className="h-3.5 w-3.5 text-ash" />
                      : signal.passed
                        ? <Check aria-label="pass" className="h-3.5 w-3.5 text-acc" />
                        : <X aria-label="fail" className="h-3.5 w-3.5 text-dist" />}
                  </span>
                  <span className="flex-1 text-xs text-chalk/90">{signal.name}</span>
                  <span className="num shrink-0 text-[0.7rem] text-ash">{signal.detail}</span>
                </li>
              ))}
            </ul>
            <p className="px-5 pt-3 text-[0.7rem] leading-relaxed text-ash">
              A tick means that measure improved on last year, or was already healthy. A check
              that could not be computed scores nothing — it is never counted as a pass, which
              is why the total moves with how complete the filings are.
            </p>
          </CardBody>
        </Card>
      )}

      {!simple && (
        <div className="grid gap-4 lg:grid-cols-2">
          {altman && (
            <Card accent={TONE_HEX[ex.altman?.tone ?? "neutral"]}>
              <CardHeader><CardTitle>How far from running out of money</CardTitle></CardHeader>
              <CardBody className="space-y-3">
                <p className="text-sm leading-relaxed text-chalk/80">{altman.reading}</p>
                <dl className="space-y-1 text-[0.72rem]">
                  {Object.entries(altman.components).map(([key, value]) => {
                    const explain = ex[`altmanComponent.${key}`];
                    return (
                      <div key={key} className="flex items-baseline justify-between gap-2">
                        <dt className="flex items-center gap-1.5 text-ash">
                          {explain?.label ?? key}
                          <Explain explain={explain} />
                        </dt>
                        <dd className="num text-chalk/80">{value === null ? "—" : num(value)}</dd>
                      </div>
                    );
                  })}
                </dl>
                <p className="text-[0.68rem] leading-relaxed text-ash">
                  This is the emerging-market version of Altman&apos;s score, so an Indonesian
                  listing and a US one are measured on the same scale. Safe above 5.85, distress
                  below 4.35, and the gap between them is a zone the model declines to call.
                </p>
              </CardBody>
            </Card>
          )}

          {beneish && (
            <Card accent={TONE_HEX[ex.beneish?.tone ?? "neutral"]}>
              <CardHeader><CardTitle>Do the earnings look massaged?</CardTitle></CardHeader>
              <CardBody className="space-y-3">
                <p className="text-sm leading-relaxed text-chalk/80">{beneish.reading}</p>
                <dl className="space-y-1 text-[0.72rem]">
                  {Object.entries(beneish.indices).map(([key, value]) => {
                    const explain = ex[`beneishIndex.${key}`];
                    return (
                      <div key={key} className="flex items-baseline justify-between gap-2">
                        <dt className="flex items-center gap-1.5 text-ash">
                          {explain?.label ?? key}
                          <Explain explain={explain} />
                        </dt>
                        <dd className="num text-chalk/80">{value === null ? "—" : num(value)}</dd>
                      </div>
                    );
                  })}
                </dl>
                <p className="text-[0.68rem] leading-relaxed text-ash">
                  A screen, not a finding. Beneish classified roughly three-quarters of known
                  manipulators correctly — which on a population where manipulation is rare also
                  means most flags are false positives. Every index is a this-year-over-last-year
                  ratio, so 1.00 means &quot;unchanged&quot; for all of them.
                </p>
              </CardBody>
            </Card>
          )}
        </div>
      )}

      <p className="text-xs leading-relaxed text-ash">
        Piotroski (2000) scores nine fundamental trends; Altman&apos;s Z&apos;&apos;-score (2005
        emerging-market variant) estimates distance from distress; Beneish (1999) screens accrual
        patterns. All three were built on non-financial firms and are not reported for banks or
        insurers. Educational and research use only.
      </p>
    </div>
  );
}
