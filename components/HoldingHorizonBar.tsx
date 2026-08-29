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
    <section className="animate-rise overflow-hidden rounded-xl border border-rule bg-panel">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-3 px-5 py-4">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <Clock aria-hidden className="h-4 w-4 shrink-0 text-tech" />
          {/* A real question at reading size. v1 asked it in 10.88px uppercase
              grey, which made the one control that changes what every number
              below means look like a table header. */}
          <h2 className="text-h3">If you held this for</h2>
          <HorizonPicker value={horizon} onChange={onHorizon} available={available} />
        </div>
        {explain && (
          <button
            type="button"
            aria-expanded={open}
            onClick={() => setOpen((v) => !v)}
            className="inline-flex h-8 items-center rounded-lg border border-rule px-3
                       text-meta font-medium text-ash transition-colors
                       hover:border-tech/50 hover:bg-tech/10 hover:text-tech
                       focus:outline-none focus-visible:ring-2 focus-visible:ring-tech"
          >
            {open ? "Less" : "What this means"}
          </button>
        )}
      </div>

      <div className="border-t border-rule px-5 py-5">
        {!data.hasLongTerm ? (
          <p className="prose-col text-base leading-relaxed text-ash">
            The chart range is too short for any holding-period history. Set it to 5y or
            longer and this becomes the strongest evidence on the page.
          </p>
        ) : !measured ? (
          <p className="prose-col text-base leading-relaxed text-ash">
            {row?.reason
              ?? `No ${horizon}-year holding periods in the loaded history.`}{" "}
            <span className="text-body">
              Nothing is known about {horizon}-year outcomes for this stock here — which is
              not the same as nothing having gone wrong over one.
            </span>
          </p>
        ) : (
          <>
            {/* THE WORST COLUMN LEADS, and it is the only one that takes a
                tone. It is the number position sizing has to survive; the
                median and the hit rate are context for it, so they are set at
                the same size but stay neutral. Ranking them by colour would be
                the app deciding which of three facts matters most, and here it
                genuinely does — Python said so, in `_rolling_worst`. */}
            <div className="grid gap-4 sm:grid-cols-3">
              <div className="rounded-lg border border-ruleSoft bg-sunken px-4 py-3.5">
                <div className="eyebrow mb-2">Worst any buyer did</div>
                <div className={cn("num text-figure font-semibold leading-none",
                                   explain ? TONE_TEXT[explain.tone] : "text-chalk")}>
                  {signedPct(row.worst)}
                </div>
                <div className="mt-2 text-micro text-ash">a year, at the unluckiest entry</div>
              </div>
              <div className="rounded-lg border border-ruleSoft bg-sunken px-4 py-3.5">
                <div className="eyebrow mb-2">Typical</div>
                <div className="num text-figure font-semibold leading-none text-chalk">
                  {signedPct(row.median)}
                </div>
                <div className="mt-2 text-micro text-ash">a year, middle of the range</div>
              </div>
              <div className="rounded-lg border border-ruleSoft bg-sunken px-4 py-3.5">
                <div className="eyebrow mb-2">Made money</div>
                <div className="num text-figure font-semibold leading-none text-chalk">
                  {pct(row.positiveShare, 0)}
                </div>
                <div className="mt-2 text-micro text-ash">
                  of {row.windows} overlapping periods
                </div>
              </div>
            </div>
            <p className="prose-col mt-4 text-meta leading-relaxed text-ash">
              Every {horizon}-year stretch in the loaded history, not the one that happened to
              start when the chart does. The worst column is the one that sets position size —
              a headline annual return quietly describes a single lucky start date.
            </p>
          </>
        )}

        {open && explain && (
          <div className="mt-4 rounded-lg border border-ruleSoft bg-sunken px-4 py-3.5">
            <ExplanationBody explain={explain} />
          </div>
        )}
      </div>
    </section>
  );
}
