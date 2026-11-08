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
 * persistence and the first-visit default; this module owns the value.
 */
export type Lang = "en" | "id";
export const LANGS: readonly Lang[] = ["en", "id"];
export const LANG_NAME: Record<Lang, string> = { en: "English", id: "Bahasa Indonesia" };

let current: Lang = "en";
const listeners = new Set<() => void>();

export function getLang(): Lang {
  return current;
}

export function setLang(next: Lang): void {
  if (next === current || !LANGS.includes(next)) return;
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

export type Vars = Record<string, string | number>;

/** `{name}` placeholders filled from `vars`; anything unmatched is left as written. */
function fill(text: string, vars?: Vars): string {
  if (!vars) return text;
  return text.replace(/\{(\w+)\}/g, (whole, name: string) =>
    Object.prototype.hasOwnProperty.call(vars, name) ? String(vars[name]) : whole);
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
