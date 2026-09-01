"use client";

import { Card, CardBody, CardHeader, CardTitle, Note, Section } from "@/components/ui/card";
import { Explain, ExplainedStat } from "@/components/ui/explain";
import type { Engine, ExpectationsResponse } from "@/lib/types";
import { signedPct } from "@/lib/utils";

const HUE = "#E07AC0";

/**
 * THE REFUSAL, AND WHY IT GETS A WHOLE CARD RATHER THAN A GREY DASH.
 *
 * A listing nobody covers is the most common outcome this lens has — analyst
 * coverage is precisely where smaller names stop being followed — and it is the
 * single easiest state in this app to misread as reassurance. "No cuts" and
 * "nobody watching" occupy the same blank space on a screen.
 *
 * So the empty state is louder than the populated one: it says in words that
 * this is a gap in coverage rather than a clean bill of health, and it does not
 * render a grid of greyed-out metrics that would read as "we tried and the
 * numbers came back fine".
 */
function NotCovered({ data }: { data: ExpectationsResponse }) {
  return (
    <Card accent={HUE}>
      <CardHeader hue={HUE}>
        <CardTitle hue={HUE}>No consensus to read</CardTitle>
        <span className="font-mono text-micro text-ash">
          {data.analysts ?? 0} analyst{data.analysts === 1 ? "" : "s"}
        </span>
      </CardHeader>
      <CardBody className="space-y-3">
        <p className="prose-col text-base leading-relaxed text-chalk">{data.headline}</p>
        <Note tone="warn">{data.refusal}</Note>
      </CardBody>
    </Card>
  );
}

/**
 * The beat-and-miss record, as a table rather than a score.
 *
 * DELIBERATELY UNCOLOURED, every row. A beat is a fact about the relationship
 * between two numbers and its sign is not the company's direction: a firm that
 * beats four quarters running while its consensus is cut all year is a
 * deteriorating business that manages expectations well, and the beats are the
 * mechanism of that rather than evidence against it. Colouring the surprises
 * green would let that company's record outvote its own estimate record, which
 * is exactly what the Python refuses to do by giving this a `context` band.
 */
function SurpriseTable({ data }: { data: ExpectationsResponse }) {
  const record = data.surprise;
  if (!record?.available || !record.quarters?.length) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Reported against expected</CardTitle>
        <span className="flex items-center gap-1.5 font-mono text-micro text-ash">
          {record.beats} of {record.reported} above
          <Explain explain={data.explain?.earningsSurprise} />
        </span>
      </CardHeader>
      <CardBody className="px-0 py-0">
        <table className="w-full text-meta">
          <caption className="sr-only">
            Quarterly reported earnings per share against the analyst estimate
          </caption>
          <thead>
            <tr className="border-b border-rule text-ash">
              <th scope="col" className="px-5 py-2 text-left font-medium">Quarter</th>
              <th scope="col" className="px-5 py-2 text-right font-medium">Expected</th>
              <th scope="col" className="px-5 py-2 text-right font-medium">Reported</th>
              <th scope="col" className="px-5 py-2 text-right font-medium">Difference</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-ruleSoft">
            {record.quarters.map((q) => (
              <tr key={q.quarter}>
                <th scope="row" className="px-5 py-2.5 text-left font-normal text-body">
                  {q.quarter}
                </th>
                <td className="num px-5 py-2.5 text-right text-ash">
                  {q.estimate == null ? "—" : q.estimate.toLocaleString(undefined,
                    { maximumFractionDigits: 4 })}
                </td>
                <td className="num px-5 py-2.5 text-right text-body">
                  {q.actual == null ? "—" : q.actual.toLocaleString(undefined,
                    { maximumFractionDigits: 4 })}
                </td>
                {/* text-body, NOT a tone. See the component docstring. */}
                <td className="num px-5 py-2.5 text-right text-body">
                  {q.surprise == null ? "—" : signedPct(q.surprise, 1)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardBody>
    </Card>
  );
}

/**
 * What this app measured about its own signal — and it came back a null.
 *
 * THIS CARD IS NEVER COLOURED, for the reason §8 gives about provenance and §15
 * about the kappa: a measurement of whether the SIGNAL works is not good or bad
 * news about the COMPANY. It would read identically on a wonderful business and
 * a failing one, and tinting it would turn "we could not show this predicts
 * anything" into a verdict on the stock in front of the reader.
 *
 * It renders the LIMIT as prominently as the result. A single-window
 * cross-section reported without it reads as a backtest, and this app does not
 * have one for this signal — the source serves no history of the quantity that
 * votes.
 */
function SignalMeasurement({ data }: { data: ExpectationsResponse }) {
  const m = data.measurement;
  if (!m) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Has this signal ever worked?</CardTitle>
        </CardHeader>
        <CardBody>
          <Note tone="warn">
            Nobody has measured it. The offline study that would answer this has not
            been run, so the revision reading above rests on the published literature
            and nothing this app has checked itself.
          </Note>
        </CardBody>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Has this signal ever worked?</CardTitle>
        <span className="font-mono text-micro text-ash">measured {m.measuredOn}</span>
      </CardHeader>
      <CardBody className="space-y-3">
        <p className="prose-col text-base leading-relaxed text-chalk">{m.reading}</p>
        <Note>{m.limit}</Note>
        {m.bridge?.usable && (
          <Note>
            The forward test above used the estimate level, because the count of
            analysts that decides the verdict has no history anywhere in the source.
            Across {m.bridge.n} names the two move together
            (rho = {m.bridge.rho.toFixed(2)}), which is what makes the level a usable
            stand-in for the count — and what makes the null above a null about the
            verdict rather than about the wrong quantity.
          </Note>
        )}
      </CardBody>
    </Card>
  );
}

/**
 * The estimate record — the fifth lens, and the only one reading a body of data
 * neither the price history nor the filings can supply.
 *
 * WHAT IS ABSENT HERE, DELIBERATELY: the mean price target. It is fetched, and
 * it is the one figure in this whole app that is simultaneously a point forecast
 * of a price, unattached to any stated method, and published by people with a
 * commercial relationship to the company being forecast. The SPREAD is shown
 * instead, because disagreement survives the objection that the level does not.
 */
export function ExpectationsPanel({ state }: { state: Engine<ExpectationsResponse> }) {
  if (state.status === "idle") return null;
  if (state.status === "loading") {
    return (
      <Section title="What does everyone else expect?"
               question="Reading the analyst estimate record…">
        <Card><CardBody><p className="text-meta text-ash">Running…</p></CardBody></Card>
      </Section>
    );
  }
  if (state.status === "error") {
    return (
      <Section title="What does everyone else expect?">
        <Card tone="warn">
          <CardBody>
            <Note tone="warn">
              The expectations lens did not run: {state.failure.message} Nothing on
              this tab is a reading about the company — it is a failed fetch, which is
              not the same as an absent consensus.
            </Note>
          </CardBody>
        </Card>
      </Section>
    );
  }

  const data = state.data;
  const ex = data.explain;

  return (
    <Section
      title="What does everyone else expect?"
      question="The analysts covering this company, and which way they have been moving
                their forecasts. The only lens here that reads neither the price history
                nor the filings."
    >
      {!data.applicable ? (
        <div className="space-y-4">
          <NotCovered data={data} />
          <SignalMeasurement data={data} />
        </div>
      ) : (
        <div className="space-y-4">
          <Card accent={HUE} tone={data.tone}>
            <CardHeader hue={HUE}>
              <CardTitle hue={HUE}>{verdictWord(data.verdict)}</CardTitle>
              <span className="font-mono text-micro text-ash">
                {data.analysts} analysts covering
              </span>
            </CardHeader>
            <CardBody>
              <p className="prose-col text-base leading-relaxed text-chalk">
                {data.headline}
              </p>
            </CardBody>
          </Card>

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <ExplainedStat explain={ex?.revisionBreadth} />
            <ExplainedStat explain={ex?.revisionDrift} />
            <ExplainedStat explain={ex?.analystCoverage} />
            <ExplainedStat explain={ex?.consensusGrowth} />
            <ExplainedStat explain={ex?.targetDispersion} />
            {/* NO SURPRISE TILE HERE. The table below is the same fact with the
                same info icon, and a tile above it made the panel state the
                beat record twice in half a screen — the doubling the v2 pass
                spent two commits removing everywhere else. */}
          </div>

          <SurpriseTable data={data} />
          <SignalMeasurement data={data} />

          {/* THE TWO HAZARDS, FROM THE PAYLOAD. They live in Python so a redesign
              of this component cannot drop them: the first says an estimate is an
              opinion, the second says why the VERDICT is taken from a count of
              analysts rather than from the forecast level a reader can see move. */}
          {data.limits?.length ? (
            <Card surface="sunken">
              <CardBody className="space-y-2">
                {data.limits.map((line) => <Note key={line}>{line}</Note>)}
              </CardBody>
            </Card>
          ) : null}
        </div>
      )}
    </Section>
  );
}

/** The server's verdict enum, as the word the panel shows. Never re-derived. */
function verdictWord(verdict: ExpectationsResponse["verdict"]): string {
  switch (verdict) {
    case "RISING": return "The forecasts are being raised";
    case "FALLING": return "The forecasts are being cut";
    case "QUIET": return "Nobody has moved a number";
    case "THIN": return "Too few analysts moved to read a direction";
    case "MIXED": return "Revisions have gone both ways";
    default: return "No revision record";
  }
}

/** Exported for the tab accent, so the tab and the rail chip share one hex. */
export const EXPECTATIONS_HUE = HUE;
