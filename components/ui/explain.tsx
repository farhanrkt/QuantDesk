"use client";

import {
  createContext, useContext, useEffect, useId, useLayoutEffect, useRef, useState,
} from "react";
import { ArrowDown, ArrowUp, Info } from "lucide-react";
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
  neutral: "#7A8CA0",
  none: "#7A8CA0",
};

const EVIDENCE_NOTE: Record<string, string> = {
  strong: "Well supported — decades of out-of-sample evidence across many markets.",
  moderate: "Reasonably supported, with caveats. Published and replicated, but not settled.",
  weak: "Weak evidence. Widely used, poorly supported once trading costs are counted.",
  none: "No evidence base. Descriptive only.",
};

const EVIDENCE_TONE: Record<string, string> = {
  strong: "text-acc/80",
  moderate: "text-ash",
  weak: "text-warn/90",
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
 *
 * The choice persists because a reader who wants one of them wants it every
 * time, and re-picking it on each load is its own small insult.
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

export function DetailToggle({
  level, onChange,
}: { level: DetailLevel; onChange: (v: DetailLevel) => void }) {
  return (
    <div role="radiogroup" aria-label="Reading mode"
         className="inline-flex rounded border border-rule bg-raised p-0.5">
      {(["simple", "detailed"] as const).map((option) => (
        <button
          key={option}
          type="button"
          role="radio"
          aria-checked={level === option}
          onClick={() => onChange(option)}
          className={cn(
            "rounded px-3 py-1 font-mono text-[0.65rem] uppercase tracking-[0.12em]",
            "transition-colors focus:outline-none focus-visible:ring-1 focus-visible:ring-tech",
            level === option ? "bg-tech/20 text-chalk" : "text-ash hover:text-chalk",
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
    <span className="inline-flex items-center gap-1 text-[0.6rem] text-ash">
      <Icon aria-hidden className="h-2.5 w-2.5" />
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
 */
export function ExplanationBody({ explain }: { explain: Explanation }) {
  return (
    <span className="block space-y-2 text-[0.72rem] leading-relaxed">
      <span className="block text-ash">
        <span className="eyebrow mr-1.5">What it is</span>
        {explain.what}
      </span>
      <span className={cn("block", TONE_TEXT[explain.tone] ?? "text-chalk", "opacity-95")}>
        <span className="eyebrow mr-1.5 text-ash">This reading</span>
        {explain.reading}
      </span>
      <span className="block text-chalk/70">
        <span className="eyebrow mr-1.5 text-ash">What to do</span>
        {explain.action}
      </span>
      <span className="flex flex-wrap items-center gap-x-4 gap-y-1 pt-0.5">
        <ArrowFor direction={explain.goodDirection} />
        {explain.evidence && (
          <span className={cn("text-[0.6rem]", EVIDENCE_TONE[explain.evidence] ?? "text-ash")}>
            Evidence: {explain.evidence} — {EVIDENCE_NOTE[explain.evidence]}
          </span>
        )}
      </span>
    </span>
  );
}

/** The shared button. Every affordance in the app that opens prose is this one. */
function InfoButton({
  label, open, onToggle, controls, small,
}: {
  label: string; open: boolean; onToggle: () => void; controls: string; small?: boolean;
}) {
  return (
    <button
      type="button"
      aria-expanded={open}
      aria-controls={controls}
      aria-label={`Explain ${label}`}
      onClick={onToggle}
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-full border border-rule",
        "text-ash transition-colors hover:border-tech/60 hover:text-tech",
        "focus:outline-none focus-visible:ring-1 focus-visible:ring-tech",
        small ? "h-3.5 w-3.5" : "h-4 w-4",
        open && "border-tech/60 text-tech",
      )}
    >
      <Info aria-hidden className={small ? "h-2 w-2" : "h-2.5 w-2.5"} />
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
    <span ref={wrapper} className="relative inline-flex">
      <InfoButton label={explain.label} open={open} controls={id} small
                  onToggle={() => { setFlip(false); setOpen((v) => !v); }} />
      {open && (
        <span
          ref={panel}
          id={id}
          role="tooltip"
          className={cn(
            "absolute top-5 z-30 block rounded border border-rule bg-ink/95 px-3 py-2 shadow-xl",
            "w-[min(20rem,calc(100vw-2rem))]",
            flip ? "right-0" : "left-0",
          )}
        >
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
    <div className="rounded border border-rule bg-panel px-4 py-3">
      <div className="mb-1 flex items-start justify-between gap-2">
        <span className="eyebrow">{label ?? explain?.label ?? ""}</span>
        {explain && (
          <InfoButton label={explain.label} open={open} controls={id}
                      onToggle={() => setOpen((v) => !v)} />
        )}
      </div>
      <div className={cn("num text-lg font-semibold leading-tight", colour)}>{shown}</div>
      {sub && <div className="mt-0.5 text-[0.7rem] leading-snug text-ash">{sub}</div>}
      {/* GUIDED: show the interpretation of THIS value without a click. It is
          the `reading` line only — the full three-part explanation stays behind
          the icon, so the affordance still has a job and the card does not
          become a wall. A reader who never discovers the icon has still been
          told whether the number in front of them is good or bad. */}
      {!open && guided && explain && explain.tone !== "none" && (
        <div className={cn("mt-1.5 text-[0.72rem] leading-relaxed",
                           TONE_TEXT[explain.tone] ?? "text-chalk", "opacity-90")}>
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
    <div className="border-b border-rule/40 pb-1.5 last:border-0">
      <div className="flex items-baseline justify-between gap-3">
        <span className="flex items-center gap-1.5 text-ash">
          {label ?? explain?.label}
          {explain && (
            <InfoButton label={explain.label} open={open} controls={id} small
                        onToggle={() => setOpen((v) => !v)} />
          )}
        </span>
        <span className={cn("num font-semibold", colour)}>{shown}</span>
      </div>
      {open && explain && (
        <div id={id} className="mt-2 rounded border border-rule bg-ink/40 px-3 py-2">
          <ExplanationBody explain={explain} />
        </div>
      )}
    </div>
  );
}

/** Convenience: pull one key out of a lens's explain map. */
export const pick = (map: ExplainMap | undefined, key: string): Explanation | undefined =>
  map?.[key];
