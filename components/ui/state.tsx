"use client";

import { AlertTriangle, CircleSlash, Inbox } from "lucide-react";
import { Skeleton, type SkeletonShape } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

/**
 * Every "there is nothing to show here yet / any more / at all" in the app.
 *
 * SIX DIFFERENT ERROR CARDS. The page's own `Panel` drew a red card with an h3;
 * the ranking, screener and event study drew an `.eyebrow` as the heading; the
 * portfolio and exposure panels drew no heading at all; peers used the warn
 * tone for the same condition everyone else called an error; and the news
 * panel rendered NOTHING when it failed, so a failure was indistinguishable
 * from a company nobody writes about.
 *
 * FOUR KINDS, AND TWO OF THEM MUST NEVER LOOK ALIKE.
 *
 *   error    something broke: a fetch, an upstream, a bad symbol. Toned bad.
 *   refused  the model does not apply here — a bank on the accounting screens,
 *            a check withheld for want of a base rate. That is a finding, not
 *            a failure, and it is styled quiet, never red: PRODUCT.md keeps the
 *            refusals precisely because they are honest, and a refusal drawn as
 *            an error reads as the app being broken.
 *   empty    nothing to show yet, usually because nothing has been asked.
 *   loading  in flight. A shaped skeleton plus one sentence a screen reader
 *            hears, so a slow engine reads as slow rather than broken.
 *
 * The distinction between a refusal and a gap is the one this codebase cares
 * about most (see the measure-before-claiming notes in RESEARCH_ROADMAP); the
 * component makes it impossible to draw them the same way by accident.
 */
export type StateKind = "error" | "refused" | "empty" | "loading";

const ICON = { error: AlertTriangle, refused: CircleSlash, empty: Inbox } as const;

export function StateCard({
  kind, title, children, action, shape = "chart", bare, className, level = 3,
}: {
  kind: StateKind;
  /**
   * The title's heading level. 3 inside a card or a tab (the default); 2 when
   * the state IS the page's content under its h1 — an empty compare view or
   * journal — so the outline does not jump from h1 to h3.
   */
  level?: 2 | 3;
  /** One line that states the condition. Optional for `loading`. */
  title?: string;
  children?: React.ReactNode;
  /** A retry, a form, a link — whatever closes the gap. */
  action?: React.ReactNode;
  /** For `loading`: what the skeleton should look like. */
  shape?: SkeletonShape;
  /** Render without its own card surface, for use inside an existing Card. */
  bare?: boolean;
  className?: string;
}) {
  const surface = bare ? "" : cn(
    "rounded-lg border",
    kind === "error" ? "border-dist/40 bg-dist/5"
      : kind === "refused" ? "border-ruleSoft bg-sunken"
        : "border-rule bg-panel",
  );

  if (kind === "loading") {
    return (
      <div className={cn(surface, className)} role="status" aria-live="polite">
        {title && <p className="px-5 pt-4 text-meta text-ash">{title}</p>}
        <Skeleton shape={shape} />
        {!title && <span className="sr-only">Loading…</span>}
      </div>
    );
  }

  const Icon = ICON[kind];
  const Heading = level === 2 ? "h2" : "h3";
  return (
    <div className={cn(surface, bare ? "" : "p-5", className)}
         role={kind === "error" ? "alert" : undefined}>
      <div className="flex gap-3.5">
        <Icon aria-hidden className={cn("mt-0.5 h-5 w-5 shrink-0",
          kind === "error" ? "text-dist" : "text-ash")} />
        <div className="min-w-0 flex-1 space-y-2">
          {title && (
            <Heading className={cn("text-lead",
              kind === "error" ? "text-dist" : "text-chalk")}>{title}</Heading>
          )}
          {children && (
            <div className="prose-col text-base leading-relaxed text-body">{children}</div>
          )}
          {action && <div className="pt-1">{action}</div>}
        </div>
      </div>
    </div>
  );
}
