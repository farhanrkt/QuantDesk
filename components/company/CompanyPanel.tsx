"use client";

import { CalendarClock, ExternalLink } from "lucide-react";
import { useState } from "react";
import {
  Bar, BarChart, Cell, ReferenceLine, ResponsiveContainer, XAxis, YAxis,
} from "recharts";
import { Card, CardBody, CardHeader, CardTitle, Explainer, Note } from "@/components/ui/card";
import { ExplainedStat, useDetail } from "@/components/ui/explain";
import { StateCard } from "@/components/ui/state";
import { alpha, palette } from "@/lib/palette";
import type { BusinessProfile, CompanyResponse, HistoryRow } from "@/lib/types";
import { cn, compact, num } from "@/lib/utils";

/**
 * "What it is" — the company itself, before any lens reads it.
 *
 * WHY THIS TAB EXISTS. PRODUCT.md's reader "arrives knowing a ticker and little
 * else", and until now nothing on the page said what the company sold, how big
 * it was, or whether it had ever made money — the four lenses each read it
 * without anyone introducing it. Every figure here was already fetched and
 * day-cached for the valuation and quality lenses; it was thrown away before
 * reaching the browser.
 *
 * DESCRIPTION, NOT A LENS. No chip in the rail, no vote in the synthesis, no
 * input to the pre-trade checks (a server test asserts both are unchanged with
 * or without this block). The charts are in the neutral `company` colour, and a
 * loss year is a bar below the zero line in that SAME colour: a year of losses
 * is visible from its position, and painting it red would be the client
 * deciding what the server's own reading only describes.
 */
const ROW_LABEL: Record<HistoryRow, string> = {
  revenue: "Revenue",
  operatingIncome: "Operating income",
  netIncome: "Net income",
  dilutedEps: "Earnings per share",
  operatingCashFlow: "Operating cash flow",
  capex: "Capital spending",
  freeCashFlow: "Free cash flow",
  totalDebt: "Total debt",
  cash: "Cash",
  equity: "Shareholders' equity",
};

/** Guided shows the four lines that answer "does it make money, in cash?". */
const GUIDED_ROWS: HistoryRow[] = ["revenue", "netIncome", "operatingCashFlow", "freeCashFlow"];
const FULL_ROWS: HistoryRow[] = [
  "revenue", "operatingIncome", "netIncome", "operatingCashFlow", "capex", "freeCashFlow",
  "totalDebt", "cash", "equity", "dilutedEps",
];

const money = (value: number | null | undefined, currency: string | null) =>
  value == null ? "—" : `${compact(value)}${currency ? ` ${currency}` : ""}`;

export function WhatItDoes({ profile, name }: { profile: BusinessProfile; name?: string }) {
  const { summary, summaryState, industry, sector, employees, country, website } = profile;
  const where = industry ?? sector;
  // FOUR LINES, THEN A CHOICE. Provider descriptions run from one sentence to
  // three hundred words (Apple's lists every subscription it sells), and the
  // long ones pushed every figure on this tab below the fold. The text is all
  // there — clamped, not cut — and one click away.
  const [expanded, setExpanded] = useState(false);
  const long = (summary?.length ?? 0) > 420;
  return (
    <Card accent={palette.company}>
      <CardHeader>
        <CardTitle>What {name ?? "this company"} does</CardTitle>
        {where && <span className="font-mono text-micro text-ash">{where}</span>}
      </CardHeader>
      <CardBody className="space-y-3">
        {summary && summaryState !== "not fetched" ? (
          <div>
            <p id="company-summary"
               className={cn("prose-col-wide text-base leading-relaxed text-body",
                             long && !expanded && "line-clamp-4")}>
              {summary}
            </p>
            {long && (
              <button type="button" onClick={() => setExpanded((v) => !v)}
                      aria-expanded={expanded} aria-controls="company-summary"
                      className="mt-1 inline-flex min-h-[24px] items-center rounded text-meta text-tech
                                 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-tech">
                {expanded ? "Show less" : "Read the full description"}
              </button>
            )}
          </div>
        ) : (
          <p className="prose-col text-base leading-relaxed text-ash">{profile.reading}</p>
        )}
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-meta text-faint">
          {employees != null && <span>{employees.toLocaleString()} employees</span>}
          {country && <span>{country}</span>}
          {website && (
            <a href={website} target="_blank" rel="noopener noreferrer"
               className="inline-flex min-h-[24px] items-center gap-1 text-tech hover:underline">
              {website.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, "")}
              <ExternalLink aria-hidden className="h-3 w-3" />
            </a>
          )}
        </p>
        <p className="text-micro text-faint">
          In the data provider&apos;s own words. Nothing in this app checks it against the filings.
        </p>
      </CardBody>
    </Card>
  );
}

function MiniChart({
  label, values, years, currency, eps,
}: {
  label: string; values: (number | null)[]; years: string[]; currency: string | null;
  eps?: boolean;
}) {
  // "FY2025" → "’25": four mini charts side by side have room for two digits.
  const data = years.map((year, i) => ({ year: `’${year.slice(-2)}`, v: values[i] }));
  const latestIndex = values.map((v, i) => (v == null ? -1 : i)).filter((i) => i >= 0).pop();
  const latest = latestIndex != null && latestIndex >= 0 ? values[latestIndex] : null;
  const shown = eps ? (latest == null ? "—" : `${num(latest)}${currency ? ` ${currency}` : ""}`)
                    : money(latest, currency);
  return (
    <div className="rounded-lg border border-ruleSoft bg-sunken p-3">
      <div className="flex items-baseline justify-between gap-2">
        <span className="eyebrow">{label}</span>
        <span className="num text-meta font-semibold text-chalk">{shown}</span>
      </div>
      <p className="text-micro text-faint">
        {latestIndex != null && latestIndex >= 0 ? years[latestIndex] : "not reported"}
      </p>
      {/* aria-hidden: the table below carries every value, and Recharts stamps
          role="img" on each bar — the anomaly chart once put 1,464 unlabelled
          images in the accessibility tree that way. */}
      <div className="mt-2 h-20" aria-hidden>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
            <XAxis dataKey="year" tick={{ fontSize: 10, fill: palette.axis }} axisLine={false}
                   tickLine={false} interval={0} />
            <YAxis hide domain={[(min: number) => Math.min(0, min), (max: number) => Math.max(0, max)]} />
            <ReferenceLine y={0} stroke={palette.grid} />
            <Bar dataKey="v" isAnimationActive={false} radius={[2, 2, 2, 2]}>
              {data.map((d, i) => (
                <Cell key={d.year} fill={palette.company}
                      fillOpacity={i === latestIndex ? 0.85 : 0.45} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export function CompanyPanel({ data }: { data: CompanyResponse }) {
  const guided = useDetail() === "simple";
  const { history, record, dividends, listing, currency, nextEarnings, explain } = data;
  const rows = guided ? GUIDED_ROWS : FULL_ROWS;
  const tradingCcy = currency.trading;

  return (
    <div className="space-y-4 animate-rise">
      <WhatItDoes profile={data.profile} name={data.name} />

      {/* ---------------------------------------------------- key facts */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <ExplainedStat label="Market value" value={money(listing.marketCap, tradingCcy)}
                       sub={listing.priceAsOf ? `At the close of ${listing.priceAsOf}` : undefined} />
        <ExplainedStat label="Listed on" value={listing.exchange ?? (listing.market === "ID" ? "IDX" : "—")}
                       sub={listing.market === "ID" ? "Indonesia" : "United States"} />
        <ExplainedStat label="Trades in" value={tradingCcy ?? "—"}
                       sub={currency.reporting && currency.reporting !== tradingCcy
                         ? `Reports in ${currency.reporting}` : "Reports in the same currency"} />
        <div className="rounded-lg border border-rule bg-panel px-4 py-3.5">
          <div className="eyebrow mb-2 flex items-center gap-1.5">
            <CalendarClock aria-hidden className="h-3.5 w-3.5" /> Next report
          </div>
          <div className="num text-figure font-semibold leading-none text-chalk">
            {nextEarnings.date ?? "—"}
          </div>
          <div className="mt-2 text-micro leading-snug text-ash">{nextEarnings.reading}</div>
        </div>
      </div>
      {currency.note && <Note tone="warn">{currency.note}</Note>}

      {/* ---------------------------------------------- year by year */}
      <Card accent={palette.company}>
        <CardHeader>
          <CardTitle>The record, year by year</CardTitle>
          {history.available && (
            <span className="font-mono text-micro text-ash">
              {history.fiscalYears[0]}–{history.fiscalYears.at(-1)} · {history.currency ?? ""}
            </span>
          )}
        </CardHeader>
        <CardBody className="space-y-4">
          {!history.available ? (
            <StateCard kind="empty" bare title="No statements came back">{history.reason}.</StateCard>
          ) : (
            <>
              <p className="prose-col text-meta leading-relaxed text-ash">{history.reading}</p>
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                {rows.filter((key) => !history.missing[key]).map((key) => (
                  <MiniChart key={key} label={ROW_LABEL[key]} values={history.rows[key]}
                             years={history.fiscalYears} currency={history.currency}
                             eps={key === "dilutedEps"} />
                ))}
              </div>
              {rows.some((key) => history.missing[key]) && (
                <ul className="space-y-1 text-meta text-ash">
                  {rows.filter((key) => history.missing[key]).map((key) => (
                    <li key={key}><span className="text-body">{ROW_LABEL[key]}:</span> {history.missing[key]}.</li>
                  ))}
                </ul>
              )}
              {history.freeCashFlowMethod && history.freeCashFlowMethod !== "reported" && (
                <p className="text-micro text-faint">
                  Free cash flow is {history.freeCashFlowMethod}; the data source reported no line of its own.
                </p>
              )}
              <HistoryTable history={history} guided={guided} />
            </>
          )}
        </CardBody>
      </Card>

      {/* ------------------------------------------ what it adds up to */}
      <Card accent={palette.company}>
        <CardHeader>
          <CardTitle>What the record adds up to</CardTitle>
          <span className="font-mono text-micro text-ash">description, not a score</span>
        </CardHeader>
        <CardBody className="space-y-4">
          {!record.available ? (
            <StateCard kind="refused" bare title="Too short to call a record">{record.reason}.</StateCard>
          ) : (
            <>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                {(["yearsProfitable", "revenueCagr", "netDebtToEbitda", "freeCashFlowYears"] as const)
                  .filter((k) => explain[k])
                  .map((k) => <ExplainedStat key={k} explain={explain[k]} />)}
              </div>
              <p className="prose-col-wide text-base leading-relaxed text-body">{record.reading}</p>
              {record.baseRatesNote && <Note>{record.baseRatesNote}</Note>}
            </>
          )}
        </CardBody>
      </Card>

      {/* ---------------------------------------------------- dividends */}
      <Card accent={palette.company}>
        <CardHeader>
          <CardTitle>Dividends per share</CardTitle>
          {dividends.basis && <span className="font-mono text-micro text-ash">{dividends.basis}</span>}
        </CardHeader>
        <CardBody className="space-y-3">
          {dividends.available && dividends.perShare.length > 0 ? (
            <>
              <div className="h-28" aria-hidden>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={dividends.perShare} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
                    <XAxis dataKey="year" tick={{ fontSize: 10, fill: palette.axis }} axisLine={false} tickLine={false} />
                    <YAxis hide />
                    <Bar dataKey="amount" isAnimationActive={false} radius={[2, 2, 0, 0]}>
                      {dividends.perShare.map((d) => (
                        <Cell key={d.year} fill={palette.company}
                              fillOpacity={d.partial ? 0.25 : 0.6}
                              stroke={d.partial ? alpha(palette.company, 0.7) : undefined}
                              strokeDasharray={d.partial ? "3 2" : undefined} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <table className="w-full text-left text-meta">
                <caption className="sr-only">Dividends per share by calendar year</caption>
                <tbody>
                  <tr className="[&>td]:px-2 [&>td]:py-1">
                    {dividends.perShare.map((d) => (
                      <td key={d.year} className="text-center">
                        <div className="text-micro text-faint">{d.year}{d.partial ? " · to date" : ""}</div>
                        <div className="num text-body">{num(d.amount, d.amount < 10 ? 3 : 0)}</div>
                      </td>
                    ))}
                  </tr>
                </tbody>
              </table>
              <p className="text-meta text-ash">{dividends.reading}</p>
            </>
          ) : (
            <StateCard kind="empty" bare title="No dividend series">{dividends.reading}</StateCard>
          )}
        </CardBody>
      </Card>
    </div>
  );
}

function HistoryTable({
  history, guided,
}: { history: Extract<CompanyResponse["history"], { available: true }>; guided: boolean }) {
  const table = (
    <div className="overflow-x-auto rounded-lg border border-ruleSoft">
      <table className="w-full min-w-[32rem] text-left text-meta">
        <caption className="sr-only">Statement lines by fiscal year, in {history.currency ?? "the reporting currency"}</caption>
        <thead>
          <tr className="eyebrow border-b border-rule bg-sunken [&>th]:px-3 [&>th]:py-2 [&>th]:font-normal">
            <th scope="col">Line</th>
            {history.fiscalYears.map((y) => <th key={y} scope="col" className="text-right">{y}</th>)}
          </tr>
        </thead>
        <tbody>
          {FULL_ROWS.map((key) => (
            <tr key={key} className="border-b border-ruleSoft last:border-0">
              <th scope="row" className="px-3 py-1.5 font-normal text-ash">{ROW_LABEL[key]}</th>
              {history.rows[key].map((v, i) => (
                <td key={i} className={cn("num px-3 py-1.5 text-right", v == null ? "text-faint" : "text-body")}>
                  {v == null ? "—" : key === "dilutedEps" ? num(v) : compact(v)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
  return guided ? (
    <Explainer summary="Every line, every year, as figures — a dash is a year the source did not report, never a zero">
      {table}
    </Explainer>
  ) : (
    <>
      {table}
      <p className="text-micro text-faint">A dash is a year the source did not report, never a zero.</p>
    </>
  );
}
