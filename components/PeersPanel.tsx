"use client";

import { AlertTriangle, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/input";
import { TONE_HEX, TONE_TEXT } from "@/components/ui/explain";
import type { Engine, PeersResponse } from "@/lib/types";
import { cn, ordinal } from "@/lib/utils";

/**
 * Where this name sits among its own index.
 *
 * WHAT THIS FIXES IS CALIBRATION. Everything else in the single-ticker view is
 * absolute — a 33% worst fall, 28% volatility, 16% a year — and a reader with no
 * priors cannot tell an ordinary number from an alarming one. "Its worst fall
 * was milder than 95% of the Nasdaq-100" is the sentence that reframes it, and
 * the ranking tier already computes everything needed to say it.
 *
 * IT IS A BUTTON, NOT A COLUMN. Placing one name against the Nasdaq-100 means
 * scanning the Nasdaq-100 — roughly six seconds, sharing the ranking tier's
 * per-IP cap. That cost belongs to a reader who asked for it, not to every
 * ticker run.
 *
 * THE BAR IS A POSITION, NOT A SCORE, and the label under it says so. Reading a
 * percentile as a rating is the mistake this panel is most likely to invite, so
 * the group is named in every sentence and the caveat sits with the numbers
 * rather than at the bottom of the card.
 */

function Bar({ percentile, tone }: { percentile: number; tone: string }) {
  return (
    <div className="relative h-1.5 w-full overflow-hidden rounded-full bg-rule">
      <div className="absolute inset-y-0 left-0 rounded-full transition-[width] duration-500"
           style={{ width: `${Math.max(2, Math.min(100, percentile))}%`,
                    background: TONE_HEX[tone] ?? "#7A8CA0" }} />
      {/* The midpoint. Without it a bar is read as "out of 100" rather than as a
          position in a distribution, which is the whole distinction. */}
      <div aria-hidden className="absolute inset-y-0 left-1/2 w-px bg-ink/70" />
    </div>
  );
}

export function PeersPanel({
  state, ticker, onCompare,
}: {
  state: Engine<PeersResponse>;
  ticker: string;
  onCompare: (universe?: string) => void;
}) {
  if (state.status === "idle") {
    return (
      <Card>
        <CardBody className="flex flex-wrap items-center justify-between gap-4 py-4">
          <div className="max-w-xl">
            <div className="eyebrow mb-1 flex items-center gap-1.5">
              <Users aria-hidden className="h-3 w-3" /> Compare with its peers
            </div>
            <p className="text-base leading-relaxed text-ash">
              Every figure on this tab is absolute. Is a 30% fall bad? Is 25% volatility high?
              Placing {ticker || "this name"} against the other companies in its index turns
              those into positions you can read — <span className="text-body">&ldquo;milder
              than 95% of the Nasdaq-100&rdquo;</span> — on the seven price signals the scanner
              already computes.
            </p>
          </div>
          <Button type="button" onClick={() => onCompare()}>Compare with peers</Button>
        </CardBody>
      </Card>
    );
  }

  if (state.status === "loading") {
    return (
      <Card>
        <CardBody className="py-5">
          <div className="eyebrow mb-2 flex items-center gap-1.5">
            <Users aria-hidden className="h-3 w-3" /> Scanning the peer group
          </div>
          <p className="text-base text-ash">
            Downloading a year of history for the whole index. This takes a few seconds &mdash;
            it is one batch request, not one per company.
          </p>
        </CardBody>
      </Card>
    );
  }

  if (state.status === "error") {
    return (
      <Card className="border-warn/40 bg-warn/5">
        <CardBody className="flex gap-3 py-4">
          <AlertTriangle aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-warn" />
          <div>
            <div className="eyebrow mb-1 text-warn">No peer group</div>
            <p className="text-base leading-relaxed text-body">{state.failure.message}</p>
          </div>
        </CardBody>
      </Card>
    );
  }

  const { universe, candidates, rank, explain } = state.data;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Against {universe.name}</CardTitle>
        <div className="flex items-center gap-3">
          {candidates.length > 1 && (
            <Select value={universe.id} aria-label="Peer group" className="h-8"
                    onChange={(e) => onCompare(e.target.value)}>
              {candidates.map((c) => (
                <option key={c.id} value={c.id}>{c.name} ({c.count})</option>
              ))}
            </Select>
          )}
          <span className="num text-meta text-ash">
            {universe.scanned} ranked &middot; list as of {universe.asOf}
          </span>
        </div>
      </CardHeader>

      <CardBody className="space-y-4">
        <p className="text-base leading-relaxed text-body">{explain.headline}</p>

        <div className="space-y-3">
          {explain.readings.map((r) => (
            <div key={r.key}>
              <div className="mb-1 flex items-baseline justify-between gap-3">
                <span className="text-meta text-ash">{r.label}</span>
                <span className="num text-micro text-ash">
                  {r.rawText ?? ""}
                  {r.percentile != null && (
                    <span className={cn("ml-2 font-semibold", TONE_TEXT[r.tone])}>
                      {Math.round(r.percentile)}
                      <span className="text-ash">{ordinal(r.percentile)}</span>
                    </span>
                  )}
                </span>
              </div>
              {r.percentile != null
                ? <Bar percentile={r.percentile} tone={r.tone} />
                : <div className="h-1.5 w-full rounded-full bg-rule/50" />}
              <p className={cn("mt-1 text-meta leading-relaxed",
                               r.percentile == null ? "text-ash" : "text-body")}>
                {r.sentence}
              </p>
            </div>
          ))}
        </div>

        {explain.overlap && (
          <p className="border-t border-rule pt-3 text-meta leading-relaxed text-warn/90">
            {explain.overlap}
          </p>
        )}

        <p className="text-meta leading-relaxed text-ash">{explain.caveat}</p>

        {rank == null && (
          <p className="text-micro text-ash">
            No combined placing: too many of the seven signals were unavailable for this name.
          </p>
        )}
      </CardBody>
    </Card>
  );
}
