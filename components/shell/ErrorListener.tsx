"use client";

import { useEffect } from "react";
import { useCapabilities } from "@/lib/api";
import { reportError, setErrorReporting } from "@/lib/errorreport";

/**
 * Turns browser error reporting on when the server says it has somewhere to
 * send it, and reports what no boundary catches: an error thrown outside a
 * render, and a promise that failed with nobody waiting for it. Draws nothing.
 */
export function ErrorListener() {
  const { errorReporting } = useCapabilities();
  useEffect(() => { setErrorReporting(errorReporting); }, [errorReporting]);
  useEffect(() => {
    if (!errorReporting) return;
    const onError = (event: ErrorEvent) => reportError("unhandled", event.error ?? event.message);
    const onRejection = (event: PromiseRejectionEvent) => {
      // An aborted request is the app cancelling work it no longer needs.
      if (event.reason instanceof DOMException && event.reason.name === "AbortError") return;
      reportError("rejection", event.reason);
    };
    window.addEventListener("error", onError);
    window.addEventListener("unhandledrejection", onRejection);
    return () => {
      window.removeEventListener("error", onError);
      window.removeEventListener("unhandledrejection", onRejection);
    };
  }, [errorReporting]);
  return null;
}
