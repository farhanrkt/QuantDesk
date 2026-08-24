"use client";

import {
  Area, Bar, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer,
  Scatter, Tooltip, XAxis, YAxis,
} from "recharts";
import type { TooltipProps } from "recharts";
import { useState } from "react";
import { Card, CardBody, CardHeader, CardTitle, Stat } from "@/components/ui/card";
import { IndicatorGrid } from "@/components/IndicatorGrid";
import { HorizonPanel } from "@/components/HorizonPanel";
import { LongTermPanel } from "@/components/LongTermPanel";
import { Tabs } from "@/components/ui/tabs";
import { useDetail } from "@/components/ui/explain";
import { ApplyButton, DownloadButton, Field, NumberField } from "@/components/ui/controls";
import type { TechnicalOptions } from "@/lib/api";
import type { TechPoint, TechnicalResponse } from "@/lib/types";
import { downloadCsv, toCsv } from "@/lib/csv";
import { TONE, cn, num, splitEmphasis } from "@/lib/utils";

const TECH = "#5B8DEF";
const FAST = "#F2C14E";
const SLOW = "#7FA8F5";
const BAND = "#A78BFA";
const UP = "#35C4A8";
const DOWN = "#FF6B6B";

/** A series row plus the derived columns the band and marker layers read. */
type ChartPoint = TechPoint & {
  bbBase: number | null;
  bbSpan: number | null;
  buy: number | null;
  sell: number | null;
};

function TechTooltip({ active, payload }: TooltipProps<number, string>) {
  // Recharts types `payload[n].payload` as the untyped source row; this is the
  // one place the cast belongs, and ChartPoint is exactly what we put in.
  const p = payload?.[0]?.payload as ChartPoint | undefined;
  if (!active || !p) return null;
  return (
    <div className="rounded border border-rule bg-ink/95 px-3 py-2 text-xs">
      <div className="num mb-1 text-ash">{p.date}</div>
      <div className="num">O {num(p.open)} · H {num(p.high)} · L {num(p.low)} · C {num(p.close)}</div>
      {p.sma50 != null && <div className="num" style={{ color: FAST }}>50-day {num(p.sma50)}</div>}
      {p.sma200 != null && <div className="num" style={{ color: SLOW }}>200-day {num(p.sma200)}</div>}
      {p.rsi != null && <div className="num text-ash">RSI {num(p.rsi, 1)}</div>}
    </div>
  );
}

export function TechnicalPanel({
  data, onApply, busy,
}: {
  data: TechnicalResponse;
  onApply: (o: TechnicalOptions) => void;
  busy: boolean;
}) {
  const { latest, summary, series, levels, signals } = data;

  // Defaults mirror api/_lib/technical.py analyze().
  const [srWindow, setSrWindow] = useState(10);
  const [srLevels, setSrLevels] = useState(6);
  // The long-horizon view leads, because that is the question this lens is
  // most often asked and the one the chart alone cannot answer. The two shorter
  // horizons sit beside it as siblings rather than underneath it: they answer a
  // DIFFERENT question ("where would the levels be if I bought this month?"),
  // not a more detailed version of the same one, and nesting them would imply
  // otherwise.
  const [section, setSection] = useState(data.hasLongTerm ? "long" : "chart");
  const guided = useDetail() === "simple";

  const downloadSeries = () =>
    downloadCsv(
      `${data.ticker}_${data.range}_indicators.csv`,
      toCsv(series, [
        { key: "date", label: "Date" }, { key: "open", label: "Open" },
        { key: "high", label: "High" }, { key: "low", label: "Low" },
        { key: "close", label: "Close" }, { key: "volume", label: "Volume" },
        { key: "sma50", label: "SMA_50" }, { key: "sma200", label: "SMA_200" },
        { key: "bbLower", label: "BB_LOWER" }, { key: "bbMid", label: "BB_MID" },
        { key: "bbUpper", label: "BB_UPPER" }, { key: "rsi", label: "RSI" },
        { key: "macd", label: "MACD" }, { key: "macdSignal", label: "MACD_SIGNAL" },
        { key: "macdHist", label: "MACD_HIST" }, { key: "signal", label: "Signal" },
      ])
    );

  const downloadSignals = () =>
    downloadCsv(
      `${data.ticker}_crossovers.csv`,
      toCsv(signals, [
        { key: "date", label: "Date" }, { key: "type", label: "Signal" },
        { key: "description", label: "What happened" },
        { key: "price", label: "Price that day" },
        { key: "changeSince", label: "Change since (%)" },
      ])
    );

  const chartData = series.map((p) => ({
    ...p,
    // Recharts stacks an invisible base plus a visible band to fake a range fill.
    bbBase: p.bbLower,
    bbSpan: p.bbUpper != null && p.bbLower != null ? p.bbUpper - p.bbLower : null,
    buy: p.signal === "Buy" ? p.low * 0.97 : null,
    sell: p.signal === "Sell" ? p.high * 1.03 : null,
  }));

  // Ordered longest-first, deliberately. Reading left to right walks from the
  // question with the strongest evidence behind it to the one with the weakest,
  // which is the order a reader should weigh them in.
  // GUIDED DROPS "ALL INDICATORS" AND NOTHING ELSE. That grid is forty-odd raw
  // readings — Aroon, CCI, Williams %R, Coppock — and it is the densest wall of
  // jargon in the app. Every other section here leads with a sentence, so they
  // survive. This is the one place where hiding beats collapsing: a beginner who
  // opens that tab does not get a gentler version of the lens, they get the
  // reason they stop using it. The line below the tabs says it is one click
  // away in Full, so nothing disappears silently.
  const SECTIONS = [
    ...(data.hasLongTerm ? [{ id: "long", label: "Long term · years", accent: "#35C4A8" }] : []),
    { id: "mid", label: "Mid term · weeks–months", accent: "#5B8DEF" },
    { id: "short", label: "Short term · days–weeks", accent: "#F2C14E" },
    { id: "chart", label: "Chart & signals", accent: "#A78BFA" },
    ...(guided ? [] : [{ id: "indicators", label: "All indicators", accent: "#A78BFA" }]),
  ];

  // A section that is open when the mode changes underneath it would otherwise
  // leave the panel blank — the tab is gone but `section` still names it. Derived
  // rather than corrected in an effect, so there is no frame where the panel has
  // rendered empty and no second render to fix it.
  const active = SECTIONS.some((s) => s.id === section) ? section : SECTIONS[0].id;

  return (
    <div className="space-y-4 animate-rise">
      <Tabs tabs={SECTIONS} active={active} onChange={setSection} />
      {guided && (
        <p className="text-[0.68rem] text-ash">
          Switch to <span className="text-chalk/80">Full</span> for the complete indicator
          grid — ADX, Aroon, Stochastic, Williams %R, CCI, Coppock and the rest, grouped by
          the horizon each one speaks to.
        </p>
      )}

      {active === "long" && data.hasLongTerm && (
        <LongTermPanel data={data.longTerm} currency={data.currency} />
      )}

      {active === "mid" && (
        <HorizonPanel data={data.midTerm} currency={data.currency} />
      )}

      {active === "short" && (
        <HorizonPanel data={data.shortTerm} currency={data.currency} />
      )}

      {active === "indicators" && (
        <IndicatorGrid explanations={data.indicatorsExplain} />
      )}

      {!data.hasLongTerm && active === "chart" && (
        <div className="rounded border border-warn/40 bg-warn/5 px-4 py-3 text-xs leading-relaxed text-warn">
          The long-horizon section needs at least a year of history. Set the chart range to
          5y, 10y or max to get drawdown depth, rolling multi-year returns and relative
          strength — a &quot;worst 3-year window&quot; computed from one year of data would be
          a statistic with nothing behind it.
        </div>
      )}

      <div className={active === "chart" ? "space-y-4" : "hidden"}>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Latest close" value={num(latest.close)} sub={latest.date} />
        <Stat label="Change on the day" value={`${latest.change >= 0 ? "+" : ""}${num(latest.change)}`}
              tone={latest.change >= 0 ? "text-acc" : "text-dist"}
              sub={`${latest.changePct >= 0 ? "+" : ""}${num(latest.changePct)}%`} />
        <Stat label="Day's high" value={num(latest.high)} />
        <Stat label="Day's low" value={num(latest.low)} />
      </div>

      <Card accent={TECH}>
        <CardBody className="pt-5">
          <p className="text-[0.95rem] leading-relaxed">
            {splitEmphasis(summary.headline).map((part, i) =>
              part.bold ? <b key={i} className="font-semibold text-chalk">{part.text}</b>
                        : <span key={i} className="text-ash">{part.text}</span>
            )}
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            {summary.chips.map((chip) => (
              <div key={chip.label}
                   className="flex-1 basis-36 rounded border-l-2 bg-raised px-3 py-2"
                   style={{ borderLeftColor: chip.tone === "bull" ? UP : chip.tone === "bear" ? DOWN
                                            : chip.tone === "warn" ? FAST : "#7A8CA0" }}>
                <div className="eyebrow mb-0.5">{chip.label}</div>
                <div className={cn("num text-sm font-semibold", TONE[chip.tone] ?? "text-chalk")}>
                  {chip.value}
                </div>
              </div>
            ))}
          </div>
        </CardBody>
      </Card>

      {!data.hasSma200 && (
        <div className="rounded border border-warn/40 bg-warn/10 px-4 py-3 text-xs text-warn">
          The 200-day average needs 200 trading days and this range is shorter, so the slow line
          and its crossover signals are missing. Pick a longer range.
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Floors and ceilings</CardTitle>
          <DownloadButton onClick={downloadSeries}>Indicators CSV</DownloadButton>
        </CardHeader>
        <CardBody>
          <div className={guided ? "hidden" : "flex flex-wrap items-end gap-3"}>
            <Field label="Turning points apart (days)"
                   hint="Larger keeps only the major turns.">
              <NumberField value={srWindow} onChange={(v) => setSrWindow(v ?? 10)}
                           min={3} max={40} />
            </Field>
            <Field label="Lines to draw">
              <NumberField value={srLevels} onChange={(v) => setSrLevels(v ?? 6)}
                           min={2} max={12} />
            </Field>
            <ApplyButton onClick={() => onApply({ srWindow, srLevels })} busy={busy} />
            <span className="pb-2 text-[0.7rem] text-ash">
              {levels.length} level{levels.length === 1 ? "" : "s"} drawn
            </span>
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Price · {data.range} · {data.bars} bars</CardTitle>
          <span className="font-mono text-[0.65rem] text-ash">{data.currency}</span>
        </CardHeader>
        <CardBody>
          <ResponsiveContainer width="100%" height={320}>
            <ComposedChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="2 4" vertical={false} />
              <XAxis dataKey="date" tickLine={false} axisLine={false} minTickGap={48} />
              <YAxis domain={["auto", "auto"]} tickLine={false} axisLine={false} width={56} />
              <Tooltip content={<TechTooltip />} />
              <Area dataKey="bbBase" stackId="bb" stroke="none" fill="transparent" isAnimationActive={false} />
              <Area dataKey="bbSpan" stackId="bb" stroke="none" fill={BAND} fillOpacity={0.10}
                    isAnimationActive={false} />
              {levels.map((level) => (
                <ReferenceLine key={level} y={level} strokeDasharray="4 4"
                               stroke={level > latest.close ? "#EF9A9A" : "#80CBC4"} strokeOpacity={0.45}
                               label={{ value: num(level), position: "insideLeft", fill: "#7A8CA0", fontSize: 10 }} />
              ))}
              <Line dataKey="close" stroke={TECH} strokeWidth={1.5} dot={false} isAnimationActive={false} />
              <Line dataKey="sma50" stroke={FAST} strokeWidth={1.2} dot={false} connectNulls
                    isAnimationActive={false} />
              <Line dataKey="sma200" stroke={SLOW} strokeWidth={1.2} dot={false} connectNulls
                    isAnimationActive={false} />
              <Scatter dataKey="buy" fill={UP} shape="triangle" isAnimationActive={false} />
              <Scatter dataKey="sell" fill={DOWN} shape="triangle" isAnimationActive={false} />
            </ComposedChart>
          </ResponsiveContainer>

          <div className="eyebrow mt-5 mb-1">RSI (14) · above 70 stretched, below 30 washed out</div>
          <ResponsiveContainer width="100%" height={110}>
            <ComposedChart data={chartData} margin={{ top: 2, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="2 4" vertical={false} />
              <XAxis dataKey="date" hide />
              <YAxis domain={[0, 100]} ticks={[30, 50, 70]} tickLine={false} axisLine={false} width={56} />
              <ReferenceLine y={70} stroke={DOWN} strokeOpacity={0.35} strokeDasharray="3 3" />
              <ReferenceLine y={30} stroke={UP} strokeOpacity={0.35} strokeDasharray="3 3" />
              <Line dataKey="rsi" stroke="#4DD0E1" strokeWidth={1.3} dot={false} connectNulls
                    isAnimationActive={false} />
            </ComposedChart>
          </ResponsiveContainer>

          <div className="eyebrow mt-5 mb-1">MACD (12, 26, 9)</div>
          <ResponsiveContainer width="100%" height={110}>
            <ComposedChart data={chartData} margin={{ top: 2, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="2 4" vertical={false} />
              <XAxis dataKey="date" hide />
              <YAxis tickLine={false} axisLine={false} width={56} />
              <ReferenceLine y={0} stroke="#7A8CA0" strokeOpacity={0.4} />
              <Bar dataKey="macdHist" isAnimationActive={false}
                   shape={(props: unknown) => {
                     // Recharts passes the rect geometry plus the source row;
                     // it has no exported type for a custom Bar shape.
                     const { x, y, width, height, payload } = props as {
                       x: number; y: number; width: number; height: number;
                       payload: ChartPoint;
                     };
                     const positive = (payload.macdHist ?? 0) >= 0;
                     return <rect x={x} y={y} width={width} height={height}
                                  fill={positive ? UP : DOWN} opacity={0.5} />;
                   }} />
              <Line dataKey="macd" stroke={TECH} strokeWidth={1.3} dot={false} connectNulls
                    isAnimationActive={false} />
              <Line dataKey="macdSignal" stroke="#FFB74D" strokeWidth={1.1} dot={false} connectNulls
                    isAnimationActive={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Every crossover in this range</CardTitle>
          {signals.length > 0 && <DownloadButton onClick={downloadSignals}>CSV</DownloadButton>}
        </CardHeader>
        <CardBody className="px-0">
          {signals.length === 0 ? (
            <p className="px-5 text-sm text-ash">
              The 50-day and 200-day averages never crossed inside this range. Try a longer one.
            </p>
          ) : (
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="eyebrow border-b border-rule [&>th]:px-5 [&>th]:py-2 [&>th]:font-normal">
                  <th>Date</th><th>What happened</th>
                  <th className="text-right">Price that day</th>
                  <th className="text-right">Change since</th>
                </tr>
              </thead>
              <tbody>
                {signals.map((s) => (
                  <tr key={s.date} className="border-b border-rule/60 last:border-0">
                    <td className="num px-5 py-2 text-ash">{s.date}</td>
                    <td className="px-5 py-2" style={{ color: s.type === "Buy" ? UP : DOWN }}>
                      {s.description}
                    </td>
                    <td className="num px-5 py-2 text-right">{num(s.price)}</td>
                    <td className={cn("num px-5 py-2 text-right",
                                      s.changeSince >= 0 ? "text-acc" : "text-dist")}>
                      {s.changeSince >= 0 ? "+" : ""}{num(s.changeSince, 1)}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardBody>
      </Card>

      <p className="text-xs leading-relaxed text-ash">
        Change since compares the latest close with the price on the signal day. It ignores costs,
        dividends and timing, so treat it as a rough scorecard. Indicators are computed on the
        visible window only — a one-year range gives the 200-day average roughly fifty valid bars.
      </p>
      </div>
    </div>
  );
}
