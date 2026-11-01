import type { ExchangeInfo } from "./types";

/**
 * Whether an exchange is trading right now, and when that changes.
 *
 * WORKED OUT HERE, EVERY MINUTE, FROM HOURS THE SERVER SENT ONCE. The calendar
 * route carries each exchange's sessions in its own time zone and its upcoming
 * closures; this turns "now" into that zone's wall clock with `Intl`, which
 * knows every daylight-saving rule, so no request is spent on a status that
 * changes at 09:30 and 16:00.
 *
 * The answer is a fact about the clock and nothing else: "open" says nothing
 * about whether it is a good time to trade.
 */

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"] as const;

/** An instant as a wall clock in `timeZone` shows it. */
export function zonedParts(at: Date, timeZone: string): { date: string; minutes: number; weekday: string } {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone, hourCycle: "h23", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", weekday: "short",
  }).formatToParts(at);
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  return {
    date: `${get("year")}-${get("month")}-${get("day")}`,
    minutes: Number(get("hour")) * 60 + Number(get("minute")),
    weekday: get("weekday"),
  };
}

/** The UTC instant at which `time` on `date` happens in `timeZone`. */
export function zonedInstant(date: string, time: string, timeZone: string): Date {
  const [y, m, d] = date.split("-").map(Number);
  const [hh, mm] = time.split(":").map(Number);
  const wanted = Date.UTC(y, m - 1, d, hh, mm);
  let guess = wanted;
  // Twice: the first pass finds the offset, the second corrects for a guess
  // that landed on the other side of a daylight-saving change.
  for (let pass = 0; pass < 2; pass++) {
    const shown = zonedParts(new Date(guess), timeZone);
    const [sy, sm, sd] = shown.date.split("-").map(Number);
    guess += wanted - Date.UTC(sy, sm - 1, sd, Math.floor(shown.minutes / 60), shown.minutes % 60);
  }
  return new Date(guess);
}

const toMinutes = (hhmm: string) => {
  const [h, m] = hhmm.split(":").map(Number);
  return h * 60 + m;
};

function addDays(date: string, days: number): string {
  const [y, m, d] = date.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d + days)).toISOString().slice(0, 10);
}

function weekdayOf(date: string): string {
  const [y, m, d] = date.split("-").map(Number);
  return WEEKDAYS[new Date(Date.UTC(y, m - 1, d)).getUTCDay()];
}

/** The sessions an exchange holds on one of its own dates, or null when it is shut. */
export function sessionsOn(exchange: ExchangeInfo, date: string): [string, string][] | null {
  const weekday = weekdayOf(date);
  if (weekday === "Sat" || weekday === "Sun") return null;
  const closure = exchange.closures.find((c) => c.date === date);
  if (closure?.kind === "holiday") return null;
  const base = weekday === "Fri" ? exchange.sessions.fri : exchange.sessions["mon-thu"];
  if (closure?.kind === "early-close" && closure.time) {
    const cut = toMinutes(closure.time);
    return base
      .filter(([open]) => toMinutes(open) < cut)
      .map(([open, close]) => [open, toMinutes(close) > cut ? closure.time! : close]);
  }
  return base;
}

export type ExchangeState = "open" | "break" | "closed";

export interface ExchangeStatus {
  state: ExchangeState;
  /** What happens next and when, or null when nothing is known within a fortnight. */
  next: { kind: "opens" | "reopens" | "closes"; at: Date } | null;
  /** Why it is shut today, when today is a holiday. */
  reason: string | null;
}

export function exchangeStatus(exchange: ExchangeInfo, now: Date): ExchangeStatus {
  const here = zonedParts(now, exchange.tz);
  const today = sessionsOn(exchange, here.date);
  const holiday = exchange.closures.find((c) => c.date === here.date && c.kind === "holiday");
  if (today) {
    for (let i = 0; i < today.length; i++) {
      const [open, close] = today[i];
      if (here.minutes >= toMinutes(open) && here.minutes < toMinutes(close)) {
        return { state: "open", next: { kind: "closes", at: zonedInstant(here.date, close, exchange.tz) }, reason: null };
      }
      if (here.minutes < toMinutes(open)) {
        return {
          state: i === 0 ? "closed" : "break",
          next: { kind: i === 0 ? "opens" : "reopens", at: zonedInstant(here.date, open, exchange.tz) },
          reason: null,
        };
      }
    }
  }
  for (let ahead = 1; ahead <= 14; ahead++) {
    const date = addDays(here.date, ahead);
    const sessions = sessionsOn(exchange, date);
    if (sessions) {
      return { state: "closed", next: { kind: "opens", at: zonedInstant(date, sessions[0][0], exchange.tz) },
               reason: holiday?.detail ?? null };
    }
  }
  return { state: "closed", next: null, reason: holiday?.detail ?? null };
}
