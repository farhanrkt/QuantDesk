import type { Metadata } from "next";
import { Suspense } from "react";
import { MarketsView } from "@/components/markets/MarketsView";
import { StateCard } from "@/components/ui/state";

export const metadata: Metadata = {
  title: "Markets",
  description: "Rank a universe, scan it for unusual activity, or see what it moves with. "
    + "A shortlist, not a verdict.",
};

export default function MarketsPage() {
  return (
    <Suspense fallback={<StateCard kind="loading" shape="table" />}>
      <MarketsView />
    </Suspense>
  );
}
