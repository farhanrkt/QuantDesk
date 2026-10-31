import type { BoardRow, Market, MarketBoard } from "./types";

/**
 * The browser's half of the board of what moved the markets.
 *
 * ORDER IS THE SERVER'S. Every function here filters the board's rows and none
 * of them reorders: a list sorted by today's move would be the leaderboard
 * api/_lib/marketboard.py refuses, and rule 19 in scripts/check_frontend.mjs
 * fails the build on a sort in any board file.
 *
 * NOTHING HERE PICKS A COLOUR. A day's move has no good or bad, every row's tone
 * is neutral, and emphasis comes from whether a move was unusual for the
 * instrument that made it — a statement about size, never about direction.
 */

/** How often the board refreshes while someone is looking at it. */
export const BOARD_REFRESH_MS = 300_000;

/** The rows a market's readers see, in declared order. */
export function rowsFor(board: MarketBoard, market: Market): BoardRow[] {
  return board.rows.filter((row) => row.markets.includes(market));
}

/** The compact strip: that market's declared subset, still in board order. */
export function stripFor(board: MarketBoard, market: Market): BoardRow[] {
  const keys = new Set(board.markets[market]?.strip ?? []);
  return board.rows.filter((row) => keys.has(row.key));
}

/** What the stock on screen has to do with a row, said plainly. */
export interface Mark {
  kind: "movesWith" | "itsMarket" | "discountRate";
  text: string;
}

/**
 * The stock a page is about, as far as the board needs to know: its market,
 * and the exposure references it MEASURABLY moves with — the Trend tab's own
 * `exposure.factors`, which survive a t-test and come with their refusals.
 * `factors` is null until the technical lens has answered.
 */
export interface BoardFocus {
  symbol: string;
  market: Market;
  /** `weeks` is the window the exposure was estimated over — five years, not one. */
  factors: { key: string; label: string; weeks?: number }[] | null;
}

/** "over the past 5 years", from the weeks an exposure was estimated over. */
export function periodText(weeks: number | undefined): string {
  if (!weeks || !Number.isFinite(weeks)) return "";
  return weeks >= 104 ? ` over the past ${Math.round(weeks / 52)} years` : ` over the past ${weeks} weeks`;
}

const OWN_INDEX: Record<Market, string> = { US: "sp500", ID: "jkse" };

/**
 * Which rows to mark for the stock on screen, and why. Three kinds, each a fact
 * rather than a guess: a reference the stock measurably moved with, the
 * stock's own market index, and — for a US listing — the yield the Value tab
 * builds its discount rate from. Nothing is marked from a sector or a hunch.
 */
export function marksFor(board: MarketBoard, focus: BoardFocus | null): Record<string, Mark[]> {
  const marks: Record<string, Mark[]> = {};
  if (!focus) return marks;
  const add = (key: string, mark: Mark) => { (marks[key] ??= []).push(mark); };
  const present = new Set(board.rows.map((row) => row.key));

  for (const factor of focus.factors ?? []) {
    const row = board.rows.find((r) => r.exposureKey === factor.key);
    if (row) {
      add(row.key, { kind: "movesWith",
                     text: `${focus.symbol} has moved with ${factor.label}${periodText(factor.weeks)}` });
    }
  }
  const index = OWN_INDEX[focus.market];
  if (present.has(index)) add(index, { kind: "itsMarket", text: `${focus.symbol}'s own market` });
  if (focus.market === "US" && present.has("t10y")) {
    add("t10y", { kind: "discountRate", text: "the rate the Value tab discounts from" });
  }
  return marks;
}

/** What each headline topic is about, for a heading that says "mentioning ...". */
export const TOPIC_LABEL: Record<string, Record<Market, string>> = {
  market: { US: "US stocks", ID: "the Jakarta market" },
  rates: { US: "US rates", ID: "interest rates" },
  dollar: { US: "the dollar", ID: "the dollar" },
  rupiah: { US: "the rupiah", ID: "the rupiah" },
  oil: { US: "oil", ID: "oil" },
  gas: { US: "natural gas", ID: "gas" },
  gold: { US: "gold", ID: "gold" },
  silver: { US: "silver", ID: "silver" },
  copper: { US: "copper", ID: "copper" },
  bitcoin: { US: "bitcoin", ID: "bitcoin" },
};

/** Headlines worth asking for: the market's own feed, then each unusual mover's topic, at most four. */
export function headlineTopics(board: MarketBoard, market: Market, max = 4): string[] {
  const topics = ["market"];
  for (const row of rowsFor(board, market)) {
    if (row.unusual && !topics.includes(row.topic)) topics.push(row.topic);
  }
  return topics.slice(0, max);
}

/** A level in its own precision: 77,480 for bitcoin, 1.1183 for EUR/USD. */
export function levelText(row: BoardRow): string {
  if (row.last == null || !Number.isFinite(row.last)) return "—";
  return row.last.toLocaleString("en-US", {
    minimumFractionDigits: row.digits, maximumFractionDigits: row.digits,
  });
}

/** "30 Oct", from an ISO date, without letting the reader's time zone move the day. */
export function dayText(iso: string | null | undefined): string {
  if (!iso) return "—";
  const [year, month, day] = iso.slice(0, 10).split("-").map(Number);
  if (!year || !month || !day) return "—";
  const name = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][month - 1];
  return `${day} ${name}`;
}

/** How long ago something was published, in the coarsest unit that is still honest. */
export function agoText(published: string | null | undefined, now: number): string | null {
  if (!published) return null;
  const at = Date.parse(published);
  if (!Number.isFinite(at)) return null;
  const minutes = Math.round((now - at) / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours} h ago`;
  return `${Math.round(hours / 24)} days ago`;
}

/** "largest fall since 5 Jun 2026", for an unusual move; null otherwise. */
export function sinceText(row: BoardRow): string | null {
  if (!row.unusual || (row.direction !== "up" && row.direction !== "down")) return null;
  const word = row.direction === "up" ? "rise" : "fall";
  if (row.largestSince) return `largest ${word} since ${dayText(row.largestSince)} ${row.largestSince.slice(0, 4)}`;
  if (row.largestInHistory && row.historyFrom) {
    return `largest ${word} since at least ${dayText(row.historyFrom)} ${row.historyFrom.slice(0, 4)}`;
  }
  return null;
}

/** Local clock time for the board's fetch, or null if unknown. */
export function clockText(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return null;
  return at.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

/**
 * The strip for a page about one stock: the rows related to it first, then the
 * rest, each part in declared order. A partition by a MEASURED relation — its
 * market, a reference it moved with — never an ordering by the size of a move.
 * Without it the related rows were often the ones scrolled out of sight.
 */
export function relatedFirst(rows: BoardRow[], marks: Record<string, Mark[]>): BoardRow[] {
  const related = rows.filter((row) => (marks[row.key]?.length ?? 0) > 0);
  const rest = rows.filter((row) => (marks[row.key]?.length ?? 0) === 0);
  return [...related, ...rest];
}
