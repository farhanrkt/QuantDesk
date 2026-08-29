"use client";

import { AlertTriangle } from "lucide-react";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { ApplyButton } from "@/components/ui/controls";
import { PanelSkeleton } from "@/components/ui/skeleton";
import type { CarSummary, EventStudyResponse, Engine } from "@/lib/types";
import { cn, num, pct } from "@/lib/utils";

const UP = "#35C4A8";
const DOWN = "#FF6B6B";

/** Conventional two-sided significance bands, labelled rather than starred. */
function significance(p: number | null): { label: string; className: string } {
  if (p === null) return { label: "—", className: "text-ash" };
  if (p < 0.01) return { label: "p < 0.01", className: "text-acc" };
  if (p < 0.05) return { label: `p = ${p.toFixed(3)}`, className: "text-acc" };
  if (p < 0.10) return { label: `p = ${p.toFixed(3)}`, className: "text-warn" };
  return { label: `p = ${p.toFixed(2)}`, className: "text-ash" };
}

/**
 * The colour of a cumulative abnormal return, decided by whether it is
 * DISTINGUISHABLE FROM ZERO rather than by its sign.
 *
 * THIS PANEL EXISTS TO REPORT NULLS. On JPM it returns no significant effect at
 * any horizon, and that is the finding the whole feature is built to deliver.
 * Painting a +0.73% mean CAR green when its p-value is 0.34 says the opposite of
 * what the row beside it says — the reader sees a green number and a "p = 0.34"
 * and takes the colour, because colour is read first and read faster.
 *
 * So an insignificant CAR is grey however it is signed, and only a result that
 * clears the conventional cutoff is allowed to take a direction.
 */
function carTone(summary: CarSummary | null): string {
  if (!summary || summary.pValue === null || summary.pValue >= 0.05) return "text-chalk";
  return summary.meanCar >= 0 ? "text-acc" : "text-dist";
}

function CarRow({ horizon, summary }: { horizon: string; summary: CarSummary | null }) {
  if (!summary) {
    return (
      <tr className="border-b border-ruleSoft last:border-0">
        <td className="num px-5 py-2">+{horizon}d</td>
        <td colSpan={5} className="px-5 py-2 text-ash">too few events to test</td>
      </tr>
    );
  }
  const sig = significance(summary.pValue);
  return (
    <tr className="border-b border-ruleSoft last:border-0 hover:bg-raised/60">
      <td className="num px-5 py-2">+{horizon}d</td>
      <td className={cn("num px-5 py-2 text-right", carTone(summary))}>
        {summary.meanCar >= 0 ? "+" : ""}{pct(summary.meanCar, 2)}
      </td>
      <td className="num px-5 py-2 text-right text-ash">
        {summary.medianCar >= 0 ? "+" : ""}{pct(summary.medianCar, 2)}
      </td>
      <td className="num px-5 py-2 text-right">{num(summary.tStat ?? 0)}</td>
      <td className={cn("num px-5 py-2 text-right", sig.className)}>{sig.label}</td>
      <td className="num px-5 py-2 text-right text-ash">{pct(summary.hitRate, 0)}</td>
      <td className="num px-5 py-2 text-right text-ash">{summary.n}</td>
    </tr>
  );
}

/**
 * Does the flow signal predict anything?
 *
 * On demand rather than automatic: this needs five years of history plus the
 * benchmark, and the honest answer is often "no". A result like that should be
 * something the user asked for, not something that ambushes them next to a
 * chart — but it should be one click away, because a signal nobody has ever
 * measured is an assertion, not a finding.
 */
export function EventStudyPanel({
  state, ticker, onValidate,
}: {
  state: Engine<EventStudyResponse>;
  ticker: string;
  onValidate: () => void;
}) {
  if (state.status === "idle") {
    return (
      <Card>
        <CardHeader><CardTitle>Has this signal ever worked?</CardTitle></CardHeader>
        <CardBody className="space-y-3">
          <p className="text-meta leading-relaxed text-ash">
            Measure the cumulative abnormal return after every anomaly detected on{" "}
            <span className="font-mono text-body">{ticker || "this ticker"}</span> over five
            years, against a market model fitted on the 120 trading days ending ten days before
            each event. The answer is frequently that there is no measurable effect — which is
            worth knowing before acting on the panel above.
          </p>
          <ApplyButton onClick={onValidate}>Run the event study</ApplyButton>
        </CardBody>
      </Card>
    );
  }

  if (state.status === "loading") return <Card><PanelSkeleton /></Card>;

  if (state.status === "error") {
    return (
      <Card className="border-dist/40 bg-dist/5">
        <div className="flex gap-3 p-5">
          <AlertTriangle aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-dist" />
          <div>
            <div className="eyebrow mb-1 text-dist">The study could not run</div>
            <p className="text-base leading-relaxed text-body">{state.failure.message}</p>
          </div>
        </div>
      </Card>
    );
  }

  const { study, earningsProximity, benchmark, anomalies, period } = state.data;

  if (!study.usable) {
    return (
      <Card>
        <CardHeader><CardTitle>Signal validation</CardTitle></CardHeader>
        <CardBody>
          <p className="text-base leading-relaxed text-ash">{study.reason}</p>
        </CardBody>
      </Card>
    );
  }

  const headline = study.horizons["20"];
  const anySignificant = Object.values(study.horizons)
    .some((h) => h && h.pValue !== null && h.pValue < 0.05);

  return (
    <div className="space-y-4">
      <Card accent={anySignificant ? (headline && headline.meanCar >= 0 ? UP : DOWN) : undefined}>
        <CardHeader>
          <CardTitle>Abnormal returns after each anomaly</CardTitle>
          <span className="font-mono text-micro text-ash">
            {study.events} of {anomalies} events · {period} · vs {benchmark}
          </span>
        </CardHeader>
        <CardBody className="px-0">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-meta">
              <thead>
                <tr className="eyebrow border-b border-rule [&>th]:px-5 [&>th]:py-2 [&>th]:font-normal">
                  <th>Horizon</th>
                  <th className="text-right">Mean CAR</th>
                  <th className="text-right">Median</th>
                  <th className="text-right">t</th>
                  <th className="text-right">Significance</th>
                  <th className="text-right">Hit rate</th>
                  <th className="text-right">n</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(study.horizons).map(([horizon, summary]) => (
                  <CarRow key={horizon} horizon={horizon} summary={summary} />
                ))}
              </tbody>
            </table>
          </div>

          <div className={cn("mx-5 mt-4 rounded border px-4 py-3 text-meta leading-relaxed",
                             anySignificant
                               ? "border-acc/40 bg-acc/5 text-body"
                               : "border-rule bg-raised/40 text-ash")}>
            {anySignificant
              ? "At least one horizon shows abnormal returns distinguishable from zero at the 5% level. In-sample, on one ticker, with overlapping windows — treat it as a reason to test further, not as a result."
              : "No horizon shows abnormal returns distinguishable from zero. On this ticker, over this window, the anomaly flag does not predict what happens next — which is the most common outcome and the reason this panel exists."}
          </div>
        </CardBody>
      </Card>

      {Object.keys(study.byDirection).length > 0 && (
        <Card>
          <CardHeader><CardTitle>By flow direction</CardTitle></CardHeader>
          <CardBody className="px-0">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-meta">
                <thead>
                  <tr className="eyebrow border-b border-rule [&>th]:px-5 [&>th]:py-2 [&>th]:font-normal">
                    <th>Direction</th><th>Horizon</th>
                    <th className="text-right">Mean CAR</th>
                    <th className="text-right">t</th>
                    <th className="text-right">n</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(study.byDirection).flatMap(([direction, horizons]) =>
                    Object.entries(horizons).map(([horizon, summary]) => (
                      <tr key={`${direction}-${horizon}`}
                          className="border-b border-ruleSoft last:border-0">
                        <td className="px-5 py-2"
                            style={{ color: direction === "Accumulation" ? UP : DOWN }}>
                          {direction}
                        </td>
                        <td className="num px-5 py-2">+{horizon}d</td>
                        <td className={cn("num px-5 py-2 text-right", carTone(summary))}>
                          {summary ? `${summary.meanCar >= 0 ? "+" : ""}${pct(summary.meanCar, 2)}` : "—"}
                        </td>
                        <td className="num px-5 py-2 text-right">
                          {summary?.tStat == null ? "—" : num(summary.tStat)}
                        </td>
                        <td className="num px-5 py-2 text-right text-ash">{summary?.n ?? "—"}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
            <p className="px-5 pt-3 text-meta leading-relaxed text-ash">
              The question that matters is not whether anomalies predict returns, but whether the
              accumulation label predicts something different from the distribution one. If both
              rows look alike, the direction classifier is not carrying information.
            </p>
          </CardBody>
        </Card>
      )}

      {earningsProximity.available && earningsProximity.tagged > 0 && (
        <div className="rounded border border-warn/40 bg-warn/5 px-4 py-3 text-meta leading-relaxed text-warn">
          {earningsProximity.tagged} of {earningsProximity.total} anomalies fall within{" "}
          {earningsProximity.window} days of an earnings release. Those are the market repricing
          an announcement rather than anyone&apos;s footprint, and the drift afterwards is a
          documented effect (Bernard &amp; Thomas 1989) rather than a discovery.
        </div>
      )}

      {study.caveat && (
        <p className="text-meta leading-relaxed text-ash">{study.caveat}</p>
      )}
      {/* HOW THE EVENTS WERE CHOSEN is a different question from how each CAR
          was measured, and only the second was ever disclosed here. The market
          model's estimation window ends before the event; the detector that
          decides which days ARE events is fitted on the whole window. */}
      {study.selectionCaveat && (
        <p className="text-meta leading-relaxed text-ash">{study.selectionCaveat}</p>
      )}
    </div>
  );
}
