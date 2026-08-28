"use client";

import { AlertTriangle, ArrowRight, EyeOff, Scale } from "lucide-react";
import type { AgreementMeasurement, Synthesis } from "@/lib/types";
import { TONE_HEX, TONE_TEXT, useDetail } from "@/components/ui/explain";
import { cn, pct, signed } from "@/lib/utils";

/**
 * What the four lenses add up to, in sentences.
 *
 * THIS IS THE ANSWER TO "SO WHAT?", AND IT IS DELIBERATELY NOT A SCORE.
 * Every sentence here restates a figure computed elsewhere on the page; none of
 * it is a new claim and none of it is a recommendation. The reasoning for
 * refusing a buy/hold/sell verdict permanently lives in `explain.for_synthesis`,
 * and a pytest suite asserts that no combination of the twenty-seven lens
 * permutations ever produces an instruction.
 *
 * THE ORDER OF THE BLOCKS IS THE ARGUMENT. Readings first, because a summary
 * that hides its inputs is a verdict. Then the cross-check, because agreement
 * between two independent bodies of data is the product's whole claim. Then the
 * tensions and the blind spots — which are placed ABOVE the next steps on
 * purpose, so nobody reaches "what to do" without passing "what this cannot
 * tell you".
 */

const LENS_HEX: Record<string, string> = {
  flow: "#35C4A8", trend: "#5B8DEF", value: "#E8B44C", quality: "#F2C14E",
};

function Block({
  icon: Icon, title, tone, children,
}: {
  icon: typeof Scale; title: string; tone?: string; children: React.ReactNode;
}) {
  return (
    <div className="border-t border-rule px-5 py-4">
      <div className="mb-2 flex items-center gap-2">
        <Icon aria-hidden className="h-3.5 w-3.5"
              style={{ color: tone ? TONE_HEX[tone] : "#7A8CA0" }} />
        <span className="eyebrow">{title}</span>
      </div>
      {children}
    </div>
  );
}

/**
 * The measurement behind the claim in the sentence above it.
 *
 * NOT COLOURED, AND THAT IS THE SAME RULE §8 APPLIES TO PROVENANCE. A kappa is
 * not good news or bad news about this company — it is a fact about how much
 * two of this app's own readings overlap across a universe, and it would be the
 * same number on a wonderful business and a failing one. Tinting it green when
 * it is low would turn "the cross-check is sound" into "the stock is fine",
 * which is exactly the reading the whole panel exists to prevent. The tone
 * belongs to the sentence above; this block is grey in every state.
 *
 * The six lens pairs sit behind a disclosure because they are supporting
 * detail: the headline is the one pair the app's arithmetic rests on, and the
 * rest is there for a reader who wants to check whether the DECLARED grouping
 * behaves the way it is declared to. Flow and Trend are supposed to be the
 * redundant pair — that is where it would show up, or fail to.
 */
function Measured({ data }: { data: AgreementMeasurement }) {
  const rows = data.pairs.filter((p) => p.usable);
  return (
    <div className="mt-3 border-t border-rule/60 pt-3">
      <p className="text-[0.72rem] leading-relaxed text-ash">{data.reading}</p>
      {rows.length > 0 && (
        <details className="mt-2">
          <summary className="eyebrow cursor-pointer list-none text-ash
                              transition-colors hover:text-chalk focus-visible:outline-none
                              focus-visible:ring-1 focus-visible:ring-tech">
            Every pair, measured ({rows.length})
          </summary>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full text-left text-[0.7rem]">
              <thead>
                <tr className="eyebrow border-b border-rule [&>th]:py-1.5 [&>th]:pr-3
                               [&>th]:font-normal">
                  <th>Pair</th>
                  <th className="text-right">Agree</th>
                  <th className="text-right">By chance</th>
                  <th className="text-right">κ</th>
                  <th className="text-right">95% interval</th>
                  <th className="text-right">τb</th>
                  <th className="text-right">Names</th>
                </tr>
              </thead>
              <tbody className="text-ash">
                {rows.map((p) => (
                  <tr key={`${p.a}-${p.b}`} className="border-b border-rule/40 last:border-0">
                    <td className="py-1.5 pr-3 text-chalk/80">{p.a} · {p.b}</td>
                    <td className="num py-1.5 pr-3 text-right">{pct(p.observed, 0)}</td>
                    <td className="num py-1.5 pr-3 text-right">{pct(p.chance, 0)}</td>
                    <td className="num py-1.5 pr-3 text-right text-chalk/80">
                      {signed(p.kappa)}
                    </td>
                    <td className="num py-1.5 pr-3 text-right">
                      {p.low === null || p.high === null
                        ? "—" : `${signed(p.low)} to ${signed(p.high)}`}
                    </td>
                    <td className="num py-1.5 pr-3 text-right">{signed(p.tauB)}</td>
                    <td className="num py-1.5 text-right">{p.n}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
      <p className="mt-2 text-[0.6rem] leading-relaxed text-ash">
        Measured {data.measuredOn} across {data.scope}. κ is agreement minus the agreement
        each pair&apos;s own habits already produce; τb is whether they order the same way.
        A rate measured today decays with the lists it was taken on — re-run{" "}
        <code className="font-mono">scripts/measure_lens_agreement.py</code> after changing
        what any lens concludes.
      </p>
    </div>
  );
}

export function SynthesisPanel({ data }: { data: Synthesis }) {
  const detail = useDetail();
  const guided = detail === "simple";
  const { agreement } = data;

  return (
    <section className="animate-rise rounded border border-rule bg-panel">
      <div className="flex flex-wrap items-baseline justify-between gap-3 px-5 py-3">
        <h2 className="eyebrow">What this adds up to</h2>
        <span className="num text-[0.68rem] text-ash">{data.headline}</span>
      </div>

      {/* Each lens in one sentence, colour-keyed to the lens that said it. */}
      <div className="grid gap-px border-t border-rule bg-rule sm:grid-cols-2">
        {data.readings.map((r) => (
          <div key={r.key} className="bg-panel px-5 py-3.5">
            <div className="mb-1 flex items-baseline gap-2">
              <span className="eyebrow" style={{ color: LENS_HEX[r.key] }}>{r.lens}</span>
              <span className={cn("num text-sm font-semibold", TONE_TEXT[r.tone])}>
                {r.verdict}
              </span>
              <span className="ml-auto text-[0.6rem] text-ash/70">
                reads {r.familyLabel}
              </span>
            </div>
            <p className="text-xs leading-relaxed text-chalk/80">{r.sentence}</p>
          </div>
        ))}
      </div>

      <Block icon={Scale} title="Do they agree?" tone={agreement.tone}>
        <p className={cn("text-sm leading-relaxed", TONE_TEXT[agreement.tone])}>
          {agreement.text}
        </p>
        {agreement.measured && <Measured data={agreement.measured} />}
      </Block>

      {data.tensions.length > 0 && (
        <Block icon={AlertTriangle} title="Where they pull against each other" tone="warn">
          <ul className="space-y-2.5">
            {data.tensions.map((t) => (
              <li key={t.title}>
                <span className="text-sm font-semibold text-warn">{t.title}. </span>
                <span className="text-sm leading-relaxed text-chalk/80">{t.text}</span>
              </li>
            ))}
          </ul>
        </Block>
      )}

      {data.blindSpots.length > 0 && (
        <Block icon={EyeOff} title="What this cannot tell you about this company">
          <ul className="space-y-2.5">
            {data.blindSpots.map((b) => (
              <li key={b.title}>
                <span className="text-sm font-semibold text-chalk/90">{b.title}. </span>
                <span className="text-sm leading-relaxed text-ash">{b.text}</span>
              </li>
            ))}
          </ul>
        </Block>
      )}

      {/* Guided readers get the next steps spelled out. In Full mode they are
          collapsed to a single line, because someone who has been here before
          does not need to be told to open the tab they are about to click. */}
      {guided ? (
        <Block icon={ArrowRight} title="What to check next">
          <ol className="space-y-2">
            {data.nextChecks.map((c, i) => (
              <li key={c} className="flex gap-2.5 text-sm leading-relaxed text-chalk/80">
                <span className="num shrink-0 text-ash">{String(i + 1).padStart(2, "0")}</span>
                <span>{c}</span>
              </li>
            ))}
          </ol>
        </Block>
      ) : (
        <details className="group border-t border-rule px-5 py-3">
          <summary className="eyebrow cursor-pointer list-none text-ash hover:text-chalk">
            What to check next ({data.nextChecks.length})
          </summary>
          <ol className="mt-3 space-y-2">
            {data.nextChecks.map((c, i) => (
              <li key={c} className="flex gap-2.5 text-sm leading-relaxed text-chalk/80">
                <span className="num shrink-0 text-ash">{String(i + 1).padStart(2, "0")}</span>
                <span>{c}</span>
              </li>
            ))}
          </ol>
        </details>
      )}

      <p className="border-t border-rule px-5 py-3 text-[0.68rem] leading-relaxed text-ash">
        {data.caveat}
      </p>
    </section>
  );
}
