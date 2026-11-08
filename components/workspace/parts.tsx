"use client";

import { Columns3, Link2, Printer, Star } from "lucide-react";
import { useEffect, useState } from "react";
import { Card, CardBody } from "@/components/ui/card";
import { ApplyButton } from "@/components/ui/controls";
import { StateCard } from "@/components/ui/state";
import type { Engine, EngineFailure } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useT } from "@/lib/i18n";

/** One wrapper so the four lens panels handle loading and failure identically. */
export function Panel<T>({
  state, children, rescue,
}: {
  state: Engine<T>;
  children: (data: T) => React.ReactNode;
  /** Rendered inside the error card when the failure is a fixable data gap. */
  rescue?: (failure: EngineFailure) => React.ReactNode;
}) {
  const t = useT();
  if (state.status === "loading") return <StateCard kind="loading" />;
  if (state.status === "error") {
    const { failure } = state;
    return (
      <StateCard
        kind="error"
        title={t("This engine could not run")}
        action={failure.manualRequired ? (
          // A data gap the user can close is a different problem from a
          // business the model cannot value. Only the former gets a form —
          // and the form has to be here, because the panel that normally
          // holds it never rendered.
          <div className="space-y-3">
            <p className="prose-col text-meta leading-relaxed text-warn">
              {t("Yahoo is missing {value} for this listing. Enter it below to value the company anyway.", { value: failure.missing?.length ? failure.missing.join(", ") : t("a required figure") })}
            </p>
            {rescue?.(failure)}
          </div>
        ) : undefined}
      >
        {failure.message}
      </StateCard>
    );
  }
  if (state.status === "ready") return <>{children(state.data)}</>;
  return null;
}

/**
 * A pointer from Trend to the one question this page cannot answer.
 *
 * WHY A SIGNPOST AND NOT THE READING ITSELF. What a set of holdings has in
 * common is a property of the SET — it is measured from how several names move
 * together, and one ticker does not have it. So the finding lives on the
 * Portfolio tab, where the holdings are, and this says so rather than
 * reproducing a number that would mean something different here.
 *
 * IT EXISTS BECAUSE THE FEATURE WAS UNFINDABLE, and it sits first on the tab
 * because, measured at 1440px, the bottom of the Trend tab is 95% of the way
 * down the page — a pointer nobody scrolls to is the same defect as none.
 * ONE LINE, DELIBERATELY: it carries no number and no verdict, so it does not
 * compete with the lens's reading for authority.
 */
export function PortfolioSignpost({ onOpen }: { onOpen: () => void }) {
  const t = useT();
  // Navigation, not a reading, so it stays off the tearsheet with the rest of
  // the chrome — printed, it was the first line of the Trend tab.
  return (
    <Card className="print:hidden">
      <CardBody className="flex flex-wrap items-center justify-between gap-3 py-4">
        <p className="max-w-measure text-lead leading-snug text-chalk">
          {t("Holdings that each look fine on their own can be one bet.")}
        </p>
        <ApplyButton onClick={onOpen}>{t("Portfolio fit")}</ApplyButton>
      </CardBody>
    </Card>
  );
}

/**
 * What the wait is, while it lasts.
 *
 * A full read is one request that takes ten to fifteen seconds on a cold
 * function, and the old counter sat at "0/4" for all of it. Elapsed seconds
 * are the honest thing to show: they move, they are true, and past twenty they
 * say plainly that the data source is being slow rather than that the app hung.
 * The sentence is in a polite live region so a screen reader hears the start
 * and the finish, not every tick.
 */
export function RunStatus({
  symbol, busy, failed, at,
}: { symbol: string; busy: boolean; failed: number; at: number | null }) {
  const t = useT();
  const [started, setStarted] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!busy) { setStarted(null); return; }
    const t0 = Date.now();
    setStarted(t0);
    setNow(t0);
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [busy]);
  const seconds = started ? Math.max(0, Math.round((now - started) / 1000)) : 0;

  // EVERY LENS FAILING IS NOT A FETCH. The stamp below used to say "Fetched
  // 12:19 · figures are as of the last close" over four failed lenses, which
  // dates figures that do not exist.
  const nothing = failed >= 4;
  const announce = busy
    ? t("Reading {symbol} through four lenses.", { symbol })
    : !at ? ""
      : nothing ? t("No lens returned figures for {symbol}.", { symbol })
        : failed ? t("{symbol} loaded; {failed} of four lenses did not answer.", { symbol, failed })
          : t("{symbol} loaded.", { symbol });
  const time = at ? new Date(at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "";

  return (
    <>
      <p className="sr-only" role="status" aria-live="polite">{announce}</p>
      {busy && (
        <div aria-hidden className="flex items-center gap-3 text-meta text-ash">
          <span className="relative h-1 w-32 overflow-hidden rounded-full bg-rule">
            <span className="absolute inset-y-0 left-0 w-1/3 animate-pulseline rounded-full bg-tech" />
          </span>
          {t("Reading {symbol} through four lenses · {seconds}s", { symbol, seconds })}
          {seconds >= 20 && <span className="text-faint">{t("— the data source is slow today")}</span>}
        </div>
      )}
      {!busy && at && (
        <p className="text-micro text-faint">
          {nothing
            ? <>{t("Asked at {time} · no lens returned figures", { time })}</>
            : <>{t("Fetched {time} · figures are as of the last close the data source had", { time })}</>}
        </p>
      )}
    </>
  );
}

const actionClass = cn(
  "inline-flex h-8 items-center gap-1.5 rounded-lg border border-rule px-2.5 text-meta text-ash",
  "transition-colors hover:border-ruleStrong hover:text-chalk",
  "focus:outline-none focus-visible:ring-2 focus-visible:ring-tech",
);

/** Things to do WITH a stock page: keep it, compare it, share it, print it. */
export function StockActions({
  watched, onWatch, onCompare, onCopy, onPrint,
}: {
  watched: boolean;
  onWatch: () => void;
  onCompare: () => void;
  onCopy: () => void;
  onPrint: () => void;
}) {
  const t = useT();
  return (
    <div className="flex flex-wrap items-center gap-1.5 print:hidden">
      <button type="button" onClick={onWatch} aria-pressed={watched} className={actionClass}
              title={watched ? t("Remove from watchlist (w)") : t("Add to watchlist (w)")}>
        <Star aria-hidden className={cn("h-3.5 w-3.5", watched && "fill-current text-chalk")} />
        <span>{watched ? t("Watching") : t("Watch")}</span>
      </button>
      <button type="button" onClick={onCompare} className={actionClass}>
        <Columns3 aria-hidden className="h-3.5 w-3.5" />
        <span>{t("Compare")}</span>
      </button>
      <button type="button" onClick={onCopy} className={actionClass} aria-label={t("Copy a link to this page")}>
        <Link2 aria-hidden className="h-3.5 w-3.5" />
        <span className="hidden sm:inline">{t("Copy link")}</span>
      </button>
      <button type="button" onClick={onPrint} className={actionClass} aria-label={t("Print this page")}>
        <Printer aria-hidden className="h-3.5 w-3.5" />
        <span className="hidden sm:inline">{t("Print")}</span>
      </button>
    </div>
  );
}

/**
 * What a printed page says about itself, which the screen does not need to.
 *
 * A printout leaves the app: it has no top bar, no live data and no URL bar,
 * so it has to carry its own provenance — which company, when it was printed,
 * which close the prices are from, where they came from, and that it is not
 * investment advice. Hidden on screen.
 */
export function PrintHeader({ symbol, name, priceAsOf }: {
  symbol: string; name?: string | null; priceAsOf?: string | null;
}) {
  const t = useT();
  const printed = new Date().toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
  return (
    <div className="hidden border-b border-rule pb-3 print:block">
      <p className="font-mono text-meta font-semibold tracking-[0.16em] text-chalk">{t("QUANTDESK")}</p>
      <p className="mt-1 text-meta text-body">
        {t("{symbol}{value} · printed {printed}{value2} · source: Yahoo Finance", { symbol, value: name ? ` — ${name}` : "", printed, value2: priceAsOf ? t(" · prices as of the close of {date}", { date: priceAsOf }) : "" })}
      </p>
      <p className="text-meta text-ash">
        {t("Educational and research use only — not investment advice. Only the tab that was open is printed; every figure explains itself on screen.")}
      </p>
    </div>
  );
}
