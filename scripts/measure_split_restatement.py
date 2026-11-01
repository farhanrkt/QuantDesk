#!/usr/bin/env python3
"""
measure_split_restatement.py
============================
Which names did an unrestated share count misread, and what does restating it
for splits change?

WHY
---
The provider's share-count series is not restated for splits. NVDA's 10-for-1
of June 2024 arrived as a +900% step, `ownership.issuance` read it as a share
count growing 121% a year, and the heavy-issuance gate fired on a company that
had issued almost nothing. `ownership.split_adjusted` now restates every count
in today's shares. This reads each name twice — on the counts as the provider
sends them, and restated — through the same boundary the app and the scanner
use (`market_data.share_register`), and prints every name whose reading moved.

    python scripts/measure_split_restatement.py                    # the four index universes
    python scripts/measure_split_restatement.py --tickers NVDA,AVGO,WMT,CMG

Live data: the counts and splits are whatever the provider returns today.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from _lib import market_data, ownership, symbols, universes

DEFAULT_UNIVERSES = ("dow30", "nasdaq100", "idx30", "lq45")


def read_both(symbol: str) -> dict:
    register = market_data.share_register(symbol)
    raw = ownership.issuance({**register, "splits": None})
    restated = ownership.issuance(register)
    return {"symbol": symbol, "splits": register.get("splits") or [],
            "raw": raw, "restated": restated}


def gated(result: dict) -> bool:
    """The condition `verdict.py` gates on: a severe annualised rise."""
    annual = result.get("annualised") if result.get("available") else None
    return annual is not None and annual >= ownership.ISSUANCE_SEVERE


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--tickers", help="comma-separated symbols instead of the universes")
    args = parser.parse_args()

    if args.tickers:
        names = [s.strip().upper() for s in args.tickers.split(",") if s.strip()]
    else:
        names = list(dict.fromkeys(
            symbols.resolve(ticker, universes.UNIVERSES[key]["market"])
            for key in DEFAULT_UNIVERSES for ticker in universes.UNIVERSES[key]["tickers"]))

    rows = [read_both(name) for name in names]
    readable = [row for row in rows if row["raw"].get("available")]
    moved = [row for row in readable if row["restated"].get("splitsRestated")]

    print(f"{len(names)} names, {len(readable)} with a readable share-count trend, "
          f"{len(moved)} with a split restated inside it.")
    print(f"Heavy-issuance gate condition: {sum(gated(r['raw']) for r in readable)} "
          f"unrestated, {sum(gated(r['restated']) for r in readable)} restated.\n")
    print(f"{'name':<10} {'split':<26} {'raw a year':>10} {'restated':>9} "
          f"{'raw step':>9} {'restated':>9}  band")
    for row in moved:
        raw, restated = row["raw"], row["restated"]
        named = ", ".join(f"{s['date']} x{s['ratio']:g}" for s in restated["splitsRestated"])
        print(f"{row['symbol']:<10} {named:<26} {raw['annualised'] * 100:>9.1f}% "
              f"{restated['annualised'] * 100:>8.1f}% "
              f"{(raw['largestStep'] or 0) * 100:>8.0f}% "
              f"{(restated['largestStep'] or 0) * 100:>8.0f}%  "
              f"{raw['band']} -> {restated['band']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
