"use client";

import { useEffect, useState } from "react";
import { exchangeStatus, type ExchangeStatus } from "@/lib/marketclock";
import type { MarketCalendar } from "@/lib/types";
import { dayShort, msg, useT } from "@/lib/i18n";
import { cn } from "@/lib/utils";

const STATE_WORD: Record<ExchangeStatus["state"], string> = {
  open: msg("open"), break: msg("on its midday break"), closed: msg("closed"),
};

const NEXT_WORD: Record<"opens" | "reopens" | "closes", string> = {
  opens: msg("opens"), reopens: msg("reopens"), closes: msg("closes"),
};

/** "opens Mon 21:30" on the reader's clock, with the weekday only when it is not today. */
function whenText(at: Date, now: Date): string {
  const time = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit" }).format(at);
  const sameDay = at.toDateString() === now.toDateString();
  return sameDay ? time
    : `${dayShort(at.getDay())} ${time}`;
}

/**
 * Whether NYSE and IDX are trading, ticking on the reader's clock. Worked out in
 * the browser from the hours and closures the calendar carries (lib/marketclock.ts),
 * so it costs no request. A filled dot for open and a hollow one otherwise:
 * a state, never a colour.
 */
export function ExchangeStatusLine({ calendar, className }: { calendar: MarketCalendar; className?: string }) {
  const t = useT();
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 30_000);
    return () => window.clearInterval(timer);
  }, []);
  return (
    <ul className={cn("flex flex-wrap gap-x-4 gap-y-1", className)}>
      {(["US", "ID"] as const).map((code) => {
        const exchange = calendar.exchanges[code];
        if (!exchange) return null;
        const status = exchangeStatus(exchange, now);
        return (
          <li key={code} className="flex items-center gap-1.5 text-micro text-ash">
            <span aria-hidden className={cn("h-1.5 w-1.5 rounded-full border border-chalk",
                                            status.state === "open" && "bg-chalk")} />
            <span>
              <span className="text-body">{exchange.name}</span> {t(STATE_WORD[status.state])}
              {status.reason ? ` (${status.reason.replace(/\.$/, "")})` : ""}
              {status.next ? ` · ${t(NEXT_WORD[status.next.kind])} ${whenText(status.next.at, now)}` : ""}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
