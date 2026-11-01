"use client";

import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

/**
 * A container that scrolls — and a keyboard user can scroll it.
 *
 * WHY THIS EXISTS. A table wider than the screen sits in an `overflow-x-auto`
 * box, and a mouse or a finger scrolls it. A keyboard cannot, unless the box
 * holds something focusable or can take focus itself; otherwise the columns
 * past the edge are simply unreachable (WCAG 2.1.1). axe found the first one on
 * the flagged-days table, and at a phone's width nearly every table in the app
 * overflows, so the fix is a primitive rather than a patch.
 *
 * FOCUSABLE ONLY WHILE IT SCROLLS. Giving every table wrapper a tab stop would
 * add twenty stops a desktop reader never needs. The box watches its own size
 * and becomes a labelled, focusable region only when its content is wider (or
 * taller) than it is — so a phone gets the stop and a wide screen does not.
 */
export function ScrollRegion({
  label, className, children, vertical,
}: {
  /** What the region holds, announced when it takes focus. */
  label: string;
  className?: string;
  children: React.ReactNode;
  /** Scroll in both directions (a capped-height table) rather than sideways only. */
  vertical?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [scrolls, setScrolls] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const check = () => setScrolls(el.scrollWidth > el.clientWidth + 1
                                   || (!!vertical && el.scrollHeight > el.clientHeight + 1));
    check();
    const observer = new ResizeObserver(check);
    observer.observe(el);
    for (const child of Array.from(el.children)) observer.observe(child);
    return () => observer.disconnect();
  }, [vertical]);

  return (
    <div ref={ref}
         // `relative` is load-bearing. Overflow clips only descendants whose
         // containing block is inside the clipping box, and `sr-only` text is
         // absolutely positioned — so a screen-reader label in a wide table
         // (the grid's "the assumed case") was positioned against the CARD,
         // escaped this box, and widened the whole page by 4px at 375px.
         className={cn("relative", vertical ? "overflow-auto" : "overflow-x-auto",
                       "focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-tech",
                       className)}
         tabIndex={scrolls ? 0 : undefined}
         role={scrolls ? "region" : undefined}
         aria-label={scrolls ? label : undefined}>
      {children}
    </div>
  );
}
