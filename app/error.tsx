"use client";

import { AlertTriangle } from "lucide-react";

/**
 * Route-level error boundary.
 *
 * Panel-level failures are already handled inside the page — an engine that
 * cannot run renders its own card. This catches the other kind: an exception
 * thrown while RENDERING, such as an unexpected shape reaching a chart
 * accessor. Without it, React unmounts the whole tree and the user is left
 * with a blank page and no way back except a manual reload.
 */
export default function Error({
  error, reset,
}: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main className="mx-auto flex min-h-screen max-w-2xl items-center px-4">
      <div className="w-full rounded border border-dist/40 bg-dist/5 p-6">
        <div className="flex gap-3">
          <AlertTriangle aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-dist" />
          <div className="min-w-0 flex-1">
            <div className="eyebrow mb-2 text-dist">Something broke while rendering</div>
            <p className="text-sm leading-relaxed text-chalk/80">
              The desk hit an unexpected error. Your last query was not saved, so retrying is
              safe — no engine result is lost by starting again.
            </p>
            {error.digest && (
              <p className="num mt-3 text-[0.7rem] text-ash">Reference: {error.digest}</p>
            )}
            <div className="mt-5 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={reset}
                className="h-9 rounded border border-tech/50 bg-tech/10 px-4 font-mono text-[0.65rem] uppercase tracking-[0.14em] text-chalk transition-colors hover:bg-tech/20"
              >
                Try again
              </button>
              {/* Deliberately a hard navigation, not next/link. `reset()` above
                  is the soft retry; this is the escape hatch for when the
                  client state itself is what broke, and a soft route change
                  would keep exactly that state alive. */}
              {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
              <a
                href="/"
                className="inline-flex h-9 items-center rounded border border-rule px-4 font-mono text-[0.65rem] uppercase tracking-[0.14em] text-ash transition-colors hover:border-tech/50 hover:text-chalk"
              >
                Back to the desk
              </a>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
