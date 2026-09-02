import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Surfaces, and the reason there are now three of them.
 *
 * v1 had exactly one: a rounded rect with a `rule` border on `panel`. One
 * screen carried SEVENTY-ONE of them, identical, so the container told the
 * reader nothing — it marked where a box started and not what kind of thing was
 * inside. Chunking that does not differentiate is just more edges to scan past.
 *
 * Three strata, each earning its use:
 *
 *   panel   the standard surface. A finding, a table, a chart.
 *   sunken  a well INSIDE a panel. Quoted figures, working, raw data. Reads as
 *           recessed, so a table nested in a card no longer looks like a second
 *           card sitting on the first.
 *   raised  something floating above the page. Controls, popovers.
 *
 * `tone` tints the border and adds a wash when the SERVER has judged the
 * contents — never when a component decides a number looks bad. `hue` is a lens
 * identity colour and is deliberately separate: a lens is its colour whether its
 * reading is good or catastrophic.
 */

export type Surface = "panel" | "sunken" | "raised";

const SURFACE: Record<Surface, string> = {
  panel: "bg-panel border-rule",
  sunken: "bg-sunken border-ruleSoft",
  raised: "bg-raised border-rule shadow-lift",
};

export const TONE_BORDER: Record<string, string> = {
  good: "border-acc/35",
  bad: "border-dist/40",
  warn: "border-warn/35",
  neutral: "border-rule",
  none: "border-rule",
};

export function Card({
  accent, surface = "panel", tone, className, children,
}: {
  /** A lens identity hex. Tints the header field, never the whole card. */
  accent?: string;
  surface?: Surface;
  /** `explain.tone`. The only thing allowed to colour a card by judgement. */
  tone?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn("relative rounded-lg border", SURFACE[surface],
                    tone && TONE_BORDER[tone], className)}
      style={accent ? ({ "--hue": accent } as React.CSSProperties) : undefined}
    >
      {children}
    </div>
  );
}

/**
 * The header is where a lens's colour lives — as a FIELD, not a stripe.
 *
 * v1 signalled identity with a 2px bar along the top edge, which is the
 * thinnest possible commitment to a colour and reads as trim. A tinted band
 * behind the title, with the title itself in the hue, gives the same
 * information at a glance without a heavy rule doing it.
 */
export function CardHeader({
  className, hue, children,
}: { className?: string; hue?: string; children: React.ReactNode }) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-center justify-between gap-x-4 gap-y-2",
        "rounded-t-lg border-b border-rule px-5 py-3.5",
        className,
      )}
      style={hue ? { background: `${hue}12`, borderBottomColor: `${hue}33` } : undefined}
    >
      {children}
    </div>
  );
}

/** A real heading. `h3` by default, because a card sits inside a section. */
export function CardTitle({
  as: Tag = "h3", hue, className, children,
}: {
  as?: "h2" | "h3" | "h4";
  hue?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <Tag className={cn("text-h3 font-semibold tracking-tight", className)}
         style={hue ? { color: hue } : undefined}>
      {children}
    </Tag>
  );
}

/** Tables pass `px-0` so their rows can run the full width of the panel. */
export function CardBody({ className, children }: { className?: string; children: React.ReactNode }) {
  return <div className={cn("px-5 py-4", className)}>{children}</div>;
}

/**
 * A page-level region: a real `h2`, an optional one-line answer to "why am I
 * looking at this", and the content.
 *
 * The subtitle is not decoration. This app's whole difficulty for a newcomer is
 * that it answers questions nobody told them were being asked, and a section
 * that names its question in plain words costs one line and saves a paragraph.
 */
export function Section({
  title, question, aside, className, children,
}: {
  title: string;
  question?: string;
  aside?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <section className={cn("animate-rise", className)}>
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <div className="min-w-0">
          <h2>{title}</h2>
          {question && <p className="mt-1 max-w-measure text-meta text-ash">{question}</p>}
        </div>
        {aside && <div className="shrink-0">{aside}</div>}
      </div>
      {children}
    </section>
  );
}

/**
 * A figure with its label. `tone` comes from the server or not at all.
 *
 * The label sits ABOVE at 11px and the figure below at 24px — a 2.2x step, so
 * the number is unmistakably the content and the label unmistakably furniture.
 * v1 ran them at 10.88 and 18px inside a grid of identical boxes, which is why
 * a screen of twelve stats read as texture rather than as twelve numbers.
 */
export function Stat({
  label, value, sub, tone,
}: { label: string; value: React.ReactNode; sub?: string; tone?: string }) {
  return (
    <div className="rounded border border-ruleSoft bg-sunken px-4 py-3">
      <div className="eyebrow mb-1.5">{label}</div>
      <div className={cn("num text-figure font-semibold leading-none", tone ?? "text-chalk")}>
        {value}
      </div>
      {sub && <div className="mt-2 text-micro leading-snug text-ash">{sub}</div>}
    </div>
  );
}


/**
 * A long explanation, with its point on the outside.
 *
 * THE SINGLE BIGGEST SOURCE OF OVERLOAD IN THIS APP. Fifty paragraphs across
 * the panels ran past ninety characters and one ran to ninety-six WORDS, each
 * of them permanently open, each of them explaining a method to a reader who
 * had not yet decided whether they cared about the method. Read end to end they
 * are the best thing here; met all at once they are why nobody reaches the
 * numbers.
 *
 * So the argument keeps its full text and gains a one-line summary. `summary`
 * has to be a claim rather than a label — "Seven columns are not seven tests"
 * is worth opening, "About this table" is not — because a disclosure whose
 * handle says nothing is just a hidden paragraph.
 *
 * NOT A CUT. Every word is still on the page, one click away, selectable and
 * printable. `PRODUCT.md` constraint 7 allows exactly this and forbids the
 * other thing.
 */
export function Explainer({
  summary, tone, defaultOpen = false, children,
}: {
  /** A claim, not a label. It is the only part most readers will see. */
  summary: string;
  /** `explain.tone`, where the server has one. Never picked from a number. */
  tone?: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  return (
    <details open={defaultOpen} className="group">
      <summary className={cn(
        "flex min-h-[24px] cursor-pointer list-none items-start gap-2 rounded py-1",
        "text-meta transition-colors hover:text-chalk",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tech",
        tone ? TONE_SUMMARY[tone] ?? "text-ash" : "text-ash",
      )}>
        <ChevronRight aria-hidden
                      className="mt-0.5 h-4 w-4 shrink-0 transition-transform group-open:rotate-90" />
        <span>{summary}</span>
      </summary>
      <div className="prose-col mt-2 pl-6 text-meta leading-relaxed text-ash">
        {children}
      </div>
    </details>
  );
}

const TONE_SUMMARY: Record<string, string> = {
  good: "text-acc", bad: "text-dist", warn: "text-warn",
  neutral: "text-ash", none: "text-ash",
};

/**
 * A short aside that is worth reading but is not the point of the panel.
 *
 * Distinct from `Explainer` by length rather than importance: under about
 * twenty-five words a disclosure costs the reader more than it saves.
 */
export function Note({
  children, tone,
}: { children: React.ReactNode; tone?: "warn" | "quiet" }) {
  return (
    <p className={cn("prose-col text-meta leading-relaxed",
                     tone === "warn" ? "text-warn" : "text-ash")}>
      {children}
    </p>
  );
}
