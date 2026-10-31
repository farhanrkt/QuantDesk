"use client";

import { ExternalLink } from "lucide-react";
import { agoText } from "@/lib/marketboard";
import type { NewsItem } from "@/lib/types";

/**
 * A list of third-party headlines, rendered as data and nothing else.
 *
 * Titles go through React's own escaping, links open in a new tab with
 * `rel="noopener noreferrer"`, and nothing in the app reads this text back as
 * instructions. Shared by the stock page's news panel and the market board, so
 * the two cannot drift into treating a headline differently.
 */
export function HeadlineList({ items, now }: { items: NewsItem[]; now?: number }) {
  return (
    <ul>
      {items.map((item, i) => {
        const ago = now ? agoText(item.published, now) : null;
        return (
          <li key={`${i}-${item.link}`} className="border-b border-ruleSoft px-5 py-2.5 last:border-0">
            <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
              <span className="shrink-0 font-mono text-micro uppercase tracking-[0.08em] text-ash">
                {item.source}
              </span>
              {ago && <span className="shrink-0 font-mono text-micro text-ash">{ago}</span>}
              {item.link ? (
                <a href={item.link} target="_blank" rel="noopener noreferrer"
                   className="group inline-flex min-h-[24px] basis-full items-baseline gap-1 py-0.5 text-meta
                              leading-relaxed text-body hover:text-chalk sm:basis-auto
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
        );
      })}
    </ul>
  );
}
