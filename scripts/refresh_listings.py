#!/usr/bin/env python3
"""
refresh_listings.py
===================
Fetch the current listed universe for a market and write it to `api/_lib/`.

DELIBERATELY OUTSIDE CI, like the other six network scripts in this directory.
It reaches the provider, it writes a dated artifact, and a stale stamped number
is worse than none — so it runs when somebody decides the universe has moved,
not on every push.

    python scripts/refresh_listings.py --market ID
    python scripts/refresh_listings.py --market ID --market US

Run this before the first scan, and again when a scan's own report says the
universe is stale.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from _lib import listings
from _lib.market_data import MarketDataError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--market", action="append", default=None,
                        choices=["ID", "US"],
                        help="Market to refresh. Repeatable. Defaults to ID.")
    args = parser.parse_args()

    markets = args.market or ["ID"]
    failed = False
    for market in markets:
        print(f"Fetching the listed universe for {market} ...", flush=True)
        try:
            payload = listings.refresh(market)
        except MarketDataError as exc:
            print(f"  FAILED: {exc}", file=sys.stderr)
            failed = True
            continue
        capitalised = [r for r in payload["rows"] if r.get("marketCap")]
        print(f"  {payload['count']} equities, as of {payload['asOf']}")
        print(f"  {len(capitalised)} carry a market capitalisation; "
              f"{payload['count'] - len(capitalised)} do not")
        print(f"  written to {listings.path_for(market)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
