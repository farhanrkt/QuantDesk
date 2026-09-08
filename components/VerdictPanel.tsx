"use client";

import { AlertTriangle, Gauge, Lock, ShieldAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle, Explainer, Note } from "@/components/ui/card";
import { TONE_FIELD, TONE_HEX } from "@/components/ui/explain";
import type { Engine, VerdictComponent, VerdictResponse } from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * One score and one action for this name — the private scanner, in the app.
 *
 * THIS IS THE COMPOSITE THE REST OF THIS APP REFUSES, AND THE REFUSAL STILL
 * STANDS. The confluence rail, the synthesis and the pre-trade panel aggregate
 * nothing and are unchanged; a pytest asserts by AST that neither `explain` nor
 * `pretrade` can even import the module behind this one. What changed is that
 * the owner asked a second question — "of a whole market, what deserves my
 * attention" — which cannot be answered without ordering. `PRODUCT.md`
 * constraint 1 records the scoping in full.
 *
 * FOUR THINGS THIS PANEL WILL NOT DO, each of which it would be easy to.
 *
 * 1. IT NEVER SHOWS THE SCORE WITHOUT THE MEASUREMENT THAT CALIBRATES IT. The
 *    null result — this app's own backtest found no detectable relationship
 *    between its price ranking and subsequent returns — renders ABOVE the
 *    number, not under it. Reading order is the argument: the figure means
 *    something different depending on that paragraph.
 *
 * 2. IT NEVER HIDES A GATE BEHIND A GOOD SCORE. A name below the turnover floor
 *    reads NO ACTION with its score still on screen, because a reader
 *    overriding a gate has to be able to see what they are overriding.
 *
 * 3. IT NEVER LETS A MISSING LENS LOOK LIKE A NEUTRAL ONE. A component that did
 *    not read is struck from the blend and says so in the same row where a score
 *    would have been. An empty component is not a 50.
 *
 * 4. IT NEVER COLOURS FROM A NUMBER. Every tone here is `data.tone` or a
 *    component's own `available` flag — the server decided direction once, and
 *    this file does not re-decide it.
 */

const ACTION_NOTE: Record<string, string> = {
  STRONG_BUY: "Both bodies of data read constructively and every component was available.",
  BUY: "The evidence leans constructive, with something missing or something disagreeing.",
  HOLD: "Nothing here argues strongly either way once the gaps are accounted for.",
  REDUCE: "The evidence leans against it.",
  AVOID: "The evidence leans against it, or a gate capped it here.",
  NO_ACTION: "A gate fired. This is not a judgement about the company.",
};

const FAMILY_WORD: Record<string, string> = {
  price: "price and volume",
  filings: "the filings",
};

/** Ends a server-supplied clause so it can be followed by another sentence. */
function sentence(text: string | null): string {
  const trimmed = (text ?? "").trim();
  if (!trimmed) return "";
  return /[.!?]$/.test(trimmed) ? trimmed : `${trimmed}.`;
}

function ComponentRow({ item }: { item: VerdictComponent }) {
  const hue = item.family === "price" ? "#6B9BFF" : "#E8B44C";
  return (
    <div className="border-t border-ruleSoft py-3 first:border-t-0">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <span className="text-base font-medium text-chalk">{item.label}</span>
        {item.available && item.score !== null ? (
          <span className="tabular-nums text-base text-chalk">{item.score.toFixed(0)}</span>
        ) : (
          <span className="text-meta italic text-faint">
            {item.refused ? "refused" : "not read"}
          </span>
        )}
      </div>
      <div className="eyebrow mt-1">
        {FAMILY_WORD[item.family]} &middot; {item.evidence} evidence &middot;
        {" "}weight {item.baseWeight.toFixed(1)}
      </div>
      {item.available && item.score !== null && (
        <div className="relative mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-rule">
          <div className="absolute inset-y-0 left-0 rounded-full transition-[width] duration-500"
               style={{ width: `${Math.max(2, Math.min(100, item.score))}%`, background: hue }} />
          <div aria-hidden className="absolute inset-y-0 left-1/2 w-px bg-ink/70" />
        </div>
      )}
      <p className="prose-col mt-2 text-meta leading-relaxed text-ash">
        {/* The server's reasons are written as clauses, not sentences, because
            `verdict._reasons` punctuates them itself when it assembles the
            list. Here they are followed by another sentence, so the full stop
            has to be added — without it the two run together mid-word. */}
        {item.available ? item.reading : sentence(item.reason)}
        {!item.available && (
          <span className="text-faint">
            {" "}Its weight was removed from the blend rather than filled in.
          </span>
        )}
      </p>
    </div>
  );
}

export function VerdictPanel({
  state, ticker, onScore,
}: {
  state: Engine<VerdictResponse>;
  ticker: string;
  onScore: () => void;
}) {
  if (state.status === "idle") {
    return (
      <Card>
        <CardBody className="flex flex-wrap items-center justify-between gap-4 py-4">
          <div className="max-w-xl">
            <div className="eyebrow mb-1 flex items-center gap-1.5">
              <Gauge aria-hidden className="h-3 w-3" /> Score this name
            </div>
            <p className="text-base leading-relaxed text-ash">
              Everything else on this page describes {ticker || "this name"} and stops
              there, on purpose. This does the other thing: blends all five readings into
              one score and one action, the way the market scanner ranks a whole exchange.
              It costs a universe scan plus four lenses, about eight seconds, and it
              arrives with the measurement of whether any of it predicts anything.
            </p>
          </div>
          <Button type="button" onClick={onScore}>Score it</Button>
        </CardBody>
      </Card>
    );
  }

  if (state.status === "loading") {
    return (
      <Card>
        <CardBody className="py-5">
          <div className="eyebrow mb-2 flex items-center gap-1.5">
            <Gauge aria-hidden className="h-3 w-3" /> Scoring
          </div>
          <p className="text-base text-ash">
            Ranking the peer universe, then running all four lenses on {ticker}.
          </p>
        </CardBody>
      </Card>
    );
  }

  if (state.status === "error") {
    return (
      <Card tone="warn">
        <CardBody className="py-5">
          <div className="mb-1 flex items-center gap-2 text-warn">
            <AlertTriangle aria-hidden className="h-4 w-4" />
            <span className="text-base font-semibold">Could not score {ticker}</span>
          </div>
          <p className="text-base text-ash">{state.failure.message}</p>
        </CardBody>
      </Card>
    );
  }

  const data = state.data;
  const gated = data.gates.length > 0;

  return (
    <div className="space-y-4">
      {/* THE MEASUREMENT COMES FIRST. Not a footnote under the number — the
          number means something different depending on this paragraph, so it
          cannot come after it. */}
      <Card tone="warn">
        <CardBody className="py-4">
          <div className="eyebrow mb-1.5 flex items-center gap-1.5 text-warn">
            <ShieldAlert aria-hidden className="h-3 w-3" />
            What this score is worth — read before the number
          </div>
          <p className="prose-col text-base leading-relaxed text-body">
            {data.provenance.headline}
          </p>
          {data.provenance.appliesTo && (
            <p className="prose-col mt-2 text-meta leading-relaxed text-ash">
              That measurement applies to {data.provenance.appliesTo}
            </p>
          )}
        </CardBody>
      </Card>

      <Card tone={data.tone}>
        <CardHeader>
          <CardTitle>{data.name === data.ticker ? data.ticker : data.name}</CardTitle>
          <span className={cn("rounded-full border px-2.5 py-1 text-meta font-semibold",
                              TONE_FIELD[data.tone] ?? TONE_FIELD.none)}>
            {data.actionLabel}
          </span>
        </CardHeader>
        <CardBody>
          <div className="flex flex-wrap items-end gap-x-8 gap-y-4">
            <div>
              <div className="eyebrow mb-1">Score</div>
              <div className="text-figure font-semibold tabular-nums"
                   style={{ color: TONE_HEX[data.tone] ?? "#8496A9" }}>
                {data.score === null ? "—" : data.score.toFixed(1)}
              </div>
            </div>
            <div>
              <div className="eyebrow mb-1">Conviction</div>
              <div className={cn("text-lead font-medium",
                                 data.conviction === "high" ? "text-acc"
                                   : data.conviction === "low" ? "text-warn" : "text-ash")}>
                {data.conviction}
              </div>
            </div>
            <div>
              <div className="eyebrow mb-1">Cross-check</div>
              <div className={cn("text-lead font-medium",
                                 data.crossChecked ? "text-ash" : "text-warn")}>
                {data.crossChecked ? "both" : "one lens only"}
              </div>
            </div>
            <div>
              <div className="eyebrow mb-1">Coverage</div>
              <div className="text-lead font-medium tabular-nums text-ash">
                {(data.coverage * 100).toFixed(0)}%
              </div>
            </div>
            {data.sizing.applicable && data.sizing.weight !== undefined && (
              <div>
                <div className="eyebrow mb-1">Mechanical size</div>
                <div className="text-lead font-medium tabular-nums text-ash">
                  {(data.sizing.weight * 100).toFixed(1)}%
                </div>
              </div>
            )}
          </div>

          <p className="prose-col mt-4 text-base leading-relaxed text-body">
            {ACTION_NOTE[data.action]}
          </p>

          {!data.crossChecked && (
            <Note tone="warn">
              Only one body of data returned a reading, so nothing cross-checked this
              score. That is the situation this app exists to avoid, and it is why the
              blend was pulled toward neutral rather than reported as it stood.
            </Note>
          )}
        </CardBody>
      </Card>

      {gated && (
        <Card tone="bad">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Lock aria-hidden className="h-4 w-4" />
              {data.gates.length === 1 ? "A gate fired" : `${data.gates.length} gates fired`}
            </CardTitle>
          </CardHeader>
          <CardBody className="space-y-3">
            <p className="prose-col text-meta leading-relaxed text-ash">
              A gate is a fact about the order book or the balance sheet, not a judgement
              about the company, and no amount of good signal overrides one. The score
              above is still shown so you can see what you would be overriding.
            </p>
            {data.gates.map((gate) => (
              <div key={gate.id}>
                <div className="text-base font-medium text-chalk">{gate.label}</div>
                <p className="prose-col mt-1 text-meta leading-relaxed text-ash">
                  {gate.detail}
                </p>
              </div>
            ))}
          </CardBody>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>How the score was built</CardTitle>
          <span className="text-meta text-faint">
            {data.componentsRead} of {data.componentsTotal} components read
          </span>
        </CardHeader>
        <CardBody className="px-5 py-2">
          {data.components.map((item) => <ComponentRow key={item.key} item={item} />)}
        </CardBody>
      </Card>

      <Card>
        <CardBody className="space-y-3">
          <div>
            <div className="eyebrow mb-1">The cross-check</div>
            <p className="prose-col text-base leading-relaxed text-body">
              {data.agreement.text}
            </p>
          </div>
          <div>
            <div className="eyebrow mb-1">The arithmetic</div>
            <p className="prose-col text-meta leading-relaxed text-ash">
              {data.shrink.text}
            </p>
          </div>

          {data.penalties.length > 0 && (
            <div>
              <div className="eyebrow mb-1">Pre-trade flags that cost points</div>
              {data.penalties.map((penalty) => (
                <div key={penalty.id}
                     className="flex items-start justify-between gap-4 py-1.5">
                  <span className="text-meta text-ash">
                    <span className="text-body">{penalty.label}.</span> {penalty.why}
                  </span>
                  <span className="shrink-0 tabular-nums text-meta font-semibold text-dist">
                    -{penalty.points.toFixed(1)}
                  </span>
                </div>
              ))}
              {data.penaltyCapped && (
                <Note>
                  The total is capped: flags are correlated, and an uncapped sum would
                  count one underlying fact several times.
                </Note>
              )}
            </div>
          )}

          {data.sizing.applicable && data.sizing.basis && (
            <div>
              <div className="eyebrow mb-1">Where the size came from</div>
              <p className="prose-col text-meta leading-relaxed text-ash">
                {data.sizing.basis}
              </p>
            </div>
          )}

          <Explainer summary="Every reason, in order of how much it moved the score">
            <ul className="list-disc space-y-1.5 pl-4">
              {data.reasons.map((reason, i) => <li key={i}>{reason}</li>)}
            </ul>
          </Explainer>

          {data.universe && (
            <Note>
              Ranked against {data.universe.name} ({data.universe.scanned} of{" "}
              {data.universe.count} scanned, list as of {data.universe.asOf}). Change the
              group and the same company moves &mdash; a percentile is a claim about one
              universe on one date.
            </Note>
          )}

          <Note tone="warn">{data.caveat}</Note>
        </CardBody>
      </Card>
    </div>
  );
}
