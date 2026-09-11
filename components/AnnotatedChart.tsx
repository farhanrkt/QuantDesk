"use client";

import { useMemo, useState } from "react";
import {
  Bar, CartesianGrid, ComposedChart, Line, ReferenceArea, ReferenceDot,
  ReferenceLine, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis,
} from "recharts";
import type { TooltipProps } from "recharts";
import { Card, CardBody, CardHeader, CardTitle, Explainer, Note } from "@/components/ui/card";
import type { ChartBar, ChartPattern, VerdictChart } from "@/lib/types";
import { cn, num } from "@/lib/utils";

/**
 * The scanner's readings, on the chart, where they can be disagreed with.
 *
 * WHY THIS COMPONENT EXISTS AT ALL
 *
 * Everything it draws was already in the payload as prose. The panel below it
 * says an inverse head-and-shoulders completed on a date, that fifty heavy
 * sessions closed high in their range, that the reward-risk ratio is 0.8 to
 * one. Each of those is a claim about a shape, and a shape is the one kind of
 * claim a reader can check in a second and cannot evaluate at all from a
 * sentence. A panel that reports the statistic and withholds the picture is
 * asking to be believed rather than read.
 *
 * FOUR THINGS THIS CHART WILL NOT DO.
 *
 * 1. IT NEVER DRAWS A TARGET. Every chart-pattern convention ends in a measured
 *    move — project the head's height from the neckline, draw the arrow. It is
 *    the most satisfying mark on the chart and the app's own study found the
 *    textbook direction carries no information, so the arrow would assert
 *    something the measurement declined. What is drawn instead is the measured
 *    excess return, labelled as measured, with the textbook bias beside it
 *    labelled as textbook.
 *
 * 2. IT NEVER SMOOTHS WITH HINDSIGHT. `chartlayers` refits each formation's
 *    curve on the window that existed when the shape completed. A whole-series
 *    fit would be smoother, better-formed, and partly drawn out of prices that
 *    had not happened yet.
 *
 * 3. IT NEVER COLOURS FROM A JUDGEMENT IT MADE ITSELF. The one sign-based hue
 *    here is the candle body — a day's own up or down, which `PRODUCT.md`
 *    constraint 4 already lists as a documented exception because Python has no
 *    interpretation to offer about one session. Everything else is identity:
 *    a heavy session is one colour whether it closed high or low, and where it
 *    closed is shown by POSITION in the pane below, which is a measurement
 *    rather than a verdict.
 *
 * 4. IT NEVER DRAWS A LAYER WITHOUT ITS CAVEAT. `legend` arrives in the payload
 *    rather than living here, so the note that a support level works only while
 *    enough people watch it cannot be dropped by editing a component.
 */

// Identity hues. None of these means good or bad.
const PRICE_UP = "#35C4A8";
const PRICE_DOWN = "#FF6B6B";
const MA_FAST = "#F2C14E";
const MA_MID = "#6B9BFF";
const MA_SLOW = "#7387A0";
const BAND = "#A78BFA";
const HEAVY = "#E8B44C";
const ORDINARY = "#2A3846";
const PATTERN = "#A78BFA";
const GUIDE = "#E7EEF5";
const SUPPORT = "#80CBC4";
// Identity, like every other hue here. A volume shelf is this colour whether the
// price is above it or below it.
const PROFILE = "#4DD0E1";
const RESISTANCE = "#EF9A9A";

type Row = ChartBar & {
  candle: [number, number] | null;
  volumeHeavy: number | null;
  volumeOrdinary: number | null;
  patternPath: number | null;
  patternPoint: number | null;
  heavyLocation: number | null;
};

function CandleShape(props: unknown) {
  // Recharts hands a custom Bar shape the rect geometry plus the source row and
  // exports no type for it.
  const { x, y, width, height, payload } = props as {
    x: number; y: number; width: number; height: number; payload: Row;
  };
  // The rect spans low to high because the bar's dataKey is the [low, high]
  // range, which is what makes the price-to-pixel scale below recoverable
  // without reaching for the axis.

  const { open, high, low, close } = payload;
  // A custom Bar shape may not return null — recharts types it as always
  // yielding an element — so a bar with a gap in it draws nothing rather than
  // being skipped.
  if (open == null || high == null || low == null || close == null) return <g />;
  if (!(high > low)) {
    return <rect x={x} y={y} width={Math.max(1, width)} height={1} fill={MA_SLOW} />;
  }

  const scale = height / (high - low);
  const top = Math.min(open, close);
  const bottom = Math.max(open, close);
  const bodyY = y + (high - bottom) * scale;
  const bodyHeight = Math.max(1, (bottom - top) * scale);
  // The one sign-based colour in this file, and it is a documented exception:
  // a session that closed below its open is down, which is arithmetic rather
  // than an interpretation Python withheld.
  const hue = close >= open ? PRICE_UP : PRICE_DOWN;
  const centre = x + width / 2;

  return (
    <g>
      <line x1={centre} x2={centre} y1={y} y2={y + height} stroke={hue}
            strokeWidth={1} opacity={0.75} />
      <rect x={x} y={bodyY} width={Math.max(1, width)} height={bodyHeight}
            fill={hue} opacity={close >= open ? 0.85 : 0.95} />
    </g>
  );
}

function PriceTooltip({ active, payload }: TooltipProps<number, string>) {
  const row = payload?.[0]?.payload as Row | undefined;
  if (!active || !row) return null;
  return (
    <div className="rounded border border-rule bg-ink/95 px-3 py-2 text-meta">
      <div className="num mb-1 text-ash">{row.date}</div>
      <div className="num">
        O {num(row.open)} · H {num(row.high)} · L {num(row.low)} · C {num(row.close)}
      </div>
      {row.relativeVolume != null && (
        <div className="num text-ash">
          Volume {num(row.relativeVolume, 2)}x its own median
          {row.heavy && <span style={{ color: HEAVY }}> · heavy</span>}
        </div>
      )}
      {row.heavy && row.closeLocation != null && (
        <div className="num text-ash">
          Closed {num(row.closeLocation, 2)} in its range
          {" "}({row.closeLocation > 0 ? "upper" : "lower"} half)
        </div>
      )}
    </div>
  );
}

export function AnnotatedChart({ chart }: { chart: VerdictChart }) {
  const [drawn, setDrawn] = useState<number>(0);
  const [showLevels, setShowLevels] = useState(true);
  const [showTrade, setShowTrade] = useState(true);
  const [showBands, setShowBands] = useState(true);
  const [showProfile, setShowProfile] = useState(true);

  const bars = useMemo(() => chart.bars ?? [], [chart.bars]);
  const shapes = useMemo(() => chart.patterns ?? [], [chart.patterns]);
  // Most recent first: a formation that completed last week is the one a reader
  // came for, and the six-month-old one is history.
  const ordered = useMemo(
    () => [...shapes].sort((a, b) => b.detectedAt.localeCompare(a.detectedAt)),
    [shapes]);
  const active: ChartPattern | null = ordered[drawn] ?? null;

  const rows: Row[] = useMemo(() => {
    const path = new Map<string, number>();
    const points = new Map<string, number>();
    if (active) {
      for (const node of active.path) if (node.date) path.set(node.date, node.price);
      for (const node of active.points) if (node.date) points.set(node.date, node.price);
    }
    return bars.map((bar) => ({
      ...bar,
      // A RANGE BAR, NOT TWO STACKED ONES. The obvious way to fake a candle in
      // recharts is an invisible base bar plus a visible span stacked on it,
      // and it silently destroys the axis: a stack has a zero baseline, so the
      // y-domain is extended down to 0 no matter what domain the axis is given.
      // The first render of this chart put a stock trading at 2,600 on an axis
      // running from 0 to 3,750, which squashed every candle, every moving
      // average and both trade bands into the top fifth of the pane — and it
      // looked like a styling problem rather than a wrong axis.
      candle: bar.high != null && bar.low != null ? [bar.low, bar.high] : null,
      // Split so the two get their own fills without a per-bar shape function.
      volumeHeavy: bar.heavy ? bar.volume : null,
      volumeOrdinary: bar.heavy ? null : bar.volume,
      patternPath: path.get(bar.date) ?? null,
      patternPoint: points.get(bar.date) ?? null,
      heavyLocation: bar.heavy ? bar.closeLocation : null,
    }));
  }, [bars, active]);

  // THE DOMAIN IS COMPUTED, NOT INFERRED. Recharts would fit the axis to the
  // series alone, and a stop sitting just under the window's low or a ceiling
  // just over its high would then be clipped off the drawing entirely — the two
  // lines a reader most needs to see are exactly the two most likely to fall
  // outside the price range.
  const domain = useMemo(() => {
    const values: number[] = [];
    for (const bar of bars) {
      if (bar.high != null) values.push(bar.high);
      if (bar.low != null) values.push(bar.low);
      if (showBands && bar.bbUpper != null) values.push(bar.bbUpper);
      if (showBands && bar.bbLower != null) values.push(bar.bbLower);
    }
    if (showLevels) for (const level of chart.levels ?? []) values.push(level.price);
    // The profile routinely sits well below a name that has run, so leaving it
    // out of the domain would clip exactly the band a reader most wants to see.
    if (showProfile && chart.volumeProfile) {
      for (const edge of [chart.volumeProfile.valueArea.low,
                          chart.volumeProfile.valueArea.high]) {
        if (edge != null) values.push(edge);
      }
    }
    if (showTrade && chart.trade) {
      for (const price of [chart.trade.stop, chart.trade.target, chart.trade.entry]) {
        if (price != null) values.push(price);
      }
    }
    if (!values.length) return ["auto", "auto"] as const;
    const low = Math.min(...values);
    const high = Math.max(...values);
    const pad = (high - low) * 0.04 || high * 0.02;
    return [low - pad, high + pad] as [number, number];
  }, [bars, chart.levels, chart.trade, chart.volumeProfile,
      showBands, showLevels, showTrade, showProfile]);

  if (!chart.available || rows.length === 0) {
    return (
      <Card>
        <CardHeader><CardTitle>The chart</CardTitle></CardHeader>
        <CardBody>
          <p className="prose-col text-base leading-relaxed text-ash">
            {chart.reason ?? "There was not enough history to draw anything."} Nothing is
            drawn rather than a shorter window being substituted — a level found in six
            weeks of bars is not the same object as one found in a year of them.
          </p>
        </CardBody>
      </Card>
    );
  }

  const trade = chart.trade ?? null;
  const profile = chart.volumeProfile ?? null;
  const tape = chart.tape;
  const heavyDrawn = rows.filter((row) => row.heavyLocation != null);

  return (
    <Card accent={MA_MID}>
      <CardHeader>
        <CardTitle>
          The tape, with everything the scanner measured on it
        </CardTitle>
        <span className="font-mono text-micro text-ash">
          {chart.sessions} sessions · {chart.from} → {chart.to}
          {chart.currency ? ` · ${chart.currency}` : ""}
        </span>
      </CardHeader>
      <CardBody className="space-y-3">
        <div className="flex flex-wrap items-center gap-1.5">
          <Toggle on={showLevels} onClick={() => setShowLevels(!showLevels)}
                  hue={SUPPORT}>Levels</Toggle>
          <Toggle on={showTrade} onClick={() => setShowTrade(!showTrade)}
                  hue={PRICE_UP}>Stop &amp; ceiling</Toggle>
          <Toggle on={showBands} onClick={() => setShowBands(!showBands)}
                  hue={BAND}>Bollinger</Toggle>
          {chart.volumeProfile && (
            <Toggle on={showProfile} onClick={() => setShowProfile(!showProfile)}
                    hue={PROFILE}>Volume at price</Toggle>
          )}
          {ordered.map((shape, i) => (
            <Toggle key={`${shape.pattern}-${shape.detectedAt}`} on={drawn === i}
                    hue={PATTERN}
                    onClick={() => setDrawn(drawn === i ? -1 : i)}>
              {shape.label}
              <span className="ml-1 text-faint">{shape.completedAt.slice(2)}</span>
            </Toggle>
          ))}
        </div>

        {/* ---------------------------------------------------------------- */}
        {/* Price                                                             */}
        {/* ---------------------------------------------------------------- */}
        <ResponsiveContainer width="100%" height={360}>
          <ComposedChart data={rows} margin={{ top: 6, right: 96, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="2 4" vertical={false} stroke="#1E2A36" />
            <XAxis dataKey="date" tickLine={false} axisLine={false} minTickGap={56}
                   tick={{ fontSize: 10, fill: "#7387A0" }} />
            <YAxis domain={domain as [number, number]} tickLine={false} axisLine={false}
                   width={60} tick={{ fontSize: 10, fill: "#7387A0" }}
                   tickFormatter={(value: number) => num(value)} />
            <Tooltip content={<PriceTooltip />} />

            {/* WHERE THE YEAR'S TRADE HAPPENED. Bands on the price axis only —
                every figure is a y-range, so it draws exactly and cannot drift
                out of alignment the way a second chart matched by hand would.
                Drawn before the candles so it sits behind them. */}
            {showProfile && profile?.valueArea.low != null
              && profile.valueArea.high != null && (
              <ReferenceArea y1={profile.valueArea.low} y2={profile.valueArea.high}
                             fill={PROFILE} fillOpacity={0.05}
                             ifOverflow="extendDomain" />
            )}
            {showProfile && profile?.pointOfControl.low != null
              && profile.pointOfControl.high != null && (
              <ReferenceArea y1={profile.pointOfControl.low}
                             y2={profile.pointOfControl.high}
                             fill={PROFILE} fillOpacity={0.30}
                             ifOverflow="extendDomain"
                             label={{ value: "most traded", position: "insideLeft",
                                      fontSize: 9, fill: PROFILE }} />
            )}
            {showProfile && (profile?.shelves ?? []).map((shelf, i) => (
              shelf.low != null && shelf.high != null ? (
                <ReferenceArea key={`shelf-${i}`} y1={shelf.low} y2={shelf.high}
                               fill={PROFILE} fillOpacity={0.12}
                               ifOverflow="extendDomain"
                               label={{
                                 value: `${((shelf.share ?? 0) * 100).toFixed(0)}% of the year`,
                                 position: "insideTopLeft", fontSize: 9, fill: PROFILE,
                               }} />
              ) : null
            ))}

            {/* The pattern's own window, so the five points are read in context. */}
            {active?.fromDate && active?.toDate && (
              <ReferenceArea x1={active.fromDate} x2={active.toDate} fill={PATTERN}
                             fillOpacity={0.07} stroke={PATTERN} strokeOpacity={0.2} />
            )}

            {/* WHERE THE TRADE IS WRONG, AND WHAT IS OVERHEAD. Two bands from the
                entry: down to the nearest defended floor, up to the first
                ceiling. The hues are definitional rather than a judgement —
                below the entry is where the position loses — and the ratio's
                own verdict comes from `structure.band`, in words, below. */}
            {showTrade && trade?.stop != null && (
              <ReferenceArea y1={trade.stop} y2={trade.entry} fill={PRICE_DOWN}
                             fillOpacity={0.07} ifOverflow="extendDomain" />
            )}
            {showTrade && trade?.target != null && (
              <ReferenceArea y1={trade.entry} y2={trade.target} fill={PRICE_UP}
                             fillOpacity={0.07} ifOverflow="extendDomain" />
            )}

            {/* TWO SEPARATE EXPRESSIONS, NOT ONE FRAGMENT AROUND THE PAIR.
                Recharts reads its children to work out what to render and does
                NOT look inside a React fragment, so `{flag && (<><Line/><Line/></>)}`
                type-checks, lints, renders no error, and silently draws
                nothing. Both Bollinger lines vanished this way and the toggle
                above them still looked like it was working. */}
            {showBands && (
              <Line dataKey="bbUpper" stroke={BAND} strokeWidth={1} dot={false}
                    strokeOpacity={0.45} connectNulls isAnimationActive={false} />
            )}
            {showBands && (
              <Line dataKey="bbLower" stroke={BAND} strokeWidth={1} dot={false}
                    strokeOpacity={0.45} connectNulls isAnimationActive={false} />
            )}

            {/* EVERY LEVEL CARRIES ITS TOUCH COUNT. A level defended four times
                and one defended twice are drawn identically everywhere else in
                this app, which invites a reader to treat them as equivalent. */}
            {showLevels && (chart.levels ?? []).map((level) => (
              <ReferenceLine key={`${level.side}-${level.price}`} y={level.price}
                             stroke={level.side === "support" ? SUPPORT : RESISTANCE}
                             strokeOpacity={level.nearest ? 0.85 : 0.3}
                             strokeDasharray={level.nearest ? undefined : "4 4"}
                             strokeWidth={level.nearest ? 1.4 : 1}
                             ifOverflow="extendDomain"
                             label={{
                               value: `${num(level.price)} · ${level.touches}x`,
                               position: "right", fontSize: 9,
                               fill: level.nearest ? "#C3CFDC" : "#7387A0",
                             }} />
            ))}

            <Bar dataKey="candle" shape={CandleShape} isAnimationActive={false} />

            <Line dataKey="sma20" stroke={MA_FAST} strokeWidth={1} dot={false}
                  connectNulls isAnimationActive={false} />
            <Line dataKey="sma50" stroke={MA_MID} strokeWidth={1.2} dot={false}
                  connectNulls isAnimationActive={false} />
            <Line dataKey="sma200" stroke={MA_SLOW} strokeWidth={1.2} dot={false}
                  connectNulls isAnimationActive={false} />

            {/* The curve the detector saw — refitted on its own window, ending on
                the detection bar. It stops there on purpose: extending it to
                today would be the two-sided smoother reading forward. */}
            {active && (
              <Line dataKey="patternPath" stroke={PATTERN} strokeWidth={2} dot={false}
                    connectNulls={false} isAnimationActive={false} />
            )}
            {active && (
              <Scatter dataKey="patternPoint" fill={PATTERN} shape="circle"
                       isAnimationActive={false} />
            )}

            {/* Necklines and boundaries. No projection: see the caption. */}
            {active?.guides.map((guide, i) => (
              guide.from.date && guide.to.date ? (
                <ReferenceLine key={`${guide.role}-${i}`} stroke={GUIDE}
                               strokeOpacity={0.5} strokeDasharray="5 4"
                               segment={[
                                 { x: guide.from.date, y: guide.from.price },
                                 { x: guide.to.date, y: guide.to.price },
                               ]} />
              ) : null
            ))}

            {(chart.crossovers ?? []).map((cross) => (
              cross.price != null ? (
                <ReferenceDot key={`${cross.date}-${cross.type}`} x={cross.date}
                              y={cross.price} r={3.5}
                              fill={cross.type === "Buy" ? PRICE_UP : PRICE_DOWN}
                              stroke="#080C10" strokeWidth={1} />
              ) : null
            ))}
          </ComposedChart>
        </ResponsiveContainer>

        {/* ---------------------------------------------------------------- */}
        {/* Volume, with the heavy sessions the tape test counted              */}
        {/* ---------------------------------------------------------------- */}
        <div>
          <div className="eyebrow mb-1">
            Volume · {tape?.drawn ?? 0} heavy sessions in this window
            {tape?.rvolCutoff != null && (
              <span className="ml-1 text-faint">
                (above {num(tape.rvolCutoff, 2)}x its own rolling median)
              </span>
            )}
          </div>
          <ResponsiveContainer width="100%" height={78}>
            <ComposedChart data={rows} margin={{ top: 2, right: 96, left: 0, bottom: 0 }}>
              <XAxis dataKey="date" hide />
              <YAxis tickLine={false} axisLine={false} width={60} tick={false} />
              <Bar dataKey="volumeOrdinary" stackId="v" fill={ORDINARY}
                   isAnimationActive={false} />
              <Bar dataKey="volumeHeavy" stackId="v" fill={HEAVY} fillOpacity={0.9}
                   isAnimationActive={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>

        {/* ---------------------------------------------------------------- */}
        {/* The Welch test, drawn                                             */}
        {/* ---------------------------------------------------------------- */}
        {tape?.available && heavyDrawn.length > 0 && (
          <div>
            <div className="eyebrow mb-1">
              Where each heavy session closed in its own range
              {tape.heavyMeanLocation != null && tape.ordinaryMeanLocation != null && (
                <>
                  {" · "}
                  <span style={{ color: HEAVY }}>
                    heavy mean {num(tape.heavyMeanLocation, 2)}
                  </span>
                  {" against "}
                  <span className="text-ash">
                    {num(tape.ordinaryMeanLocation, 2)} on its ordinary sessions
                  </span>
                  <span className="text-faint">
                    {tape.significant ? " · the gap cleared its test"
                                      : " · the gap did not clear its test"}
                  </span>
                </>
              )}
            </div>
            <ResponsiveContainer width="100%" height={96}>
              <ComposedChart data={rows}
                             margin={{ top: 4, right: 96, left: 0, bottom: 6 }}>
                <CartesianGrid strokeDasharray="2 4" vertical={false} stroke="#1E2A36" />
                <XAxis dataKey="date" hide />
                {/* Padded past the extremes so a session that closed exactly at
                    its high or low is a dot rather than a half-dot on the
                    frame. */}
                <YAxis domain={[-1.12, 1.12]} ticks={[-1, 0, 1]} tickLine={false}
                       axisLine={false} width={60}
                       tick={{ fontSize: 9, fill: "#7387A0" }}
                       tickFormatter={(v: number) =>
                         v === 1 ? "at high" : v === -1 ? "at low" : "middle"} />
                {/* THE COMPARISON THE TEST ACTUALLY MADE. Not zero — the middle
                    of the range is the wrong null, and mistaking it for the
                    right one is an error this app has made three times in three
                    different modules. The grey line is this name's own ordinary
                    sessions, which is what the heavy ones were tested against.

                    NEITHER LINE IS LABELLED ON THE CHART. The whole question is
                    whether these two numbers differ, so they sit within a few
                    hundredths of each other on almost every name and two labels
                    at the same height render as one unreadable smear. They are
                    named in the heading above instead, where there is room. */}
                {tape.ordinaryMeanLocation != null && (
                  <ReferenceLine y={tape.ordinaryMeanLocation} stroke={MA_SLOW}
                                 strokeDasharray="4 4" />
                )}
                {tape.heavyMeanLocation != null && (
                  <ReferenceLine y={tape.heavyMeanLocation} stroke={HEAVY}
                                 strokeOpacity={0.9} />
                )}
                <Scatter dataKey="heavyLocation" fill={HEAVY} shape="circle"
                         isAnimationActive={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        )}

        {active && <PatternCaption shape={active} />}

        <p className="prose-col text-meta leading-relaxed text-ash">
          {chart.caption}
        </p>

        <Explainer summary="What each layer is, and what it is not">
          <ul className="space-y-2">
            {(chart.legend ?? []).map((row) => (
              <li key={row.key} className="text-meta leading-relaxed text-ash">
                <span className="text-body">{row.label}.</span> {row.note}
              </li>
            ))}
          </ul>
        </Explainer>

        {trade && (
          <Note>
            The shaded bands are measured from the last close to the nearest defended
            floor and the first ceiling above it — the same two prices the reward-risk
            ratio used. A level is not a barrier: it works only for as long as enough
            participants are watching the same one.
          </Note>
        )}
      </CardBody>
    </Card>
  );
}

function Toggle({ on, hue, onClick, children }: {
  on: boolean; hue: string; onClick: () => void; children: React.ReactNode;
}) {
  return (
    <button type="button" onClick={onClick} aria-pressed={on}
            className={cn(
              "flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-micro",
              "transition-colors",
              on ? "border-rule bg-raised text-body" : "border-ruleSoft text-faint")}>
      <span aria-hidden className="h-1.5 w-1.5 shrink-0 rounded-full"
            style={{ background: on ? hue : "#2A3846" }} />
      {children}
    </button>
  );
}

/**
 * The two directions, side by side, never merged.
 *
 * This is the whole reason the drawing is safe to ship. A head-and-shoulders on
 * a chart is one of the most loaded images in this business, and rendering one
 * without the measurement beside it would let the picture make a claim the app
 * has explicitly refused to make.
 */
function PatternCaption({ shape }: { shape: ChartPattern }) {
  return (
    <div className="rounded-lg border border-ruleSoft bg-raised px-3.5 py-3">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <span className="text-base font-medium text-chalk">{shape.label}</span>
        <span className="num text-micro text-faint">
          completed {shape.completedAt} · known {shape.detectedAt}
        </span>
      </div>
      <div className="mt-2 grid gap-2 sm:grid-cols-2">
        <div className="rounded border border-ruleSoft px-2.5 py-2">
          <div className="eyebrow mb-0.5">What the chart books say</div>
          <div className="text-meta text-ash">
            {shape.textbookBias === "up" ? "Bullish reversal"
              : shape.textbookBias === "down" ? "Bearish reversal"
              : "Continuation, either way"}
            <span className="text-faint"> — carried for display, never scored.</span>
          </div>
        </div>
        <div className="rounded border border-ruleSoft px-2.5 py-2">
          <div className="eyebrow mb-0.5">What it measured on this market</div>
          <div className="text-meta text-ash">
            {shape.significant && shape.measuredExcess != null ? (
              <>
                <span className="num text-chalk">
                  {(shape.measuredExcess * 100).toFixed(1)}%
                </span>
                {" "}against the market over {shape.measuredHorizon} sessions.
                {shape.measuredMonths != null && (
                  <>
                    {" "}Measured across {shape.measuredMonths} months
                    {shape.measuredObservations != null && (
                      <span className="text-faint">
                        {" "}(from {shape.measuredObservations.toLocaleString()} detections,
                        collapsed by month because these formations fire together in a
                        selloff)
                      </span>
                    )}, and it survived a false-discovery correction across every
                    pattern and horizon tested.
                  </>
                )}
              </>
            ) : (
              <>Nothing that survived correction, so this formation moved the score by
                zero. It is drawn because it is there, not because it means something.</>
            )}
          </div>
        </div>
      </div>
      {shape.significant && shape.measuredExcess != null && shape.measuredExcess < 0
        && shape.textbookBias === "up" && (
        <p className="prose-col mt-2 text-meta leading-relaxed text-warn">
          Note the disagreement: this shape is textbook-bullish and measured negative.
          Across both markets studied, a formation and its mirror image predicted the
          same thing — which is the cleanest evidence that the shape&apos;s supposed
          meaning is not what is being measured.
        </p>
      )}
      <p className="prose-col mt-2 text-meta leading-relaxed text-faint">
        The heavy line is the kernel fit as it stood on the detection bar, and it stops
        there. No target is projected from it.{shape.firingRate != null && (
          <> This formation fires on {(shape.firingRate * 100).toFixed(0)}% of names in a
          quarter, so finding one is not itself unusual.</>
        )}
      </p>
    </div>
  );
}
