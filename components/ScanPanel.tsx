"use client";

import { useMemo, useState } from "react";
import { ArrowDown, Gauge, Lock, ShieldAlert, Telescope } from "lucide-react";
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

type SortKey = "default" | "score" | "growth" | "margin" | "coverage" | "field";

/**
 * What each sortable column sorts on. `null` means UNKNOWN, and unknown sorts
 * LAST in both directions rather than at one end.
 *
 * That is not a nicety. A name whose revenue growth did not read is not the
 * slowest-growing company in the market, and letting it settle at the bottom of
 * a descending sort would say exactly that — the same conflation of a gap with
 * a finding that this codebase keeps having to undo. Sorting it to the end in
 * both directions leaves it visible and uninterpreted.
 */
const SORT_VALUE: Record<Exclude<SortKey, "default" | "field">,
                         (row: ScanRow) => number | null> = {
  score: (row) => row.score,
  growth: (row) => row.record?.revenueCagr ?? null,
  margin: (row) => row.record?.netMargin ?? null,
  coverage: (row) => row.coverage,
};

function compareRows(a: ScanRow, b: ScanRow, key: SortKey): number {
  if (key === "default") {
    const byAction = (ACTION_ORDER[a.action] ?? 9) - (ACTION_ORDER[b.action] ?? 9);
    return byAction !== 0 ? byAction : (b.score ?? 0) - (a.score ?? 0);
  }
  if (key === "field") {
    // Leaders first, then sole listings, then alphabetically by label — so the
    // column groups the names doing the same thing next to each other.
    const rank = (row: ScanRow) =>
      row.field?.leads ? 0 : row.field?.soleListing ? 1 : 2;
    const byRank = rank(a) - rank(b);
    if (byRank !== 0) return byRank;
    return (a.industry ?? "\uffff").localeCompare(b.industry ?? "\uffff");
  }
  const left = SORT_VALUE[key](a);
  const right = SORT_VALUE[key](b);
  if (left === null && right === null) return 0;
  if (left === null) return 1;      // unknown last, always
  if (right === null) return -1;
  return right - left;              // largest first
}

type Filter =
  | "directional" | "buys" | "neglected" | "leaders" | "sole" | "compounding" | "all";

const FILTERS: { id: Filter; label: string; hint: string }[] = [
  { id: "directional", label: "Says something", hint: "Everything but hold and gated" },
  { id: "buys", label: "Buys only", hint: "Strong buy and buy" },
  { id: "neglected", label: "Cheap & uncovered", hint: "The screen the blend cannot reach" },
  { id: "leaders", label: "Leads its field",
    hint: "Largest of the scanned names sharing its industry label, by 2x or more" },
  { id: "sole", label: "No listed rival",
    hint: "The only scanned name carrying its industry label" },
  { id: "compounding", label: "Profitable & growing",
    hint: "Profitable every year the filings cover, cash-backed, and growing revenue "
        + "in this market's top quartile" },
  { id: "all", label: "Everything", hint: "Including gated and hold" },
];

/**
 * Everything about a row a specialist search should reach.
 *
 * THE DESCRIPTION IS IN HERE BECAUSE THE INDUSTRY LABEL IS NOT ENOUGH, and the
 * gap is not marginal. KETR.JK is labelled "Communication Equipment" — shared
 * with radio makers and handset distributors — and the thing that actually
 * identifies it, "sells submarine and terrestrial fiber optic cable systems",
 * exists only in the prose. No label search finds it.
 */
function searchableText(row: ScanRow): string {
  return [row.ticker, row.name, row.sector, row.industry, row.summary]
    .filter(Boolean).join(" · ").toLowerCase();
}

/**
 * The sentence a search matched, rather than the opening of the description.
 *
 * Searching "submarine" and being shown "PT Ketrosden Triasmitra operates as a
 * telecommunication infrastructure company" answers a question nobody asked.
 * The match is the point, so the match is what shows.
 */
function matchedSentence(text: string | null, needle: string): string | null {
  if (!text || !needle) return null;
  const at = text.toLowerCase().indexOf(needle);
  if (at < 0) return null;
  const start = Math.max(0, text.lastIndexOf(". ", at) + 1);
  const dot = text.indexOf(". ", at + needle.length);
  const end = dot < 0 ? text.length : dot + 1;
  return text.slice(start, end).trim();
}

/**
 * The filing record as one cell: years profitable, and the growth rate.
 *
 * ALWAYS "n of m", never "profitable". Two thirds of this exchange is
 * profitable in every year its filings cover, so the bare word is not a
 * distinction — the denominator is what makes the figure readable, and it also
 * carries how short the window is.
 */
function recordLabel(row: ScanRow): string {
  const r = row.record;
  if (!r || r.years == null) return "—";
  const profit = `${r.yearsProfitable ?? 0}/${r.years} yrs profitable`;
  if (r.revenueCagr == null) return profit;
  const sign = r.revenueCagr >= 0 ? "+" : "";
  return `${profit} · ${sign}${(r.revenueCagr * 100).toFixed(0)}%/yr`;
}

/** The industry and the standing in it, as one line. Never the rank alone: a
 *  rank without its peer count is not interpretable. */
function fieldLabel(row: ScanRow): string {
  if (!row.industry) return "—";
  const place = row.field;
  if (!place?.rank || !place.peers) return row.industry;
  return `${row.industry} · ${place.rank} of ${place.peers}`;
}

function entryLabel(row: ScanRow): string {
  if (row.entry.ratioWithheld) return "stop in noise";
  if (row.entry.rewardRisk != null) return `${row.entry.rewardRisk.toFixed(1)}:1`;
  return row.entry.band ?? "—";
}

/**
 * A column header that sorts, and says whether it is sorting.
 *
 * `aria-sort` goes on the `th`, which is what a screen reader announces; the
 * button inside is what takes focus and the keyboard. Clicking the active
 * column returns to the report's own ordering rather than reversing — the
 * default is action-then-score, which is an ORDER OF PRECEDENCE rather than a
 * direction, and there is no meaningful ascending version of it.
 */
function SortHeader({ label, sortKey, sort, onSort, align = "left" }: {
  label: string;
  sortKey: SortKey;
  sort: SortKey;
  onSort: (key: SortKey) => void;
  align?: "left" | "right";
}) {
  const active = sort === sortKey;
  return (
    <th aria-sort={active ? "descending" : "none"}
        className={align === "right" ? "text-right" : undefined}>
      <button type="button" onClick={() => onSort(active ? "default" : sortKey)}
              title={active
                ? `Sorted by ${label.toLowerCase()}, largest first. Click to return to `
                  + "the scan's own ordering."
                : `Sort by ${label.toLowerCase()}, largest first. Names this did not `
                  + "read for go last, not lowest."}
              className={cn("eyebrow inline-flex items-center gap-1 hover:text-body",
                            active ? "text-body" : "text-inherit")}>
        {label}
        <ArrowDown aria-hidden
                   className={cn("h-3 w-3 transition-opacity",
                                 active ? "opacity-100" : "opacity-0")} />
      </button>
    </th>
  );
}

export function ScanPanel({ state, market, onSelect }: {
  state: Engine<ScanResponse>;
  market: string;
  onSelect: (ticker: string) => void;
}) {
  const [filter, setFilter] = useState<Filter>("directional");
  const [sort, setSort] = useState<SortKey>("default");
  const [query, setQuery] = useState("");
  const needle = query.trim().toLowerCase();

  const rows = useMemo(() => {
    if (state.status !== "ready" || !state.data.available) return [];
    const all = state.data.rows ?? [];
    const picked = all.filter((row) => {
      // A SEARCH IGNORES THE ACTION FILTER, DELIBERATELY. Looking up who lays
      // submarine cable is a lookup, not a refinement of the current view, and
      // the name being looked for is usually a Hold — that is the whole premise
      // of the screen next door. Intersecting the two would hide the answer and
      // give no sign it had.
      if (needle) return searchableText(row).includes(needle);
      if (filter === "all") return true;
      if (filter === "buys") return row.action === "BUY" || row.action === "STRONG_BUY";
      if (filter === "neglected") return row.neglected;
      if (filter === "leaders") return row.field?.leads === true;
      if (filter === "sole") return row.field?.soleListing === true;
      // THE CONJUNCTION, NOT THE FIRST CONDITION. "Profitable every year" alone
      // is true of two thirds of this exchange; see `trackrecord.py`.
      if (filter === "compounding") {
        const r = row.record;
        return !!r && r.everyYearProfitable && r.operatingCashFlowPositive && r.growing;
      }
      return row.action !== "HOLD" && row.action !== "NO_ACTION";
    });
    return [...picked].sort((a, b) => compareRows(a, b, sort));
  }, [state, filter, needle, sort]);

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
  const rejectedByReason = data.rejectedByReason;
  const neglected = data.neglected;
  const specialists = data.specialists;

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
          {/* Every value here is a number because the route guarantees it — see
              `GET /api/scan/latest`. It did not always, and a nested map
              rendered as a child blanked this whole page behind an error
              boundary. The breakdown renders below, as the sentence it is. */}
          <div className="flex flex-wrap gap-2">
            {Object.entries(counts).map(([key, value]) => (
              <div key={key}
                   className="flex-1 basis-28 rounded-lg border border-ruleSoft
                              bg-raised px-3 py-2">
                <div className="eyebrow mb-0.5">{key}</div>
                <div className="num text-base font-semibold text-chalk">{value}</div>
              </div>
            ))}
          </div>

          {rejectedByReason && (
            <p className="prose-col text-meta leading-relaxed text-ash">
              Not scored:{" "}
              {Object.entries(rejectedByReason)
                .sort((a, b) => b[1] - a[1])
                .map(([reason, n]) => `${n} ${reason}`)
                .join(", ")}.
            </p>
          )}

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

      {/* THE ANSWER, ABOVE THE INGREDIENTS. The two cards below and the table
          supply the parts — what a company does, who else does it, what the
          filings say, who is watching. This is their intersection, and it is
          first because a reader who wants the parts can read on. */}
      {specialists && specialists.selected > 0 && (
        <Card accent="#C9A227">
          <CardHeader>
            <CardTitle>Profitable specialists nobody is covering</CardTitle>
            <span className="font-mono text-micro text-ash">
              {specialists.tradeable.length} tradeable of {specialists.selected}
            </span>
          </CardHeader>
          <CardBody className="space-y-2.5">
            {specialists.tradeable.length === 0 ? (
              <p className="prose-col text-meta leading-relaxed text-ash">
                Every name this found is gated as untradeable, which is the usual
                outcome — a specialist nobody covers is usually a specialist nobody
                trades.
              </p>
            ) : (
              specialists.tradeable.map((row) => (
                <button key={row.ticker} type="button"
                        onClick={() => onSelect(row.ticker)}
                        className="block w-full rounded border border-ruleSoft px-3 py-2.5
                                   text-left hover:border-rule">
                  <span className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                    <span className="num text-base text-chalk">{row.ticker}</span>
                    <span className="flex-1 truncate text-meta text-ash">{row.name}</span>
                    <span className="num text-meta text-body">
                      {row.revenueCagr == null
                        ? "—"
                        : `${row.revenueCagr >= 0 ? "+" : ""}${(row.revenueCagr * 100).toFixed(0)}%/yr`}
                    </span>
                  </span>
                  <span className="mt-1 block text-micro text-faint">
                    <span className="text-flow">
                      {row.soleListing
                        ? "only listed name in"
                        : `largest of ${row.fieldPeers ?? "?"} in`}
                    </span>
                    {" "}{row.industry ?? "an unstated field"}
                    {" · "}{row.yearsProfitable}/{row.yearsAvailable} yrs profitable
                    {row.netMargin != null
                      && ` · ${(row.netMargin * 100).toFixed(1)}% net margin`}
                    {row.analysts != null && ` · ${row.analysts} analysts`}
                  </span>
                  {row.summary && (
                    <span className="mt-1.5 block max-w-prose text-meta leading-relaxed
                                     text-ash">
                      {row.summary}
                    </span>
                  )}
                </button>
              ))
            )}
            {/* The base rates, because the intersection reads as three demanding
                tests and one of them admits most of a small exchange. */}
            <Note>
              Of the {specialists.baseRates.scanned} names scanned,
              {" "}{(specialists.baseRates.specialist * 100).toFixed(0)}% are the largest
              or the only name in their field,
              {" "}{(specialists.baseRates.compounding * 100).toFixed(0)}% are profitable
              every year with cash behind it and growing in this market&apos;s top
              quartile, and {(specialists.baseRates.unattended * 100).toFixed(0)}% are
              uncovered — which is the loosest of the three by a distance.
              {" "}{specialists.note}
            </Note>
          </CardBody>
        </Card>
      )}

      {/* The screen for what the blend cannot reach, above the table because it
          is, by construction, not near the top of it. */}
      {neglected && neglected.selected > 0 && (
        <Card accent="#6FD0C0">
          <CardHeader>
            <CardTitle>Cheap, solid and uncovered</CardTitle>
            <span className="font-mono text-micro text-ash">
              {neglected.tradeable.length} tradeable of {neglected.selected}
              {neglected.leadTheirField ? `, ${neglected.leadTheirField} lead a field` : ""}
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
                  {/* WHAT IT ACTUALLY SELLS. The screen above says cheap, solid
                      and unwatched; none of those says what the business is,
                      and that is the half a reader cannot get from a ratio. */}
                  <span className="w-full text-micro text-faint">
                    {row.industry && (
                      <span className="text-ash">{row.industry}</span>
                    )}
                    {row.leadsField && row.fieldPeers != null && (
                      <span className="ml-1.5 text-flow">
                        largest of {row.fieldPeers} scanned
                      </span>
                    )}
                    {row.summary && (
                      <span className="mt-1 block max-w-prose text-meta leading-relaxed
                                       text-ash">
                        {row.summary}
                      </span>
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
          <div className="px-5">
            <label className="block">
              <span className="eyebrow mb-1 block">
                Search what the companies actually do
              </span>
              <input
                type="search" value={query} inputMode="search"
                onChange={(event) => setQuery(event.target.value)}
                placeholder="submarine cable, geothermal, cement, cold storage…"
                className="w-full rounded-lg border border-ruleSoft bg-raised px-3 py-2
                           text-[1rem] text-chalk placeholder:text-faint
                           focus:border-rule focus:outline-none"
              />
            </label>
            {needle && (
              <p className="prose-col mt-1.5 text-meta leading-relaxed text-faint">
                {rows.length === 0
                  ? `No description in this scan mentions “${query.trim()}”.`
                  : `${rows.length} of ${state.data.rows?.length ?? 0} scored names
                     mention “${query.trim()}”.`}
                {" "}Searching every scored name, not just the current filter — a
                specialist is usually a Hold. This reads the description the data
                source publishes, which is a summary and not a full account of what a
                company does, so an absence here is not evidence.
              </p>
            )}
          </div>

          <div className="flex flex-wrap gap-1.5 px-5">
            {FILTERS.map((option) => (
              <button key={option.id} type="button" onClick={() => setFilter(option.id)}
                      aria-pressed={filter === option.id && !needle} title={option.hint}
                      disabled={needle.length > 0}
                      className={cn(
                        "rounded-full border px-2.5 py-1 text-micro transition-colors",
                        needle
                          ? "border-ruleSoft text-faint opacity-40"
                          : filter === option.id
                            ? "border-rule bg-raised text-body"
                            : "border-ruleSoft text-faint")}>
                {option.label}
              </button>
            ))}
          </div>

          {rows.length === 0 ? (
            <p className="px-5 text-base text-ash">
              {needle
                ? `Nothing in this scan mentions “${query.trim()}”. The scan covers
                   ${state.data.rows?.length ?? 0} names on this exchange, so a
                   specialist listed elsewhere, or one whose filings did not arrive,
                   would not be here either.`
                : "Nothing in this scan matches that filter."}
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-meta">
                <thead>
                  <tr className="eyebrow border-b border-rule
                                 [&>th]:px-5 [&>th]:py-2 [&>th]:font-normal">
                    <th>Ticker</th>
                    <SortHeader label="Score" sortKey="score" align="right"
                                sort={sort} onSort={setSort} />
                    <th>Action</th>
                    <SortHeader label="Business" sortKey="field"
                                sort={sort} onSort={setSort} />
                    <SortHeader label="Record" sortKey="growth"
                                sort={sort} onSort={setSort} />
                    <th>Conviction</th>
                    <SortHeader label="Coverage" sortKey="coverage" align="right"
                                sort={sort} onSort={setSort} />
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
                      {/* WHAT IT SELLS, AND WHERE IT STANDS AMONG THE NAMES
                          SELLING IT. `title` carries the provider's description
                          and the standing's own sentence; the caveat that this
                          is not market share is under the table, where it
                          cannot be scrolled away from the ranks. */}
                      <td className="px-5 py-2 text-ash"
                          title={[row.summary, row.field?.reading]
                                   .filter(Boolean).join("\n\n") || undefined}>
                        {/* THE LABEL IS A WAY INTO THE FIELD, not just a note.
                            "1 of 7" invites the question "which seven", and the
                            answer is one click away. `stopPropagation` because
                            the row itself opens the company. */}
                        {row.industry ? (
                          <button type="button"
                                  onClick={(event) => {
                                    event.stopPropagation();
                                    setQuery(row.industry ?? "");
                                  }}
                                  title={`Show the other scanned names in ${row.industry}`}
                                  className="block max-w-56 truncate text-left
                                             hover:text-body hover:underline">
                            {fieldLabel(row)}
                          </button>
                        ) : (
                          <span className="block max-w-56 truncate">{fieldLabel(row)}</span>
                        )}
                        {row.field?.leads && (
                          <span className="text-micro text-flow">largest of its field</span>
                        )}
                        {/* The sentence that matched, not the opening of the
                            description — see `matchedSentence`. */}
                        {needle && matchedSentence(row.summary, needle) && (
                          <span className="mt-0.5 block max-w-96 text-meta
                                           leading-relaxed text-faint">
                            {matchedSentence(row.summary, needle)}
                          </span>
                        )}
                      </td>
                      {/* RULE 3 APPLIES HERE TOO: no colour is taken from the
                          growth rate's sign. The only accent is on a state
                          Python decided — `growing`, which is the market's own
                          top quartile. */}
                      <td className="num px-5 py-2 text-ash"
                          title={row.record?.reading ?? undefined}>
                        <span className="block whitespace-nowrap">{recordLabel(row)}</span>
                        {row.record && !row.record.operatingCashFlowPositive && (
                          <span className="block text-micro text-faint">
                            no cash from ops
                          </span>
                        )}
                        {/* `netCash === true` only. Null means the question does
                            not apply to a lender, and false is just "borrows",
                            which most of the market does. */}
                        {row.record?.netCash === true && (
                          <span className="block text-micro text-faint">net cash</span>
                        )}
                        {row.record?.netDebtToEbitda != null && (
                          <span className="block text-micro text-faint">
                            {row.record.netDebtToEbitda.toFixed(1)}x net debt
                          </span>
                        )}
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

          {/* A RANK RENDERED WITHOUT THIS READS AS MARKET SHARE, which nothing
              here measures. It sits under the table rather than in the
              explainer because the explainer is collapsed by default and this
              is the condition on every number in the Business column. */}
          {!data.fields && rows.length > 0 && (
            <div className="px-5">
              <Note>
                This scan was written before the app recorded what each company does,
                so the Business column is empty rather than unknown — re-running the
                scan fills it. Nothing else here is affected.
              </Note>
            </div>
          )}

          {filter === "compounding" && !needle && (
            <div className="px-5">
              <Note>
                Profitable in every year the filings cover is true of about two thirds
                of this exchange, so it is not on its own a distinction. This filter is
                the conjunction — profitable every year, operating cash flow positive,
                and revenue compounding at or above the market&apos;s own top quartile —
                which about one name in seven meets. The window is whatever the filings
                cover, typically four years, which does not span a cycle.
              </Note>
            </div>
          )}

          {data.fields?.basis && (
            <div className="px-5">
              <Note>
                {data.fields.basis}
                {data.fields.unplaced > 0 && (
                  <> {data.fields.unplaced} of the scanned names could not be placed in
                  any field at all — no industry label, or no revenue comparable with
                  its peers — so a field with few members may simply be missing its
                  real leader.</>
                )}
              </Note>
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
