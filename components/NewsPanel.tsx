"use client";

import { ExternalLink } from "lucide-react";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import type { Engine, NewsResponse } from "@/lib/types";

/**
 * Contextual catalyst — the headline panel from the Whale Tracker app.
 *
 * Everything here is third-party text fetched from a public feed. It is
 * rendered as data and nothing else: titles go through React's own escaping,
 * links open in a new tab with `rel="noopener noreferrer"`, and no part of the
 * app reads this content back as instructions.
 */
export function NewsPanel({ state }: { state: Engine<NewsResponse> }) {
  if (state.status !== "ready" || state.data.items.length === 0) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Contextual catalyst</CardTitle>
        <span className="font-mono text-[0.65rem] text-ash">Google News · {state.data.ticker}</span>
      </CardHeader>
      <CardBody className="px-0">
        <ul>
          {state.data.items.map((item, i) => (
            <li key={i} className="border-b border-rule/60 px-5 py-2.5 last:border-0">
              <div className="flex items-baseline gap-2">
                <span className="shrink-0 font-mono text-[0.62rem] uppercase tracking-[0.08em] text-ash">
                  {item.source}
                </span>
                {item.link ? (
                  <a href={item.link} target="_blank" rel="noopener noreferrer"
                     className="group inline-flex items-baseline gap-1 text-xs leading-relaxed text-chalk/90 hover:text-chalk">
                    {item.title}
                    <ExternalLink aria-hidden
                                  className="h-3 w-3 shrink-0 self-center text-ash opacity-0 transition-opacity group-hover:opacity-100" />
                  </a>
                ) : (
                  <span className="text-xs leading-relaxed text-chalk/90">{item.title}</span>
                )}
              </div>
            </li>
          ))}
        </ul>
        <p className="px-5 pt-3 text-[0.7rem] leading-relaxed text-ash">
          Headlines via Google News RSS. Relevance is best-effort and unverified — read them as
          context for the signals above, not as confirmation of them.
        </p>
      </CardBody>
    </Card>
  );
}
