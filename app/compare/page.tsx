import type { Metadata } from "next";
import { Suspense } from "react";
import { CompareView } from "@/components/compare/CompareView";
import { StateCard } from "@/components/ui/state";

export const metadata: Metadata = {
  title: "Compare",
  description: "Two to four companies, each read through the same four lenses, side by side. "
    + "Nothing is summed, scored or ranked.",
};

export default function ComparePage() {
  return (
    <Suspense fallback={<StateCard kind="loading" shape="table" />}>
      <CompareView />
    </Suspense>
  );
}
