"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { DetailProvider, useDetailLevel, type DetailLevel } from "@/components/ui/explain";
import { HorizonProvider, useHoldingHorizon, type Horizon } from "@/components/ui/horizon";
import { msg, resolveLanguage, setLang, storeLanguage, translate, type Lang } from "@/lib/i18n";

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
// THE TAB'S TITLE, IN THE READER'S LANGUAGE (UX-5). Next writes each page's
// title from metadata on the server, which cannot know a language kept in this
// browser, so an Indonesian reader's tab said "Markets · QuantDesk". The fixed
// titles are listed here and swapped wherever Next sets one, on every
// navigation; a ticker is a title in any language and is left alone. What a
// shared link's preview says still comes from the server, in English.
const PAGE_TITLES = [msg("Markets"), msg("Thesis journal"), msg("Compare"), msg("Not found"),
                     msg("Not a ticker")];
const TITLE_SUFFIX = " · QuantDesk";

function useTitleInLanguage(language: Lang, resolved: boolean) {
  useEffect(() => {
    if (!resolved) return;
    const apply = () => {
      const title = document.title;
      if (!title.endsWith(TITLE_SUFFIX)) return;
      const shown = title.slice(0, -TITLE_SUFFIX.length);
      const english = PAGE_TITLES.find((e) => e === shown || translate("id", e) === shown);
      if (!english) return;
      const wanted = translate(language, english) + TITLE_SUFFIX;
      if (wanted !== title) document.title = wanted;
    };
    apply();
    const observer = new MutationObserver(apply);
    observer.observe(document.head, { subtree: true, childList: true, characterData: true });
    return () => observer.disconnect();
  }, [language, resolved]);
}

function useLanguagePreference(): [Lang, (l: Lang) => void] {
  const [language, setLanguageState] = useState<Lang>("en");
  // Until this browser's choice is read, the "en" above is only the server's
  // default; announcing it would point requests already in flight at English.
  const [resolved, setResolved] = useState(false);
  useEffect(() => { setLanguageState(resolveLanguage()); setResolved(true); }, []);
  useEffect(() => {
    if (!resolved) return;
    setLang(language);
    document.documentElement.lang = language;
  }, [language, resolved]);
  useTitleInLanguage(language, resolved);
  const update = useCallback((next: Lang) => {
    setLanguageState(next);
    storeLanguage(next);
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
