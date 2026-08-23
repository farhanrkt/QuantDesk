#!/usr/bin/env python3
"""
check_data_invariants.py
========================
Hunt for the class of bug that produces a PLAUSIBLE WRONG NUMBER and no error.

WHY THIS IS A SCRIPT AND NOT A TEST
-----------------------------------
The pytest suite is offline by design, and offline is exactly what cannot find
this. These bugs live in the units and conventions of live upstream data:

  * ITMG.JK keeps its accounts in USD while its shares trade in IDR, so the
    model discounted dollar cash flows and printed the answer with a rupiah
    symbol. Thirteen of the forty-six names in IDX30 and LQ45 do this. Median
    fair value came out at Rp 4 against a Rp 25,200 share price, and nothing
    raised so much as a warning.
  * Yahoo publishes `dividendYield` as a PERCENTAGE and
    `trailingAnnualDividendYield` as a FRACTION. One heuristic read AAPL's 0.35
    as a 35% yield rather than 0.34% — a hundredfold error, silently.

Neither was reachable from synthetic data, because synthetic data is written by
someone who already believes they know the units. Both were found by asserting
relationships that must hold for every real company and seeing which broke.

EVERY CHECK BELOW CALLS THE APP'S OWN CODE rather than reimplementing it. A
checker that re-derives the conversion it is auditing agrees with itself and
proves nothing.

REQUIRES THE NETWORK, so it is deliberately NOT part of CI — an upstream outage
must never redden the build. Run it by hand after touching anything that reads a
field from the data source, and read the distributions at the end: a field that
is mis-scaled for EVERY company shows up there rather than as an outlier.

USAGE
    python scripts/check_data_invariants.py [--limit N]
"""

from __future__ import annotations

import argparse
import contextlib
import io
import math
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

import pandas as pd  # noqa: E402

from _lib import market_data as MD  # noqa: E402
from _lib import universes as U  # noqa: E402
from _lib import valuation as V  # noqa: E402


def finite(x) -> bool:
    try:
        return math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


def inspect_company(ticker: str) -> dict:
    """Every invariant, for one company. `flags` is what a human should read."""
    out: dict = {"ticker": ticker, "flags": []}
    try:
        data = MD.company(ticker)
    except Exception as exc:
        out["flags"].append(("fetch", type(exc).__name__))
        return out

    price, shares, cap = data["price"], data["shares"], data["market_cap"]
    out["ccy"], out["fccy"], out["fx"] = (
        data["currency"], data["financial_currency"], data["fx_rate"])

    # 1. Price x shares must reconcile with the reported market capitalisation.
    #    Catches a wrong share count, and a market cap in the other currency.
    if finite(price) and finite(shares) and finite(cap) and float(cap) > 0:
        ratio = (float(price) * float(shares)) / float(cap)
        out["cap_ratio"] = ratio
        if not 0.85 <= ratio <= 1.18:
            out["flags"].append(("market cap", f"price x shares / cap = {ratio:.3f}"))

    # 2. The dividend the app RESOLVES must match what the company actually paid.
    #    Runs the real chain, so a convention error anywhere in it surfaces here.
    ttm = data.get("ttm_dividend")
    if finite(ttm) and finite(price) and float(price) > 0:
        stripped = dict(data, ttm_dividend=float("nan"))   # force the fallbacks
        derived, how = V.resolve_dividend(stripped, float(price))
        if finite(derived) and float(derived) > 0:
            ratio = float(derived) / float(ttm)
            out["dividend_ratio"] = ratio
            if not 0.4 <= ratio <= 2.5:
                out["flags"].append(
                    ("dividend", f"resolved {derived:,.4f} ({how}) vs paid {float(ttm):,.4f}"))

    # 3. Ratio-shaped fields must look like ratios, not percentages.
    for key, low, high in (("payout_ratio", -0.1, 3.0), ("roe_info", -2.0, 2.0)):
        value = data.get(key)
        if finite(value) and not low <= float(value) <= high:
            out["flags"].append((key, f"{float(value):.4f} outside [{low}, {high}]"))

    # 4. Statement magnitudes must be commensurate with the market cap. A
    #    currency or units error moves these by orders of magnitude.
    if finite(cap) and float(cap) > 0:
        try:
            fcf = V.build_fcf_history(data["cashflow"])
            if not fcf.empty and "Free Cash Flow" in fcf.columns:
                value = float(fcf["Free Cash Flow"].iloc[0])
                if value != 0:
                    ratio = abs(value) / float(cap)
                    out["fcf_over_cap"] = ratio
                    if ratio > 1.5 or ratio < 1e-4:
                        out["flags"].append(("FCF scale", f"|FCF| / cap = {ratio:.2e}"))
        except Exception as exc:
            out["flags"].append(("fcf", type(exc).__name__))

        equity = V._first_valid(V._get_row(data["balance"], "equity"), float("nan"))
        if finite(equity) and float(equity) != 0:
            ratio = abs(float(equity)) / float(cap)
            out["equity_over_cap"] = ratio
            if ratio > 25 or ratio < 1e-3:
                out["flags"].append(("equity scale", f"|equity| / cap = {ratio:.2e}"))

    # 5. After the boundary, the statements and the shares share a currency.
    if data["financial_currency"] and data["currency"] \
            and data["financial_currency"] != data["currency"] and not data["fx_rate"]:
        out["flags"].append(
            ("currency", f"{data['financial_currency']} vs {data['currency']}, no rate"))

    # 6. Statements this old are describing a different company.
    latest = None
    for key in ("income", "balance", "cashflow"):
        frame = data.get(key)
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            with contextlib.suppress(Exception):
                newest = max(pd.to_datetime(list(frame.columns)))
                latest = newest if latest is None or newest > latest else latest
    if latest is not None:
        age = (pd.Timestamp.today().normalize() - latest.normalize()).days
        out["statement_age"] = age
        if age > 550:
            out["flags"].append(("stale filings", f"{age} days old"))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=40,
                        help="how many companies to sample (default 40)")
    args = parser.parse_args()

    indonesian = sorted({t for u in ("idx30", "lq45") for t in U.get(u)["tickers"]})
    american = U.get("dow30")["tickers"]
    half = max(1, args.limit // 2)
    names = american[:half] + indonesian[:args.limit - half]

    # yfinance narrates its failures to stdout; the report is the output here.
    noise = io.StringIO()
    with contextlib.redirect_stdout(noise), contextlib.redirect_stderr(noise):
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(inspect_company, names))

    flagged = [r for r in results if r["flags"]]
    print(f"{len(results)} companies checked against 6 invariants\n")
    for row in flagged:
        print(f"  {row['ticker']:10} {row.get('ccy', '?')}/{row.get('fccy') or '-'}"
              f"{'  fx ' + format(row['fx'], ',.0f') if row.get('fx') else ''}")
        for what, why in row["flags"]:
            print(f"      {what:16} {why}")
    print(f"\n{len(flagged)} of {len(results)} tripped at least one invariant.\n")

    print("distributions — a field mis-scaled for EVERYONE shows up here, not above:")
    for key in ("cap_ratio", "dividend_ratio", "fcf_over_cap",
                "equity_over_cap", "statement_age"):
        values = sorted(float(r[key]) for r in results
                        if finite(r.get(key)))
        if values:
            print(f"  {key:16} n={len(values):3}  min={values[0]:<10.4g} "
                  f"median={statistics.median(values):<10.4g} max={values[-1]:.4g}")
    return 1 if flagged else 0


if __name__ == "__main__":
    raise SystemExit(main())
