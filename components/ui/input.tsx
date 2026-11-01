"use client";

import { cn } from "@/lib/utils";

/**
 * 44px tall, not 40, and 15px text, not 14.
 *
 * The ticker box is the first thing anybody touches and the only control on the
 * page that is genuinely required. iOS zooms a focused input whose text is
 * under 16px, which on a phone yanks the whole layout sideways mid-typing — so
 * the field steps up at the small breakpoint where that rule applies.
 */
export function Input({ className, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      {...props}
      className={cn(
        "h-11 w-full rounded-lg border border-rule bg-sunken px-3.5",
        // 16px below `sm`, 15px above it. iOS zooms a focused input whose text
        // is under 16px and does not zoom back out, so on a phone the whole
        // layout stays yanked sideways for the rest of the session.
        "text-[1rem] text-chalk placeholder:text-faint sm:text-base",
        "transition-colors hover:border-ruleStrong focus:border-tech/60",
        "focus:outline-none focus-visible:ring-2 focus-visible:ring-tech",
        className,
      )}
    />
  );
}

export function Select({ className, children, ...props }: React.ComponentProps<"select">) {
  return (
    <select
      {...props}
      className={cn(
        "h-11 shrink-0 rounded-lg border border-rule bg-sunken px-3",
        // Same iOS rule: a `select` zooms on focus under 16px too.
        "text-[1rem] text-chalk transition-colors hover:border-tech/40 sm:text-meta",
        "focus:outline-none focus-visible:ring-2 focus-visible:ring-tech",
        className,
      )}
    >
      {children}
    </select>
  );
}

/**
 * A multi-line field. There was no primitive, so five textareas were each
 * written by hand on two different grounds (`bg-raised` in the ranking and
 * screener lists, `bg-ink` in the portfolio and thesis forms). Same ground,
 * border, focus and iOS rule as `Input`.
 */
export function Textarea({ className, mono, ...props }:
  React.ComponentProps<"textarea"> & { mono?: boolean }) {
  return (
    <textarea
      {...props}
      className={cn(
        "w-full rounded-lg border border-rule bg-sunken px-3.5 py-2.5",
        "text-[1rem] leading-relaxed text-chalk placeholder:text-faint sm:text-base",
        mono && "font-mono sm:text-meta",
        "transition-colors hover:border-ruleStrong focus:border-tech/60",
        "focus:outline-none focus-visible:ring-2 focus-visible:ring-tech",
        className,
      )}
    />
  );
}
