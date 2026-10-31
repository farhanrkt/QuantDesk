"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { fetchMarketBoard } from "@/lib/api";
import { BOARD_REFRESH_MS, type BoardFocus } from "@/lib/marketboard";
import type { Engine, EngineFailure, Market, MarketBoard } from "@/lib/types";

/**
 * The board of what moved the markets, fetched once for the whole app and kept
 * fresh while somebody is looking at it.
 *
 * ONE LOOP, NOT ONE PER COMPONENT. The bar at the foot of every page, the Today
 * view and the landing all read this, so a reader with three of them on screen
 * still makes one request every five minutes — and that request is served by
 * the edge cache for everyone else, because it names nothing.
 *
 * PAUSED WHILE THE TAB IS HIDDEN. A background tab polling a market board all
 * afternoon is load nobody reads; on return the board refreshes at once if it
 * is older than the interval.
 *
 * Which stock a page is about reaches the board through `useBoardFocus`, and
 * stays in this browser: it decides what the strip MARKS, never what is asked.
 */
interface BoardContext {
  state: Engine<MarketBoard>;
  refreshing: boolean;
  refresh: () => void;
  /** The market in view: the stock's own on a stock page, otherwise the reader's last choice. */
  market: Market;
  chooseMarket: (market: Market) => void;
  focus: BoardFocus | null;
  setFocus: (focus: BoardFocus | null) => void;
  /** A page showing the whole board, where the bar would only repeat it. */
  fullBoard: boolean;
  setFullBoard: (on: boolean) => void;
  dockOpen: boolean;
  setDockOpen: (open: boolean) => void;
}

const Context = createContext<BoardContext | null>(null);

const MARKET_KEY = "quantdesk.board.market";
const DOCK_KEY = "quantdesk.board.dock";

export function useMarketBoard(): BoardContext {
  const value = useContext(Context);
  if (!value) throw new Error("useMarketBoard outside MarketBoardProvider");
  return value;
}

/** Tell the board which stock this page is about, for as long as the page is open. */
export function useBoardFocus(focus: BoardFocus | null) {
  const { setFocus } = useMarketBoard();
  const latest = useRef(focus);
  latest.current = focus;
  const identity = focus
    ? `${focus.symbol}|${focus.market}|${focus.factors === null ? "pending"
        : focus.factors.map((f) => f.key).join(",")}`
    : "";
  useEffect(() => {
    setFocus(latest.current);
    return () => setFocus(null);
  }, [identity, setFocus]);
}

/** Mark this page as the one showing the whole board, so the bar steps aside. */
export function useFullBoard() {
  const { setFullBoard } = useMarketBoard();
  useEffect(() => {
    setFullBoard(true);
    return () => setFullBoard(false);
  }, [setFullBoard]);
}

export function MarketBoardProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<Engine<MarketBoard>>({ status: "idle" });
  const [refreshing, setRefreshing] = useState(false);
  const [chosen, setChosen] = useState<Market>("US");
  const [focus, setFocus] = useState<BoardFocus | null>(null);
  const [fullBoard, setFullBoard] = useState(false);
  const [dockOpen, setDockOpenState] = useState(true);
  const received = useRef<number | null>(null);
  const inFlight = useRef<AbortController | null>(null);

  // Read on mount, never during render: the server renders this tree too.
  useEffect(() => {
    try {
      const market = window.localStorage.getItem(MARKET_KEY);
      if (market === "US" || market === "ID") setChosen(market);
      if (window.localStorage.getItem(DOCK_KEY) === "closed") setDockOpenState(false);
    } catch { /* private mode: defaults stand */ }
  }, []);

  const load = useCallback(() => {
    inFlight.current?.abort();
    const controller = new AbortController();
    inFlight.current = controller;
    setRefreshing(true);
    setState((current) => (current.status === "ready" ? current : { status: "loading" }));
    fetchMarketBoard(controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return;
        received.current = Date.now();
        setState({ status: "ready", data, at: received.current });
      })
      .catch((failure: EngineFailure | Error) => {
        if (controller.signal.aborted) return;
        // A failed refresh keeps the board already on screen; its "as of" time
        // says how old it is. Only a board that never loaded becomes an error.
        setState((current) => (current.status === "ready" ? current : {
          status: "error",
          failure: { message: (failure as EngineFailure)?.message ?? "The board did not load." },
        }));
      })
      .finally(() => {
        if (!controller.signal.aborted) setRefreshing(false);
      });
  }, []);

  useEffect(() => {
    load();
    const stale = () => received.current === null || Date.now() - received.current >= BOARD_REFRESH_MS;
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible" && stale()) load();
    }, 30_000);
    const onVisible = () => {
      if (document.visibilityState === "visible" && stale()) load();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
      inFlight.current?.abort();
    };
  }, [load]);

  const chooseMarket = useCallback((market: Market) => {
    setChosen(market);
    try { window.localStorage.setItem(MARKET_KEY, market); } catch { /* private mode */ }
  }, []);

  const setDockOpen = useCallback((open: boolean) => {
    setDockOpenState(open);
    try { window.localStorage.setItem(DOCK_KEY, open ? "open" : "closed"); } catch { /* private mode */ }
  }, []);

  const value = useMemo<BoardContext>(() => ({
    state, refreshing, refresh: load,
    market: focus?.market ?? chosen, chooseMarket,
    focus, setFocus, fullBoard, setFullBoard, dockOpen, setDockOpen,
  }), [state, refreshing, load, focus, chosen, chooseMarket, fullBoard, dockOpen, setDockOpen]);

  return <Context.Provider value={value}>{children}</Context.Provider>;
}
