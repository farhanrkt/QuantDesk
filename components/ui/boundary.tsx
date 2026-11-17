"use client";

import { Component, type ReactNode } from "react";
import { reportError } from "@/lib/errorreport";

/**
 * A part of the shell that may fail without taking the page with it.
 *
 * The markets band and panel sit in the layout, above every page and outside
 * the route's error boundary (app/error.tsx), so an exception while drawing
 * them replaced the whole document — top bar, page and all. Wrapped in this,
 * a failure there draws `fallback` (nothing, by default), is reported, and the
 * page the reader came for is untouched.
 */
export class PartBoundary extends Component<{ children: ReactNode; fallback?: ReactNode },
                                            { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: unknown) {
    reportError("render", error);
  }

  render() {
    return this.state.failed ? (this.props.fallback ?? null) : this.props.children;
  }
}
