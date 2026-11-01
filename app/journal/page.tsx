import type { Metadata } from "next";
import { JournalView } from "@/components/journal/JournalView";

export const metadata: Metadata = {
  title: "Thesis journal",
  description: "Every thesis you wrote down, as written. Kept in this browser only.",
};

export default function JournalPage() {
  return <JournalView />;
}
