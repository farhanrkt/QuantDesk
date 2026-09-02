"use client";

import { AlertTriangle, ArrowRight, ChevronRight, EyeOff, Scale } from "lucide-react";
import type { AgreementMeasurement, Synthesis } from "@/lib/types";
import { TONE_HEX, TONE_TEXT } from "@/components/ui/explain";
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
  icon: Icon, title, tone, weight = "finding", collapsible, children,
}: {
  icon: typeof Scale;
  title: string;
  tone?: string;
  weight?: "finding" | "quiet";
  /**
   * Collapsed by default. Only for a block whose TITLE already states its
   * point: "What this cannot tell you about this company" says the thing even
   * shut, so closing it hides the list and not the claim.
   *
   * This panel and the pre-trade one sit above every tab — 1,080 words between
   * them, met again on each of the seven. What the reader must not be able to
   * miss is the agreement sentence and the named tensions; the enumeration of
   * blind spots is worth reading and worth reaching for.
   */
  collapsible?: boolean;
  children: React.ReactNode;
}) {
  const head = (
    <>
      <Icon aria-hidden className="h-4 w-4 shrink-0"
            style={{ color: tone ? TONE_HEX[tone] : "#8496A9" }} />
      <span className={cn("text-meta font-semibold uppercase tracking-wider",
                          weight === "quiet" ? "text-ash" : "text-chalk")}>
        {title}
      </span>
    </>
  );
  if (!collapsible) {
    return (
      <div className={cn("border-t border-rule px-5 py-5",
                         weight === "quiet" && "bg-sunken/40")}>
        <h3 className="mb-3 flex items-center gap-2.5">{head}</h3>
        {children}
      </div>
    );
  }
  return (
    <details className={cn("group border-t border-rule",
                           weight === "quiet" && "bg-sunken/40")}>
      <summary className="flex cursor-pointer list-none items-center gap-2.5 px-5 py-4
                          transition-colors hover:bg-raised/40 focus-visible:outline-none
                          focus-visible:ring-2 focus-visible:ring-tech">
        <ChevronRight aria-hidden
                      className="h-4 w-4 shrink-0 text-faint transition-transform
                                 group-open:rotate-90" />
        {head}
      </summary>
      <div className="px-5 pb-5">{children}</div>
    </details>
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
  // Guided/Full no longer splits this panel. It used to decide whether the next
  // steps were spelled out or collapsed, and now everything below the conclusion
  // is behind one control in both modes — a distinction that no longer had
  // anything to distinguish.
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
      {/* THE PANEL OPENS TO ITS CONCLUSION AND NOTHING ELSE.
          It sits above all seven tabs, so whatever shows by default is shown
          seven times to a reader working through the lenses. What survives that
          repetition is the sentence answering "do they agree?" — the reason the
          panel exists. Everything else is worth reading once and is one click
          away.

          That sentence is OUTSIDE the disclosure on purpose. A summary that
          collapses to a bare title is a hidden paragraph; this one collapses to
          its own answer.

          THE PER-LENS GRID IS GONE, AND THAT WAS A DUPLICATE RATHER THAN A CUT.
          The confluence rail above already names each lens, its verdict and a
          sentence of detail — visible on a wide screen, one tap away on a narrow
          one. Printing the same four verdicts again cost 220 words and 900
          pixels above every tab. "What this adds up to" is now only the adding
          up. */}
      <div className="px-5 pb-4 pt-5">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <h2>What this adds up to</h2>
          <p className="text-meta text-ash">{data.headline}</p>
        </div>
        <p className={cn("prose-col mt-3 text-lead leading-snug", TONE_TEXT[agreement.tone])}>
          {agreement.text}
        </p>
      </div>

      <details className="group border-t border-rule">
        <summary className="flex cursor-pointer list-none items-center gap-2.5 px-5 py-3.5
                            text-meta text-ash transition-colors hover:bg-raised/40
                            hover:text-chalk focus-visible:outline-none
                            focus-visible:ring-2 focus-visible:ring-tech">
          <ChevronRight aria-hidden
                        className="h-4 w-4 shrink-0 transition-transform group-open:rotate-90" />
          {/* Built from what is actually inside, so the handle never promises a
              section that is not there — a disclosure listing "where they
              conflict" on a company with no conflicts is a small lie. */}
          {(() => {
            const parts = [
              agreement.measured && "how much the two overlap",
              data.tensions.length > 0 && "where they conflict",
              data.blindSpots.length > 0 && "what none of them can see",
              "what to check next",
            ].filter(Boolean) as string[];
            const joined = parts.length > 1
              ? `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}`
              : parts[0];
            return joined.charAt(0).toUpperCase() + joined.slice(1);
          })()}
        </summary>

        {agreement.measured && (
          <Block icon={Scale} title="How much the two actually overlap" tone={agreement.tone}>
            <Measured data={agreement.measured} />
          </Block>
        )}

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
          <Block icon={EyeOff} title="What this cannot tell you about this company"
                 weight="quiet">
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

        <Block icon={ArrowRight} title="What to check next">{steps}</Block>
      </details>

      <p className="prose-col border-t border-rule px-5 py-4 text-meta leading-relaxed text-ash">
        {data.caveat}
      </p>
    </section>
  );
}
