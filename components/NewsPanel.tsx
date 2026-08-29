"use client";

import { ExternalLink } from "lucide-react";
import { Card, CardBody, CardHeader, CardTitle, Note } from "@/components/ui/card";
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
        <span className="font-mono text-micro text-ash">Google News · {state.data.ticker}</span>
      </CardHeader>
      <CardBody className="px-0">
        <ul>
          {state.data.items.map((item, i) => (
            <li key={i} className="border-b border-ruleSoft px-5 py-2.5 last:border-0">
              <div className="flex items-baseline gap-2">
                <span className="shrink-0 font-mono text-micro uppercase tracking-[0.08em] text-ash">
                  {item.source}
                </span>
                {item.link ? (
                  <a href={item.link} target="_blank" rel="noopener noreferrer"
                     className="group inline-flex min-h-[24px] items-baseline gap-1 py-0.5 text-meta
                               leading-relaxed text-body hover:text-chalk
                               focus:outline-none focus-visible:ring-2 focus-visible:ring-tech">
                    {item.title}
                    <ExternalLink aria-hidden
                                  className="h-3 w-3 shrink-0 self-center text-ash opacity-0 transition-opacity group-hover:opacity-100" />
                  </a>
                ) : (
                  <span className="text-meta leading-relaxed text-body">{item.title}</span>
                )}
              </div>
            </li>
          ))}
        </ul>
        <div className="px-5 pt-3">
          <Note>
            Headlines from Google News, unverified and matched by best effort. Context for the
            signals above, never confirmation of them — nothing in this app reads them back as
            data.
          </Note>
        </div>
      </CardBody>
    </Card>
  );
}
