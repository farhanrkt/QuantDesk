"""
exposure.py
===========
What a set of holdings is actually a bet on, when they turn out to be one bet.

THE GAP THIS FILLS, AND WHY IT IS NOT A FIFTH LENS
---------------------------------------------------
`portfolio.py` already reports that four holdings correlate at 0.82 and that
they amount to about 1.6 independent positions. It cannot say WHY. "Because
they are all one bet on energy" is the sentence that tells a holder whether the
concentration is an accident or the entire thesis, and no panel in this app
could produce it.

That is all this module does. It does NOT vote, and that is a constraint rather
than a scoping decision: a beta has no bullish or bearish direction, and a
negative loading on the dollar is not a bad loading. Nothing here reaches
`explain._family_votes` or `ConfluenceRail.agreementOf`, so the kappa measured
in RESEARCH_ROADMAP.md §15 stays valid — see the "DO NOT" note there, which
exists because the rail's `Family` type is extensible enough to make breaking
that one easy commit.

THE MARKET IS REMOVED FIRST, AND THAT IS THE WHOLE DESIGN
----------------------------------------------------------
The first principal component of any set of stocks in one market is largely
that market. "Your holdings share a direction and it correlates 0.9 with the
Jakarta Composite" is true, useless, and would fire on every portfolio ever
entered — the same failure `screendomain.py` avoids by refusing to colour a
condition that holds for everybody.

So the shared direction is split in two:

  1. how much of it is the local index, reported plainly;
  2. what is left once the index is projected out, and whether THAT looks like
     anything nameable.

Step 2 is where the finding is. Measured on real books: a mixed defensive
Indonesian portfolio is 58% index, and an Indonesian coal book is 12%. The
second number is the interesting one — that book's common movement is almost
entirely NOT the market it trades in.

WEEKLY, NOT DAILY, AND THE DIFFERENCE IS NOT MARGINAL
------------------------------------------------------
Every reference here settles in a different time zone from an IDX close, and at
daily frequency that mismatch eats the signal. Measured on a concentrated
Indonesian coal book against crude: **0.17 daily, 0.52 weekly**. Daily would have
shipped a panel that cannot find energy in a book of energy companies.

Weekly log returns are the exact sum of the daily ones, so this resamples the
returns it is handed rather than asking the caller for a second frame.

WHAT WAS TRIED AND DROPPED: PEER-EQUITY BASKETS
-----------------------------------------------
The obvious way to name "coal" is a basket of coal miners. Two versions were
built and measured, and NEITHER ships:

  * FOREIGN baskets — Australian coal, Malaysian plantations — are non-circular
    by construction, since no holding can be inside them. They reached 0.19-0.27
    against a concentrated Indonesian coal book, and on that book palm oil scored
    HIGHER than coal. A labeller that cannot tell palm from coal on four coal
    miners is not a labeller.
  * DOMESTIC leave-one-out baskets, built from the resource names a holder does
    not own, did better — 0.28 to 0.49 — and still never cleared the naming
    threshold. Worse, a nickel-and-gold book read 0.49 against COAL, which is a
    confident mislabel rather than a miss.

The traded futures cleared where the equity baskets did not, so the futures are
what ship. This is a null worth stating rather than a gap worth hiding: it means
this panel names an ENERGY exposure, not a coal one, and the difference is
recorded here so the next person does not rebuild the baskets from scratch.

WHAT IT REFUSES TO DO
---------------------
It does not rank drivers by strength. `PRODUCT.md` constraint 1 forbids a
strength ranking as squarely as it forbids a composite, and a leaderboard of
factors is one — two references correlating 0.61 and 0.58 are not
distinguishable at this sample size, and a list sorted by size would invite
reading the first as the real answer. Matches come back in DECLARATION ORDER.

Where two references both clear and land close together, it names NEITHER and
says the data cannot separate them. That is the same refusal `screendomain.py`
makes when a dimension cannot be placed.

It does not report a driver it did not test. A book with no named match is not
thereby diversified: it means nothing in `REFERENCES` explained the residual,
which may mean the right reference is missing — and given the paragraph above,
for an Indonesian resources book it very likely is. The payload carries that
sentence rather than leaving it to the reader.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

# Below this many holdings there is no "shared direction" worth extracting: the
# first component of two names is their average wearing a longer name.
MIN_HOLDINGS = 3

# Overlapping WEEKS a reference needs before its correlation is quoted. Forty is
# about ten months — short enough that a book assembled last year still gets an
# answer, long enough that a correlation from it is not an anecdote.
MIN_WEEKS = 40

# How much of the holdings' joint variance the first component must carry before
# calling it "a shared direction" at all. Below this the book does not have one
# thing driving it, which is a finding rather than a failure. Measured range on
# real books: 0.41 (US megacaps) to 0.78 (three Indonesian banks).
MIN_VARIANCE_SHARE = 0.35

# Correlation with the residual direction at which a reference is named.
#
# A READING THRESHOLD, NOT A PUBLISHED CONSTANT, and the panel says so. Set from
# what the references actually produce across ten deliberately constructed
# books: the two energy books cleared it (0.52, 0.53), a US energy book cleared
# it (0.48), and every non-commodity book — three banks, a defensive mix, a
# broad mix, US megacap tech — topped out at 0.11. There is a wide gap between
# those two groups and this sits in it.
NAME_AT = 0.45

# Two references landing within this of each other are not distinguishable at
# this sample size, so neither is named. See the module docstring.
AMBIGUOUS_WITHIN = 0.10


@dataclass(frozen=True)
class Reference:
    """One thing a portfolio might turn out to be a bet on.

    ALL FOUR ARE GLOBALLY TRADED CONTRACTS, which is not an aesthetic choice:
    a future cannot be a holding, so the circularity that makes peer baskets
    need leave-one-out does not arise here at all. See the module docstring for
    the two basket designs that were measured and dropped.
    """
    key: str
    label: str
    symbol: str
    markets: tuple[str, ...]
    note: str


# DECLARATION ORDER IS THE RENDER ORDER, and it is not strength order. See the
# module docstring: sorting these by correlation would build the driver ranking
# `PRODUCT.md` refuses, through a list rather than through a column.
REFERENCES: tuple[Reference, ...] = (
    Reference("gold", "gold", "GC=F", ("US", "ID"),
              "Gold futures."),
    Reference("oil", "the energy complex", "CL=F", ("US", "ID"),
              # Labelled "the energy complex" rather than "oil" deliberately.
              # An Indonesian coal book reads 0.52 against crude, and crude is
              # not what those companies sell — it is the closest tradeable
              # instrument to what moves them. Calling the reading "oil" would
              # name a contract; calling it "the energy complex" names the thing
              # the contract is standing in for, which is what is actually
              # measured. The symbol is shown alongside so the substitution is
              # visible rather than implied.
              "WTI crude futures, standing in for energy prices generally."),
    Reference("copper", "copper", "HG=F", ("US", "ID"),
              "Copper futures."),
    Reference("dollar", "the dollar", "DX-Y.NYB", ("US", "ID"),
              # NOT USDIDR, and this was measured rather than assumed. Of the 15
              # IDX names carrying a material raw USDIDR loading, 12 fall below
              # the threshold once the dollar index is projected out, and the
              # survivors are two domestically funded banks and a property
              # developer. The miners' loadings are NEGATIVE, which is the wrong
              # sign for the translation exposure a dollar-reporting exporter is
              # supposed to have — they fall when the rupiah falls, along with
              # everything else in a risk-off week. Labelling that "the rupiah"
              # would name the wrong fact.
              "The ICE dollar index. Not USDIDR: a rupiah cross mostly measures "
              "the dollar, and the sign says so."),
)

LOCAL_INDEX = {"US": "^GSPC", "ID": "^JKSE"}


def reference_symbols(market_code: str) -> list[str]:
    """Every symbol a run for this market needs, for one batched fetch.

    Returned flat and deduplicated so `portfolio.analyse` can append them to the
    download it already makes rather than paying for a second round trip.
    """
    market = (market_code or "US").upper()
    out = [LOCAL_INDEX.get(market, LOCAL_INDEX["US"])]
    out.extend(r.symbol for r in REFERENCES if market in r.markets)
    return list(dict.fromkeys(out))


def _finite(value) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if np.isfinite(out) else None


def to_weekly(daily_log_returns: pd.DataFrame) -> pd.DataFrame:
    """Daily log returns summed into weeks ending Friday.

    EXACT, NOT APPROXIMATE, because log returns add: the log return over a week
    is the sum of its days. Resampling prices and re-differencing would give the
    same answer with an extra fetch, and averaging daily returns would give a
    different and wrong one.

    A week where a market was shut contributes whatever days it had rather than
    a gap, which is right for the cross-market comparisons here — the ASX and
    the IDX do not share a holiday calendar and demanding both be open every day
    would throw away most of the sample.
    """
    if daily_log_returns is None or daily_log_returns.empty:
        return pd.DataFrame()
    weekly = daily_log_returns.resample("W-FRI").sum(min_count=1)
    return weekly.dropna(how="all")


def shared_direction(weekly: pd.DataFrame) -> Optional[dict]:
    """The first principal component of the holdings, as a time series.

    Computed on STANDARDISED returns — the correlation matrix rather than the
    covariance — so a single volatile holding does not become the "shared"
    direction on its own. Same reason `portfolio.py` reports correlations and
    risk contributions as separate things.

    THE SIGN OF A COMPONENT IS ARBITRARY and left that way it would flip between
    requests as data arrives, so it is fixed: the direction is oriented so most
    holdings load positively, which makes "the book went up" positive and every
    correlation downstream readable in the obvious direction.
    """
    if weekly is None or weekly.empty:
        return None
    usable = weekly.dropna(axis=1, thresh=MIN_WEEKS).dropna()
    if usable.shape[1] < MIN_HOLDINGS or len(usable) < MIN_WEEKS:
        return None

    spread = usable.std(ddof=1)
    usable = usable.loc[:, spread > 0]
    if usable.shape[1] < MIN_HOLDINGS:
        return None
    standardised = (usable - usable.mean()) / usable.std(ddof=1)

    matrix = standardised.corr().to_numpy("float64")
    if not np.all(np.isfinite(matrix)):
        return None
    try:
        values, vectors = np.linalg.eigh(matrix)
    except np.linalg.LinAlgError:
        return None
    order = np.argsort(values)[::-1]
    values, vectors = values[order], vectors[:, order]

    total = float(np.sum(np.clip(values, 0.0, None)))
    if total <= 0:
        return None
    loadings = vectors[:, 0]
    if float(np.sum(loadings)) < 0:
        loadings = -loadings          # orient it, see the docstring

    series = pd.Series(standardised.to_numpy("float64") @ loadings,
                       index=standardised.index)
    return {
        "series": series,
        "varianceShare": float(values[0] / total),
        "names": list(standardised.columns),
        "loadings": {name: float(loadings[i])
                     for i, name in enumerate(standardised.columns)},
        "weeks": len(series),
    }


def _residualise(target: pd.Series, against: pd.Series) -> Optional[pd.Series]:
    """`target` with the part explained by `against` projected out."""
    paired = pd.concat([target.rename("y"), against.rename("x")], axis=1).dropna()
    if len(paired) < MIN_WEEKS:
        return None
    design = np.column_stack([np.ones(len(paired)), paired["x"].to_numpy("float64")])
    try:
        coefficients, *_ = np.linalg.lstsq(design, paired["y"].to_numpy("float64"),
                                           rcond=None)
    except np.linalg.LinAlgError:
        return None
    return pd.Series(paired["y"].to_numpy("float64") - design @ coefficients,
                     index=paired.index)


def _correlate(first: pd.Series, second: pd.Series) -> Optional[tuple[float, int]]:
    paired = pd.concat([first.rename("a"), second.rename("b")], axis=1).dropna()
    if len(paired) < MIN_WEEKS:
        return None
    if paired["a"].std(ddof=1) <= 0 or paired["b"].std(ddof=1) <= 0:
        return None
    value = _finite(paired["a"].corr(paired["b"]))
    return (value, len(paired)) if value is not None else None


def analyse(holding_returns: pd.DataFrame, reference_returns: pd.DataFrame,
            market_code: str = "US") -> dict:
    """Name the direction a book shares, once the local market is taken out.

    Both arguments are DAILY log-return frames — the same shape
    `portfolio.daily_returns` already produces — and are resampled to weeks here.
    The caller owns the fetch because it already made one.
    """
    market = (market_code or "US").upper()
    weekly_holdings = to_weekly(holding_returns)
    weekly_references = to_weekly(reference_returns)

    direction = shared_direction(weekly_holdings)
    if direction is None:
        return {"usable": False,
                "reason": (f"Needs at least {MIN_HOLDINGS} holdings sharing "
                           f"{MIN_WEEKS} weeks of history before there is a common "
                           f"direction to name.")}

    index_symbol = LOCAL_INDEX.get(market, LOCAL_INDEX["US"])
    index_returns = (weekly_references[index_symbol]
                     if index_symbol in weekly_references.columns else None)

    series = direction["series"]
    market_share, residual = None, series
    if index_returns is not None:
        paired = _correlate(series, index_returns)
        if paired is not None:
            # Reported as R-squared, not correlation: "58% of the shared
            # direction is the index" is the sentence a holder can use, and the
            # sign of a component against its own market is not information.
            market_share = float(paired[0] ** 2)
            stripped = _residualise(series, index_returns)
            if stripped is not None:
                residual = stripped

    matches, tested = [], []
    for reference in REFERENCES:
        if market not in reference.markets:
            continue
        if reference.symbol not in weekly_references.columns:
            tested.append({"key": reference.key, "label": reference.label,
                           "symbol": reference.symbol, "available": False})
            continue
        scored = _correlate(residual, weekly_references[reference.symbol])
        if scored is None:
            tested.append({"key": reference.key, "label": reference.label,
                           "symbol": reference.symbol, "available": False})
            continue
        value, overlap = scored
        tested.append({"key": reference.key, "label": reference.label,
                       "symbol": reference.symbol, "available": True,
                       "correlation": value, "overlapWeeks": overlap})
        if abs(value) >= NAME_AT:
            matches.append({"key": reference.key, "label": reference.label,
                            "symbol": reference.symbol, "correlation": value,
                            "overlapWeeks": overlap, "note": reference.note})

    # AMBIGUITY IS A REFUSAL, NOT A TIE-BREAK. Comparing magnitudes here is not
    # the same as showing a ranking: nothing ordered by strength ever reaches the
    # payload, because when two references land this close the answer is that
    # neither is named.
    ambiguous = False
    if len(matches) > 1:
        strengths = sorted((abs(m["correlation"]) for m in matches), reverse=True)
        if strengths[0] - strengths[1] < AMBIGUOUS_WITHIN:
            ambiguous, matches = True, []

    return {
        "usable": True,
        "holdings": direction["names"],
        "weeks": direction["weeks"],
        "varianceShare": direction["varianceShare"],
        "hasSharedDirection": direction["varianceShare"] >= MIN_VARIANCE_SHARE,
        "loadings": direction["loadings"],
        "marketShare": market_share,
        "indexSymbol": index_symbol,
        # Declaration order, never strength order. See the module docstring.
        "matches": matches,
        "tested": tested,
        "ambiguous": ambiguous,
        "nameAt": NAME_AT,
        "minVarianceShare": MIN_VARIANCE_SHARE,
    }
