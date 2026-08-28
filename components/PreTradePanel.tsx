"use client";

import { useState } from "react";
import { AlertTriangle, CircleSlash, HelpCircle, Layers } from "lucide-react";
import type { PreTrade, PreTradeCheck } from "@/lib/types";
import { ExplanationBody, TONE_HEX, TONE_TEXT, useDetail } from "@/components/ui/explain";
import { cn } from "@/lib/utils";

/**
 * What would give a careful buyer pause.
 *
 * THIS PANEL IS DESIGNED AGAINST ONE FAILURE, and every decision here follows
 * from it: a checklist that renders clean as a row of green ticks has made the
 * app MORE authoritative than its evidence supports. The reader sees nothing
 * found, concludes nothing is there, and the app has quietly asserted something
 * it never tested.
 *
 * So there is no pass state to render. A condition either fired or it is absent
 * from the page, and the empty case is a PARAGRAPH rather than a tick — the one
 * state where the panel has to work hardest is the one where it has nothing to
 * show. Nothing in this file is ever green: the only tones it can receive are
 * `warn`, `bad` and `neutral`, and `tests/test_pretrade.py` asserts that on the
 * server side so it cannot arrive here wrong.
 *
 * NO COUNT IS RENDERED ANYWHERE. Not in the header, not as a badge, not as
 * "3 conditions". Three flags on one company and two on another are not
 * comparable quantities — that is exactly what the per-line firing rate exists
 * to say — and a tally in the header would be read as a score whether or not it
 * was meant as one. `notChecked` is collapsed behind a disclosure that names the
 * conditions rather than counting them, for the same reason.
 *
 * THE ORDER IS THE ARGUMENT. Flags, then the conditions that are ordinary for
 * this market, then what was never tested, then the sentence saying an empty
 * panel is not a clean bill of health. A reader who stops early has still read
 * the strongest claim; a reader who reaches the end cannot have missed the
 * caveat that governs all of it.
 */

const PRETRADE = "#F2A25C";

function Rate({ check }: { check: PreTradeCheck }) {
  return (
    <span className="num shrink-0 text-[0.62rem] text-ash" title={check.rateSentence}>
      fires on {check.firingRateText}
    </span>
  );
}

function Check({ check }: { check: PreTradeCheck }) {
  const [open, setOpen] = useState(false);
  const base = check.classification === "base";
  // Colour comes from `explain.tone` and nothing else — the same rule as every
  // other panel. A base condition arrives already neutral, decided in Python,
  // so this file never has to know that a common condition should be uncoloured.
  const colour = TONE_TEXT[check.explain.tone] ?? "text-chalk";

  return (
    <li className="border-b border-rule/60 px-5 py-3 last:border-0">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className={cn("text-sm font-semibold", colour)}>{check.explain.label}</span>
        {check.explain.valueText && (
          <span className={cn("num text-sm", colour)}>{check.explain.valueText}</span>
        )}
        <span className="ml-auto flex items-center gap-3">
          <Rate check={check} />
          <button
            type="button"
            aria-expanded={open}
            onClick={() => setOpen((v) => !v)}
            className="eyebrow text-ash transition-colors hover:text-chalk focus:outline-none
                       focus-visible:ring-1 focus-visible:ring-tech"
          >
            {open ? "Less" : "Why"}
          </button>
        </span>
      </div>

      <p className={cn("mt-1 text-[0.82rem] leading-relaxed",
                       base ? "text-ash" : "text-chalk/80")}>
        {check.explain.reading}
      </p>

      <p className="mt-1.5 text-[0.68rem] leading-relaxed text-ash">
        {check.rateSentence} <span className="text-chalk/60">Look at: {check.where}.</span>
      </p>

      {open && (
        <div className="mt-3 rounded border border-rule bg-ink/40 px-3 py-2">
          <ExplanationBody explain={check.explain} />
        </div>
      )}
    </li>
  );
}

function Section({
  icon: Icon, title, note, tone, children,
}: {
  icon: typeof Layers; title: string; note?: string; tone?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="border-t border-rule">
      <div className="flex items-center gap-2 px-5 pb-1 pt-4">
        <Icon aria-hidden className="h-3.5 w-3.5"
              style={{ color: tone ? TONE_HEX[tone] : "#7A8CA0" }} />
        <span className="eyebrow">{title}</span>
      </div>
      {note && <p className="px-5 pb-2 text-[0.7rem] leading-relaxed text-ash">{note}</p>}
      {children}
    </div>
  );
}

export function PreTradePanel({ data }: { data: PreTrade }) {
  const guided = useDetail() === "simple";
  const { flags, baseConditions, notChecked, uncalibrated } = data;

  return (
    <section className="animate-rise rounded border border-rule bg-panel">
      <div className="flex flex-wrap items-baseline justify-between gap-3 border-l-2 px-5 py-3"
           style={{ borderLeftColor: PRETRADE }}>
        <h2 className="eyebrow">{data.headline}</h2>
        {/* No universe named up here on purpose. Each line is scored against
            the universes for its own market, so a single label in the header
            would contradict half the lines beneath it. */}
        {data.calibration?.measuredOn && (
          <span className="num text-[0.62rem] text-ash">
            rates measured {data.calibration.measuredOn}
          </span>
        )}
      </div>

      <p className="border-t border-rule px-5 py-3 text-sm leading-relaxed text-chalk/85">
        {data.framing}
      </p>

      {flags.length > 0 && (
        <Section icon={AlertTriangle} title="Conditions that fired" tone="warn">
          <ul>{flags.map((c) => <Check key={c.id} check={c} />)}</ul>
        </Section>
      )}

      {baseConditions.length > 0 && (
        <Section
          icon={Layers}
          title="True here, and ordinary for this market"
          note={data.notes.base}
        >
          <ul>{baseConditions.map((c) => <Check key={c.id} check={c} />)}</ul>
        </Section>
      )}

      {/* NOT TESTED IS NOT CLEAR, and this section exists so the difference is
          impossible to miss. In Guided it is open, because a beginner is exactly
          who would otherwise read silence as a pass. */}
      {notChecked.length > 0 && (
        <Section
          icon={CircleSlash}
          title="Not checked"
          note={data.notes.notChecked}
        >
          <ul className="px-5 pb-1">
            {(guided ? notChecked : notChecked.slice(0, 3)).map((entry) => (
              <li key={entry.id} className="border-b border-rule/40 py-2 last:border-0">
                <span className="text-[0.8rem] text-chalk/75">{entry.label}. </span>
                <span className="text-[0.8rem] leading-relaxed text-ash">{entry.reason.replace(/\.$/, "")}.</span>
              </li>
            ))}
          </ul>
          {!guided && notChecked.length > 3 && (
            <details className="px-5 pb-3">
              <summary className="eyebrow cursor-pointer list-none text-ash hover:text-chalk">
                The rest
              </summary>
              <ul className="mt-2">
                {notChecked.slice(3).map((entry) => (
                  <li key={entry.id} className="border-b border-rule/40 py-2 last:border-0">
                    <span className="text-[0.8rem] text-chalk/75">{entry.label}. </span>
                    <span className="text-[0.8rem] leading-relaxed text-ash">
                      {entry.reason.replace(/\.$/, "")}.
                    </span>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </Section>
      )}

      {uncalibrated.length > 0 && (
        <Section icon={HelpCircle} title="Withheld for want of a base rate"
                 note={data.notes.uncalibrated}>
          <p className="px-5 pb-2 text-[0.75rem] leading-relaxed text-ash">
            {uncalibrated.map((u) => u.label).join(". ")}.
          </p>
        </Section>
      )}

      <p className="border-t border-rule px-5 py-3 text-[0.7rem] leading-relaxed text-ash">
        {data.caveat}
        {data.measuredOn && <> {data.measuredOn}</>}
      </p>
    </section>
  );
}
