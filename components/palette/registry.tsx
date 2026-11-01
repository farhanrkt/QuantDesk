"use client";

import { useEffect, useRef, useSyncExternalStore } from "react";
import type { Command } from "@/lib/commands";

/**
 * Commands a page adds to the palette while it is on screen — the stock page's
 * tabs, "add to watchlist", "copy link". Registered from the page and removed
 * when it unmounts, so the palette never offers "go to the Value tab" on the
 * compare view.
 *
 * A module-level store rather than a context provider: the palette lives in the
 * shell and the pages are its children, so a provider would need the page to
 * render above the palette it is configuring.
 */
export type RunnableCommand = Command & { run: () => void };

const sources = new Map<string, RunnableCommand[]>();
const listeners = new Set<() => void>();
let snapshot: RunnableCommand[] = [];

function publish() {
  snapshot = [...sources.values()].flat();
  listeners.forEach((l) => l());
}

export function usePageCommands(): RunnableCommand[] {
  return useSyncExternalStore(
    (l) => { listeners.add(l); return () => { listeners.delete(l); }; },
    () => snapshot,
    () => snapshot,
  );
}

/** Register `commands` under `id` for as long as the calling component is mounted. */
export function useRegisterCommands(id: string, commands: RunnableCommand[]) {
  // The latest closures, without re-registering on every render: the labels
  // rarely change, but the handlers close over state that does.
  const latest = useRef(commands);
  latest.current = commands;
  const signature = commands.map((c) => `${c.id}|${c.label}|${c.detail ?? ""}`).join("\n");
  useEffect(() => {
    sources.set(id, latest.current.map((c) => ({
      ...c, run: () => latest.current.find((x) => x.id === c.id)?.run(),
    })));
    publish();
    return () => { sources.delete(id); publish(); };
  }, [id, signature]);
}
