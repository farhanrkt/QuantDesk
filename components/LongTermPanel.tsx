"use client";

import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { Check, Minus, X } from "lucide-react";
import { Card, CardBody, CardHeader, CardTitle, Stat } from "@/components/ui/card";
import type { LongTermBlock } from "@/lib/types";
import { cn, num, pct, signedPct } from "@/lib/utils";

const UP = "#35C4A8";
const DOWN = "#FF6B6B";
const ASH = "#7A8CA0";

/**
 * The long-horizon view: what holding this would actually have been like.
 *
 * Ordered by what decides a multi-year holding, not by what is conventional.
 * The rolling-return table comes before any indicator, because "every 5-year
 * window in this history returned between +12% and +47% a year" tells an
 * investor more than every oscillator on the page combined — and the drawdown
 * section comes before the upside, because the depth and DURATION of past
 * declines is what determines whether someone actually holds long enough to
 * collect the return.
 */
export function LongTermPanel({ data, currency }: { data: LongTermBlock; currency: string }) {
  const { view, drawdown, risk, rollingReturns, seasonality, position,
          faber, relativeStrength, regression, calendarReturns } = data;

  const verdictColor = view.tone === "bull" ? UP : view.tone === "bear" ? DOWN : ASH;

  const drawdownSeries = (drawdown.series ?? []).filter((_, i, all) =>
    all.length <= 1200 || i % Math.ceil(all.length / 1200) === 0);

  return (
    <div className="space-y-4 animate-rise">
      {/* ---------------- verdict + checklist ---------------- */}
      <Card accent={verdictColor}>
        <CardHeader>
          <CardTitle>Long-horizon checklist</CardTitle>
          <span className="num text-xs font-semibold" style={{ color: verdictColor }}>
            {view.verdict} · {view.passed}/{view.scored}
          </span>
        </CardHeader>
        <CardBody className="px-0">
          <p className="px-5 pb-3 text-sm leading-relaxed text-chalk/85">{view.headline}</p>
          <ul>
            {view.checks.map((check) => (
              <li key={check.label}
                  className="flex items-baseline gap-3 border-b border-rule/60 px-5 py-2 last:border-0">
                <span className="mt-0.5 shrink-0">
                  {check.passed === null
                    ? <Minus aria-label="no reading" className="h-3.5 w-3.5 text-ash" />
                    : check.passed
                      ? <Check aria-label="pass" className="h-3.5 w-3.5 text-acc" />
                      : <X aria-label="fail" className="h-3.5 w-3.5 text-dist" />}
                </span>
                <span className="w-56 shrink-0 text-xs text-chalk/90">{check.label}</span>
                <span className="flex-1 text-[0.7rem] leading-relaxed text-ash">
                  {check.detail}
                </span>
              </li>
            ))}
          </ul>
          <p className="px-5 pt-3 text-[0.7rem] leading-relaxed text-ash">{view.caveat}</p>
        </CardBody>
      </Card>

      {/* ---------------- rolling returns: the headline table ---------------- */}
      {rollingReturns.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>If you had bought at any point and held</CardTitle>
            <span className="font-mono text-[0.65rem] text-ash">annualised</span>
          </CardHeader>
          <CardBody className="px-0">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="eyebrow border-b border-rule [&>th]:px-5 [&>th]:py-2 [&>th]:font-normal">
                    <th>Held for</th>
                    <th className="text-right">Worst</th>
                    <th className="text-right">P25</th>
                    <th className="text-right">Median</th>
                    <th className="text-right">P75</th>
                    <th className="text-right">Best</th>
                    <th className="text-right">Positive</th>
                    <th className="text-right">Windows</th>
                  </tr>
                </thead>
                <tbody>
                  {rollingReturns.map((row) => (
                    <tr key={row.years}
                        className="border-b border-rule/60 last:border-0 hover:bg-raised/60">
                      <td className="num px-5 py-2 font-semibold">{row.years}y</td>
                      <td className={cn("num px-5 py-2 text-right",
                                        row.worst >= 0 ? "text-acc" : "text-dist")}>
                        {signedPct(row.worst)}
                      </td>
                      <td className="num px-5 py-2 text-right text-ash">{signedPct(row.p25)}</td>
                      <td className="num px-5 py-2 text-right font-semibold">
                        {signedPct(row.median)}
                      </td>
                      <td className="num px-5 py-2 text-right text-ash">{signedPct(row.p75)}</td>
                      <td className="num px-5 py-2 text-right text-acc">{signedPct(row.best)}</td>
                      <td className="num px-5 py-2 text-right">{pct(row.positiveShare, 0)}</td>
                      <td className="num px-5 py-2 text-right text-ash">{row.windows}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="px-5 pt-3 text-[0.7rem] leading-relaxed text-ash">
              Every overlapping holding period in this history, not one lucky start date. The
              <span className="text-chalk/80"> worst </span>column is the one that decides
              position size — a headline CAGR quietly reports only the path that happened.
            </p>
          </CardBody>
        </Card>
      )}

      {/* ---------------- drawdown ---------------- */}
      {drawdown.usable && (
        <Card accent={DOWN}>
          <CardHeader>
            <CardTitle>What holding it cost</CardTitle>
            <span className="font-mono text-[0.65rem] text-ash">
              underwater history
            </span>
          </CardHeader>
          <CardBody>
            <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
              <Stat label="Worst drawdown" value={pct(drawdown.maxDrawdown ?? 0)}
                    tone="text-dist"
                    sub={`${drawdown.maxDrawdownPeak} → ${drawdown.maxDrawdownTrough}`} />
              <Stat label="Recovered"
                    value={drawdown.maxDrawdownRecovered ?? "not yet"}
                    sub={drawdown.maxDrawdownRecoveryDays
                      ? `${drawdown.maxDrawdownRecoveryDays} days to get back`
                      : "still below that peak"} />
              <Stat label="Longest underwater"
                    value={`${drawdown.timeUnderWaterDays} d`}
                    sub="consecutive days below a prior high" />
              <Stat label="Ulcer index" value={num(drawdown.ulcerIndex ?? 0, 1)}
                    sub="depth and duration combined" />
            </div>

            <ResponsiveContainer width="100%" height={170}>
              <AreaChart data={drawdownSeries} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="ddFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={DOWN} stopOpacity={0.05} />
                    <stop offset="100%" stopColor={DOWN} stopOpacity={0.35} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="2 4" vertical={false} />
                <XAxis dataKey="date" tickLine={false} axisLine={false} minTickGap={64} />
                <YAxis tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
                       tickLine={false} axisLine={false} width={48} />
                <Tooltip
                  contentStyle={{ background: "#080C10E6", border: "1px solid #1E2A36",
                                  borderRadius: 4, fontSize: 12 }}
                  formatter={(v: number) => [pct(v), "drawdown"]} />
                <ReferenceLine y={0} stroke="#1E2A36" />
                <Area type="monotone" dataKey="drawdown" stroke={DOWN} strokeWidth={1}
                      fill="url(#ddFill)" isAnimationActive={false} />
              </AreaChart>
            </ResponsiveContainer>

            <p className="mt-3 text-[0.7rem] leading-relaxed text-ash">
              Depth is only half of it. A 30% fall that recovers in a quarter is survivable; a
              15% one that grinds on for three years is where most people sell. The Ulcer index
              scores both at once, which is why it is here beside the maximum.
            </p>
          </CardBody>
        </Card>
      )}

      {/* ---------------- risk-adjusted return ---------------- */}
      {risk.usable && (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Stat label="CAGR" value={signedPct(risk.cagr)}
                tone={(risk.cagr ?? 0) >= 0 ? "text-acc" : "text-dist"}
                sub={`over ${risk.observations} trading days`} />
          <Stat label="Volatility" value={pct(risk.volatility)}
                sub={`downside ${pct(risk.downsideDeviation)}`} />
          <Stat label="Sortino" value={num(risk.sortino ?? 0)}
                sub={`Sharpe ${num(risk.sharpe ?? 0)}`} />
          <Stat label="Calmar"
                value={risk.calmar == null ? "—" : num(risk.calmar)}
                sub="return per unit of worst drawdown" />
          <Stat label="Worst day" value={pct(risk.worstDay)} tone="text-dist"
                sub={`best ${pct(risk.bestDay)}`} />
          <Stat label="VaR 95%" value={pct(risk.var95)}
                sub={`beyond it, ${pct(risk.cvar95)} average`} />
          <Stat label="Up days" value={pct(risk.positiveDays, 0)}
                sub={`skew ${num(risk.skew ?? 0)}`} />
          <Stat label="Fat tails" value={num(risk.kurtosis ?? 0, 1)}
                sub="excess kurtosis" />
        </div>
      )}

      {/* ---------------- relative strength ---------------- */}
      {relativeStrength.usable && relativeStrength.periods && (
        <Card accent={relativeStrength.outperforming ? UP : DOWN}>
          <CardHeader>
            <CardTitle>Against just owning the index</CardTitle>
            <span className="font-mono text-[0.65rem] text-ash">
              vs {relativeStrength.benchmark}
            </span>
          </CardHeader>
          <CardBody className="px-0">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="eyebrow border-b border-rule [&>th]:px-5 [&>th]:py-2 [&>th]:font-normal">
                    <th>Period</th>
                    <th className="text-right">This stock</th>
                    <th className="text-right">{relativeStrength.benchmark}</th>
                    <th className="text-right">Excess</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(relativeStrength.periods).map(([label, row]) => (
                    <tr key={label} className="border-b border-rule/60 last:border-0">
                      <td className="num px-5 py-2">{label}</td>
                      <td className="num px-5 py-2 text-right">
                        {row ? signedPct(row.stock) : "—"}
                      </td>
                      <td className="num px-5 py-2 text-right text-ash">
                        {row ? signedPct(row.benchmark) : "—"}
                      </td>
                      <td className={cn("num px-5 py-2 text-right font-semibold",
                                        (row?.excess ?? 0) >= 0 ? "text-acc" : "text-dist")}>
                        {row ? signedPct(row.excess) : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="px-5 pt-3 text-[0.7rem] leading-relaxed text-ash">
              The real alternative is never cash — it is the index fund you could have bought
              instead. A stock up 40% while the market rose 60% has cost its holder money in the
              only sense that matters. Correlation with the benchmark:{" "}
              {num(relativeStrength.correlation ?? 0)}.
            </p>
          </CardBody>
        </Card>
      )}

      {/* ---------------- position and timing ---------------- */}
      <div className="grid gap-4 lg:grid-cols-2">
        {position.usable && (
          <Card>
            <CardHeader><CardTitle>Where it sits</CardTitle></CardHeader>
            <CardBody className="space-y-2 text-xs">
              <Row label="From 52-week high" value={signedPct(position.fromHigh52w)}
                   tone={(position.fromHigh52w ?? 0) > -0.1 ? "text-acc" : "text-ash"} />
              <Row label="From 52-week low" value={signedPct(position.fromLow52w)} />
              <Row label="From all-time high" value={signedPct(position.fromAllTimeHigh)}
                   tone={(position.fromAllTimeHigh ?? 0) < -0.2 ? "text-dist" : "text-ash"} />
              <Row label="52-week range position"
                   value={pct(position.rangePosition, 0)} />
              <Row label="52-week high"
                   value={`${currency} ${num(position.high52w ?? 0)}`} />
              <Row label="52-week low"
                   value={`${currency} ${num(position.low52w ?? 0)}`} />
            </CardBody>
          </Card>
        )}

        {faber.usable && (
          <Card accent={faber.signal === "invested" ? UP : DOWN}>
            <CardHeader>
              <CardTitle>Faber 10-month rule</CardTitle>
              <span className={cn("num text-xs font-semibold",
                                  faber.signal === "invested" ? "text-acc" : "text-dist")}>
                {faber.signal === "invested" ? "Invested" : "Defensive"}
              </span>
            </CardHeader>
            <CardBody className="space-y-2 text-xs">
              <Row label="Monthly close vs 10-month average"
                   value={signedPct(faber.distance)} />
              <Row label="Months in this stance" value={String(faber.monthsInStance ?? 0)} />
              <Row label="Share of history invested"
                   value={pct(faber.sharOfTimeInvested, 0)} />
              {regression && (
                <>
                  <Row label="Fitted trend" value={`${signedPct(regression.slopePerYear)} / yr`} />
                  <Row label="Trend fit (R²)" value={pct(regression.rSquared, 0)}
                       tone={(regression.rSquared ?? 0) < 0.5 ? "text-warn" : "text-ash"} />
                </>
              )}
              <p className="pt-2 text-[0.7rem] leading-relaxed text-ash">
                Hold while the monthly close is above its 10-month average, stand aside below.
                It trades a couple of times a year and its documented value is shallower
                drawdowns rather than higher returns — which is the variable that decides
                whether a long-term holder stays invested at all.
              </p>
            </CardBody>
          </Card>
        )}
      </div>

      {/* ---------------- calendar returns ---------------- */}
      {calendarReturns.length > 0 && (
        <Card>
          <CardHeader><CardTitle>Year by year</CardTitle></CardHeader>
          <CardBody>
            <ResponsiveContainer width="100%" height={150}>
              <BarChart data={calendarReturns} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="2 4" vertical={false} />
                <XAxis dataKey="year" tickLine={false} axisLine={false} />
                <YAxis tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
                       tickLine={false} axisLine={false} width={48} />
                <Tooltip
                  contentStyle={{ background: "#080C10E6", border: "1px solid #1E2A36",
                                  borderRadius: 4, fontSize: 12 }}
                  formatter={(v: number) => [signedPct(v), "return"]} />
                <ReferenceLine y={0} stroke="#1E2A36" />
                <Bar dataKey="return" isAnimationActive={false}>
                  {calendarReturns.map((row) => (
                    <Cell key={row.year} fill={(row.return ?? 0) >= 0 ? UP : DOWN} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </CardBody>
        </Card>
      )}

      {/* ---------------- seasonality, clearly labelled ---------------- */}
      {seasonality.usable && (
        <Card>
          <CardHeader>
            <CardTitle>Average return by calendar month</CardTitle>
            <span className="font-mono text-[0.65rem] text-warn">descriptive only</span>
          </CardHeader>
          <CardBody>
            <div className="grid grid-cols-6 gap-2 lg:grid-cols-12">
              {seasonality.months.map((month) => {
                const value = month.mean ?? 0;
                const intensity = Math.min(Math.abs(value) / 0.05, 1);
                return (
                  <div key={month.month}
                       className="rounded border border-rule px-1.5 py-2 text-center"
                       style={{
                         background: month.mean == null ? "transparent"
                           : `${value >= 0 ? UP : DOWN}${Math.round(intensity * 40)
                               .toString(16).padStart(2, "0")}`,
                       }}>
                    <div className="font-mono text-[0.6rem] uppercase text-ash">{month.month}</div>
                    <div className={cn("num text-[0.7rem]",
                                       value >= 0 ? "text-acc" : "text-dist")}>
                      {month.mean == null ? "—" : signedPct(month.mean)}
                    </div>
                    <div className="text-[0.55rem] text-ash">n={month.count}</div>
                  </div>
                );
              })}
            </div>
            <p className="mt-3 text-[0.7rem] leading-relaxed text-warn">
              {seasonality.caveat}
            </p>
          </CardBody>
        </Card>
      )}
    </div>
  );
}

function Row({ label, value, tone = "text-ash" }: {
  label: string; value: string; tone?: string;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-rule/40 pb-1.5 last:border-0">
      <span className="text-ash">{label}</span>
      <span className={cn("num font-semibold", tone)}>{value}</span>
    </div>
  );
}
