"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { DetailProvider, useDetailLevel, type DetailLevel } from "@/components/ui/explain";
import { HorizonProvider, useHoldingHorizon, type Horizon } from "@/components/ui/horizon";
import { setLang, type Lang } from "@/lib/i18n";

/**
 * The things a reader states once and every page reads: how much detail they
 * want (Guided / Full), how long they mean to hold, and which language to read.
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
  language: Lang;
  setLanguage: (l: Lang) => void;
}

const PreferencesContext = createContext<Preferences | null>(null);
const LANGUAGE_KEY = "quantdesk.language";

export function usePreferences(): Preferences {
  const value = useContext(PreferencesContext);
  if (!value) throw new Error("usePreferences outside PreferencesProvider");
  return value;
}

/**
 * THE READING LANGUAGE: chosen once, kept in this browser, and on a first visit
 * taken from the browser's own language — a reader whose browser asks for
 * Indonesian gets Indonesian without looking for a switch. Read on mount for
 * the same reason the reading mode is: the server renders this tree too, and
 * has no localStorage.
 */
function useLanguagePreference(): [Lang, (l: Lang) => void] {
  const [language, setLanguageState] = useState<Lang>("en");
  useEffect(() => {
    let initial: Lang = "en";
    try {
      const stored = window.localStorage.getItem(LANGUAGE_KEY);
      if (stored === "en" || stored === "id") initial = stored;
      else if ((navigator.language || "").toLowerCase().startsWith("id")) initial = "id";
    } catch { /* private mode — fall back to the browser's language below */
      if ((navigator.language || "").toLowerCase().startsWith("id")) initial = "id";
    }
    setLanguageState(initial);
  }, []);
  useEffect(() => {
    setLang(language);
    document.documentElement.lang = language;
  }, [language]);
  const update = useCallback((next: Lang) => {
    setLanguageState(next);
    try { window.localStorage.setItem(LANGUAGE_KEY, next); } catch { /* ignore */ }
  }, []);
  return [language, update];
}

export function PreferencesProvider({ children }: { children: React.ReactNode }) {
  const [detail, setDetail] = useDetailLevel();
  const [horizon, setHorizon] = useHoldingHorizon();
  const [language, setLanguage] = useLanguagePreference();
  return (
    <PreferencesContext.Provider value={{ detail, setDetail, horizon, setHorizon,
                                          language, setLanguage }}>
      <DetailProvider level={detail}>
        <HorizonProvider value={horizon}>{children}</HorizonProvider>
      </DetailProvider>
    </PreferencesContext.Provider>
  );
}
