"use client";

import { CalendarClock } from "lucide-react";
import type { CompanyResponse, Engine } from "@/lib/types";
import { useT } from "@/lib/i18n";

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
  const t = useT();
  // THE PLACEHOLDER IS THE HEADER'S HEIGHT, measured: a name line (two on a
  // phone), a two-line summary and the report date — 132 px at 375, 98 from
  // 640. It was one 16 px bar, so the rail grew by eighty pixels when the
  // company arrived and pushed the lens chips off the first screen of a tablet
  // under a reader who had started on them. It stands in before the request
  // starts too, since that is the same wait.
  if (state.status !== "ready") {
    return state.status === "error" ? null : (
      <div aria-hidden className="mt-1.5 h-[132px] space-y-2.5 pt-1 sm:h-[98px]">
        <div className="h-4 w-64 max-w-full animate-pulseline rounded bg-rule" />
        <div className="h-3 w-full max-w-measureWide animate-pulseline rounded bg-rule" />
        <div className="h-3 w-4/5 max-w-measure animate-pulseline rounded bg-rule" />
      </div>
    );
  }
  const { name, profile, listing, currency, nextEarnings } = state.data;
  const facts = [profile.industry ?? profile.sector, listing.exchange, currency.trading]
    .filter(Boolean);
  return (
    <div className="mt-1.5 max-w-measureWide space-y-1">
      <p className="text-base text-body">
        <span className="font-semibold text-chalk">{name}</span>
        {facts.length > 0 && <span lang="en" className="text-ash"> · {facts.join(" · ")}</span>}
      </p>
      {profile.summaryShort && (
        <p lang="en" className="line-clamp-2 text-meta leading-relaxed text-ash">{profile.summaryShort}</p>
      )}
      {nextEarnings.date && (
        <p className="inline-flex items-center gap-1.5 text-micro text-faint">
          <CalendarClock aria-hidden className="h-3.5 w-3.5" />
          {t("Next report {date} (provider's date, often an estimate)", { date: nextEarnings.date })}
        </p>
      )}
    </div>
  );
}
