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
  return (
    <div role="radiogroup" aria-label="Holding horizon"
         className="inline-flex rounded border border-rule bg-raised p-0.5">
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
            onClick={() => onChange(option)}
            title={measured ? undefined : "Not enough loaded history for this horizon"}
            className={cn(
              "rounded px-2.5 py-1 font-mono text-[0.65rem] uppercase tracking-[0.1em]",
              "transition-colors focus:outline-none focus-visible:ring-1 focus-visible:ring-tech",
              value === option ? "bg-tech/20 text-chalk"
                : measured ? "text-ash hover:text-chalk"
                  : "text-ash/40 hover:text-ash",
            )}
          >
            {option}y
          </button>
        );
      })}
    </div>
  );
}
