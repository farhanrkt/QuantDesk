"use client";

import { useCallback, useSyncExternalStore } from "react";

/**
 * State that outlives the component showing it, for as long as the tab is open.
 * ============================================================================
 *
 * WHY IT EXISTS. Every panel held its results in its own `useState`, and the
 * old tab strip unmounted inactive panels — so a six-second Nasdaq-100 ranking,
 * a screener scan, a half-written thesis and the Technical sub-tab were thrown
 * away the moment the reader looked at another tab. Path routes would have made
 * that worse: leaving a stock page for the compare view unmounts all of it.
 *
 * KEYED, AND THE KEY IS THE FIX FOR A SECOND BUG. A request records its result
 * under the key it was STARTED with — `peers:AAPL`, not "whatever ticker is on
 * screen now" — so a late response lands beside the company it describes and
 * can never appear under another one's header. The old hooks needed a reset
 * call on every ticker change to approximate that, and three call sites passed
 * the ticker still being typed rather than the one loaded, which is exactly the
 * mistake a key makes impossible.
 *
 * NEVER ON A SERVER, NEVER IN STORAGE. The map lives in this module, in the
 * browser tab. It is not written to localStorage (a refresh starts clean, the
 * same as before) and nothing is written to it during a server render: writes
 * happen only in event handlers and effects, which do not run there.
 *
 * `initial` must be referentially stable (a module constant or a primitive):
 * it is returned as the snapshot when nothing is stored, and React requires a
 * snapshot to be the same object until the store changes.
 */
const store = new Map<string, unknown>();
const listeners = new Map<string, Set<() => void>>();

export function readSession<T>(key: string): T | undefined {
  return store.get(key) as T | undefined;
}

export function writeSession<T>(key: string, value: T | ((prev: T | undefined) => T)): void {
  const next = typeof value === "function"
    ? (value as (prev: T | undefined) => T)(store.get(key) as T | undefined)
    : value;
  store.set(key, next);
  listeners.get(key)?.forEach((notify) => notify());
}

export function clearSession(key: string): void {
  store.delete(key);
  listeners.get(key)?.forEach((notify) => notify());
}

export function useSessionState<T>(key: string, initial: T):
  [T, (value: T | ((prev: T) => T)) => void] {
  const subscribe = useCallback((notify: () => void) => {
    let set = listeners.get(key);
    if (!set) { set = new Set(); listeners.set(key, set); }
    set.add(notify);
    return () => { set!.delete(notify); };
  }, [key]);
  const value = useSyncExternalStore(
    subscribe,
    () => (store.has(key) ? store.get(key) as T : initial),
    () => initial,
  );
  const set = useCallback((next: T | ((prev: T) => T)) => {
    writeSession<T>(key, (prev) => typeof next === "function"
      ? (next as (p: T) => T)(prev === undefined ? initial : prev)
      : next);
  }, [key, initial]);
  return [value, set];
}
