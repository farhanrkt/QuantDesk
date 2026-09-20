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

# Below this many resolved calls, a hit rate is noise wearing a percentage sign.
# Thirty is the floor `pretrade`, `calibrate_tape` and `calibrate_patterns` all
# use, and the argument is identical: a rate quoted from twenty observations
# describes the twenty.
MIN_CLOSED = 30

# How long a call is given before it is resolved. A quarter, matching the
# longest horizon anything else in this app measures at.
HORIZON_DAYS = 63

# Actions worth measuring. HOLD is excluded deliberately — it is what the
# scanner says when it has nothing to say, so scoring it would measure the
# market rather than the scanner.
DIRECTIONAL = {"STRONG_BUY", "BUY", "REDUCE", "AVOID"}


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


def summarise(resolved: Sequence[dict]) -> dict:
    """What the closed calls add up to, or a refusal to say.

    NO HIT RATE UNDER `MIN_CLOSED`. The first ten resolved calls of anything are
    noise, and a percentage printed over them is how a method gets abandoned or
    trusted for no reason. The refusal names the count so the reader knows how
    far off it is rather than being told nothing.
    """
    closed = [row for row in resolved if not row.get("open")
              and row.get("excess") is not None
              and row.get("action") in DIRECTIONAL]
    open_calls = [row for row in resolved if row.get("open")]

    if len(closed) < MIN_CLOSED:
        return {
            "available": False,
            "closed": len(closed),
            "open": len(open_calls),
            "needed": MIN_CLOSED,
            "reading": (
                f"{len(closed)} resolved call{'' if len(closed) == 1 else 's'} against "
                f"the {MIN_CLOSED} needed before a rate means anything, and "
                f"{len(open_calls)} still open. This is a slow instrument: it is the "
                f"only honest way to measure the components that cannot be "
                f"reconstructed historically, and it produces nothing until it has "
                f"waited."),
        }

    buys = [row for row in closed if row["action"] in ("BUY", "STRONG_BUY")]
    sells = [row for row in closed if row["action"] in ("REDUCE", "AVOID")]

    def side(rows: list[dict], expect: int) -> Optional[dict]:
        if len(rows) < MIN_CLOSED // 3:
            return None
        values = np.array([row["excess"] for row in rows], dtype="float64")
        return {
            "calls": len(rows),
            "meanExcess": float(values.mean()),
            "medianExcess": float(np.median(values)),
            # "Right" means the excess went the way the call implied. For a buy
            # that is positive; for a reduce or avoid, negative.
            "correct": int(np.sum(np.sign(values) == expect)),
            "hitRate": float(np.mean(np.sign(values) == expect)),
        }

    buy_side, sell_side = side(buys, 1), side(sells, -1)
    spread = None
    if buy_side and sell_side:
        spread = buy_side["meanExcess"] - sell_side["meanExcess"]

    return {
        "available": True,
        "closed": len(closed),
        "open": len(open_calls),
        "horizonDays": HORIZON_DAYS,
        "buys": buy_side,
        "sells": sell_side,
        "spread": spread,
        "reading": _reading(len(closed), len(open_calls), buy_side, sell_side, spread),
    }


def _reading(closed: int, open_calls: int, buy_side: Optional[dict],
             sell_side: Optional[dict], spread: Optional[float]) -> str:
    text = (f"{closed} calls resolved at {HORIZON_DAYS} sessions, {open_calls} still "
            f"open. ")
    if buy_side:
        text += (f"Buys averaged {buy_side['meanExcess'] * 100:+.1f}% against the market "
                 f"across {buy_side['calls']}, right {buy_side['hitRate'] * 100:.0f}% of "
                 f"the time. ")
    if sell_side:
        text += (f"Reduce and avoid averaged {sell_side['meanExcess'] * 100:+.1f}% across "
                 f"{sell_side['calls']}. ")
    if spread is not None:
        text += (f"The gap between the two sides is {spread * 100:+.1f} points"
                 + (", which is the number that says whether the ordering meant "
                    "anything." if abs(spread) > 0 else "."))
    text += (" No significance is claimed here: these are overlapping windows on "
             "correlated names, and the count is what it is. It is a record, not a "
             "study.")
    return text
