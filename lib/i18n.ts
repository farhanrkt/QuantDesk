"use client";

import { useCallback, useSyncExternalStore } from "react";
import { ID } from "./i18n-id";

/**
 * The reading language: English or Bahasa Indonesia.
 * ==================================================
 *
 * THE ENGLISH IS THE KEY. A component writes `t("Run all lenses")` and gets the
 * Indonesian from `lib/i18n-id.ts` when the reader chose it, or the English
 * itself otherwise. Keeping the English in the component keeps the component
 * readable, and `scripts/check_frontend.mjs` fails the build if a wrapped string
 * has no Indonesian entry — wrapping a string and translating it are one change.
 *
 * WHAT IS TRANSLATED, AND WHAT IS NOT. Every sentence, label and button the
 * reader reads. Never an identifier, a ticker, a number or a unit the server
 * also uses; the server translates its own prose when a request carries
 * `lang=id` (api/_lib/lang.py), so the page and the panels beneath it change
 * together.
 *
 * A STORE, NOT A CONTEXT, because the request layer (lib/api.ts) needs the
 * language outside React to put it on the URL. The preferences provider owns
 * persistence; this module owns the value.
 *
 * TWO MOMENTS, TWO READINGS. The server draws every page in English, because it
 * cannot know what this browser chose, and the first client render has to draw
 * the same thing or React discards the page. So the language the interface is
 * DRAWN in (`useLang`, `useT`, `t`) switches only after hydration, when the
 * preferences provider calls `setLang`. The language REQUESTS ask for
 * (`requestLang`) is resolved from this browser at once — the first fetch on a
 * page already asks for Indonesian, rather than fetching English and then
 * fetching everything again a frame later.
 */
export type Lang = "en" | "id";
export const LANGS: readonly Lang[] = ["en", "id"];
export const LANG_NAME: Record<Lang, string> = { en: "English", id: "Bahasa Indonesia" };

const STORAGE_KEY = "quantdesk.language";

let current: Lang = "en";
let requested: Lang | null = null;
const listeners = new Set<() => void>();

/**
 * What this browser asked for: the stored choice, or on a first visit the
 * browser's own language — a reader whose browser asks for Indonesian gets
 * Indonesian without looking for a switch.
 */
export function resolveLanguage(): Lang {
  if (typeof window === "undefined") return "en";
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "en" || stored === "id") return stored;
  } catch { /* private mode: fall through to the browser's language */ }
  return (navigator.language || "").toLowerCase().startsWith("id") ? "id" : "en";
}

/** Remember the reader's choice in this browser, and nowhere else. */
export function storeLanguage(next: Lang): void {
  try { window.localStorage.setItem(STORAGE_KEY, next); } catch { /* ignore */ }
}

/** The language the interface is drawn in right now. */
export function getLang(): Lang {
  return current;
}

/** The language a request asks the server for. See the module comment. */
export function requestLang(): Lang {
  if (typeof window === "undefined") return "en";
  if (requested === null) requested = resolveLanguage();
  return requested;
}

export function setLang(next: Lang): void {
  if (!LANGS.includes(next)) return;
  requested = next;
  if (next === current) return;
  current = next;
  listeners.forEach((notify) => notify());
}

const subscribe = (notify: () => void) => {
  listeners.add(notify);
  return () => { listeners.delete(notify); };
};

/** The current language, re-rendering the caller when it changes. */
export function useLang(): Lang {
  return useSyncExternalStore(subscribe, getLang, () => "en");
}

/** A value a sentence carries. Like a JSX child, null, undefined and booleans print nothing. */
export type Vars = Record<string, string | number | boolean | null | undefined>;

/** `{name}` placeholders filled from `vars`; anything unmatched is left as written. */
function fill(text: string, vars?: Vars): string {
  if (!vars) return text;
  return text.replace(/\{(\w+)\}/g, (whole, name: string) => {
    if (!Object.prototype.hasOwnProperty.call(vars, name)) return whole;
    const value = vars[name];
    return value === null || value === undefined || typeof value === "boolean" ? "" : String(value);
  });
}

/** `english` in `lang`: its Indonesian entry when there is one, or the English. */
export function translate(lang: Lang, english: string, vars?: Vars): string {
  return fill(lang === "id" ? ID[english] ?? english : english, vars);
}

/** Outside React: the text in whatever language is current at the call. */
export function t(english: string, vars?: Vars): string {
  return translate(current, english, vars);
}

/** Inside React: a `t` that re-renders the component when the language changes. */
export function useT(): (english: string, vars?: Vars) => string {
  const lang = useLang();
  return useCallback((english: string, vars?: Vars) => translate(lang, english, vars), [lang]);
}

/**
 * A catalog key written where it is DECLARED rather than where it is shown — a
 * label in a constant table, a group name — and translated later with
 * `t(label)`. It returns its argument unchanged; it exists so the build check
 * can see the string and demand its Indonesian entry, which it cannot do for
 * `t(item.label)`.
 */
export function msg(english: string): string {
  return english;
}

// --------------------------------------------------------------------------- //
// Dates, in the language the page is drawn in
// --------------------------------------------------------------------------- //
// Month and weekday names come from tables rather than `Intl`, because the
// calendar formats them in the exchange's zone and the reader's, and a browser's
// own locale data would decide the spelling ("Agt" or "Agu") per device.
const MONTHS_SHORT: Record<Lang, string[]> = {
  en: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
  id: ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"],
};
const MONTHS_LONG: Record<Lang, string[]> = {
  en: ["January", "February", "March", "April", "May", "June", "July", "August", "September",
       "October", "November", "December"],
  id: ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September",
       "Oktober", "November", "Desember"],
};
const DAYS_SHORT: Record<Lang, string[]> = {
  en: ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
  id: ["Min", "Sen", "Sel", "Rab", "Kam", "Jum", "Sab"],
};
const DAYS_LONG: Record<Lang, string[]> = {
  en: ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
  id: ["Minggu", "Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu"],
};

/** "Nov" / "Nov", "May" / "Mei"; `month` is 1-12. */
export const monthShort = (month: number): string => MONTHS_SHORT[current][month - 1];
/** "November" / "November"; `month` is 1-12. */
export const monthLong = (month: number): string => MONTHS_LONG[current][month - 1];
/** "Tue" / "Sel"; `weekday` is 0 (Sunday) to 6, as `getUTCDay` returns it. */
export const dayShort = (weekday: number): string => DAYS_SHORT[current][weekday];
/** "Tuesday" / "Selasa"; `weekday` is 0 (Sunday) to 6. */
export const dayLong = (weekday: number): string => DAYS_LONG[current][weekday];
