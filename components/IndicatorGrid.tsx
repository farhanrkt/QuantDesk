"use client";

import { Card, CardBody, CardHeader, CardTitle, Explainer } from "@/components/ui/card";
import { ExplainedStat, useDetail } from "@/components/ui/explain";
import type { ExplainMap } from "@/lib/types";

/**
 * Every indicator, grouped by the horizon it actually speaks to.
 *
 * The grouping is the point. A long-term investor reading "Stochastic 82,
 * overbought" next to "price above its 200-day average" has been handed two
 * statements of very different weight presented identically. Short-horizon
 * oscillators are useful for TIMING an entry once a multi-year case exists;
 * they are not a case. Labelling the horizon on each group says so without
 * hiding anything — and now the evidence line inside each explanation says it
 * again in words: momentum is "strong", RSI levels are "weak".
 *
 * WHAT MOVED OUT OF THIS FILE. The previous version decided here what "ADX 27"
 * meant, what colour it should be, and wrote a one-line note. Three separate
 * judgements, in JSX, untested. All three now arrive from
 * `api/_lib/explain.py`; this component decides layout and nothing else.
 */
export function IndicatorGrid({ explanations }: { explanations: ExplainMap }) {
  const detail = useDetail();
  const simple = detail === "simple";
  const ex = explanations ?? {};

  const groups: [string, string, string[]][] = [
    ["Long horizon", "months to years — where a long-term case is made",
     ["sma200", "sma100", "adx", "aroon", "roc252"]],
    ["Medium", "weeks to months — confirmation",
     ["sma50", "macd", "roc63", "cci", "cmf", "mfi", "volumeTrend"]],
    ["Short horizon", "days to weeks — entry timing only, never a thesis",
     ["rsi", "stochastic", "williamsR", "bbPercentB", "bbBandwidth", "atrPct"]],
  ];

  return (
    <div className="space-y-4">
      {simple && (
        <div className="rounded border border-rule bg-panel px-4 py-3">
          <Explainer summary="Grouped by how long a horizon each one actually speaks to">
            Only the top group has any bearing on owning something for years. The bottom group
            describes the last two weeks, and the evidence behind it is weak even for that.
            {" "}Press the <span className="font-semibold text-body">i</span> beside any number
            to see what it measures and whether this reading is good or bad.
          </Explainer>
        </div>
      )}
      {groups.map(([title, subtitle, keys]) => {
        const present = keys.map((key) => ex[key]).filter(Boolean);
        if (present.length === 0) return null;
        // Simple mode drops the short-horizon group entirely rather than
        // shrinking it. Everything in it is labelled weak evidence and none of
        // it belongs in a five-number summary of a holding.
        if (simple && title === "Short horizon") return null;
        return (
          <Card key={title}>
            <CardHeader>
              <CardTitle>{title}</CardTitle>
              <span className="text-micro text-ash">{subtitle}</span>
            </CardHeader>
            <CardBody>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {keys.map((key) => ex[key] && (
                  <ExplainedStat key={key} explain={ex[key]} />
                ))}
              </div>
            </CardBody>
          </Card>
        );
      })}
    </div>
  );
}
