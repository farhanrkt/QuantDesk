/**
 * The compare view's rows: two to four companies, each read the same way.
 * ======================================================================
 *
 * A COMPARISON THAT NEVER DECIDES. Placing companies side by side is exactly
 * where an app drifts into "which is best" — a highlighted column, a sort, a
 * row of totals, a winner. PRODUCT.md constraint 1 refuses that on the single-
 * company view and the same refusal is extended here, enforced rather than
 * intended:
 *
 *   - Columns come out in the order the reader gave. Nothing here sorts, and
 *     check_frontend.mjs rule 14 fails the build if a compare file calls
 *     `.sort(`, `toSorted(`, `Math.max` or `.reduce(`.
 *   - Every cell carries the SERVER's tone for its own company and nothing
 *     else. No figure is computed across columns, so no cell can say "highest".
 *   - `agreementOf` is not used. "2 of 2 independent readings" beside "1 of 2"
 *     is a cross-company count — the composite the rail refuses, arriving
 *     through a layout.
 *   - The private scanner's score is never read.
 *
 * MIXED CURRENCIES ARE LEFT MIXED. Each column speaks in its listing's own
 * currency and the view says so; converting rupiah to dollars at today's rate
 * to make a column "comparable" would invent a number no lens computed.
 *
 * Pure: compiled into the frontend assertions and pinned there.
 */
import {
  readAnomaly, readQuality, readTechnical, readValuation, voteTone,
} from "@/components/ConfluenceRail";
import { palette } from "./palette";
import type {
  ConfluenceResponse, Engine, EngineFailure, Explanation, Leg,
} from "./types";
import { compact, pct, signedPct, verdictLabel } from "./utils";

export interface CompareCell {
  /** What the cell says, formatted. "—" when the company has no reading here. */
  text: string;
  /** The server's tone for THIS company's figure, or null where none applies. */
  tone: string | null;
  /** One sentence of context, from the lens or the explanation layer. */
  sentence?: string;
  explain?: Explanation;
  /** A list rather than one value — the pre-trade conditions that fired. */
  items?: string[];
}

export interface CompareRow { key: string; label: string; cells: CompareCell[] }

export interface CompareSection {
  key: "company" | "flow" | "trend" | "value" | "quality" | "pretrade";
  title: string;
  question: string;
  hue: string;
  rows: CompareRow[];
}

export interface CompareColumn {
  symbol: string;
  status: Engine<ConfluenceResponse>["status"];
  name: string | null;
  currency: string | null;
  error: string | null;
}

export interface CompareModel {
  columns: CompareColumn[];
  sections: CompareSection[];
  currencyNote: string | null;
}

const EMPTY: CompareCell = { text: "—", tone: null };

// Spelled out rather than narrowed on `leg.ok`: the assertion compile in
// check_frontend.mjs runs without strictNullChecks, where that narrowing fails.
const fromLeg = <T,>(leg: Leg<T> | undefined): Engine<T> => {
  if (!leg) return { status: "idle" };
  if (leg.ok === true) return { status: "ready", data: (leg as { ok: true; data: T }).data };
  const error = (leg as { ok: false; error: string | EngineFailure }).error;
  return { status: "error", failure: typeof error === "string" ? { message: error } : error };
};

const fromExplain = (e: Explanation | undefined, fallback?: string): CompareCell =>
  e ? { text: e.valueText ?? fallback ?? "—", tone: e.tone ?? null, sentence: e.reading, explain: e }
    : EMPTY;

/** Build every row for `columns`, in the order given. */
export function buildCompare(
  columns: { symbol: string; state: Engine<ConfluenceResponse> }[],
  horizon: number,
): CompareModel {
  const payloads = columns.map((c) => (c.state.status === "ready" ? c.state.data : null));
  const legs = payloads.map((p) => ({
    anomaly: fromLeg(p?.anomaly), technical: fromLeg(p?.technical),
    valuation: fromLeg(p?.valuation), quality: fromLeg(p?.quality),
    company: p?.company?.ok ? p.company.data : null,
    preTrade: p?.preTrade ?? null,
  }));

  const outColumns: CompareColumn[] = columns.map((c, i) => ({
    symbol: c.symbol,
    status: c.state.status,
    name: legs[i].company?.name ?? null,
    currency: legs[i].company?.currency.trading
      ?? (legs[i].valuation.status === "ready" ? legs[i].valuation.data.market.code === "ID" ? "IDR" : "USD" : null),
    error: c.state.status === "error" ? c.state.failure.message : null,
  }));

  const row = (key: string, label: string, cell: (i: number) => CompareCell): CompareRow => ({
    key, label, cells: columns.map((_, i) => (payloads[i] ? cell(i) : EMPTY)),
  });

  const lensRow = (read: (i: number) => ReturnType<typeof readAnomaly>): CompareRow =>
    row("reading", "Reading", (i) => {
      const r = read(i);
      return r.verdict === "—" ? EMPTY : { text: r.verdict, tone: voteTone(r), sentence: r.detail };
    });

  const sections: CompareSection[] = [
    {
      key: "company", title: "What it is", hue: palette.company,
      question: "Who the company is, and what its filings say it has done.",
      rows: [
        row("industry", "Industry", (i) => {
          const c = legs[i].company;
          return c ? { text: c.profile.industry ?? c.profile.sector ?? "—", tone: null,
                       sentence: c.profile.summaryShort ?? undefined } : EMPTY;
        }),
        row("listing", "Listed", (i) => {
          const c = legs[i].company;
          return c ? { text: [c.listing.exchange, c.currency.trading].filter(Boolean).join(" · ") || "—",
                       tone: null } : EMPTY;
        }),
        row("marketCap", "Market value", (i) => {
          const c = legs[i].company;
          return c?.listing.marketCap != null
            ? { text: `${compact(c.listing.marketCap)} ${c.currency.trading ?? ""}`.trim(), tone: null }
            : EMPTY;
        }),
        row("yearsProfitable", "Years profitable", (i) => fromExplain(legs[i].company?.explain.yearsProfitable)),
        row("revenueCagr", "Revenue growth", (i) => fromExplain(legs[i].company?.explain.revenueCagr)),
        row("nextEarnings", "Next report", (i) => {
          const c = legs[i].company;
          return c ? { text: c.nextEarnings.date ?? "—", tone: null } : EMPTY;
        }),
      ],
    },
    {
      key: "flow", title: "Who is trading it", hue: palette.flow,
      question: "Is anyone unusual trading this?",
      rows: [lensRow((i) => readAnomaly(legs[i].anomaly))],
    },
    {
      key: "trend", title: "What the price did", hue: palette.trend,
      question: "What has the price been doing, and could you have held it?",
      rows: [
        lensRow((i) => readTechnical(legs[i].technical)),
        row("rollingWorst", `Worst ${horizon}-year holding`, (i) => {
          const t = legs[i].technical;
          if (t.status !== "ready") return EMPTY;
          const r = t.data.longTerm?.rollingReturns?.find((x) => x.years === horizon);
          if (!r || r.usable === false || r.worst == null) {
            return { text: "—", tone: null, sentence: r?.reason ?? "Not enough history for this horizon." };
          }
          return { text: `${signedPct(r.worst, 1)} a year`, tone: null,
                   sentence: `The worst of ${r.windows} overlapping ${horizon}-year entries; ${pct(r.positiveShare ?? null, 0)} of them made money.` };
        }),
        row("maxDrawdown", "Worst fall", (i) => {
          const t = legs[i].technical;
          return t.status === "ready" ? fromExplain(t.data.longTerm?.explain?.maxDrawdown) : EMPTY;
        }),
        row("volatility", "Volatility", (i) => {
          const t = legs[i].technical;
          return t.status === "ready" ? fromExplain(t.data.longTerm?.explain?.volatility) : EMPTY;
        }),
      ],
    },
    {
      key: "value", title: "What it is worth", hue: palette.value,
      question: "What is the business worth, on its own cash flows?",
      rows: [
        row("reading", "Reading", (i) => {
          const v = legs[i].valuation;
          if (v.status !== "ready") return EMPTY;
          const r = readValuation(v);
          return { text: verdictLabel(v.data.verdict), tone: voteTone(r), sentence: r.detail };
        }),
        row("impliedGrowth", "Growth the price implies", (i) => {
          const v = legs[i].valuation;
          return v.status === "ready" ? fromExplain(v.data.explain?.impliedGrowth) : EMPTY;
        }),
        row("terminalShare", "Share that is guesswork", (i) => {
          const v = legs[i].valuation;
          return v.status === "ready" ? fromExplain(v.data.explain?.terminalShare) : EMPTY;
        }),
      ],
    },
    {
      key: "quality", title: "Are the numbers real", hue: palette.quality,
      question: "Is the business sound, and do the accounts look like the real thing?",
      rows: [
        lensRow((i) => readQuality(legs[i].quality)),
        row("piotroski", "Health checks", (i) => {
          const q = legs[i].quality;
          return q.status === "ready" && q.data.applicable ? fromExplain(q.data.explain?.piotroski) : EMPTY;
        }),
        row("altman", "Distance from distress", (i) => {
          const q = legs[i].quality;
          return q.status === "ready" && q.data.applicable ? fromExplain(q.data.explain?.altman) : EMPTY;
        }),
        row("beneish", "Earnings manipulation screen", (i) => {
          const q = legs[i].quality;
          return q.status === "ready" && q.data.applicable ? fromExplain(q.data.explain?.beneish) : EMPTY;
        }),
      ],
    },
    {
      key: "pretrade", title: "What would give a careful buyer pause", hue: palette.pretrade,
      question: "The conditions that fired for each company, beside nothing else.",
      rows: [
        row("fired", "Fired", (i) => {
          const p = legs[i].preTrade;
          if (!p) return EMPTY;
          const fired = p.flags.map((f) => f.explain.label);
          // NO NUMBER. A count per column would rank the columns by how many
          // alarms they raised — a severity score with extra steps. And an empty
          // list is never "clear": the panel's own caveat says so in words.
          return fired.length
            ? { text: "", tone: null, items: fired }
            : { text: "None of the calibrated conditions fired", tone: null, sentence: p.caveat };
        }),
      ],
    },
  ];

  const currencies = [...new Set(outColumns.map((c) => c.currency).filter(Boolean))];
  return {
    columns: outColumns,
    sections,
    currencyNote: currencies.length > 1
      ? `Figures are in each listing's own currency (${currencies.join(", ")}) and are not converted. `
        + "Nothing on this page is computed across columns."
      : null,
  };
}
