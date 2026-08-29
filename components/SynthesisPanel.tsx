"use client";

import { AlertTriangle, ArrowRight, ChevronRight, EyeOff, Scale } from "lucide-react";
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
 *
 * WHAT v2 CHANGED, AND WHY NONE OF IT IS A CUT. Not one sentence was deleted.
 * The panel was unreadable because every block arrived at the same weight: four
 * lens readings, a cross-check, the tensions, the blind spots and the next
 * steps, all at 12px, all in the same grey, one after another for eight hundred
 * words. Three fixes, none of them subtractive:
 *
 *   Blocks are TYPED rather than uniform. A tension is a finding and reads like
 *   one; a blind spot is an admission and reads quieter; the working behind the
 *   agreement measurement is a disclosure and starts closed. A reader can tell
 *   from the shape of a block whether it is telling them something new.
 *
 *   Long findings open with a LEAD line at 17px and continue at 15px, so
 *   stopping after one line still leaves you holding the finding.
 *
 *   Prose stops at a readable measure. These paragraphs ran to 96ch.
 */

const LENS_HUE: Record<string, string> = {
  flow: "#2FBFA4", trend: "#6B9BFF", value: "#E8B44C", quality: "#C9A227",
};

/**
 * One region of the argument.
 *
 * `weight` is the only knob and it is deliberately coarse: `finding` for things
 * the app is telling you, `quiet` for things it is admitting. A third option
 * would be a severity scale, and a severity scale over blind spots is a ranking
 * of how bad the gaps are — the composite this panel refuses, arriving through
 * the back door of a font size.
 */
function Block({
  icon: Icon, title, tone, weight = "finding", children,
}: {
  icon: typeof Scale;
  title: string;
  tone?: string;
  weight?: "finding" | "quiet";
  children: React.ReactNode;
}) {
  return (
    <div className={cn("border-t border-rule px-5 py-5",
                       weight === "quiet" && "bg-sunken/40")}>
      <div className="mb-3 flex items-center gap-2.5">
        <Icon aria-hidden className="h-4 w-4 shrink-0"
              style={{ color: tone ? TONE_HEX[tone] : "#8496A9" }} />
        <h3 className={cn("text-meta font-semibold uppercase tracking-wider",
                          weight === "quiet" ? "text-ash" : "text-chalk")}>
          {title}
        </h3>
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
 * IT STARTS CLOSED IN v2. The working runs to about two hundred words of
 * statistics and it sat open, at body weight, directly under the sentence it
 * supports — so a reader met a paragraph about Cohen's kappa before finishing
 * the paragraph about their company. Closed by default, with the number itself
 * on the summary line so the disclosure is not a mystery box, and nothing
 * removed.
 */
function Measured({ data }: { data: AgreementMeasurement }) {
  const rows = data.pairs.filter((p) => p.usable);
  return (
    <div className="mt-4 rounded-lg border border-ruleSoft bg-sunken">
      <details className="group">
        <summary className="flex cursor-pointer list-none items-center gap-2.5 px-4 py-3
                            text-meta text-ash transition-colors hover:text-chalk
                            focus-visible:outline-none focus-visible:ring-2
                            focus-visible:ring-tech">
          <ChevronRight aria-hidden
                        className="h-4 w-4 shrink-0 transition-transform group-open:rotate-90" />
          <span className="min-w-0">
            How much do the two actually overlap? Measured:{" "}
            <span className="num font-semibold text-chalk">
              κ = {signed(data.families.kappa)}
            </span>{" "}
            across {data.families.n} names
          </span>
        </summary>

        <div className="space-y-4 px-4 pb-4 pl-11">
          <p className="prose-col text-meta text-ash">{data.reading}</p>

          {rows.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-micro">
                <caption className="sr-only">
                  Chance-corrected agreement between each pair of lenses
                </caption>
                <thead>
                  <tr className="border-b border-rule text-faint [&>th]:py-2 [&>th]:pr-3
                                 [&>th]:font-medium">
                    <th scope="col">Pair</th>
                    <th scope="col" className="text-right">Agree</th>
                    <th scope="col" className="text-right">By chance</th>
                    <th scope="col" className="text-right">κ</th>
                    <th scope="col" className="text-right">95% interval</th>
                    <th scope="col" className="text-right">τb</th>
                    <th scope="col" className="text-right">Names</th>
                  </tr>
                </thead>
                <tbody className="text-ash">
                  {rows.map((p) => (
                    <tr key={`${p.a}-${p.b}`} className="border-b border-ruleSoft last:border-0">
                      <th scope="row" className="py-2 pr-3 text-left font-medium text-body">
                        {p.a} · {p.b}
                      </th>
                      <td className="num py-2 pr-3 text-right">{pct(p.observed, 0)}</td>
                      <td className="num py-2 pr-3 text-right">{pct(p.chance, 0)}</td>
                      <td className="num py-2 pr-3 text-right font-semibold text-chalk">
                        {signed(p.kappa)}
                      </td>
                      <td className="num py-2 pr-3 text-right">
                        {p.low === null || p.high === null
                          ? "—" : `${signed(p.low)} to ${signed(p.high)}`}
                      </td>
                      <td className="num py-2 pr-3 text-right">{signed(p.tauB)}</td>
                      <td className="num py-2 text-right">{p.n}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <p className="prose-col text-meta leading-relaxed text-faint">
            Measured {data.measuredOn} across {data.scope}. κ is agreement minus the agreement
            each pair&apos;s own habits already produce; τb is whether they order the same way.
            A rate measured today decays with the lists it was taken on — re-run{" "}
            <code className="font-mono text-ash">scripts/measure_lens_agreement.py</code> after
            changing what any lens concludes.
          </p>
        </div>
      </details>
    </div>
  );
}

export function SynthesisPanel({ data }: { data: Synthesis }) {
  const guided = useDetail() === "simple";
  const { agreement } = data;

  const steps = (
    <ol className="space-y-3">
      {data.nextChecks.map((c, i) => (
        <li key={c} className="flex gap-3">
          <span aria-hidden
                className="num mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center
                           rounded-full bg-tech/15 text-micro font-semibold text-tech">
            {i + 1}
          </span>
          <span className="prose-col text-base leading-relaxed text-body">{c}</span>
        </li>
      ))}
    </ol>
  );

  return (
    <section className="animate-rise overflow-hidden rounded-xl border border-rule bg-panel">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 px-5 pb-4 pt-5">
        <h2>What this adds up to</h2>
        <p className="text-meta text-ash">{data.headline}</p>
      </div>

      {/* Each lens in one sentence, colour-keyed to the lens that said it. */}
      <div className="grid gap-px border-t border-rule bg-rule sm:grid-cols-2">
        {data.readings.map((r) => (
          <div key={r.key} className="bg-panel px-5 py-4">
            <div className="mb-2 flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
              <span className="text-micro font-semibold uppercase tracking-wider"
                    style={{ color: LENS_HUE[r.key] }}>
                {r.lens}
              </span>
              <span className={cn("text-lead font-semibold", TONE_TEXT[r.tone])}>
                {r.verdict}
              </span>
              <span className="ml-auto shrink-0 text-micro text-faint">
                reads {r.familyLabel}
              </span>
            </div>
            <p className="prose-col text-meta leading-relaxed text-body">{r.sentence}</p>
          </div>
        ))}
      </div>

      <Block icon={Scale} title="Do they agree?" tone={agreement.tone}>
        {/* THE LEAD. One sentence at 17px in the tone colour, the working below
            it at 15px and closed. A reader who stops after this line has the
            finding rather than a fragment of it. */}
        <p className={cn("prose-col text-lead leading-snug", TONE_TEXT[agreement.tone])}>
          {agreement.text}
        </p>
        {agreement.measured && <Measured data={agreement.measured} />}
      </Block>

      {data.tensions.length > 0 && (
        <Block icon={AlertTriangle} title="Where they pull against each other" tone="warn">
          <ul className="space-y-4">
            {data.tensions.map((t) => (
              <li key={t.title} className="border-l border-warn/40 pl-4">
                <h4 className="text-lead font-semibold text-warn">{t.title}</h4>
                <p className="prose-col mt-1 text-base leading-relaxed text-body">{t.text}</p>
              </li>
            ))}
          </ul>
        </Block>
      )}

      {data.blindSpots.length > 0 && (
        <Block icon={EyeOff} title="What this cannot tell you about this company" weight="quiet">
          <ul className="space-y-3.5">
            {data.blindSpots.map((b) => (
              <li key={b.title}>
                <h4 className="text-meta font-semibold text-chalk">{b.title}</h4>
                <p className="prose-col mt-0.5 text-meta leading-relaxed text-ash">{b.text}</p>
              </li>
            ))}
          </ul>
        </Block>
      )}

      {/* Guided readers get the next steps spelled out. In Full mode they are
          collapsed to a single line, because someone who has been here before
          does not need to be told to open the tab they are about to click. */}
      {guided ? (
        <Block icon={ArrowRight} title="What to check next">{steps}</Block>
      ) : (
        <details className="group border-t border-rule">
          <summary className="flex cursor-pointer list-none items-center gap-2.5 px-5 py-3.5
                              text-meta text-ash transition-colors hover:text-chalk
                              focus-visible:outline-none focus-visible:ring-2
                              focus-visible:ring-tech">
            <ChevronRight aria-hidden
                          className="h-4 w-4 shrink-0 transition-transform group-open:rotate-90" />
            What to check next ({data.nextChecks.length})
          </summary>
          <div className="px-5 pb-5 pl-11">{steps}</div>
        </details>
      )}

      <p className="prose-col border-t border-rule px-5 py-4 text-meta leading-relaxed text-faint">
        {data.caveat}
      </p>
    </section>
  );
}
