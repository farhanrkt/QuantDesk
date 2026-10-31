"use client";

import { ExternalLink } from "lucide-react";
import Image from "next/image";
import { agoText } from "@/lib/marketboard";
import type { NewsItem } from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * A list of third-party headlines, rendered as data and nothing else.
 *
 * Titles go through React's own escaping, links open in a new tab with
 * `rel="noopener noreferrer"`, and nothing in the app reads this text back as
 * instructions. Shared by the stock page's news panel and the market board, so
 * the two cannot drift into treating a headline differently.
 *
 * THUMBNAILS COME THROUGH OUR OWN ORIGIN. `next/image` fetches them server-side
 * from the two hosts `next.config.mjs` allows, so the page's CSP stays
 * `img-src 'self'` and the reader's browser never contacts the news site. They
 * are decorative — the headline beside them says what the story is — so `alt`
 * is empty.
 */
export function HeadlineList({
  items, now, compact,
}: { items: NewsItem[]; now?: number; compact?: boolean }) {
  return (
    <ul>
      {items.map((item, i) => {
        const ago = now ? agoText(item.published, now) : null;
        return (
          <li key={`${i}-${item.link}`}
              className={compact ? "flex gap-3 border-b border-ruleSoft py-2.5 last:border-0"
                                 : "flex gap-3 border-b border-ruleSoft px-5 py-2.5 last:border-0"}>
            {item.image && (
              <Image src={item.image.url} alt="" width={compact ? 72 : 112} height={compact ? 48 : 72}
                     sizes={compact ? "72px" : "112px"}
                     className={compact ? "h-12 w-[4.5rem] shrink-0 rounded object-cover"
                                        : "h-[4.5rem] w-28 shrink-0 rounded object-cover"} />
            )}
            <div className="flex min-w-0 flex-1 flex-wrap items-baseline gap-x-2 gap-y-0.5">
              <span className="shrink-0 font-mono text-micro uppercase tracking-[0.08em] text-ash">
                {item.source}
              </span>
              {ago && <span className="shrink-0 font-mono text-micro text-ash">{ago}</span>}
              {item.link ? (
                <a href={item.link} target="_blank" rel="noopener noreferrer"
                   className={cn("group inline-flex min-h-[24px] basis-full items-baseline gap-1 py-0.5 text-meta",
                                 "leading-relaxed text-body hover:text-chalk",
                                 "focus:outline-none focus-visible:ring-2 focus-visible:ring-tech",
                                 !compact && !item.image && "sm:basis-auto")}>
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
