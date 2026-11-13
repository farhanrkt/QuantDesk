import type { Metadata } from "next";
import { NotFoundBody } from "@/components/shell/NotFoundBody";

export const metadata: Metadata = { title: "Not found" };

/**
 * An address with nothing behind it — including a path that is not a ticker at
 * all, which /stock/[symbol] refuses rather than guessing at.
 *
 * Inside the shell, so it is a region of the page rather than a second <main>:
 * the old version wrapped itself in one, which put two main landmarks on the
 * page once the shell existed. And it says what an address here looks like,
 * because the old copy pointed at a ticker bar on the root that no longer
 * drives every engine.
 */
export default function NotFound() {
  return <NotFoundBody />;
}
