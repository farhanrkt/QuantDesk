import type { CalendarEvent, Market } from "./types";

/**
 * The calendar's browser half: which day an event falls on for the reader, in
 * what order, what a stock's report date looks like as an event, and the file
 * a reader can add to their own calendar.
 *
 * THE READER'S DAY, NOT THE EVENT'S. A 14:00 FOMC statement in Washington is
 * 02:00 the next day in Jakarta, so a timed event is grouped by its instant in
 * the reader's zone; an all-day date (a holiday, a Bank Indonesia decision with
 * no published hour) stays on its own date. Ordering is by time, which is the
 * only order a calendar has.
 */

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August",
  "September", "October", "November", "December"];
const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const DAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

/** The reader's date now, YYYY-MM-DD. */
export function todayIn(now: Date, timeZone?: string): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" })
    .format(now);
}

const utcOf = (day: string) => {
  const [y, m, d] = day.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d));
};

const momentOf = (event: CalendarEvent) => (event.utc ? Date.parse(event.utc) : Date.parse(`${event.date}T00:00:00Z`));

/** A date `n` days on, by the calendar alone: no zone and no clock change can move it. */
export function addDays(day: string, n: number): string {
  const date = utcOf(day);
  date.setUTCDate(date.getUTCDate() + n);
  return date.toISOString().slice(0, 10);
}

/** "2026-11" moved `n` months. */
export function shiftMonth(month: string, n: number): string {
  const [y, m] = month.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1 + n, 1)).toISOString().slice(0, 7);
}

/** "November 2026". */
export function monthHeading(month: string): string {
  const [y, m] = month.split("-").map(Number);
  return `${MONTH_NAMES[m - 1]} ${y}`;
}

/** "Tuesday 10 November 2026", for a screen reader or a tooltip. */
export function dayLong(day: string): string {
  const date = utcOf(day);
  return `${DAY_NAMES[date.getUTCDay()]} ${date.getUTCDate()} ${MONTH_NAMES[date.getUTCMonth()]} ${date.getUTCFullYear()}`;
}

/**
 * The weeks of one month, Monday first, as the days a grid draws: whole weeks,
 * so the first and last rows carry days of the months either side, marked as
 * outside it. Monday first because the week does on the exchange the app is
 * built around, and in ISO 8601.
 */
export function monthGrid(month: string): { day: string; inMonth: boolean }[][] {
  const first = `${month}-01`;
  const offset = (utcOf(first).getUTCDay() + 6) % 7;        // Monday 0 … Sunday 6
  let day = addDays(first, -offset);
  const weeks: { day: string; inMonth: boolean }[][] = [];
  do {
    const week = [];
    for (let i = 0; i < 7; i++) {
      week.push({ day, inMonth: day.startsWith(month) });
      day = addDays(day, 1);
    }
    weeks.push(week);
  } while (day.startsWith(month));
  return weeks;
}

/** Every event under the reader's day, each day's in time order. */
export function byDay(events: CalendarEvent[], timeZone?: string): Map<string, CalendarEvent[]> {
  const days = new Map<string, CalendarEvent[]>();
  for (const event of [...events].sort((a, b) => momentOf(a) - momentOf(b))) {
    const day = dayOf(event, timeZone);
    days.set(day, [...(days.get(day) ?? []), event]);
  }
  return days;
}

const CELL_LABELS: Partial<Record<CalendarEvent["kind"], string>> = {
  fomc: "FOMC", cpi: "CPI", jobs: "Jobs", pce: "PCE", gdp: "GDP", "bi-rate": "BI",
  holiday: "Closed", "early-close": "Early",
};

/** What a calendar cell has room to say: the kind's short name, or the ticker that reports. */
export function cellLabel(event: CalendarEvent): string {
  if (event.kind === "earnings" && event.ticker) return event.ticker.replace(/\.JK$/, "");
  return CELL_LABELS[event.kind] ?? event.label;
}

/** "today", "tomorrow", "in 5 days", "yesterday", "5 days ago". */
export function relativeDay(day: string, today: string): string {
  const diff = Math.round((utcOf(day).getTime() - utcOf(today).getTime()) / 86_400_000);
  if (diff === 0) return "today";
  if (diff === 1) return "tomorrow";
  if (diff === -1) return "yesterday";
  return diff > 0 ? `in ${diff} days` : `${-diff} days ago`;
}

/** The reader's date for an event, YYYY-MM-DD. */
export function dayOf(event: CalendarEvent, timeZone?: string): string {
  if (!event.utc) return event.date;
  return new Intl.DateTimeFormat("en-CA", {
    timeZone, year: "numeric", month: "2-digit", day: "2-digit",
  }).format(new Date(event.utc));
}


/** Events from `now` through `days` ahead, in time order. An all-day event stays until its day ends. */
export function upcoming(events: CalendarEvent[], now: Date, days: number, timeZone?: string): CalendarEvent[] {
  const today = todayIn(now, timeZone);
  const last = addDays(today, days);
  return events
    .filter((e) => (e.utc ? Date.parse(e.utc) >= now.getTime() : e.date >= today) && dayOf(e, timeZone) <= last)
    .sort((a, b) => momentOf(a) - momentOf(b));
}

/** Consecutive events grouped under the reader's date, in the order given. */
export function groupByDay(events: CalendarEvent[], timeZone?: string): { day: string; events: CalendarEvent[] }[] {
  const groups: { day: string; events: CalendarEvent[] }[] = [];
  for (const event of events) {
    const day = dayOf(event, timeZone);
    const last = groups[groups.length - 1];
    if (last && last.day === day) last.events.push(event);
    else groups.push({ day, events: [event] });
  }
  return groups;
}

/** "Tue 10 Nov", from YYYY-MM-DD, without the reader's zone moving the day. */
export function dayHeading(day: string): string {
  const [y, m, d] = day.split("-").map(Number);
  return `${DAYS[new Date(Date.UTC(y, m - 1, d)).getUTCDay()]} ${d} ${MONTHS[m - 1]}`;
}

/** The event's time on the reader's clock, or "All day". */
export function timeText(event: CalendarEvent, timeZone?: string): string {
  if (!event.utc) return "All day";
  return new Intl.DateTimeFormat("en-GB", { timeZone, hour: "2-digit", minute: "2-digit" })
    .format(new Date(event.utc));
}

/** Report dates as calendar events: the stock on screen, then the watchlist, one per ticker. */
export function earningsEvents(
  stock: { symbol: string; date: string } | null,
  watchlist: { ticker: string; next: string | null }[],
): CalendarEvent[] {
  const seen = new Set<string>();
  const out: CalendarEvent[] = [];
  const add = (ticker: string, date: string, origin: "stock" | "watchlist") => {
    if (seen.has(ticker)) return;
    seen.add(ticker);
    const market: Market = ticker.endsWith(".JK") ? "ID" : "US";
    out.push({
      kind: "earnings", date, time: null, tz: market === "ID" ? "Asia/Jakarta" : "America/New_York",
      market, source: "provider", title: `${ticker} reports`,
      detail: "The data provider's date, often an estimate until the company confirms it.",
      utc: null, allDay: true, label: "Earnings report", ticker, origin,
    });
  };
  if (stock) add(stock.symbol, stock.date, "stock");
  for (const item of watchlist) if (item.next) add(item.ticker, item.next, "watchlist");
  return out;
}

const escapeIcs = (text: string) =>
  text.replace(/\\/g, "\\\\").replace(/;/g, "\\;").replace(/,/g, "\\,").replace(/\r?\n/g, "\\n");

const basic = (iso: string) => iso.replace(/[-:]/g, "").replace(/\.\d{3}/, "");

/**
 * One event as an iCalendar file, for the reader's own calendar app. Built in
 * the browser and handed over as a download: nothing about which events a
 * reader saves ever reaches a server.
 */
export function toIcs(event: CalendarEvent, stamp: Date): string {
  const lines = [
    "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//QuantDesk//Market calendar//EN", "CALSCALE:GREGORIAN",
    "BEGIN:VEVENT",
    `UID:${event.kind}-${event.date}-${event.market}${event.ticker ? `-${event.ticker}` : ""}@quantdesk`,
    `DTSTAMP:${basic(stamp.toISOString())}`,
  ];
  if (event.utc) {
    lines.push(`DTSTART:${basic(new Date(event.utc).toISOString())}`, "DURATION:PT30M");
  } else {
    const [y, m, d] = event.date.split("-").map(Number);
    const next = new Date(Date.UTC(y, m - 1, d + 1)).toISOString().slice(0, 10);
    lines.push(`DTSTART;VALUE=DATE:${event.date.replace(/-/g, "")}`, `DTEND;VALUE=DATE:${next.replace(/-/g, "")}`);
  }
  lines.push(`SUMMARY:${escapeIcs(event.title)}`);
  if (event.detail) lines.push(`DESCRIPTION:${escapeIcs(event.detail)}`);
  lines.push("END:VEVENT", "END:VCALENDAR");
  return lines.join("\r\n") + "\r\n";
}
