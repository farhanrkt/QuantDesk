"use client";

import {
  createContext, useContext, useEffect, useId, useLayoutEffect, useRef, useState,
} from "react";
import { ArrowDown, ArrowUp, Info, X } from "lucide-react";
import type { Explanation, ExplainMap } from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * The plain-language layer, rendered.
 *
 * TONE IS THE ONLY COLOUR INPUT. Every component here reads `explain.tone` and
 * nothing else — never the sign or size of the underlying number. That is
 * deliberate and it is the fix for the whole class of bug where a 60% drawdown
 * renders green because 60 is a big number. Direction is decided once, in
 * `api/_lib/explain.py`, where a pytest suite asserts it; by the time a value
 * reaches this file the judgement has already been made and cannot be
 * re-litigated by accident.
 *
 * TWO AFFORDANCES, NOT ONE. `ExplainedStat` and `ExplainedRow` expand INLINE,
 * because they own their own block and a paragraph that pushes the layout down
 * can be read, selected and printed. `Explain` — the bare icon that sits inside
 * table cells and running prose, where there is no block to expand into — uses a
 * floating panel and pays for it with positioning logic (see its own comment).
 * Neither is a tooltip: these are paragraphs meant to be read.
 */

export const TONE_TEXT: Record<string, string> = {
  good: "text-acc",
  bad: "text-dist",
  warn: "text-warn",
  neutral: "text-chalk",
  none: "text-ash",
};

export const TONE_HEX: Record<string, string> = {
  good: "#35C4A8",
  bad: "#FF6B6B",
  warn: "#F2C14E",
  neutral: "#8496A9",
  none: "#8496A9",
};

/** Surfaces for a tone, used by chips and callouts. Never picked from a number. */
export const TONE_FIELD: Record<string, string> = {
  good: "border-acc/35 bg-acc/10 text-acc",
  bad: "border-dist/40 bg-dist/10 text-dist",
  warn: "border-warn/35 bg-warn/10 text-warn",
  neutral: "border-rule bg-raised text-chalk",
  none: "border-rule bg-raised text-ash",
};

const EVIDENCE_NOTE: Record<string, string> = {
  strong: "Well supported — decades of out-of-sample evidence across many markets.",
  moderate: "Reasonably supported, with caveats. Published and replicated, but not settled.",
  weak: "Weak evidence. Widely used, poorly supported once trading costs are counted.",
  none: "No evidence base. Descriptive only.",
};

const EVIDENCE_TONE: Record<string, string> = {
  strong: "text-acc",
  moderate: "text-ash",
  weak: "text-warn",
  none: "text-ash",
};

// --------------------------------------------------------------------------- //
// Guided / Full
// --------------------------------------------------------------------------- //
export type DetailLevel = "simple" | "detailed";

const DetailContext = createContext<DetailLevel>("simple");
export const useDetail = () => useContext(DetailContext);

const STORAGE_KEY = "quantdesk.detail";

/**
 * GUIDED is the default. The stored value is still "simple" / "detailed" —
 * renaming the label is a UI change, and rewriting what is already in people's
 * localStorage would silently reset every existing reader to the default.
 *
 * The two modes are not more-and-less of one thing. GUIDED walks a reader
 * through: the handful of numbers that decide a holding, their readings shown
 * rather than hidden behind an icon, and every expert control collapsed out of
 * the first screen. FULL is the app as it has always been — nothing moved,
 * nothing renamed, nothing added. That second promise is the load-bearing one:
 * a mode that "simplifies" by taking capability away from the people who came
 * for the capability is a mode they turn off once and never trust again.
 */
export function DetailProvider({
  level, children,
}: { level: DetailLevel; children: React.ReactNode }) {
  return <DetailContext.Provider value={level}>{children}</DetailContext.Provider>;
}

export function useDetailLevel(): [DetailLevel, (v: DetailLevel) => void] {
  const [level, setLevel] = useState<DetailLevel>("simple");
  // Read on mount rather than during render: the server renders this tree too,
  // and localStorage does not exist there. Hydrating from a value the server
  // could not have known would mismatch the markup.
  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(STORAGE_KEY);
      if (stored === "simple" || stored === "detailed") setLevel(stored);
    } catch { /* private mode or storage disabled — the default is fine */ }
  }, []);
  const update = (next: DetailLevel) => {
    setLevel(next);
    try { window.localStorage.setItem(STORAGE_KEY, next); } catch { /* ignore */ }
  };
  return [level, update];
}

/**
 * A two-option switch that behaves like one.
 *
 * v1 declared `role="radiogroup"` with `role="radio"` children and implemented
 * none of the keyboard contract that promises — a screen reader announced a
 * radio group, the reader pressed an arrow key, and nothing happened. Declaring
 * a pattern you have not built is worse than declaring nothing, so this now
 * carries the roving tabindex and arrow keys the role commits to.
 */
export function DetailToggle({
  level, onChange,
}: { level: DetailLevel; onChange: (v: DetailLevel) => void }) {
  const options = ["simple", "detailed"] as const;
  const move = (event: React.KeyboardEvent) => {
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) return;
    event.preventDefault();
    onChange(level === "simple" ? "detailed" : "simple");
  };
  return (
    <div role="radiogroup" aria-label="Reading mode"
         className="inline-flex rounded-lg border border-rule bg-raised p-1">
      {options.map((option) => (
        <button
          key={option}
          type="button"
          role="radio"
          aria-checked={level === option}
          // ONE TAB STOP for the whole group, which is what a radiogroup means.
          tabIndex={level === option ? 0 : -1}
          onKeyDown={move}
          onClick={() => onChange(option)}
          className={cn(
            "rounded px-3.5 py-1.5 text-meta font-medium transition-colors",
            "focus:outline-none focus-visible:ring-2 focus-visible:ring-tech",
            level === option
              ? "bg-tech/20 text-chalk shadow-sm"
              : "text-ash hover:text-chalk",
          )}
        >
          {option === "simple" ? "Guided" : "Full"}
        </button>
      ))}
    </div>
  );
}

// --------------------------------------------------------------------------- //
// The explanation itself
// --------------------------------------------------------------------------- //
function ArrowFor({ direction }: { direction: Explanation["goodDirection"] }) {
  if (direction === "none") return null;
  const Icon = direction === "high" ? ArrowUp : ArrowDown;
  return (
    <span className="inline-flex items-center gap-1 text-micro text-ash">
      <Icon aria-hidden className="h-3 w-3" />
      {direction === "high" ? "higher is better" : "lower is better"}
    </span>
  );
}

/**
 * The three questions, laid out.
 *
 * BUILT FROM SPANS, NOT DIVS AND PARAGRAPHS, and that is not a style choice.
 * This body renders inside `Explain`, which sits inline in table cells, list
 * terms and running prose — so its wrapper has to be a `<span>`, and a `<div>`
 * or `<p>` inside a `<span>` is invalid HTML. The browser silently reparents
 * it, which is how the popover ended up escaping its own positioning context.
 * `display: block` on a span gives identical layout and is legal anywhere.
 *
 * THE THREE LABELS ARE THE STRUCTURE. v1 set them as inline run-in eyebrows the
 * same size as the text they introduced, so the block read as one grey paragraph
 * with occasional capitals. Stacking them makes the shape of the answer visible
 * before any of it is read, and a reader who only wants the middle one can find
 * it.
 */
export function ExplanationBody({ explain }: { explain: Explanation }) {
  return (
    <span className="block space-y-3">
      <span className="block">
        <span className="eyebrow mb-1 block">What it is</span>
        <span className="block text-meta leading-relaxed text-body">{explain.what}</span>
      </span>
      <span className="block">
        <span className="eyebrow mb-1 block">This reading</span>
        <span className={cn("block text-meta font-medium leading-relaxed",
                            TONE_TEXT[explain.tone] ?? "text-chalk")}>
          {explain.reading}
        </span>
      </span>
      <span className="block">
        <span className="eyebrow mb-1 block">What to do</span>
        <span className="block text-meta leading-relaxed text-body">{explain.action}</span>
      </span>
      <span className="flex flex-wrap items-center gap-x-4 gap-y-1.5 border-t border-ruleSoft pt-2.5">
        <ArrowFor direction={explain.goodDirection} />
        {explain.evidence && (
          <span className={cn("text-micro", EVIDENCE_TONE[explain.evidence] ?? "text-ash")}>
            <span className="font-semibold uppercase tracking-wide">
              {explain.evidence} evidence
            </span>
            {" — "}
            <span className="text-ash">{EVIDENCE_NOTE[explain.evidence]}</span>
          </span>
        )}
      </span>
    </span>
  );
}

/**
 * The shared button. Every affordance in the app that opens prose is this one,
 * and there are dozens of them on a screen.
 *
 * IT IS 24x24, WHICH IS THE ENTIRE POINT OF THIS REVISION. v1 drew it at 14 or
 * 16px — an audit found 48 of 74 interactive elements on the Trend tab below
 * the WCAG 2.2 minimum, and this component was most of them. The app's central
 * promise is that every number explains itself; on a phone the affordance
 * carrying that promise was effectively unhittable.
 *
 * The RING is what grew, not the glyph: the icon stays small so a dense table
 * row still looks like a table row, while padding takes the hit area to 24.
 */
function InfoButton({
  label, open, onToggle, controls,
}: { label: string; open: boolean; onToggle: () => void; controls: string }) {
  return (
    <button
      type="button"
      aria-expanded={open}
      // ONLY WHILE THE PANEL EXISTS. Every one of these renders its explanation
      // conditionally, so a permanent `aria-controls` points at an id that is
      // not in the document — 25 of them were, across one screen. `aria-expanded`
      // is the attribute that carries the state; a reference to nothing is worse
      // than no reference, because assistive technology offers the reader a jump
      // that goes nowhere. Found by resolving every id rather than by reading
      // the markup.
      aria-controls={open ? controls : undefined}
      aria-label={open ? `Hide the explanation of ${label}` : `Explain ${label}`}
      onClick={onToggle}
      className={cn(
        "inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full",
        "border transition-colors",
        "focus:outline-none focus-visible:ring-2 focus-visible:ring-tech",
        open
          ? "border-tech/60 bg-tech/15 text-tech"
          : "border-rule text-faint hover:border-tech/50 hover:bg-tech/10 hover:text-tech",
      )}
    >
      <Info aria-hidden className="h-3.5 w-3.5" />
    </button>
  );
}

/**
 * An info affordance that opens its explanation in a small floating panel.
 *
 * THREE THINGS A POPOVER OWES THE READER, all of which the first version
 * skipped. It must not open off the side of the screen — pinned to `left-0` at
 * 320px wide, the rightmost column of the ranking table put its right edge at
 * 1391px on a 1400px viewport and past it on anything narrower, so on open it
 * measures itself and flips to right-aligned when it would overflow. Escape
 * must close it. And clicking anywhere else must close it, because a panel you
 * can only dismiss by finding the same tiny button again is a trap.
 *
 * IT IS NOT `role="tooltip"`, WHICH v1 CLAIMED. A tooltip is a short label
 * describing its trigger, announced through `aria-describedby` and never
 * interactive. This is three labelled paragraphs with a heading and a close
 * button, opened by a click, and a screen reader told it was a tooltip gets
 * neither the disclosure semantics nor a way in. A labelled group behind
 * `aria-expanded`/`aria-controls` describes what is actually here.
 */
export function Explain({ explain }: { explain?: Explanation }) {
  const [open, setOpen] = useState(false);
  const [flip, setFlip] = useState(false);
  const id = useId();
  const wrapper = useRef<HTMLSpanElement>(null);
  const panel = useRef<HTMLSpanElement>(null);

  // Measure BEFORE paint so the reader never sees it in the wrong place.
  useLayoutEffect(() => {
    if (!open || !panel.current) return;
    const box = panel.current.getBoundingClientRect();
    setFlip(box.right > window.innerWidth - 8);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    const onDown = (event: MouseEvent) => {
      if (!wrapper.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDown);
    };
  }, [open]);

  if (!explain) return null;
  return (
    <span ref={wrapper} className="relative inline-flex align-middle">
      <InfoButton label={explain.label} open={open} controls={id}
                  onToggle={() => { setFlip(false); setOpen((v) => !v); }} />
      {open && (
        <span
          ref={panel}
          id={id}
          role="group"
          aria-label={explain.label}
          className={cn(
            "absolute top-7 z-30 block rounded-lg border border-rule bg-raised",
            "px-4 py-3.5 shadow-pop",
            "w-[min(22rem,calc(100vw-2rem))]",
            flip ? "right-0" : "left-0",
          )}
        >
          <span className="mb-2.5 flex items-start justify-between gap-3 border-b border-ruleSoft pb-2">
            <span className="block text-meta font-semibold text-chalk">{explain.label}</span>
            <button type="button" onClick={() => setOpen(false)}
                    aria-label={`Close the explanation of ${explain.label}`}
                    className="-mr-1 -mt-0.5 inline-flex h-6 w-6 shrink-0 items-center
                               justify-center rounded text-faint transition-colors
                               hover:bg-rule/60 hover:text-chalk focus:outline-none
                               focus-visible:ring-2 focus-visible:ring-tech">
              <X aria-hidden className="h-3.5 w-3.5" />
            </button>
          </span>
          <ExplanationBody explain={explain} />
        </span>
      )}
    </span>
  );
}

/**
 * A number with its explanation attached — the unit Job 1 is really about.
 *
 * `value` is optional: when omitted it falls back to `explain.valueText`, the
 * string the interpreter itself quoted inside its reading. Letting the server
 * decide the formatting is what keeps the sentence "Fell 33%" beside a figure
 * that also says 33% rather than 33.4%.
 */
export function ExplainedStat({
  label, value, sub, explain, tone,
}: {
  label?: string;
  value?: React.ReactNode;
  sub?: string;
  explain?: Explanation;
  /** Override the colour. Only for figures with no explanation to speak for them. */
  tone?: string;
}) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const guided = useDetail() === "simple";
  if (!explain && value === undefined) return null;
  const shown = value ?? explain?.valueText ?? "—";
  const colour = tone ?? (explain ? TONE_TEXT[explain.tone] : undefined) ?? "text-chalk";
  return (
    <div className={cn("rounded-lg border bg-panel px-4 py-3.5 transition-colors",
                       explain ? TONE_BORDER_SOFT[explain.tone] ?? "border-rule" : "border-rule")}>
      <div className="mb-2 flex items-start justify-between gap-2">
        <span className="eyebrow pt-0.5">{label ?? explain?.label ?? ""}</span>
        {explain && (
          <InfoButton label={explain.label} open={open} controls={id}
                      onToggle={() => setOpen((v) => !v)} />
        )}
      </div>
      <div className={cn("num text-figure font-semibold leading-none", colour)}>{shown}</div>
      {sub && <div className="mt-2 text-micro leading-snug text-ash">{sub}</div>}
      {/* GUIDED: show the interpretation of THIS value without a click. It is
          the `reading` line only — the full three-part explanation stays behind
          the icon, so the affordance still has a job and the card does not
          become a wall. A reader who never discovers the icon has still been
          told whether the number in front of them is good or bad. */}
      {!open && guided && explain && explain.tone !== "none" && (
        <div className={cn("mt-2.5 border-t border-ruleSoft pt-2.5 text-meta leading-relaxed",
                           TONE_TEXT[explain.tone] ?? "text-chalk")}>
          {explain.reading}
        </div>
      )}
      {open && explain && (
        <div id={id} className="mt-3 border-t border-rule pt-3">
          <ExplanationBody explain={explain} />
        </div>
      )}
    </div>
  );
}

/** Tone as a whisper on a border — enough to group, never enough to shout. */
const TONE_BORDER_SOFT: Record<string, string> = {
  good: "border-acc/25",
  bad: "border-dist/30",
  warn: "border-warn/25",
  neutral: "border-rule",
  none: "border-rule",
};

/** A label-and-value row with the same affordance, for two-column lists. */
export function ExplainedRow({
  label, value, explain, tone,
}: { label?: string; value?: React.ReactNode; explain?: Explanation; tone?: string }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  if (!explain && value === undefined) return null;
  const shown = value ?? explain?.valueText ?? "—";
  const colour = tone ?? (explain ? TONE_TEXT[explain.tone] : undefined) ?? "text-chalk";
  return (
    <div className="border-b border-ruleSoft py-2 last:border-0">
      <div className="flex items-center justify-between gap-3">
        <span className="flex min-w-0 items-center gap-2 text-meta text-ash">
          <span className="truncate">{label ?? explain?.label}</span>
          {explain && (
            <InfoButton label={explain.label} open={open} controls={id}
                        onToggle={() => setOpen((v) => !v)} />
          )}
        </span>
        <span className={cn("num shrink-0 text-meta font-semibold", colour)}>{shown}</span>
      </div>
      {open && explain && (
        <div id={id} className="mt-2.5 rounded border border-ruleSoft bg-sunken px-3.5 py-3">
          <ExplanationBody explain={explain} />
        </div>
      )}
    </div>
  );
}

/** Convenience: pull one key out of a lens's explain map. */
export const pick = (map: ExplainMap | undefined, key: string): Explanation | undefined =>
  map?.[key];
