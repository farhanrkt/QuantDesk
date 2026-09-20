#!/usr/bin/env python3
"""
review_scanlog.py
=================
What the scanner said, and what has happened since.

    python scripts/review_scanlog.py --market ID

DELIBERATELY OUTSIDE CI. It reaches the network to price what the log recorded,
and it will say nothing useful for months — which is the nature of the
instrument rather than a fault in it. See `_lib/scanlog.py` for why this exists
at all: five of the nine components in the verdict score cannot be reconstructed
on a past date, so the only honest way to measure them is to write down what the
scanner said on the day it said it and wait.

IT REFUSES TO QUOTE A RATE UNDER THIRTY RESOLVED CALLS, and that refusal is the
whole point. The first ten resolved calls of any method are noise, and reading
them is how a method gets abandoned or trusted for no reason.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

from _lib import market_data, riskmodel, scanlog                     # noqa: E402

REPORT_DIR = ROOT / "reports"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--market", default="ID", choices=["ID", "US"])
    parser.add_argument("--horizon", type=int, default=scanlog.HORIZON_DAYS,
                        help=f"Sessions before a call resolves "
                             f"(default {scanlog.HORIZON_DAYS}).")
    args = parser.parse_args()

    rows = scanlog.read(REPORT_DIR, args.market)
    if not rows:
        print(f"No scan log for {args.market}. Run scripts/scan_market.py first; "
              f"the log is written as a side effect of every scan.")
        return 0

    dates = sorted({row["scannedOn"] for row in rows})
    tickers = sorted({row["ticker"] for row in rows})
    print(f"{len(rows)} calls across {len(dates)} scans "
          f"({dates[0]} to {dates[-1]}), {len(tickers)} distinct names.")

    earliest = dt.date.fromisoformat(dates[0]) - dt.timedelta(days=10)
    print(f"Pricing {len(tickers)} names from {earliest} ...", flush=True)
    frames = market_data.ohlcv_batch(tickers, earliest, dt.date.today())
    prices = {symbol: frame["Close"].astype("float64")
              for symbol, frame in frames.items()}

    benchmark_symbol = riskmodel.MARKET_INDEX.get(args.market, "^GSPC")
    index_frames = market_data.ohlcv_batch([benchmark_symbol], earliest,
                                           dt.date.today())
    benchmark = (index_frames[benchmark_symbol]["Close"].astype("float64")
                 if benchmark_symbol in index_frames else None)

    resolved = scanlog.resolve(rows, prices, benchmark=benchmark,
                               horizon=args.horizon)
    summary = scanlog.summarise(resolved)

    print()
    print(summary["reading"])

    # THE SCREENS, EACH REFUSING ON ITS OWN COUNT. `scanlog.record` writes down
    # which names each screen picked on the day it picked them, because nothing
    # about them can be reconstructed afterwards — the filings come back
    # restated and the share register and industry labels have no history at
    # all. For a while it wrote that down and nothing read it back, which is the
    # same defect one layer up.
    #
    # Not pooled to reach the threshold sooner: a screen selecting seven names a
    # sweep gets to thirty resolved calls long after the blended score does, and
    # averaging them together would measure neither.
    print()
    print("Screens, each measured on its own selections:")
    for flag, block in scanlog.summarise_screens(resolved).items():
        print(f"  {flag}: {block['reading']}")

    if summary["available"]:
        print()
        closed = [r for r in resolved if not r.get("open") and r.get("excess") is not None]
        closed.sort(key=lambda r: -(r["excess"] or 0))
        print(f"{'TICKER':<11}{'CALLED':>12}{'SCORE':>7}{'EXCESS':>9}  SCANNED")
        print("-" * 60)
        for row in closed[:10] + (["..."] if len(closed) > 20 else []) + closed[-10:]:
            if row == "...":
                print("...")
                continue
            print(f"{row['ticker']:<11}{row['action'].replace('_', ' ').title():>12}"
                  f"{row['score']:>7.1f}{row['excess'] * 100:>8.1f}%  {row['scannedOn']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
