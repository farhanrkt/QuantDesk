"use client";

import { X } from "lucide-react";
import {
  createContext, useCallback, useContext, useEffect, useMemo, useRef, useState,
} from "react";
import { cn } from "@/lib/utils";

/**
 * Short confirmations of something the reader just did — "link copied",
 * "added to watchlist", "entry deleted, undo".
 *
 * WHY THE APP HAD NONE, AND WHY IT NEEDS ONE NOW. Every action used to change
 * something visible on the panel it was pressed on, so the panel was its own
 * confirmation. Copying a link, starring a ticker from the command palette or
 * deleting a journal entry from another page changes nothing the reader is
 * looking at; without a confirmation, the only way to know it worked is to go
 * and check.
 *
 * TWO LIVE REGIONS, IN THE DOM BEFORE ANY MESSAGE. A live region that is
 * inserted together with its text is frequently not announced at all — screen
 * readers watch regions that already exist. So both are rendered on mount and
 * empty: a polite one for confirmations and an assertive one for failures.
 *
 * NEVER A FINDING. A toast confirms an action; it does not report anything
 * about a company. Nothing the server concluded is ever shown here, because a
 * finding that disappears after five seconds is a finding nobody can re-read.
 */
type Toast = {
  id: number;
  message: string;
  tone?: "error";
  action?: { label: string; onClick: () => void };
  duration: number;
};

type ToastInput = Omit<Toast, "id" | "duration"> & { duration?: number };

const ToastContext = createContext<(t: ToastInput) => void>(() => {});

export function useToast() {
  return useContext(ToastContext);
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const seq = useRef(0);

  const dismiss = useCallback((id: number) => {
    setToasts((all) => all.filter((t) => t.id !== id));
  }, []);

  const push = useCallback((input: ToastInput) => {
    seq.current += 1;
    const toast: Toast = { duration: input.action ? 8000 : 4000, ...input, id: seq.current };
    // Three at most: a fourth confirmation means the reader is doing things
    // faster than they could read these, and the oldest one no longer matters.
    setToasts((all) => [...all.slice(-2), toast]);
  }, []);

  const polite = toasts.filter((t) => t.tone !== "error").at(-1)?.message ?? "";
  const assertive = toasts.filter((t) => t.tone === "error").at(-1)?.message ?? "";

  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="sr-only" role="status" aria-live="polite">{polite}</div>
      <div className="sr-only" role="alert" aria-live="assertive">{assertive}</div>
      <div aria-hidden={toasts.length === 0}
           className="pointer-events-none fixed inset-x-0 bottom-4 z-50 flex flex-col items-center
                      gap-2 px-4 print:hidden">
        {toasts.map((t) => <ToastView key={t.id} toast={t} onDismiss={dismiss} />)}
      </div>
    </ToastContext.Provider>
  );
}

function ToastView({ toast, onDismiss }: { toast: Toast; onDismiss: (id: number) => void }) {
  const [paused, setPaused] = useState(false);
  useEffect(() => {
    if (paused) return;
    const timer = window.setTimeout(() => onDismiss(toast.id), toast.duration);
    return () => window.clearTimeout(timer);
  }, [paused, toast.id, toast.duration, onDismiss]);

  return useMemo(() => (
    <div
      onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)}
      onFocus={() => setPaused(true)} onBlur={() => setPaused(false)}
      className={cn(
        "pointer-events-auto flex w-full max-w-md animate-rise items-center gap-3 rounded-lg border",
        "bg-raised px-4 py-2.5 text-meta shadow-pop",
        toast.tone === "error" ? "border-dist/40 text-chalk" : "border-rule text-body",
      )}
    >
      <span className="min-w-0 flex-1">{toast.message}</span>
      {toast.action && (
        <button type="button"
                onClick={() => { toast.action!.onClick(); onDismiss(toast.id); }}
                className="min-h-[24px] rounded px-2 font-semibold text-tech hover:bg-tech/10
                           focus:outline-none focus-visible:ring-2 focus-visible:ring-tech">
          {toast.action.label}
        </button>
      )}
      <button type="button" aria-label="Dismiss" onClick={() => onDismiss(toast.id)}
              className="flex h-6 w-6 items-center justify-center rounded text-ash hover:text-chalk
                         focus:outline-none focus-visible:ring-2 focus-visible:ring-tech">
        <X aria-hidden className="h-3.5 w-3.5" />
      </button>
    </div>
  ), [toast, onDismiss]);
}
