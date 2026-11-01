"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import {
  RECENT_KEY, WATCHLIST_KEY, WATCHLIST_MAX, parseList, pushRecent, serialiseList, toggle,
} from "@/lib/watchlist";
import { RECENT_MAX } from "@/lib/watchlist";

/**
 * The reader's watchlist and recent tickers, for every page.
 *
 * In this browser and nowhere else — see lib/watchlist.ts for why, and
 * scripts/check_frontend.mjs for the rule that keeps the request layer from
 * reaching it. Synced across tabs through the `storage` event, so starring a
 * ticker in one tab does not leave another tab's list quietly out of date.
 */
interface Workspace {
  watchlist: string[];
  recent: string[];
  isWatched: (symbol: string) => boolean;
  /** Returns false when the list is full and nothing was added. */
  toggleWatch: (symbol: string) => boolean;
  recordRecent: (symbol: string) => void;
  clearRecent: () => void;
}

const WorkspaceContext = createContext<Workspace | null>(null);

export function useWorkspace(): Workspace {
  const value = useContext(WorkspaceContext);
  if (!value) throw new Error("useWorkspace outside WorkspaceProvider");
  return value;
}

function read(key: string, max: number): string[] {
  try { return parseList(window.localStorage.getItem(key), max); } catch { return []; }
}

function write(key: string, list: string[]) {
  try { window.localStorage.setItem(key, serialiseList(list)); } catch { /* private mode */ }
}

export function WorkspaceProvider({ children }: { children: React.ReactNode }) {
  const [watchlist, setWatchlist] = useState<string[]>([]);
  const [recent, setRecent] = useState<string[]>([]);

  // Read on mount, never during render: the server renders this tree too and
  // has no localStorage, so hydrating from a value it could not know would
  // mismatch the markup.
  useEffect(() => {
    setWatchlist(read(WATCHLIST_KEY, WATCHLIST_MAX));
    setRecent(read(RECENT_KEY, RECENT_MAX));
    const sync = (e: StorageEvent) => {
      if (e.key === WATCHLIST_KEY) setWatchlist(parseList(e.newValue, WATCHLIST_MAX));
      if (e.key === RECENT_KEY) setRecent(parseList(e.newValue, RECENT_MAX));
    };
    window.addEventListener("storage", sync);
    return () => window.removeEventListener("storage", sync);
  }, []);

  const toggleWatch = useCallback((symbol: string) => {
    const current = read(WATCHLIST_KEY, WATCHLIST_MAX);
    const next = toggle(current, symbol);
    const refused = next === current && !current.includes(symbol.toUpperCase());
    if (!refused) { write(WATCHLIST_KEY, next); setWatchlist(next); }
    return !refused;
  }, []);

  const recordRecent = useCallback((symbol: string) => {
    const next = pushRecent(read(RECENT_KEY, RECENT_MAX), symbol);
    write(RECENT_KEY, next);
    setRecent(next);
  }, []);

  const clearRecent = useCallback(() => { write(RECENT_KEY, []); setRecent([]); }, []);

  const isWatched = useCallback((symbol: string) =>
    watchlist.includes(symbol.trim().toUpperCase()), [watchlist]);

  return (
    <WorkspaceContext.Provider
      value={{ watchlist, recent, isWatched, toggleWatch, recordRecent, clearRecent }}>
      {children}
    </WorkspaceContext.Provider>
  );
}
