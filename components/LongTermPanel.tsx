"use client";

import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { Check, Minus, X } from "lucide-react";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Explain, ExplainedRow, ExplainedStat, TONE_HEX, useDetail,
} from "@/components/ui/explain";
import { useHorizon } from "@/components/ui/horizon";
import type { ExplainMap, LongTermBlock } from "@/lib/types";
import { cn, num, pct, signedPct } from "@/lib/utils";

const UP = "#35C4A8";
const DOWN = "#FF6B6B";
const ASH = "#7A8CA0";

/**
 * The long-horizon view: what holding this would actually have been like.
 *
 * TWO CHANGES OF PRINCIPLE FROM THE FIRST VERSION, both about comprehension.
 *
 * First, it opens with PROSE. The tables underneath were correct and complete
 * and unreadable to anyone who did not already know what Sortino, Calmar and
 * the Ulcer index were — which is to say, unreadable to the person the tool is
 * for. The paragraph at the top is the same evidence said out loud, and it is
 * built server-side (`_lib/explain.py`) so it is testable against the numbers
 * it claims to describe.
 *
 * Second, NO COMPONENT HERE DECIDES WHAT A NUMBER MEANS. Colour comes from
 * `explain[key].tone`, which was decided in Python with a test asserting that
 * a low Ulcer index is green and a deep drawdown is red. The old version wrote
 * `tone={value >= 0 ? "text-acc" : "text-dist"}` at each call site, which is
 * right for CAGR, wrong for drawdown, and impossible to audit at a glance.
 *
 * Ordering is unchanged and still deliberate: the rolling-return table comes
 * before any indicator, and the drawdown section before the upside, because
 * the depth and DURATION of past declines is what decides whether someone
 * actually holds long enough to collect the return.
 */
export function LongTermPanel({ data, currency }: { data: LongTermBlock; currency: string }) {
  const { view, drawdown, risk, rollingReturns, seasonality, position,
          faber, relativeStrength, regression, calendarReturns,
          plainEnglish } = data;
  const detail = useDetail();
  const simple = detail === "simple";
  const horizon = useHorizon();
  const ex: ExplainMap = data.explain ?? {};

  const verdictColor = view.tone === "bull" ? UP : view.tone === "bear" ? DOWN : ASH;

  const drawdownSeries = (drawdown.series ?? []).filter((_, i, all) =>
    all.length <= 1200 || i % Math.ceil(all.length / 1200) === 0);

  // Simple mode keeps the checks that carry a verdict and drops the ones with
  // no reading — a row saying "needs 200 bars of history" is honest but it is
  // not what someone asked to be shown less of came for.
  const checks = simple ? view.checks.filter((c) => c.passed !== null) : view.checks;

  return (
    <div className="space-y-4 animate-rise">
      {/* ---------------- the summary in plain English ---------------- */}
      {plainEnglish && plainEnglish.paragraphs.length > 0 && (
        <Card accent={verdictColor}>
          <CardHeader>
            <CardTitle>In plain English</CardTitle>
            <span className="num text-xs font-semibold" style={{ color: verdictColor }}>
              {view.verdict}
            </span>
          </CardHeader>
          <CardBody className="space-y-3">
            {plainEnglish.paragraphs.map((paragraph, i) => (
              <p key={i}
                 className={cn(
                   "leading-relaxed",
                   i === plainEnglish.paragraphs.length - 1
                     ? "text-[0.78rem] text-ash"
                     : "text-[0.95rem] text-chalk/90",
                 )}>
                {paragraph}
              </p>
            ))}
          </CardBody>
        </Card>
      )}

      {/* ---------------- the numbers that decide a holding ---------------- */}
      {plainEnglish && (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
          {plainEnglish.simpleMetrics.map((key) => {
            const explain = ex[key];
            if (!explain) return null;
            return <ExplainedStat key={key} explain={explain} />;
          })}
        </div>
      )}

      {/* ---------------- verdict + checklist ---------------- */}
      <Card>
        <CardHeader>
          <CardTitle>Long-horizon checklist</CardTitle>
          <span className="num text-xs font-semibold" style={{ color: verdictColor }}>
            {view.passed}/{view.scored} pointing up
          </span>
        </CardHeader>
        <CardBody className="px-0">
          <p className="px-5 pb-3 text-sm leading-relaxed text-chalk/85">{view.headline}</p>
          <ul>
            {checks.map((check) => (
              <li key={check.label}
                  className="flex items-baseline gap-3 border-b border-rule/60 px-5 py-2 last:border-0">
                <span className="mt-0.5 shrink-0">
                  {check.passed === null
                    ? <Minus aria-label="no reading" className="h-3.5 w-3.5 text-ash" />
                    : check.passed
                      ? <Check aria-label="points up" className="h-3.5 w-3.5 text-acc" />
                      : <X aria-label="points down" className="h-3.5 w-3.5 text-dist" />}
                </span>
                <span className="w-56 shrink-0 text-xs text-chalk/90">{check.label}</span>
                <span className="flex-1 text-[0.7rem] leading-relaxed text-ash">
                  {check.detail}
                </span>
              </li>
            ))}
          </ul>
          <p className="px-5 pt-3 text-[0.7rem] leading-relaxed text-ash">
            A tick means that line points upward, not that it is a reason to buy. {view.caveat}
          </p>
        </CardBody>
      </Card>

      {/* ---------------- rolling returns: the headline table ---------------- */}
      {rollingReturns.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>If you had bought at any point and held</CardTitle>
            <span className="font-mono text-[0.65rem] text-ash">% per year</span>
          </CardHeader>
          <CardBody className="px-0">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="eyebrow border-b border-rule [&>th]:px-5 [&>th]:py-2 [&>th]:font-normal">
                    <th>Held for</th>
                    <th className="text-right">Worst</th>
                    {!simple && <th className="text-right">P25</th>}
                    <th className="text-right">Typical</th>
                    {!simple && <th className="text-right">P75</th>}
                    <th className="text-right">Best</th>
                    <th className="text-right">Made money</th>
                    {!simple && <th className="text-right">Windows</th>}
                  </tr>
                </thead>
                <tbody>
                  {rollingReturns.map((row) => {
                    // A HORIZON THE HISTORY CANNOT SUPPORT GETS A ROW SAYING SO.
                    // These used to be dropped, and on the app's default range
                    // the five-year row usually was — leaving a reader unable to
                    // tell whether the stock had never had a bad five-year
                    // stretch or whether nobody had looked.
                    const measured = row.usable !== false && row.worst != null;
                    const chosen = row.years === horizon;
                    if (!measured) {
                      return (
                        <tr key={row.years} className="border-b border-rule/60 last:border-0">
                          <td className={cn("num px-5 py-2 font-semibold",
                                            chosen ? "text-chalk" : "text-ash")}>
                            <span className="flex items-center gap-1.5">
                              {row.years}y
                              <Explain explain={ex[`rollingWorst.${row.years}`]} />
                            </span>
                          </td>
                          <td className="px-5 py-2 text-[0.7rem] leading-relaxed text-ash"
                              colSpan={simple ? 4 : 7}>
                            {row.reason ?? "Not enough loaded history for this horizon."}
                          </td>
                        </tr>
                      );
                    }
                    return (
                      <tr key={row.years}
                          className={cn("border-b border-rule/60 last:border-0 hover:bg-raised/60",
                                        chosen && "bg-raised/70")}>
                        <td className="num px-5 py-2 font-semibold">
                          <span className="flex items-center gap-1.5">
                            {row.years}y
                            {chosen && (
                              <span className="eyebrow text-tech" title="your stated horizon">
                                yours
                              </span>
                            )}
                            <Explain explain={ex[`rollingWorst.${row.years}`]} />
                          </span>
                        </td>
                        <td className={cn("num px-5 py-2 text-right",
                                          (row.worst ?? 0) >= 0 ? "text-acc" : "text-dist")}>
                          {signedPct(row.worst)}
                        </td>
                        {!simple && (
                          <td className="num px-5 py-2 text-right text-ash">{signedPct(row.p25)}</td>
                        )}
                        <td className="num px-5 py-2 text-right font-semibold">
                          {signedPct(row.median)}
                        </td>
                        {!simple && (
                          <td className="num px-5 py-2 text-right text-ash">{signedPct(row.p75)}</td>
                        )}
                        <td className="num px-5 py-2 text-right text-acc">{signedPct(row.best)}</td>
                        <td className="num px-5 py-2 text-right">{pct(row.positiveShare, 0)}</td>
                        {!simple && (
                          <td className="num px-5 py-2 text-right text-ash">{row.windows}</td>
                        )}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="px-5 pt-3 text-[0.7rem] leading-relaxed text-ash">
              Read a row like this: &quot;buying on any day in this history and holding for that
              many years, here is the range of yearly returns you would have got&quot;. The
              <span className="text-chalk/80"> worst </span>column is the one that decides
              position size — a headline growth rate quietly reports only the one path that
              happened to occur.
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
              time spent below a previous high
            </span>
          </CardHeader>
          <CardBody>
            <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
              <ExplainedStat explain={ex.maxDrawdown}
                             sub={`${drawdown.maxDrawdownPeak} → ${drawdown.maxDrawdownTrough}`} />
              <ExplainedStat explain={ex.maxDrawdownRecoveryDays}
                             sub={drawdown.maxDrawdownRecovered
                               ? `back to even ${drawdown.maxDrawdownRecovered}`
                               : "still below that peak"} />
              <ExplainedStat explain={ex.timeUnderWaterDays}
                             sub="longest run of days with no new high" />
              <ExplainedStat explain={ex.ulcerIndex} sub="depth and duration combined" />
            </div>

            {!simple && (
              <>
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
                      formatter={(v: number) => [pct(v), "below the high"]} />
                    <ReferenceLine y={0} stroke="#1E2A36" />
                    <Area type="monotone" dataKey="drawdown" stroke={DOWN} strokeWidth={1}
                          fill="url(#ddFill)" isAnimationActive={false} />
                  </AreaChart>
                </ResponsiveContainer>
                <p className="mt-1 text-[0.7rem] leading-relaxed text-ash">
                  The line is how far below its best-ever price it sat on each day. Zero means a
                  new high; every dip is a stretch where holders were down on paper.
                </p>
              </>
            )}

            <p className="mt-3 text-[0.7rem] leading-relaxed text-ash">
              Depth is only half of it. A 30% fall that recovers in a quarter is survivable; a
              15% one that grinds on for three years is where most people sell. The Ulcer index
              scores both at once, which is why it is here beside the maximum.
            </p>
          </CardBody>
        </Card>
      )}

      {/* ---------------- risk-adjusted return ---------------- */}
      {risk.usable && !simple && (
        <Card>
          <CardHeader>
            <CardTitle>Was the risk paid for?</CardTitle>
            <span className="font-mono text-[0.65rem] text-ash">
              over {risk.observations} trading days
            </span>
          </CardHeader>
          <CardBody>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <ExplainedStat explain={ex.cagr} />
              <ExplainedStat explain={ex.volatility}
                             sub={`downside only ${pct(risk.downsideDeviation)}`} />
              <ExplainedStat explain={ex.sortino} sub={`Sharpe ${num(risk.sharpe ?? 0)}`} />
              <ExplainedStat explain={ex.calmar} />
              <ExplainedStat explain={ex.var95} />
              <ExplainedStat explain={ex.cvar95} />
              <ExplainedStat explain={ex.skew} />
              <ExplainedStat explain={ex.kurtosis} />
            </div>
          </CardBody>
        </Card>
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
                    <th className="text-right">Difference</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(relativeStrength.periods).map(([label, row]) => {
                    const explain = ex[`relativeExcess.${label}`];
                    return (
                      <tr key={label} className="border-b border-rule/60 last:border-0">
                        <td className="num px-5 py-2">
                          <span className="flex items-center gap-1.5">
                            {label}
                            <Explain explain={explain} />
                          </span>
                        </td>
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
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="px-5 pt-3 text-[0.7rem] leading-relaxed text-ash">
              The real alternative is never cash — it is the index fund you could have bought
              instead. A stock up 40% while the market rose 60% has cost its holder money in the
              only sense that matters.
            </p>
          </CardBody>
        </Card>
      )}

      {/* ---------------- position and timing ---------------- */}
      {!simple && (
        <div className="grid gap-4 lg:grid-cols-2">
          {position.usable && (
            <Card>
              <CardHeader><CardTitle>Where it sits</CardTitle></CardHeader>
              <CardBody className="space-y-2 text-xs">
                <ExplainedRow explain={ex.fromHigh52w} />
                <ExplainedRow explain={ex.rangePosition} />
                <ExplainedRow explain={ex.fromAllTimeHigh} />
                <ExplainedRow label="52-week high"
                              value={`${currency} ${num(position.high52w ?? 0)}`}
                              tone="text-chalk" />
                <ExplainedRow label="52-week low"
                              value={`${currency} ${num(position.low52w ?? 0)}`}
                              tone="text-chalk" />
                <ExplainedRow explain={ex.benchmarkCorrelation} />
              </CardBody>
            </Card>
          )}

          {faber.usable && (
            <Card accent={TONE_HEX[ex.faberDistance?.tone ?? "neutral"]}>
              <CardHeader>
                <CardTitle>A simple long-term trend rule</CardTitle>
                <span className={cn("num text-xs font-semibold",
                                    faber.signal === "invested" ? "text-acc" : "text-dist")}>
                  {faber.signal === "invested" ? "Stay invested" : "Stand aside"}
                </span>
              </CardHeader>
              <CardBody className="space-y-2 text-xs">
                <ExplainedRow explain={ex.faberDistance} />
                <ExplainedRow label="Months in this stance"
                              value={String(faber.monthsInStance ?? 0)} tone="text-chalk" />
                <ExplainedRow label="Share of history invested"
                              value={pct(faber.sharOfTimeInvested, 0)} tone="text-chalk" />
                {regression && (
                  <>
                    <ExplainedRow explain={ex.regressionSlope} />
                    <ExplainedRow explain={ex.regressionR2} />
                  </>
                )}
                <ExplainedRow explain={ex.hurst} />
                <ExplainedRow explain={ex.momentum12_1} />
              </CardBody>
            </Card>
          )}
        </div>
      )}

      {/* ---------------- calendar returns ---------------- */}
      {calendarReturns.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Year by year</CardTitle>
            <span className="font-mono text-[0.65rem] text-ash">total return each year</span>
          </CardHeader>
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
      {seasonality.usable && !simple && (
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
