"use client";

import { CalendarClock } from "lucide-react";
import type { CompanyResponse, Engine } from "@/lib/types";

/**
 * Who the ticker is, under the ticker, on every tab.
 *
 * The rail's symbol is the biggest thing on the page by design, and for a
 * reader who typed "AAPL" that is enough. For one who arrived from a shared
 * link or a ranking row, "BBRI.JK" names nothing; one line saying it is PT Bank
 * Rakyat Indonesia, a regional bank on the Jakarta exchange, answers the first
 * question anyone has, without a click and without leaving the tab they are on.
 */
export function CompanyHeader({ state }: { state: Engine<CompanyResponse> }) {
  if (state.status !== "ready") {
    return state.status === "loading"
      ? <div aria-hidden className="mt-2 h-4 w-64 max-w-full animate-pulseline rounded bg-rule" />
      : null;
  }
  const { name, profile, listing, currency, nextEarnings } = state.data;
  const facts = [profile.industry ?? profile.sector, listing.exchange, currency.trading]
    .filter(Boolean);
  return (
    <div className="mt-1.5 max-w-measureWide space-y-1">
      <p className="text-base text-body">
        <span className="font-semibold text-chalk">{name}</span>
        {facts.length > 0 && <span className="text-ash"> · {facts.join(" · ")}</span>}
      </p>
      {profile.summaryShort && (
        <p className="line-clamp-2 text-meta leading-relaxed text-ash">{profile.summaryShort}</p>
      )}
      {nextEarnings.date && (
        <p className="inline-flex items-center gap-1.5 text-micro text-faint">
          <CalendarClock aria-hidden className="h-3.5 w-3.5" />
          Next report {nextEarnings.date} (provider&apos;s date, often an estimate)
        </p>
      )}
    </div>
  );
}
