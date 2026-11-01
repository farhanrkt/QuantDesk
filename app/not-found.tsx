import type { Metadata } from "next";
import { ButtonLink } from "@/components/ui/button";
import { Kbd } from "@/components/ui/kbd";

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
  return (
    <div className="mx-auto flex min-h-[50vh] max-w-2xl items-center">
      <div className="w-full rounded-xl border border-dashed border-rule px-6 py-14 text-center">
        <p className="eyebrow mb-3">404</p>
        <h1>Nothing lives at this address</h1>
        <p className="mx-auto mt-3 max-w-md text-base leading-relaxed text-ash">
          A company&apos;s page takes its ticker — /stock/AAPL, /stock/BBCA.JK — and anything that is
          not a ticker lands here. Search by name from the top bar, or press{" "}
          <Kbd keys={["mod", "K"]} className="align-middle" />.
        </p>
        <div className="mt-6 flex flex-wrap justify-center gap-3">
          <ButtonLink href="/" variant="primary" size="sm">Go to the start</ButtonLink>
          <ButtonLink href="/markets" variant="quiet" size="sm">Market tools</ButtonLink>
        </div>
      </div>
    </div>
  );
}
