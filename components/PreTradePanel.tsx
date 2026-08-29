"use client";

import { useState } from "react";
import { AlertTriangle, ChevronRight, CircleSlash, HelpCircle, Layers } from "lucide-react";
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
 *
 * WHAT v2 CHANGED. The firing rate — the number this whole feature exists to
 * deliver — rendered at 0.62rem in the dimmest grey on the page, smaller than
 * the condition it qualified. It is now a bordered pill at the same weight as
 * the reading, because "Altman says distress" and "so does 31% of this market"
 * are one thought and one of them was whispered. The four sections also gained
 * distinct surfaces: fired conditions sit on the panel, ordinary ones are
 * recessed, and not-checked is quieter still, so the three read as three
 * different kinds of statement before a word of them is read.
 */

const PRETRADE = "#F2A25C";

/**
 * The base rate, given the weight of the claim it qualifies.
 *
 * A condition true of a third of the market describes the market, not this
 * company, and this number is the only thing that lets a reader tell those
 * apart. v1 set it at 0.62rem `text-ash` — the smallest, dimmest text in the
 * row — beside a 14px semibold condition name. The prominence was exactly
 * backwards.
 */
function Rate({ check }: { check: PreTradeCheck }) {
  return (
    <span
      className="num shrink-0 rounded-full border border-rule bg-sunken px-2.5 py-1
                 text-micro font-medium text-ash"
      title={check.rateSentence}
    >
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
    <li className="border-b border-ruleSoft px-5 py-4 last:border-0">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <span className={cn("text-lead font-semibold", colour)}>{check.explain.label}</span>
        {check.explain.valueText && (
          <span className={cn("num text-lead", colour)}>{check.explain.valueText}</span>
        )}
        <span className="ml-auto flex items-center gap-2.5">
          <Rate check={check} />
          <button
            type="button"
            aria-expanded={open}
            aria-label={open
              ? `Hide the detail behind ${check.explain.label}`
              : `Why ${check.explain.label} matters`}
            onClick={() => setOpen((v) => !v)}
            className="inline-flex h-6 items-center gap-1 rounded border border-rule px-2
                       text-micro font-medium text-ash transition-colors
                       hover:border-tech/50 hover:bg-tech/10 hover:text-tech
                       focus:outline-none focus-visible:ring-2 focus-visible:ring-tech"
          >
            {open ? "Less" : "Why"}
          </button>
        </span>
      </div>

      <p className={cn("prose-col mt-2 text-base leading-relaxed",
                       base ? "text-ash" : "text-body")}>
        {check.explain.reading}
      </p>

      <p className="prose-col mt-2 text-meta leading-relaxed text-faint">
        {check.rateSentence}{" "}
        <span className="text-ash">Look at: {check.where}.</span>
      </p>

      {open && (
        <div className="mt-3 rounded-lg border border-ruleSoft bg-sunken px-4 py-3.5">
          <ExplanationBody explain={check.explain} />
        </div>
      )}
    </li>
  );
}

/**
 * `weight` is what makes four sections read as four KINDS of statement rather
 * than as one list with headings in it. Fired conditions sit on the panel;
 * everything the app is qualifying or admitting is recessed.
 */
function Group({
  icon: Icon, title, note, tone, weight = "finding", children,
}: {
  icon: typeof Layers;
  title: string;
  note?: string;
  tone?: string;
  weight?: "finding" | "quiet";
  children: React.ReactNode;
}) {
  return (
    <div className={cn("border-t border-rule", weight === "quiet" && "bg-sunken/40")}>
      <div className="flex items-center gap-2.5 px-5 pb-1.5 pt-4">
        <Icon aria-hidden className="h-4 w-4 shrink-0"
              style={{ color: tone ? TONE_HEX[tone] : "#8496A9" }} />
        <h3 className={cn("text-meta font-semibold uppercase tracking-wider",
                          weight === "quiet" ? "text-ash" : "text-chalk")}>
          {title}
        </h3>
      </div>
      {note && <p className="prose-col px-5 pb-2 text-meta leading-relaxed text-ash">{note}</p>}
      {children}
    </div>
  );
}

const NotCheckedRow = ({ label, reason }: { label: string; reason: string }) => (
  <li className="border-b border-ruleSoft py-2.5 last:border-0">
    <span className="text-meta font-medium text-body">{label}. </span>
    <span className="text-meta leading-relaxed text-ash">{reason.replace(/\.$/, "")}.</span>
  </li>
);

export function PreTradePanel({ data }: { data: PreTrade }) {
  const guided = useDetail() === "simple";
  const { flags, baseConditions, notChecked, uncalibrated } = data;

  return (
    <section className="animate-rise overflow-hidden rounded-xl border border-rule bg-panel">
      <div className="px-5 pb-4 pt-5" style={{ background: `${PRETRADE}0F` }}>
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <h2 style={{ color: PRETRADE }}>{data.headline}</h2>
          {/* No universe named up here on purpose. Each line is scored against
              the universes for its own market, so a single label in the header
              would contradict half the lines beneath it. */}
          {data.calibration?.measuredOn && (
            <span className="num text-micro text-ash">
              rates measured {data.calibration.measuredOn}
            </span>
          )}
        </div>
        <p className="prose-col mt-2 text-base leading-relaxed text-body">{data.framing}</p>
      </div>

      {flags.length > 0 && (
        <Group icon={AlertTriangle} title="Conditions that fired" tone="warn">
          <ul>{flags.map((c) => <Check key={c.id} check={c} />)}</ul>
        </Group>
      )}

      {baseConditions.length > 0 && (
        <Group icon={Layers} title="True here, and ordinary for this market"
               note={data.notes.base} weight="quiet">
          <ul>{baseConditions.map((c) => <Check key={c.id} check={c} />)}</ul>
        </Group>
      )}

      {/* NOT TESTED IS NOT CLEAR, and this section exists so the difference is
          impossible to miss. In Guided it is open, because a beginner is exactly
          who would otherwise read silence as a pass. */}
      {notChecked.length > 0 && (
        <Group icon={CircleSlash} title="Not checked" note={data.notes.notChecked}
               weight="quiet">
          <ul className="px-5 pb-2">
            {(guided ? notChecked : notChecked.slice(0, 3)).map((entry) => (
              <NotCheckedRow key={entry.id} label={entry.label} reason={entry.reason} />
            ))}
          </ul>
          {!guided && notChecked.length > 3 && (
            <details className="group px-5 pb-3">
              <summary className="flex cursor-pointer list-none items-center gap-2 py-1
                                  text-meta text-ash transition-colors hover:text-chalk
                                  focus-visible:outline-none focus-visible:ring-2
                                  focus-visible:ring-tech">
                <ChevronRight aria-hidden
                              className="h-4 w-4 shrink-0 transition-transform group-open:rotate-90" />
                The rest
              </summary>
              <ul className="mt-1 pl-6">
                {notChecked.slice(3).map((entry) => (
                  <NotCheckedRow key={entry.id} label={entry.label} reason={entry.reason} />
                ))}
              </ul>
            </details>
          )}
        </Group>
      )}

      {uncalibrated.length > 0 && (
        <Group icon={HelpCircle} title="Withheld for want of a base rate"
               note={data.notes.uncalibrated} weight="quiet">
          <p className="prose-col px-5 pb-3 text-meta leading-relaxed text-ash">
            {uncalibrated.map((u) => u.label).join(". ")}.
          </p>
        </Group>
      )}

      <p className="prose-col border-t border-rule px-5 py-4 text-meta leading-relaxed text-faint">
        {data.caveat}
        {data.measuredOn && <> {data.measuredOn}</>}
      </p>
    </section>
  );
}
