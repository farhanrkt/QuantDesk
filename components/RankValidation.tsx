"use client";

import { FlaskConical } from "lucide-react";
import type { RankValidation as Validation } from "@/lib/types";
import { cn, num, signedPct } from "@/lib/utils";

/**
 * Does this ranking predict anything?
 *
 * THE PANEL THAT PRESENTS AN ORDER OWES THE READER THIS. A composite that sorts
 * a universe implies, without ever saying so, that the order means something.
 * The flow lens has been held to that standard since the event study shipped —
 * it measures whether an anomaly flag predicts abnormal returns and prints the
 * null result when there is one. The breadth tier asserted its usefulness by
 * omission until this existed.
 *
 * IT IS PLACED BELOW THE TABLE, NOT ABOVE IT, and that is deliberate. Above, it
 * would read as a disclaimer to scroll past before getting to the interesting
 * part. Below, it is the last thing read and the thing carried away — which is
 * the correct weighting, because "these seven signals did not predict returns
 * in six years of testing" is more decision-relevant than any single row.
 *
 * The numbers are measured offline by `scripts/backtest_ranking.py` and stamped
 * with their date, the same treatment the constituent lists get.
 */
export function RankValidation({ data }: { data?: Validation }) {
  if (!data?.available) return null;

  const rows = data.universe ?? [];
  const noEdge = (data.significant ?? 0) === 0;

  return (
    <section className="rounded border border-rule bg-panel">
      <div className="flex flex-wrap items-baseline justify-between gap-3 border-b border-rule px-5 py-3">
        <h3 className="eyebrow flex items-center gap-1.5">
          <FlaskConical aria-hidden className="h-3 w-3" />
          Does this ranking predict anything?
        </h3>
        <span className="num text-[0.65rem] text-ash">
          {data.tests} tests over {data.years} years &middot; measured {data.measuredOn}
        </span>
      </div>

      <div className="px-5 py-4">
        <p className={cn("text-sm leading-relaxed", noEdge ? "text-warn" : "text-chalk/90")}>
          {data.headline}
        </p>

        {rows.length > 0 && (
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-rule text-ash">
                  <th className="py-1.5 pr-3 font-normal">Holding period</th>
                  <th className="py-1.5 pr-3 text-right font-normal">Periods</th>
                  <th className="py-1.5 pr-3 text-right font-normal">Rank vs return</th>
                  <th className="py-1.5 pr-3 text-right font-normal">Top fifth &minus; bottom</th>
                  <th className="py-1.5 text-right font-normal">Smallest detectable</th>
                </tr>
              </thead>
              <tbody className="text-chalk/80">
                {rows.map((r) => (
                  <tr key={r.horizonDays} className="border-b border-rule/40 last:border-0">
                    <td className="py-1.5 pr-3">
                      {r.horizonDays} trading days
                      <span className="ml-1.5 text-ash">
                        (~{Math.round(r.horizonDays / 21)} month{r.horizonDays > 31 ? "s" : ""})
                      </span>
                    </td>
                    <td className="num py-1.5 pr-3 text-right">{r.periods}</td>
                    {/* Never coloured by sign. An information coefficient that
                        does not clear its own significance test is noise, and
                        painting noise green is how a reader learns to trust it. */}
                    <td className="num py-1.5 pr-3 text-right">
                      {num(r.ic, 3)}
                      <span className="ml-1.5 text-ash">q {num(r.icQ, 2)}</span>
                    </td>
                    <td className="num py-1.5 pr-3 text-right">{signedPct(r.spread)}</td>
                    <td className="num py-1.5 text-right text-ash">
                      {num(r.minimumDetectableIc, 3)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* The distinction the whole panel turns on. */}
        <p className="mt-3 text-[0.72rem] leading-relaxed text-ash">
          <span className="text-chalk/80">Rank vs return</span> is the correlation, within
          each period, between where a name ranked and what it did next; zero means the order
          carried no information. <span className="text-chalk/80">q</span> is the p-value after
          correcting for having run {data.tests} tests &mdash; running that many produces a
          winner by construction, and {num(data.expectedByChance ?? 0, 1)} of them are expected
          to clear the usual cutoff by chance alone.{" "}
          <span className="text-chalk/80">Smallest detectable</span> is the weakest relationship
          this sample could have found; a genuinely useful one in this field is nearer 0.03, so
          a blank result here means <em>too small to see</em> rather than <em>not there</em>.
        </p>

        {data.caveats && data.caveats.length > 0 && (
          <ul className="mt-3 space-y-1 border-t border-rule pt-3">
            {data.caveats.map((c) => (
              <li key={c} className="text-[0.7rem] leading-relaxed text-ash">&middot; {c}</li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
