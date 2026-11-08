"use client";

import { ArrowRight, Download, NotebookPen } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Entry, exportJournal } from "@/components/ThesisPanel";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle, Note } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { StateCard } from "@/components/ui/state";
import { useToast } from "@/components/ui/toaster";
import {
  JOURNAL_KEY, appendEntry, applyChange, readJournal, removeEntry,
  type JournalChange, type ThesisEntry,
} from "@/lib/journal";
import { stockHref } from "@/lib/url";
import { useT } from "@/lib/i18n";

/**
 * Every thesis the reader has written, for every company, as written.
 *
 * WHY A PAGE. The journal could only be read from the Thesis tab of the company
 * an entry was about, so the only way to see what you had written last month
 * was to remember which companies you had written about and load each one. The
 * count of other entries showed in the header and nothing else did.
 *
 * WHAT IT DOES NOT DO, deliberately, and for the reasons ThesisPanel gives:
 * there is no editing, no score, no profit and loss and no "how did you do".
 * Each entry links to its company's Thesis tab, which is where movement since
 * the entry is shown — against today's figures, labelled as movement and never
 * as a verdict. Nothing on this page loads a company, so nothing here measures
 * anything.
 *
 * In this browser only: the request layer cannot import the journal at all
 * (scripts/check_frontend.mjs).
 */
export function JournalView() {
  const t = useT();
  const toast = useToast();
  const [entries, setEntries] = useState<ThesisEntry[] | null>(null);
  const [filter, setFilter] = useState("");

  // Read on mount, not during render: the server renders this tree too and has
  // no localStorage.
  useEffect(() => {
    try { setEntries(readJournal(window.localStorage.getItem(JOURNAL_KEY))); }
    catch { setEntries([]); }
    // A thesis locked on a stock page in another tab appears here as it lands.
    const sync = (e: StorageEvent) => {
      if (e.key === JOURNAL_KEY || e.key === null) setEntries(readJournal(e.newValue));
    };
    window.addEventListener("storage", sync);
    return () => window.removeEventListener("storage", sync);
  }, []);

  // Every change is applied to what is stored at the moment of writing, never
  // to the copy this page read when it opened — see `applyChange`.
  const persist = (change: JournalChange) => {
    let stored: string | null = null;
    let readable = true;
    try { stored = window.localStorage.getItem(JOURNAL_KEY); } catch { readable = false; }
    const next = readable ? applyChange(stored, change) : change(entries ?? []);
    setEntries(next);
    try {
      window.localStorage.setItem(JOURNAL_KEY, JSON.stringify(next));
    } catch {
      toast({ message: t("Not saved — this browser would not store the change."), tone: "error" });
    }
  };

  const groups = useMemo(() => {
    const needle = filter.trim().toUpperCase();
    const map = new Map<string, ThesisEntry[]>();
    for (const entry of entries ?? []) {
      if (needle && !entry.ticker.includes(needle)) continue;
      map.set(entry.ticker, [...(map.get(entry.ticker) ?? []), entry]);
    }
    return [...map.entries()];
  }, [entries, filter]);

  if (entries === null) return <StateCard kind="loading" shape="lines" />;

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-2">
          <h1>{t("Thesis journal")}</h1>
          <p className="prose-col text-ash">
            {t("What you wrote down before acting, in the words you used at the time. Entries cannot be edited, and nothing here is ever scored.")}
          </p>
        </div>
        <Button variant="quiet" size="sm" onClick={() => exportJournal(entries)}
                disabled={entries.length === 0}>
          <Download aria-hidden className="h-3.5 w-3.5" />{" "}{t("Export as JSON")}
        </Button>
      </header>

      {entries.length === 0 ? (
        <StateCard kind="empty" level={2} title={t("No entries yet")}>
          {t("Open a company and use its Thesis tab to write down what has to be true and what would prove it wrong — before you act. Entries are kept in this browser only.")}
        </StateCard>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-3">
            <Input value={filter} onChange={(e) => setFilter(e.target.value)}
                   placeholder={t("Filter by ticker")} aria-label={t("Filter entries by ticker")}
                   className="h-9 max-w-[16rem]" />
            <span className="text-meta text-ash">
              {t("{length} entr{value} across {size} compan{value2}", { length: entries.length, value: entries.length === 1 ? "y" : "ies", size: new Set(entries.map((e) => e.ticker)).size, value2: new Set(entries.map((e) => e.ticker)).size === 1 ? "y" : "ies" })}
            </span>
          </div>

          {groups.length === 0 && (
            <StateCard kind="empty" level={2} title={t("No entry matches that ticker")} />
          )}

          {groups.map(([ticker, list]) => (
            <Card key={ticker} id={`journal-${ticker}`}>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <NotebookPen aria-hidden className="h-4 w-4 text-ash" />
                  <span className="num">{ticker}</span>
                </CardTitle>
                <Link href={stockHref(ticker, "thesis")}
                      className="inline-flex min-h-[24px] items-center gap-1.5 text-meta text-tech hover:underline">
                  {t("Open with today's figures")}
                  <ArrowRight aria-hidden className="h-3.5 w-3.5" />
                </Link>
              </CardHeader>
              <CardBody className="space-y-4 px-0">
                {list.map((entry) => (
                  <Entry key={entry.id} entry={entry} current={null}
                         onDelete={() => {
                           persist((current) => removeEntry(current, entry.id));
                           toast({ message: t("Entry on {ticker} deleted", { ticker }),
                                   action: { label: t("Undo"),
                                             onClick: () => persist((current) => appendEntry(current, entry)) } });
                         }} />
                ))}
              </CardBody>
            </Card>
          ))}
        </>
      )}

      <Note tone="warn">
        {t("Kept in this browser and nowhere else — one cleared cache, private window or new machine away from gone. Export it.")}
      </Note>
    </div>
  );
}
