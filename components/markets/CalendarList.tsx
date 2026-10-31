"use client";

import { CalendarPlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { dayHeading, groupByDay, timeText, toIcs } from "@/lib/calendar";
import { PRIMARY_HISTORY, historyShort } from "@/lib/marketboard";
import type { CalendarEvent, MarketBoard } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Hand the reader one event as an .ics file. Built here; nothing reaches a server. */
function download(event: CalendarEvent) {
  const blob = new Blob([toIcs(event, new Date())], { type: "text/calendar;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${event.kind}-${event.date}${event.ticker ? `-${event.ticker}` : ""}.ics`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

/**
 * The dates that move markets, grouped by the reader's own day.
 *
 * WHAT PAST OCCURRENCES WERE LIKE, AS HISTORY. Beside an FOMC, CPI, jobs or Bank
 * Indonesia date sits how often the market moved more than on its median day on
 * the past ones, from the board's own two years of prices. Mostly that is about
 * half — event days looked like ordinary days — and the line says so rather
 * than implying the folklore. The compact panel shows one instrument per event;
 * the Today view shows every pair with the medians.
 */
export function CalendarList({
  events, kinds, board, compact, timeZone,
}: {
  events: CalendarEvent[];
  kinds: Record<string, { label: string; about: string }>;
  board: MarketBoard | null;
  compact?: boolean;
  timeZone?: string;
}) {
  const groups = groupByDay(events, timeZone);
  return (
    <div className="space-y-3">
      {groups.map((group) => (
        <section key={group.day} aria-label={dayHeading(group.day)}>
          <h4 className="mb-1 text-meta font-semibold text-chalk">{dayHeading(group.day)}</h4>
          <ul>
            {group.events.map((event) => (
              <CalendarRow key={`${event.kind}-${event.date}-${event.market}-${event.ticker ?? ""}`}
                           event={event} about={kinds[event.kind]?.about}
                           board={board} compact={compact} timeZone={timeZone} />
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

function CalendarRow({
  event, about, board, compact, timeZone,
}: {
  event: CalendarEvent;
  about?: string;
  board: MarketBoard | null;
  compact?: boolean;
  timeZone?: string;
}) {
  const rows = board?.eventHistory?.[event.kind] ?? [];
  const readings = board?.explain.eventHistory?.[event.kind] ?? {};
  const shown = compact ? rows.filter((r) => r.key === PRIMARY_HISTORY[event.kind]) : rows;
  const flags = [
    event.market === "ID" ? "IDX" : "US",
    event.projections ? "with projections" : null,
    event.tentative ? "tentative" : null,
    event.scheduled ? "scheduled" : null,
    event.origin === "watchlist" ? "your watchlist" : event.origin === "stock" ? "this stock" : null,
  ].filter(Boolean) as string[];
  return (
    <li className="flex gap-2 border-b border-ruleSoft py-2 last:border-0">
      <span className="num w-12 shrink-0 pt-px text-meta text-body">{timeText(event, timeZone)}</span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
          <span className="text-meta font-medium text-chalk">{event.title}</span>
          {flags.map((flag) => (
            <span key={flag} className="rounded-sm border border-rule px-1 text-micro leading-tight text-ash">
              {flag}
            </span>
          ))}
        </div>
        {event.detail && !compact && (
          <p className="mt-0.5 text-micro leading-snug text-ash">{event.detail}</p>
        )}
        {shown.map((row) => {
          const short = historyShort(row);
          if (!short) return null;
          return (
            <p key={row.key} title={readings[row.key]?.reading}
               className={cn("mt-0.5 text-micro leading-snug text-ash", !compact && "text-body")}>
              {compact ? short : readings[row.key]?.reading ?? short}
            </p>
          );
        })}
        {about && (
          <details className="mt-0.5">
            <summary className="inline-flex min-h-[24px] cursor-pointer items-center text-micro text-ash hover:text-chalk">
              What is this?
            </summary>
            <p className="text-micro leading-snug text-body">{about}</p>
          </details>
        )}
      </div>
      <Button variant="quiet" size="icon" className="h-8 w-8 shrink-0"
              aria-label={`Add ${event.title} on ${dayHeading(event.date)} to your calendar`}
              title="Add to your calendar" onClick={() => download(event)}>
        <CalendarPlus aria-hidden className="h-3.5 w-3.5" />
      </Button>
    </li>
  );
}
