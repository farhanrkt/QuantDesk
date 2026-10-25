"use client";

import { ListOrdered } from "lucide-react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { useRanking } from "@/lib/api";
import { writeSession } from "@/lib/session";
import { marketOf } from "@/lib/symbols";
import { marketsHref } from "@/lib/url";

/**
 * "Rank these" for the watchlist — the one place the list leaves the browser,
 * and only because the reader pressed a button that says so.
 *
 * It goes in a POST body (see useRanking), never a URL, and the result opens in
 * the ranking view with the list loaded as "your own list", so pressing Rank
 * there again sends the same body rather than switching to a query string.
 *
 * ONE MARKET AT A TIME, because the ranking compares names against each other
 * and against one benchmark: a rupiah bank and a dollar chipmaker ranked on
 * "relative strength" against one index would be one of them measured against
 * the wrong market. A mixed watchlist ranks its larger half and says so.
 */
export function WatchlistRank({ symbols }: { symbols: string[] }) {
  const router = useRouter();
  const { scan } = useRanking();
  const idx = symbols.filter((s) => marketOf(s) === "ID");
  const us = symbols.filter((s) => marketOf(s) === "US");
  const market = idx.length > us.length ? "ID" : "US";
  const list = market === "ID" ? idx : us;
  const left = symbols.length - list.length;
  if (list.length < 2) return null;

  const run = () => {
    writeSession("rank:choice", "__custom__");
    writeSession("rank:custom", list.join(", "));
    writeSession("rank:customMarket", market);
    scan({ universe: null, tickers: list.join(","), market });
    router.push(marketsHref("rank"));
  };

  return (
    <div className="flex flex-wrap items-center gap-3 border-t border-ruleSoft pt-4">
      <Button variant="secondary" size="sm" onClick={run}>
        <ListOrdered aria-hidden className="h-4 w-4" />
        Rank these {list.length} against each other
      </Button>
      <span className="text-micro text-ash">
        Sends the list to rank it, in the request body — never in a link.
        {left > 0 && ` ${left} from the other market ${left === 1 ? "is" : "are"} left out.`}
      </span>
    </div>
  );
}
