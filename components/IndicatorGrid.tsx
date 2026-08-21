"use client";

import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { cn, num, pct } from "@/lib/utils";

type Reading = {
  label: string;
  value: string;
  note: string;
  tone: "bull" | "bear" | "warn" | "neutral";
};

const TONE_CLASS = {
  bull: "text-acc", bear: "text-dist", warn: "text-warn", neutral: "text-chalk/85",
} as const;

const has = (v: number | null | undefined): v is number =>
  v !== null && v !== undefined && Number.isFinite(v);

/**
 * Every indicator, grouped by the horizon it actually speaks to.
 *
 * The grouping is the point. A long-term investor reading "Stochastic 82,
 * overbought" next to "price above its 200-day average" has been handed two
 * statements of very different weight presented identically. Short-horizon
 * oscillators are useful for TIMING an entry once a multi-year case exists;
 * they are not a case. Labelling the horizon on each group says so without
 * hiding anything.
 */
export function IndicatorGrid({
  indicators, price,
}: { indicators: Record<string, number | null>; price: number }) {
  const i = indicators;

  const longHorizon: Reading[] = [];
  const medium: Reading[] = [];
  const short: Reading[] = [];

  // ---- long horizon ----
  if (has(i.sma200)) {
    const above = price > i.sma200;
    longHorizon.push({
      label: "200-day average", value: num(i.sma200),
      note: `${signed(price / i.sma200 - 1)} away`,
      tone: above ? "bull" : "bear",
    });
  }
  if (has(i.sma100)) {
    longHorizon.push({
      label: "100-day average", value: num(i.sma100),
      note: `${signed(price / i.sma100 - 1)} away`,
      tone: price > i.sma100 ? "bull" : "bear",
    });
  }
  if (has(i.adx) && has(i.plusDi) && has(i.minusDi)) {
    const strong = i.adx >= 25;
    longHorizon.push({
      label: "ADX (trend strength)", value: num(i.adx, 0),
      note: strong
        ? `trending, ${i.plusDi > i.minusDi ? "+DI leads" : "-DI leads"}`
        : "below 25 — directionless",
      tone: !strong ? "neutral" : i.plusDi > i.minusDi ? "bull" : "bear",
    });
  }
  if (has(i.aroonUp) && has(i.aroonDown)) {
    longHorizon.push({
      label: "Aroon", value: `${num(i.aroonUp, 0)} / ${num(i.aroonDown, 0)}`,
      note: "up / down — recency of the high and low",
      tone: i.aroonUp > i.aroonDown ? "bull" : "bear",
    });
  }
  if (has(i.donchianUpper) && has(i.donchianLower)) {
    const nearHigh = price >= i.donchianUpper * 0.98;
    longHorizon.push({
      label: "52-week channel",
      value: `${num(i.donchianLower)} – ${num(i.donchianUpper)}`,
      note: nearHigh ? "at the top of its yearly range" : "inside the yearly range",
      tone: nearHigh ? "bull" : "neutral",
    });
  }
  if (has(i.ichimokuSpanA) && has(i.ichimokuSpanB)) {
    const top = Math.max(i.ichimokuSpanA, i.ichimokuSpanB);
    const bottom = Math.min(i.ichimokuSpanA, i.ichimokuSpanB);
    const above = price > top;
    longHorizon.push({
      label: "Ichimoku cloud", value: `${num(bottom)} – ${num(top)}`,
      note: above ? "price above the cloud" : price < bottom ? "below the cloud" : "inside it",
      tone: above ? "bull" : price < bottom ? "bear" : "neutral",
    });
  }
  if (has(i.roc252)) {
    longHorizon.push({
      label: "12-month rate of change", value: `${num(i.roc252, 1)}%`,
      note: "trailing one-year price change",
      tone: i.roc252 > 0 ? "bull" : "bear",
    });
  }

  // ---- medium ----
  if (has(i.macd) && has(i.macdSignal)) {
    medium.push({
      label: "MACD", value: num(i.macd, 2),
      note: i.macd > i.macdSignal ? "above its signal line" : "below its signal line",
      tone: i.macd > i.macdSignal ? "bull" : "bear",
    });
  }
  if (has(i.roc63)) {
    medium.push({
      label: "3-month rate of change", value: `${num(i.roc63, 1)}%`,
      note: "trailing quarter", tone: i.roc63 > 0 ? "bull" : "bear",
    });
  }
  if (has(i.cci)) {
    medium.push({
      label: "CCI", value: num(i.cci, 0),
      note: i.cci > 100 ? "stretched high" : i.cci < -100 ? "stretched low" : "in range",
      tone: i.cci > 100 ? "warn" : i.cci < -100 ? "warn" : "neutral",
    });
  }
  if (has(i.cmf)) {
    medium.push({
      label: "Chaikin money flow", value: num(i.cmf, 3),
      note: i.cmf > 0 ? "buying pressure" : "selling pressure",
      tone: i.cmf > 0 ? "bull" : "bear",
    });
  }
  if (has(i.mfi)) {
    medium.push({
      label: "Money flow index", value: num(i.mfi, 0),
      note: i.mfi > 80 ? "overbought" : i.mfi < 20 ? "oversold" : "neutral",
      tone: i.mfi > 80 || i.mfi < 20 ? "warn" : "neutral",
    });
  }
  if (has(i.volumeTrend)) {
    medium.push({
      label: "Volume vs its year", value: `${num(i.volumeTrend)}x`,
      note: i.volumeTrend > 1.2 ? "participation rising" : "participation normal or fading",
      tone: i.volumeTrend > 1.2 ? "bull" : "neutral",
    });
  }

  // ---- short ----
  if (has(i.rsi)) {
    short.push({
      label: "RSI (14)", value: num(i.rsi, 0),
      note: i.rsi >= 70 ? "overbought" : i.rsi <= 30 ? "oversold" : "neutral",
      tone: i.rsi >= 70 || i.rsi <= 30 ? "warn" : "neutral",
    });
  }
  if (has(i.stochK) && has(i.stochD)) {
    short.push({
      label: "Stochastic", value: `${num(i.stochK, 0)} / ${num(i.stochD, 0)}`,
      note: i.stochK >= 80 ? "overbought" : i.stochK <= 20 ? "oversold" : "%K / %D",
      tone: i.stochK >= 80 || i.stochK <= 20 ? "warn" : "neutral",
    });
  }
  if (has(i.williamsR)) {
    short.push({
      label: "Williams %R", value: num(i.williamsR, 0),
      note: i.williamsR >= -20 ? "overbought" : i.williamsR <= -80 ? "oversold" : "neutral",
      tone: i.williamsR >= -20 || i.williamsR <= -80 ? "warn" : "neutral",
    });
  }
  if (has(i.bbPercentB)) {
    short.push({
      label: "Bollinger %B", value: num(i.bbPercentB, 2),
      note: i.bbPercentB > 1 ? "above the upper band"
        : i.bbPercentB < 0 ? "below the lower band" : "inside the bands",
      tone: i.bbPercentB > 1 || i.bbPercentB < 0 ? "warn" : "neutral",
    });
  }
  if (has(i.bbBandwidth)) {
    short.push({
      label: "Bollinger bandwidth", value: pct(i.bbBandwidth, 1),
      note: "band width relative to the centre — the squeeze measure",
      tone: "neutral",
    });
  }
  if (has(i.atr) && has(i.atrPct)) {
    short.push({
      label: "ATR (14)", value: num(i.atr),
      note: `${pct(i.atrPct, 1)} of price — the unit to size positions in`,
      tone: "neutral",
    });
  }

  const groups: [string, string, Reading[]][] = [
    ["Long horizon", "months to years — where a long-term case is made", longHorizon],
    ["Medium", "weeks to months — confirmation", medium],
    ["Short horizon", "days to weeks — entry timing only, never a thesis", short],
  ];

  return (
    <div className="space-y-4">
      {groups.map(([title, subtitle, readings]) => readings.length > 0 && (
        <Card key={title}>
          <CardHeader>
            <CardTitle>{title}</CardTitle>
            <span className="text-[0.65rem] text-ash">{subtitle}</span>
          </CardHeader>
          <CardBody>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {readings.map((reading) => (
                <div key={reading.label}
                     className="rounded border border-rule bg-raised/40 px-3 py-2">
                  <div className="eyebrow mb-1">{reading.label}</div>
                  <div className={cn("num text-base font-semibold", TONE_CLASS[reading.tone])}>
                    {reading.value}
                  </div>
                  <div className="mt-0.5 text-[0.68rem] leading-snug text-ash">
                    {reading.note}
                  </div>
                </div>
              ))}
            </div>
          </CardBody>
        </Card>
      ))}
    </div>
  );
}

function signed(value: number) {
  return `${value >= 0 ? "+" : ""}${(value * 100).toFixed(1)}%`;
}
