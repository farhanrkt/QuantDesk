"use client";

import {
  ArrowLeft, ArrowRight, Columns3, Plus, RotateCw, X,
} from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useRegisterCommands } from "@/components/palette/registry";
import { usePreferences } from "@/components/shell/preferences";
import { useWorkspace } from "@/components/shell/workspace";
import { Button } from "@/components/ui/button";
import { Note } from "@/components/ui/card";
import { Explain, TONE_TEXT, useDetail } from "@/components/ui/explain";
import { Input, Select } from "@/components/ui/input";
import { StateCard } from "@/components/ui/state";
import { fetchConfluence, peekConfluence, type RunOptions } from "@/lib/api";
import { buildCompare, type CompareCell, type CompareModel } from "@/lib/compare";
import { writeSession } from "@/lib/session";
import { isTicker, marketOf, resolveSymbol } from "@/lib/symbols";
import type { ConfluenceResponse, Engine, Market } from "@/lib/types";
import { MAX_COMPARE, PRESETS, RUN_DEFAULTS, compareHref, parseSymbolList, stockHref } from "@/lib/url";
import { cn } from "@/lib/utils";

/**
 * Two to four companies, each read through the same lenses, side by side.
 *
 * NOTHING HERE DECIDES BETWEEN THEM. The columns stay in the reader's order
 * (move them by hand; there is no sort), every cell carries its own company's
 * server tone and nothing computed across columns, and every column is the same
 * width — no highlighted winner, no row of totals, no count of how many lenses
 * are "positive". lib/compare.ts holds the reasoning; check_frontend.mjs rule 14
 * holds the line.
 *
 * TWO AT A TIME. Each column is one full read of a company — four engines on a
 * serverless function, often cold. Four at once is four cold starts and twenty
 * simultaneous calls to the data source from one reader, so columns are fetched
 * two at a time, each through the shared cache: a company already open in this
 * tab appears at once, and opening a column's stock page afterwards reuses the
 * same answer.
 */
const opts = (symbol: string): RunOptions => ({ ticker: symbol, market: marketOf(symbol), ...RUN_DEFAULTS });

function useColumns(symbols: string[]) {
  const [states, setStates] = useState<Record<string, Engine<ConfluenceResponse>>>({});
  const [nonce, setNonce] = useState(0);
  const key = symbols.join(",");

  useEffect(() => {
    let alive = true;
    const set = (s: string, v: Engine<ConfluenceResponse>) => {
      if (alive) setStates((prev) => ({ ...prev, [s]: v }));
    };
    const pending: string[] = [];
    for (const s of symbols) {
      const hit = peekConfluence(opts(s));
      if (hit) set(s, { status: "ready", data: hit.value, at: hit.at });
      else { pending.push(s); set(s, { status: "idle" }); }
    }
    let next = 0;
    const worker = async () => {
      while (alive && next < pending.length) {
        const s = pending[next++];
        set(s, { status: "loading" });
        try {
          const result = await fetchConfluence(opts(s));
          set(s, { status: "ready", data: result.value, at: result.at });
        } catch (err) {
          const message = err && typeof err === "object" && "message" in err
            ? String((err as { message: unknown }).message) : String(err);
          set(s, { status: "error", failure: { message } });
        }
      }
    };
    void worker();
    void worker();
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `key` is the list
  }, [key, nonce]);

  return {
    states: symbols.map((s) => ({ symbol: s, state: states[s] ?? ({ status: "idle" } as const) })),
    retry: () => setNonce((n) => n + 1),
  };
}

export function CompareView() {
  const router = useRouter();
  const search = useSearchParams();
  const { horizon } = usePreferences();
  const { recent } = useWorkspace();
  const guided = useDetail() === "simple";
  const symbols = useMemo(() => parseSymbolList(search?.get("symbols")), [search]);
  const { states, retry } = useColumns(symbols);
  const model: CompareModel = useMemo(() => buildCompare(states, horizon), [states, horizon]);

  // Remembered so "Compare" on a stock page adds to the set being built here.
  useEffect(() => { writeSession("compare:last", symbols); }, [symbols]);

  const go = useCallback((next: string[]) => router.replace(compareHref(next), { scroll: false }),
                         [router]);
  const move = (i: number, by: number) => {
    const next = [...symbols];
    const j = i + by;
    if (j < 0 || j >= next.length) return;
    [next[i], next[j]] = [next[j], next[i]];
    go(next);
  };

  const [draft, setDraft] = useState("");
  const [market, setMarket] = useState<Market>("US");
  const add = (raw: string, m: Market = market) => {
    const symbol = resolveSymbol(raw, m);
    if (!symbol || !isTicker(symbol) || symbols.includes(symbol) || symbols.length >= MAX_COMPARE) return;
    setDraft("");
    go([...symbols, symbol]);
  };

  useRegisterCommands("compare", symbols.map((s) => ({
    id: `compare:open:${s}`, group: "Go to" as const, label: `Open ${s} in all lenses`,
    run: () => router.push(stockHref(s)),
  })));

  const n = symbols.length;
  const gridStyle = { gridTemplateColumns: `minmax(9rem, 13rem) repeat(${n || 1}, minmax(0, 1fr))` };
  const suggestions = [...recent, ...PRESETS].filter((s) => !symbols.includes(s)).slice(0, 6);

  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <h1>Compare</h1>
        <p className="prose-col text-ash">
          Up to four companies, each read through the same lenses. Nothing is summed, scored or
          ranked — the columns stay in the order you put them, and what to make of the
          differences is yours.
        </p>
      </header>

      {n < MAX_COMPARE && (
        <form className="flex flex-col gap-2 sm:flex-row sm:items-center"
              onSubmit={(e) => { e.preventDefault(); add(draft); }}>
          <Input value={draft} onChange={(e) => setDraft(e.target.value)} aria-label="Add a ticker"
                 placeholder={n ? "Add another ticker" : "First ticker — AAPL, BBCA.JK"}
                 className="sm:max-w-xs" autoComplete="off" spellCheck={false} />
          <Select value={market} onChange={(e) => setMarket(e.target.value as Market)} aria-label="Market">
            <option value="US">US market</option>
            <option value="ID">IDX (.JK)</option>
          </Select>
          <Button type="submit" variant="secondary" disabled={!draft.trim()}>
            <Plus aria-hidden className="h-4 w-4" /> Add
          </Button>
          <span className="text-meta text-faint sm:ml-2">{n} of {MAX_COMPARE}</span>
        </form>
      )}
      {suggestions.length > 0 && n < MAX_COMPARE && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-meta text-faint">Add:</span>
          {suggestions.map((s) => (
            <Button key={s} variant="chip" size="xs" onClick={() => add(s, marketOf(s))}>{s}</Button>
          ))}
        </div>
      )}

      {n === 0 ? (
        <StateCard kind="empty" title="Nothing to compare yet">
          Add two to four tickers. Each column runs all four lenses on that company — the same
          read its own page gives — and the rows line up so the same question sits side by side.
        </StateCard>
      ) : (
        <>
          {model.currencyNote && <Note tone="warn">{model.currencyNote}</Note>}
          {n === 1 && <Note>Add at least one more company to read them side by side.</Note>}

          {/* ------------------------------------------- column headers */}
          <div className="sticky top-14 z-20 -mx-4 border-b border-rule bg-ink/95 px-4 py-3 backdrop-blur
                          supports-[backdrop-filter]:bg-ink/80 sm:-mx-6 sm:px-6 lg:-mx-8 lg:px-8">
            <div className="grid gap-3 max-lg:!grid-cols-2" style={gridStyle}>
              <div className="hidden items-end text-meta text-faint lg:flex">
                <Columns3 aria-hidden className="mr-2 h-4 w-4" /> In your order
              </div>
              {model.columns.map((col, i) => (
                <div key={col.symbol} className="min-w-0 rounded-lg border border-rule bg-panel px-3 py-2">
                  <div className="flex items-center gap-1">
                    <Link href={stockHref(col.symbol)}
                          className="num truncate text-base font-semibold text-chalk hover:text-tech">
                      {col.symbol}
                    </Link>
                    <span className="ml-auto flex shrink-0 items-center">
                      <IconButton label={`Move ${col.symbol} left`} disabled={i === 0}
                                  onClick={() => move(i, -1)}><ArrowLeft className="h-3.5 w-3.5" /></IconButton>
                      <IconButton label={`Move ${col.symbol} right`} disabled={i === n - 1}
                                  onClick={() => move(i, 1)}><ArrowRight className="h-3.5 w-3.5" /></IconButton>
                      <IconButton label={`Remove ${col.symbol}`}
                                  onClick={() => go(symbols.filter((s) => s !== col.symbol))}><X className="h-3.5 w-3.5" /></IconButton>
                    </span>
                  </div>
                  <p className="truncate text-micro text-ash">
                    {col.status === "ready" ? (col.name ?? "—")
                      : col.status === "error" ? "did not load" : "reading four lenses…"}
                    {col.currency && col.status === "ready" ? ` · ${col.currency}` : ""}
                  </p>
                  {col.status === "error" && (
                    <button type="button" onClick={retry}
                            className="mt-1 inline-flex min-h-[24px] items-center gap-1 text-micro text-tech hover:underline">
                      <RotateCw aria-hidden className="h-3 w-3" /> Try again
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* --------------------------------------------------- sections */}
          {model.sections.map((section) => (
            <section key={section.key} aria-labelledby={`compare-${section.key}`}
                     className="overflow-hidden rounded-xl border border-rule bg-panel">
              <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-rule px-5 py-3"
                   style={{ background: `color-mix(in srgb, ${section.hue} 7%, transparent)` }}>
                <h2 id={`compare-${section.key}`} className="text-h3" style={{ color: section.hue }}>
                  {section.title}
                </h2>
                <p className="text-meta text-ash">{section.question}</p>
              </div>
              <div className="divide-y divide-ruleSoft">
                {section.rows.map((r) => (
                  <div key={r.key} className="grid gap-3 px-5 py-3 max-lg:!grid-cols-1" style={gridStyle}>
                    <div className="eyebrow pt-1">{r.label}</div>
                    {r.cells.map((cell, i) => (
                      <Cell key={model.columns[i].symbol} cell={cell} symbol={model.columns[i].symbol}
                            status={model.columns[i].status} guided={guided} />
                    ))}
                  </div>
                ))}
              </div>
            </section>
          ))}

          <p className="prose-col text-meta leading-relaxed text-faint">
            Each column is the same read its own page gives, at the default settings. Open a
            column&apos;s page for every chart, control and caveat behind these lines.
          </p>
        </>
      )}
    </div>
  );
}

function IconButton({
  label, onClick, disabled, children,
}: { label: string; onClick: () => void; disabled?: boolean; children: React.ReactNode }) {
  return (
    <button type="button" aria-label={label} onClick={onClick} disabled={disabled}
            className="inline-flex h-7 w-7 items-center justify-center rounded text-faint transition-colors
                       hover:text-chalk disabled:opacity-30 focus:outline-none focus-visible:ring-2
                       focus-visible:ring-tech">
      <span aria-hidden>{children}</span>
    </button>
  );
}

function Cell({
  cell, symbol, status, guided,
}: { cell: CompareCell; symbol: string; status: string; guided: boolean }) {
  // On a phone the columns stack, so each cell names its company.
  const tag = <span className="num mr-2 text-micro text-faint lg:hidden">{symbol}</span>;
  if (status === "loading" || status === "idle") {
    return <div aria-hidden className="h-5 w-3/4 animate-pulseline rounded bg-rule" />;
  }
  if (status === "error") return <div className="text-meta text-faint">{tag}—</div>;
  return (
    <div className="min-w-0">
      {cell.items ? (
        <>
          {tag}
          <ul className="space-y-0.5 text-meta text-body">
            {cell.items.map((item) => <li key={item}>{item}</li>)}
          </ul>
        </>
      ) : (
        <div className="flex items-start gap-1.5">
          <span className={cn("text-base font-semibold",
                              /\d/.test(cell.text) && "num",
                              cell.tone ? TONE_TEXT[cell.tone] ?? "text-chalk" : "text-chalk")}>
            {tag}{cell.text}
          </span>
          {cell.explain && <Explain explain={cell.explain} />}
        </div>
      )}
      {cell.sentence && (
        <p className={cn("mt-1 text-meta leading-relaxed text-ash", guided && "line-clamp-3")}>
          {cell.sentence}
        </p>
      )}
    </div>
  );
}

