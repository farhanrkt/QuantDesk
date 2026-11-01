"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useWorkspace } from "@/components/shell/workspace";
import { fetchMarketBoard, fetchMarketCalendar, fetchWatchlistEarnings } from "@/lib/api";
import { BOARD_REFRESH_MS, type BoardFocus } from "@/lib/marketboard";
import type {
  Engine, EngineFailure, Market, MarketBoard, MarketCalendar, WatchlistEarnings,
} from "@/lib/types";

/**
 * The market panel's data, fetched once for the whole app and kept fresh while
 * somebody is looking at it: the board, the calendar, and the watchlist's
 * report dates.
 *
 * ONE LOOP, NOT ONE PER COMPONENT. The side panel, the band on narrower
 * screens, the Today view and the landing all read this, so a reader with all
 * of them on screen still makes one board request every five minutes — and
 * that request is served by the edge cache for everyone else, because it names
 * nothing. The calendar is refetched hourly; it changes when a file is committed.
 *
 * PAUSED WHILE THE TAB IS HIDDEN, refreshed at once on return if stale.
 *
 * THE WATCHLIST STAYS A PERSONAL INPUT. Its report dates are asked for in a POST
 * body, handed over here from the workspace, and kept in memory for the day;
 * the request layer never reads the watchlist itself.
 */
interface BoardContext {
  state: Engine<MarketBoard>;
  refreshing: boolean;
  refresh: () => void;
  calendar: Engine<MarketCalendar>;
  earnings: Engine<WatchlistEarnings>;
  /** The market in view: the stock's own on a stock page, otherwise the reader's last choice. */
  market: Market;
  chooseMarket: (market: Market) => void;
  focus: BoardFocus | null;
  setFocus: (focus: BoardFocus | null) => void;
  /** A page showing the whole board, where the side panel would only repeat it. */
  fullBoard: boolean;
  setFullBoard: (on: boolean) => void;
  railOpen: boolean;
  setRailOpen: (open: boolean) => void;
}

const Context = createContext<BoardContext | null>(null);

const MARKET_KEY = "quantdesk.board.market";
const RAIL_KEY = "quantdesk.board.rail";
const CALENDAR_REFRESH_MS = 3_600_000;
const EARNINGS_MAX = 20;

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
    ? `${focus.symbol}|${focus.market}|${focus.earnings ?? ""}|${focus.factors === null ? "pending"
        : focus.factors.map((f) => f.key).join(",")}`
    : "";
  useEffect(() => {
    setFocus(latest.current);
    return () => setFocus(null);
  }, [identity, setFocus]);
}

/** Mark this page as the one showing the whole board, so the side panel steps aside. */
export function useFullBoard() {
  const { setFullBoard } = useMarketBoard();
  useEffect(() => {
    setFullBoard(true);
    return () => setFullBoard(false);
  }, [setFullBoard]);
}

const failureOf = (failure: unknown, fallback: string): EngineFailure =>
  ({ message: (failure as EngineFailure)?.message ?? fallback });

export function MarketBoardProvider({ children }: { children: React.ReactNode }) {
  const { watchlist } = useWorkspace();
  const [state, setState] = useState<Engine<MarketBoard>>({ status: "idle" });
  const [calendar, setCalendar] = useState<Engine<MarketCalendar>>({ status: "idle" });
  const [earnings, setEarnings] = useState<Engine<WatchlistEarnings>>({ status: "idle" });
  const [refreshing, setRefreshing] = useState(false);
  const [chosen, setChosen] = useState<Market>("US");
  const [focus, setFocus] = useState<BoardFocus | null>(null);
  const [fullBoard, setFullBoard] = useState(false);
  const [railOpen, setRailOpenState] = useState(true);
  const received = useRef<number | null>(null);
  const calendarReceived = useRef<number | null>(null);
  const inFlight = useRef<AbortController | null>(null);

  // Read on mount, never during render: the server renders this tree too.
  useEffect(() => {
    try {
      const market = window.localStorage.getItem(MARKET_KEY);
      if (market === "US" || market === "ID") setChosen(market);
      if (window.localStorage.getItem(RAIL_KEY) === "closed") setRailOpenState(false);
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
      .catch((failure) => {
        if (controller.signal.aborted) return;
        // A failed refresh keeps the board already on screen; its "as of" time
        // says how old it is. Only a board that never loaded becomes an error.
        setState((current) => (current.status === "ready" ? current
          : { status: "error", failure: failureOf(failure, "The board did not load.") }));
      })
      .finally(() => {
        if (!controller.signal.aborted) setRefreshing(false);
      });
  }, []);

  const loadCalendar = useCallback(() => {
    fetchMarketCalendar()
      .then((data) => {
        calendarReceived.current = Date.now();
        setCalendar({ status: "ready", data, at: calendarReceived.current });
      })
      .catch((failure) => setCalendar((current) => (current.status === "ready" ? current
        : { status: "error", failure: failureOf(failure, "The calendar did not load.") })));
  }, []);

  useEffect(() => {
    load();
    loadCalendar();
    const stale = () => received.current === null || Date.now() - received.current >= BOARD_REFRESH_MS;
    const calendarStale = () => calendarReceived.current !== null
      && Date.now() - calendarReceived.current >= CALENDAR_REFRESH_MS;
    const tick = () => {
      if (document.visibilityState !== "visible") return;
      if (stale()) load();
      if (calendarStale()) loadCalendar();
    };
    const timer = window.setInterval(tick, 30_000);
    document.addEventListener("visibilitychange", tick);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", tick);
      inFlight.current?.abort();
    };
  }, [load, loadCalendar]);

  // The watchlist's report dates: asked for when the list changes, at most
  // twenty names, in a body. Nothing is asked for an empty list.
  const watchKey = watchlist.slice(0, EARNINGS_MAX).join(",");
  useEffect(() => {
    if (!watchKey) {
      setEarnings({ status: "idle" });
      return;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setEarnings((current) => (current.status === "ready" ? current : { status: "loading" }));
      fetchWatchlistEarnings(watchKey.split(","), controller.signal)
        .then((data) => { if (!controller.signal.aborted) setEarnings({ status: "ready", data, at: Date.now() }); })
        .catch((failure) => {
          if (!controller.signal.aborted) {
            setEarnings({ status: "error", failure: failureOf(failure, "Report dates did not load.") });
          }
        });
    }, 800);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [watchKey]);

  const chooseMarket = useCallback((market: Market) => {
    setChosen(market);
    try { window.localStorage.setItem(MARKET_KEY, market); } catch { /* private mode */ }
  }, []);

  const setRailOpen = useCallback((open: boolean) => {
    setRailOpenState(open);
    try { window.localStorage.setItem(RAIL_KEY, open ? "open" : "closed"); } catch { /* private mode */ }
  }, []);

  const value = useMemo<BoardContext>(() => ({
    state, refreshing, refresh: load, calendar, earnings,
    market: focus?.market ?? chosen, chooseMarket,
    focus, setFocus, fullBoard, setFullBoard, railOpen, setRailOpen,
  }), [state, refreshing, load, calendar, earnings, focus, chosen, chooseMarket, fullBoard,
       railOpen, setRailOpen]);

  return <Context.Provider value={value}>{children}</Context.Provider>;
}
