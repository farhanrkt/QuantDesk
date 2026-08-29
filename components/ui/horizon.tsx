"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { cn } from "@/lib/utils";

/**
 * How long the reader intends to hold this, stated once and read everywhere.
 *
 * WHY THE APP NEEDED THIS AT ALL. Every figure on the long-horizon section was
 * computed over whatever history happened to be loaded, and the rolling-return
 * table offered a fixed 1/3/5 years. Neither is the question a buyer is asking.
 * "What did three-year holders of this actually get" is answerable from the
 * data; "what did holders get, for some horizon nobody chose" is not a question.
 *
 * IT IS A SELECTION, NOT A REQUEST. Every horizon the loaded history can support
 * arrives already computed in the same payload, so switching costs nothing and
 * re-runs no engine. The alternative — a query parameter — would put a ten to
 * sixteen second four-lens round trip behind a control whose whole purpose is
 * to be moved around, and would have put the arithmetic on the wire for a
 * number the server had already worked out.
 *
 * THREE YEARS IS THE DEFAULT, and the reason is not that it is the middle
 * option. It is the shortest horizon over which the rolling-return distribution
 * of a typical equity stops being dominated by the entry date, and it is what
 * the plain-English summary has always quoted. A default of one year would
 * flatter almost everything; a default of ten would report "needs more history"
 * for most tickers at the range this app loads.
 */
export type Horizon = 1 | 2 | 3 | 5 | 10;

export const HORIZONS: readonly Horizon[] = [1, 2, 3, 5, 10];
const DEFAULT_HORIZON: Horizon = 3;

const HorizonContext = createContext<Horizon>(DEFAULT_HORIZON);
export const useHorizon = () => useContext(HorizonContext);

const STORAGE_KEY = "quantdesk.horizon";

export function HorizonProvider({
  value, children,
}: { value: Horizon; children: React.ReactNode }) {
  return <HorizonContext.Provider value={value}>{children}</HorizonContext.Provider>;
}

/**
 * Persisted for the same reason the reading mode is: someone who holds for a
 * decade holds for a decade on every ticker they look up, and asking them to
 * say so again on each one is its own small insult.
 */
export function useHoldingHorizon(): [Horizon, (h: Horizon) => void] {
  const [horizon, setHorizon] = useState<Horizon>(DEFAULT_HORIZON);
  // Read on mount, not during render: the server renders this tree too and has
  // no localStorage, so hydrating from a value it could not have known would
  // mismatch the markup.
  useEffect(() => {
    try {
      const stored = Number(window.localStorage.getItem(STORAGE_KEY));
      if ((HORIZONS as readonly number[]).includes(stored)) setHorizon(stored as Horizon);
    } catch { /* private mode or storage disabled — the default is fine */ }
  }, []);
  const update = (next: Horizon) => {
    setHorizon(next);
    try { window.localStorage.setItem(STORAGE_KEY, String(next)); } catch { /* ignore */ }
  };
  return [horizon, update];
}

export function HorizonPicker({
  value, onChange, available,
}: {
  value: Horizon;
  onChange: (h: Horizon) => void;
  /** Horizons the loaded history can actually support. */
  available?: readonly number[];
}) {
  // A `radiogroup` promises arrow keys and one tab stop. v1 declared the role
  // and implemented neither, so a screen reader announced a control that did
  // not behave like one — worse than plain buttons, because the announcement
  // teaches an interaction that is not there.
  const move = (event: React.KeyboardEvent) => {
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"].includes(event.key))
      return;
    event.preventDefault();
    const index = HORIZONS.indexOf(value);
    const next =
      event.key === "Home" ? 0
        : event.key === "End" ? HORIZONS.length - 1
          : event.key === "ArrowLeft" || event.key === "ArrowUp"
            ? (index - 1 + HORIZONS.length) % HORIZONS.length
            : (index + 1) % HORIZONS.length;
    onChange(HORIZONS[next]);
  };
  return (
    <div role="radiogroup" aria-label="Holding horizon" onKeyDown={move}
         className="inline-flex rounded-lg border border-rule bg-raised p-1">
      {HORIZONS.map((option) => {
        // An unsupported horizon stays SELECTABLE. Greying it out would hide
        // the one thing worth knowing — that this stock has no answer at that
        // length and the fix is a longer chart range — behind a disabled
        // attribute nobody hovers.
        const measured = !available || available.includes(option);
        return (
          <button
            key={option}
            type="button"
            role="radio"
            aria-checked={value === option}
            tabIndex={value === option ? 0 : -1}
            onClick={() => onChange(option)}
            title={measured ? undefined : "Not enough loaded history for this horizon"}
            className={cn(
              // 28px tall, over the 24px target floor. v1 was 24 exactly and
              // the label inside it was 10.4px.
              "num min-w-[2.75rem] rounded px-3 py-1.5 text-meta font-medium",
              "transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-tech",
              value === option ? "bg-tech/20 text-chalk"
                : measured ? "text-ash hover:bg-rule/50 hover:text-chalk"
                  : "text-faint hover:text-ash",
            )}
          >
            {option}y
          </button>
        );
      })}
    </div>
  );
}
