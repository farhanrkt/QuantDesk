"use client";

import { Fragment, useEffect, useRef } from "react";
import { alpha } from "@/lib/palette";
import { cn } from "@/lib/utils";

export interface Tab {
  id: string;
  label: string;
  /** Engine hue — the active tab is the only place this colour appears here. */
  accent: string;
  /** What this tab answers, in the reader's own words. Shown when there is room. */
  hint?: string;
  /**
   * A label drawn before this tab, marking where one kind of tab ends and
   * another begins — the private scoring tier after the published lenses.
   * Presentation only: it is not a tab and takes no focus.
   */
  divider?: string;
}

/**
 * A tablist that keeps the promise its role makes.
 *
 * v1 declared `role="tablist"` and `role="tab"` and implemented none of the
 * keyboard contract those roles commit to: no `aria-controls`, no
 * `role="tabpanel"` on the content, no roving tabindex, no arrow keys. A screen
 * reader announced "tab, 2 of 7" and arrow keys did nothing, while every one of
 * the twelve tabs on screen (seven here plus five inside the technical panel)
 * sat in the tab order. Declaring a widget you have not built is worse than
 * using plain buttons, because the announcement teaches the reader an
 * interaction that is not there.
 *
 * So: one tab stop for the group, Left/Right to move between tabs, Home/End to
 * jump, and `aria-controls` pointing at a real `TabPanel`.
 */
export function Tabs({
  tabs, active, onChange, idPrefix = "tab", label = "Lenses", hasPanels = true,
}: {
  tabs: Tab[];
  active: string;
  onChange: (id: string) => void;
  /** False where the caller switches sections itself rather than using `TabPanel`. */
  hasPanels?: boolean;
  /** Distinct per tablist, so the nested technical tabs cannot collide. */
  idPrefix?: string;
  /**
   * What this group of tabs IS. Two tablists render on the Trend tab — the
   * seven lenses and the five horizons inside the technical panel — and both
   * announced themselves as "Lenses", so a screen-reader user heard the same
   * group name twice and had no way to tell which one they were in. Found by
   * walking the real tab order rather than by reading the markup.
   */
  label?: string;
}) {
  const strip = useRef<HTMLDivElement>(null);

  // ONE ROW, SCROLLED SIDEWAYS, and the selected tab kept in view. The strip
  // used to wrap, which on a phone made it three sticky rows covering a third of
  // the screen; scrolling keeps it one row, and a tab chosen from the palette or
  // with `]` is brought into view rather than selected off-screen.
  useEffect(() => {
    const el = strip.current?.querySelector<HTMLElement>(`[role=tab][aria-selected=true]`);
    el?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [active]);

  const onKeyDown = (event: React.KeyboardEvent) => {
    const keys = ["ArrowLeft", "ArrowRight", "Home", "End"];
    if (!keys.includes(event.key)) return;
    event.preventDefault();
    const index = tabs.findIndex((t) => t.id === active);
    const next =
      event.key === "Home" ? 0
        : event.key === "End" ? tabs.length - 1
          : event.key === "ArrowLeft" ? (index - 1 + tabs.length) % tabs.length
            : (index + 1) % tabs.length;
    onChange(tabs[next].id);
    // Focus follows selection, which is the automatic-activation pattern and the
    // right one here: every panel is already loaded, so moving through them
    // costs nothing and manual activation would add a keystroke per tab.
    strip.current?.querySelectorAll<HTMLButtonElement>("[role=tab]")[next]?.focus();
  };

  return (
    <div
      ref={strip}
      role="tablist"
      aria-label={label}
      onKeyDown={onKeyDown}
      className="flex gap-1 overflow-x-auto border-b border-rule [scrollbar-width:none]
                 [&::-webkit-scrollbar]:hidden"
    >
      {tabs.map((tab) => {
        const selected = tab.id === active;
        return (
          <Fragment key={tab.id}>
          {tab.divider && (
            <span aria-hidden
                  className="ml-2 flex shrink-0 items-center border-l border-rule pl-3 pr-1 text-micro
                             uppercase tracking-[0.14em] text-faint">
              {tab.divider}
            </span>
          )}
          <button
            type="button"
            role="tab"
            id={`${idPrefix}-${tab.id}`}
            aria-selected={selected}
            // `aria-controls` ONLY where a `TabPanel` actually renders that id.
            // The technical panel switches sections with a plain conditional, so
            // pointing at `horizonpanel-long` would be a reference to an element
            // that does not exist — worse than omitting it, because a screen
            // reader offers the reader a jump that goes nowhere.
            // Only the SELECTED tab's panel is in the document — `TabPanel`
            // returns null for the rest — so only the selected tab may point at
            // one. Six of seven were dangling before.
            aria-controls={hasPanels && selected ? `${idPrefix}panel-${tab.id}` : undefined}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(tab.id)}
            className={cn(
              // No `rounded-t`. A 2px underline under rounded top corners reads as a
              // box that failed to close; the tint alone carries the active state
              // and the rule finishes it.
              "-mb-px shrink-0 whitespace-nowrap border-b-2 px-3.5 py-2.5 text-meta font-medium",
              "transition-colors focus:outline-none focus-visible:ring-2",
              "focus-visible:ring-tech focus-visible:ring-offset-0",
              selected
                ? "text-chalk"
                : "border-transparent text-ash hover:bg-raised/60 hover:text-chalk",
            )}
            style={selected
              ? { borderBottomColor: tab.accent, color: tab.accent,
                  background: alpha(tab.accent, 0.06) }
              : undefined}
          >
            {tab.label}
          </button>
          </Fragment>
        );
      })}
    </div>
  );
}

/** The other half of the contract. A `tablist` with no `tabpanel` is a claim. */
export function TabPanel({
  id, active, idPrefix = "tab", children,
}: {
  id: string;
  active: string;
  idPrefix?: string;
  children: React.ReactNode;
}) {
  if (id !== active) return null;
  return (
    <div
      role="tabpanel"
      id={`${idPrefix}panel-${id}`}
      aria-labelledby={`${idPrefix}-${id}`}
      // A panel with no focusable content of its own still needs to be
      // reachable, or a keyboard reader tabs straight from the tablist to
      // whatever follows the panel and never hears what is in it.
      tabIndex={0}
      className="focus:outline-none focus-visible:ring-2 focus-visible:ring-tech"
    >
      {children}
    </div>
  );
}
