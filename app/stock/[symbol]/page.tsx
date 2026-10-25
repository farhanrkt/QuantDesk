import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import { StockWorkspace } from "@/components/workspace/StockWorkspace";
import { StateCard } from "@/components/ui/state";
import { PRESETS, symbolFromSegment } from "@/lib/url";

/**
 * One company's page: /stock/AAPL, /stock/BBCA.JK, /stock/%5EGSPC.
 *
 * NOTHING IS FETCHED HERE. The server validates the path and names the page —
 * "AAPL · QuantDesk" in a tab strip, and in a shared link's preview — and hands
 * the symbol to the client workspace, which runs the engines exactly as the
 * single page always did. Reading `searchParams` here would make every request
 * a server render for the sake of the tab name; the tab lives on the client.
 *
 * The presets are rendered at build time; any other symbol is rendered on its
 * first request and kept (`dynamicParams`). Each is an empty shell, so keeping
 * them costs nothing and says nothing about any company.
 */
export const dynamicParams = true;

export function generateStaticParams() {
  return PRESETS.map((symbol) => ({ symbol }));
}

type Params = { params: Promise<{ symbol: string }> };

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const symbol = symbolFromSegment((await params).symbol);
  return symbol
    ? { title: symbol,
        description: `${symbol} read through four independent lenses — order flow, price trend, `
          + "intrinsic value and accounting quality. Not investment advice." }
    : { title: "Not a ticker" };
}

export default async function StockPage({ params }: Params) {
  const symbol = symbolFromSegment((await params).symbol);
  if (!symbol) notFound();
  return (
    <Suspense fallback={<StateCard kind="loading" title={`Opening ${symbol}…`} />}>
      <StockWorkspace symbol={symbol} />
    </Suspense>
  );
}
