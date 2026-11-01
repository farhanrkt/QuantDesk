"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  addDays, byDay, cellLabel, dayHeading, dayLong, monthGrid, monthHeading, relativeDay, shiftMonth,
} from "@/lib/calendar";
import type { CalendarEvent } from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * The calendar as a calendar: a month of days with the dates that move markets
 * written into them, and a seven-day strip of the same for a narrow screen.
 *
 * A DAY IS A BUTTON ONLY WHERE THERE IS SOMETHING ON IT. Choosing one hands it
 * to the page, which shows that day's events — time, badges, what it is and how
 * its past occurrences went — in the list beside or under the grid; choosing it
 * again lets go. Everything else is a plain cell, so a keyboard walks the event
 * days of a month in a handful of stops rather than thirty-five.
 *
 * NOTHING IS RANKED OR COLOURED BY KIND. Every event day looks the same, because
 * the measured history says event days were mostly ordinary days; a closure
 * reads in the quieter tone because the market is shut, which is a state, not a
 * weight. A day past what the calendar has loaded is drawn as not loaded rather
 * than as a day with nothing on it.
 */

const WEEKDAYS: [string, string][] = [
  ["M", "Monday"], ["T", "Tuesday"], ["W", "Wednesday"], ["T", "Thursday"],
  ["F", "Friday"], ["S", "Saturday"], ["S", "Sunday"],
];
const WEEKDAY_SHORT = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

const FOCUS = "focus:outline-none focus-visible:ring-2 focus-visible:ring-tech "
  + "focus-visible:ring-offset-2 focus-visible:ring-offset-ink";

const closed = (event: CalendarEvent) => event.kind === "holiday" || event.kind === "early-close";

/** What a screen reader hears for a day: the date, how far off it is, and every event on it. */
function dayName(day: string, today: string, events: CalendarEvent[]): string {
  const when = `${dayLong(day)}, ${relativeDay(day, today)}`;
  return events.length ? `${when}: ${events.map((e) => e.title).join("; ")}` : when;
}

function Labels({ events, room, past }: { events: CalendarEvent[]; room: number; past: boolean }) {
  const shown = events.slice(0, room);
  const more = events.length - shown.length;
  return (
    <>
      {shown.map((event) => (
        <span key={`${event.kind}-${event.ticker ?? event.market}`}
              className={cn("block w-full truncate text-micro leading-tight",
                            past || closed(event) ? "text-ash" : "text-body")}>
          {cellLabel(event)}
        </span>
      ))}
      {more > 0 && (
        <span className="block text-micro leading-tight text-ash">+{more}{room > 1 ? " more" : ""}</span>
      )}
    </>
  );
}

function DayNumber({ day, today }: { day: string; today: string }) {
  return (
    <span className={cn("num inline-flex h-5 min-w-5 items-center justify-center rounded-full px-1 text-meta leading-none",
                        day === today ? "bg-chalk font-semibold text-ink"
                          : day < today ? "text-ash" : "text-chalk")}>
      {Number(day.slice(8))}
    </span>
  );
}

/**
 * One month. `from` and `through` are the dates the calendar holds; the reader
 * can page from the current month to the last one those reach.
 */
export function CalendarMonth({
  events, today, from, through, selected, onSelect, size = "compact", timeZone,
}: {
  events: CalendarEvent[];
  /** The reader's date, YYYY-MM-DD. */
  today: string;
  from?: string;
  through?: string;
  selected: string | null;
  onSelect: (day: string | null) => void;
  size?: "compact" | "full";
  timeZone?: string;
}) {
  const first = today.slice(0, 7);
  const last = through && through.slice(0, 7) > first ? through.slice(0, 7) : first;
  const [month, setMonth] = useState(first);
  // The reader's month can roll over under an open page; never show one
  // before it, nor one past what is loaded.
  const shown = month < first ? first : month > last ? last : month;
  const days = byDay(events, timeZone);
  const loaded = (day: string) => (!from || day >= from) && (!through || day <= through);
  const room = size === "full" ? 2 : 1;
  const cut = through && through.slice(0, 7) === shown ? through : null;

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <Button variant="quiet" size="icon" className="h-8 w-8" aria-label="Previous month"
                disabled={shown <= first} onClick={() => setMonth(shiftMonth(shown, -1))}>
          <ChevronLeft aria-hidden className="h-4 w-4" />
        </Button>
        <p aria-live="polite" className="text-meta font-semibold text-chalk">{monthHeading(shown)}</p>
        <Button variant="quiet" size="icon" className="h-8 w-8" aria-label="Next month"
                disabled={shown >= last} onClick={() => setMonth(shiftMonth(shown, 1))}>
          <ChevronRight aria-hidden className="h-4 w-4" />
        </Button>
      </div>
      <table className="w-full table-fixed border-separate border-spacing-0.5">
        <caption className="sr-only">
          The dates that move markets in {monthHeading(shown)}, on your clock. Days with something
          on them are buttons that show what it is.
        </caption>
        <thead>
          <tr>
            {WEEKDAYS.map(([short, long]) => (
              <th key={long} scope="col" className="pb-0.5 text-center text-micro font-normal text-ash">
                <span aria-hidden>{short}</span>
                <span className="sr-only">{long}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {monthGrid(shown).map((week) => (
            <tr key={week[0].day}>
              {week.map(({ day, inMonth }) => {
                if (!inMonth) return <td key={day} />;
                const items = days.get(day) ?? [];
                const isSelected = selected === day;
                const box = cn("flex w-full flex-col items-start gap-0.5 rounded px-1 py-1 text-left",
                               size === "full" ? "min-h-[4.5rem]" : "min-h-[3.25rem]");
                return (
                  <td key={day} className="p-0 align-top" aria-current={day === today ? "date" : undefined}>
                    {!loaded(day) ? (
                      <div className={cn(box, "border border-dashed border-rule")}>
                        <DayNumber day={day} today={today} />
                        <span className="sr-only">, not loaded yet</span>
                      </div>
                    ) : items.length ? (
                      <button type="button" aria-pressed={isSelected}
                              aria-label={dayName(day, today, items)}
                              title={items.map((e) => e.title).join("\n")}
                              onClick={() => onSelect(isSelected ? null : day)}
                              className={cn(box, FOCUS, "border",
                                            isSelected ? "border-tech/60 bg-raised"
                                              : "border-rule hover:border-ruleStrong hover:bg-raised")}>
                        <DayNumber day={day} today={today} />
                        <Labels events={items} room={room} past={day < today} />
                      </button>
                    ) : (
                      <div className={cn(box, "border border-transparent")}>
                        <DayNumber day={day} today={today} />
                      </div>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {cut && (
        <p className="text-micro text-ash">
          Dates after {dayHeading(cut)} are not loaded yet; the calendar holds 90 days ahead.
        </p>
      )}
    </div>
  );
}

/**
 * The next seven days, for a screen too narrow for a month: today first, each
 * day's events by their short names.
 */
export function CalendarWeek({
  events, today, selected, onSelect, timeZone,
}: {
  events: CalendarEvent[];
  today: string;
  selected: string | null;
  onSelect: (day: string | null) => void;
  timeZone?: string;
}) {
  const days = byDay(events, timeZone);
  const week = Array.from({ length: 7 }, (_, i) => addDays(today, i));
  return (
    <ul aria-label="The next seven days" className="grid grid-cols-7 gap-1">
      {week.map((day) => {
        const items = days.get(day) ?? [];
        const isSelected = selected === day;
        const weekday = day === today ? "Today"
          : WEEKDAY_SHORT[new Date(`${day}T00:00:00Z`).getUTCDay()];
        const body = (
          <>
            <span className="text-micro leading-tight text-ash">{weekday}</span>
            <DayNumber day={day} today={today} />
            <Labels events={items} room={1} past={false} />
          </>
        );
        const box = "flex min-h-[4rem] w-full flex-col items-center gap-0.5 rounded px-0.5 py-1 text-center";
        return (
          <li key={day} className="min-w-0">
            {items.length ? (
              <button type="button" aria-pressed={isSelected} aria-label={dayName(day, today, items)}
                      onClick={() => onSelect(isSelected ? null : day)}
                      className={cn(box, FOCUS, "border",
                                    isSelected ? "border-tech/60 bg-raised"
                                      : "border-rule hover:border-ruleStrong hover:bg-raised")}>
                {body}
              </button>
            ) : (
              <div className={cn(box, "border border-transparent")}>
                <span className="sr-only">{dayName(day, today, [])}, nothing on the calendar</span>
                <span aria-hidden className="contents">{body}</span>
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
