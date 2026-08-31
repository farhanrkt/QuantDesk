"use client";

import { useMemo, useState } from "react";
import {
  CartesianGrid, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart,
  Tooltip, XAxis, YAxis,
} from "recharts";
import { Card, CardBody, CardHeader, CardTitle, Explainer, Note } from "@/components/ui/card";
import { Explain } from "@/components/ui/explain";
import { Field, SelectField } from "@/components/ui/controls";
import type { Engine, ExposureScanResponse, Market, UniversesResponse } from "@/lib/types";
import { num, pct } from "@/lib/utils";

/**
 * What a whole universe moves with, as a cross-section.
 *
 * WHY A SCATTER AND NOT A TABLE OF NUMBERS. This tier exists because one beta
 * is uninterpretable alone — 0.57 against the energy complex is remarkable or
 * ordinary depending on what the other forty names read — and a column of
 * numbers makes the reader do the comparison in their head, one row at a time.
 * Position does it for them: a point's distance from the vertical zero line is
 * how hard the stock moves, its height is how much of the movement that
 * accounts for, and a cluster is visible without reading a single figure.
 *
 * TWO AXES BECAUSE ONE IS A LIE. Beta alone would rank a name that swings 3x on
 * a factor explaining 2% of its variance above one that swings 0.5x on a factor
 * explaining 40%, and the first of those is noise with a large coefficient. The
 * horizontal band below the dotted line is exactly that noise, drawn rather than
 * filtered away, because a scatter showing only the names that loaded would make
 * every universe look uniformly exposed.
 *
 * NO DIVERGING COLOUR SCALE, and that is a constraint rather than a taste. A
 * red-to-green heatmap over beta would be a component deciding that negative is
 * bad — the exact re-litigation of a judgement Python already made that
 * `DESIGN.md` forbids, and here Python has made no such judgement at all,
 * because a stock that rises when the dollar falls is not failing at anything.
 * Every point is the same hue; only position carries meaning.
 */

const EXPOSURE = "#D4763A";
const GRID = "#1E2A36";
const AXIS = "#63748A";

interface Point {
  x: number; y: number; ticker: string; material: boolean;
  /** Vertical dodge level for the label, so neighbours do not overprint. */
  level: number;
}

function FactorTooltip({ active, payload }: {
  active?: boolean; payload?: { payload: Point }[];
}) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="rounded-lg border border-rule bg-raised px-3 py-2 shadow-lg">
      <div className="font-mono text-meta font-semibold text-chalk">{p.ticker}</div>
      <div className="mt-1 text-micro text-ash">
        moves <span className="num text-body">{num(p.x, 2)}x</span> ·{" "}
        explains <span className="num text-body">{pct(p.y, 0)}</span>
      </div>
      {!p.material && (
        <div className="mt-1 text-micro text-faint">below the reporting floor</div>
      )}
    </div>
  );
}

function FactorChart({ factor, rows, materialAt, highlight, yMax }: {
  factor: { key: string; label: string; symbol: string };
  rows: ExposureScanResponse["rows"];
  materialAt: number;
  highlight: string | null;
  yMax: number;
}) {
  const { points, span, named } = useMemo(() => {
    const all: Point[] = rows.flatMap((row) => {
      const load = row.loadings[factor.key];
      if (!load) return [];
      return [{
        x: load.beta, y: load.rSquared, level: 0,
        ticker: row.ticker.replace(/\.JK$/, ""),
        material: load.material || row.ticker === highlight,
      }];
    });
    const width = Math.max(0.4, ...all.map((p) => Math.abs(p.x))) * 1.2;
    // LABELS COLLIDE IN THE MIDDLE OF EVERY CHART, because that is where most
    // of an index sits. Left alone they overprint into an unreadable smear —
    // "CPIN" over "ICBP" reads as neither. Points close together in x are dealt
    // out onto three stacked rows so each name keeps its own line; the dodge is
    // deterministic in data space rather than measured in pixels, so it does not
    // change when the container resizes.
    // COLLISION IS TWO-DIMENSIONAL, and treating it as one was the first mistake.
    // Testing only horizontal distance dodged labels that were never going to
    // overlap — two points a third of the chart apart vertically do not fight —
    // which spent the dodge levels on the wrong pairs and left the real clashes
    // stacked. Both axes, four rows, and the tallest point gets the closest row
    // so the strongest loading is the one that reads cleanly.
    const placed: Point[] = [];
    for (const point of all.filter((p) => p.material)
                           .sort((a, b) => b.y - a.y || a.x - b.x)) {
      const near = placed.filter((q) =>
        Math.abs(q.x - point.x) < width * 0.15 &&
        Math.abs(q.y - point.y) < Math.max(yMax, 0.01) * 0.14);
      const taken = new Set(near.map((q) => q.level));
      point.level = [0, 1, 2, 3].find((l) => !taken.has(l)) ?? 0;
      placed.push(point);
    }
    return {
      points: all,
      named: placed.length,
      span: width,
    };
  }, [rows, factor.key, highlight, yMax]);

  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between gap-2">
        <span className="text-h3 font-semibold text-chalk">{factor.label}</span>
        <span className="font-mono text-micro text-faint">{factor.symbol}</span>
      </div>
      <div className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={{ top: 14, right: 22, bottom: 26, left: 4 }}>
            <CartesianGrid stroke={GRID} strokeDasharray="2 4" />
            <XAxis type="number" dataKey="x" domain={[-span, span]}
                   tick={{ fill: AXIS, fontSize: 11 }} stroke={GRID}
                   tickFormatter={(v: number) => num(v, 1)}
                   label={{ value: "moves this many times as hard", position: "insideBottom",
                            offset: -16, fill: AXIS, fontSize: 11 }} />
            {/* ONE SCALE ACROSS ALL THREE CHARTS. Per-chart auto-scaling made a
                14% loading on copper sit as high as a 31% loading on energy, so
                the eye read two different quantities as the same height — the
                one comparison a small-multiple layout exists to make. */}
            <YAxis type="number" dataKey="y" domain={[0, yMax]}
                   tick={{ fill: AXIS, fontSize: 11 }} stroke={GRID}
                   tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
                   width={44}
                   label={{ value: "share of its moves explained", angle: -90,
                            position: "insideLeft", fill: AXIS, fontSize: 11,
                            style: { textAnchor: "middle" } }} />
            {/* Zero is the only meaningful vertical anchor: left of it the stock
                moves against the factor, right of it with it. Neither is good. */}
            <ReferenceLine x={0} stroke={AXIS} strokeWidth={1} />
            <ReferenceLine y={materialAt} stroke={AXIS} strokeDasharray="3 3"
                           label={{ value: "reporting floor", position: "insideTopRight",
                                    fill: AXIS, fontSize: 10 }} />
            <Tooltip content={<FactorTooltip />} cursor={{ stroke: AXIS }} />
            {/* ONE SERIES, DRAWN BY HAND, and both halves of that are fixes.
                Two Scatter series — one recessive, one labelled — silently
                rendered only the first, and a ZAxis bound to a constant collapsed
                every radius to zero, so the chart showed axes and no points. A
                shape that draws its own circle and its own label depends on
                neither, and puts the label where the finding is: on the point. */}
            <Scatter data={points} shape={(props: unknown) => {
              const { cx, cy, payload } = props as
                { cx: number; cy: number; payload: Point };
              return (
                <g>
                  <circle cx={cx} cy={cy} r={payload.material ? 5 : 3}
                          fill={payload.material ? EXPOSURE : AXIS}
                          fillOpacity={payload.material ? 0.9 : 0.4} />
                  {payload.material && (
                    <text x={cx} y={cy - 9 - payload.level * 11} textAnchor="middle"
                          fill="#C3CFDC" fontSize={10} fontFamily="monospace">
                      {payload.ticker}
                    </text>
                  )}
                </g>
              );
            }} />
          </ScatterChart>
        </ResponsiveContainer>
      </div>
      {named === 0 && (
        <p className="mt-1 text-meta leading-relaxed text-ash">
          Nothing in this list clears the floor on this one.
        </p>
      )}
    </div>
  );
}

/** The tallest loading anywhere in the scan, so all three charts share a scale. */
function sharedYMax(data: ExposureScanResponse): number {
  const all = data.rows.flatMap((r) => Object.values(r.loadings).map((l) => l.rSquared));
  return Math.max(0.12, ...all) * 1.15;
}

export function ExposurePanel({
  universeState, market, onMarketChange, state, onScan, highlight,
}: {
  universeState: Engine<UniversesResponse>;
  market: Market;
  onMarketChange: (m: Market) => void;
  state: Engine<ExposureScanResponse>;
  onScan: (params: { universe?: string | null; tickers?: string; market: Market }) => void;
  highlight: string | null;
}) {
  const catalogue = universeState.status === "ready" ? universeState.data.universes : [];
  const [choice, setChoice] = useState<string>("idx30");

  return (
    <div className="space-y-4 animate-rise">
      <Card accent={EXPOSURE}>
        <CardHeader>
          <CardTitle>What drives this market</CardTitle>
        </CardHeader>
        <CardBody className="space-y-3">
          <p className="prose-col text-meta leading-relaxed">
            A large part of any index is not a set of companies so much as a set of bets
            on a few outside prices. This measures every name in a list against the
            factors whose betas were shown to survive a year, and plots the whole
            cross-section — because one beta on its own has no scale to be read against.
          </p>
          <div className="flex flex-wrap items-end gap-3">
            <Field label="Universe">
              <SelectField value={choice} onChange={setChoice}
                           options={catalogue.map((u) => ({
                             value: u.id, label: `${u.name} (${u.count})` }))} />
            </Field>
            <Field label="Market">
              <SelectField value={market} onChange={(v) => onMarketChange(v as Market)}
                           options={[{ value: "US", label: "US" },
                                     { value: "ID", label: "IDX (.JK)" }]} />
            </Field>
            <button type="button"
                    onClick={() => onScan({ universe: choice, market })}
                    disabled={state.status === "loading"}
                    className="min-h-[2.25rem] rounded-lg border border-rule bg-raised px-4
                               text-meta font-medium text-chalk transition
                               hover:border-faint disabled:opacity-50">
              {state.status === "loading" ? "Measuring…" : "Measure this universe"}
            </button>
          </div>
        </CardBody>
      </Card>

      {state.status === "error" && (
        <Card className="border-dist/40 bg-dist/5">
          <CardBody>
            <p className="prose-col text-meta leading-relaxed">{state.failure.message}</p>
          </CardBody>
        </Card>
      )}

      {state.status === "ready" && !state.data.usable && (
        <Card>
          <CardBody>
            <p className="prose-col text-meta leading-relaxed">
              {state.data.reason ?? "Nothing measurable in this list."}
            </p>
          </CardBody>
        </Card>
      )}

      {state.status === "ready" && state.data.usable && (
        <>
          <Card>
            <CardHeader>
              <CardTitle>{state.data.universe.name}</CardTitle>
              <span className="font-mono text-micro text-ash">
                {state.data.scanned} names · {state.data.weeks} weeks
              </span>
            </CardHeader>
            {/* STACKED, NOT THREE ACROSS. At a third of the width the points
                collided near zero and there was no room to name any of them, so
                the chart showed that something loaded without showing what. */}
            <CardBody className="space-y-8">
              {state.data.factors.map((factor) => (
                <FactorChart key={factor.key} factor={factor} rows={state.data.rows}
                             materialAt={state.data.materialAt ?? 0.05}
                             highlight={highlight}
                             yMax={sharedYMax(state.data)} />
              ))}
            </CardBody>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>How common each one is here</CardTitle>
            </CardHeader>
            <CardBody className="space-y-2">
              {state.data.factors.map((factor) => {
                const ex = state.data.explain?.[`factorBreadth.${factor.key}`];
                return (
                  <div key={factor.key} className="flex items-start gap-2">
                    <Explain explain={ex} />
                    <p className="text-meta leading-relaxed text-body">
                      {ex?.reading ?? factor.label}
                    </p>
                  </div>
                );
              })}
            </CardBody>
          </Card>

          <Card>
            <CardBody className="space-y-3">
              <Note>
                An empty chart is not a finding about diversification. It means none of
                these factors explained these names, and the factor that does may not be
                on the list — peer baskets of miners and plantations were built for this
                and measured worse than the traded contracts, so they are not here.
              </Note>
              {state.data.refused.length > 0 && (
                <Explainer summary={
                  state.data.refused.length === 1
                    ? `${state.data.refused[0].label} was tested and is deliberately not shown`
                    : "Some factors were tested and are deliberately not shown"
                }>
                  <p>
                    A factor is only screened on if its own year-to-year stability was
                    measured and survived. Across nine years the names loading hardest on
                    gold in one year were barely the same names the next, so a gold beta
                    describes what happened rather than what is likely to keep happening.
                  </p>
                  <ul className="mt-2 space-y-1">
                    {state.data.refused.map((r) => (
                      <li key={r.key} className="text-meta text-ash">
                        <span className="text-body">{r.label}</span> — {r.reason}
                      </li>
                    ))}
                  </ul>
                  {state.data.measuredOn && (
                    <p className="mt-2 text-micro text-faint">
                      Persistence measured {state.data.measuredOn}; a factor is screened
                      on only above a rank correlation of {num(state.data.killAt ?? 0, 2)}.
                      Price and volume only — nothing here knows what these businesses do,
                      which is why an industrials company sitting among the miners is a
                      question for the reader rather than an answer.
                    </p>
                  )}
                </Explainer>
              )}
              {(state.data.missing ?? []).length > 0 && (
                <p className="text-meta leading-relaxed text-ash">
                  Not measured: {(state.data.missing ?? []).join(", ")} — too few weeks of
                  history. Dropped rather than estimated.
                </p>
              )}
            </CardBody>
          </Card>
        </>
      )}
    </div>
  );
}
