"use client";

import { AlertTriangle, ArrowRight, Ban, Target } from "lucide-react";
import { Card, CardBody, CardHeader, CardTitle, Note } from "@/components/ui/card";
import {
  Explain, ExplainedRow, ExplainedStat, TONE_HEX, useDetail,
} from "@/components/ui/explain";
import type { ExplainMap, HorizonBlock, PivotSet } from "@/lib/types";
import { cn, num, pct, signedPct } from "@/lib/utils";

const UP = "#35C4A8";
const DOWN = "#FF6B6B";
const WARN = "#F2C14E";
const ASH = "#7A8CA0";

const EVIDENCE_BADGE: Record<string, { text: string; colour: string }> = {
  strong: { text: "Well evidenced", colour: UP },
  moderate: { text: "Moderately evidenced", colour: UP },
  weak: { text: "Thinly evidenced", colour: WARN },
};

/**
 * One shorter-horizon readout: the setup, the levels, and how much to risk.
 *
 * THE PANEL IS ORGANISED AROUND ITS OWN WEAKNESS. The long-horizon section
 * earns its confidence from decades of published work. This one does not, and
 * presenting both in the same voice would be the most misleading thing the app
 * could do. So the evidence grade sits in the header next to the setup name
 * rather than in a footnote, and when no setup is present the panel says so in
 * a full sentence instead of quietly rendering an empty grid.
 *
 * The plan block only appears for a LONG setup. A breakdown gets its structure
 * described and no entry, stop or target — this app does not plan short
 * positions and pretending otherwise with a mirrored arithmetic would be a
 * feature nobody validated.
 */
export function HorizonPanel({ data, currency }: { data: HorizonBlock; currency: string }) {
  const detail = useDetail();
  const simple = detail === "simple";
  const ex: ExplainMap = data.explain ?? {};

  if (!data.usable) {
    return (
      <Card className="animate-rise border-warn/40 bg-warn/5">
        <CardBody className="flex gap-3">
          <AlertTriangle aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-warn" />
          <div>
            <div className="eyebrow mb-1 text-warn">
              {data.label ?? "This horizon"} withheld
            </div>
            <p className="text-base leading-relaxed text-body">{data.reason}</p>
          </div>
        </CardBody>
      </Card>
    );
  }

  const setup = data.setup!;
  const plan = data.plan!;
  const levels = data.levels!;
  const story = data.plainEnglish;
  const evidence = setup.evidence ? EVIDENCE_BADGE[setup.evidence] : null;
  const accent = setup.direction === "long" ? UP
    : setup.direction === "short" ? DOWN : ASH;
  const money = (v: number | null | undefined) =>
    v == null ? "—" : `${currency === "USD" ? "$" : currency === "IDR" ? "Rp" : ""}${num(v)}`;

  return (
    <div className="space-y-4 animate-rise">
      {/* ---------------- the readout in plain English ---------------- */}
      <Card accent={accent}>
        <CardHeader>
          <CardTitle>
            {setup.name ?? "No setup right now"}
          </CardTitle>
          <div className="flex items-center gap-3">
            {evidence && (
              <span className="font-mono text-micro uppercase tracking-[0.1em]"
                    style={{ color: evidence.colour }}>
                {evidence.text}
              </span>
            )}
            <span className="font-mono text-micro text-ash">{data.window}</span>
          </div>
        </CardHeader>
        <CardBody className="space-y-3">
          {story?.paragraphs.map((paragraph, i) => (
            <p key={i}
               className={cn(
                 "leading-relaxed",
                 i === story.paragraphs.length - 1
                   ? "rounded border border-warn/30 bg-warn/5 px-3 py-2 text-meta text-warn/90"
                   : "text-base text-body",
               )}>
              {paragraph}
            </p>
          ))}
        </CardBody>
      </Card>

      {/* ---------------- the plan ---------------- */}
      {plan.usable ? (
        <Card accent={TONE_HEX[ex.riskReward?.tone ?? "neutral"]}>
          <CardHeader>
            <CardTitle>Where the levels would sit</CardTitle>
            <span className="font-mono text-micro text-ash">
              not a recommendation
            </span>
          </CardHeader>
          <CardBody className="space-y-4">
            {/* The entry → stop → target line, drawn as one journey rather than
                three unrelated tiles, because the relationship between them is
                the only thing that makes any of them meaningful. */}
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded border border-rule bg-raised/40 px-3 py-2">
                <div className="eyebrow mb-1">Entry</div>
                <div className="num text-figure font-semibold text-chalk">{money(plan.entry)}</div>
                <div className="mt-0.5 text-micro leading-snug text-ash">
                  today&apos;s price
                </div>
              </div>
              <div className="rounded border border-dist/40 bg-dist/5 px-3 py-2">
                <div className="eyebrow mb-1 flex items-center gap-1.5">
                  Stop <Explain explain={ex.stopDistance} />
                </div>
                <div className="num text-figure font-semibold text-dist">{money(plan.stop)}</div>
                <div className="mt-0.5 text-micro leading-snug text-ash">
                  {pct(plan.stopDistancePct)} down ·{" "}
                  {num(plan.stopDistanceAtr, 1)} average days
                  {plan.stopWidened && " · widened from structure"}
                </div>
              </div>
              <div className="rounded border border-acc/40 bg-acc/5 px-3 py-2">
                <div className="eyebrow mb-1 flex items-center gap-1.5">
                  <Target aria-hidden className="h-3 w-3" /> First target
                </div>
                <div className="num text-figure font-semibold text-acc">
                  {money(plan.targets?.[0]?.price)}
                </div>
                <div className="mt-0.5 text-micro leading-snug text-ash">
                  {signedPct(plan.targets?.[0]?.distancePct)} · {plan.targets?.[0]?.basis}
                </div>
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <ExplainedStat explain={ex.riskReward} />
              <ExplainedStat explain={ex.positionShare}
                             sub={`risking ${pct(plan.riskBudget, 0)} of the account`} />
            </div>

            {(plan.targets?.length ?? 0) > 1 && !simple && (
              <div className="space-y-1 text-meta">
                <div className="eyebrow">Further targets</div>
                {plan.targets!.slice(1).map((target) => (
                  <div key={target.label}
                       className="flex items-baseline justify-between gap-3 border-b border-ruleSoft pb-1 last:border-0">
                    <span className="text-ash">{target.label}</span>
                    <span className="num">
                      {money(target.price)} · {num(target.rMultiple, 1)}x risk
                    </span>
                  </div>
                ))}
              </div>
            )}

            <Note>
              The stop sits beyond a level the price turned at before, not at a round
              percentage. A wider stop means a smaller position for the same money at risk.
            </Note>
          </CardBody>
        </Card>
      ) : (
        <Card>
          <CardBody className="flex gap-3">
            <Ban aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-ash" />
            <p className="text-base leading-relaxed text-ash">{plan.reason}</p>
          </CardBody>
        </Card>
      )}

      {/* ---------------- levels ---------------- */}
      <Card>
        <CardHeader>
          <CardTitle>Floors and ceilings</CardTitle>
          <span className="font-mono text-micro text-ash">
            confirmed turning points
          </span>
        </CardHeader>
        <CardBody className="space-y-3">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5 text-meta">
              <div className="eyebrow flex items-center gap-1.5">
                Ceilings above <Explain explain={ex["distanceToLevel.resistance"]} />
              </div>
              {levels.resistances.length === 0 ? (
                <p className="text-meta leading-relaxed text-ash">
                  None. The price is above every level it has previously turned at in this
                  window — there is no overhead supply to work through, and equally no reference
                  point for a target.
                </p>
              ) : levels.resistances.map((level) => (
                <LevelRow key={level.price} level={level} money={money} tone="text-dist" />
              ))}
            </div>
            <div className="space-y-1.5 text-meta">
              <div className="eyebrow flex items-center gap-1.5">
                Floors below <Explain explain={ex["distanceToLevel.support"]} />
              </div>
              {levels.supports.length === 0 ? (
                <p className="text-meta leading-relaxed text-ash">
                  None in this window, which is why any stop below has to be placed by
                  volatility rather than by structure.
                </p>
              ) : levels.supports.map((level) => (
                <LevelRow key={level.price} level={level} money={money} tone="text-acc" />
              ))}
            </div>
          </div>
          <p className="text-meta leading-relaxed text-ash">
            A level is a price the market turned at, with {" "}
            <span className="text-body">bars either side</span> confirming it. A level tested
            once is barely a level; one tested three or four times is a price more participants
            are watching. The most recent {levels.confirmationLag} bars can never appear here —
            a turning point is only a turning point in hindsight.
          </p>
        </CardBody>
      </Card>

      {/* ---------------- context ---------------- */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <ExplainedStat explain={ex.volumeRatio} />
        <ExplainedStat explain={ex.squeezePercentile} />
        <ExplainedStat explain={ex.divergenceState} />
        <ExplainedStat explain={ex.gapState} />
        {(data.vwap?.anchors ?? []).slice(0, 2).map((anchor) => (
          <ExplainedStat key={anchor.label}
                         explain={ex[`vwapDistance.${anchor.label}`]}
                         sub={`${money(anchor.vwap)} · anchored ${anchor.anchoredOn}`} />
        ))}
      </div>

      {!simple && (
        <>
          {/* ---------------- pivots ---------------- */}
          {data.pivots?.classic.usable && (
            <Card>
              <CardHeader>
                <CardTitle>Pivot levels</CardTitle>
                <span className="font-mono text-micro text-ash">
                  from last complete {data.pivots.classic.period}
                </span>
              </CardHeader>
              <CardBody className="space-y-3">
                <div className="grid gap-4 lg:grid-cols-2">
                  <PivotTable title="Classic" set={data.pivots.classic}
                              price={data.price!} money={money} />
                  <PivotTable title="Fibonacci" set={data.pivots.fibonacci}
                              price={data.price!} money={money} />
                </div>
                <p className="text-meta leading-relaxed text-ash">
                  Arithmetic on last {data.pivots.classic.period}&apos;s high, low and close —
                  nothing more. They are here because a great many traders watch them, which is
                  the only mechanism by which they could work and also the reason not to
                  overstate them. There is no published evidence they produce excess returns
                  after costs. They are computed from the last COMPLETE period, so they do not
                  move under you during the current one.
                </p>
              </CardBody>
            </Card>
          )}

          {/* ---------------- candlesticks, honestly framed ---------------- */}
          <Card>
            <CardHeader>
              <CardTitle>Candlestick and chart patterns</CardTitle>
              <span className="font-mono text-micro text-warn">no demonstrated value</span>
            </CardHeader>
            <CardBody className="space-y-3">
              {(data.candlesticks?.length ?? 0) === 0 ? (
                <p className="text-base text-ash">
                  No single- or two-bar formation on the latest bar.
                </p>
              ) : (
                <ul className="space-y-2">
                  {data.candlesticks!.map((pattern) => (
                    <li key={pattern.name} className="border-b border-ruleSoft pb-2 last:border-0">
                      <div className="flex items-baseline gap-2">
                        <span className="text-meta font-semibold text-body">{pattern.name}</span>
                        <span className="font-mono text-micro text-ash">{pattern.date}</span>
                      </div>
                      <p className="mt-0.5 text-meta leading-relaxed text-ash">
                        {pattern.meaning}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
              <div className="rounded border border-warn/30 bg-warn/5 px-3 py-2">
                <Note tone="warn">
                  Shown because you will meet them elsewhere. No entry, stop or target here
                  ever comes from one — tested against random price series, they show no value.
                </Note>
              </div>
              <div>
                <div className="eyebrow mb-1.5">What this app will not claim to detect</div>
                <ul className="space-y-1">
                  {(data.undetectable ?? []).map((item) => (
                    <li key={item.name} className="flex gap-2 text-meta leading-relaxed">
                      <ArrowRight aria-hidden className="mt-1 h-2.5 w-2.5 shrink-0 text-ash" />
                      <span>
                        <span className="text-body">{item.name}</span>
                        <span className="text-ash"> — {item.why}.</span>
                      </span>
                    </li>
                  ))}
                </ul>
                <div className="mt-2">
                  <Note>
                    Each needs a judgement about where the shape begins. A simple matcher would
                    fire several times a month on noise, so they are declined rather than
                    detected badly.
                  </Note>
                </div>
              </div>
            </CardBody>
          </Card>

          {/* ---------------- trend and structure detail ---------------- */}
          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader><CardTitle>Moving-average alignment</CardTitle></CardHeader>
              <CardBody className="space-y-2 text-meta">
                <ExplainedRow label={`${setup.trend?.fastLength}-day average`}
                              value={money(setup.trend?.fast)} tone="text-chalk" />
                <ExplainedRow label={`${setup.trend?.slowLength}-day average`}
                              value={money(setup.trend?.slow)} tone="text-chalk" />
                <ExplainedRow label="200-day average" value={money(setup.trend?.long)}
                              tone="text-chalk" />
                <ExplainedRow label="Slower average is"
                              value={setup.trend?.slowRising == null ? "—"
                                : setup.trend.slowRising ? "rising" : "falling"}
                              tone={setup.trend?.slowRising ? "text-acc" : "text-dist"} />
                <ExplainedRow label="Stacked"
                              value={setup.trend?.alignment === "up" ? "price > fast > slow"
                                : setup.trend?.alignment === "down" ? "price < fast < slow"
                                : "mixed"}
                              tone={setup.trend?.alignment === "up" ? "text-acc"
                                : setup.trend?.alignment === "down" ? "text-dist" : "text-ash"} />
                <p className="pt-1 text-meta leading-relaxed text-ash">
                  &quot;Stacked&quot; means the price, the fast average and the slow average are
                  in order. It is the plainest description of a trend there is, and it is
                  descriptive — it tells you what has been happening, not what happens next.
                </p>
              </CardBody>
            </Card>

            <Card>
              <CardHeader><CardTitle>Recent gaps</CardTitle></CardHeader>
              <CardBody className="space-y-2 text-meta">
                {(data.gaps?.gaps?.length ?? 0) === 0 ? (
                  <p className="text-meta leading-relaxed text-ash">
                    No gap larger than half an average daily range in the recent history.
                  </p>
                ) : (
                  <>
                    {data.gaps!.gaps.slice(-5).reverse().map((gap) => (
                      <div key={gap.date}
                           className="flex items-baseline justify-between gap-3 border-b border-ruleSoft pb-1.5 last:border-0">
                        <span className="text-ash">
                          {gap.date} · {gap.direction}
                        </span>
                        <span className={cn("num", gap.filled ? "text-ash" : "text-warn")}>
                          {money(gap.from)} → {money(gap.to)} · {gap.filled ? "filled" : "open"}
                        </span>
                      </div>
                    ))}
                    <div className="pt-1">
                      <Note>
                        Prices the stock jumped over, so almost nobody traded there. Gaps do
                        not always fill.
                      </Note>
                    </div>
                  </>
                )}
              </CardBody>
            </Card>
          </div>

          {data.vwap?.usable && (
            <p className="text-meta leading-relaxed text-ash">{data.vwap.caveat}</p>
          )}
          {data.divergence?.caveat && (
            <p className="text-meta leading-relaxed text-ash">{data.divergence.caveat}</p>
          )}
        </>
      )}
    </div>
  );
}

function LevelRow({
  level, money, tone,
}: {
  level: { price: number; touches: number; distancePct: number; distanceAtr: number };
  money: (v: number | null | undefined) => string;
  tone: string;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-ruleSoft pb-1 last:border-0">
      <span className="text-ash">
        turned {level.touches}x
      </span>
      <span className={cn("num font-semibold", tone)}>
        {money(level.price)}
        <span className="ml-2 font-normal text-ash">{signedPct(level.distancePct)}</span>
      </span>
    </div>
  );
}

function PivotTable({
  title, set, price, money,
}: {
  title: string; set: PivotSet; price: number;
  money: (v: number | null | undefined) => string;
}) {
  if (!set.usable) return null;
  const rows: [string, number | undefined][] = [
    ["R3", set.r3], ["R2", set.r2], ["R1", set.r1],
    ["Pivot", set.pivot],
    ["S1", set.s1], ["S2", set.s2], ["S3", set.s3],
  ];
  return (
    <div>
      <div className="eyebrow mb-1.5">{title}</div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-meta">
          <tbody>
            {rows.map(([label, value]) => (
              <tr key={label} className="border-b border-ruleSoft last:border-0">
                <td className={cn("py-1", label === "Pivot" ? "text-chalk" : "text-ash")}>
                  {label}
                </td>
                <td className={cn("num py-1 text-right",
                                  label === "Pivot" ? "font-semibold text-chalk"
                                    : label.startsWith("R") ? "text-dist/80" : "text-acc/80")}>
                  {money(value)}
                </td>
                <td className="num py-1 text-right text-ash">
                  {value == null ? "—" : signedPct(value / price - 1)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
