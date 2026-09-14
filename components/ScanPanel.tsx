"use client";

import { useMemo, useState } from "react";
import { Gauge, Lock, ShieldAlert, Telescope } from "lucide-react";
import { Card, CardBody, CardHeader, CardTitle, Explainer, Note } from "@/components/ui/card";
import { TONE_FIELD } from "@/components/ui/explain";
import { Button } from "@/components/ui/button";
import type { Engine, ScanResponse, ScanRow } from "@/lib/types";
import { cn, num } from "@/lib/utils";

/**
 * A market scan that already ran, shown in the app rather than left in a file.
 *
 * WHY THIS EXISTS: THE RESULTS WERE ONLY EVER A FILE ON DISK. The scan is a
 * script because a whole exchange takes about an hour and the serverless
 * function has sixty seconds — that constraint is real and unchanged. But the
 * RESULT is a JSON file that already exists, and for a week the only way to
 * read it was to open a seven-megabyte HTML report by hand. The owner of the
 * tool asked where the buy recommendations were and the honest answer was
 * "check the files yourself", which is not an interface.
 *
 * IT RUNS NOTHING. Every number here was computed by `scan_market.py` and is
 * read back unchanged.
 *
 * THREE RULES IT KEEPS, all inherited from the report it replaces.
 *
 * 1. THE NULL RESULT COMES FIRST. `provenance` renders above the table, not
 *    under it, because the ordering means something different depending on that
 *    paragraph. Same rule `VerdictPanel` follows for a single name.
 *
 * 2. A GATED NAME IS NEVER HIDDEN BY A GOOD SCORE. The score stays on screen
 *    beside the gate, because a reader overriding one has to see what they are
 *    overriding.
 *
 * 3. IT NEVER COLOURS FROM A NUMBER. Every tone is `row.tone`, decided once in
 *    Python.
 */

const ACTION_ORDER: Record<string, number> = {
  STRONG_BUY: 0, BUY: 1, HOLD: 2, REDUCE: 3, AVOID: 4, NO_ACTION: 5,
};

type Filter = "directional" | "buys" | "neglected" | "all";

const FILTERS: { id: Filter; label: string; hint: string }[] = [
  { id: "directional", label: "Says something", hint: "Everything but hold and gated" },
  { id: "buys", label: "Buys only", hint: "Strong buy and buy" },
  { id: "neglected", label: "Cheap & uncovered", hint: "The screen the blend cannot reach" },
  { id: "all", label: "Everything", hint: "Including gated and hold" },
];

function entryLabel(row: ScanRow): string {
  if (row.entry.ratioWithheld) return "stop in noise";
  if (row.entry.rewardRisk != null) return `${row.entry.rewardRisk.toFixed(1)}:1`;
  return row.entry.band ?? "—";
}

export function ScanPanel({ state, market, onSelect }: {
  state: Engine<ScanResponse>;
  market: string;
  onSelect: (ticker: string) => void;
}) {
  const [filter, setFilter] = useState<Filter>("directional");

  const rows = useMemo(() => {
    if (state.status !== "ready" || !state.data.available) return [];
    const all = state.data.rows ?? [];
    const picked = all.filter((row) => {
      if (filter === "all") return true;
      if (filter === "buys") return row.action === "BUY" || row.action === "STRONG_BUY";
      if (filter === "neglected") return row.neglected;
      return row.action !== "HOLD" && row.action !== "NO_ACTION";
    });
    return [...picked].sort((a, b) => {
      const byAction = (ACTION_ORDER[a.action] ?? 9) - (ACTION_ORDER[b.action] ?? 9);
      return byAction !== 0 ? byAction : (b.score ?? 0) - (a.score ?? 0);
    });
  }, [state, filter]);

  if (state.status === "loading" || state.status === "idle") {
    return (
      <Card>
        <CardBody className="py-5">
          <p className="text-base text-ash">Looking for a market scan on this machine…</p>
        </CardBody>
      </Card>
    );
  }

  if (state.status === "error") {
    return (
      <Card tone="warn">
        <CardBody className="py-5">
          <p className="text-base text-warn">
            Could not read the scan: {state.failure.message}
          </p>
        </CardBody>
      </Card>
    );
  }

  const data = state.data;

  // NO SCAN IS THE NORMAL STATE, not an error. A fresh checkout has none, and
  // the deployed app never will — `reports/` is local and gitignored. So this
  // says what to run rather than showing a broken panel.
  if (!data.available) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Telescope aria-hidden className="h-4 w-4" /> No market scan yet
          </CardTitle>
        </CardHeader>
        <CardBody>
          <p className="prose-col text-base leading-relaxed text-ash">{data.reason}</p>
        </CardBody>
      </Card>
    );
  }

  const counts = data.counts ?? {};
  const neglected = data.neglected;

  return (
    <div className="space-y-4">
      {/* RULE 1: the measurement before the ordering. */}
      {data.provenance?.headline && (
        <Card tone="warn">
          <CardBody className="py-4">
            <div className="eyebrow mb-1.5 flex items-center gap-1.5 text-warn">
              <ShieldAlert aria-hidden className="h-3 w-3" />
              What this ordering is worth — read before the table
            </div>
            <p className="prose-col text-base leading-relaxed text-body">
              {data.provenance.headline}
            </p>
          </CardBody>
        </Card>
      )}

      <Card accent="#7C8FA6">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Gauge aria-hidden className="h-4 w-4" />
            {market} market scan
          </CardTitle>
          <span className="font-mono text-micro text-ash">
            {data.generatedAt?.slice(0, 16).replace("T", " ")} · {data.file}
          </span>
        </CardHeader>
        <CardBody className="space-y-3">
          <div className="flex flex-wrap gap-2">
            {Object.entries(counts).map(([key, value]) => (
              <div key={key}
                   className="flex-1 basis-28 rounded-lg border border-ruleSoft bg-raised
                              px-3 py-2">
                <div className="eyebrow mb-0.5">{key}</div>
                <div className="num text-base font-semibold text-chalk">{value}</div>
              </div>
            ))}
          </div>

          {data.regime?.reading && (
            <p className="prose-col text-meta leading-relaxed text-ash">
              {data.regime.reading}
            </p>
          )}
          {data.concentration?.reading && (
            <p className="prose-col text-meta leading-relaxed text-ash">
              {data.concentration.reading}
            </p>
          )}
        </CardBody>
      </Card>

      {/* The screen for what the blend cannot reach, above the table because it
          is, by construction, not near the top of it. */}
      {neglected && neglected.selected > 0 && (
        <Card accent="#6FD0C0">
          <CardHeader>
            <CardTitle>Cheap, solid and uncovered</CardTitle>
            <span className="font-mono text-micro text-ash">
              {neglected.tradeable.length} tradeable of {neglected.selected}
            </span>
          </CardHeader>
          <CardBody className="space-y-2">
            {neglected.tradeable.length === 0 ? (
              <p className="prose-col text-meta leading-relaxed text-ash">
                Everything the screen selected is gated, which is the usual outcome: a
                company nobody covers is usually a company nobody trades.
              </p>
            ) : (
              neglected.tradeable.map((row) => (
                <button key={row.ticker} type="button"
                        onClick={() => onSelect(row.ticker)}
                        className="flex w-full flex-wrap items-baseline justify-between
                                   gap-x-4 gap-y-1 rounded border border-ruleSoft
                                   px-3 py-2 text-left hover:border-rule">
                  <span className="num text-base text-chalk">{row.ticker}</span>
                  <span className="flex-1 truncate text-meta text-ash">{row.name}</span>
                  <span className="text-meta text-faint">
                    value <span className="num text-body">{num(row.value, 0)}</span>
                    {" · "}quality <span className="num text-body">{num(row.quality, 0)}</span>
                    {row.institutionsHeld != null && (
                      <>{" · "}<span className="num text-body">
                        {(row.institutionsHeld * 100).toFixed(1)}%
                      </span> held</>
                    )}
                  </span>
                </button>
              ))
            )}
            <Note>{neglected.note}</Note>
          </CardBody>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Every name it scored</CardTitle>
          <span className="text-meta text-faint">{rows.length} shown</span>
        </CardHeader>
        <CardBody className="space-y-3 px-0">
          <div className="flex flex-wrap gap-1.5 px-5">
            {FILTERS.map((option) => (
              <button key={option.id} type="button" onClick={() => setFilter(option.id)}
                      aria-pressed={filter === option.id} title={option.hint}
                      className={cn(
                        "rounded-full border px-2.5 py-1 text-micro transition-colors",
                        filter === option.id
                          ? "border-rule bg-raised text-body"
                          : "border-ruleSoft text-faint")}>
                {option.label}
              </button>
            ))}
          </div>

          {rows.length === 0 ? (
            <p className="px-5 text-base text-ash">
              Nothing in this scan matches that filter.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-meta">
                <thead>
                  <tr className="eyebrow border-b border-rule
                                 [&>th]:px-5 [&>th]:py-2 [&>th]:font-normal">
                    <th>Ticker</th><th className="text-right">Score</th>
                    <th>Action</th><th>Conviction</th>
                    <th className="text-right">Coverage</th>
                    <th>Entry</th><th>Why not</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.ticker}
                        className="cursor-pointer border-b border-ruleSoft last:border-0
                                   hover:bg-raised"
                        onClick={() => onSelect(row.ticker)}>
                      <td className="px-5 py-2">
                        <span className="num text-body">{row.ticker}</span>
                        {row.neglected && (
                          <span className="ml-2 text-micro text-flow">uncovered</span>
                        )}
                        <div className="truncate text-micro text-faint">{row.name}</div>
                      </td>
                      <td className="num px-5 py-2 text-right text-chalk">
                        {row.score === null ? "—" : row.score.toFixed(1)}
                      </td>
                      <td className="px-5 py-2">
                        {/* RULE 3: the tone is the server's, never the number's. */}
                        <span className={cn("rounded-full border px-2 py-0.5 text-micro",
                                            TONE_FIELD[row.tone] ?? TONE_FIELD.none)}>
                          {row.actionLabel}
                        </span>
                      </td>
                      <td className="px-5 py-2 text-ash">{row.conviction}</td>
                      <td className="num px-5 py-2 text-right text-ash">
                        {(row.coverage * 100).toFixed(0)}%
                      </td>
                      <td className="num px-5 py-2 text-ash">{entryLabel(row)}</td>
                      {/* RULE 2: the gate shows beside the score, never instead. */}
                      <td className="px-5 py-2 text-faint">
                        {row.gates.length > 0 ? (
                          <span className="flex items-center gap-1">
                            <Lock aria-hidden className="h-3 w-3 shrink-0" />
                            {row.gates.map((g) => g.label).join("; ")}
                          </span>
                        ) : ""}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardBody>
      </Card>

      <Explainer summary="What this scan is, and what it is not">
        <p>
          Every figure here was computed by <code>scripts/scan_market.py</code> and is
          read back unchanged — the app runs nothing. A whole exchange takes about an
          hour, which is why it is a script and why this shows the last one rather than
          offering to start a new one.
        </p>
        {data.blendBacktest?.headline && (
          <p className="mt-2">{data.blendBacktest.headline}</p>
        )}
        {data.signalOverlap?.reading && (
          <p className="mt-2">{data.signalOverlap.reading}</p>
        )}
      </Explainer>

      <div className="flex justify-end">
        <Button type="button" onClick={() => onSelect(rows[0]?.ticker ?? "")}
                disabled={rows.length === 0}>
          Open the top name
        </Button>
      </div>
    </div>
  );
}
