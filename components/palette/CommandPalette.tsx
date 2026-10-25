"use client";

import {
  ArrowRight, BookOpen, Clock, Columns3, CornerDownLeft, Hash, Home, LayoutGrid, NotebookPen,
  Search, Settings2, Star,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { usePageCommands, type RunnableCommand } from "@/components/palette/registry";
import { usePreferences } from "@/components/shell/preferences";
import { useWorkspace } from "@/components/shell/workspace";
import { HORIZONS } from "@/components/ui/horizon";
import { Kbd } from "@/components/ui/kbd";
import { searchSymbols } from "@/lib/api";
import { rankCommands, type CommandGroup } from "@/lib/commands";
import { isTicker, marketOf, resolveSymbol } from "@/lib/symbols";
import type { SymbolSearch } from "@/lib/types";
import { compareHref, marketsHref, stockHref } from "@/lib/url";
import { cn } from "@/lib/utils";

/**
 * One box that opens any company and reaches any page — ⌘K, `/`, or the search
 * button in the top bar.
 *
 * WHY A PALETTE AND NOT A BIGGER SEARCH FIELD. A reader who knows the ticker
 * was already served by the input on the page. The palette is for the two who
 * were not: the newcomer who knows "Bank Central Asia" and not BBCA.JK, and the
 * returning reader who wants the Value tab of something they looked at
 * yesterday without retyping it. Both are a few keystrokes here.
 *
 * "OPEN AS TYPED" IS ALWAYS FIRST when the text is a valid ticker. The listing
 * files hold equities only, so crypto pairs, indices, ETFs and last month's IPO
 * are not in them; the palette is a finder, never a gate on what can be opened.
 *
 * A NATIVE <dialog> with the ARIA combobox pattern: focus moves to the input,
 * arrows move the active option (announced through aria-activedescendant),
 * Enter runs it, Escape closes and focus returns to wherever it was.
 */
const ICONS: Record<CommandGroup, typeof Search> = {
  Open: Hash, Recent: Clock, Watchlist: Star, "Go to": ArrowRight, Actions: CornerDownLeft,
  Settings: Settings2,
};

const QUERY_OK = /^[A-Za-z0-9 .&'\-^=,()]{1,40}$/;

export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const router = useRouter();
  const dialog = useRef<HTMLDialogElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const returnFocus = useRef<HTMLElement | null>(null);
  const listId = useId();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const [found, setFound] = useState<SymbolSearch | null>(null);
  const [searching, setSearching] = useState(false);
  const { watchlist, recent } = useWorkspace();
  const { detail, setDetail, horizon, setHorizon } = usePreferences();
  const pageCommands = usePageCommands();

  // Open and close the native dialog from the prop, remembering where focus was.
  useEffect(() => {
    const el = dialog.current;
    if (!el) return;
    if (open && !el.open) {
      returnFocus.current = document.activeElement as HTMLElement | null;
      setQuery(""); setActive(0); setFound(null);
      el.showModal();
      requestAnimationFrame(() => input.current?.focus());
    } else if (!open && el.open) {
      el.close();
    }
  }, [open]);

  const close = useCallback(() => {
    onClose();
    const target = returnFocus.current;
    requestAnimationFrame(() => target?.focus?.());
  }, [onClose]);

  // Debounced, superseding symbol search. 120ms is under the gap between
  // keystrokes of someone typing a name, so it fires on a pause, not a key.
  useEffect(() => {
    const q = query.trim();
    if (!open || !QUERY_OK.test(q)) { setFound(null); setSearching(false); return; }
    const controller = new AbortController();
    setSearching(true);
    const timer = window.setTimeout(() => {
      searchSymbols(q, null, controller.signal)
        .then((r) => { setFound(r); setSearching(false); })
        .catch(() => { if (!controller.signal.aborted) { setFound(null); setSearching(false); } });
    }, 120);
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [query, open]);

  // Navigation closes the dialog WITHOUT returning focus: the reader asked to go
  // somewhere else, and putting focus back on the button they came from would
  // put it on a page that is being replaced.
  const go = useCallback((href: string) => { onClose(); router.push(href); }, [onClose, router]);

  const commands = useMemo<RunnableCommand[]>(() => {
    const typed = query.trim();
    const list: RunnableCommand[] = [];
    if (typed && isTicker(typed)) {
      const asTyped = resolveSymbol(typed, "US");
      list.push({ id: `open:${asTyped}`, group: "Open", label: `Open ${asTyped}`,
                  detail: "as typed", run: () => go(stockHref(asTyped)) });
      // A bare four-letter code is how IDX names are written everywhere but
      // Yahoo. Offer the suffixed form beside it rather than guessing: BBCA is a
      // US ETF and BBCA.JK a bank, and only the reader knows which they meant.
      if (/^[A-Za-z]{4}$/.test(typed)) {
        const idx = resolveSymbol(typed, "ID");
        list.push({ id: `open:${idx}`, group: "Open", label: `Open ${idx}`,
                    detail: "Indonesia (IDX)", run: () => go(stockHref(idx)) });
      }
    }
    for (const hit of found?.results ?? []) {
      if (list.some((c) => c.id === `open:${hit.symbol}`)) continue;
      list.push({ id: `open:${hit.symbol}`, group: "Open", label: `${hit.symbol} · ${hit.name}`,
                  keywords: hit.name, detail: hit.market === "ID" ? "IDX" : hit.exchange ?? "US",
                  run: () => go(stockHref(hit.symbol)) });
    }
    if (!typed) {
      for (const s of recent.slice(0, 5)) {
        list.push({ id: `recent:${s}`, group: "Recent", label: s,
                    detail: marketOf(s) === "ID" ? "IDX" : "US", run: () => go(stockHref(s)) });
      }
      for (const s of watchlist.slice(0, 8)) {
        list.push({ id: `watch:${s}`, group: "Watchlist", label: s,
                    detail: marketOf(s) === "ID" ? "IDX" : "US", run: () => go(stockHref(s)) });
      }
    }
    list.push(...pageCommands);
    list.push(
      { id: "go:home", group: "Go to", label: "Home", keywords: "landing start",
        run: () => go("/") },
      { id: "go:rank", group: "Go to", label: "Markets: rank a universe",
        keywords: "scan ranking dow nasdaq idx30 lq45", run: () => go(marketsHref("rank")) },
      { id: "go:screener", group: "Go to", label: "Markets: anomaly screener",
        keywords: "unusual scan", run: () => go(marketsHref("screener")) },
      { id: "go:exposure", group: "Go to", label: "Markets: what a universe moves with",
        keywords: "exposure factors drivers beta", run: () => go(marketsHref("exposure")) },
      { id: "go:scan", group: "Go to", label: "Markets: latest local scan",
        keywords: "scanner report private", run: () => go(marketsHref("scan")) },
      { id: "go:compare", group: "Go to", label: "Compare companies",
        keywords: "side by side columns", run: () => go(compareHref([])) },
      { id: "go:journal", group: "Go to", label: "Thesis journal",
        keywords: "notes entries", run: () => go("/journal") },
      { id: "go:manual", group: "Go to", label: "Field manual", keywords: "help glossary guide learn",
        run: () => { onClose(); window.location.href = "/docs/field-manual.html"; } },
      { id: "set:mode", group: "Settings",
        label: detail === "simple" ? "Switch to Full mode" : "Switch to Guided mode",
        keywords: "reading detail guided full",
        run: () => { setDetail(detail === "simple" ? "detailed" : "simple"); close(); } },
      ...HORIZONS.map((h) => ({
        id: `set:horizon:${h}`, group: "Settings" as const,
        label: `Holding horizon: ${h} year${h === 1 ? "" : "s"}`,
        detail: h === horizon ? "current" : undefined, keywords: "hold years",
        run: () => { setHorizon(h); close(); },
      })),
    );
    return list;
  }, [query, found, recent, watchlist, pageCommands, go, onClose, close, detail, setDetail,
      horizon, setHorizon]);

  const ranked = useMemo(() => {
    // Server results are already ordered by how they matched; ranking them
    // again on the label would re-sort companies by something the server did
    // not mean. So "Open" keeps its own order and the rest is ranked.
    const opens = commands.filter((c) => c.group === "Open");
    const rest = rankCommands(commands.filter((c) => c.group !== "Open"), query) as RunnableCommand[];
    return [...opens, ...rest];
  }, [commands, query]);

  useEffect(() => { setActive(0); }, [query]);
  const activeIndex = Math.min(active, Math.max(0, ranked.length - 1));
  const optionId = (i: number) => `${listId}-opt-${i}`;

  useEffect(() => {
    if (!open) return;
    document.getElementById(`${listId}-opt-${activeIndex}`)?.scrollIntoView({ block: "nearest" });
  }, [activeIndex, open, listId]);

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setActive(Math.min(activeIndex + 1, ranked.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive(Math.max(activeIndex - 1, 0)); }
    else if (e.key === "PageDown" || (e.key === "End" && e.ctrlKey)) { e.preventDefault(); setActive(ranked.length - 1); }
    else if (e.key === "PageUp" || (e.key === "Home" && e.ctrlKey)) { e.preventDefault(); setActive(0); }
    else if (e.key === "Enter") { e.preventDefault(); ranked[activeIndex]?.run(); }
  };

  const iconFor = (c: RunnableCommand) =>
    c.id === "go:home" ? Home
      : c.id === "go:compare" ? Columns3
        : c.id === "go:journal" ? NotebookPen
          : c.id === "go:manual" ? BookOpen
            : c.id.startsWith("go:") ? LayoutGrid : ICONS[c.group];

  return (
    <dialog ref={dialog} aria-labelledby={`${listId}-title`}
            onClose={() => { if (open) onClose(); }}
            onCancel={(e) => { e.preventDefault(); close(); }}
            onClick={(e) => { if (e.target === dialog.current) close(); }}
            className="mt-[12vh] w-[min(40rem,calc(100vw-2rem))] rounded-xl border border-rule bg-panel
                       p-0 text-body shadow-pop backdrop:bg-ink/70 open:animate-rise print:hidden">
      <h2 id={`${listId}-title`} className="sr-only">Search and commands</h2>
      <div className="flex items-center gap-3 border-b border-rule px-4">
        <Search aria-hidden className="h-4 w-4 shrink-0 text-ash" />
        <input
          ref={input}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={onKeyDown}
          role="combobox"
          aria-label="Company name, ticker, or a page to go to"
          aria-expanded={ranked.length > 0}
          aria-controls={listId}
          aria-activedescendant={ranked.length ? optionId(activeIndex) : undefined}
          aria-autocomplete="list"
          autoComplete="off" spellCheck={false}
          placeholder="Company name or ticker, or a page to go to"
          className="h-14 min-w-0 flex-1 bg-transparent text-[1rem] text-chalk placeholder:text-faint
                     focus:outline-none sm:text-base"
        />
        {searching && <span className="text-micro text-faint" aria-hidden>searching…</span>}
        <Kbd keys={["esc"]} className="hidden sm:inline-flex" />
      </div>
      <div id={listId} role="listbox" aria-label="Results"
           className="max-h-[min(60vh,28rem)] overflow-y-auto p-2">
        {ranked.length === 0 && (
          <p className="px-3 py-6 text-center text-meta text-ash">
            No listing or page matches. Type a full symbol — BTC-USD, ^GSPC — to open it as typed.
          </p>
        )}
        {ranked.map((c, i) => {
          const header = i === 0 || ranked[i - 1].group !== c.group ? c.group : null;
          const Icon = iconFor(c);
          return (
            <div key={c.id} role="presentation">
              {header && (
                <div role="presentation" className="eyebrow px-3 pb-1 pt-3 first:pt-1">{header}</div>
              )}
              <div
                id={optionId(i)} role="option" aria-selected={i === activeIndex}
                onMouseMove={() => { if (i !== activeIndex) setActive(i); }}
                onClick={() => c.run()}
                className={cn(
                  "flex min-h-[40px] cursor-pointer items-center gap-3 rounded-lg px-3 text-meta",
                  i === activeIndex ? "bg-raised text-chalk" : "text-body",
                )}
              >
                <Icon aria-hidden className="h-4 w-4 shrink-0 text-ash" />
                <span className="min-w-0 flex-1 truncate">{c.label}</span>
                {c.detail && <span className="shrink-0 text-micro text-faint">{c.detail}</span>}
              </div>
            </div>
          );
        })}
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-rule px-4 py-2 text-micro text-faint">
        <span className="inline-flex items-center gap-1.5"><Kbd keys={["up", "down"]} /> move</span>
        <span className="inline-flex items-center gap-1.5"><Kbd keys={["enter"]} /> open</span>
        {found && (
          <span className="ml-auto">
            Listings as of {found.listings.US?.asOf ?? "—"} (US) · {found.listings.ID?.asOf ?? "—"} (IDX)
          </span>
        )}
      </div>
    </dialog>
  );
}
