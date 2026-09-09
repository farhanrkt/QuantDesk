"use client";

import {
  AlertTriangle, Coins, Crosshair, FlaskConical, Gauge, Lock, Shapes, ShieldAlert,
  TrendingDown, Users, Waves,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle, Explainer, Note } from "@/components/ui/card";
import { TONE_FIELD, TONE_HEX } from "@/components/ui/explain";
import type {
  BlendBacktest, Engine, RoundTripCost, TapeCalibration, VerdictComponent,
  VerdictPatterns, VerdictRegister, VerdictResponse, VerdictStructure, VerdictTape,
} from "@/lib/types";
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
  STRONG_BUY: "At least two independent bodies of data read constructively, none "
    + "contradicted them, and the components were substantially complete.",
  BUY: "The evidence leans constructive, with something missing or something disagreeing.",
  HOLD: "Nothing here argues strongly either way once the gaps are accounted for.",
  REDUCE: "The evidence leans against it.",
  AVOID: "The evidence leans against it, or a gate capped it here.",
  NO_ACTION: "A gate fired. This is not a judgement about the company.",
};

const FAMILY_WORD: Record<string, string> = {
  price: "price and volume",
  filings: "the filings",
  register: "the share register",
};

// Identity, never judgement — the same rule the lens hues follow. A family is
// its colour whether its reading is excellent or terrible.
const FAMILY_HUE: Record<string, string> = {
  price: "#6B9BFF",
  filings: "#E8B44C",
  register: "#A78BFA",
};

/** Ends a server-supplied clause so it can be followed by another sentence. */
function sentence(text: string | null): string {
  const trimmed = (text ?? "").trim();
  if (!trimmed) return "";
  return /[.!?]$/.test(trimmed) ? trimmed : `${trimmed}.`;
}

function ComponentRow({ item }: { item: VerdictComponent }) {
  const hue = FAMILY_HUE[item.family] ?? "#8496A9";
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

/**
 * The heavy-session reading, and the three things it is not.
 *
 * THE REFUSAL IS THE POINT OF THIS BLOCK. The reader asked for bandarmology and
 * this is not bandarmology: the method is defined by the exchange's broker
 * summary, which names the accumulating desk and splits foreign from domestic,
 * and no provider this app can reach carries it. What renders here is the OHLCV
 * shadow of one question that method asks. Saying so in the panel rather than
 * only in a docstring is the difference between a tool that is honest and one
 * that is honest where nobody looks.
 *
 * The market-wide firing rate renders beside the verdict for the same reason
 * the backtest null renders above the score: on US listings the test fires at
 * chance, so a US accumulation reading means nothing, and a reader must not
 * have to go looking for that.
 */
function TapeReading({ tape, calibration }: {
  tape: VerdictTape;
  calibration: TapeCalibration | null;
}) {
  const concentration = tape.concentration;
  const chanceRate = tape.alpha ?? 0.05;
  const measured = calibration?.significantShare ?? null;
  const atChance = measured !== null && measured <= chanceRate * 1.5;

  return (
    <div>
      <div className="eyebrow mb-1 flex items-center gap-1.5">
        <Waves aria-hidden className="h-3 w-3" /> Who wins the heavy days
      </div>
      <p className="prose-col text-meta leading-relaxed text-ash">{tape.reading}</p>

      {concentration?.available && concentration.topFiveShare !== null && (
        <p className="prose-col mt-1.5 text-meta leading-relaxed text-ash">
          {(concentration.topFiveShare * 100).toFixed(0)}% of the year&rsquo;s volume
          traded on its five biggest sessions
          {concentration.effectiveDays !== null &&
            `, making the window worth about ${concentration.effectiveDays.toFixed(0)} sessions of even trading`}
          . Reported and never scored: a year that happened in five sessions is not
          thereby good or bad, it is unsizeable.
        </p>
      )}

      {measured !== null && (
        <p className={cn("prose-col mt-1.5 text-meta leading-relaxed",
                         atChance ? "text-warn" : "text-faint")}>
          Across {calibration?.names} names in {calibration?.population}, this test fires
          on {(measured * 100).toFixed(0)}% against {(chanceRate * 100).toFixed(0)}%
          expected by chance
          {atChance
            ? " — which is chance. In this market the reading above is measuring nothing, and no accumulation verdict should be taken from it."
            : ` — so roughly ${Math.max(0, Math.round((1 - chanceRate / measured) * 100))}% of the names that fire are real and the rest are noise, with no way to tell which is which.`}
        </p>
      )}

      <p className="prose-col mt-1.5 text-meta leading-relaxed text-faint">
        {tape.missing}
      </p>
    </div>
  );
}

/**
 * The share register: how much is actually for sale, and whether the count of
 * shares keeps going up.
 *
 * Institutional ownership renders here and never as a component. "Somebody
 * professional owns this" is an argument from authority, and the holders are
 * mostly index funds with no view on the company at all.
 */
function RegisterReading({ register }: { register: VerdictRegister }) {
  const institutions = register.institutions;

  return (
    <div>
      <div className="eyebrow mb-1 flex items-center gap-1.5">
        <Users aria-hidden className="h-3 w-3" /> The share register
      </div>
      <p className="prose-col text-meta leading-relaxed text-ash">{register.reading}</p>

      {/* The turnover sentence lives in `register.reading`, which the server
          assembles. Repeating it here printed it twice on every name that had
          one — the same duplication the reasons list already had to drop. */}
      {register.earnings?.available && register.earnings.soon && (
        <p className="prose-col mt-1.5 text-meta leading-relaxed text-warn">
          {register.earnings.reading}
        </p>
      )}

      {institutions && institutions.percentHeld !== null && (
        <p className="prose-col mt-1.5 text-meta leading-relaxed text-faint">
          {(institutions.percentHeld * 100).toFixed(1)}% sits with
          {institutions.count !== null ? ` ${institutions.count.toFixed(0)}` : ""}{" "}
          institutions. {institutions.note}
        </p>
      )}
    </div>
  );
}

/**
 * Where the trade is wrong — the entry, as distinct from the asset.
 *
 * IT IS NOT A COMPONENT AND MUST NOT BECOME ONE. The score answers "is this
 * worth owning"; this answers "is now a sensible moment, and where would I be
 * wrong". Blending them would let a tidy entry make a poor company look better,
 * which is the confusion a composite is most prone to — so this renders beside
 * the score and feeds only a gate.
 */
function EntryReading({ site }: { site: VerdictStructure }) {
  const band = site.band;
  const alarming = band === "bad" || band === "poor" || band === "riskTooWide";
  return (
    <div>
      <div className="eyebrow mb-1 flex items-center gap-1.5">
        <Crosshair aria-hidden className="h-3 w-3" /> Where the trade is wrong
      </div>
      <p className={cn("prose-col text-meta leading-relaxed",
                       alarming ? "text-warn" : "text-ash")}>
        {site.reading}
      </p>
      {site.rewardRisk !== null && site.rewardRisk !== undefined && (
        <p className="prose-col mt-1.5 text-meta leading-relaxed text-faint">
          Reward to risk against structure: {site.rewardRisk.toFixed(2)} to 1. Measured to
          the nearest level either side, never to a target chosen to make the ratio look
          better — and it is not a forecast, only a description of what is in front of it.
        </p>
      )}
    </div>
  );
}

/**
 * What one buy and one sell cost, beside the effects the page asks you to act
 * on. The measured effects in this app are a few percent; a round trip on a
 * thin listing can be more than that, and a gross number presented as though it
 * were net is the quietest way to mislead somebody.
 */
function CostReading({ costs }: { costs: RoundTripCost }) {
  return (
    <div>
      <div className="eyebrow mb-1 flex items-center gap-1.5">
        <Coins aria-hidden className="h-3 w-3" /> What a round trip costs
      </div>
      <p className="prose-col text-meta leading-relaxed text-ash">
        {costs.available ? costs.reading : costs.reason}
      </p>
    </div>
  );
}

/**
 * Chart formations, and the measurement that decides whether they count.
 *
 * THE SENTENCE THIS BLOCK EXISTS FOR is the one about the sign. On both markets
 * measured, every formation that survived a false-discovery correction
 * predicted UNDERperformance — a head-and-shoulders and its bullish mirror image
 * measured the same. A reader who has seen a chart book will expect the
 * opposite, and the panel has to say so rather than let the number pass.
 */
function PatternReading({ patterns }: { patterns: VerdictPatterns }) {
  const found = patterns.detections ?? [];
  const labels = Array.from(new Set(found.map((d) => d.label))).sort();

  return (
    <div>
      <div className="eyebrow mb-1 flex items-center gap-1.5">
        <Shapes aria-hidden className="h-3 w-3" /> Chart formations
      </div>
      <p className="prose-col text-meta leading-relaxed text-ash">{patterns.reading}</p>

      {labels.length > 0 && (
        <div className="mt-2 space-y-1.5">
          {found.map((detection, i) => (
            <div key={`${detection.pattern}-${i}`}
                 className="flex flex-wrap items-baseline justify-between gap-x-3">
              <span className="text-meta text-body">
                {detection.label}
                <span className="text-faint"> completed {detection.completedAt}</span>
              </span>
              <span className="text-meta text-faint">
                {detection.significant && detection.forward
                  ? `${(detection.forward.meanExcess * 100).toFixed(1)}% over ${detection.forward.horizonDays}d`
                  : "measured null"}
              </span>
            </div>
          ))}
        </div>
      )}

      {(patterns.refused ?? []).length > 0 && (
        <p className="prose-col mt-2 text-meta leading-relaxed text-faint">
          Still refused, by name: {(patterns.refused ?? []).map((r) => r.name).join(", ")}.
          None has a numeric definition that survives two stocks of different volatility.
        </p>
      )}
    </div>
  );
}

/**
 * The measurement that is about THIS score rather than one of its components.
 *
 * The provenance block below covers the seven-signal price composite. This
 * covers the blend — and covers less than half of it, because five of the nine
 * components cannot be reconstructed on a past date without reading filings
 * published years later. The coverage is stated as a percentage rather than
 * implied, and where a surviving coefficient is contradicted by its own
 * quintile spread the panel says so: a rank correlation that lives in the
 * middle of the distribution while the extremes go the other way is not a
 * finding anybody can act on.
 */
function BlendReading({ blend }: { blend: BlendBacktest }) {
  if (!blend.available) {
    return (
      <Card tone="warn">
        <CardBody className="py-3">
          <div className="eyebrow mb-1 text-warn">The blend has not been backtested</div>
          <p className="prose-col text-meta leading-relaxed text-body">
            {blend.reason} Until it has, the score below is an ordering of evidence with
            no established relationship to returns.
          </p>
        </CardBody>
      </Card>
    );
  }

  const contradicted = (blend.contradicted ?? 0) > 0;
  return (
    <Card>
      <CardBody className="py-3">
        <div className="eyebrow mb-1 flex items-center gap-1.5">
          <FlaskConical aria-hidden className="h-3 w-3" />
          And what the blend is worth — measured on{" "}
          {((blend.coverage ?? 0) * 100).toFixed(0)}% of it
        </div>
        <p className="prose-col text-meta leading-relaxed text-body">{blend.headline}</p>
        {blend.medianRoundTrip !== null && blend.medianRoundTrip !== undefined && (
          <p className="prose-col mt-1.5 text-meta leading-relaxed text-faint">
            A quintile spread is gross. The spread estimator resolved for only{" "}
            {blend.roundTripResolved} of {blend.roundTripAttempted} names — it clears its
            own noise floor on the widest spreads and almost nowhere else — so the{" "}
            {(blend.medianRoundTrip * 100).toFixed(2)}% median of those is an upper bound
            on a typical cost, not a measurement of one. Each result carries the round
            trip at which it reaches zero; compare that against your own dealing costs.
          </p>
        )}

        {contradicted && (
          <p className="prose-col mt-1.5 text-meta leading-relaxed text-warn">
            One surviving result is contradicted by its own quintile spread — the rank
            correlation and the top-minus-bottom gap point opposite ways, so the
            relationship is not monotone and the extremes, which are the only part
            anybody would act on, go the other way.
          </p>
        )}
        {blend.excluded && (
          <Explainer summary={`Why ${Object.keys(blend.excluded).length} of the nine could not be measured at all`}>
            <ul className="list-disc space-y-1.5 pl-4">
              {Object.entries(blend.excluded).map(([key, reason]) => (
                <li key={key}><span className="text-body">{key}</span> — {reason}</li>
              ))}
            </ul>
          </Explainer>
        )}
      </CardBody>
    </Card>
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
      {data.blendBacktest && <BlendReading blend={data.blendBacktest} />}

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

      {data.regime?.available && (
        <Card>
          <CardBody className="py-3">
            <div className="eyebrow mb-1 flex items-center gap-1.5">
              <TrendingDown aria-hidden className="h-3 w-3" />
              The market this reading was taken in &mdash; {data.regime.state}
            </div>
            <p className="prose-col text-meta leading-relaxed text-ash">
              {data.regime.reading}
            </p>
          </CardBody>
        </Card>
      )}

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

          {data.structure?.available && <EntryReading site={data.structure} />}
          {data.costs && <CostReading costs={data.costs} />}
          {data.patterns?.available && <PatternReading patterns={data.patterns} />}
          {data.tape?.available && <TapeReading tape={data.tape}
                                                calibration={data.tapeCalibration} />}
          {data.register?.available && <RegisterReading register={data.register} />}

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
