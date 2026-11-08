"use client";

import {
  Area, Bar, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer,
  Scatter, Tooltip, XAxis, YAxis,
} from "recharts";
import type { TooltipProps } from "recharts";
import { useState } from "react";
import { useSessionState } from "@/lib/session";
import { Card, CardBody, CardHeader, CardTitle, Explainer, Note, Stat } from "@/components/ui/card";
import { IndicatorGrid } from "@/components/IndicatorGrid";
import { HorizonPanel } from "@/components/HorizonPanel";
import { LongTermPanel } from "@/components/LongTermPanel";
import { Tabs } from "@/components/ui/tabs";
import { Explain, useDetail } from "@/components/ui/explain";
import { ApplyButton, DownloadButton, Field, NumberField } from "@/components/ui/controls";
import type { TechnicalOptions } from "@/lib/api";
import type { TechPoint, TechnicalResponse } from "@/lib/types";
import { downloadCsv, toCsv } from "@/lib/csv";
import { TONE, cn, num, pct, splitEmphasis } from "@/lib/utils";
import { palette } from "@/lib/palette";
import { ScrollRegion } from "@/components/ui/scroll";
import { useT } from "@/lib/i18n";

const TECH = palette.tech;
const FAST = palette.seriesFast;
const SLOW = palette.seriesSlow;
const BAND = palette.seriesViolet;
const UP = palette.acc;
const EXPOSURE_HUE = palette.drivers;
const DOWN = palette.dist;

/** A series row plus the derived columns the band and marker layers read. */
type ChartPoint = TechPoint & {
  bbBase: number | null;
  bbSpan: number | null;
  buy: number | null;
  sell: number | null;
};

function TechTooltip({ active, payload }: TooltipProps<number, string>) {
  const t = useT();
  // Recharts types `payload[n].payload` as the untyped source row; this is the
  // one place the cast belongs, and ChartPoint is exactly what we put in.
  const p = payload?.[0]?.payload as ChartPoint | undefined;
  if (!active || !p) return null;
  return (
    <div className="rounded border border-rule bg-ink/95 px-3 py-2 text-meta">
      <div className="num mb-1 text-ash">{p.date}</div>
      <div className="num">O {num(p.open)} · H {num(p.high)} · L {num(p.low)} · C {num(p.close)}</div>
      {p.sma50 != null && <div className="num" style={{ color: FAST }}>{t("50-day {sma50}", { sma50: num(p.sma50) })}</div>}
      {p.sma200 != null && <div className="num" style={{ color: SLOW }}>{t("200-day {sma200}", { sma200: num(p.sma200) })}</div>}
      {p.rsi != null && <div className="num text-ash">{t("RSI {rsi}", { rsi: num(p.rsi, 1) })}</div>}
    </div>
  );
}

export function TechnicalPanel({
  data, onApply, busy, stateKey,
}: {
  data: TechnicalResponse;
  onApply: (o: TechnicalOptions) => void;
  busy: boolean;
  /** Which company this is, so the chosen sub-section survives a tab switch. */
  stateKey?: string;
}) {
  const t = useT();
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
  // Kept for the session per company: the old panel forgot the reader was on
  // "Short term" every time they glanced at another tab and came back.
  const [section, setSection] = useSessionState<string>(
    `tech:section:${stateKey ?? data.ticker}`, data.hasLongTerm ? "long" : "chart");
  const guided = useDetail() === "simple";

  const downloadSeries = () =>
    downloadCsv(
      `${data.ticker}_${data.range}_indicators.csv`,
      toCsv(series, [
        { key: "date", label: t("Date") }, { key: "open", label: t("Open") },
        { key: "high", label: t("High") }, { key: "low", label: t("Low") },
        { key: "close", label: t("Close") }, { key: "volume", label: t("Volume") },
        { key: "sma50", label: "SMA_50" }, { key: "sma200", label: "SMA_200" },
        { key: "bbLower", label: "BB_LOWER" }, { key: "bbMid", label: "BB_MID" },
        { key: "bbUpper", label: "BB_UPPER" }, { key: "rsi", label: "RSI" },
        { key: "macd", label: "MACD" }, { key: "macdSignal", label: "MACD_SIGNAL" },
        { key: "macdHist", label: "MACD_HIST" }, { key: "signal", label: t("Signal") },
      ])
    );

  const downloadSignals = () =>
    downloadCsv(
      `${data.ticker}_crossovers.csv`,
      toCsv(signals, [
        { key: "date", label: t("Date") }, { key: "type", label: t("Signal") },
        { key: "description", label: t("What happened") },
        { key: "price", label: t("Price that day") },
        { key: "changeSince", label: t("Change since (%)") },
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
    ...(data.hasLongTerm ? [{ id: "long", label: t("Long term · years"), accent: palette.trend }] : []),
    { id: "mid", label: t("Mid term · weeks–months"), accent: palette.trend },
    { id: "short", label: t("Short term · days–weeks"), accent: palette.trend },
    { id: "chart", label: t("Chart & signals"), accent: palette.trend },
    ...(guided ? [] : [{ id: "indicators", label: t("All indicators"), accent: palette.trend }]),
  ];

  // A section that is open when the mode changes underneath it would otherwise
  // leave the panel blank — the tab is gone but `section` still names it. Derived
  // rather than corrected in an effect, so there is no frame where the panel has
  // rendered empty and no second render to fix it.
  const active = SECTIONS.some((s) => s.id === section) ? section : SECTIONS[0].id;

  return (
    <div className="space-y-4 animate-rise">
      <Tabs tabs={SECTIONS} active={active} onChange={setSection}
            idPrefix="horizon" label={t("Time horizon")} hasPanels={false} />
      {guided && (
        <p className="text-micro text-ash">
          {t("Switch to")}{" "}<span className="text-body">{t("Full")}</span>{" "}{t("for the complete indicator grid — ADX, Aroon, Stochastic, Williams %R, CCI, Coppock and the rest, grouped by the horizon each one speaks to.")}
        </p>
      )}

      {/*
        OUTSIDE THE HORIZON SWITCH, and the first attempt was inside it. This
        card went in beside "Floors and ceilings", which lives in the `chart`
        section — hidden whenever the default long-horizon view is showing, so
        the reading rendered into a `display:none` container and measured 0px
        tall. Caught by reading the element's own box, not by looking at the page.

        It belongs here on the merits anyway: the beta is estimated over its own
        fixed 52 weeks and does not change when the reader switches horizon or
        chart range, so tying its visibility to one of those would imply a
        relationship that is not there.
      */}
      {data.exposure?.usable && (
        <Card>
          <CardHeader>
            <CardTitle>{t("What this moves with")}</CardTitle>
            <span className="font-mono text-micro text-ash">
              {t("{weeks} weeks", { weeks: data.exposure.weeks })}
            </span>
          </CardHeader>
          {/*
            NEVER TONE-COLOURED. A stock that tracks copper is not thereby better
            or worse than one that does not, and a NEGATIVE beta is not a bad
            beta — a name that rises when the dollar falls is not failing at
            anything. Python returns `context` for every figure here and this
            file never picks a colour from a number's sign or size.
          */}
          <CardBody className="space-y-3">
            {/*
              A BAR FROM ZERO, NOT A ROW OF SENTENCES. Three numbers read as
              three unrelated facts in prose; drawn from a common zero line they
              read as one shape — which side of zero each sits on, and which is
              the big one. The width scale is shared across the three rows, so
              the comparison the eye makes is the true one.

              The bar is a length, never a colour: filling a negative bar red
              would say a stock that rises when the dollar falls is failing at
              something, which is the judgement `DESIGN.md` reserves for Python
              and which Python has deliberately not made here.
            */}
            {(() => {
              const rows = data.exposure?.factors ?? [];
              const widest = Math.max(0.25, ...rows.map((r) => Math.abs(r.beta)));
              return rows.map((row) => {
                const share = Math.abs(row.beta) / widest;
                const negative = row.beta < 0;
                return (
                  <div key={row.key}>
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="text-meta text-body">{row.label}</span>
                      <span className="flex items-center gap-1.5">
                        <span className="num text-meta font-semibold text-chalk">
                          {num(row.beta, 2)}x
                        </span>
                        <Explain
                          explain={data.exposure?.explain?.[`factorExposure.${row.key}`]} />
                      </span>
                    </div>
                    <div className="mt-1 flex h-2 w-full items-stretch">
                      <div className="flex flex-1 justify-end">
                        {negative && (
                          <div style={{ width: `${share * 100}%`, background: EXPOSURE_HUE }}
                               className="rounded-l-sm" />
                        )}
                      </div>
                      <div className="w-px bg-faint" aria-hidden />
                      <div className="flex flex-1 justify-start">
                        {!negative && (
                          <div style={{ width: `${share * 100}%`, background: EXPOSURE_HUE }}
                               className="rounded-r-sm" />
                        )}
                      </div>
                    </div>
                    <p className="mt-1 text-meta leading-relaxed text-ash">
                      {t("explains {rSquared} of what is left of its weekly moves once the market is out · over {weeks} weeks", { rSquared: pct(row.rSquared, 0), weeks: row.weeks })}
                    </p>
                  </div>
                );
              });
            })()}
            {(data.exposure.factors ?? []).length === 0 && (
              <p className="prose-col text-meta leading-relaxed">
                {t("None of the tested factors accounted for enough of this stock's movement to report. That is not evidence it is unexposed — only that these ones did not explain it.")}
              </p>
            )}
            {(data.exposure.refused ?? []).length > 0 && (
              // THE SUMMARY HAS TO COUNT WHAT IS ACTUALLY BELOW IT. A fixed
              // "One factor was tested and is deliberately not shown" read
              // correctly on a name where only gold was refused and wrongly on
              // AAPL, where all four were — and a summary is the only part of a
              // closed disclosure anyone sees, so it cannot be approximately true.
              <Explainer summary={(data.exposure.refused ?? []).length === 1
                ? t("{count} tested factor did not explain this name", { count: 1 })
                : t("{count} tested factors did not explain this name",
                    { count: (data.exposure.refused ?? []).length })}>
                <p>
                  {t("Every factor is tested on every name. One is listed here when it did not account for enough of this stock's movement, once the local market is taken out of both sides, to be worth a number — which is not evidence the stock is unexposed to it.")}
                </p>
                <ul className="mt-2 space-y-1">
                  {(data.exposure?.refused ?? []).map((r) => (
                    <li key={r.key} className="text-meta text-ash">
                      <span className="text-body">{r.label}</span> — {r.reason}
                    </li>
                  ))}
                </ul>
                <p className="mt-2 text-meta leading-relaxed text-ash">
                  {t("Estimated over five years of weekly moves. Whether a loading like this persists into the next five could not be measured from the history available, so nothing here is offered as a forecast.")}
                </p>
              </Explainer>
            )}
          </CardBody>
        </Card>
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
        <div className="rounded-lg border border-warn/40 bg-warn/5 px-4 py-3.5">
          <p className="prose-col text-meta leading-relaxed text-warn">
            {t("The long-horizon section needs at least a year of history. Set the chart range to 5y or longer for drawdown depth, multi-year returns and relative strength — a “worst 3-year window” built from one year of data would be a number with nothing behind it.")}
          </p>
        </div>
      )}

      <div className={active === "chart" ? "space-y-4" : "hidden"}>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label={t("Latest close")} value={num(latest.close)} sub={latest.date} />
        <Stat label={t("Change on the day")} value={`${latest.change >= 0 ? "+" : ""}${num(latest.change)}`}
              tone={latest.change >= 0 ? "text-acc" : "text-dist"}
              sub={`${latest.changePct >= 0 ? "+" : ""}${num(latest.changePct)}%`} />
        <Stat label={t("Day's high")} value={num(latest.high)} />
        <Stat label={t("Day's low")} value={num(latest.low)} />
      </div>

      <Card accent={TECH}>
        <CardBody className="pt-5">
          <p className="text-base leading-relaxed">
            {splitEmphasis(summary.headline).map((part, i) =>
              part.bold ? <b key={i} className="font-semibold text-chalk">{part.text}</b>
                        : <span key={i} className="text-ash">{part.text}</span>
            )}
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            {summary.chips.map((chip) => (
              // A DOT, NOT A 2px LEFT BORDER. The coloured side-stripe is the most
              // recognisable tell of a generated interface, and it does the job worse:
              // on a rounded card the stripe fights the corner, and at 2px it reads as
              // trim rather than as a status. The tone still comes from the server.
              <div key={chip.label}
                   className="flex-1 basis-36 rounded-lg border border-ruleSoft bg-raised
                              px-3.5 py-2.5">
                <div className="mb-1 flex items-center gap-2">
                  <span aria-hidden className="h-1.5 w-1.5 shrink-0 rounded-full"
                        style={{ background: chip.tone === "bull" ? UP
                                             : chip.tone === "bear" ? DOWN
                                             : chip.tone === "warn" ? FAST : palette.faint }} />
                  <span className="eyebrow">{chip.label}</span>
                </div>
                <div className={cn("num text-base font-semibold", TONE[chip.tone] ?? "text-chalk")}>
                  {chip.value}
                </div>
              </div>
            ))}
          </div>
        </CardBody>
      </Card>

      {!data.hasSma200 && (
        <div className="rounded border border-warn/40 bg-warn/10 px-4 py-3 text-meta text-warn">
          {t("The 200-day average needs 200 trading days and this range is shorter, so the slow line and its crossover signals are missing. Pick a longer range.")}
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle>{t("Floors and ceilings")}</CardTitle>
          <DownloadButton onClick={downloadSeries}>{t("Indicators CSV")}</DownloadButton>
        </CardHeader>
        {/* GUIDED KEEPS THE COUNT, NOT AN EMPTY BOX. The tuning fields are Full's;
            hiding them used to leave Guided a header over a blank body, which
            reads as a panel that failed to load. */}
        <CardBody>
          {guided && (
            <p className="text-meta text-ash">
              {t("{length} level{value} drawn on the chart. Switch to Full to change how far apart the turning points must be.", { length: levels.length, value: levels.length === 1 ? "" : "s" })}
            </p>
          )}
          <div className={guided ? "hidden" : "flex flex-wrap items-end gap-3"}>
            <Field label={t("Turning points apart (days)")}
                   hint={t("Larger keeps only the major turns.")}>
              <NumberField value={srWindow} onChange={(v) => setSrWindow(v ?? 10)}
                           min={3} max={40} />
            </Field>
            <Field label={t("Lines to draw")}>
              <NumberField value={srLevels} onChange={(v) => setSrLevels(v ?? 6)}
                           min={2} max={12} />
            </Field>
            <ApplyButton onClick={() => onApply({ srWindow, srLevels })} busy={busy} />
            <span className="pb-2 text-micro text-ash">
              {t("{length} level{value} drawn", { length: levels.length, value: levels.length === 1 ? "" : "s" })}
            </span>
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("Price · {range} · {bars} bars", { range: data.range, bars: data.bars })}</CardTitle>
          <span className="font-mono text-micro text-ash">{data.currency}</span>
        </CardHeader>
        <CardBody>
          {/* Hidden from assistive tech: the crossover table and the levels list carry what the chart shows; Recharts stamps role=img on each buy/sell marker. */}
          <div aria-hidden>
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
                                 stroke={level > latest.close ? palette.levelAbove : palette.levelBelow} strokeOpacity={0.45}
                                 label={{ value: num(level), position: "insideLeft", fill: palette.axis, fontSize: 10 }} />
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
          </div>

          <div className="eyebrow mt-5 mb-1">{t("RSI (14) · above 70 stretched, below 30 washed out")}</div>
          <div aria-hidden>
            <ResponsiveContainer width="100%" height={110}>
              <ComposedChart data={chartData} margin={{ top: 2, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="2 4" vertical={false} />
                <XAxis dataKey="date" hide />
                <YAxis domain={[0, 100]} ticks={[30, 50, 70]} tickLine={false} axisLine={false} width={56} />
                <ReferenceLine y={70} stroke={DOWN} strokeOpacity={0.35} strokeDasharray="3 3" />
                <ReferenceLine y={30} stroke={UP} strokeOpacity={0.35} strokeDasharray="3 3" />
                <Line dataKey="rsi" stroke={palette.seriesCyan} strokeWidth={1.3} dot={false} connectNulls
                      isAnimationActive={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>

          <div className="eyebrow mt-5 mb-1">{t("MACD (12, 26, 9)")}</div>
          <div aria-hidden>
            <ResponsiveContainer width="100%" height={110}>
              <ComposedChart data={chartData} margin={{ top: 2, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="2 4" vertical={false} />
                <XAxis dataKey="date" hide />
                <YAxis tickLine={false} axisLine={false} width={56} />
                <ReferenceLine y={0} stroke={palette.axis} strokeOpacity={0.4} />
                <Bar dataKey="macdHist" isAnimationActive={false}
                     shape={(props: unknown) => {
                       // Recharts passes the rect geometry plus the source row;
                       // it has no exported type for a custom Bar shape.
                       const { x, y, width, height, payload } = props as {
                         x: number; y: number; width: number; height: number;
                         payload: ChartPoint;
                       };
                       const positive = (payload.macdHist ?? 0) >= 0;
                       // A BAR BELOW ZERO ARRIVES WITH A NEGATIVE HEIGHT, which an
                       // SVG <rect> refuses: every negative histogram bar was
                       // dropped and logged as an error, so the chart showed only
                       // the positive half. Found in the November 2026 audit.
                       return <rect x={x} y={height < 0 ? y + height : y} width={width}
                                    height={Math.abs(height)}
                                    fill={positive ? UP : DOWN} opacity={0.5} />;
                     }} />
                <Line dataKey="macd" stroke={TECH} strokeWidth={1.3} dot={false} connectNulls
                      isAnimationActive={false} />
                <Line dataKey="macdSignal" stroke={palette.seriesOrange} strokeWidth={1.1} dot={false} connectNulls
                      isAnimationActive={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("Every crossover in this range")}</CardTitle>
          {signals.length > 0 && <DownloadButton onClick={downloadSignals}>{t("CSV")}</DownloadButton>}
        </CardHeader>
        <CardBody className="px-0">
          {signals.length === 0 ? (
            <p className="px-5 text-base text-ash">
              {t("The 50-day and 200-day averages never crossed inside this range. Try a longer one.")}
            </p>
          ) : (
            <ScrollRegion label={t("Every crossover in this range")}>
              <table className="w-full text-left text-meta">
                <thead>
                  <tr className="eyebrow border-b border-rule [&>th]:px-5 [&>th]:py-2 [&>th]:font-normal">
                    <th>{t("Date")}</th><th>{t("What happened")}</th>
                    <th className="text-right">{t("Price that day")}</th>
                    <th className="text-right">{t("Change since")}</th>
                  </tr>
                </thead>
                <tbody>
                  {signals.map((s) => (
                    <tr key={s.date} className="border-b border-ruleSoft last:border-0">
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
            </ScrollRegion>
          )}
        </CardBody>
      </Card>

      <Note>
        {t("“Change since” compares today's close with the price on the signal day, ignoring costs, dividends and timing — a rough scorecard, not a return. Everything here is computed on the visible window only, so a one-year range leaves the 200-day average about fifty usable days.")}
      </Note>
      </div>
    </div>
  );
}
