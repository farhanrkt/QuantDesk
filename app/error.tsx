"use client";

import { AlertTriangle } from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";

/**
 * Route-level error boundary.
 *
 * Panel-level failures are already handled inside the page — an engine that
 * cannot run renders its own card. This catches the other kind: an exception
 * thrown while RENDERING, such as an unexpected shape reaching a chart
 * accessor. Without it, React unmounts the whole tree and the user is left
 * with a blank page and no way back except a manual reload.
 *
 * A region inside the shell, not its own <main>: the top bar stays, so the
 * reader can leave by any route rather than only by the buttons here.
 */
export default function Error({
  error, reset,
}: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div className="mx-auto flex min-h-[50vh] max-w-2xl items-center">
      <div className="w-full rounded-xl border border-dist/40 bg-dist/5 p-6" role="alert">
        <div className="flex gap-3">
          <AlertTriangle aria-hidden className="mt-1 h-5 w-5 shrink-0 text-dist" />
          <div className="min-w-0 flex-1">
            <h1 className="text-h2">Something broke while drawing this page</h1>
            <p className="mt-2 text-base leading-relaxed text-body">
              Nothing you had entered is lost: results are kept for this tab, and your watchlist,
              holdings and journal live in this browser. Trying again is safe.
            </p>
            {error.digest && (
              <p className="num mt-3 text-micro text-ash">Reference: {error.digest}</p>
            )}
            <div className="mt-5 flex flex-wrap gap-3">
              <Button variant="secondary" size="sm" onClick={reset}>Try again</Button>
              {/* Deliberately a hard navigation, not next/link. `reset()` above
                  is the soft retry; this is the escape hatch for when the
                  client state itself is what broke, and a soft route change
                  would keep exactly that state alive. */}
              {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
              <a href="/" className={buttonVariants({ variant: "quiet", size: "sm" })}>
                Go to the start
              </a>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
