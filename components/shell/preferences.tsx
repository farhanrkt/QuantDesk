"use client";

import { createContext, useContext } from "react";
import { DetailProvider, useDetailLevel, type DetailLevel } from "@/components/ui/explain";
import { HorizonProvider, useHoldingHorizon, type Horizon } from "@/components/ui/horizon";

/**
 * The two things a reader states once and every page reads: how much detail
 * they want (Guided / Full) and how long they mean to hold.
 *
 * They lived in the single page component, which was fine while there was one
 * page. With routes, the top bar sets the reading mode and the stock page, the
 * compare view and the thesis journal all read the horizon, so both move up to
 * the shell — still persisted in this browser and nowhere else, exactly as
 * before.
 */
interface Preferences {
  detail: DetailLevel;
  setDetail: (v: DetailLevel) => void;
  horizon: Horizon;
  setHorizon: (h: Horizon) => void;
}

const PreferencesContext = createContext<Preferences | null>(null);

export function usePreferences(): Preferences {
  const value = useContext(PreferencesContext);
  if (!value) throw new Error("usePreferences outside PreferencesProvider");
  return value;
}

export function PreferencesProvider({ children }: { children: React.ReactNode }) {
  const [detail, setDetail] = useDetailLevel();
  const [horizon, setHorizon] = useHoldingHorizon();
  return (
    <PreferencesContext.Provider value={{ detail, setDetail, horizon, setHorizon }}>
      <DetailProvider level={detail}>
        <HorizonProvider value={horizon}>{children}</HorizonProvider>
      </DetailProvider>
    </PreferencesContext.Provider>
  );
}
