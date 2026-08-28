"use client";

import { Clock } from "lucide-react";
import { HorizonPicker, type Horizon } from "@/components/ui/horizon";
import { ExplanationBody, TONE_TEXT } from "@/components/ui/explain";
import { useState } from "react";
import type { Engine, TechnicalResponse } from "@/lib/types";
import { cn, pct, signedPct } from "@/lib/utils";

/**
 * What holders of this actually got, over the length the reader intends to hold.
 *
 * WHY IT IS ABOVE THE TABS AND NOT INSIDE THE TREND LENS. The rolling-return
 * distribution is the strongest evidence in this app — it replaces "it returned
 * 16% a year", which describes one start date, with what EVERY start date got —
 * and it sat behind a tab, a section and a fixed 1/3/5-year table nobody chose.
 * The worst outcome at a stated horizon is a fact the data fully supports, and
 * it belongs where a decision gets made rather than three clicks away.
 *
 * IT IS A FRAME, NOT A VERDICT, which is why it sits above the synthesis rather
 * than beside the pre-trade panel. It says what this length of ownership has
 * historically been like; the synthesis then describes what the lenses report,
 * and the pre-trade panel then names what argues against acting. Nothing here
 * is a forecast: it is the historical distribution, and the worst entry in it
 * is the number position sizing exists to survive.
 *
 * COLOUR COMES FROM `explain`, as everywhere. The panel never decides that a
 * negative worst-case is bad news; `_rolling_worst` in Python did, with a test.
 */
export function HoldingHorizonBar({
  state, horizon, onHorizon,
}: {
  state: Engine<TechnicalResponse>;
  horizon: Horizon;
  onHorizon: (h: Horizon) => void;
}) {
  const [open, setOpen] = useState(false);
  if (state.status !== "ready") return null;

  const data = state.data;
  const rows = data.longTerm?.rollingReturns ?? [];
  const row = rows.find((r) => r.years === horizon);
  const available = rows.filter((r) => r.usable !== false && r.worst != null)
                        .map((r) => r.years);
  const explain = data.longTerm?.explain?.[`rollingWorst.${horizon}`];
  const measured = row && row.usable !== false && row.worst != null;

  return (
    <section className="animate-rise rounded border border-rule bg-panel">
      <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-3">
        <div className="flex items-center gap-2">
          <Clock aria-hidden className="h-3.5 w-3.5 text-ash" />
          <span className="eyebrow">If you held this for</span>
          <HorizonPicker value={horizon} onChange={onHorizon} available={available} />
        </div>
        {explain && (
          <button
            type="button"
            aria-expanded={open}
            onClick={() => setOpen((v) => !v)}
            className="eyebrow text-ash transition-colors hover:text-chalk focus:outline-none
                       focus-visible:ring-1 focus-visible:ring-tech"
          >
            {open ? "Less" : "What this means"}
          </button>
        )}
      </div>

      <div className="border-t border-rule px-5 py-4">
        {!data.hasLongTerm ? (
          <p className="text-[0.82rem] leading-relaxed text-ash">
            The chart range is too short for any holding-period history. Set it to 5y or
            longer and this becomes the strongest evidence on the page.
          </p>
        ) : !measured ? (
          <p className="text-[0.82rem] leading-relaxed text-ash">
            {row?.reason
              ?? `No ${horizon}-year holding periods in the loaded history.`}{" "}
            <span className="text-chalk/70">
              Nothing is known about {horizon}-year outcomes for this stock here — which is
              not the same as nothing having gone wrong over one.
            </span>
          </p>
        ) : (
          <>
            <div className="grid grid-cols-3 gap-4">
              <div>
                <div className="eyebrow mb-0.5">Worst any buyer did</div>
                <div className={cn("num text-xl font-semibold",
                                   explain ? TONE_TEXT[explain.tone] : "text-chalk")}>
                  {signedPct(row.worst)}
                </div>
                <div className="text-[0.65rem] text-ash">a year, at the unluckiest entry</div>
              </div>
              <div>
                <div className="eyebrow mb-0.5">Typical</div>
                <div className="num text-xl font-semibold text-chalk">
                  {signedPct(row.median)}
                </div>
                <div className="text-[0.65rem] text-ash">a year, middle of the range</div>
              </div>
              <div>
                <div className="eyebrow mb-0.5">Made money</div>
                <div className="num text-xl font-semibold text-chalk">
                  {pct(row.positiveShare, 0)}
                </div>
                <div className="text-[0.65rem] text-ash">
                  of {row.windows} overlapping periods
                </div>
              </div>
            </div>
            <p className="mt-3 text-[0.72rem] leading-relaxed text-ash">
              Every {horizon}-year stretch in the loaded history, not the one that happened to
              start when the chart does. The worst column is the one that sets position size —
              a headline annual return quietly describes a single lucky start date.
            </p>
          </>
        )}

        {open && explain && (
          <div className="mt-3 border-t border-rule pt-3">
            <ExplanationBody explain={explain} />
          </div>
        )}
      </div>
    </section>
  );
}
