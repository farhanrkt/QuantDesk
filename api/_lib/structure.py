"""
structure.py
============
Where the price sits against the levels the market actually defended, and what
buying it HERE risks.

THE GAP THIS FILLS, WHICH IS THE LARGEST ONE THE SCANNER HAD
--------------------------------------------------------------
`verdict.py` will say BUY and then stop. It orders names by how much the
evidence likes them and says nothing whatever about the price on the screen —
so a name it likes reads identically whether it is sitting on support having
just been defended, or two percent under a ceiling it has failed at three times.
Those are the same asset and they are not the same trade.

That is not a scoring problem and this module is deliberately not a scoring
component. The score answers "is this worth owning". This answers "is now a
sensible moment, and where would I be wrong" — and mixing them would let a
tidy entry make a poor company look better, which is exactly the confusion a
composite is most prone to.

So it feeds two things and nothing else: a GATE when buying at this price risks
more than the nearest structure offers, and the levels themselves, printed
beside the verdict so a reader knows what they would be acting on.

REWARD TO RISK IS MEASURED TO STRUCTURE, NOT TO A TARGET SOMEBODY CHOSE
-----------------------------------------------------------------------
The upside is the distance to the nearest resistance overhead — the price where
the last sellers were — and the risk is the distance to the nearest support
below, the price whose failure would mean the reason for the trade was wrong.
Both come from `swing.support_resistance`, which clusters actual swing highs and
lows rather than drawing lines.

Neither is a forecast. A stock can go through resistance and often does; the
ratio says what the structure in front of it looks like, not what it will do.

WHAT IT REFUSES
---------------
1. NO TARGET BEYOND THE NEXT LEVEL. `swing.build_plan` already makes this
   argument: projecting past the nearest resistance because the arithmetic gives
   a nicer ratio is how a 3:1 gets manufactured. Where there is nothing
   overhead — the price is at a high — the ratio is reported as unbounded and
   the gate does not fire, because "no resistance" is not a reason to refuse.

2. NO ENTRY PRICE. This says whether the current price is a poor place to buy.
   It does not suggest a better one, because a limit order that never fills is
   a position nobody has and this app cannot tell whether that is what the
   reader wanted.

3. NOTHING WHERE THERE IS NO STRUCTURE. A recently listed name with two swing
   points has no levels worth the name, and the honest output is that the check
   could not run — which the gate treats as unmeasured, not as clear.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

# Where the reward-to-risk line sits, and why it is a DEFINITION rather than a
# tuned parameter. Below 1.0 the nearest ceiling is closer than the nearest
# floor: the trade risks more to the level whose failure invalidates it than it
# stands to make to the level that would cap it. That is not a threshold anybody
# fitted, it is the point where the two distances cross, and it is the only
# number in this file that would survive being argued about.
POOR_REWARD_RISK = 1.0

# Under this, the entry is not merely poor, it is inside the noise: a ceiling
# less than a third of the distance away that the floor is. Kept separate
# because the gate treats them differently.
BAD_REWARD_RISK = 0.33

# A support this far below is not a stop, it is a different investment. Beyond
# it the "risk" being measured is the whole thesis rather than a level, and the
# ratio stops meaning anything a position could be sized on.
MAX_USEFUL_RISK = 0.35

# How close counts as "at" a level, in multiples of the average daily range.
# Half a day's range: near enough that a single ordinary session reaches it.
AT_LEVEL_ATR = 0.5


def _finite(value) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if np.isfinite(out) else None


def _levels_from(technical: Optional[dict]) -> Optional[dict]:
    """The swing levels out of the assembled technical payload.

    READ, NOT RECOMPUTED. `swing.support_resistance` already ran inside the
    trend lens and its output is on the payload; running it again here would
    cost nothing but would eventually drift from the levels the chart draws,
    which is the failure `explain.for_synthesis` avoids by reading the assembled
    payload rather than recomputing.

    The short horizon is preferred over the mid because its levels are the ones
    a buyer meets first. Where it did not resolve, the mid-horizon levels stand
    in and the caller is told which was used.
    """
    if not isinstance(technical, dict):
        return None
    for horizon in ("shortTerm", "midTerm"):
        block = technical.get(horizon)
        if not isinstance(block, dict):
            continue
        levels = block.get("levels")
        if isinstance(levels, dict) and levels.get("usable"):
            return {**levels, "horizon": horizon}
    return None


def read(technical: Optional[dict] = None, levels: Optional[dict] = None,
         frame: Optional[pd.DataFrame] = None) -> dict:
    """Where the price sits, and what buying it here risks.

    Takes either the assembled technical leg or a levels dict directly — the
    scanner has the first, tests and the calibration have the second.
    """
    resolved = levels if isinstance(levels, dict) else _levels_from(technical)
    if not resolved or not resolved.get("usable"):
        return {"available": False,
                "reason": ("no usable support or resistance — usually a listing too "
                           "recent to have defended a level twice")}

    price = _finite(resolved.get("price"))
    atr = _finite(resolved.get("atr"))
    if price is None or price <= 0:
        return {"available": False, "reason": "no usable price on the levels"}

    supports = [s for s in (resolved.get("supports") or [])
                if _finite(s.get("price")) is not None and s["price"] < price]
    resistances = [r for r in (resolved.get("resistances") or [])
                   if _finite(r.get("price")) is not None and r["price"] > price]

    support = max((float(s["price"]) for s in supports), default=None)
    resistance = min((float(r["price"]) for r in resistances), default=None)

    risk = (price - support) / price if support else None
    reward = (resistance - price) / price if resistance else None

    # UNBOUNDED, NOT INFINITE, and the distinction is the point. A name at a
    # 52-week high has nothing overhead, which is not a bad entry — it is the
    # absence of the measurement. It reads as unbounded and the gate stays
    # silent rather than treating a breakout as a refusal.
    ratio = None
    unbounded = resistance is None
    if risk and risk > 0 and reward is not None:
        ratio = reward / risk

    band = _band(ratio, risk, unbounded, support is not None)
    return {
        "available": True,
        "horizon": resolved.get("horizon"),
        "price": price,
        "atr": atr,
        "support": support,
        "resistance": resistance,
        "riskToSupport": risk,
        "rewardToResistance": reward,
        "rewardRisk": ratio,
        "unboundedUpside": unbounded,
        "noSupport": support is None,
        "atSupport": bool(support and atr and (price - support) <= AT_LEVEL_ATR * atr),
        "atResistance": bool(resistance and atr
                             and (resistance - price) <= AT_LEVEL_ATR * atr),
        "band": band,
        "reading": _reading(price, support, resistance, risk, reward, ratio,
                            unbounded, band, atr),
    }


def _band(ratio: Optional[float], risk: Optional[float], unbounded: bool,
          has_support: bool) -> str:
    """Which of five states this entry is in. `unmeasured` is not `fine`."""
    if not has_support:
        return "noSupport"
    if unbounded:
        return "unbounded"
    if ratio is None:
        return "unmeasured"
    if risk is not None and risk > MAX_USEFUL_RISK:
        return "riskTooWide"
    if ratio < BAD_REWARD_RISK:
        return "bad"
    if ratio < POOR_REWARD_RISK:
        return "poor"
    return "fine"


def _reading(price: float, support: Optional[float], resistance: Optional[float],
             risk: Optional[float], reward: Optional[float], ratio: Optional[float],
             unbounded: bool, band: str, atr: Optional[float]) -> str:
    if support is None:
        return ("No support below the current price in the scanned window, so there is no "
                "level whose failure would say the trade was wrong — and therefore nothing "
                "to measure risk against. That is a gap, not a clean entry.")

    where = (f"The nearest support the market actually defended is {support:,.0f}, "
             f"{risk * 100:.1f}% below. ")

    if unbounded:
        return (where + "There is no resistance overhead in the window — the price is at "
                        "or near the top of its own range — so the upside cannot be "
                        "measured against structure. Unbounded is not the same as large.")

    upside = (f"The nearest resistance is {resistance:,.0f}, {reward * 100:.1f}% above, "
              f"so the structure in front of it is {ratio:.1f} to 1. ")

    tail = {
        "bad": ("Buying here risks three times what the next ceiling offers. The company "
                "may be perfectly sound; this price is not where to express that."),
        "poor": ("The next ceiling is closer than the floor whose failure would mean the "
                 "reason for the trade was wrong."),
        "riskTooWide": (f"The support is {risk * 100:.0f}% away, which is not a stop but a "
                        f"different investment — past that distance the ratio stops "
                        f"describing anything a position could be sized on."),
        "fine": "There is more room to the ceiling than to the floor.",
        "unmeasured": "The ratio could not be computed.",
    }[band]

    at = ""
    if atr and resistance and (resistance - price) <= AT_LEVEL_ATR * atr:
        at = " The price is within half a day's range of that resistance."
    elif atr and (price - support) <= AT_LEVEL_ATR * atr:
        at = " The price is within half a day's range of that support."

    return where + upside + tail + at


def round_trip_cost(liquidity: Optional[dict]) -> dict:
    """What one buy and one sell would cost, from the spread already estimated.

    THE NUMBER THAT DECIDES WHETHER ANY OF THIS IS ACTIONABLE. The measured
    effects in this app are small — the chart-pattern study found about -3% over
    a quarter, the tape reading less — and a round trip on a thin Indonesian
    listing can cost more than that. A scanner that ranks names without saying
    what trading them costs is quoting a gross number as though it were net.

    `microstructure.liquidity_profile` already estimates the spread and, more
    usefully, already knows when its own estimate is beneath the estimator's
    noise floor. An unresolved spread is reported as unmeasured rather than as
    cheap — the same rule the turnover gate follows.
    """
    if not isinstance(liquidity, dict):
        return {"available": False, "reason": "no liquidity profile for this name"}

    spread = liquidity.get("spread")
    resolved = bool(liquidity.get("spreadResolved"))
    try:
        value = float(spread)
    except (TypeError, ValueError):
        value = None

    if value is None or not np.isfinite(value) or value <= 0:
        return {"available": False,
                "reason": "no usable spread estimate for this listing"}
    if not resolved:
        return {"available": False, "resolved": False, "spread": value,
                "reason": ("the spread estimate sits at the estimator's own noise "
                           "floor, so the cost could not be measured — which is not "
                           "the same as it being small")}

    # One round trip crosses the spread twice: once buying, once selling.
    cost = 2.0 * value
    return {"available": True, "resolved": True, "spread": value,
            "roundTrip": cost,
            "reading": (f"A round trip costs about {cost * 100:.2f}% at the estimated "
                        f"spread — crossed twice, once each way. Compare that against "
                        f"any effect on this page before treating one as actionable.")}


# ============================================================================ #
# The market the name trades in
#
# WHY A BUY LIST NEEDS THIS PRINTED ON IT.
#
# Every score in this app is CROSS-SECTIONAL: `ranking.py` converts each signal
# to a percentile within the scanned universe before anything is combined, and
# says why — "top decile of this scan" is a claim the data supports and "82/100"
# is not. That is the right design and it has one consequence nobody reading a
# ranked table remembers: the top of a falling market still has a top. A scan
# run while the index is 20% below its own 200-day average produces a list of
# names that are merely losing less, and every number on it looks identical to
# the same list produced in a bull market.
#
# So the regime is measured once per scan, from the same benchmark the relative
# strength is measured against, and printed at the top of the report. It scores
# NOTHING and gates nothing. Timing the market is a different claim from the one
# this app makes, nobody here has measured whether it works, and a gate on it
# would be exactly the unmeasured predictive claim `PRODUCT.md` constraint 2
# forbids. It is context, and context is allowed to be context.
# ============================================================================ #

# The two lines the regime is read from. Both are conventional, both are
# arbitrary, and neither is tuned — which is why this reports a state rather
# than a signal.
REGIME_SLOW = 200
REGIME_FAST = 50


def regime(frame: Optional[pd.DataFrame], symbol: Optional[str] = None) -> dict:
    """Where the index itself is, in one sentence.

    Read from the benchmark's own closes: whether it sits above its 200-day
    average, whether that average is rising, and how far below its own one-year
    high it is. Three facts, no verdict.
    """
    if frame is None or len(frame) < REGIME_SLOW + 21:
        have = 0 if frame is None else len(frame)
        return {"available": False,
                "reason": (f"needs {REGIME_SLOW + 21} sessions of index history; "
                           f"this has {have}")}

    close = frame["Close"].astype("float64")
    slow = close.rolling(REGIME_SLOW, min_periods=REGIME_SLOW).mean()
    fast = close.rolling(REGIME_FAST, min_periods=REGIME_FAST).mean()
    if slow.dropna().empty:
        return {"available": False, "reason": "not enough history for a 200-day average"}

    price = float(close.iloc[-1])
    slow_now = float(slow.iloc[-1])
    fast_now = _finite(fast.iloc[-1])

    # Is the average itself rising? A price above a FALLING average is a bounce;
    # above a rising one is a trend — the distinction `ranking.py` makes for its
    # own trend signal, applied to the index.
    slow_clean = slow.dropna()
    rising = None
    if len(slow_clean) > 63:
        rising = bool(float(slow_clean.iloc[-1]) > float(slow_clean.iloc[-64]))

    year = close.tail(252)
    high = float(year.max())
    drawdown = (price / high - 1.0) if high > 0 else None

    above = price > slow_now
    if above and rising:
        state, tone = "advancing", "good"
    elif above:
        state, tone = "recovering", "neutral"
    elif rising:
        state, tone = "pulling back", "warn"
    else:
        state, tone = "declining", "bad"

    return {
        "available": True,
        "symbol": symbol,
        "state": state,
        "tone": tone,
        "price": price,
        "slowAverage": slow_now,
        "fastAverage": fast_now,
        "aboveSlow": above,
        "slowRising": rising,
        "distanceToSlow": price / slow_now - 1.0 if slow_now else None,
        "drawdownFromYearHigh": drawdown,
        "scores": False,
        "reading": _regime_reading(symbol, state, price, slow_now, rising, drawdown),
    }


def _regime_reading(symbol: Optional[str], state: str, price: float,
                    slow: float, rising: Optional[bool],
                    drawdown: Optional[float]) -> str:
    name = symbol or "The index"
    gap = price / slow - 1.0 if slow else 0.0
    direction = ("rising" if rising else "falling") if rising is not None else "flat"
    text = (f"{name} is {state}: {abs(gap) * 100:.1f}% "
            f"{'above' if gap >= 0 else 'below'} its {REGIME_SLOW}-day average, and that "
            f"average is {direction}. ")
    if drawdown is not None and drawdown < -0.005:
        text += f"It sits {abs(drawdown) * 100:.1f}% below its own one-year high. "
    text += ("This scores nothing and gates nothing — every ranking below is "
             "cross-sectional, so the top of a falling market is still a top, and "
             "whether that is worth acting on is a market-timing claim nobody here "
             "has measured.")
    return text
