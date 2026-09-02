/**
 * A thesis, written down before acting, and never edited afterwards.
 *
 * WHY THIS IS ENTIRELY CLIENT-SIDE, AND WHY THAT IS NOT A COMPROMISE
 * ------------------------------------------------------------------
 * Everything else in this app sends a ticker to a server and gets a reading
 * back. A thesis is the opposite kind of object: it is what the reader believes,
 * which is nobody else's business and has no reason to leave the machine it was
 * typed on. So it does not. It is written to this browser's storage beside the
 * reading mode, the holding horizon and the holdings list, and no request in
 * this codebase carries it.
 *
 * That constraint puts the logic here rather than in Python, which is where the
 * rest of this project's judgement lives. The escape hatch is the one the
 * project already built for exactly this: `scripts/check_frontend.mjs` compiles
 * modules like this one with the `tsc` already in the tree and runs assertions
 * on bare node. `agreementOf` went the same way for the same reason.
 *
 * WHY AN ENTRY CANNOT BE EDITED
 * -----------------------------
 * A thesis you can revise after the fact is not a thesis, it is a
 * rationalisation with a timestamp on it. The whole value of writing one down
 * is that the version you wrote before you knew the outcome is still there
 * afterwards, in the words you actually used. So `save` only ever appends, there
 * is no update path, and the snapshot of what the app was showing at the time is
 * frozen into the entry rather than re-fetched when it is read back.
 *
 * WHY NOTHING IS EVER SCORED
 * --------------------------
 * A journal that graded its own entries would be a backtest of one, on a sample
 * the reader chose, with no control for what they did not write down. This app
 * refuses composites everywhere else on far better evidence than that. Entries
 * are shown back as written; where the numbers have since moved, the movement is
 * reported as movement — never as a verdict on the thesis that preceded it.
 */

export const JOURNAL_KEY = "quantdesk.journal";

/** What the app was showing when the thesis was written. Frozen at save. */
export interface ThesisSnapshot {
  /** Reverse-DCF: the growth rate today's price requires. */
  impliedGrowth?: number | null;
  /** The growth the model was actually run with. */
  assumedGrowth?: number | null;
  price?: number | null;
  priceLabel?: string | null;
  /** Worst peak-to-trough fall in the loaded history. */
  maxDrawdown?: number | null;
  /** Worst annualised outcome at the stated horizon, if that horizon was measured. */
  worstAtHorizon?: number | null;
  /** Conditions the pre-trade panel had fired, as written at the time. */
  firedChecks?: string[];
}

export interface ThesisEntry {
  id: string;
  ticker: string;
  /** ISO timestamp. The one field that makes the rest worth keeping. */
  written: string;
  /** What has to be true for this to work. */
  thesis: string;
  /** What would tell you it is wrong. */
  falsifier: string;
  /** The reader's own growth expectation, as a fraction. Null if not stated. */
  growthBelief: number | null;
  /** Intended holding period in years. */
  horizonYears: number;
  /** Share of the account, as a fraction. Null if not stated. */
  positionShare: number | null;
  snapshot: ThesisSnapshot;
}

// A belief and the price's implication are never going to match exactly, and
// treating a rounding difference as disagreement would make the check noise.
// Five points of annual growth compounded over five years is roughly a third
// more cumulative growth — the point at which two people are describing
// different futures rather than the same one imprecisely.
export const BELIEF_GAP = 0.05;

// Where a position stops being survivable through the fall this stock has
// already had. Losing a fifth of an account is the conventional line at which
// people stop behaving like investors, and the check exists to be arithmetic
// about it rather than encouraging.
export const PAINFUL_ACCOUNT_LOSS = 0.20;

export interface Contradiction {
  key: string;
  title: string;
  detail: string;
}

/**
 * Where a written thesis disagrees with what the app was showing when it was
 * written.
 *
 * NOT A SCORE AND NOT A REFUSAL. Disagreeing with the model is a perfectly
 * respectable thing to do — the reverse DCF exists to be argued with, and the
 * whole Value lens says so. What is not respectable is disagreeing without
 * noticing. Each of these names the gap and leaves it there.
 */
export function contradictions(entry: {
  growthBelief: number | null;
  positionShare: number | null;
  horizonYears: number;
  snapshot: ThesisSnapshot;
}): Contradiction[] {
  const out: Contradiction[] = [];
  const s = entry.snapshot ?? {};

  const implied = s.impliedGrowth;
  if (entry.growthBelief != null && implied != null && Number.isFinite(implied)) {
    const gap = implied - entry.growthBelief;
    if (gap >= BELIEF_GAP) {
      out.push({
        key: "belowImplied",
        title: "You expect less growth than the price requires",
        detail:
          `You wrote ${fmt(entry.growthBelief)} a year; today's price needs ` +
          `${fmt(implied)} a year for five years to be worth what it costs. On this ` +
          `model you are buying something you think is expensive. That can be ` +
          `deliberate — the model is one set of assumptions — but it should be ` +
          `deliberate.`,
      });
    } else if (-gap >= BELIEF_GAP) {
      out.push({
        key: "aboveImplied",
        title: "You expect more growth than the price requires",
        detail:
          `You wrote ${fmt(entry.growthBelief)} a year against the ${fmt(implied)} ` +
          `today's price needs. That gap is the thesis: you are betting the market ` +
          `is asking too little of this business. Write down why you know something ` +
          `it does not.`,
      });
    }
  }

  const drawdown = s.maxDrawdown;
  if (entry.positionShare != null && drawdown != null && Number.isFinite(drawdown)) {
    const accountLoss = entry.positionShare * Math.abs(drawdown);
    if (accountLoss >= PAINFUL_ACCOUNT_LOSS) {
      out.push({
        key: "sizeVsDrawdown",
        title: "This size would not have survived this stock's own history",
        detail:
          `A ${fmt(entry.positionShare)} position in something that has already fallen ` +
          `${fmt(Math.abs(drawdown))} peak to trough is ${fmt(accountLoss)} of the ` +
          `account, gone, in a repeat of a fall this stock has actually had. Not a ` +
          `forecast — a thing that happened.`,
      });
    }
  }

  const worst = s.worstAtHorizon;
  if (worst != null && Number.isFinite(worst) && worst < 0) {
    out.push({
      key: "negativeAtHorizon",
      title: `Some ${entry.horizonYears}-year holders of this lost money`,
      detail:
        `The unluckiest entry over your stated horizon returned ${fmt(worst)} a year. ` +
        `Your thesis has to survive being that buyer, because nothing here says you ` +
        `are not.`,
    });
  }
  return out;
}

function fmt(value: number): string {
  return `${(value * 100).toFixed(value !== 0 && Math.abs(value) < 0.01 ? 2 : 0)}%`;
}

/** What has moved since an entry was written. Movement, never a verdict. */
export interface Drift {
  key: string;
  label: string;
  then: string;
  now: string;
}

export function drift(entry: ThesisEntry, current: ThesisSnapshot): Drift[] {
  const out: Drift[] = [];
  const rows: [string, string, keyof ThesisSnapshot][] = [
    ["impliedGrowth", "Growth the price requires", "impliedGrowth"],
    ["maxDrawdown", "Worst fall in the loaded history", "maxDrawdown"],
  ];
  for (const [key, label, field] of rows) {
    const before = entry.snapshot?.[field];
    const after = current?.[field];
    if (typeof before !== "number" || typeof after !== "number") continue;
    if (Math.abs(after - before) < 0.005) continue;
    out.push({ key, label, then: fmt(before), now: fmt(after) });
  }
  const beforePrice = entry.snapshot?.priceLabel;
  const afterPrice = current?.priceLabel;
  if (beforePrice && afterPrice && beforePrice !== afterPrice) {
    out.push({ key: "price", label: "Price", then: beforePrice, now: afterPrice });
  }
  return out;
}

// --------------------------------------------------------------------------- //
// Storage. Append-only, and defensive about what comes back out of it.
// --------------------------------------------------------------------------- //
function isEntry(value: unknown): value is ThesisEntry {
  if (!value || typeof value !== "object") return false;
  const e = value as Record<string, unknown>;
  return typeof e.id === "string" && typeof e.ticker === "string"
    && typeof e.written === "string" && typeof e.thesis === "string";
}

/**
 * Everything ever written, newest first.
 *
 * PARSES DEFENSIVELY BECAUSE THE STORE IS NOT OURS. localStorage is editable by
 * anything else on the origin and by the reader themselves, and an entry list
 * that throws on one malformed row would lose every good row with it. Anything
 * unrecognisable is dropped and the rest survives.
 */
export function readJournal(raw: string | null): ThesisEntry[] {
  if (!raw) return [];
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return [];
  }
  if (!Array.isArray(parsed)) return [];
  return parsed.filter(isEntry)
    .sort((a, b) => (a.written < b.written ? 1 : -1));
}

/**
 * Append. There is deliberately no update and no edit.
 *
 * See the module note: a thesis you can revise after the outcome is known is a
 * rationalisation. Deletion is offered in the panel because keeping something
 * against someone's wishes is a different kind of wrong, but nothing rewrites.
 */
export function appendEntry(existing: ThesisEntry[], entry: ThesisEntry): ThesisEntry[] {
  return [entry, ...existing.filter((e) => e.id !== entry.id)];
}

export function newId(now: Date, ticker: string): string {
  return `${ticker.toUpperCase()}-${now.toISOString()}`;
}
