"""
basket.py
=========
How many bets a buy list actually is.

THE ERROR THIS EXISTS TO FIX, AND THE ONE IT CAUGHT ON ITS FIRST RUN
----------------------------------------------------------------------
The scanner ranks every name on its own merits and hands over a list.
`verdict._sizing` then sizes each one by inverse volatility, which is the right
arithmetic for INDEPENDENT positions and the wrong arithmetic otherwise. Whether
it is wrong here is a property of the SET, invisible from any row, and nothing
in the app computed it.

On a real Indonesian sweep the list was sixteen names of which nine were
commodity-linked by label — three palm oil producers, a poultry-feed group, a
coal miner, a nickel miner, an oil-services contractor, a petrochemical
producer, a fuel distributor. Reading those labels, the obvious conclusion is
that sixteen tickets are being written on about four bets.

MEASURED, THAT CONCLUSION IS WRONG. Those sixteen names span about EIGHT
independent bets on weekly returns: mean pairwise correlation +0.23, the highest
pair +0.58, and the two palm oil producers correlate 0.53 — real, but not one
position. Half the list's length is repetition and half of it is genuine
diversification, which is a different finding from the one the sector labels
suggest and the opposite of what a reader would assume.

That is the whole argument for computing this rather than eyeballing it, and it
is why the module reports the number instead of a warning.

WEEKLY RETURNS ARE THE HEADLINE, DAILY ARE REPORTED BESIDE THEM
----------------------------------------------------------------
Non-synchronous trading attenuates daily correlations — two thinly traded names
that genuinely move together do not print on the same minutes, so a daily
correlation understates the co-movement and flatters the diversification. The
Epps effect is exactly the failure this measurement is most vulnerable to, since
its whole job is to warn about concentration.

On the sixteen-name list above, daily returns give 9.2 effective bets and weekly
returns give 7.8. Both are reported so the size of the attenuation is visible;
the weekly figure is the one the prose quotes, and it is the frequency
`exposure.py` already uses for the same reason.

WHAT IT COMPUTES, AND WHY THESE TWO NUMBERS
--------------------------------------------
EFFECTIVE BETS is the participation ratio of the correlation matrix's
eigenvalues — the same estimator `ranking.signal_correlation` uses to ask how
many opinions a composite is really averaging, and `portfolio.py` to ask how
many independent positions a book really holds. It equals the name count when
everything moves separately and collapses toward 1 as they move together. It
answers "how many bets are available here", and it does not depend on the
weights.

DIVERSIFICATION RATIO answers the other half: how much of that the weights
actually capture. It is the weighted average volatility divided by the
portfolio's own volatility (Choueifaty & Coignard 2008). At 1.0 the weights have
bought nothing — the portfolio is as volatile as its parts. The gap between the
two numbers is the difference between diversification that exists and
diversification that has been taken.

WHAT IT DOES NOT DO
-------------------
1. IT DOES NOT RE-SCORE ANYTHING. Concentration is a fact about a list, not
   about a company, and marking a name down for the company it keeps would put
   a portfolio property into a per-name score where no reader could find it.

2. IT DOES NOT PICK THE LIST. Dropping the most redundant name would be
   portfolio construction, which needs to know what is already owned, what the
   holder's tax position is and how much they have — none of which this app
   knows. It reports; the reader decides.

3. IT DOES NOT CLAIM CORRELATIONS PERSIST. `correlation_stability.json` is the
   measurement of that, it is already stamped, and `persistence_context` is
   carried through so the reader sees how much a one-year correlation is worth
   before acting on this.

References
----------
Choueifaty, Y., & Coignard, Y. (2008). "Toward Maximum Diversification."
    Journal of Portfolio Management 35(1). (The diversification ratio.)
Meucci, A. (2009). "Managing Diversification." Risk 22(5). (Effective number of
    bets as a participation ratio.)
"""

from __future__ import annotations

from typing import Optional, Sequence

import numpy as np
import pandas as pd

from . import riskmodel

# TWO years of daily returns, and this is the one window in the app that is
# deliberately LONGER than `ranking.RANK_WINDOW`.
#
# A percentile estimates one number per name. A correlation matrix estimates
# n(n-1)/2 of them — for a sixteen-name buy list that is 120 parameters — and a
# year of weekly returns is 52 observations. The matrix is then estimated on
# fewer observations than it has parameters, its small eigenvalues are noise,
# and the participation ratio built from them overstates the number of
# independent bets. At 252 days the first real run reported 55 weeks and
# flagged itself thin on every single scan, which is a constant warning nobody
# reads rather than a measurement.
#
# Two years gives about 104 weekly observations against those 120 parameters.
# Still not comfortable — the reading says so whenever it is under eighty — but
# it is the longest window over which a correlation is plausibly describing the
# same companies.
WINDOW = 504

# Below this many overlapping observations a correlation is not a measurement.
MIN_OBSERVATIONS = 120

# And below this many overlapping WEEKS, which is the frequency the headline is
# quoted at. Forty weeks against a matrix of up to a few dozen names is already
# thin — the estimate is noisy and the reading says so — but under it the
# eigenvalues are describing the sample rather than the market.
MIN_WEEKS = 40

# Two names count as linked when their weekly returns correlate above this.
#
# JUDGEMENT, AND SET AFTER LOOKING AT THE DISTRIBUTION RATHER THAN BEFORE.
# There is no correlation at which two stocks become "the same bet" — the
# quantity is continuous and this line exists to make the grouping legible, not
# because 0.44 and 0.46 differ in kind. It was first written as 0.60, which on a
# real IDX buy list sat ABOVE THE ENTIRE OBSERVED DISTRIBUTION (mean +0.23,
# maximum +0.58): every name formed its own cluster and the output said nothing.
# A threshold that never binds is not conservative, it is broken.
#
# The EFFECTIVE BET COUNT uses no threshold at all, which is why that is the
# headline and this is the illustration. `clusterSensitivity` prints the
# grouping a decimal either side so a reader can see how much the line is doing.
CLUSTER_LINK = 0.45
CLUSTER_SENSITIVITY = (0.35, 0.55)

# Below this share of its names, a list is doing much less diversifying than its
# length suggests — sixteen names spanning four bets is 0.25. Used only to pick
# which sentence to print.
CONCENTRATED_BELOW = 0.45


def _finite(value) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if np.isfinite(out) else None


def returns_matrix(frames: dict, tickers: Sequence[str],
                   window: int = WINDOW) -> Optional[pd.DataFrame]:
    """Aligned daily LOG returns for the names with enough overlapping history.

    ALIGNED ON DATES, NOT STACKED BY POSITION. Two Indonesian listings can have
    different suspension days, and lining them up by row number correlates one
    name's Tuesday against another's Wednesday — a mistake that inflates nothing
    and deflates everything, so it looks like prudence.

    LOG returns because `weekly` sums them, and the sum of daily log returns IS
    the weekly log return. Summing simple returns would give a different and
    wrong number, and `exposure.to_weekly` makes the same choice for the same
    reason.
    """
    columns: dict[str, pd.Series] = {}
    for ticker in tickers:
        frame = frames.get(ticker)
        if frame is None or len(frame) < MIN_OBSERVATIONS:
            continue
        close = frame["Close"].astype("float64").tail(window + 1)
        positive = close.where(close > 0)
        # `fill_method` is not in play for a `diff` of logs, but the same rule
        # `ranking.py` states applies: a non-positive or missing price becomes
        # NaN and is dropped, never padded forward into a fabricated 0% day.
        series = np.log(positive).diff().dropna()
        if len(series) >= MIN_OBSERVATIONS:
            columns[ticker] = series
    if len(columns) < 2:
        return None
    joined = pd.DataFrame(columns).dropna()
    return joined if len(joined) >= MIN_OBSERVATIONS else None


def weekly(daily: pd.DataFrame) -> pd.DataFrame:
    """Daily log returns summed into weeks ending Friday.

    THE FREQUENCY THE HEADLINE IS QUOTED AT. Non-synchronous trading attenuates
    daily correlations between thinly traded names, so a daily figure flatters
    the diversification of exactly the list this module exists to warn about.
    Same transformation `exposure.to_weekly` applies, kept here rather than
    imported so `basket` does not acquire a dependency on a module it otherwise
    only touches for a stamped artifact.
    """
    if daily is None or daily.empty:
        return pd.DataFrame()
    return daily.resample("W-FRI").sum(min_count=1).dropna(how="all").dropna()


def clusters(correlation: pd.DataFrame, link: float = CLUSTER_LINK) -> list[list[str]]:
    """Groups of names linked, directly or through a chain, above `link`.

    Connected components rather than a clustering algorithm, deliberately: the
    grouping is then reproducible from the matrix and the threshold with no
    seed, no linkage choice and no distance metric to argue about. The cost is
    chaining — A links B links C puts all three together even where A and C are
    uncorrelated — and that is the right error for this purpose, because a chain
    of correlated names is exactly what a common factor looks like.
    """
    names = list(correlation.columns)
    remaining = set(names)
    found: list[list[str]] = []
    while remaining:
        seed = remaining.pop()
        group = {seed}
        queue = [seed]
        while queue:
            current = queue.pop()
            for other in list(remaining):
                value = _finite(correlation.loc[current, other])
                if value is not None and value >= link:
                    remaining.discard(other)
                    group.add(other)
                    queue.append(other)
        found.append(sorted(group))
    found.sort(key=lambda g: (-len(g), g[0]))
    return found


def analyse(frames: dict, tickers: Sequence[str],
            weights: Optional[dict] = None,
            sectors: Optional[dict] = None,
            window: int = WINDOW) -> dict:
    """How many bets this list is, and how much of that the weights capture."""
    picked = list(dict.fromkeys(t for t in tickers if t))
    if len(picked) < 2:
        return {"available": False,
                "reason": (f"{len(picked)} name{'' if len(picked) == 1 else 's'} in the "
                           f"list — concentration is a property of a set and needs at "
                           f"least two.")}

    daily = returns_matrix(frames, picked, window=window)
    if daily is None:
        return {"available": False,
                "reason": (f"fewer than {MIN_OBSERVATIONS} overlapping sessions across "
                           f"these names, so no correlation between them is a "
                           f"measurement")}

    matrix = weekly(daily)
    if len(matrix) < MIN_WEEKS:
        return {"available": False,
                "reason": (f"{len(matrix)} overlapping weeks, under the {MIN_WEEKS} a "
                           f"correlation matrix this wide needs")}

    correlation = matrix.corr()
    names = list(correlation.columns)
    effective = riskmodel.effective_independent(correlation.to_numpy(dtype="float64"))

    # The daily figure beside it, so the size of the attenuation is visible
    # rather than taken on trust from the docstring.
    daily_correlation = daily[names].corr()
    daily_effective = riskmodel.effective_independent(
        daily_correlation.to_numpy(dtype="float64"))

    # --- what the weights actually capture ---------------------------------
    # Annualised from WEEKLY observations, so the volatility and the correlation
    # it is combined with describe the same frequency. Mixing a daily volatility
    # with a weekly correlation would produce a portfolio figure that is neither.
    volatility = matrix.std(ddof=1) * np.sqrt(52)
    supplied = {k.upper(): float(v) for k, v in (weights or {}).items()
                if _finite(v) and float(v) > 0}
    raw = np.array([supplied.get(name.upper(), 1.0) for name in names], dtype="float64")
    total = raw.sum()
    share = raw / total if total > 0 else np.full(len(names), 1.0 / len(names))

    sigma = volatility.reindex(names).to_numpy(dtype="float64")
    covariance = correlation.to_numpy(dtype="float64") * np.outer(sigma, sigma)
    portfolio_variance = float(share @ covariance @ share)
    portfolio_vol = float(np.sqrt(portfolio_variance)) if portfolio_variance > 0 else None
    weighted_vol = float(share @ sigma)
    diversification = (weighted_vol / portfolio_vol
                       if portfolio_vol and portfolio_vol > 0 else None)

    # If the names were genuinely independent, the portfolio would carry this
    # much volatility. The gap against the real figure is what the correlation
    # is costing, in the units a holder feels.
    independent_vol = float(np.sqrt(np.sum((share * sigma) ** 2)))

    pairs = []
    for i, first in enumerate(names):
        for second in names[i + 1:]:
            value = _finite(correlation.loc[first, second])
            if value is not None:
                pairs.append({"a": first, "b": second, "correlation": value})
    pairs.sort(key=lambda p: -p["correlation"])

    # Which single name is most redundant — the one whose average correlation to
    # the rest is highest. Reported because "drop one" is the cheapest action a
    # reader can take, and the app should say which one rather than make them
    # read a matrix.
    average_to_rest = {
        name: float(np.mean([correlation.loc[name, other]
                             for other in names if other != name]))
        for name in names
    }
    most_redundant = max(average_to_rest, key=average_to_rest.get) if names else None

    grouped = clusters(correlation)
    sensitivity = {
        f"{link:.2f}": len(clusters(correlation, link=link))
        for link in CLUSTER_SENSITIVITY
    }

    sector_counts: dict[str, int] = {}
    for name in names:
        sector = (sectors or {}).get(name)
        if sector:
            sector_counts[sector] = sector_counts.get(sector, 0) + 1

    concentration = (effective / len(names)) if effective and names else None
    return {
        "available": True,
        "names": names,
        "count": len(names),
        "observations": len(matrix),
        "windowDays": window,
        "thin": len(matrix) < 2 * MIN_WEEKS,
        "effectiveBets": effective,
        "effectiveBetsDaily": daily_effective,
        "dailyObservations": len(daily),
        "frequency": "weekly",
        "concentration": concentration,
        "diversificationRatio": diversification,
        "portfolioVolatility": portfolio_vol,
        "independentVolatility": independent_vol,
        "weightedVolatility": weighted_vol,
        "equalWeighted": not supplied,
        "averageCorrelation": _finite(np.mean([p["correlation"] for p in pairs]))
        if pairs else None,
        "pairs": pairs[:12],
        "mostRedundant": most_redundant,
        "averageToRest": average_to_rest,
        "clusters": grouped,
        "clusterLink": CLUSTER_LINK,
        "clusterSensitivity": sensitivity,
        "sectors": dict(sorted(sector_counts.items(), key=lambda kv: -kv[1])),
        "persistence": riskmodel_persistence(),
        "reading": _reading(names, effective, concentration, diversification,
                            portfolio_vol, independent_vol, grouped, sector_counts,
                            most_redundant, average_to_rest,
                            thin=len(matrix) < 2 * MIN_WEEKS),
    }


def riskmodel_persistence() -> Optional[dict]:
    """What the stamped study says a one-year correlation is worth.

    Imported through `exposure` rather than restated, so this cannot come to
    disagree with the portfolio panel about how much persistence was measured.
    Returns None on a checkout that has never run the measurement, which reads
    as "unmeasured" rather than as "stable".
    """
    try:
        from . import exposure
        return exposure.persistence_context(exposure.load_stability())
    except Exception:
        return None


def _reading(names: list[str], effective: Optional[float],
             concentration: Optional[float], diversification: Optional[float],
             portfolio_vol: Optional[float], independent_vol: Optional[float],
             grouped: list[list[str]], sectors: dict[str, int],
             most_redundant: Optional[str],
             average_to_rest: dict[str, float], thin: bool = False) -> str:
    count = len(names)
    if effective is None:
        return f"{count} names, but their correlation could not be measured."

    text = (f"{count} names spanning about {effective:.1f} independent bets. ")
    if concentration is not None and concentration < CONCENTRATED_BELOW:
        text += ("Most of the length here is repetition: the list is far less "
                 "diversified than its count suggests, and sizing every name as though "
                 "it were a separate wager overstates how spread the risk is. ")
    else:
        text += "That is a fair spread for a list of this length. "

    big = [group for group in grouped if len(group) > 1]
    if big:
        largest = big[0]
        text += (f"The largest group that moves together is "
                 f"{', '.join(largest[:5])}"
                 f"{f' and {len(largest) - 5} more' if len(largest) > 5 else ''}. ")

    if sectors:
        top_sector, top_count = next(iter(sorted(sectors.items(), key=lambda kv: -kv[1])))
        if top_count > 1:
            text += (f"{top_count} of {count} sit in {top_sector}. ")

    if thin:
        text += ("Measured on fewer than eighty weeks, so the correlation matrix is "
                 "noisy and the bet count carries a wide error. ")

    if portfolio_vol and independent_vol and portfolio_vol > independent_vol:
        text += (f"At these weights the list carries {portfolio_vol * 100:.0f}% "
                 f"annualised volatility, against {independent_vol * 100:.0f}% if the "
                 f"same positions moved independently — the difference is what the "
                 f"correlation costs. ")

    if diversification is not None:
        text += (f"Diversification ratio {diversification:.2f}"
                 + (" — the weights are capturing very little of the spread that is "
                    "available." if diversification < 1.25 else
                    ". "))

    if most_redundant and average_to_rest.get(most_redundant, 0) > 0.5:
        text += (f" {most_redundant} is the most redundant single name, correlating "
                 f"{average_to_rest[most_redundant]:+.2f} with the rest on average.")

    return text.strip()
