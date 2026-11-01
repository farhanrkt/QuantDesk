"""
scanlog.py
==========
What the scanner said, and what happened next.

WHY THIS IS THE MOST IMPORTANT THING IN THE PRIVATE TIER
----------------------------------------------------------
`verdict.provenance()` admits, on every screen, that the blend of nine
components has never been backtested. `scripts/backtest_verdict.py` closes part
of that gap retrospectively, and it can only close part: point-in-time
fundamentals are not obtainable from this data source, so the value and quality
components — 1.7 of the 4.9 base weight — cannot be reconstructed as they stood
on a past date without reading filings that had not been published.

There is exactly one way to measure those honestly, and it is to write down what
the scanner said on the day it said it and wait. That is what this file does.

It is therefore a slow instrument. It produces nothing useful for months, and
the temptation will be to read it early and conclude something. `summarise`
refuses to compute a hit rate under `MIN_CLOSED` observations, because the first
ten resolved calls of any strategy are noise and reading them is how a strategy
gets abandoned or trusted for no reason.

A CALL IS NOT AN OBSERVATION
-----------------------------
A call is one row: what the scanner said about one name on one scan date. A name
it calls a buy on six scans in a fortnight is measured six times over nearly the
same 63 sessions, and the six outcomes are one outcome counted six times. The
first Indonesian log has exactly that shape: 74 buy calls on 23 names, every one
made between 9 and 21 September 2026. Counted as rows, five companies called on
every scan would have met `MIN_CLOSED` on their own.

So `observations` counts a name once per horizon window. The call that opens a
window is the observation, scored on its own action and its own outcome. A later
call on the same name before that window resolves is the same observation,
whatever it says; a call on or after the session it resolved on opens the next
one. Every count `summarise` and `summarise_screens` gate on is a count of these,
and the rows behind it are reported beside it (calls, distinct names, scan
dates), so the gap between the two stays visible.

Counting each name once does not make the names independent of each other. Calls
made inside one window share one market path: the same quarter's sector moves
land on all of them at once, and an excess over the index removes the index's
level, not what moved inside it. When every observation was opened inside one
window the reading says so in as many words: one draw of the market, not many.

WHAT IS RECORDED, AND WHAT IS DELIBERATELY NOT
-----------------------------------------------
One row per name per scan: the ticker, the date, the action, the score, the
conviction, the price at the time and the gates that fired. That is enough to
measure whether the ordering meant anything.

NOT recorded: the whole verdict payload. It is megabytes per scan, it would make
the log unreadable, and every field in it is reproducible from the scan report
that sits beside it. The log is an index, not an archive.

NOT recorded anywhere a server can see it. This is the same rule the thesis
journal follows — a list of what somebody is about to buy is a fact about them,
not about a company. It is a local file under `reports/`, which is gitignored.

THE PRICE IS THE ONE FIELD THAT MUST BE EXACT
----------------------------------------------
Everything else here is a label. The price is what every later measurement is
computed against, and it is recorded as the close on the scan date — not the
price when the log is read, and not adjusted afterwards. `resolve` re-fetches
the same symbol later and compares, and if the recorded price were ever
back-adjusted for a split the comparison would silently measure the split.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

# Below this many resolved observations, a hit rate is noise wearing a percentage
# sign. Thirty is the floor `pretrade`, `calibrate_tape` and `calibrate_patterns`
# all use, and the argument is identical: a rate quoted from twenty observations
# describes the twenty. It counts observations, not calls; see `observations`.
MIN_CLOSED = 30

# How long a call is given before it is resolved. A quarter, matching the
# longest horizon anything else in this app measures at.
HORIZON_DAYS = 63

# Actions worth measuring. HOLD is excluded deliberately — it is what the
# scanner says when it has nothing to say, so scoring it would measure the
# market rather than the scanner.
BUYS = frozenset({"STRONG_BUY", "BUY"})
SELLS = frozenset({"REDUCE", "AVOID"})
DIRECTIONAL = BUYS | SELLS


def path_for(directory: Path, market: str) -> Path:
    return directory / f"scanlog_{(market or '').strip().upper()}.jsonl"


def record(directory: Path, market: str, verdicts: Sequence[dict],
           scanned_on: Optional[str] = None,
           regime: Optional[dict] = None) -> dict:
    """Append one row per verdict. Idempotent for a given market and date.

    APPEND-ONLY, AND ONE FILE PER MARKET. JSON Lines rather than a JSON document
    because the file is written by appending and read by streaming, and a
    top-level array would have to be parsed and rewritten in full on every scan
    — which is how a log gets truncated by an interrupted write.

    Re-running a scan on the same day REPLACES that day's rows rather than
    doubling them. A scan run twice with different settings is one opinion
    revised, not two observations.
    """
    directory.mkdir(parents=True, exist_ok=True)
    target = path_for(directory, market)
    today = scanned_on or dt.date.today().isoformat()

    existing = [row for row in read(directory, market) if row.get("scannedOn") != today]

    rows = []
    for entry in verdicts:
        if entry.get("score") is None:
            continue
        rows.append({
            "scannedOn": today,
            "ticker": entry["ticker"],
            "name": entry.get("name"),
            "action": entry["action"],
            "score": entry["score"],
            "conviction": entry.get("conviction"),
            "crossChecked": entry.get("crossChecked"),
            "rank": entry.get("rank"),
            "sector": entry.get("sector"),
            # The close on the scan date. See the module docstring: this is the
            # one field every later measurement is computed against.
            "price": entry.get("latestClose"),
            "gates": [gate["id"] for gate in (entry.get("gates") or [])],
            "regime": (regime or {}).get("state"),
            # WHAT THE SCREENS SAID ON THE DAY THEY SAID IT.
            #
            # `neglect.py` and the specialist shortlist both publish that they
            # cannot be backtested and that THIS FILE is the honest alternative:
            # the filings are only available as restated today, and industry
            # labels and the share register arrive as a snapshot with no history
            # at all, so "was this name cheap, unrivalled and uncovered in
            # March" cannot be reconstructed after the fact — only recorded
            # before it.
            #
            # The log did not record any of it. Both docstrings claimed a
            # prospective record that did not exist, which is the failure this
            # repository keeps finding in its own instruments: the thing next to
            # the thing that matters. `sector` alone cannot answer a question
            # asked about an industry, a screen or a field.
            #
            # Rows written before this existed simply lack these keys. A reader
            # must treat absent as UNRECORDED rather than as false — see
            # `selected_on`, which refuses a day it cannot speak for.
            "industry": entry.get("industry"),
            "neglected": bool((entry.get("neglect") or {}).get("selected")),
            "leadsField": bool((entry.get("fieldPosition") or {}).get("leads")),
            "soleListing": bool((entry.get("fieldPosition") or {})
                                .get("soleListing")),
            "compounding": bool(
                (entry.get("trackRecord") or {}).get("everyYearProfitable")
                and (entry.get("trackRecord") or {}).get("operatingCashFlowPositive")
                and (entry.get("trackRecord") or {}).get("growing")),
            "revenueCagr": (entry.get("trackRecord") or {}).get("revenueCagr"),
        })

    with target.open("w") as handle:
        for row in existing + rows:
            handle.write(json.dumps(row) + "\n")

    return {"path": str(target), "added": len(rows),
            "total": len(existing) + len(rows), "scannedOn": today}


# The screen flags added on 20 September 2026. A row written before that date
# carries none of them, and the difference between "not selected" and "not
# recorded" is the whole value of a prospective log.
SCREEN_FLAGS = ("neglected", "leadsField", "soleListing", "compounding")


def selected_on(rows: Sequence[dict], flag: str) -> dict:
    """Which names a screen selected, by scan date, refusing the days it cannot speak for.

    A DAY WITH NO ROWS CARRYING THE FLAG IS UNRECORDED, NOT EMPTY. Reading a
    missing key as False would report that the screen selected nothing in
    August, which is a finding about the screen rather than about the log — and
    it is exactly the reading that would make a prospective record useless, by
    filling its early history with fabricated zeroes.
    """
    if flag not in SCREEN_FLAGS:
        raise ValueError(f"{flag} is not a recorded screen: {SCREEN_FLAGS}")
    days: dict[str, dict] = {}
    for row in rows:
        day = row.get("scannedOn")
        if not day:
            continue
        block = days.setdefault(day, {"recorded": False, "tickers": []})
        if flag in row:
            block["recorded"] = True
            if row.get(flag):
                block["tickers"].append(row["ticker"])
    return {day: block for day, block in sorted(days.items())}


def read(directory: Path, market: str) -> list[dict]:
    """Every row ever recorded for this market, oldest first."""
    target = path_for(directory, market)
    if not target.exists():
        return []
    rows = []
    for line in target.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            # A truncated final line from an interrupted write. Skipping it
            # loses one row; refusing to read loses the whole history.
            continue
    rows.sort(key=lambda r: (r.get("scannedOn") or "", r.get("ticker") or ""))
    return rows


def resolve(rows: Sequence[dict], prices: dict, benchmark=None,
            horizon: int = HORIZON_DAYS,
            today: Optional[dt.date] = None) -> list[dict]:
    """Attach the outcome to every call old enough to have one.

    `prices` maps ticker to a date-indexed close series; `benchmark` is the same
    for the index. The outcome is an EXCESS return — what the name did against
    the market over the same window — because a market that fell 20% makes every
    call look wrong and a market that rose makes every call look right, and
    neither says anything about the ordering.

    A call younger than the horizon returns `open: True` and no outcome. It is
    not a miss and it is not a hit; it has not happened yet.
    """
    import pandas as pd

    today = today or dt.date.today()
    out = []
    for row in rows:
        try:
            scanned = dt.date.fromisoformat(row["scannedOn"])
        except (KeyError, TypeError, ValueError):
            continue

        entry = {**row, "open": True, "excess": None, "raw": None, "days": None}
        series = prices.get(row["ticker"])
        if series is None or len(series) == 0:
            entry["reason"] = "no later price for this symbol"
            out.append(entry)
            continue

        after = series[series.index.date > scanned]
        if len(after) < horizon:
            entry["days"] = len(after)
            out.append(entry)
            continue

        start = float(series[series.index.date <= scanned].iloc[-1]) \
            if len(series[series.index.date <= scanned]) else None
        end = float(after.iloc[horizon - 1])
        if not start or start <= 0:
            entry["reason"] = "no usable price on the scan date"
            out.append(entry)
            continue

        raw = end / start - 1.0
        excess = raw
        if benchmark is not None and len(benchmark):
            before = benchmark[benchmark.index.date <= scanned]
            later = benchmark[benchmark.index.date > scanned]
            if len(before) and len(later) >= horizon:
                index_start = float(before.iloc[-1])
                index_end = float(later.iloc[horizon - 1])
                if index_start > 0:
                    excess = raw - (index_end / index_start - 1.0)

        entry.update({"open": False, "raw": float(raw), "excess": float(excess),
                      "days": horizon,
                      "resolvedOn": pd.Timestamp(after.index[horizon - 1]).date()
                      .isoformat()})
        out.append(entry)
    return out


def _resolved(row: dict) -> bool:
    return not row.get("open") and row.get("excess") is not None


def _inside(row: dict, window: dict) -> bool:
    """Whether a call falls inside the window an earlier call opened.

    The window runs from the opening call's scan date up to the session it
    resolved on, and stops short of that session: a call made on it starts from
    the close the earlier one ended on, so the two outcomes share no day. A
    window with no `resolvedOn` has not ended.
    """
    start, day = window.get("scannedOn") or "", row.get("scannedOn") or ""
    end = window.get("resolvedOn")
    return start <= day and (end is None or day < end)


def observations(calls: Sequence[dict]) -> list[dict]:
    """One entry per name per horizon window, which is what the log observed.

    `calls` are rows from `resolve`, already narrowed to what is being measured:
    the directional actions, or one screen's selections. Each entry is the call
    that opened its window, carrying `calls`, every call that fell inside it,
    the opening one first. The module docstring says why a call is not an
    observation.

    RESOLVED CALLS ARE GROUPED FIRST, AMONG THEMSELVES. Their windows are exact:
    `resolvedOn` is the session the outcome was read on, counted in the name's
    own sessions, so a suspension lengthens the window instead of passing for
    time. A call that could not be priced is placed afterwards, and can never
    hide one that could.

    WHAT HAS NOT RESOLVED ADDS AT MOST ONE OBSERVATION PER NAME. A call still
    inside its horizon has a window that has not ended, so every later call on
    the name falls inside it. A call inside a resolved window belongs to that
    window whatever it said: a buy revised to a reduce nine days later is one
    observation, scored on the buy.
    """
    by_name: dict = {}
    for row in sorted(calls, key=lambda r: r.get("scannedOn") or ""):
        by_name.setdefault(row.get("ticker"), []).append(row)

    out = []
    for rows in by_name.values():
        windows: list[dict] = []
        for row in rows:
            if not _resolved(row):
                continue
            if windows and _inside(row, windows[-1]):
                windows[-1]["calls"].append(row)
            else:
                windows.append({**row, "calls": [row]})

        pending = []
        for row in rows:
            if _resolved(row):
                continue
            home = next((window for window in windows if _inside(row, window)), None)
            (home["calls"] if home is not None else pending).append(row)
        if pending:
            windows.append({**pending[0], "calls": pending})

        for window in windows:
            window["calls"].sort(key=lambda r: r.get("scannedOn") or "")
        out.extend(windows)
    out.sort(key=lambda o: (o.get("scannedOn") or "", o.get("ticker") or ""))
    return out


def _dates(rows: Sequence[dict]) -> list[str]:
    return sorted({row["scannedOn"] for row in rows if row.get("scannedOn")})


def _s(count: int) -> str:
    return "" if count == 1 else "s"


def _one_quarter(dates, horizon: int = HORIZON_DAYS) -> bool:
    """Whether several observations were all opened inside one horizon window.

    `dates` holds one entry per observation, repeats included; a single
    observation is not "many" sharing a path, so it is never called one.

    Counted in weekdays, because this is a statement about scan dates and must
    not depend on a price fetch having worked. A weekday count is never smaller
    than a session count, so a span shorter than the horizon in weekdays is
    certainly inside one window. A span a holiday or two longer may be too, and
    is not called one.
    """
    days = sorted(day for day in dates if day)
    if len(days) < 2:
        return False
    # The weekdays after the first date, up to and including the last.
    after_first = np.datetime64(days[0], "D") + 1
    through_last = np.datetime64(days[-1], "D") + 1
    return int(np.busday_count(after_first, through_last)) < horizon


def _behind(rows: Sequence[dict], noun: str, verb: str, horizon: int) -> str:
    """The rows behind a count of observations, so the gap between them shows."""
    if not rows:
        return ""
    names = len({row.get("ticker") for row in rows})
    dates = _dates(rows)
    where = ""
    if dates:
        span = dates[0] if len(dates) == 1 else f"{dates[0]} to {dates[-1]}"
        where = f" across {len(dates)} scan{_s(len(dates))} ({span})"
    return (f"They come from {len(rows)} {noun}{_s(len(rows))} on {names} "
            f"name{_s(names)}{where}; a name counts once per {horizon}-session "
            f"window, however often it was {verb} inside one. ")


def _one_draw(one_quarter: bool, resolved: bool, horizon: int) -> str:
    """The sentence that stops a count of names reading as a count of draws."""
    if not one_quarter:
        return ""
    if resolved:
        return (f"Every resolved observation was opened inside a single "
                f"{horizon}-session window, so this is one quarter of one market "
                f"path: one draw of the market, not many. ")
    return (f"Every one of them was opened inside a single {horizon}-session window, "
            f"so even once all of them have resolved they are one quarter of one "
            f"market path: one draw of the market, not many. ")


def summarise_screens(resolved: Sequence[dict], horizon: int = HORIZON_DAYS) -> dict:
    """What each screen's selections did, or a refusal to say, per screen.

    THE OTHER HALF OF RECORDING THEM. `record` writes down which names each
    screen picked on the day it picked them, because nothing about those screens
    can be reconstructed afterwards — the filings come back restated and the
    share register and industry labels have no history at all. Writing that down
    and never reading it back is the same defect one layer up, and this
    repository has now produced it twice.

    EVERY REFUSAL HERE IS PER SCREEN AND NAMED. `MIN_CLOSED` applies to each one
    separately: a screen selecting six names a month reaches thirty resolved
    calls long after the blended score does, and pooling them to reach the
    threshold sooner would measure neither.

    A NAME COUNTS ONCE PER WINDOW HERE TOO. A screen that picks the same company
    on two scans a day apart has picked it once. `closed` and `open` count
    `observations`; `selected`, `names` and `scanDates` report the rows behind
    them.

    A SCREEN WITH NO RECORDED DAYS IS NOT A SCREEN THAT SELECTED NOBODY. Rows
    written before a flag existed do not carry it, so `selected_on` reports
    those days as unrecorded and they are excluded here rather than counted as
    zero — see that function for why a fabricated zero is worse than a gap.
    """
    out = {}
    for flag in SCREEN_FLAGS:
        picked = [row for row in resolved if row.get(flag)]
        recorded = [row for row in resolved if flag in row]
        observed = observations(picked)
        closed = [o for o in observed if _resolved(o)]
        open_obs = [o for o in observed if not _resolved(o)]
        counts = {
            "selected": len(picked),
            "names": len({row.get("ticker") for row in picked}),
            "scanDates": _dates(picked),
            "closed": len(closed),
            "open": len(open_obs),
        }

        if not recorded:
            out[flag] = {
                "available": False, **counts, "oneQuarter": False,
                "reading": (f"No scan in this log recorded the {flag} screen. The "
                            f"rows predate it, which is not the same as the screen "
                            f"having selected nobody."),
            }
            continue

        if len(closed) < MIN_CLOSED:
            one_quarter = _one_quarter((o.get("scannedOn") for o in observed), horizon)
            out[flag] = {
                "available": False,
                **counts,
                "needed": MIN_CLOSED,
                "oneQuarter": one_quarter,
                "reading": (
                    f"{len(closed)} resolved observation{_s(len(closed))} against the "
                    f"{MIN_CLOSED} needed before a rate means anything, "
                    f"{len(open_obs)} still open. "
                    + _behind(picked, "selection", "picked", horizon)
                    + _one_draw(one_quarter, False, horizon)
                    + "This screen makes no predictive claim and cannot be "
                      "backtested; this is the only measurement it will ever get, "
                      "and it is not ready."),
            }
            continue

        one_quarter = _one_quarter((o.get("scannedOn") for o in closed), horizon)
        values = np.array([o["excess"] for o in closed], dtype="float64")
        out[flag] = {
            "available": True,
            **counts,
            "oneQuarter": one_quarter,
            "meanExcess": float(values.mean()),
            "medianExcess": float(np.median(values)),
            "positive": int((values > 0).sum()),
            "reading": (
                f"{len(closed)} resolved observations, {len(open_obs)} still open. "
                + _behind(picked, "selection", "picked", horizon)
                + f"The resolved ones: mean excess {values.mean() * 100:+.1f}%, "
                  f"median {np.median(values) * 100:+.1f}%, "
                  f"{int((values > 0).sum())} of {len(closed)} positive. "
                + _one_draw(one_quarter, True, horizon)
                + "No significance test is quoted: this is one screen on one market "
                  "with no control group, and the number is a record of what "
                  "happened rather than evidence it will happen again."),
        }
    return out


def summarise(resolved: Sequence[dict], horizon: int = HORIZON_DAYS) -> dict:
    """What the resolved observations add up to, or a refusal to say.

    NO HIT RATE UNDER `MIN_CLOSED`, AND THE FLOOR COUNTS OBSERVATIONS. The first
    ten resolved calls of anything are noise, and a percentage printed over them
    is how a method gets abandoned or trusted for no reason. The refusal names
    the count so the reader knows how far off it is rather than being told
    nothing. Both floors, `MIN_CLOSED` overall and a third of it per side, count
    `observations`: a name once per window, not once per scan that named it.

    THE ROWS ARE REPORTED BESIDE THE COUNT. `calls`, `names` and `scanDates`
    describe every directional call logged, resolved or not, so 74 calls on 23
    names sit next to the 23 that count. `oneQuarter` says whether the
    observations the reading is about (the resolved ones once a rate is quoted,
    all of them before that) were opened inside one window, and the reading says
    what that means. `open` counts observations too, and only directional ones:
    a HOLD still waiting on its horizon is not a call that is coming.

    `horizon` must be the one `resolve` was given. The windows come from each
    call's own `resolvedOn` and do not depend on it; the reading quotes it, and
    one quarter is measured in it.
    """
    calls = [row for row in resolved if row.get("action") in DIRECTIONAL]
    observed = observations(calls)
    closed = [o for o in observed if _resolved(o)]
    open_obs = [o for o in observed if not _resolved(o)]
    logged = {
        "calls": len(calls),
        "names": len({row.get("ticker") for row in calls}),
        "scanDates": _dates(calls),
    }

    if len(closed) < MIN_CLOSED:
        one_quarter = _one_quarter((o.get("scannedOn") for o in observed), horizon)
        return {
            "available": False,
            "closed": len(closed),
            "open": len(open_obs),
            "needed": MIN_CLOSED,
            **logged,
            "oneQuarter": one_quarter,
            "reading": (
                f"{len(closed)} resolved observation{_s(len(closed))} against the "
                f"{MIN_CLOSED} needed before a rate means anything, and "
                f"{len(open_obs)} still open. "
                + _behind(calls, "call", "called", horizon)
                + _one_draw(one_quarter, False, horizon)
                + "This is a slow instrument: it is the only honest way to measure "
                  "the components that cannot be reconstructed historically, and it "
                  "produces nothing until it has waited."),
        }

    buys = [o for o in closed if o["action"] in BUYS]
    sells = [o for o in closed if o["action"] in SELLS]

    def side(group: list[dict], expect: int) -> Optional[dict]:
        if len(group) < MIN_CLOSED // 3:
            return None
        values = np.array([o["excess"] for o in group], dtype="float64")
        return {
            # What every figure below is computed over: one per name per window.
            # `calls` is every call inside those windows, whatever it said.
            "observations": len(group),
            "names": len({o.get("ticker") for o in group}),
            "calls": sum(len(o["calls"]) for o in group),
            "meanExcess": float(values.mean()),
            "medianExcess": float(np.median(values)),
            # "Right" means the excess went the way the call implied. For a buy
            # that is positive; for a reduce or avoid, negative.
            "correct": int(np.sum(np.sign(values) == expect)),
            "hitRate": float(np.mean(np.sign(values) == expect)),
        }

    buy_side, sell_side = side(buys, 1), side(sells, -1)
    spread, leave_one_out = None, None
    if buy_side and sell_side:
        spread = buy_side["meanExcess"] - sell_side["meanExcess"]
        leave_one_out = _leave_one_out(buys, sells, spread)
    one_quarter = _one_quarter((o.get("scannedOn") for o in closed), horizon)

    return {
        "available": True,
        "closed": len(closed),
        "open": len(open_obs),
        **logged,
        "oneQuarter": one_quarter,
        "horizonDays": horizon,
        "buys": buy_side,
        "sells": sell_side,
        "spread": spread,
        "spreadLeaveOneOut": leave_one_out,
        "reading": _reading(closed, open_obs, calls, buy_side, sell_side, spread,
                            leave_one_out, one_quarter, horizon),
    }


def _leave_one_out(buys: list[dict], sells: list[dict],
                   spread: float) -> Optional[dict]:
    """The spread again with each name dropped in turn, and whether its sign held.

    The test §21 of the research roadmap fixed before the first read: a spread
    one company can reverse is that company, not an ordering. A name goes with
    every observation it has, on whichever side.
    """
    by_name: dict = {}
    for key, group in (("buys", buys), ("sells", sells)):
        for o in group:
            by_name.setdefault(o.get("ticker"), {"buys": [], "sells": []})[key].append(
                o["excess"])
    buy_total = sum(o["excess"] for o in buys)
    sell_total = sum(o["excess"] for o in sells)

    spreads = []
    for own in by_name.values():
        kept_buys, kept_sells = len(buys) - len(own["buys"]), len(sells) - len(own["sells"])
        if not kept_buys or not kept_sells:
            continue
        spreads.append((buy_total - sum(own["buys"])) / kept_buys
                       - (sell_total - sum(own["sells"])) / kept_sells)
    if not spreads:
        return None
    return {
        "lowest": float(min(spreads)),
        "highest": float(max(spreads)),
        "signHolds": bool(spread != 0
                          and all(np.sign(value) == np.sign(spread) for value in spreads)),
    }


def _across(side: dict) -> str:
    if side["observations"] == side["names"]:
        return f"{side['names']} name{_s(side['names'])}"
    return f"{side['observations']} observations on {side['names']} names"


def _reading(closed: list[dict], open_obs: list[dict], calls: list[dict],
             buy_side: Optional[dict], sell_side: Optional[dict],
             spread: Optional[float], leave_one_out: Optional[dict],
             one_quarter: bool, horizon: int) -> str:
    text = (f"{len(closed)} independent observations resolved at {horizon} sessions, "
            f"{len(open_obs)} still open. ")
    text += _behind(calls, "call", "called", horizon)
    if buy_side:
        text += (f"Buys averaged {buy_side['meanExcess'] * 100:+.1f}% against the market "
                 f"across {_across(buy_side)}, right {buy_side['hitRate'] * 100:.0f}% of "
                 f"the time. ")
    if sell_side:
        text += (f"Reduce and avoid averaged {sell_side['meanExcess'] * 100:+.1f}% across "
                 f"{_across(sell_side)}. ")
    if spread is not None:
        text += f"The gap between the two sides is {spread * 100:+.1f} points"
        if abs(spread) > 0:
            text += ", which is the number that says whether the ordering meant anything"
        if leave_one_out:
            text += (f"; dropping any one name moves it between "
                     f"{leave_one_out['lowest'] * 100:+.1f} and "
                     f"{leave_one_out['highest'] * 100:+.1f}")
            if not leave_one_out["signHolds"]:
                text += ", so its sign rests on a single name"
        text += ". "
    text += _one_draw(one_quarter, True, horizon)
    text += ("No significance is claimed here: the windows of different names overlap "
             "and the names are correlated, so a name counted once is still not an "
             "independent draw, and the count is what it is. It is a record, not a "
             "study.")
    return text
