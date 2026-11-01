/**
 * The reader's watchlist and recent tickers. Browser-only, by construction.
 * =========================================================================
 *
 * WHY THESE NEVER LEAVE THE BROWSER. The analytics comment in lib/api.ts has
 * said it since the start: "a watchlist is one of the more revealing things
 * someone can tell you". So both lists live in localStorage under the keys
 * below and nowhere else. The request layer is not allowed to import this file
 * (scripts/check_frontend.mjs fails the build if it does), and the one feature
 * that sends a watchlist anywhere — ranking it — does so only on an explicit
 * click, in a POST body, never in a URL.
 *
 * DEFENSIVE ON READ, the way the journal is. Storage is user-writable and
 * survives across versions of this app; a corrupt or hand-edited value must
 * cost the bad rows, never the good ones and never an exception at startup.
 *
 * Pure: compiled into the frontend assertions and pinned there.
 */
import { isTicker } from "./symbols";

export const WATCHLIST_KEY = "quantdesk.watchlist";
export const RECENT_KEY = "quantdesk.recent";
export const WATCHLIST_MAX = 50;
export const RECENT_MAX = 12;

/** `{ v: 1, symbols: [...] }`, or a bare array from a hand edit. Bad rows are dropped. */
export function parseList(raw: string | null | undefined, max = WATCHLIST_MAX): string[] {
  if (!raw) return [];
  let parsed: unknown;
  try { parsed = JSON.parse(raw); } catch { return []; }
  const rows = Array.isArray(parsed) ? parsed
    : parsed && typeof parsed === "object" && Array.isArray((parsed as { symbols?: unknown }).symbols)
      ? (parsed as { symbols: unknown[] }).symbols : [];
  const out: string[] = [];
  for (const row of rows) {
    if (typeof row !== "string" || !isTicker(row)) continue;
    const symbol = row.trim().toUpperCase();
    if (!out.includes(symbol)) out.push(symbol);
    if (out.length === max) break;
  }
  return out;
}

export function serialiseList(symbols: string[]): string {
  return JSON.stringify({ v: 1, symbols });
}

/** Add to the front, or remove if already there. A full list refuses rather than evicts. */
export function toggle(list: string[], symbol: string, max = WATCHLIST_MAX): string[] {
  const s = symbol.trim().toUpperCase();
  if (list.includes(s)) return list.filter((x) => x !== s);
  // EVICTING THE OLDEST WOULD BE A SILENT DELETION of something the reader
  // chose to keep. At the cap the add is refused and the caller says so.
  if (list.length >= max) return list;
  return [s, ...list];
}

/** Newest first, de-duplicated, capped. Recent tickers DO evict: they are a trail, not a choice. */
export function pushRecent(list: string[], symbol: string, max = RECENT_MAX): string[] {
  const s = symbol.trim().toUpperCase();
  return [s, ...list.filter((x) => x !== s)].slice(0, max);
}
