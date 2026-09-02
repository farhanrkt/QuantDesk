"""
portfolio.py
============
How a candidate sits against what is already owned.

THE FAILURE THIS ADDRESSES
--------------------------
Every other lens in this app evaluates one ticker in isolation, which hides the
most common way a retail portfolio goes wrong: the candidate is the fourth copy
of a bet already held. Four names that each look independently reasonable and
all move together are one position with four ticker symbols on it, and nothing
on a single-ticker page can say so.

WHY THIS ONE IS ALLOWED TO INFORM POSITION SIZE
------------------------------------------------
Reporting that a candidate correlated 0.82 with a holding over the past year is
a description of history. Using it to decide how much to buy is a claim about
the future — that last year's correlation is informative about next year's — and
this codebase does not ship those unmeasured. The ranking tier carries its own
null result for precisely this reason.

So it was measured first, by `scripts/measure_correlation_stability.py`, and the
answer is the reason this feature exists in the shape it does: over a one-year
window the rank correlation between one period's pairwise correlations and the
next period's runs **0.50 to 0.65** across four index universes, at t-statistics
between +9.5 and +15.7. That is a different world from the composite ranking,
where the information coefficient was indistinguishable from zero. Correlations
are among the few things about equities that are genuinely persistent, and that
is what licenses them to inform size where a return forecast may not.

THE SAME MEASUREMENT FOUND THE LIMIT, AND THE PANEL CARRIES IT
---------------------------------------------------------------
In the worst quarter of quarters for those markets the mean pairwise correlation
runs about **0.06 higher** than in the rest — up to 0.12 on the LQ45. So a
correlation measured over an ordinary year is a FLOOR on how correlated these
positions will be in the stretch a holder actually needs the diversification.
Every number here is reported with that stated rather than as a precise input.

WHAT IT COMPUTES, AND WHAT IT REFUSES TO
----------------------------------------
Descriptions of a historical covariance matrix, and nothing else:

  * the candidate's correlation with each holding, and with the book as a whole
  * how many INDEPENDENT positions the holdings really amount to, before and
    after adding the candidate — the participation ratio, which is the same
    estimator `ranking.py` uses to say seven correlated signals carry about 3.4
    signals' worth of information
  * what share of the portfolio's risk each position accounts for, against what
    share of its money — the gap between those two is the whole point

It does NOT produce a recommended weight. Risk contribution and money
contribution diverging is the finding; what to do about it depends on why the
positions are held, which this app does not know and does not ask.

NO STATE, AND WHAT THAT COSTS
-----------------------------
Holdings never touch this server's storage — there is none. They arrive as a
query parameter, are used, and are forgotten, exactly as the ranking tier's
pasted universe already is. Two consequences are stated rather than glossed:
the list travels in a URL and therefore appears in the hosting platform's access
logs, and this route sets `no-store` so no shared cache keeps a copy. Nothing
about a portfolio ever reaches the analytics event, which carries a market code
and a count and has never carried a ticker.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
import pandas as pd

from . import exposure, market_data, riskmodel

# One year of daily returns. Not a free choice: it is the window whose
# persistence was measured, so it is the only one whose stability this app can
# quote a number for. A shorter window is noisier and a longer one describes a
# book the reader may no longer hold.
WINDOW_DAYS = 252

# Below this, a correlation is an anecdote. Ninety trading days is a quarter,
# which is the shortest window the stability script found usable.
MIN_OVERLAP = 90

# Where a pair stops being diversification and starts being one position with
# two names on it. Not a published constant — a reading threshold, and the panel
# says so. It is set where the second name stops meaningfully reducing the
# variance of the pair: at rho = 0.8 two equally sized positions carry 90% of
# the variance one double-sized position would.
HIGH_CORRELATION = 0.80
MODERATE_CORRELATION = 0.60

STABILITY_PATH = Path(__file__).with_name("correlation_stability.json")


def load_stability(path: Path = STABILITY_PATH) -> Optional[dict]:
    """The measured persistence of correlations, or None if never measured.

    Served from a stamped file for the same reason the ranking backtest and the
    check calibration are: it is a research finding about the method rather than
    a per-user computation, and a figure that decays slowly should be dated
    rather than recomputed on every request.
    """
    try:
        payload = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) and payload.get("universes") else None


def _finite(value) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if np.isfinite(out) else None


def daily_returns(frames: dict, window: int = WINDOW_DAYS) -> pd.DataFrame:
    """Aligned daily log returns over the trailing window, one column per name.

    Aligned on the shared calendar, so a name that does not trade on a given day
    contributes nothing to that day rather than carrying its neighbour's move.
    That matters here more than elsewhere: a US holding and an IDX one share
    perhaps half their sessions, and a naive join would manufacture correlation
    out of the mismatch.
    """
    closes = pd.DataFrame({
        symbol: frame["Close"].astype("float64")
        for symbol, frame in frames.items() if len(frame)
    }).sort_index()
    returns = np.log(closes / closes.shift(1))
    return returns.tail(window)


def _correlation_matrix(returns: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Pairwise correlations over the names with enough overlapping days."""
    usable = [c for c in returns.columns if returns[c].notna().sum() >= MIN_OVERLAP]
    if len(usable) < 2:
        return pd.DataFrame(), usable
    return returns[usable].corr(min_periods=MIN_OVERLAP), usable


def _band(value: float) -> str:
    if value >= HIGH_CORRELATION:
        return "high"
    if value >= MODERATE_CORRELATION:
        return "moderate"
    return "low"


def risk_contributions(matrix: pd.DataFrame, volatility: pd.Series,
                       weights: pd.Series) -> dict:
    """Each position's share of portfolio risk, against its share of the money.

    Standard decomposition and no more than that: with covariance S and weights
    w, portfolio volatility is sqrt(w'Sw) and position i contributes
    w_i (Sw)_i / (w'Sw) of it. The contributions sum to one by construction,
    which is what makes the comparison against the money weights readable.

    THE GAP BETWEEN THE TWO IS THE FINDING. A position holding 10% of the money
    and carrying 25% of the risk is not diversified by being one of ten; it is
    the portfolio wearing a smaller number.
    """
    names = list(matrix.columns)
    sigma = volatility.reindex(names).to_numpy(dtype="float64")
    w = weights.reindex(names).fillna(0.0).to_numpy(dtype="float64")
    total = w.sum()
    if total <= 0 or not np.all(np.isfinite(sigma)):
        return {"usable": False, "reason": "No usable weights or volatilities."}

    w = w / total
    covariance = matrix.to_numpy(dtype="float64") * np.outer(sigma, sigma)
    variance = float(w @ covariance @ w)
    if not np.isfinite(variance) or variance <= 0:
        return {"usable": False, "reason": "Portfolio variance could not be computed."}

    marginal = covariance @ w
    shares = (w * marginal) / variance
    return {
        "usable": True,
        "portfolioVolatility": float(np.sqrt(variance)),
        "rows": [
            {"ticker": name, "weight": float(w[i]), "riskShare": float(shares[i]),
             "volatility": float(sigma[i]),
             # Positive means the position carries more of the risk than of the
             # money, which is the only comparison worth making here.
             "excess": float(shares[i] - w[i])}
            for i, name in enumerate(names)
        ],
    }


def analyse(candidate: str, holdings: Sequence[str],
            weights: Optional[dict] = None,
            window: int = WINDOW_DAYS,
            market_code: str = "US") -> dict:
    """Where a candidate sits against a book, from one batched download.

    Price only, so it batches — a twenty-name portfolio is one upstream call,
    not twenty. The fundamentals lenses do not batch, which is why there is no
    quality or valuation dimension here and the panel says so.

    THE REFERENCE SERIES RIDE ALONG IN THE SAME CALL. `exposure` needs a market
    index and four futures to name what a book has in common; appending five
    symbols to a download already being made costs one chunk rather than a
    second round trip, and they are filtered back out before anything here
    correlates holdings against each other.
    """
    symbols = list(dict.fromkeys([candidate, *holdings]))
    references = exposure.reference_symbols(market_code)
    end = dt.date.today()
    # Calendar days, generously, so the window survives holidays and a market
    # that trades fewer sessions than the US one.
    start = end - dt.timedelta(days=int(window * 1.9) + 30)
    frames = market_data.ohlcv_batch(symbols + references, start, end)
    reference_frames = {s: f for s, f in frames.items()
                        if s in references and s not in symbols}
    frames = {s: f for s, f in frames.items() if s in symbols}

    returns = daily_returns(frames, window=window)
    matrix, usable = _correlation_matrix(returns)

    missing = [s for s in symbols if s not in usable]
    if candidate not in usable:
        return {
            "usable": False,
            "reason": (f"{candidate} has fewer than {MIN_OVERLAP} trading days in common "
                       f"with the last {window} sessions, so no correlation against it "
                       f"means anything."),
            "missing": missing,
        }

    held = [s for s in usable if s != candidate]
    if not held:
        return {
            "usable": False,
            "reason": ("None of the holdings had enough overlapping history to correlate "
                       "against. Check the symbols, including their exchange suffixes."),
            "missing": missing,
        }

    volatility = returns[usable].std(ddof=1) * np.sqrt(252)

    # --- the candidate against each holding ------------------------------
    pairs = []
    for name in held:
        value = _finite(matrix.loc[candidate, name])
        if value is None:
            continue
        overlap = int((returns[candidate].notna() & returns[name].notna()).sum())
        pairs.append({"ticker": name, "correlation": value, "band": _band(value),
                      "overlapDays": overlap})
    pairs.sort(key=lambda row: -row["correlation"])

    # --- how many independent bets, before and after ---------------------
    before = riskmodel.effective_independent(matrix.loc[held, held].to_numpy("float64"))
    after = riskmodel.effective_independent(
        matrix.loc[usable, usable].to_numpy("float64"))

    # --- risk against money ----------------------------------------------
    supplied = {k.upper(): v for k, v in (weights or {}).items()}
    equal_weight = not supplied
    money = pd.Series(
        {name: float(supplied.get(name.upper(), 1.0)) for name in usable},
        dtype="float64")
    contributions = risk_contributions(matrix, volatility, money)

    # --- what the book has in common, named where it can be --------------
    #
    # ON THE FULL FETCHED WINDOW, NOT THE TRAILING 252 DAYS. Those are different
    # questions and they want different samples. The correlation window is 252
    # because that is the length whose PERSISTENCE was measured, and quoting a
    # number from any other window would be quoting a stability this app has not
    # established. Naming a shared direction makes no persistence claim at all —
    # it describes what these names did — so it uses everything fetched, which
    # is about seventy weeks against the fifty-two a one-year window would give.
    driver = exposure.analyse(
        daily_returns(frames, window=10 ** 6),
        daily_returns(reference_frames, window=10 ** 6) if reference_frames
        else pd.DataFrame(),
        market_code=market_code,
    )

    stability = load_stability()
    return {
        "driver": driver,
        "usable": True,
        "candidate": candidate,
        "holdings": held,
        "missing": missing,
        "windowDays": window,
        "equalWeighted": equal_weight,
        "observations": len(returns),
        "pairs": pairs,
        "portfolioCorrelation": _finite(
            np.mean([p["correlation"] for p in pairs]) if pairs else None),
        "independence": {
            "before": before, "after": after,
            "holdings": len(held), "withCandidate": len(usable),
            "gain": (after - before) if (before is not None and after is not None) else None,
        },
        "contributions": contributions,
        "volatility": {name: float(volatility[name]) for name in usable
                       if np.isfinite(volatility[name])},
        "stability": ({
            "measuredOn": stability.get("measuredOn"),
            "headline": stability.get("headline"),
            "yearlyPersistence": stability.get("yearlyPersistence"),
            "stressRise": stability.get("stressRise"),
            "caveats": stability.get("caveats"),
        } if stability else None),
    }
