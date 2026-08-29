"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Download, Lock, Trash2 } from "lucide-react";
import { Card, CardBody, CardHeader, CardTitle, Explainer, Note } from "@/components/ui/card";
import { ApplyButton, Field, NumberField, PercentField } from "@/components/ui/controls";
import { useHorizon } from "@/components/ui/horizon";
import {
  JOURNAL_KEY, appendEntry, contradictions, drift, newId, readJournal,
  type ThesisEntry, type ThesisSnapshot,
} from "@/lib/journal";
import { cn } from "@/lib/utils";

/**
 * What you believed, written down before you acted, and never edited after.
 *
 * NOTHING HERE REACHES A SERVER. Every other panel sends a ticker away and gets
 * a reading back; a thesis is what the reader thinks, which is nobody else's
 * business. It lives in this browser's storage beside the reading mode, the
 * holding horizon and the holdings list, and no request in this codebase carries
 * it. That is also why its logic sits in `lib/journal.ts` and is tested by
 * `scripts/check_frontend.mjs` rather than by pytest — the same route
 * `agreementOf` took, for the same reason.
 *
 * AN ENTRY CANNOT BE EDITED, and that is the feature rather than a missing one.
 * A thesis you can revise once you know how it turned out is a rationalisation
 * with a timestamp on it. The words you used before the outcome are the only
 * ones worth keeping, so saving appends and there is no update path. Deleting is
 * offered, because keeping something against someone's wishes is a different
 * kind of wrong.
 *
 * NOTHING IS EVER SCORED. Entries come back as written. Where the numbers have
 * moved since, the movement is reported as movement — never as a verdict on the
 * thesis that preceded it. A journal that graded itself would be a backtest of
 * one, on a sample the reader chose, with no control for what they left out;
 * this app refuses composites elsewhere on far better evidence than that.
 */

const THESIS = "#A78BFA";

export function ThesisPanel({
  ticker, snapshot,
}: {
  ticker: string;
  /** What the app is showing right now, frozen into an entry when one is saved. */
  snapshot: ThesisSnapshot;
}) {
  const horizon = useHorizon();
  const [entries, setEntries] = useState<ThesisEntry[]>([]);
  const [thesis, setThesis] = useState("");
  const [falsifier, setFalsifier] = useState("");
  // `null` from the field means "cleared", which is a stated absence rather
  // than a zero — and the checks below skip an absent belief rather than
  // comparing against a default one.
  const [growth, setGrowth] = useState<number | null>(null);
  const [size, setSize] = useState<number | null>(null);

  // Read on mount, not during render: the server renders this tree too and has
  // no localStorage.
  useEffect(() => {
    try {
      setEntries(readJournal(window.localStorage.getItem(JOURNAL_KEY)));
    } catch { /* private mode — an empty journal is the right default */ }
  }, []);

  const persist = (next: ThesisEntry[]) => {
    setEntries(next);
    try {
      window.localStorage.setItem(JOURNAL_KEY, JSON.stringify(next));
    } catch { /* storage full or disabled; the entry stays on screen this session */ }
  };

  const draft = useMemo(() => ({
    growthBelief: growth,
    positionShare: size,
    horizonYears: horizon,
    snapshot,
  }), [growth, size, horizon, snapshot]);
  const live = contradictions(draft);

  const forTicker = entries.filter((e) => e.ticker === ticker.toUpperCase());
  const ready = ticker && thesis.trim().length > 0 && falsifier.trim().length > 0;

  const save = () => {
    const now = new Date();
    persist(appendEntry(entries, {
      id: newId(now, ticker),
      ticker: ticker.toUpperCase(),
      written: now.toISOString(),
      thesis: thesis.trim(),
      falsifier: falsifier.trim(),
      growthBelief: growth ?? null,
      horizonYears: horizon,
      positionShare: size ?? null,
      snapshot,
    }));
    setThesis("");
    setFalsifier("");
  };

  const exportAll = () => {
    const blob = new Blob([JSON.stringify(entries, null, 2)],
                          { type: "application/json;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `quantdesk-thesis-journal-${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-4 animate-rise">
      <Card accent={THESIS}>
        <CardHeader>
          <CardTitle>Write it down before you act</CardTitle>
          <span className="font-mono text-micro text-ash">
            {entries.length} entr{entries.length === 1 ? "y" : "ies"}, in this browser only
          </span>
        </CardHeader>
        <CardBody className="space-y-4">
          <Explainer summary="Saved entries cannot be edited, and nothing here is ever scored"
                     defaultOpen>
            The point of writing it down is that the version you wrote <em>before</em> you knew
            the outcome is still there afterwards, in the words you actually used. So each entry
            is timestamped, saved alongside what the app was showing at the time, and locked.
            {" "}There is no verdict, no profit and loss, and no marking of your own homework.
          </Explainer>

          <div className="space-y-1.5">
            <span className="eyebrow">What has to be true for this to work?</span>
            <textarea
              value={thesis}
              onChange={(e) => setThesis(e.target.value)}
              rows={3}
              aria-label="What has to be true"
              placeholder="The specific thing you are betting on."
              className="w-full rounded border border-rule bg-ink px-3 py-2 text-meta
                         leading-relaxed text-chalk placeholder:text-faint
                         focus:border-tech/60 focus:outline-none
                         focus-visible:ring-1 focus-visible:ring-tech"
            />
          </div>

          <div className="space-y-1.5">
            <span className="eyebrow">What would tell you it is wrong?</span>
            <textarea
              value={falsifier}
              onChange={(e) => setFalsifier(e.target.value)}
              rows={2}
              aria-label="What would falsify this"
              placeholder="Something observable, that you would actually notice."
              className="w-full rounded border border-rule bg-ink px-3 py-2 text-meta
                         leading-relaxed text-chalk placeholder:text-faint
                         focus:border-tech/60 focus:outline-none
                         focus-visible:ring-1 focus-visible:ring-tech"
            />
            <Note>
              A thesis with nothing that could disprove it is a hope. If no observation would
              change your mind, this will still save — but you will read it back one day and
              know.
            </Note>
          </div>

          <div className="flex flex-wrap items-end gap-3">
            <Field label="Growth you expect"
                   hint="A year, for five years. Compared with what the price requires.">
              <PercentField value={growth ?? undefined} onChange={setGrowth} />
            </Field>
            <Field label="Position size"
                   hint="Share of the account. Checked against this stock's own worst fall.">
              <PercentField value={size ?? undefined} onChange={setSize} />
            </Field>
            <Field label="Horizon" hint="Set on the bar above the tabs.">
              <NumberField value={horizon} onChange={() => undefined} min={1} max={10} />
            </Field>
            <ApplyButton onClick={save} disabled={!ready}>Lock this entry</ApplyButton>
          </div>
          {!ready && (
            <Note>
              Both halves are needed. Half a thesis reads back later as agreement with whatever
              happened to occur.
            </Note>
          )}
        </CardBody>
      </Card>

      {live.length > 0 && (
        <Card accent="#F2C14E">
          <CardHeader>
            <CardTitle>Where this disagrees with the page</CardTitle>
            <span className="font-mono text-micro text-ash">before you save</span>
          </CardHeader>
          <CardBody className="space-y-2.5">
            {live.map((c) => (
              <div key={c.key}>
                <span className="text-base font-semibold text-warn">{c.title}. </span>
                <span className="text-base leading-relaxed text-body">{c.detail}</span>
              </div>
            ))}
            <Note>
              Disagreeing with the model is a perfectly respectable thing to do — the
              price-implied growth figure exists to be argued with. Disagreeing without
              noticing is not, and that is all this names.
            </Note>
          </CardBody>
        </Card>
      )}

      {forTicker.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>What you wrote about {ticker.toUpperCase()}</CardTitle>
            <span className="font-mono text-micro text-ash">as written, unedited</span>
          </CardHeader>
          <CardBody className="space-y-4 px-0">
            {forTicker.map((entry) => (
              <Entry key={entry.id} entry={entry} current={snapshot}
                     onDelete={() => persist(entries.filter((e) => e.id !== entry.id))} />
            ))}
          </CardBody>
        </Card>
      )}

      <Card>
        <CardHeader><CardTitle>Where this is kept</CardTitle></CardHeader>
        <CardBody className="space-y-3">
          <p className="prose-col text-meta leading-relaxed text-ash">
            In this browser and nowhere else. It is never sent anywhere — not even to draw the
            checks above, which run here on your own machine.
          </p>
          <Note tone="warn">
            Which also means it is one cleared cache, one private window or one new machine
            away from gone. Export it.
          </Note>
          <button
            type="button"
            onClick={exportAll}
            disabled={entries.length === 0}
            className={cn(
              "inline-flex h-9 items-center gap-2 rounded border border-rule px-4",
              "font-mono text-micro uppercase tracking-[0.14em] text-chalk",
              "transition-colors hover:border-tech/60 disabled:cursor-not-allowed",
              "disabled:opacity-40 focus:outline-none focus-visible:ring-1 focus-visible:ring-tech",
            )}
          >
            <Download aria-hidden className="h-3.5 w-3.5" />
            Export as JSON
          </button>
        </CardBody>
      </Card>
    </div>
  );
}

function Entry({
  entry, current, onDelete,
}: { entry: ThesisEntry; current: ThesisSnapshot; onDelete: () => void }) {
  const moved = drift(entry, current);
  const written = contradictions(entry);

  return (
    <div className="border-t border-rule px-5 pt-4 first:border-0 first:pt-0">
      <div className="mb-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <Lock aria-label="locked" className="h-3 w-3 text-ash" />
        <span className="num text-micro text-ash">
          {new Date(entry.written).toLocaleString()}
        </span>
        <span className="text-micro text-ash">
          {entry.horizonYears}-year horizon
          {entry.growthBelief != null && `, expecting ${(entry.growthBelief * 100).toFixed(0)}% a year`}
          {entry.positionShare != null && `, ${(entry.positionShare * 100).toFixed(0)}% of the account`}
        </span>
        <button type="button" onClick={onDelete}
                aria-label="Delete this entry"
                className="-mr-1 ml-auto inline-flex h-6 w-6 shrink-0 items-center
                           justify-center rounded text-ash transition-colors hover:bg-dist/10
                           hover:text-dist
                           focus:outline-none focus-visible:ring-1 focus-visible:ring-tech">
          <Trash2 aria-hidden className="h-3.5 w-3.5" />
        </button>
      </div>

      <p className="text-base leading-relaxed text-body">{entry.thesis}</p>
      <p className="mt-1.5 text-meta leading-relaxed text-ash">
        <span className="eyebrow mr-1.5">Wrong if</span>{entry.falsifier}
      </p>

      {written.length > 0 && (
        <ul className="mt-2 space-y-1">
          {written.map((c) => (
            <li key={c.key} className="flex gap-2 text-meta leading-relaxed text-ash">
              <AlertTriangle aria-hidden className="mt-0.5 h-3 w-3 shrink-0 text-warn/70" />
              <span>{c.title}, at the time of writing.</span>
            </li>
          ))}
        </ul>
      )}

      {moved.length > 0 && (
        <div className="mt-3 rounded border border-rule bg-raised/60 px-3 py-2">
          <div className="eyebrow mb-1.5">What has moved since</div>
          <ul className="space-y-1">
            {moved.map((d) => (
              <li key={d.key} className="flex items-baseline gap-2 text-micro">
                <span className="text-ash">{d.label}</span>
                <span className="num ml-auto text-ash">{d.then}</span>
                <span className="text-ash">&rarr;</span>
                <span className="num text-body">{d.now}</span>
              </li>
            ))}
          </ul>
          <p className="mt-1.5 text-meta leading-relaxed text-ash">
            Movement, not a verdict. Nothing here says whether the thesis was right.
          </p>
        </div>
      )}
    </div>
  );
}
