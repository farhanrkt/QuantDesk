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

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
import pandas as pd

from . import market_data

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

# What counts as a name actually LOADING on a factor, rather than carrying a beta
# that is estimation noise.
#
# A T-STATISTIC, NOT AN R-SQUARED, AND THE FIRST VERSION GOT THIS WRONG IN A WAY
# THAT MADE THE WHOLE FEATURE USELESS. It shipped `MATERIAL_R2 = 0.05` shared
# between the panel and the persistence study, with a comment congratulating
# itself that one constant with two readers could not drift. The two readers have
# different SAMPLE SIZES, which is precisely when a shared R-squared threshold is
# the wrong thing to share: 0.05 is |t| = 5.0 across the study's 469 weekly
# observations and |t| = 1.6 across the panel's 52. The panel was screening at
# p = 0.11 and calling the survivors findings.
#
# Measured on the IDX30 the day this was fixed: the old floor passed ten of
# thirty names on energy — a poultry producer, a pharmaceutical company and a
# packaged-food company among them — where two clear a real test. The chart was
# drawing noise and labelling it.
#
# A t-statistic is the thing that transfers between sample sizes, so that is what
# is shared. Each caller converts it to whatever R-squared its own window implies.
MATERIAL_T = 3.0

# The window a beta is estimated over.
#
# FIVE YEARS, AND THE STABILITY STUDY IS THE ARGUMENT FOR IT RATHER THAN AGAINST.
# This was 52 weeks because that is the block length whose persistence was
# measured, which sounded principled and produced betas too noisy to report: at
# 52 observations a loading needs R-squared above 0.15 to clear |t| = 3, and
# almost nothing in the IDX30 does.
#
# What the study actually found is that a one-year beta carries only 0.21 to 0.43
# of itself into the next year. The response to "one year of data gives an
# unstable estimate" is more data, not less. What this costs is stated on the
# panel: the persistence figure was measured on one-year betas and describes the
# lower bound of a five-year one's stability, not its own.
ESTIMATION_WEEKS = 260

STABILITY_PATH = Path(__file__).with_name("exposure_stability.json")

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


def material_r2(observations: int, t: float = MATERIAL_T) -> float:
    """The R-squared that clears `t` at this many observations.

    The screen is a t-statistic; this is how each caller spends it on its own
    window. At 52 weeks it asks for 0.15, at 260 for 0.03 — the same evidential
    bar, which a fixed R-squared emphatically is not.
    """
    dof = max(1, observations - 2)
    return float(t * t / (t * t + dof))


def t_stat(r_squared: float, observations: int) -> float:
    """The t-statistic a simple regression's R-squared implies."""
    dof = max(1, observations - 2)
    r_squared = min(max(float(r_squared), 0.0), 0.999999)
    return float(np.sqrt(r_squared * dof / (1.0 - r_squared)))


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


# --------------------------------------------------------------------------- #
# One name against the factors that survived the gate
# --------------------------------------------------------------------------- #
def load_stability(path: Path = STABILITY_PATH) -> Optional[dict]:
    """The measured persistence of factor betas, or None if never measured.

    Served from a stamped file for the same reason the ranking backtest and the
    correlation stability are: it is a research finding about the method rather
    than a per-user computation.
    """
    try:
        payload = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) and payload.get("factors") else None


def persistence_context(stability: Optional[dict]) -> dict:
    """What the stability study can and cannot say about the betas shown here.

    IT IS CONTEXT, NOT A GATE, AND IT USED TO BE A GATE. An earlier version
    filtered factors by their measured persistence and refused gold at +0.21
    against a 0.25 line. That was defensible while the panel reported the same
    quantity the study measured — raw one-year betas. It no longer does: the
    panel reports a five-year beta with the local market removed, because the
    one-year raw version was too noisy to be worth printing.

    THE PERSISTENCE OF WHAT IS NOW SHOWN CANNOT BE MEASURED AT THIS DATA DEPTH,
    and pretending otherwise would be the error this whole feature keeps making
    in new places. Nine years holds fewer than two non-overlapping five-year
    blocks, and re-running the study on market-removed one-year betas produced
    too few qualifying names per block to rank-correlate anything. Both are
    stated rather than papered over.

    So nothing here is offered as a forecast. The panel reports what a stock did
    over five years, which needs no gate — the same standing as the portfolio
    driver label, and the same reason it ships ungated. What the study DID
    establish, about a different quantity, is reported as exactly that.
    """
    if not stability:
        return {"measured": False}
    return {
        "measured": True,
        "measuredOn": stability.get("measuredOn"),
        "blockWeeks": stability.get("blockWeeks"),
        # Raw one-year betas: the quantity the study could measure.
        "rawOneYear": {
            key: (((block.get("all") or {}).get("persistenceAllNames") or {})
                  .get("meanRankCorrelation"))
            for key, block in (stability.get("factors") or {}).items()
        },
    }


_SERIES_CACHE: dict[tuple[str, str], pd.Series] = {}


def _weekly_returns(symbol: str, weeks: int) -> Optional[pd.Series]:
    """Weekly log returns for one symbol, cached for the current day.

    Fetched generously in calendar days and trimmed to `weeks`, so a market that
    trades fewer sessions than the US one still fills the window.
    """
    key = (symbol.upper(), dt.date.today().isoformat())
    cached = _SERIES_CACHE.get(key)
    if cached is not None:
        return cached.tail(weeks)

    end = dt.date.today()
    frame = market_data.ohlcv(symbol, start=end - dt.timedelta(days=int(weeks * 9)),
                              end=end)
    if frame is None or frame.empty:
        return None
    close = frame["Close"].astype("float64")
    weekly = to_weekly(np.log(close / close.shift(1)).to_frame("r"))["r"].dropna()
    if len(_SERIES_CACHE) > 128:
        _SERIES_CACHE.clear()          # only ever hold the current day
    _SERIES_CACHE[key] = weekly
    return weekly.tail(weeks)


def _fit(own: pd.Series, factor: pd.Series,
         index_returns: Optional[pd.Series]) -> Optional[dict]:
    """One name against one factor, with the local market taken out of BOTH.

    BOTH SIDES OR NEITHER. The portfolio panel removes the index before naming
    anything and calls it the whole design; the single-name and scan tiers
    shipped without it and reported that a packaged-food company was exposed to
    crude. It was not — it and crude were both moving with the Jakarta Composite,
    and a raw beta cannot tell that from an exposure.

    Stripping only the stock would be worse than stripping neither: it would
    compare a market-free series against one that still carries the market, and
    the surviving common factor fights the signal instead of adding to it.
    """
    frame = pd.concat([own.rename("y"), factor.rename("x")], axis=1).dropna()
    if len(frame) < MIN_WEEKS:
        return None
    y, x = frame["y"], frame["x"]
    if index_returns is not None:
        stripped_y = _residualise(y, index_returns)
        stripped_x = _residualise(x, index_returns)
        if stripped_y is not None and stripped_x is not None:
            pair = pd.concat([stripped_y.rename("y"), stripped_x.rename("x")],
                             axis=1).dropna()
            if len(pair) >= MIN_WEEKS:
                y, x = pair["y"], pair["x"]
    centred = x - x.mean()
    sxx = float((centred ** 2).sum())
    if sxx <= 0:
        return None
    beta = float((centred * (y - y.mean())).sum() / sxx)
    correlation = y.corr(x)
    if not np.isfinite(beta) or correlation is None or not np.isfinite(correlation):
        return None
    r_squared = float(correlation ** 2)
    return {"beta": beta, "rSquared": r_squared, "weeks": len(y),
            "tStat": t_stat(r_squared, len(y)) * (1.0 if beta >= 0 else -1.0),
            "marketRemoved": index_returns is not None}


def for_symbol(symbol: str, market_code: str = "US",
               weeks: int = ESTIMATION_WEEKS) -> dict:
    """What one stock moves with, among the factors whose betas survive a year.

    THE RAW WEEKLY BETA, NOT A MARKET-ADJUSTED ONE, and that is a constraint
    rather than a simplification. `measure_exposure_stability.py` measured the
    persistence of the raw beta; reporting a residualised one here would quote a
    stability figure for a quantity nobody measured. The market beta is a
    separate number and `riskmodel.estimate_beta` already reports it.

    THREE REFUSALS, ALL OF WHICH FIRE IN PRACTICE:

      * a factor the study could not clear — gold, at +0.21 against a 0.25 line
        set before the numbers were seen — is never printed, and is named on
        screen as refused rather than quietly dropped;
      * a factor this name does not materially load on is not printed either,
        because the persistence figure was measured on names that DID load and
        does not describe a beta estimated from noise;
      * too little history is a refusal rather than a shorter window, since a
        different window has no measured stability at all.

    What it does NOT report is an upside and downside beta. The study found the
    gap between them does not persist — sign agreement of 46% to 66% across the
    factor's own rising and falling years, a coin flip on gold — and printing two
    numbers a reader will inevitably compare, beside a note asking them not to,
    is worse than printing neither.
    """
    market = (market_code or "US").upper()
    stability = load_stability()
    context = persistence_context(stability)
    considered = [r for r in REFERENCES if market in r.markets]

    index_returns = _weekly_returns(LOCAL_INDEX.get(market, LOCAL_INDEX["US"]), weeks)
    own = _weekly_returns(symbol, weeks)
    if own is None or len(own) < MIN_WEEKS:
        return {"usable": False,
                "reason": (f"Needs {MIN_WEEKS} weeks of price history before a factor "
                           f"beta means anything; this listing has "
                           f"{0 if own is None else len(own)}."),
                "refused": [], "measuredOn": (stability or {}).get("measuredOn")}

    rows, refused = [], []
    for reference in considered:
        series = _weekly_returns(reference.symbol, weeks)
        if series is None:
            refused.append({"key": reference.key, "label": reference.label,
                            "reason": "no data for the factor series"})
            continue
        fitted = _fit(own, series, index_returns)
        if fitted is None:
            refused.append({"key": reference.key, "label": reference.label,
                            "reason": "too few overlapping weeks"})
            continue
        if abs(fitted["tStat"]) < MATERIAL_T:
            refused.append({"key": reference.key, "label": reference.label,
                            "reason": "no material loading on this name"})
            continue
        rows.append({"key": reference.key, "label": reference.label,
                     "symbol": reference.symbol, "note": reference.note, **fitted})

    return {
        "usable": True,
        "ticker": symbol,
        "weeks": len(own),
        # Declaration order, never strength order — see the module docstring.
        "factors": rows,
        "refused": refused,
        "materialAt": material_r2(len(own)),
        "materialT": MATERIAL_T,
        "persistence": context,
    }


# --------------------------------------------------------------------------- #
# A whole universe at once
# --------------------------------------------------------------------------- #
def scan(symbols: Sequence[str], market_code: str = "US",
         weeks: int = ESTIMATION_WEEKS) -> dict:
    """Every name in a universe against every factor that survived the gate.

    WHY THIS EXISTS AS ITS OWN TIER RATHER THAN A PER-TICKER READING. A single
    beta is uninterpretable on its own — 0.57 against the energy complex is
    either remarkable or ordinary depending on what the other forty names in the
    index read, and a reader with no priors cannot tell which. That is the same
    argument `peers.py` makes for percentiles, and it applies harder here because
    a factor beta has no natural scale at all.

    It is also the only shape in which the interesting finding is FINDABLE.
    United Tractors files as Industrials, sells mining equipment, and loads on
    energy about as hard as the coal miners do. Nobody types UNTR into a factor
    screen to check; they see it sitting among the miners in a cross-section and
    ask why. A per-ticker view can confirm an exposure somebody already suspected
    and cannot surface one they did not.

    PRICE ONLY, SO IT BATCHES — a forty-five name universe is one upstream call,
    not forty-five. The fundamentals lenses do not batch, which is why there is
    no sector label on these rows and the panel says so: a reader supplies the
    "but that is an industrials company" themselves.

    Returns every name that could be measured, including those whose loadings are
    all below the material threshold. THEY ARE THE CONTROL GROUP: a scatter
    showing only the names that loaded would make every universe look uniformly
    exposed, which is the selection effect this app spends `screendomain.py`
    avoiding in a neighbouring place.
    """
    market = (market_code or "US").upper()
    stability = load_stability()
    context = persistence_context(stability)
    factors = [r for r in REFERENCES if market in r.markets]
    refused: list = []

    wanted = list(dict.fromkeys([*symbols, *(r.symbol for r in factors),
                                 LOCAL_INDEX.get(market, LOCAL_INDEX["US"])]))
    end = dt.date.today()
    frames = market_data.ohlcv_batch(
        wanted, end - dt.timedelta(days=int(weeks * 9)), end)
    if not frames:
        return {"usable": False, "reason": "No price history came back for this list.",
                "factors": [], "refused": refused, "rows": [],
                "measuredOn": (stability or {}).get("measuredOn")}

    closes = pd.DataFrame({s: f["Close"].astype("float64") for s, f in frames.items()})
    weekly = to_weekly(np.log(closes.sort_index() / closes.sort_index().shift(1)))
    weekly = weekly.tail(weeks)

    index_symbol = LOCAL_INDEX.get(market, LOCAL_INDEX["US"])
    index_returns = weekly[index_symbol] if index_symbol in weekly.columns else None

    rows, missing = [], []
    for symbol in symbols:
        if symbol not in weekly.columns:
            missing.append(symbol)
            continue
        own = weekly[symbol].dropna()
        if len(own) < MIN_WEEKS:
            missing.append(symbol)
            continue
        loadings = {}
        for reference in factors:
            if reference.symbol not in weekly.columns:
                continue
            # THE SAME `_fit` THE SINGLE-NAME READ USES, market removed from both
            # sides. Two copies of this arithmetic would eventually disagree about
            # the same stock on the same day, which is the one thing a tab and a
            # panel showing the same number may not do.
            fitted = _fit(own, weekly[reference.symbol], index_returns)
            if fitted is None:
                continue
            loadings[reference.key] = {
                **fitted, "material": bool(abs(fitted["tStat"]) >= MATERIAL_T),
            }
        if loadings:
            rows.append({"ticker": symbol, "weeks": len(own), "loadings": loadings})

    return {
        "usable": bool(rows),
        "reason": None if rows else "Nothing in this list had enough weekly history.",
        # Declaration order, never strength order — see the module docstring.
        "factors": [{"key": r.key, "label": r.label, "symbol": r.symbol,
                     "note": r.note} for r in factors],
        "refused": refused,
        "rows": rows,
        "missing": missing,
        "scanned": len(rows),
        "requested": len(list(symbols)),
        "weeks": weeks,
        "materialAt": material_r2(weeks),
        "materialT": MATERIAL_T,
        "indexSymbol": index_symbol,
        "persistence": context,
    }
