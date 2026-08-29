"""
explain.py
==========
Plain-English interpretation for every number this app puts on screen.

WHY THIS IS A PYTHON MODULE AND NOT UI COPY
-------------------------------------------
The obvious place to write "Sortino 1.35 is good" is in the React component
that renders it. That was rejected for two reasons.

The first is testability. The single easiest mistake in this whole layer is
getting the DIRECTION backwards — colouring a deep drawdown green because the
number is large, or a low Ulcer index red because it is small. Roughly a third
of the metrics here are "low is good", and they sit in the same grid as the
"high is good" ones. In TypeScript that mistake ships silently; here it is a
pytest assertion (`tests/test_explain.py::test_low_is_good_metrics_*`).

The second is that direction should not be re-decided per call site. So this
module makes it structurally impossible to get wrong:

    value ──► _ladder(ascending thresholds) ──► band ──► TONE_FOR_BAND ──► colour

A metric's direction is encoded ONCE, in the order of its ladder. Nothing
downstream ever looks at the sign or magnitude of the raw number again; the UI
receives a `tone` and maps it to a colour with no arithmetic of its own. To
make a "low is good" metric, you write the ladder with `excellent` first. There
is no second place to keep in sync.

WHAT AN EXPLANATION OWES THE READER
-----------------------------------
Three things, and the shape enforces all three:

  what     one sentence a non-finance reader understands, no jargon
  reading  an interpretation of THIS value, not of the concept — the number
           is quoted back with what it means for this specific holding
  action   what would make them do something differently, or the explicit
           admission "this is context, not a trigger"

That last field is the honest one. Most of what a research tool displays is
context. Saying so is better than implying every number is actionable, and it
is why `action` is required rather than optional: an interpreter that cannot
name a decision has to write the sentence admitting it.

`evidence` carries the other kind of honesty — how well the signal is supported
out of sample. A 12-1 momentum reading and a bullish-engulfing candle are not
the same class of claim, and presenting them in identical type is the failure
this field exists to prevent.
"""

from __future__ import annotations

from typing import Callable, Optional, Sequence

import numpy as np

# --------------------------------------------------------------------------- #
# Bands and tone
# --------------------------------------------------------------------------- #
# The ONLY vocabulary an interpreter may return, and the only place a band
# becomes a colour. Six words, deliberately: a wider vocabulary tempts callers
# into inventing a seventh and mapping it themselves.
#
#   excellent / good      unambiguously favourable for a holder
#   fair                  neither — a middling reading
#   caution               not a verdict on quality, a flag that something is
#                         stretched or fragile (overbought, thin, wide spread)
#   poor / bad            unambiguously unfavourable
#   context               no verdict is appropriate; the number describes
#                         rather than judges (skew, correlation, ADX level)
#   unavailable           not computable from the data we have
TONE_FOR_BAND: dict[str, str] = {
    "excellent": "good",
    "good": "good",
    "fair": "neutral",
    "context": "neutral",
    "caution": "warn",
    "poor": "warn",
    "bad": "bad",
    "unavailable": "none",
}

# How strongly the published evidence supports acting on a signal. Shown on the
# panel so a reader can tell a documented effect from folklore.
EVIDENCE = ("strong", "moderate", "weak", "none")


def _ladder(value: float, steps: Sequence[tuple[Optional[float], str]]) -> str:
    """Pick a band from thresholds written in ASCENDING order of `value`.

    `steps` is ((upper_bound, band), ...) with the final bound `None` meaning
    "everything above". Direction is expressed purely by which band sits at
    which end, so a "low is good" metric is written excellent-first and needs
    no flag, no negation and no second code path. That is the whole trick.
    """
    for bound, band in steps:
        if bound is None or value < bound:
            return band
    return steps[-1][1]


def _pct(value: Optional[float], digits: int = 1) -> str:
    if value is None or not np.isfinite(value):
        return "n/a"
    return f"{value * 100:.{digits}f}%"


def _signed_pct(value: Optional[float], digits: int = 1) -> str:
    if value is None or not np.isfinite(value):
        return "n/a"
    return f"{value * 100:+.{digits}f}%"


def _num(value: Optional[float], digits: int = 2) -> str:
    if value is None or not np.isfinite(value):
        return "n/a"
    return f"{value:,.{digits}f}"


CONTEXT_NOT_TRIGGER = "Context, not a trigger — nothing here on its own is a reason to buy or sell."

# Yahoo's index tickers are not words. Writing "^GSPC" inside a sentence meant
# for a non-specialist undoes the sentence.
INDEX_NAMES = {
    "^GSPC": "the S&P 500",
    "^JKSE": "the Jakarta Composite",
    "^IXIC": "the Nasdaq Composite",
    "^DJI": "the Dow",
}


def index_name(symbol: Optional[str]) -> str:
    if not symbol:
        return "the index"
    return INDEX_NAMES.get(symbol.upper(), symbol)


def make(label: str, what: str, reading: str, action: str, band: str,
         good_direction: str = "high", evidence: Optional[str] = None,
         value_text: Optional[str] = None) -> dict:
    """Assemble one explanation, deriving tone from the band and nothing else.

    `good_direction` is carried for the UI to draw an arrow and for the tests to
    assert against; it is NOT consulted when picking the colour, because the
    band already encodes it. Keeping it advisory means a mismatch between the
    two shows up as a failing test rather than as a wrong-coloured number.
    """
    if band not in TONE_FOR_BAND:
        raise ValueError(f"unknown band {band!r}")
    if good_direction not in ("high", "low", "none"):
        raise ValueError(f"unknown direction {good_direction!r}")
    if evidence is not None and evidence not in EVIDENCE:
        raise ValueError(f"unknown evidence level {evidence!r}")
    return {
        "label": label,
        "what": what,
        "reading": reading,
        "action": action,
        "band": band,
        "tone": TONE_FOR_BAND[band],
        "goodDirection": good_direction,
        "evidence": evidence,
        "valueText": value_text,
    }


def unavailable(label: str, what: str, reason: str) -> dict:
    """A metric the data could not support. Never a pass, never a colour."""
    return make(
        label=label, what=what,
        reading=f"No reading — {reason}.",
        action="Nothing to act on until there is enough data to compute it.",
        band="unavailable", good_direction="none",
    )


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
_REGISTRY: dict[str, Callable[..., Optional[dict]]] = {}


def metric(key: str):
    def register(fn):
        _REGISTRY[key] = fn
        return fn
    return register


def explain(key: str, value, **context) -> Optional[dict]:
    """One explanation, or None if the key is unknown.

    A missing or non-finite value returns the interpreter's own `unavailable`
    text rather than a generic one, because "needs 200 bars of history" and
    "this company files no dividend" are different facts.
    """
    fn = _REGISTRY.get(key)
    if fn is None:
        return None
    try:
        return fn(value, **context)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def explain_all(values: dict, **context) -> dict:
    """Explanations for every key present in `values` that we know how to read.

    Unknown keys are skipped silently rather than raising: the payload dicts
    carry plumbing fields (`usable`, `observations`, dates) alongside the
    metrics, and an engine adding a field should not break the panel.
    """
    out = {}
    for key, value in values.items():
        result = explain(key, value, **context)
        if result is not None:
            out[key] = result
    return out


def _known(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value)
    try:
        return bool(np.isfinite(float(value)))
    except (TypeError, ValueError):
        return False


# ============================================================================ #
# Return and risk-adjusted return
#
# The risk-free rate matters here and is threaded through as context. Sharpe
# and Sortino computed against rf=0 are not the textbook ratios and are
# systematically flattering; the reading text says which rate was used so the
# number can be compared with one from somewhere else.
# ============================================================================ #
@metric("cagr")
def _cagr(value, **_):
    label = "Annual return (CAGR)"
    what = ("The single yearly growth rate that would have taken the price from where it "
            "started to where it is now — the smoothed speed of the whole journey.")
    if not _known(value):
        return unavailable(label, what, "needs at least two priced days")
    band = _ladder(value, ((0.0, "bad"), (0.05, "poor"), (0.10, "fair"),
                           (0.20, "good"), (None, "excellent")))
    if value < 0:
        reading = (f"Lost about {_pct(abs(value))} a year. A holder over this whole window "
                   f"is behind, before counting dividends.")
    elif value < 0.05:
        reading = (f"Made about {_pct(value)} a year — below what cash or bonds have "
                   f"typically paid, for equity risk.")
    elif value < 0.10:
        reading = (f"Made about {_pct(value)} a year, a bit under the long-run average for "
                   f"a broad stock market (roughly 8-10% before inflation).")
    elif value < 0.20:
        reading = (f"Made about {_pct(value)} a year, comfortably ahead of the long-run "
                   f"stock-market average.")
    else:
        reading = (f"Made about {_pct(value)} a year. Rates this high are rare and rarely "
                   f"repeat — they usually come with the drawdowns shown below.")
    return make(label, what, reading,
                "Compare it against the index row before deciding it is good: beating cash "
                "is not the test, beating the fund you could have bought instead is.",
                band, "high", evidence="strong",
                value_text=_signed_pct(value))


@metric("volatility")
def _volatility(value, **_):
    label = "Volatility"
    what = ("How much the price bounces around in a typical year. Bigger means a wilder "
            "ride, in both directions.")
    if not _known(value):
        return unavailable(label, what, "needs about a month of history")
    band = _ladder(value, ((0.15, "excellent"), (0.25, "good"), (0.35, "fair"),
                           (0.50, "poor"), (None, "bad")))
    reading = (f"About {_pct(value, 0)} a year. In plain terms, a roughly two-in-three chance "
               f"that any given year lands within {_pct(value, 0)} either side of the average "
               f"return. ")
    reading += {
        "excellent": "That is calm for a single stock — closer to an index fund than a typical listing.",
        "good": "That is unremarkable for a single stock.",
        "fair": "That is on the lively side; expect double-digit swings routinely.",
        "poor": "That is high. Position size, not conviction, is what keeps this holdable.",
        "bad": "That is extreme. A stock this volatile can halve without anything being wrong.",
    }[band]
    return make(label, what, reading,
                "Use it to size the position: the same money in a name twice as volatile is "
                "twice the risk, whatever you think of the company.",
                band, "low", evidence="strong", value_text=_pct(value, 0))


@metric("downsideDeviation")
def _downside_deviation(value, **_):
    label = "Downside volatility"
    what = ("The same bounce measure, but counting only the days the price fell. Rising fast "
            "is not risk to someone who owns it.")
    if not _known(value):
        return unavailable(label, what, "needs more than one down day")
    band = _ladder(value, ((0.12, "excellent"), (0.20, "good"), (0.28, "fair"),
                           (0.40, "poor"), (None, "bad")))
    return make(label, what,
                f"About {_pct(value, 0)} a year of downward movement. This is the number the "
                f"Sortino ratio divides by, which is why Sortino is the fairer of the two "
                f"risk-adjusted ratios for someone holding rather than trading.",
                CONTEXT_NOT_TRIGGER, band, "low", evidence="strong",
                value_text=_pct(value, 0))


@metric("sharpe")
def _sharpe(value, riskFree=0.0, **_):
    label = "Sharpe ratio"
    what = ("Return earned per unit of price swing. It answers 'was the bumpy ride paid for?' "
            "with one number.")
    if not _known(value):
        return unavailable(label, what, "needs a return and a volatility to divide")
    band = _ladder(value, ((0.0, "bad"), (0.5, "poor"), (1.0, "fair"),
                           (2.0, "good"), (None, "excellent")))
    reading = (f"{_num(value)} — {_num(value)} units of return above a "
               f"{_pct(riskFree, 1)} risk-free rate for every unit of price swing. ")
    reading += {
        "bad": "Below zero: the holding did worse than simply holding cash, and was volatile doing it.",
        "poor": "Under 0.5 is weak — the swings were not well paid for.",
        "fair": "Between 0.5 and 1 is ordinary; most individual stocks live here.",
        "good": "Above 1 is generally considered good.",
        "excellent": "Above 2 is excellent, and over a short window usually too good to persist.",
    }[band]
    return make(label, what, reading,
                "Sharpe treats a fast rise as risk, which for a holder it is not. Read Sortino "
                "beside it and trust that one more.",
                band, "high", evidence="strong", value_text=_num(value))


@metric("sortino")
def _sortino(value, riskFree=0.0, **_):
    label = "Sortino ratio"
    what = ("Return earned per unit of DOWNSIDE risk — the same idea as Sharpe, but it stops "
            "penalising the stock for going up quickly.")
    if not _known(value):
        return unavailable(label, what, "needs enough down days to measure downside risk")
    band = _ladder(value, ((0.0, "bad"), (0.5, "poor"), (1.0, "fair"),
                           (2.0, "good"), (None, "excellent")))
    reading = (f"{_num(value)} — you earned {_num(value)} units of return above a "
               f"{_pct(riskFree, 1)} risk-free rate for every unit of downside risk. ")
    reading += {
        "bad": "Below zero means the downside was not paid for at all.",
        "poor": "Under 0.5 is weak.",
        "fair": "Between 0.5 and 1 is acceptable but not compelling.",
        "good": "Above 1.0 is generally considered good; above 2.0 is excellent.",
        "excellent": "Above 2.0 is excellent — check it is not one lucky window before believing it.",
    }[band]
    return make(label, what, reading,
                "A persistently negative Sortino is the clearest statistical argument against "
                "holding: the falls were not compensated. Anything above 1 is context.",
                band, "high", evidence="strong", value_text=_num(value))


@metric("calmar")
def _calmar(value, **_):
    label = "Calmar ratio"
    what = ("Yearly return divided by the worst fall the holding ever had. It asks: was the "
            "pain worth the reward?")
    if not _known(value):
        return unavailable(label, what, "needs both a return and a drawdown")
    band = _ladder(value, ((0.0, "bad"), (0.5, "poor"), (1.0, "fair"),
                           (3.0, "good"), (None, "excellent")))
    reading = (f"{_num(value)} — for every 1% of the worst peak-to-trough fall, the holding "
               f"returned about {_num(value)}% a year. ")
    reading += {
        "bad": "Negative: the fall happened and the return did not.",
        "poor": "Under 0.5 means the worst drawdown was several years of returns deep.",
        "fair": "Around 1 means roughly a year of returns to recover the worst fall.",
        "good": "Above 1 is solid for a single stock.",
        "excellent": "Above 3 is exceptional and usually reflects a short, kind history.",
    }[band]
    return make(label, what, reading,
                "This is the ratio that predicts whether you actually hold on. Below 0.5, "
                "assume you will be tested.",
                band, "high", evidence="moderate", value_text=_num(value))


@metric("var95")
def _var95(value, **_):
    label = "Bad-day loss (VaR 95%)"
    what = "How much the price falls on a genuinely bad day — the worst 1 day in 20."
    if not _known(value):
        return unavailable(label, what, "needs about a month of returns")
    magnitude = abs(value)
    band = _ladder(magnitude, ((0.02, "good"), (0.035, "fair"), (0.06, "poor"), (None, "bad")))
    return make(label, what,
                f"On the worst day in a typical month, this fell about {_pct(magnitude)}. One "
                f"trading day in twenty was at least this bad.",
                "Use it as a nerve test. If a one-day fall of this size in your position size "
                "would make you sell, the position is too big.",
                # HIGH, and the SIGN is the whole reason. This is shown as a
                # NEGATIVE percentage, so the better outcome is the LARGER
                # number: -8% beats -60%. Declaring "low" printed an arrow
                # reading "lower is better" beneath a negative value, which
                # tells a reader that a deeper fall is the good one. The
                # colour ladder was right throughout; only the arrow
                # contradicted it, and no test compared the two.
                band, "high", evidence="strong", value_text=_pct(value))


@metric("cvar95")
def _cvar95(value, var95=None, **_):
    label = "Worst-days average (CVaR)"
    what = ("When it does have one of those genuinely bad days, this is the average size of "
            "the fall. It measures how bad 'bad' gets.")
    if not _known(value):
        return unavailable(label, what, "needs enough tail days to average")
    magnitude = abs(value)
    band = _ladder(magnitude, ((0.03, "good"), (0.05, "fair"), (0.08, "poor"), (None, "bad")))
    reading = f"Across the worst 5% of days, the average fall was {_pct(magnitude)}."
    if _known(var95) and abs(var95) > 0:
        ratio = magnitude / abs(var95)
        reading += (f" That is {_num(ratio, 1)}x the bad-day threshold above — the further "
                    f"past 1.0 this gets, the more the really bad days cluster far out.")
    return make(label, what, reading,
                CONTEXT_NOT_TRIGGER + " It tells you the shape of the tail, not when it arrives.",
                # HIGH, and the SIGN is the whole reason. This is shown as a
                # NEGATIVE percentage, so the better outcome is the LARGER
                # number: -8% beats -60%. Declaring "low" printed an arrow
                # reading "lower is better" beneath a negative value, which
                # tells a reader that a deeper fall is the good one. The
                # colour ladder was right throughout; only the arrow
                # contradicted it, and no test compared the two.
                band, "high", evidence="strong", value_text=_pct(value))


@metric("skew")
def _skew(value, **_):
    label = "Lopsidedness (skew)"
    what = ("Whether the surprises come as sharp falls or sharp jumps. Negative means the "
            "violent days tend to be down days.")
    if not _known(value):
        return unavailable(label, what, "needs about a month of returns")
    if value < -0.5:
        reading = (f"{_num(value)} — clearly negative. The big moves in this name have mostly "
                   f"been falls: it drips up and gaps down.")
    elif value < 0.5:
        reading = (f"{_num(value)} — near zero, so up-surprises and down-surprises have been "
                   f"about the same size. That is the normal case.")
    else:
        reading = (f"{_num(value)} — positive. The outsized days have mostly been jumps up, "
                   f"which is the friendlier shape to hold.")
    return make(label, what, reading,
                CONTEXT_NOT_TRIGGER + " Skew describes the past shape of surprises; it does "
                "not forecast the next one.",
                "context", "none", evidence="moderate", value_text=_num(value))


@metric("kurtosis")
def _kurtosis(value, **_):
    label = "Fat tails (excess kurtosis)"
    what = ("How often this stock does something extreme. Zero would mean it behaves like a "
            "textbook bell curve; higher means shock days happen far more often than that.")
    if not _known(value):
        return unavailable(label, what, "needs about a month of returns")
    if value < 1:
        reading = (f"{_num(value, 1)} — close to a normal bell curve. Extreme days are about "
                   f"as rare as the textbook says.")
    elif value < 5:
        reading = (f"{_num(value, 1)} — fatter tails than a bell curve. Shock days happen "
                   f"noticeably more often than a standard risk model assumes. This is "
                   f"completely normal for a single stock.")
    else:
        reading = (f"{_num(value, 1)} — very fat tails. This name has a real history of days "
                   f"that no normal-distribution model would predict in a lifetime.")
    return make(label, what, reading,
                "It is the reason the loss figures above are measured from actual history "
                "rather than from a formula. " + CONTEXT_NOT_TRIGGER,
                "context", "none", evidence="strong", value_text=_num(value, 1))


@metric("positiveDays")
def _positive_days(value, **_):
    label = "Up days"
    what = "The share of trading days that finished higher than the day before."
    if not _known(value):
        return unavailable(label, what, "needs a return series")
    return make(label, what,
                f"{_pct(value, 0)} of days closed up. Almost every stock sits near 50% — "
                f"returns come from the SIZE of the up days, not from how many there are, "
                f"so this number is much less informative than it looks.",
                CONTEXT_NOT_TRIGGER, "context", "none", evidence="strong",
                value_text=_pct(value, 0))


@metric("worstDay")
def _worst_day(value, **_):
    label = "Worst single day"
    what = "The largest one-day fall in this history."
    if not _known(value):
        return unavailable(label, what, "needs a return series")
    magnitude = abs(value)
    band = _ladder(magnitude, ((0.07, "good"), (0.12, "fair"), (0.20, "poor"), (None, "bad")))
    return make(label, what,
                f"The worst day here fell {_pct(magnitude)}. It has happened once, so it can "
                f"happen again.",
                # HIGH, and the SIGN is the whole reason. This is shown as a
                # NEGATIVE percentage, so the better outcome is the LARGER
                # number: -8% beats -60%. Declaring "low" printed an arrow
                # reading "lower is better" beneath a negative value, which
                # tells a reader that a deeper fall is the good one. The
                # colour ladder was right throughout; only the arrow
                # contradicted it, and no test compared the two.
                CONTEXT_NOT_TRIGGER, band, "high", evidence="strong", value_text=_pct(value))


@metric("bestDay")
def _best_day(value, **_):
    label = "Best single day"
    what = "The largest one-day rise in this history."
    if not _known(value):
        return unavailable(label, what, "needs a return series")
    return make(label, what,
                f"The best day here rose {_pct(value)}. Big up days and big down days tend to "
                f"arrive in the same weeks, so this is a volatility reading as much as a "
                f"good-news one.",
                CONTEXT_NOT_TRIGGER, "context", "none", evidence="strong",
                value_text=_signed_pct(value))


# ============================================================================ #
# Drawdown — the numbers that decide whether someone actually holds on
# ============================================================================ #
@metric("maxDrawdown")
def _max_drawdown(value, **_):
    label = "Worst fall (max drawdown)"
    what = ("The deepest peak-to-bottom fall in this history — how much someone who bought at "
            "the worst possible moment was down before it turned.")
    if not _known(value):
        return unavailable(label, what, "needs at least three priced days")
    depth = abs(value)
    band = _ladder(depth, ((0.20, "good"), (0.35, "fair"), (0.50, "poor"), (None, "bad")))
    recovery = 1.0 / (1.0 - depth) - 1.0 if depth < 0.999 else None
    reading = f"Fell {_pct(depth, 0)} from its high at the worst point. "
    if recovery is not None:
        reading += (f"Getting back to even from there needed a {_pct(recovery, 0)} rise, "
                    f"because a fall and its recovery are not the same percentage. ")
    reading += {
        "good": "Under 20% is mild for a single stock.",
        "fair": "A fall of this size is normal for an individual stock over a long window.",
        "poor": "A fall this deep tests most holders. Assume it repeats.",
        "bad": "Over half the value gone. Whatever the return figures say, this is the number "
               "that decides whether the position was ever holdable.",
    }[band]
    return make(label, what, reading,
                "Size the position so a repeat of this fall does not force you out. That is "
                "the decision this number is for.",
                # HIGH, and the SIGN is the whole reason. This is shown as a
                # NEGATIVE percentage, so the better outcome is the LARGER
                # number: -8% beats -60%. Declaring "low" printed an arrow
                # reading "lower is better" beneath a negative value, which
                # tells a reader that a deeper fall is the good one. The
                # colour ladder was right throughout; only the arrow
                # contradicted it, and no test compared the two.
                band, "high", evidence="strong", value_text=_pct(value, 0))


@metric("currentDrawdown")
def _current_drawdown(value, **_):
    label = "Below its high right now"
    what = "How far the price currently sits under its own best-ever level."
    if not _known(value):
        return unavailable(label, what, "needs a price history")
    depth = abs(value)
    if depth < 0.02:
        return make(label, what,
                    f"{_pct(depth)} below its peak, which is effectively at the high — "
                    f"everyone who has ever owned it is in profit.",
                    CONTEXT_NOT_TRIGGER, "good", "high", evidence="strong",
                    value_text=_pct(value, 1))
    band = _ladder(depth, ((0.10, "good"), (0.25, "fair"), (0.45, "poor"), (None, "bad")))
    return make(label, what,
                f"Currently {_pct(depth)} below its peak. Anyone who bought at that peak is "
                f"still down by that much.",
                CONTEXT_NOT_TRIGGER + " Being far below a high is neither cheap nor broken on "
                "its own — the Value and Quality lenses are what settle that.",
                # HIGH, and the SIGN is the whole reason. This is shown as a
                # NEGATIVE percentage, so the better outcome is the LARGER
                # number: -8% beats -60%. Declaring "low" printed an arrow
                # reading "lower is better" beneath a negative value, which
                # tells a reader that a deeper fall is the good one. The colour
                # ladder was right throughout; only the arrow contradicted it,
                # and no test compared the two. Note `band` is picked from
                # `depth`, the absolute value — which is why the ladder reads
                # low-is-good while the DISPLAYED number does not.
                band, "high", evidence="strong", value_text=_pct(value, 1))


@metric("timeUnderWaterDays")
def _time_under_water(value, **_):
    label = "Longest time under water"
    what = ("The longest unbroken stretch spent below a previous high — how long a holder went "
            "without seeing a new best price.")
    if not _known(value):
        return unavailable(label, what, "needs a price history")
    days = float(value)
    band = _ladder(days, ((60, "good"), (250, "fair"), (500, "poor"), (None, "bad")))
    years = days / 252.0
    span = (f"{days:.0f} trading days — about {years:.1f} years"
            if days >= 252 else f"{days:.0f} trading days — about {days / 21:.0f} months")
    reading = f"{span} of holding without a new high. "
    reading += {
        "good": "Short enough that impatience was never really tested.",
        "fair": "Long enough to be uncomfortable, short enough to be normal.",
        "poor": "A stretch this long is where most people give up and sell.",
        "bad": "Years of no progress. Depth is not what breaks conviction — this is.",
    }[band]
    return make(label, what, reading,
                "If a period this long with nothing to show would make you abandon the "
                "position, this is not a holding you can size large.",
                band, "low", evidence="moderate", value_text=f"{days:.0f} d")


@metric("ulcerIndex")
def _ulcer(value, **_):
    label = "Ulcer index"
    what = ("A single score for how uncomfortable holding this has been — it combines how far "
            "the price fell below its highs with how LONG it stayed there. A long shallow "
            "grind scores worse than a sharp fall that recovers, because that is how it feels.")
    if not _known(value):
        return unavailable(label, what, "needs a price history")
    band = _ladder(value, ((5, "excellent"), (10, "good"), (20, "fair"),
                           (30, "poor"), (None, "bad")))
    reading = f"{_num(value, 1)}. "
    reading += {
        "excellent": "Very low — this has spent most of its life at or near its highs.",
        "good": "Low. Falls have been shallow, or brief, or both.",
        "fair": "Middling. There have been real stretches below the highs, but not punishing ones.",
        "poor": "High. This has spent a lot of its life meaningfully underwater.",
        "bad": "Very high — long, deep periods below the high. Hard to hold, whatever it returned.",
    }[band]
    reading += (" Lower is better; roughly, under 5 is calm, over 20 is a difficult holding. "
                "The scale is in percentage points, so it is comparable between stocks but not "
                "meaningful in isolation.")
    return make(label, what, reading,
                "Read it next to the worst-fall number. A modest worst fall with a high Ulcer "
                "index means the pain was slow rather than sharp.",
                band, "low", evidence="moderate", value_text=_num(value, 1))


@metric("maxDrawdownRecoveryDays")
def _recovery_days(value, **_):
    label = "Time to recover"
    what = "How long it took to climb back to the old high after that worst fall."
    if not _known(value):
        return make(label, what,
                    "It has not recovered. The price is still below the peak it fell from, so "
                    "this history contains no example of it coming back.",
                    "An unrecovered drawdown is not a verdict — but it means every recovery "
                    "figure here is a hope rather than an observation.",
                    "caution", "low", evidence="strong", value_text="not yet")
    days = float(value)
    band = _ladder(days, ((180, "good"), (500, "fair"), (1000, "poor"), (None, "bad")))
    return make(label, what,
                f"{days:.0f} calendar days — about {days / 365.25:.1f} years to get back to "
                f"where it had already been.",
                CONTEXT_NOT_TRIGGER + " It is the closest thing here to an estimate of how "
                "long a bad entry takes to forgive.",
                band, "low", evidence="moderate", value_text=f"{days:.0f} d")


# ============================================================================ #
# Trend, momentum and position
# ============================================================================ #
@metric("hurst")
def _hurst(value, stderr=None, verdict=None, low=None, high=None, observations=None, **_):
    label = "Trend or noise? (Hurst exponent)"
    what = ("A test of whether this price series has real memory or is essentially a coin "
            "flip. 0.5 means a random walk — moves tell you nothing about the next move.")
    if not _known(value):
        return unavailable(label, what, "needs roughly 100 bars of history")

    # THE ERROR BAR IS NOT DECORATION. This measure is noisy: on five years of
    # daily bars its standard error is about 0.05, so the fixed 0.45-0.55 band
    # this reading used to be judged against was barely one standard error wide
    # and called a genuine random walk "trending" a third of the time. The
    # verdict now comes from `indicators.hurst_estimate`, whose band widens when
    # there is less history — which is why a short range says "cannot tell"
    # instead of confidently saying the wrong thing.
    figure = f"{_num(value)}" + (f" ± {_num(stderr)}" if _known(stderr) else "")
    span = (f"{_num(low)} to {_num(high)}" if _known(low) and _known(high)
            else "0.45 to 0.55")

    if verdict == "persistent":
        band, reading = "good", (
            f"{figure} — above {_num(high)}, which is further from 0.5 than the estimate's own "
            f"error. Moves have tended to continue, so trend-following tools have something "
            f"real to work with on this name.")
    elif verdict == "meanReverting":
        band, reading = "caution", (
            f"{figure} — below {_num(low)}, meaning moves have tended to REVERSE. Rallies here "
            f"have historically been given back, and trend-following would have been punished.")
    else:
        band, reading = "caution", (
            f"{figure} — inside {span}, which is the range a genuine random walk produces at "
            f"this sample size. The measure simply cannot tell this series apart from a coin "
            f"flip, so every trend line, moving average and momentum reading on this page is "
            f"probably describing noise.")
    if _known(observations) and observations < 750:
        reading += (f" Note it has only {int(observations)} days to work with; this measure "
                    f"needs several years before it can say much at all, so widen the range "
                    f"before reading anything into it.")
    return make(label, what, reading,
                "This is the honesty check on the rest of the technical lens. When it cannot "
                "separate the series from a random walk, downgrade everything else here rather "
                "than acting on it.",
                band, "none", evidence="moderate", value_text=_num(value))


@metric("momentum12_1")
def _momentum_12_1(value, **_):
    label = "12-1 month momentum"
    what = ("How much the price rose over the twelve months ending ONE month ago. The recent "
            "month is deliberately skipped, because very short-term moves tend to snap back "
            "and would pollute the reading.")
    if not _known(value):
        return unavailable(label, what, "needs about a year of history")
    band = "good" if value > 0 else "poor"
    reading = (f"{_signed_pct(value)} over that window. "
               + ("Positive, which historically is the side of this measure that has done "
                  "better across large groups of stocks."
                  if value > 0 else
                  "Negative. Across large samples, names on this side have tended to keep "
                  "lagging for a while."))
    return make(label, what, reading,
                "One of the few technical signals with decades of out-of-sample support "
                "across many markets — but it is a statement about averages over hundreds of "
                "stocks, not a forecast for this one.",
                band, "high", evidence="strong", value_text=_signed_pct(value))


@metric("roc252")
def _roc252(value, **_):
    label = "One-year price change"
    what = "How much the price has moved over the last twelve months, as a percentage."
    if not _known(value):
        return unavailable(label, what, "needs a year of history")
    return make(label, what,
                f"{value:+.1f}% over the past year. That is the whole twelve months including "
                f"the most recent weeks, so it is a plainer number than the 12-1 momentum "
                f"reading above and a slightly less useful one.",
                CONTEXT_NOT_TRIGGER, "good" if value > 0 else "poor", "high",
                evidence="moderate", value_text=f"{value:+.1f}%")


@metric("roc63")
def _roc63(value, **_):
    label = "Three-month price change"
    what = "How much the price has moved over the last quarter, as a percentage."
    if not _known(value):
        return unavailable(label, what, "needs a quarter of history")
    return make(label, what,
                f"{value:+.1f}% over the past three months — a quarter is short enough that "
                f"one earnings report can account for the whole figure.",
                CONTEXT_NOT_TRIGGER, "good" if value > 0 else "poor", "high",
                evidence="moderate", value_text=f"{value:+.1f}%")


@metric("faberDistance")
def _faber_distance(value, signal=None, monthsInStance=None, **_):
    label = "Faber 10-month rule"
    what = ("A very simple published rule: stay invested while the month-end price is above "
            "its average of the last ten month-ends, step aside when it drops below. It trades "
            "once or twice a year at most.")
    if not _known(value):
        return unavailable(label, what, "needs about a year of month-end closes")
    invested = signal == "invested"
    stance = (f"{monthsInStance} month{'s' if monthsInStance != 1 else ''} in this stance"
              if _known(monthsInStance) else "")
    reading = (f"The latest monthly close is {_signed_pct(value)} versus its 10-month average, "
               f"so the rule says {'STAY INVESTED' if invested else 'STAND ASIDE'}"
               + (f" — {stance}." if stance else "."))
    return make(label, what, reading,
                "Its documented benefit is shallower falls, not higher returns. If you would "
                "not actually sell on a signal flip, treat it as context rather than a rule.",
                "good" if invested else "poor", "high", evidence="moderate",
                value_text=_signed_pct(value))


@metric("fromHigh52w")
def _from_high(value, **_):
    label = "Distance from the 52-week high"
    what = "How far below (or above) its best price of the past year it is trading."
    if not _known(value):
        return unavailable(label, what, "needs a year of history")
    gap = abs(value)
    band = _ladder(gap, ((0.05, "excellent"), (0.15, "good"), (0.30, "fair"),
                         (0.50, "poor"), (None, "bad")))
    reading = (f"{_signed_pct(value)} from its 52-week high. "
               + ("Right at the top of its yearly range." if gap < 0.05
                  else "Well off its yearly high." if gap > 0.30
                  else "Somewhat below its yearly high."))
    return make(label, what, reading,
                "Nearness to the 52-week high is itself a documented momentum variable — "
                "names near their highs have on average kept doing better. It is an average "
                "across many stocks, not a promise about this one.",
                band, "high", evidence="moderate", value_text=_signed_pct(value))


@metric("fromAllTimeHigh")
def _from_ath(value, **_):
    label = "Distance from the all-time high"
    what = "How far below its best price ever it is trading, over the window loaded here."
    if not _known(value):
        return unavailable(label, what, "needs a price history")
    gap = abs(value)
    band = _ladder(gap, ((0.05, "excellent"), (0.20, "good"), (0.40, "fair"),
                         (0.60, "poor"), (None, "bad")))
    return make(label, what,
                f"{_signed_pct(value)} from the highest price in this window. "
                + ("At or near a record." if gap < 0.05 else
                   f"Recovering this alone needs a {_pct(gap / (1 - gap), 0)} rise."),
                CONTEXT_NOT_TRIGGER + " A large gap is not cheapness; the business decides that.",
                band, "high", evidence="weak", value_text=_signed_pct(value))


@metric("rangePosition")
def _range_position(value, **_):
    label = "Position in the 52-week range"
    what = ("Where today's price sits between the lowest and highest price of the past year. "
            "0% is the year's low, 100% is the year's high.")
    if not _known(value):
        return unavailable(label, what, "needs a year of history")
    band = _ladder(value, ((0.2, "poor"), (0.45, "fair"), (0.75, "good"), (None, "excellent")))
    return make(label, what,
                f"{_pct(value, 0)} of the way up its yearly range.",
                CONTEXT_NOT_TRIGGER, band, "high", evidence="weak",
                value_text=_pct(value, 0))


@metric("regressionSlope")
def _regression_slope(value, rSquared=None, **_):
    label = "Fitted long-run trend"
    what = ("A straight line drawn through the price history, reported as the yearly slope of "
            "that line. It is the plainest possible summary of direction.")
    if not _known(value):
        return unavailable(label, what, "needs about a year of history")
    band = "good" if value > 0 else "poor"
    reading = f"The fitted line rises {_signed_pct(value)} a year."
    if _known(rSquared):
        if rSquared < 0.3:
            band = "caution"
            reading += (f" But the fit is poor (R² {_pct(rSquared, 0)}) — the price is nowhere "
                        f"near that line, so the slope is close to meaningless here.")
        elif rSquared < 0.5:
            reading += (f" The fit is loose (R² {_pct(rSquared, 0)}), so read the slope as a "
                        f"rough direction rather than a rate.")
        else:
            reading += f" The fit is reasonable (R² {_pct(rSquared, 0)})."
    return make(label, what, reading,
                "A trend line describes the past exactly and forecasts nothing. Check the "
                "Hurst reading before giving it any weight.",
                band, "high", evidence="weak", value_text=_signed_pct(value))


@metric("regressionR2")
def _regression_r2(value, **_):
    label = "Trend fit (R²)"
    what = ("How closely the price has actually hugged that straight trend line. 100% would "
            "be a perfect ruler-straight rise; 0% means the line explains nothing.")
    if not _known(value):
        return unavailable(label, what, "needs about a year of history")
    band = _ladder(value, ((0.3, "caution"), (0.5, "fair"), (0.75, "good"), (None, "excellent")))
    reading = (f"{_pct(value, 0)}. "
               + {"caution": "The price barely follows the line at all — do not read the slope as a rate.",
                  "fair": "A loose fit. The direction is indicative, the rate is not.",
                  "good": "A reasonable fit; the trend line is a fair summary of the path.",
                  "excellent": "A tight fit — the price has tracked this line closely."}[band])
    return make(label, what, reading,
                "This is a quality check on the line above, not a signal in itself.",
                band, "high", evidence="weak", value_text=_pct(value, 0))


@metric("relativeExcess")
def _relative_excess(value, period=None, benchmark=None, **_):
    label = f"Versus the index{f' ({period})' if period else ''}"
    what = ("How much better or worse this did than simply buying the market index over the "
            "same stretch. The index fund is the real alternative — not cash.")
    if not _known(value):
        return unavailable(label, what, "needs overlapping history with the index")
    band = _ladder(value, ((-0.10, "bad"), (0.0, "poor"), (0.10, "good"), (None, "excellent")))
    name = index_name(benchmark)
    reading = (f"{_signed_pct(value)} versus {name}. "
               + ("Ahead of the index over this stretch." if value > 0 else
                  "Behind the index over this stretch — the same money in an index fund would "
                  "have done better."))
    return make(label, what, reading,
                "A stock up 40% while the market rose 60% has cost its holder money in the "
                "only sense that matters. This row is the one that decides whether picking "
                "this name was worth the effort.",
                band, "high", evidence="strong", value_text=_signed_pct(value))


@metric("benchmarkCorrelation")
def _correlation(value, benchmark=None, **_):
    label = "Correlation with the index"
    what = ("How closely this moves in step with the whole market. 1.0 would be perfect "
            "lockstep, 0 would be completely independent.")
    if not _known(value):
        return unavailable(label, what, "needs overlapping history with the index")
    if value > 0.8:
        detail = ("Very tightly tied to the market — most of what happens here is just the "
                  "market happening. It adds little diversification.")
    elif value > 0.5:
        detail = "Moves broadly with the market, with a real amount of its own behaviour on top."
    elif value > 0.2:
        detail = "Only loosely tied to the market; much of its movement is its own."
    else:
        detail = "Largely independent of the market, which is unusual and worth understanding."
    return make(label, what, f"{_num(value)} against {index_name(benchmark)}. {detail}",
                CONTEXT_NOT_TRIGGER + " High correlation is not bad — it just means this is "
                "not a diversifier.",
                "context", "none", evidence="strong", value_text=_num(value))


@metric("rollingWorst")
def _rolling_worst(value, years=None, positiveShare=None, reason=None, windows=None, **_):
    horizon = f"{years}-year" if years else "multi-year"
    label = f"Worst {horizon} outcome"
    what = (f"Out of every possible {horizon} holding period in this history, the one that "
            f"turned out worst. It answers 'what if I had bought at the worst moment?'")
    if not _known(value):
        # The row carries WHY, including how much history is missing. A generic
        # "needs more years" would hide that the fix is one dropdown away.
        return unavailable(
            label, what,
            (reason or f"needs more than {years or 'several'} years of history").rstrip("."))
    band = _ladder(value, ((-0.10, "bad"), (0.0, "poor"), (0.05, "fair"),
                           (0.12, "good"), (None, "excellent")))
    reading = (f"The unluckiest {horizon} entry still returned {_signed_pct(value)} a year. ")
    if _known(positiveShare):
        reading += (f"{_pct(positiveShare, 0)} of all {horizon} windows finished in profit. ")
    reading += ("Every one of them made money." if value > 0 else
                "At least one entry point lost money over the full period.")
    return make(label, what, reading,
                "This is the number that should set your position size — not the headline "
                "annual return, which quietly describes one lucky starting date.",
                band, "high", evidence="strong", value_text=_signed_pct(value))


# ============================================================================ #
# Classical indicators
#
# EVIDENCE IS NOT UNIFORM HERE and the `evidence` field says so. Trend and
# time-series momentum have decades of cross-market out-of-sample support;
# oscillator overbought/oversold levels have very little once trading costs are
# taken out. Both used to be printed in the same type on the same grid, which
# is exactly the impression this field exists to correct.
# ============================================================================ #
def _distance_reading(price, level, name):
    """Distance from a moving average, with BOTH numbers in the sentence.

    The panel shows the level and the prose discusses the gap; quoting only one
    of them leaves the reader matching a percentage against a price.
    """
    gap = price / level - 1.0
    side = "above" if gap >= 0 else "below"
    return gap, (f"The {name} sits at {_num(level)}, and the price is "
                 f"{_pct(abs(gap))} {side} it.")


@metric("sma200")
def _sma200(value, price=None, **_):
    label = "200-day average"
    what = ("The average closing price of the last 200 trading days — the most widely watched "
            "single line in markets, and a rough divide between 'in an uptrend' and not.")
    if not _known(value) or not _known(price):
        return unavailable(label, what, "needs 200 trading days of history")
    gap, sentence = _distance_reading(price, value, "200-day average")
    above = gap >= 0
    reading = sentence + (
        " Being above it is the plainest definition of a long-term uptrend."
        if above else
        " Being below it is the plainest definition of a long-term downtrend.")
    if abs(gap) > 0.30:
        reading += (" It is a long way from the line, though, which usually means the move is "
                    "stretched rather than freshly confirmed.")
    return make(label, what, reading,
                "Long-horizon trend rules built on this line are among the better-supported "
                "technical signals — their documented benefit is smaller falls, not bigger "
                "gains.",
                "good" if above else "poor", "high", evidence="moderate",
                value_text=_num(value))


@metric("sma100")
def _sma100(value, price=None, **_):
    label = "100-day average"
    what = "The average closing price of the last 100 trading days — a medium-term trend line."
    if not _known(value) or not _known(price):
        return unavailable(label, what, "needs 100 trading days of history")
    gap, sentence = _distance_reading(price, value, "100-day average")
    return make(label, what, sentence, CONTEXT_NOT_TRIGGER,
                "good" if gap >= 0 else "poor", "high", evidence="weak",
                value_text=_num(value))


@metric("sma50")
def _sma50(value, price=None, **_):
    label = "50-day average"
    what = "The average closing price of the last 50 trading days — a short-to-medium trend line."
    if not _known(value) or not _known(price):
        return unavailable(label, what, "needs 50 trading days of history")
    gap, sentence = _distance_reading(price, value, "50-day average")
    return make(label, what,
                sentence + " Traders often watch this line as the level a healthy uptrend "
                           "pulls back to rather than breaks.",
                CONTEXT_NOT_TRIGGER, "good" if gap >= 0 else "poor", "high",
                evidence="weak", value_text=_num(value))


@metric("adx")
def _adx(value, plusDi=None, minusDi=None, **_):
    label = "ADX (trend strength)"
    what = ("How strongly the price is trending — in EITHER direction. A high ADX in a "
            "collapse looks the same as a high ADX in a rally: it measures conviction, not "
            "which way.")
    if not _known(value):
        return unavailable(label, what, "needs about a month of history")
    if value < 20:
        band, verdict = "caution", (
            f"ADX {value:.0f} — under 20 means there is no real trend. The price is drifting "
            f"sideways, and trend-following signals here tend to whipsaw.")
    elif value < 25:
        band, verdict = "caution", (
            f"ADX {value:.0f} — borderline. A trend may be forming but has not established itself.")
    elif value < 40:
        band, verdict = "context", f"ADX {value:.0f} — a genuine trend is in place."
    else:
        band, verdict = "context", (
            f"ADX {value:.0f} — a very strong trend, and often a late-stage one; readings this "
            f"high historically cool off rather than climb further.")
    if _known(plusDi) and _known(minusDi) and value >= 20:
        verdict += (" The direction is UP" if plusDi > minusDi else " The direction is DOWN")
        verdict += f" (+DI {plusDi:.0f} versus -DI {minusDi:.0f})."
    return make(label, what, verdict,
                "Use it as a filter, not a signal: it says whether the OTHER trend readings on "
                "this page deserve any weight.",
                band, "none", evidence="weak", value_text=f"{value:.0f}")


@metric("aroon")
def _aroon(value, aroonDown=None, **_):
    label = "Aroon"
    what = ("How recently the price set a new high versus a new low, each scored 0-100. "
            "100 on the up side means it made its highest price today.")
    if not _known(value) or not _known(aroonDown):
        return unavailable(label, what, "needs about 25 bars of history")
    up = float(value)
    down = float(aroonDown)
    if up > 70 and down < 30:
        band, verdict = "good", (f"Up {up:.0f} versus down {down:.0f} — new highs are recent and "
                                 f"new lows are stale. That is an uptrend by this measure.")
    elif down > 70 and up < 30:
        band, verdict = "poor", (f"Down {down:.0f} versus up {up:.0f} — new lows are recent and "
                                 f"new highs are stale. A downtrend by this measure.")
    else:
        band, verdict = "context", (f"Up {up:.0f} versus down {down:.0f} — neither side dominates, "
                                    f"so this is a sideways reading.")
    return make(label, what, verdict, CONTEXT_NOT_TRIGGER, band, "high",
                evidence="weak", value_text=f"{up:.0f} / {down:.0f}")


@metric("rsi")
def _rsi_metric(value, **_):
    label = "RSI (14)"
    what = ("A 0-100 speedometer of recent buying versus selling pressure. Above 70 is the "
            "traditional 'overbought' line, below 30 'oversold'.")
    if not _known(value):
        return unavailable(label, what, "needs 14 bars of history")
    if value >= 70:
        band, verdict = "caution", (
            f"{value:.0f} — traditionally 'overbought'. Be careful with that word: in a strong "
            f"uptrend RSI can sit above 70 for months, and selling every time it crossed 70 "
            f"would have been costly. It means stretched, not doomed.")
    elif value <= 30:
        band, verdict = "caution", (
            f"{value:.0f} — traditionally 'oversold'. It means the fall has been fast, not that "
            f"it is over; in a real downtrend RSI stays low for a long time.")
    else:
        band, verdict = "context", (
            f"{value:.0f} — in the middle of the range, which is where it sits most of the time. "
            f"No signal either way.")
    return make(label, what, verdict,
                "The evidence that RSI levels predict returns is weak once trading costs are "
                "counted. Treat it as a description of how stretched the last two weeks were.",
                band, "none", evidence="weak", value_text=f"{value:.0f}")


@metric("stochastic")
def _stochastic(value, stochD=None, **_):
    label = "Stochastic"
    what = ("Where today's close sits inside the high-low range of the last two weeks. 100 "
            "means it closed at the very top of that range.")
    if not _known(value):
        return unavailable(label, what, "needs about 17 bars of history")
    if value >= 80:
        band, verdict = "caution", f"{value:.0f} — closing near the top of its recent range."
    elif value <= 20:
        band, verdict = "caution", f"{value:.0f} — closing near the bottom of its recent range."
    else:
        band, verdict = "context", f"{value:.0f} — mid-range."
    if _known(stochD):
        verdict += f" (%K {value:.0f} against its %D average of {stochD:.0f}.)"
    return make(label, what, verdict,
                "A very short-horizon description with little out-of-sample support. It is "
                "entry timing at most, never a reason to own something.",
                band, "none", evidence="weak", value_text=f"{value:.0f}")


@metric("williamsR")
def _williams(value, **_):
    label = "Williams %R"
    what = ("The same idea as the Stochastic, flipped onto a -100 to 0 scale. Near 0 means "
            "closing at the top of the recent range, near -100 the bottom.")
    if not _known(value):
        return unavailable(label, what, "needs 14 bars of history")
    if value >= -20:
        band, verdict = "caution", (
            f"{value:.0f} — pinned near the top of its two-week range, which the textbooks call "
            f"overbought. In a strong trend it can stay here for weeks.")
    elif value <= -80:
        band, verdict = "caution", (
            f"{value:.0f} — pinned near the bottom of its two-week range. The fall has been "
            f"fast; that is not the same as it being over.")
    else:
        band, verdict = "context", (
            f"{value:.0f} — somewhere in the middle of its two-week range, which is where it "
            f"spends most of its time. Nothing to read into it.")
    return make(label, what, verdict,
                "Near-duplicate of the Stochastic above; if the two disagree it is a rounding "
                "difference, not information. Weak evidence either way.",
                band, "none", evidence="weak", value_text=f"{value:.0f}")


@metric("cci")
def _cci(value, **_):
    label = "CCI"
    what = ("How far the price has strayed from its own recent average, scaled so that most "
            "readings fall between -100 and +100.")
    if not _known(value):
        return unavailable(label, what, "needs 20 bars of history")
    if value > 100:
        band, verdict = "caution", (
            f"{value:.0f} — stretched well above its own recent average. A move this far from "
            f"the mean is unusual, though a genuine trend can hold there.")
    elif value < -100:
        band, verdict = "caution", (
            f"{value:.0f} — stretched well below its own recent average, which is unusual but "
            f"not by itself a floor.")
    else:
        band, verdict = "context", (
            f"{value:.0f} — inside the -100 to +100 band where roughly three-quarters of all "
            f"readings fall. The price is not unusually far from its own average.")
    return make(label, what, verdict,
                "A stretch measure, not a direction. " + CONTEXT_NOT_TRIGGER,
                band, "none", evidence="weak", value_text=f"{value:.0f}")


@metric("macd")
def _macd_metric(value, macdSignal=None, **_):
    label = "MACD"
    what = ("The gap between a fast and a slow average of the price. Above its own signal "
            "line means the recent trend is accelerating; below means it is fading.")
    if not _known(value) or not _known(macdSignal):
        return unavailable(label, what, "needs about 35 bars of history")
    above = value > macdSignal
    return make(label, what,
                f"{_num(value)} against a signal line of {_num(macdSignal)} — "
                + ("above it, so momentum is currently building."
                   if above else "below it, so momentum is currently fading.")
                + " The distance between the two matters more than the crossing itself, which "
                  "arrives late by construction.",
                "MACD is a smoothed restatement of the trend you can already see on the chart. "
                "Weak standalone evidence; useful mainly for spotting divergence against price.",
                "good" if above else "poor", "high", evidence="weak", value_text=_num(value))


@metric("bbPercentB")
def _percent_b(value, **_):
    label = "Bollinger %B"
    what = ("Where the price sits inside its volatility bands. 0 is the lower band, 1 is the "
            "upper band, 0.5 is the middle. Above 1 or below 0 means it has broken out of them.")
    if not _known(value):
        return unavailable(label, what, "needs 20 bars of history")
    if value > 1:
        band, verdict = "caution", (
            f"{_num(value)} — trading ABOVE the upper band. That is an unusually strong move, "
            f"not automatically an overpriced one: strong trends walk the upper band for weeks.")
    elif value < 0:
        band, verdict = "caution", (
            f"{_num(value)} — trading BELOW the lower band, an unusually weak move.")
    elif value > 0.8:
        band, verdict = "context", f"{_num(value)} — in the upper fifth of its band range."
    elif value < 0.2:
        band, verdict = "context", f"{_num(value)} — in the lower fifth of its band range."
    else:
        band, verdict = "context", f"{_num(value)} — comfortably inside the bands."
    return make(label, what, verdict,
                "Bands describe volatility, not value. " + CONTEXT_NOT_TRIGGER,
                band, "none", evidence="weak", value_text=_num(value))


@metric("bbBandwidth")
def _bandwidth(value, squeezePercentile=None, **_):
    label = "Bollinger bandwidth"
    what = ("How wide the volatility bands are right now, as a share of the price. Narrow "
            "bands mean the price has gone quiet; wide bands mean it is swinging hard.")
    if not _known(value):
        return unavailable(label, what, "needs 20 bars of history")
    reading = f"{_pct(value, 1)} of price wide."
    band = "context"
    if _known(squeezePercentile):
        reading += (f" That is narrower than {_pct(1 - squeezePercentile, 0)} of the past year "
                    if squeezePercentile <= 0.5 else
                    f" That is wider than {_pct(squeezePercentile, 0)} of the past year ")
        reading += "of readings."
        if squeezePercentile <= 0.15:
            band = "caution"
            reading += (" Bands this tight are called a 'squeeze'. Quiet periods do tend to be "
                        "followed by loud ones — but the squeeze says NOTHING about which "
                        "direction the loud move goes, which is the part most write-ups skip.")
    return make(label, what, reading,
                "A squeeze is a volatility forecast, not a direction forecast. Anyone telling "
                "you it predicts a breakout upward is adding a claim the measure cannot make.",
                band, "none", evidence="weak", value_text=_pct(value, 1))


@metric("atrPct")
def _atr_pct(value, atr=None, **_):
    label = "Daily range (ATR)"
    what = ("How much this typically moves in a single day, including overnight gaps, as a "
            "percentage of the price. It is the natural unit for setting a stop-loss.")
    if not _known(value):
        return unavailable(label, what, "needs 14 bars of history")
    band = _ladder(value, ((0.015, "excellent"), (0.025, "good"), (0.04, "fair"),
                           (0.07, "poor"), (None, "bad")))
    reading = (f"A typical day moves about {_pct(value, 1)}"
               + (f" ({_num(atr)} in price terms)" if _known(atr) else "") + ". ")
    reading += {
        "excellent": "Very steady for a single stock.",
        "good": "Normal daily movement.",
        "fair": "Livelier than average — stops need room.",
        "poor": "Large daily swings. A tight stop here gets hit by ordinary noise.",
        "bad": "Extremely volatile day to day.",
    }[band]
    return make(label, what, reading,
                "Set stops in multiples of this, not in round percentages: a 5% stop on a name "
                "that moves 6% a day is a coin flip, not a risk control.",
                band, "low", evidence="strong", value_text=_pct(value, 1))


@metric("mfi")
def _mfi(value, **_):
    label = "Money flow index"
    what = ("Like RSI, but it weights each day by how much money changed hands. It asks "
            "whether the buying or the selling had volume behind it.")
    if not _known(value):
        return unavailable(label, what, "needs 14 bars with volume")
    if value >= 80:
        band, verdict = "caution", (
            f"{value:.0f} — above 80, so recent buying has been unusually concentrated. That is "
            f"a description of intensity, not a warning that it must stop.")
    elif value <= 20:
        band, verdict = "caution", (
            f"{value:.0f} — below 20, so recent selling has been unusually concentrated.")
    else:
        band, verdict = "context", (
            f"{value:.0f} — between 20 and 80, the range it sits in most of the time. Money "
            f"flow is not leaning hard either way.")
    return make(label, what, verdict, CONTEXT_NOT_TRIGGER, band, "none",
                evidence="weak", value_text=f"{value:.0f}")


@metric("cmf")
def _cmf(value, **_):
    label = "Chaikin money flow"
    what = ("Whether recent days have tended to close near their high (buyers in control) or "
            "near their low (sellers), weighted by volume. Runs from -1 to +1.")
    if not _known(value):
        return unavailable(label, what, "needs 20 bars with volume")
    if value > 0.05:
        band, verdict = "good", f"{_num(value, 3)} — positive, so closes have been in the upper part of their daily ranges on volume."
    elif value < -0.05:
        band, verdict = "poor", f"{_num(value, 3)} — negative, so closes have been in the lower part of their daily ranges on volume."
    else:
        band, verdict = "context", f"{_num(value, 3)} — effectively neutral."
    return make(label, what, verdict, CONTEXT_NOT_TRIGGER, band, "high",
                evidence="weak", value_text=_num(value, 3))


@metric("volumeTrend")
def _volume_trend(value, **_):
    label = "Volume versus its year"
    what = "How busy trading has been lately compared with a normal day over the past year."
    if not _known(value):
        return unavailable(label, what, "needs a year of volume history")
    if value > 1.5:
        band, verdict = "context", f"{_num(value)}x normal — trading is much heavier than usual."
    elif value > 1.2:
        band, verdict = "context", f"{_num(value)}x normal — participation is picking up."
    elif value < 0.7:
        band, verdict = "caution", f"{_num(value)}x normal — interest has faded, which makes every other reading here noisier."
    else:
        band, verdict = "context", f"{_num(value)}x normal — ordinary participation."
    return make(label, what, verdict,
                "Volume confirms moves rather than causing them. Heavy volume on a breakout is "
                "worth more than the breakout alone; heavy volume by itself means nothing.",
                band, "none", evidence="moderate", value_text=f"{_num(value)}x")


@metric("coppock")
def _coppock(value, previous=None, **_):
    label = "Coppock curve"
    what = ("A slow, monthly indicator built in the 1960s specifically to spot the end of long "
            "bear markets. It turning up from below zero is its one classic signal.")
    if not _known(value):
        return unavailable(label, what, "needs about two years of month-end closes")
    turning_up = _known(previous) and value > previous
    if value < 0 and turning_up:
        band, verdict = "good", (f"{_num(value, 1)} — below zero and turning UP. That is the "
                                 f"single setup this indicator was designed to find.")
    elif value < 0:
        band, verdict = "poor", f"{_num(value, 1)} — below zero and still falling."
    else:
        band, verdict = "context", (f"{_num(value, 1)} — above zero, where the indicator has no "
                                    f"defined signal. It only speaks from below.")
    return make(label, what, verdict,
                "It fires a handful of times per lifetime. Between signals it is decoration.",
                band, "none", evidence="weak", value_text=_num(value, 1))


# ============================================================================ #
# Accounting quality — Piotroski, Altman, Beneish
# ============================================================================ #
@metric("piotroski")
def _piotroski(value, maxScore=9, **_):
    label = "Piotroski F-Score"
    what = ("A nine-point health checklist run on the company's own filings. It asks nine "
            "yes/no questions — is it profitable, is cash coming in, is debt falling, are "
            "margins improving — and counts the yeses.")
    if not _known(value):
        return unavailable(label, what, "the filings needed are not available")
    total = int(maxScore) if _known(maxScore) and maxScore else 9
    score = int(value)
    ratio = score / total if total else 0.0
    band = _ladder(ratio, ((0.25, "bad"), (0.45, "poor"), (0.70, "fair"),
                           (0.89, "good"), (None, "excellent")))
    reading = f"{score} out of {total} checks passed. "
    reading += {
        "bad": "That is a weak score — the business is going backwards on most of the axes "
               "this checklist measures.",
        "poor": "That is on the weak side; more is deteriorating than improving.",
        "fair": "That is middling — no clear direction, improving in some places and not others.",
        "good": "That is a solid score: most fundamental trends are moving the right way.",
        "excellent": "That is a strong score — almost everything this checklist looks at is "
                     "improving.",
    }[band]
    if total < 9:
        reading += (f" Note the denominator: only {total} of the nine checks could be computed "
                    f"from the available filings, and an uncomputable check never counts as a pass.")
    return make(label, what, reading,
                "Piotroski's original finding was that a high score picked out the winners "
                "among CHEAP stocks specifically. On its own it is a health reading, not a "
                "buy case — pair it with the Value lens.",
                band, "high", evidence="moderate", value_text=f"{score}/{total}")


@metric("altman")
def _altman(value, **_):
    label = "Altman Z''-score"
    what = ("A bankruptcy-distance score built from the balance sheet. It was fitted on "
            "companies that later went bust versus ones that did not, and it asks how much "
            "this one resembles the survivors.")
    if not _known(value):
        return unavailable(label, what, "the balance-sheet items needed are not available")
    if value > 5.85:
        band, verdict = "good", (
            f"{_num(value)} — comfortably above 5.85, which is the line for 'safe'. The balance "
            f"sheet does not look like a company heading for trouble.")
    elif value >= 4.35:
        band, verdict = "caution", (
            f"{_num(value)} — inside the grey zone between 4.35 and 5.85. Neither clearly safe "
            f"nor clearly distressed; the model declines to call it.")
    else:
        band, verdict = "bad", (
            f"{_num(value)} — below 4.35, inside the distress zone. That does not mean "
            f"bankruptcy is coming, it means the balance sheet shares features with companies "
            f"that got there.")
    verdict += (" This is the emerging-market variant of the score, so an Indonesian listing "
                "and a US one are on the same scale.")
    return make(label, what, verdict,
                "A distress reading should override an attractive valuation, not sit beside "
                "it. A discounted cash flow on a company sliding toward insolvency is "
                "arithmetic, not a valuation.",
                band, "high", evidence="moderate", value_text=_num(value))


@metric("beneish")
def _beneish(value, indicesAvailable=None, indicesTotal=8, **_):
    label = "Beneish M-Score"
    what = ("A screen for earnings that may have been massaged. It compares this year's "
            "receivables, margins, asset quality and accruals against last year's, and asks "
            "whether the pattern resembles companies later found to have manipulated their "
            "numbers.")
    if not _known(value):
        return unavailable(label, what,
                           "too few of the eight component indices could be computed")
    if value > -1.78:
        band, verdict = "bad", (
            f"{_num(value)} — above the -1.78 threshold, so the accounting pattern FLAGS. "
            f"Read that carefully: the screen catches roughly three-quarters of real "
            f"manipulators, but manipulation is rare, so most flags are false alarms. It is a "
            f"reason to read the filings, not a finding.")
    elif value > -2.22:
        band, verdict = "caution", (
            f"{_num(value)} — close to the -1.78 threshold without crossing it. Worth a look "
            f"at the accruals if you are going to own this.")
    else:
        band, verdict = "good", (
            f"{_num(value)} — well below the threshold. No manipulation signature. Note this is "
            f"the absence of one specific pattern, not a clean bill of health.")
    if _known(indicesAvailable) and indicesAvailable < (indicesTotal or 8):
        verdict += (f" Built from {int(indicesAvailable)} of {int(indicesTotal or 8)} indices, "
                    f"so it is less reliable than a full score.")
    return make(label, what, verdict,
                "Higher is worse here, which is the opposite of the other two quality scores. "
                "A flag means go and read the cash-flow statement against the income statement.",
                band, "low", evidence="moderate", value_text=_num(value))


# The four ratios Altman's Z'' is built from, each explained in ordinary words.
_ALTMAN_PARTS = {
    "workingCapitalToAssets": (
        "Short-term cushion",
        "Money due in soon minus bills due soon, as a share of everything the company owns. "
        "Negative means short-term bills exceed short-term resources.",
        "low"),
    "retainedToAssets": (
        "Lifetime profits kept",
        "How much of what the company owns was paid for by profits it earned and kept, rather "
        "than by borrowing or issuing shares. Young or loss-making firms score low.",
        "low"),
    "ebitToAssets": (
        "Operating profitability",
        "Operating profit as a share of everything the company owns — how hard the assets work "
        "before interest and tax.",
        "low"),
    "equityToLiabilities": (
        "Cushion against debts",
        "Shareholders' stake divided by everything owed. Under 1 means the company owes more "
        "than the owners have in it.",
        "low"),
}


@metric("altmanComponent")
def _altman_component(value, part=None, **_):
    name, what, _direction = _ALTMAN_PARTS.get(
        part, ("Component", "One input to the distress score.", "low"))
    if not _known(value):
        return unavailable(name, what, "not available in these filings")
    band = "poor" if value < 0 else "context"
    return make(name, what,
                f"{_num(value)}. " + ("Negative, which drags the combined distress score down "
                                      "and is the kind of reading that puts a company in the "
                                      "grey zone on its own."
                                      if value < 0 else
                                      "Positive, which supports the combined distress score."),
                "One input among four. The combined score above is what carries the meaning.",
                band, "high", evidence="moderate", value_text=_num(value))


# Beneish's eight indices are printed as bare acronyms today. Each is a
# this-year-over-last-year ratio, so 1.0 means "unchanged" for all of them — and
# that shared anchor is the thing that makes them readable at all.
_BENEISH_PARTS = {
    "DSRI": ("Receivables vs sales",
             "Are customers taking longer to pay, relative to sales growth? A jump can mean "
             "revenue was booked before the cash was real.", True),
    "GMI": ("Margin deterioration",
            "Are gross margins worse than last year? Deteriorating margins create pressure to "
            "make the numbers look better.", True),
    "AQI": ("Asset quality",
            "Is a bigger share of the balance sheet made of soft, hard-to-value assets rather "
            "than physical ones?", True),
    "SGI": ("Sales growth",
            "How fast revenue grew. Fast growth is not manipulation, but it is the environment "
            "where manipulation most often happens.", True),
    "DEPI": ("Depreciation slowdown",
             "Has the company slowed the rate it writes assets down? Doing so flatters profit.",
             True),
    "SGAI": ("Overheads vs sales",
             "Are admin and selling costs growing faster than sales?", True),
    "LVGI": ("Leverage change",
             "Is the company carrying more debt relative to its assets than last year?", True),
    "TATA": ("Accruals",
             "How much of reported profit is NOT backed by cash actually collected. The single "
             "most informative of the eight.", True),
}


@metric("beneishIndex")
def _beneish_index(value, part=None, **_):
    name, what, higher_worse = _BENEISH_PARTS.get(
        part, ("Index", "One of the eight Beneish inputs.", True))
    label = f"{part} · {name}" if part else name
    if not _known(value):
        return unavailable(label, what, "not computable from these filings")
    if part == "TATA":
        band = "caution" if value > 0.03 else "context"
        reading = (f"{_num(value)} — accruals are {_pct(value, 1)} of total assets. "
                   + ("A high positive figure means reported profit is running well ahead of "
                      "cash collected." if value > 0.03 else
                      "Profit and cash are broadly in step."))
    else:
        band = "caution" if value > 1.20 else "context"
        reading = (f"{_num(value)} — 1.00 would mean unchanged from last year, so this is "
                   + (f"{_pct(value - 1, 0)} higher. " if value >= 1 else
                      f"{_pct(1 - value, 0)} lower. ")
                   + ("A rise of this size is the direction Beneish treats as suspicious."
                      if value > 1.20 else "Not an unusual year-on-year change."))
    return make(label, what, reading,
                "One input among eight. No single index means anything alone — the combined "
                "M-Score is the reading.",
                band, "low" if higher_worse else "high", evidence="moderate",
                value_text=_num(value))


# ============================================================================ #
# Flow lens — liquidity, trading costs, anomaly statistics
# ============================================================================ #
@metric("spread")
def _spread(value, source=None, floor=None, at_floor=False, **_):
    label = "Bid-ask spread"
    what = ("The invisible toll on every trade: the gap between what a buyer pays and what a "
            "seller receives at the same instant. Buy and sell immediately and you lose this "
            "much without the price moving at all.")
    if not _known(value):
        return unavailable(label, what, "not enough high-low data to estimate it")
    # AT THE FLOOR, THE FIGURE IS NOT A MEASUREMENT. Both estimators have a
    # noise floor proportional to the stock's own volatility — about 0.15x the
    # daily standard deviation for the headline one — because volatility leaks
    # into the estimate. On a liquid name that floor is an order of magnitude
    # above the real spread, so quoting it as "0.29% per round trip" states a
    # cost the stock does not charge, and does it most confidently on the names
    # where it is most wrong. Below the floor the honest reading is an upper
    # bound, and the band must not reward or punish a number that is noise.
    if at_floor and _known(floor):
        return make(label, what,
                    f"At most about {_pct(max(value, floor), 2)} per round trip — and this is a "
                    f"ceiling, not a measurement. Daily high-low data cannot separate a spread "
                    f"from ordinary volatility below roughly {_pct(floor, 2)} on a stock that "
                    f"moves like this one, and the estimate sits inside that range. A genuinely "
                    f"liquid listing lands here, and so does anything whose real cost is too "
                    f"small for this method to see.",
                    "Read it as 'trading costs are small enough that this data cannot see "
                    "them'. If you need the real number, it comes from a quote feed, not from "
                    "daily bars.",
                    "good", "low", evidence="moderate",
                    value_text=f"≤{_pct(max(value, floor), 2)}")

    band = _ladder(value, ((0.001, "excellent"), (0.003, "good"), (0.01, "fair"),
                           (0.02, "poor"), (None, "bad")))
    reading = f"About {_pct(value, 2)} per round trip. "
    reading += {
        "excellent": "Very tight — a heavily traded name where costs barely matter.",
        "good": "Tight. Trading costs are not a concern at ordinary size.",
        "fair": "Noticeable. Frequent trading here gives back real money.",
        "poor": "Wide. Any signal worth less than a couple of percent is not worth acting on.",
        "bad": "Very wide. This is a thin listing and most short-term signals here are illusions.",
    }[band]
    if source:
        reading += f" (Estimated from daily high-low data using {source}; there is no quote feed here.)"
    return make(label, what, reading,
                "It sets the minimum size a move has to clear before it is worth trading. "
                "Compare it against the move-versus-spread reading beside it.",
                band, "low", evidence="strong", value_text=_pct(value, 2))


@metric("moveVsSpread")
def _move_vs_spread(value, resolved=True, **_):
    label = "Move versus trading cost"
    what = ("How big the latest day's move was compared with what it costs to trade in and out. "
            "Below about 2, the move is smaller than the toll.")
    if not _known(value):
        return unavailable(label, what, "needs a spread estimate and a price move")
    if not resolved:
        # The denominator is the estimator's noise floor rather than a spread,
        # so this ratio is a LOWER bound on the real one. Reporting it as though
        # it were measured turns "we cannot see the cost" into "the cost is big".
        return make(label, what,
                    f"At least {_num(value, 1)}x the estimated cost, and in truth more — the "
                    f"spread this divides by could not be resolved from daily data, so it is "
                    f"an over-estimate of the real cost and this ratio is an under-estimate of "
                    f"the real margin. On a liquid name the move clears the cost comfortably.",
                    "No warning to draw from this. When the cost cannot be measured, the "
                    "honest conclusion is that it is small, not that it is dangerous.",
                    "good", "high", evidence="moderate", value_text=f"≥{_num(value, 1)}x")
    band = _ladder(value, ((1.0, "bad"), (2.0, "poor"), (5.0, "fair"), (None, "good")))
    reading = f"{_num(value, 1)}x the estimated round-trip cost. "
    reading += {
        "bad": "The move is smaller than the cost of trading it. Whatever the model found, it "
               "is not something you could have captured.",
        "poor": "Barely above the cost of trading. Treat any signal on this day as noise.",
        "fair": "Comfortably larger than the trading cost.",
        "good": "Far larger than the trading cost — a real move, not spread noise.",
    }[band]
    return make(label, what, reading,
                "This is the reality check on the anomaly detector. A dramatic-looking volume "
                "spike on a thin stock often just means the order book is shallow.",
                band, "high", evidence="strong", value_text=f"{_num(value, 1)}x")


@metric("yangZhangVol")
def _yang_zhang(value, **_):
    label = "Volatility (gap-aware)"
    what = ("How much this moves in a typical year, measured using each day's open, high, low "
            "AND close rather than closes alone — so overnight gaps are not invisible to it.")
    if not _known(value):
        return unavailable(label, what, "needs about a month of full daily bars")
    band = _ladder(value, ((0.15, "excellent"), (0.25, "good"), (0.35, "fair"),
                           (0.50, "poor"), (None, "bad")))
    return make(label, what,
                f"About {_pct(value, 0)} a year. Using the full daily bar rather than just "
                f"closes gives the same answer with far less estimation noise, which is why "
                f"this figure is preferred to the simple one.",
                "Position sizing, same as any volatility reading. " + CONTEXT_NOT_TRIGGER,
                band, "low", evidence="strong", value_text=_pct(value, 0))


def _money(amount: float, currency: Optional[str]) -> str:
    """A large sum written the way a person says it."""
    symbol = {"USD": "$", "IDR": "Rp", "EUR": "\u20ac", "GBP": "\u00a3"}.get(currency or "", "")
    for cutoff, suffix in ((1e12, "tn"), (1e9, "bn"), (1e6, "m"), (1e3, "k")):
        if abs(amount) >= cutoff:
            return f"{symbol}{amount / cutoff:,.1f}{suffix}"
    return f"{symbol}{amount:,.0f}"


@metric("amihud")
def _amihud(value, currency=None, **_):
    label = "Depth (what it takes to move it)"
    what = ("How much money has to trade before the price actually moves. It is the cost of "
            "SIZE, as opposed to the spread, which is the cost of being in a hurry.")
    if not _known(value) or value <= 0:
        return unavailable(label, what, "needs volume data")

    # EXPRESSED AS MONEY, NOT AS A RATIO. The underlying figure is a fractional
    # price move per million traded, which on a mega-cap is around 8e-7 — and
    # formatting that as a percentage produced the literal string "0.00%", a
    # real quantity rendered into nothing. Inverting it states the same fact in
    # a unit a person can picture: what it costs to move the price one percent.
    to_move_one_percent = 0.01 / value * 1e6
    reading = (f"It takes roughly {_money(to_move_one_percent, currency)} of trading to move "
               f"this price by 1%, averaged over the last month. ")
    if value > 0.05:
        band = "poor"
        reading += ("That is very little depth — a meaningful order would move the price "
                    "against itself.")
    elif value > 0.005:
        band = "fair"
        reading += "Moderate depth. Large orders would be felt."
    else:
        band = "good"
        reading += "Deep — this absorbs size without much complaint."
    reading += (" Currencies are not comparable here, so it is most useful ranked against "
                "other names in the same market.")
    return make(label, what, reading,
                "It tells you what size this can absorb, not whether to own it. "
                + CONTEXT_NOT_TRIGGER,
                band, "low", evidence="moderate",
                value_text=_money(to_move_one_percent, currency))


@metric("anomalyRate")
def _anomaly_rate(value, totalDays=None, **_):
    label = "How often this flags"
    what = ("The share of all days in the history that the detector marked as unusual. It is "
            "the baseline any fresh flag has to beat.")
    if not _known(value):
        return unavailable(label, what, "needs a fitted model")
    reading = (f"{_pct(value)} of days"
               + (f" out of {int(totalDays)}" if _known(totalDays) else "")
               + " were flagged. ")
    if value > 0.08:
        band = "caution"
        reading += ("This name flags often, so a handful of recent flags is not news — it is "
                    "the normal rate.")
    else:
        band = "context"
        reading += ("This name is normally quiet, so recent flags carry more weight than they "
                    "would on a chronically noisy stock.")
    return make(label, what, reading,
                "This is the number each recent count is tested against, which is why a quiet "
                "stock needs less activity to qualify as significant than a noisy one.",
                band, "none", evidence="moderate", value_text=_pct(value))


@metric("qValue")
def _q_value(value, **_):
    label = "q-value"
    what = ("The chance this particular hit is a false alarm, AFTER accounting for the fact "
            "that scanning many names produces hits by luck alone.")
    if not _known(value):
        return unavailable(label, what, "not enough history to test against")
    if value <= 0.05:
        band, verdict = "good", (f"{_num(value, 3)} — survives the multiple-testing correction. "
                                 f"Roughly a 1-in-20 chance or better that this is noise.")
    elif value <= 0.2:
        band, verdict = "caution", (f"{_num(value, 3)} — suggestive but not significant once the "
                                    f"size of the scan is accounted for.")
    else:
        band, verdict = "poor", (f"{_num(value, 3)} — not distinguishable from what the scan "
                                 f"would throw up by chance.")
    return make(label, what, verdict,
                "Scan enough names and something always looks interesting. This column is what "
                "stops that from being mistaken for a discovery.",
                band, "low", evidence="strong", value_text=_num(value, 3))


@metric("cusumEpisode")
def _cusum(value, direction=None, days=None, avgRvol=None, ongoing=False, **_):
    label = "Sustained flow regime (CUSUM)"
    what = ("A detector for slow, patient buying or selling. A fund building a position spreads "
            "it over weeks precisely so no single day looks unusual — this adds up the small "
            "daily deviations until the total is too big to be chance.")
    if not _known(days):
        return unavailable(label, what, "no sustained regime detected in this window")
    # "A Accumulation" — the article has to agree with the word after it.
    word = (direction or "flow").lower()
    article = "An" if word[:1] in "aeiou" else "A"
    reading = (f"{'An ongoing' if ongoing else article} {word} run lasting "
               f"{int(days)} days"
               + (f", at an average of {_num(avgRvol)}x normal volume" if _known(avgRvol) else "")
               + ". " + ("" if ongoing else "It has since ended. "))
    if _known(avgRvol) and avgRvol < 1.3:
        reading += ("Note how ordinary that volume is — this is exactly the pattern a "
                    "day-by-day detector cannot see, and the reason this test exists.")
    band = "good" if direction == "Accumulation" else "poor" if direction == "Distribution" else "context"
    return make(label, what, reading,
                "It says the pattern is statistically unusual, not who caused it. Index "
                "rebalances, buybacks and fund flows all leave this footprint.",
                band, "high", evidence="moderate",
                value_text=f"{int(days)} d" if _known(days) else None)


@metric("flowBias")
def _flow_bias(value, days=None, count=None, **_):
    label = f"Flow bias{f' · last {days} days' if days else ''}"
    what = ("Whether the unusual days recently found looked more like buying or more like "
            "selling, decided by a four-way vote of volume-based measures.")
    if not value:
        return unavailable(label, what, "no unusual days in this window")
    if value == "Accumulation":
        band, verdict = "good", "Recent unusual activity has leaned toward buying."
    elif value == "Distribution":
        band, verdict = "poor", "Recent unusual activity has leaned toward selling."
    else:
        band, verdict = "context", "Recent unusual activity has been mixed, with no clear side."
    if _known(count):
        verdict += f" Based on {int(count)} flagged day{'s' if count != 1 else ''}."
    return make(label, what, verdict,
                "It cannot tell you WHO traded. Index rebalances, dividend dates, options "
                "expiry and earnings all produce the same footprint as an institution.",
                band, "high", evidence="weak", value_text=str(value))


# ============================================================================ #
# Valuation — the lens most likely to be mistaken for a price target
# ============================================================================ #
@metric("upside")
def _upside(value, engine=None, price_label=None, fair_label=None, **_):
    label = "Gap to fair value"
    what = ("How far today's share price sits from what the model thinks the business is "
            "worth. Positive means the model says it is cheap.")
    if not _known(value):
        return unavailable(label, what, "the model could not produce a value")
    band = _ladder(value, ((-0.30, "bad"), (-0.10, "poor"), (0.10, "fair"),
                           (0.30, "good"), (None, "excellent")))
    reading = (f"The model's middle estimate is {fair_label or 'its fair value'} against a "
               f"market price of {price_label or 'today\'s price'} — "
               + (f"a {_pct(abs(value), 0)} discount." if value >= 0
                  else f"a {_pct(abs(value), 0)} premium.") + " ")
    if abs(value) > 0.5:
        reading += ("A gap that large is more often a sign the assumptions are wrong than a "
                    "genuine mispricing. Check the growth rate and the discount rate before "
                    "believing it.")
    else:
        reading += ("Gaps of this size are ordinary and well inside the error bars of any "
                    "discounted-cash-flow exercise.")
    return make(label, what, reading,
                "Treat this as a range, not a target. Move the growth assumption two points "
                "and watch the answer move further than the gap you are looking at — which is "
                "why every input on this panel is editable.",
                # Whole percents deliberately: a fair-value gap quoted to one
                # decimal claims a precision the model does not have.
                band, "high", evidence="weak", value_text=_signed_pct(value, 0))


@metric("probUndervalued")
def _prob_undervalued(value, iterations=None, **_):
    label = "Share of runs that came out cheap"
    what = ("The model was run thousands of times with slightly different assumptions each "
            "time. This is the fraction of those runs where the business came out worth more "
            "than its market price.")
    if not _known(value):
        return unavailable(label, what, "the simulation did not run")
    band = _ladder(value, ((0.20, "poor"), (0.45, "fair"), (0.75, "good"), (None, "excellent")))
    reading = (f"{_pct(value, 0)} of "
               + (f"{int(iterations):,} " if _known(iterations) else "")
               + "simulated runs valued it above the market price. ")
    if value > 0.9:
        reading += "Almost every version of the assumptions says cheap."
    elif value < 0.1:
        reading += "Almost every version of the assumptions says expensive."
    else:
        reading += "The assumptions genuinely disagree with each other about this one."
    reading += (" This is NOT a probability that the price will rise. It is a measure of how "
                "sensitive the model's answer is to its own inputs.")
    return make(label, what, reading,
                "Read it as confidence in the model's own answer, not confidence about the "
                "future. A tight result on wrong assumptions is still wrong.",
                band, "high", evidence="weak", value_text=_pct(value, 0))


@metric("impliedGrowth")
def _implied_growth(value, assumedGrowth=None, engine=None, **_):
    label = "What the price is assuming"
    what = ("The growth rate the market must be expecting for today's share price "
            "to be correct, working the model backwards. Instead of asking what the "
            "business is worth, it asks what would have to be true for the current "
            "price to be right.")
    if not _known(value):
        return unavailable(label, what,
                           "today's price cannot be reproduced by this model at any "
                           "growth rate between -60% and +60% a year")

    band = _ladder(value, ((0.03, "good"), (0.10, "fair"), (0.20, "caution"), (None, "bad")))
    gap = ""
    if _known(assumedGrowth):
        difference = value - assumedGrowth
        if abs(difference) < 0.005:
            gap = (f" That is almost exactly the {_pct(assumedGrowth)} this model was run "
                   f"with, so the model and the market agree.")
        elif difference > 0:
            gap = (f" The model was run at {_pct(assumedGrowth)}, so the market is pricing "
                   f"in {_pct(difference)} a year MORE growth than you assumed.")
        else:
            gap = (f" The model was run at {_pct(assumedGrowth)}, so the market is pricing "
                   f"in {_pct(abs(difference))} a year LESS growth than you assumed.")

    reading = {
        "good": (f"The price implies about {_pct(value)} a year for the next five years — "
                 f"a modest bar for the business to clear."),
        "fair": (f"The price implies about {_pct(value)} a year for the next five years, "
                 f"which is a real but ordinary expectation."),
        "caution": (f"The price implies about {_pct(value)} a year for five years. That is a "
                    f"demanding assumption; it needs the business to keep compounding hard."),
        "bad": (f"The price implies about {_pct(value)} a year for five years, which very few "
                f"companies sustain. The price is carrying an expectation the cash flows would "
                f"have to work hard to meet."),
    }[band]

    return make(
        label=label, what=what, reading=reading + gap,
        action=("The number to argue with. Ask whether you believe THIS company can "
                "grow at that rate for five years — you know things about the business the "
                "model does not. If you think it can do better, the price is cheap on this "
                "model; if worse, expensive. That judgement is yours, and it is a far more "
                "answerable question than whether a fair-value estimate is right. "
                "It is NOT independent of the other assumptions, though: it is the growth "
                "implied GIVEN this discount rate, this terminal growth and this starting "
                "cash flow. Lower the discount rate and the implied growth falls with it. "
                "Change one on the panel and watch this move before you treat it as a fact "
                "about the company."),
        band=band, good_direction="low", evidence="moderate",
        value_text=_pct(value),
    )


@metric("terminalShare")
def _terminal_share(value, **_):
    label = "Share of value that is guesswork"
    what = ("A discounted-cash-flow model forecasts five years explicitly and then assumes the "
            "business carries on forever at a fixed growth rate. This is how much of the answer "
            "comes from that forever assumption rather than the forecast.")
    if not _known(value):
        return unavailable(label, what, "no terminal value was computed")
    band = _ladder(value, ((0.50, "good"), (0.70, "fair"), (0.85, "poor"), (None, "bad")))
    reading = f"{_pct(value, 0)} of the valuation comes from the perpetuity assumption. "
    reading += {
        "good": "Under half — unusually well grounded for a cash-flow model.",
        "fair": "Typical for a DCF, and still means most of the answer rests on a guess.",
        "poor": "High. The five-year forecast is doing very little of the work here.",
        "bad": "Almost all of the answer is the forever assumption. The projection table below "
               "is close to decorative.",
    }[band]
    return make(label, what, reading,
                "The higher this is, the more the answer is a statement about the terminal "
                "growth rate you chose. Change that input and see how far the value moves.",
                band, "low", evidence="strong", value_text=_pct(value, 0))


@metric("discountRate")
def _discount_rate(value, rate_name=None, risk_free=None, beta=None, **_):
    label = rate_name or "Discount rate"
    what = ("The yearly return an investor should demand for taking this much risk. Future "
            "cash is worth less than cash today, and this is the rate used to shrink it.")
    if not _known(value):
        return unavailable(label, what, "could not be estimated")
    reading = f"{_pct(value, 1)} a year. "
    if _known(risk_free) and _known(beta):
        reading += (f"Built from a {_pct(risk_free, 1)} risk-free rate plus this company's "
                    f"share of market risk (beta {_num(beta)}). ")
    if value > 0.15:
        band = "caution"
        reading += ("That is a high bar. A high discount rate compresses the valuation hard, so "
                    "a low answer here may be the rate speaking rather than the business.")
    elif value < 0.06:
        band = "caution"
        reading += ("That is a low bar for equity risk, and a low rate inflates the valuation. "
                    "Check it against what you would actually demand to own this.")
    else:
        band = "context"
        reading += "That is an ordinary range for a listed equity."
    return make(label, what, reading,
                "It is the single input the answer is most sensitive to, after growth. It is "
                "editable above for exactly that reason.",
                band, "none", evidence="strong", value_text=_pct(value, 1))


@metric("valuationSpread")
def _valuation_spread(value, p25_label=None, p75_label=None, **_):
    label = "How wide the answer is"
    what = ("The gap between the pessimistic and optimistic halves of the simulation, as a "
            "share of the middle estimate. Wide means the model is not confident.")
    if not _known(value):
        return unavailable(label, what, "the simulation did not run")
    band = _ladder(value, ((0.25, "good"), (0.60, "fair"), (1.20, "poor"), (None, "bad")))
    reading = ("The middle half of the runs spans "
               + (f"{p25_label} to {p75_label}, " if p25_label and p75_label else "")
               + f"which is {_pct(value, 0)} of the central estimate. ")
    reading += {
        "good": "That is a narrow range for a model like this.",
        "fair": "A normal spread. The single median figure is less informative than the range.",
        "poor": "A wide range. Any single 'fair value' quoted from this is over-precise.",
        "bad": "Extremely wide. The model is telling you it does not know.",
    }[band]
    return make(label, what, reading,
                "Quote the range, never the median alone. A number with error bars this wide "
                "does not support a precise decision.",
                band, "low", evidence="strong", value_text=_pct(value, 0))



# ============================================================================ #
# Shorter horizons — where the evidence is thinnest and says so
# ============================================================================ #
@metric("riskReward")
def _risk_reward(value, target_label=None, **_):
    label = "Reward for the risk"
    what = ("How much you stand to make if the target is reached, for every unit you lose if "
            "the stop is hit. 2.0 means twice as much up as down.")
    if not _known(value):
        return unavailable(label, what, "no entry and stop could be placed")
    band = _ladder(value, ((1.0, "bad"), (1.5, "poor"), (2.5, "good"), (None, "excellent")))
    reading = f"{_num(value, 1)} to 1"
    if target_label:
        reading += f", measuring to {target_label.lower()}"
    reading += ". "
    reading += {
        "bad": "You are risking more than you stand to make. That needs a very high hit rate "
               "to be worth doing, and nothing here estimates the hit rate.",
        "poor": "Thin. After trading costs there is not much left of the edge.",
        "good": "A conventional ratio for this kind of setup.",
        "excellent": "Generous — check the target is a real level and not just the number that "
                     "made the arithmetic look good.",
    }[band]
    return make(label, what, reading,
                "A ratio is only half the sum. It tells you the payoff shape, not how often "
                "the setup works, and this app does not claim to know that.",
                band, "high", evidence="moderate", value_text=f"{_num(value, 1)}:1")


@metric("stopDistance")
def _stop_distance(value, atr_multiple=None, basis=None, **_):
    label = "Distance to the stop"
    what = ("How far the price would have to fall before the reason for the trade is wrong and "
            "you would get out.")
    if not _known(value):
        return unavailable(label, what, "no stop could be placed")
    reading = f"{_pct(value)} below the entry"
    if _known(atr_multiple):
        reading += f", which is {_num(atr_multiple, 1)} times an average day's range"
    reading += ". "
    if basis == "structure":
        reading += ("It sits just under a level the market has actually defended, so if it is "
                    "hit, something real has broken rather than the price having wobbled.")
        band = "good"
    else:
        reading += ("There was no defended level below to anchor it to, so it is placed purely "
                    "by how much this stock normally moves. That is weaker than a structural "
                    "stop.")
        band = "caution"
    if _known(atr_multiple) and atr_multiple < 1.2:
        band = "caution"
        reading += (" It is close enough to the entry that ordinary daily noise could trigger "
                    "it without anything meaningful happening.")
    return make(label, what, reading,
                "This is the input to position sizing. Halve the distance and you can hold "
                "twice the position for the same money at risk — and get stopped out twice as "
                "often.",
                band, "none", evidence="strong", value_text=_pct(value))


@metric("positionShare")
def _position_share(value, risk_budget=None, uncapped=None, **_):
    label = "Position size"
    what = ("How much of your account this position would be, if a stop-out is not allowed to "
            "cost you more than your chosen risk budget.")
    if not _known(value):
        return unavailable(label, what, "no stop distance to size against")
    budget = risk_budget if _known(risk_budget) else 0.01
    reading = (f"{_pct(value, 0)} of the account. That is the size at which being stopped out "
               f"costs {_pct(budget, 0)} of the whole account — no more.")
    band = "context"
    if _known(uncapped) and uncapped > 1.0:
        band = "caution"
        reading += (f" The unconstrained arithmetic says {_pct(uncapped, 0)}, which is more "
                    f"money than there is. The stop is tight enough that hitting the risk "
                    f"budget would need borrowing; treat the shown figure as a cap, not a "
                    f"recommendation.")
    elif value > 0.25:
        band = "caution"
        reading += (" That is a large single holding. The arithmetic is correct and "
                    "concentration is a separate risk it does not measure.")
    return make(label, what, reading,
                "Change the risk budget and this moves proportionally. It is the one number "
                "here that is arithmetic rather than opinion.",
                band, "none", evidence="strong", value_text=_pct(value, 0))


@metric("distanceToLevel")
def _distance_to_level(value, side=None, touches=None, price_text=None, **_):
    label = ("Distance to the nearest ceiling" if side == "resistance"
             else "Distance to the nearest floor")
    what = ("How far the price is from the closest level where it has previously turned around. "
            + ("A ceiling is where sellers showed up before."
               if side == "resistance" else "A floor is where buyers showed up before."))
    if not _known(value):
        return unavailable(label, what, "no confirmed turning point on that side")
    reading = (f"{_pct(abs(value))} "
               + ("above" if side == "resistance" else "below")
               + " today's price"
               + (f", at {price_text}" if price_text else "") + ". ")
    if _known(touches):
        reading += (f"The price turned there {int(touches)} time"
                    f"{'s' if touches != 1 else ''} before. "
                    + ("A level tested once is barely a level."
                       if touches < 2 else
                       "A level tested repeatedly is one more participants are watching."))
    band = "context"
    if abs(value) < 0.02:
        band = "caution"
        reading += " The price is right on top of it, which is where the decision gets made."
    return make(label, what, reading,
                "Levels are where past participants transacted, not forecasts. They are most "
                "useful for placing a stop beyond, which is what the plan above does.",
                band, "none", evidence="weak", value_text=_signed_pct(value))


@metric("vwapDistance")
def _vwap_distance(value, anchor=None, **_):
    label = (f"Average price paid since the {anchor.lower()}" if anchor
             else "Versus the average price paid")
    what = ("The volume-weighted average price everyone who bought since a chosen date has "
            "paid. Above it, the average buyer since then is in profit; below it, under water.")
    if not _known(value):
        return unavailable(label, what, "not enough volume history since that anchor")
    above = value >= 0
    reading = (f"{_signed_pct(value)} versus that average. "
               + ("The typical buyer since then is sitting on a gain, so there is less trapped "
                  "supply overhead."
                  if above else
                  "The typical buyer since then is under water. People who bought there often "
                  "sell into any rally back to break even, which is what makes this level act "
                  "as resistance."))
    return make(label, what, reading,
                "It is a description of who is where, not a signal. Its usefulness is in "
                "explaining WHY a level might hold.",
                "good" if above else "caution", "high", evidence="weak",
                value_text=_signed_pct(value))


@metric("squeezePercentile")
def _squeeze(value, fired=None, **_):
    # THE LABEL AND THE FIGURE HAVE TO AGREE. This first shipped as "How quiet
    # it has gone: 94%", where 94 is a percentile meaning *very lively* — a
    # reader scanning the tile takes exactly the wrong reading, and nothing on
    # the face of it corrects them. The value now leads with the word.
    label = "How much it is moving"
    what = ("How much the price has been moving lately compared with the rest of the past year. "
            "Low means unusually calm.")
    if not _known(value):
        return unavailable(label, what, "needs about 40 bars of history")
    if value <= 0.15:
        band = "caution"
        summary = f"Squeezed ({_pct(value, 0)})"
        reading = (f"At the {_pct(value, 0)} mark of its own past year — quieter than "
                   f"{_pct(1 - value, 0)} of it, which is a 'squeeze'. Calm "
                   f"periods really are followed by loud ones more often than chance, because "
                   f"volatility clusters. What that does NOT tell you is which direction the "
                   f"loud move goes, and most write-ups quietly add that part.")
    elif value >= 0.85:
        band = "caution"
        summary = f"Volatile ({_pct(value, 0)})"
        reading = (f"At the {_pct(value, 0)} mark of its own past year — wider than most of "
                   f"it, so this is a volatile stretch. "
                   f"Stops need more room than usual and position sizes less.")
    else:
        band = "context"
        summary = f"Ordinary ({_pct(value, 0)})"
        reading = f"Ordinary — around the {_pct(value, 0)} mark of its own past year."
    if fired:
        reading += (f" The price has now closed outside the bands to the {fired}side, so the "
                    f"quiet period has resolved in that direction.")
    return make(label, what, reading,
                "A volatility forecast, never a direction forecast. Wait for the break rather "
                "than guessing it.",
                band, "none", evidence="weak", value_text=summary)


@metric("volumeRatio")
def _volume_ratio(value, **_):
    label = "Volume on the day"
    what = "How much trading happened today compared with a normal day over the past month."
    if not _known(value):
        return unavailable(label, what, "needs a month of volume history")
    if value >= 2.0:
        band, verdict = "context", (f"{_num(value, 1)}x a normal day — a lot of people traded "
                                    f"this. Heavy volume behind a move means more participants "
                                    f"agreed with it.")
    elif value >= 1.5:
        band, verdict = "context", (f"{_num(value, 1)}x a normal day — heavier than usual, which "
                                    f"is the confirmation a breakout rule normally asks for.")
    elif value <= 0.6:
        band, verdict = "caution", (f"{_num(value, 1)}x a normal day — thin. A move on volume "
                                    f"this light involved few participants and is easier to "
                                    f"reverse.")
    else:
        band, verdict = "context", f"{_num(value, 1)}x a normal day — ordinary participation."
    return make(label, what, verdict,
                "Volume confirms a move, it does not cause one. Heavy volume on its own, with "
                "no move to confirm, means nothing.",
                band, "none", evidence="moderate", value_text=f"{_num(value, 1)}x")


@metric("divergenceState")
def _divergence(value, kind=None, **_):
    label = "Price versus momentum"
    what = ("Whether the price is making new highs (or lows) that the momentum reading is not "
            "matching. When the two disagree, the move is said to be losing steam.")
    if not kind:
        return make(label, what,
                    "Price and momentum are moving together — no disagreement between them at "
                    "the last two turning points.",
                    CONTEXT_NOT_TRIGGER, "context", "none", evidence="weak",
                    value_text="In step")
    if kind == "bearish":
        band = "caution"
        reading = ("The price made a HIGHER high than last time, but momentum made a lower one. "
                   "The advance is being driven by less force than before.")
    else:
        band = "caution"
        reading = ("The price made a LOWER low than last time, but momentum made a higher one. "
                   "The decline is being driven by less force than before.")
    reading += (" Treat it lightly: divergence depends heavily on how a turning point is "
                "defined, and it can persist for months without resolving.")
    return make(label, what, reading,
                "Not a trigger. At most a reason to want more confirmation before acting on "
                "the move it is arguing with.",
                band, "none", evidence="weak",
                value_text="Losing steam" if kind == "bearish" else "Selling drying up")


@metric("gapState")
def _gap(value, direction=None, size_atr=None, **_):
    label = "Unfilled gap"
    what = ("A price band the stock jumped straight over between one day's close and the next "
            "day's open. Almost nobody traded inside it, so there is no established support or "
            "resistance in there.")
    if not _known(value):
        return make(label, what,
                    "No unfilled gap of any size in the recent history — the price has traded "
                    "through every level on its way here.",
                    CONTEXT_NOT_TRIGGER, "context", "none", evidence="weak", value_text="None")
    reading = (f"An unfilled gap {_pct(abs(value))} "
               + ("below" if value < 0 else "above") + " today's price"
               + (f", about {_num(size_atr, 1)} average daily ranges wide" if _known(size_atr)
                  else "") + f", left by a jump {direction or ''}. ")
    reading += ("Because there is no trading history inside it, price often moves through that "
                "band quickly in either direction. The common claim that gaps always get filled "
                "is not supported — many never do.")
    return make(label, what, reading,
                "Useful for knowing where price may move fast, which affects where a stop is "
                "safe. Not a directional signal.",
                "caution", "none", evidence="weak", value_text=_signed_pct(value))



# ============================================================================ #
# The plain-English story
# ============================================================================ #
def _years_of(observations: Optional[int]) -> Optional[float]:
    if not _known(observations):
        return None
    return float(observations) / 252.0


def _describe_span(years: Optional[float]) -> str:
    if years is None:
        return "Over the loaded history"
    if years < 1.5:
        return "Over the past year or so"
    return f"Over the past {years:.0f} years"


def long_horizon_story(ticker: str, block: dict) -> dict:
    """The long-horizon evidence retold as sentences a person would say out loud.

    WHY THIS IS SERVER-SIDE PROSE AND NOT A TEMPLATE IN THE COMPONENT
    -----------------------------------------------------------------
    Every clause here is conditional on a number existing and on which side of a
    threshold it falls. Written in JSX that becomes a thicket of nested ternaries
    that nobody can read and no test can reach. Written here it is ordinary
    Python with an offline test asserting that a planted 40% drawdown produces
    the sentence "fell 40%" — which is the only way to be sure the paragraph and
    the table beside it are describing the same history.

    Returns paragraphs rather than one blob so the panel can lay them out, and
    so a missing engine (no benchmark, too little history) drops one sentence
    instead of collapsing the whole summary.
    """
    risk = block.get("risk") or {}
    drawdown = block.get("drawdown") or {}
    rolling = block.get("rollingReturns") or []
    relative = block.get("relativeStrength") or {}
    position = block.get("position") or {}
    name = ticker.upper() if ticker else "This stock"

    paragraphs: list[str] = []

    # ---- 1. What it returned -------------------------------------------
    years = _years_of(risk.get("observations"))
    span = _describe_span(years)
    cagr_value = risk.get("cagr")
    if _known(cagr_value):
        if cagr_value >= 0:
            first = (f"{span}, {name} returned about {_pct(cagr_value, 0)} a year. "
                     f"Money left in it would have grown at roughly that pace, on average.")
        else:
            first = (f"{span}, {name} LOST about {_pct(abs(cagr_value), 0)} a year. "
                     f"A holder over that whole window is behind.")
        excess = ((relative.get("periods") or {}).get("36m") or {}).get("excess")
        benchmark = relative.get("benchmark")
        if _known(excess) and benchmark:
            index = index_name(benchmark)
            first += (f" Over the last three years it beat {index} by "
                      f"{_pct(excess, 0)}." if excess > 0 else
                      f" Over the last three years it trailed {index} by "
                      f"{_pct(abs(excess), 0)} — an index fund would have done better.")
        paragraphs.append(first)

    # ---- 2. What holding it cost ---------------------------------------
    depth = drawdown.get("maxDrawdown")
    if _known(depth):
        pain = f"The worst stretch was a {_pct(abs(depth), 0)} fall"
        recovery_days = drawdown.get("maxDrawdownRecoveryDays")
        if _known(recovery_days):
            pain += f" that took {int(recovery_days)} days to climb back from"
        elif drawdown.get("maxDrawdownRecovered") is None:
            pain += " that it has still not climbed back from"
        under_water = drawdown.get("timeUnderWaterDays")
        if _known(under_water) and under_water > 20:
            pain += (f", and there was a {int(under_water)}-day stretch where you would have "
                     f"been sitting on a loss with nothing to show for it")
        pain += "."
        current = drawdown.get("currentDrawdown")
        if _known(current):
            pain += (" Right now it is at or near its high."
                     if abs(current) < 0.02 else
                     f" Right now it sits {_pct(abs(current), 0)} below its best price.")
        paragraphs.append(pain)

    # ---- 3. The random-entry test --------------------------------------
    # The single most useful sentence in the summary, because it replaces "it
    # returned X" (one lucky start date) with "here is what EVERY start date
    # would have given you".
    # USABLE rows only. Unsupported horizons are now reported rather than
    # dropped, so "there is a 3-year row" no longer means "there is a 3-year
    # answer" — and a summary built from one would say a stock made money in
    # every window it never measured.
    usable = [row for row in rolling if row.get("usable", True) and _known(row.get("worst"))]
    chosen = next((row for row in usable if row.get("years") == 3), None)
    if chosen is None and usable:
        chosen = usable[-1]
    if chosen:
        horizon = chosen.get("years")
        worst = chosen.get("worst")
        share = chosen.get("positiveShare")
        windows = chosen.get("windows")
        line = (f"If you had bought at any random point in this history and held for "
                f"{horizon} years, ")
        if _known(share) and share >= 0.999:
            line += "you would have made money every single time"
        elif _known(share):
            line += f"you would have made money {_pct(share, 0)} of the time"
        else:
            line += "the outcomes were mixed"
        if _known(worst):
            if worst >= 0.02:
                line += f", with even the worst entry returning {_pct(worst, 0)} a year"
            elif worst >= -0.02:
                line += ", with the worst case being roughly break-even"
            else:
                line += f", with the worst entry losing {_pct(abs(worst), 0)} a year"
        if _known(windows):
            line += f" (across {int(windows)} overlapping windows)"
        line += "."
        paragraphs.append(line)

    # ---- 4. Where it stands today --------------------------------------
    from_high = position.get("fromHigh52w")
    faber = (block.get("faber") or {})
    if _known(from_high):
        stance = ""
        if faber.get("usable"):
            stance = (" A simple long-term trend rule that follows the ten-month average "
                      "currently says stay invested."
                      if faber.get("signal") == "invested" else
                      " A simple long-term trend rule that follows the ten-month average "
                      "currently says stand aside.")
        near = abs(from_high) < 0.05
        paragraphs.append(
            (f"Today it trades {'right at' if near else _pct(abs(from_high), 0) + ' below'} "
             f"its 52-week high.") + stance)

    # ---- 5. The honesty paragraph --------------------------------------
    # Always present. If the series is indistinguishable from a random walk, the
    # reader is told before they read the trend section, not after.
    hurst_reading = block.get("hurstReading") or {}
    hurst_verdict = hurst_reading.get("verdict")
    caveats = []
    if hurst_verdict == "indistinguishable":
        caveats.append(
            "a statistical test cannot tell this price history apart from a random walk, so "
            "the trend readings below are probably describing noise")
    elif hurst_verdict == "meanReverting":
        caveats.append(
            "this series has historically tended to reverse rather than continue, so discount "
            "the trend readings below")
    if years is not None and years < 3:
        caveats.append(
            f"only about {years:.0f} years of history is loaded, which is thin for any "
            f"multi-year statement — try 10y or max")
    caveats.append(
        "none of this knows anything about the business — it would read the same on a company "
        "about to be delisted")
    lead = "Worth remembering: " if len(caveats) == 1 else "Two things to remember: "
    if len(caveats) > 2:
        lead = "A few things to remember: "
    paragraphs.append(lead + "; ".join(caveats) + ".")

    return {
        "ticker": name,
        "paragraphs": paragraphs,
        # The handful of numbers that survive into Simple mode, in the order a
        # person actually asks them: what did it make, what did it cost, was the
        # cost paid for, and what does a bad entry look like.
        "simpleMetrics": ["cagr", "maxDrawdown", "timeUnderWaterDays",
                          "sortino", "rollingWorst", "relativeExcess"],
    }


# ============================================================================ #
# Assembly — one function per lens
#
# These map an engine's payload onto the registry. They live here rather than in
# the routes so that the set of metrics carrying an explanation is visible in
# one place: if a number appears on screen without a line here, it has no
# explanation, and `tests/test_explain.py` asserts that list is empty.
# ============================================================================ #
def for_long_term(block: dict, ticker: str = "", risk_free: float = 0.0,
                  currency: str = "") -> dict:
    """Explanations for every figure the long-horizon panel renders."""
    risk = block.get("risk") or {}
    drawdown = block.get("drawdown") or {}
    position = block.get("position") or {}
    faber = block.get("faber") or {}
    relative = block.get("relativeStrength") or {}
    regression = block.get("regression") or {}
    momentum = block.get("momentum") or {}
    coppock = block.get("coppock") or []

    out: dict = {}

    for key in ("cagr", "volatility", "downsideDeviation", "calmar", "skew",
                "kurtosis", "positiveDays", "bestDay", "worstDay"):
        result = explain(key, risk.get(key))
        if result:
            out[key] = result
    for key in ("sharpe", "sortino"):
        result = explain(key, risk.get(key), riskFree=risk.get("riskFree", risk_free))
        if result:
            out[key] = result
    out["var95"] = explain("var95", risk.get("var95"))
    out["cvar95"] = explain("cvar95", risk.get("cvar95"), var95=risk.get("var95"))

    for key in ("maxDrawdown", "currentDrawdown", "timeUnderWaterDays", "ulcerIndex"):
        result = explain(key, drawdown.get(key))
        if result:
            out[key] = result
    # Recovery is the one metric whose MISSING value is the interesting case —
    # "never recovered" is a reading, not a gap — so it is always asked for.
    out["maxDrawdownRecoveryDays"] = explain(
        "maxDrawdownRecoveryDays", drawdown.get("maxDrawdownRecoveryDays"))

    reading = block.get("hurstReading") or {}
    out["hurst"] = explain("hurst", block.get("hurst"),
                           stderr=reading.get("stderr"), verdict=reading.get("verdict"),
                           low=reading.get("randomWalkLow"), high=reading.get("randomWalkHigh"),
                           observations=reading.get("observations"))
    out["momentum12_1"] = explain("momentum12_1", momentum.get("momentum12_1"))

    if faber.get("usable"):
        out["faberDistance"] = explain("faberDistance", faber.get("distance"),
                                       signal=faber.get("signal"),
                                       monthsInStance=faber.get("monthsInStance"))
    for key in ("fromHigh52w", "fromAllTimeHigh", "rangePosition"):
        result = explain(key, position.get(key))
        if result:
            out[key] = result

    if regression:
        out["regressionSlope"] = explain("regressionSlope", regression.get("slopePerYear"),
                                         rSquared=regression.get("rSquared"))
        out["regressionR2"] = explain("regressionR2", regression.get("rSquared"))

    benchmark = relative.get("benchmark")
    out["benchmarkCorrelation"] = explain("benchmarkCorrelation", relative.get("correlation"),
                                          benchmark=benchmark)
    for label, row in (relative.get("periods") or {}).items():
        result = explain("relativeExcess", (row or {}).get("excess"),
                         period=label, benchmark=benchmark)
        if result:
            out[f"relativeExcess.{label}"] = result

    rolling_rows = block.get("rollingReturns") or []
    for row in rolling_rows:
        result = explain("rollingWorst", row.get("worst"), years=row.get("years"),
                         positiveShare=row.get("positiveShare"),
                         reason=row.get("reason"), windows=row.get("windows"))
        if result:
            out[f"rollingWorst.{row.get('years')}"] = result
    # The bare key is what Simple mode renders, so it has to point at a horizon
    # that was actually measured. Preferring the 3-year row by key alone would
    # now hand Simple mode a "needs more history" card while a perfectly good
    # 1-year answer sat beside it.
    measured = [row for row in rolling_rows
                if row.get("usable", True) and _known(row.get("worst"))]
    preferred = next((row for row in measured if row.get("years") == 3), None)
    if preferred is None and measured:
        preferred = measured[-1]
    if preferred is not None:
        out["rollingWorst"] = out.get(f"rollingWorst.{preferred.get('years')}")

    if coppock:
        out["coppock"] = explain("coppock", coppock[-1].get("value"),
                                 previous=coppock[-2].get("value") if len(coppock) > 1 else None)

    # `relativeExcess` bare key for Simple mode: prefer the 36-month row, which
    # is the horizon this panel is about, and fall back to the longest available.
    for label in ("36m", "12m", "6m", "3m"):
        if f"relativeExcess.{label}" in out:
            out["relativeExcess"] = out[f"relativeExcess.{label}"]
            break

    return {k: v for k, v in out.items() if v is not None}


def for_indicators(indicators: dict, price: Optional[float] = None) -> dict:
    """Explanations for the all-indicators grid."""
    i = indicators or {}
    out = {
        "sma200": explain("sma200", i.get("sma200"), price=price),
        "sma100": explain("sma100", i.get("sma100"), price=price),
        "sma50": explain("sma50", i.get("sma50"), price=price),
        "adx": explain("adx", i.get("adx"), plusDi=i.get("plusDi"), minusDi=i.get("minusDi")),
        "aroon": explain("aroon", i.get("aroonUp"), aroonDown=i.get("aroonDown")),
        "rsi": explain("rsi", i.get("rsi")),
        "stochastic": explain("stochastic", i.get("stochK"), stochD=i.get("stochD")),
        "williamsR": explain("williamsR", i.get("williamsR")),
        "cci": explain("cci", i.get("cci")),
        "macd": explain("macd", i.get("macd"), macdSignal=i.get("macdSignal")),
        "bbPercentB": explain("bbPercentB", i.get("bbPercentB")),
        "bbBandwidth": explain("bbBandwidth", i.get("bbBandwidth"),
                               squeezePercentile=i.get("bbBandwidthPercentile")),
        "atrPct": explain("atrPct", i.get("atrPct"), atr=i.get("atr")),
        "mfi": explain("mfi", i.get("mfi")),
        "cmf": explain("cmf", i.get("cmf")),
        "volumeTrend": explain("volumeTrend", i.get("volumeTrend")),
        "roc63": explain("roc63", i.get("roc63")),
        "roc252": explain("roc252", i.get("roc252")),
    }
    return {k: v for k, v in out.items() if v is not None}


def for_quality(payload: dict) -> dict:
    """Explanations for Piotroski, Altman, Beneish, their inputs and their provenance."""
    out: dict = {}
    # One explanation per validation-domain dimension, keyed
    # `domain.<screen>.<dimension>`. The FACTS live in `_lib/screendomain.py`
    # where the citations are; this only wraps them in the standard three-part
    # shape so the panel renders them with the same affordance as every other
    # number, and so the band is decided in the one place bands are decided.
    for screen, block in ((payload.get("domains") or {}).get("screens") or {}).items():
        for dimension in block.get("dimensions") or []:
            result = explain("validationDomain", dimension.get("verdict"),
                             name=dimension.get("name"), sample=dimension.get("sample"),
                             this_use=dimension.get("thisUse"), note=dimension.get("note"))
            if result:
                out[f"domain.{screen}.{dimension['key']}"] = result
    piotroski = payload.get("piotroski") or {}
    if piotroski:
        out["piotroski"] = explain("piotroski", piotroski.get("score"),
                                   maxScore=piotroski.get("maxScore"))
    altman = payload.get("altman") or {}
    if altman:
        out["altman"] = explain("altman", altman.get("score"))
        for part, value in (altman.get("components") or {}).items():
            result = explain("altmanComponent", value, part=part)
            if result:
                out[f"altmanComponent.{part}"] = result
    beneish = payload.get("beneish") or {}
    if beneish:
        out["beneish"] = explain("beneish", beneish.get("score"),
                                 indicesAvailable=beneish.get("indicesAvailable"),
                                 indicesTotal=beneish.get("indicesTotal"))
    posterior = payload.get("manipulationPosterior")
    if posterior:
        out["manipulationPosterior"] = explain(
            "manipulationPosterior", posterior.get("posterior"),
            flagged=posterior.get("flagged"), prior_text=posterior.get("priorText"),
            robust=(posterior.get("robustRange") or {}).get("sentence"),
            partial=posterior.get("partialScore"))
        for part, value in (beneish.get("indices") or {}).items():
            result = explain("beneishIndex", value, part=part)
            if result:
                out[f"beneishIndex.{part}"] = result
    return {k: v for k, v in out.items() if v is not None}


def for_valuation(payload: dict) -> dict:
    """Explanations for the intrinsic-value panel.

    The lens most at risk of being read as a price target, so the readings here
    push hardest in the other direction: every one of them ends by pointing at
    an assumption the reader can change.
    """
    mc = payload.get("monteCarlo") or {}
    base = payload.get("baseCase") or {}
    assumptions = payload.get("assumptions") or {}
    beta_estimate = payload.get("betaEstimate") or {}

    median = mc.get("p50")
    p25, p75 = mc.get("p25"), mc.get("p75")
    spread = None
    if all(_known(v) for v in (median, p25, p75)) and median:
        spread = abs(float(p75) - float(p25)) / abs(float(median))

    out = {
        "upside": explain("upside", mc.get("upside"), engine=payload.get("engine"),
                          price_label=payload.get("priceLabel"),
                          fair_label=mc.get("p50Label")),
        "probUndervalued": explain("probUndervalued", mc.get("probUndervalued"),
                                   iterations=assumptions.get("iterations")),
        "terminalShare": explain("terminalShare", base.get("terminalShare")),
        "impliedGrowth": explain("impliedGrowth", base.get("impliedGrowth"),
                                 assumedGrowth=base.get("assumedGrowth"),
                                 engine=payload.get("engine")),
        "discountRate": explain("discountRate", payload.get("discountRate"),
                                rate_name=payload.get("rateName"),
                                risk_free=payload.get("riskFree"),
                                beta=beta_estimate.get("used")),
        "valuationSpread": explain("valuationSpread", spread,
                                   p25_label=mc.get("p25Label"), p75_label=mc.get("p75Label")),
    }
    return {k: v for k, v in out.items() if v is not None}


def for_flow(payload: dict, currency: str = "") -> dict:
    """Explanations for the liquidity block and the anomaly statistics."""
    liquidity = payload.get("liquidity") or {}
    stats = payload.get("stats") or {}
    accumulation = payload.get("accumulation") or {}
    current = accumulation.get("current") or {}

    out = {
        "spread": explain("spread", liquidity.get("spread"),
                          source=(liquidity.get("spreadDetail") or {}).get("primarySource"),
                          floor=(liquidity.get("spreadDetail") or {}).get("resolutionFloor"),
                          at_floor=(liquidity.get("spreadDetail") or {}).get("atFloor")),
        "moveVsSpread": explain("moveVsSpread", liquidity.get("moveVsSpread"),
                                resolved=liquidity.get("spreadResolved", True)),
        "yangZhangVol": explain("yangZhangVol", liquidity.get("yangZhangVol")),
        "amihud": explain("amihud", liquidity.get("amihud"), currency=currency),
        "anomalyRate": explain("anomalyRate", stats.get("anomalyRate"),
                               totalDays=stats.get("totalDays")),
        "recentFlowBias": explain("flowBias", stats.get("recentFlowBias"),
                                  days=stats.get("recentDays"), count=stats.get("recentCount")),
        "netFlowBias": explain("flowBias", stats.get("netFlowBias")),
    }
    # The panel renders its regimes table whenever ANY episode exists, but this
    # explanation was emitted only when one was still ONGOING — so a ticker with
    # two finished regimes showed the table with nothing saying what a regime is.
    # Describe the current one if there is one, otherwise the most recent.
    episode = current or (accumulation.get("episodes") or [None])[-1]
    if episode:
        out["cusumEpisode"] = explain("cusumEpisode", None,
                                      direction=episode.get("direction"),
                                      days=episode.get("days"),
                                      avgRvol=episode.get("avgRvol"),
                                      ongoing=bool(episode.get("ongoing")))
    return {k: v for k, v in out.items() if v is not None}


# ============================================================================ #
# The shorter-horizon story
# ============================================================================ #
def horizon_story(ticker: str, block: dict, currency_format=None) -> dict:
    """The short- or mid-term readout, said out loud.

    Deliberately opens by naming the setup or admitting there is none, because
    "nothing here" is the most common honest answer and burying it under
    paragraphs of context is how a tool teaches people to always find a trade.
    """
    money = currency_format or (lambda v: f"{v:,.2f}")
    name = (ticker or "This stock").upper()
    setup = block.get("setup") or {}
    plan = block.get("plan") or {}
    levels = block.get("levels") or {}
    paragraphs: list[str] = []

    # ---- 1. what the setup is ------------------------------------------
    if setup.get("name"):
        paragraphs.append(f"{name} is in a {setup['name'].lower()}. {setup['reason']}")
    else:
        paragraphs.append(setup.get("reason") or "No recognised setup is present.")

    # ---- 2. the levels, if there are any -------------------------------
    if plan.get("usable"):
        target = (plan.get("targets") or [{}])[0]
        line = (f"If you were taking it: entry around {money(plan['entry'])}, stop at "
                f"{money(plan['stop'])} — that is {_pct(plan['stopDistancePct'])} below, "
                f"placed just under "
                + ("a level the price has previously turned at"
                   if plan.get("stopBasis") == "structure"
                   else f"{_num(plan['stopDistanceAtr'], 1)} average daily ranges")
                + ". ")
        if target.get("price") is not None:
            line += (f"First target {money(target['price'])} "
                     f"({_signed_pct(target.get('distancePct'))}), which is "
                     f"{_num(plan['riskReward'], 1)} times what you are risking.")
        paragraphs.append(line)

        paragraphs.append(
            f"Sized so that being stopped out costs {_pct(plan['riskBudget'], 0)} of your "
            f"account, the position would be {_pct(plan['positionShare'], 0)} of it."
            + (" The arithmetic wanted more than the whole account, so that figure is a cap."
               if plan.get("positionUncapped", 0) > 1.0 else ""))
    else:
        supports = levels.get("supports") or []
        resistances = levels.get("resistances") or []
        if supports or resistances:
            parts = []
            if resistances:
                parts.append(f"the nearest ceiling is {money(resistances[0]['price'])} "
                             f"({_signed_pct(resistances[0]['distancePct'])} away)")
            if supports:
                parts.append(f"the nearest floor is {money(supports[0]['price'])} "
                             f"({_signed_pct(supports[0]['distancePct'])} away)")
            paragraphs.append("There is no trade to plan, but the structure is worth knowing: "
                              + " and ".join(parts) + ".")

    # ---- 3. what would change the picture -------------------------------
    squeeze = block.get("squeeze") or {}
    volume = block.get("volume") or {}
    watch: list[str] = []
    if squeeze.get("inSqueeze"):
        watch.append("price movement has contracted to the quietest in about a year, so a "
                     "larger move is more likely than usual — in an unknown direction")
    if volume.get("anaemic"):
        watch.append("trading volume is unusually thin, which makes every reading here noisier")
    if (block.get("gaps") or {}).get("unfilled"):
        gap = block["gaps"]["unfilled"][-1]
        watch.append(f"there is an unfilled gap around {money(gap['from'])} that the price "
                     f"jumped straight over, so it may move quickly through that band")
    if watch:
        paragraphs.append("Worth watching: " + "; ".join(watch) + ".")

    # ---- 4. the honesty paragraph, always present -----------------------
    paragraphs.append(_horizon_caveat(block))

    return {"ticker": name, "paragraphs": paragraphs}


def _horizon_caveat(block: dict) -> str:
    """The standing warning, phrased for how good the evidence actually is.

    This is the paragraph the whole shorter-horizon section is built around. The
    long-horizon panel earns its confidence from decades of published work; this
    one does not, and printing both in the same voice would be the single most
    misleading thing the app could do.
    """
    setup = block.get("setup") or {}
    evidence = setup.get("evidence")
    lead = "Be careful how much weight you put on this. "
    if evidence == "moderate":
        return (lead + "Breakout rules of this kind sit on the strongest evidence anything in "
                "this section has — trends in price do persist over months, across many markets "
                "and decades of data. That is a statement about averages over thousands of "
                "trades, not a forecast for this one, and the edge is thin enough that trading "
                "costs matter.")
    if evidence == "weak":
        return (lead + "This setup is widely taught and thinly evidenced. The mechanism is "
                "plausible and the published out-of-sample support is close to absent once "
                "trading costs are counted. The levels below are useful for deciding how much "
                "to risk; they are not a reason to take the trade.")
    return (lead + "Everything in this section describes the last few weeks of price movement. "
            "Short-horizon technical signals have far weaker published support than the "
            "long-horizon ones, and over one to four weeks prices have historically shown mild "
            "REVERSAL rather than continuation — the opposite of the twelve-month effect. "
            "Nothing here knows anything about the business.")


def for_horizon(block: dict, currency_format=None) -> dict:
    """Explanations for one shorter-horizon readout."""
    if not block.get("usable"):
        return {}
    money = currency_format or (lambda v: f"{v:,.2f}")
    plan = block.get("plan") or {}
    levels = block.get("levels") or {}
    squeeze = block.get("squeeze") or {}
    volume = block.get("volume") or {}
    divergence = block.get("divergence") or {}
    gaps = block.get("gaps") or {}

    out: dict = {}
    if plan.get("usable"):
        first = (plan.get("targets") or [{}])[0]
        out["riskReward"] = explain("riskReward", plan.get("riskReward"),
                                    target_label=first.get("label"))
        out["stopDistance"] = explain("stopDistance", plan.get("stopDistancePct"),
                                      atr_multiple=plan.get("stopDistanceAtr"),
                                      basis=plan.get("stopBasis"))
        out["positionShare"] = explain("positionShare", plan.get("positionShare"),
                                       risk_budget=plan.get("riskBudget"),
                                       uncapped=plan.get("positionUncapped"))

    for side, key in (("resistance", "resistances"), ("support", "supports")):
        nearest = (levels.get(key) or [None])[0]
        if nearest:
            out[f"distanceToLevel.{side}"] = explain(
                "distanceToLevel", nearest.get("distancePct"), side=side,
                touches=nearest.get("touches"), price_text=money(nearest["price"]))

    out["squeezePercentile"] = explain("squeezePercentile", squeeze.get("percentile"),
                                       fired=squeeze.get("firedDirection"))
    out["volumeRatio"] = explain("volumeRatio", volume.get("ratio"))

    active = divergence.get("bearish") or divergence.get("bullish")
    out["divergenceState"] = explain("divergenceState", 1 if active else None,
                                     kind=(active or {}).get("kind"))

    unfilled = (gaps.get("unfilled") or [None])[-1]
    out["gapState"] = explain("gapState", (unfilled or {}).get("distancePct"),
                              direction=(unfilled or {}).get("direction"),
                              size_atr=(unfilled or {}).get("sizeAtr"))

    for anchor in (block.get("vwap") or {}).get("anchors") or []:
        result = explain("vwapDistance", anchor.get("distancePct"), anchor=anchor.get("label"))
        if result:
            out[f"vwapDistance.{anchor['label']}"] = result

    return {k: v for k, v in out.items() if v is not None}


# ============================================================================ #
# The breadth tier
#
# Percentiles, not scores. Every reading here has to say "within this scan",
# because that is the only claim a cross-sectional rank supports — a name in the
# top decile of the Nasdaq-100 on momentum may still be falling in absolute
# terms if the whole index is.
# ============================================================================ #
def _percentile_words(value: float) -> str:
    if value >= 90:
        return "in the top tenth of this scan"
    if value >= 75:
        return "in the top quarter of this scan"
    if value >= 60:
        return "in the better half of this scan"
    if value >= 40:
        return "around the middle of this scan"
    if value >= 25:
        return "in the weaker half of this scan"
    if value >= 10:
        return "in the bottom quarter of this scan"
    return "in the bottom tenth of this scan"


@metric("compositeRank")
def _composite(value, coverage=None, available=None, total=None, **_):
    label = "Overall rank"
    what = ("The weighted average of where this name sits on every signal, compared with the "
            "others in the same scan. 100 would be best on everything.")
    if not _known(value):
        return unavailable(label, what, "no signal could be computed for this name")
    band = _ladder(value, ((25, "poor"), (45, "fair"), (70, "good"), (None, "excellent")))
    reading = (f"{value:.0f} out of 100, {_percentile_words(value)}. This is a position "
               f"WITHIN this universe on this date, not a score on an absolute scale — if the "
               f"whole list is falling, the top of it is still falling.")
    if _known(available) and _known(total) and available < total:
        reading += (f" Built from {int(available)} of {int(total)} signals; the rest had too "
                    f"little history and were left out rather than filled in with a guess.")
    return make(label, what, reading,
                "A ranking is a shortlist, not a verdict. Its job is to decide which few names "
                "are worth opening the four lenses on.",
                band, "high", evidence="moderate", value_text=f"{value:.0f}")


@metric("signalRank")
def _signal_rank(value, signal=None, raw=None, raw_text=None, **_):
    from . import ranking
    definition = ranking.SIGNAL_BY_KEY.get(signal or "", {})
    label = definition.get("label", "Signal")
    what = f"{definition.get('question', '')} {definition.get('detail', '')}".strip()
    if not _known(value):
        return unavailable(label, what or "One ranking signal.",
                           "not enough history for this name")
    band = _ladder(value, ((25, "poor"), (45, "fair"), (70, "good"), (None, "excellent")))
    reading = f"{value:.0f} out of 100 — {_percentile_words(value)}"
    if raw_text:
        reading += f", on a reading of {raw_text}"
    reading += ". "
    if definition.get("direction") == -1:
        reading += ("Note the direction: a LOWER raw number ranks better here, and the "
                    "percentile already accounts for that.")
    return make(label, what or "One ranking signal.", reading,
                "One input among several. The composite beside it is what orders the table, "
                "and the overlap between signals is measured below it.",
                band, "high", evidence=definition.get("evidence"),
                value_text=f"{value:.0f}")


@metric("signalOverlap")
def _signal_overlap(value, a=None, b=None, **_):
    label = "Signal overlap"
    what = ("How much two of the ranking signals are measuring the same thing. 1.0 would mean "
            "they are interchangeable.")
    if not _known(value):
        return unavailable(label, what, "too few complete rows to measure it")
    magnitude = abs(value)
    if magnitude > 0.7:
        band = "caution"
        verdict = (f"{_num(value)} — these two are close to the same measurement. The composite "
                   f"is counting that one fact more than once, which makes it look like a "
                   f"consensus of independent tests when it is not.")
    elif magnitude > 0.4:
        band = "context"
        verdict = f"{_num(value)} — related, as you would expect, but not duplicates."
    else:
        band = "good"
        verdict = f"{_num(value)} — largely independent of each other."
    if a and b:
        verdict = f"{a} and {b}: " + verdict
    return make(label, what, verdict,
                "Where two signals overlap heavily, treat their agreement as one opinion rather "
                "than two. This is the same caveat the four-lens view carries, measured instead "
                "of asserted.",
                band, "low", evidence="strong", value_text=_num(value))


def for_ranking(result: dict) -> dict:
    """Explanations for the ranking table: the composite, each signal, the overlap."""
    from . import ranking

    out: dict = {}
    for signal in result.get("signals") or ranking.SIGNALS:
        key = signal["key"]
        # A definition-level explanation for the column header, independent of
        # any one row: the table needs to explain its columns before a reader
        # has clicked into a name.
        out[f"signalDefinition.{key}"] = make(
            label=signal["label"],
            what=f"{signal['question']} {signal['detail']}",
            reading=("Ranked across every name in this scan"
                     + (", with a LOWER raw reading ranking better."
                        if signal["direction"] == -1 else ", highest first.")
                     + f" Weighted {signal['weight']:.1f} in the composite, because the "
                       f"published evidence for it is {signal['evidence']}."),
            action=("One column among several. Sort by it to see the ranking that signal alone "
                    "would produce."),
            band="context", good_direction="none", evidence=signal["evidence"],
        )

    correlation = result.get("correlation") or {}
    # EVERY pair, not the top few. The panel decides how many rows to show, and
    # when the server explained three while the panel listed four, the last row
    # lost its info icon — the two counts were free to drift apart because
    # nothing tied them together. Seven signals make twenty-one pairs; that is
    # cheap enough to send in full and removes the coupling.
    for pair in (correlation.get("pairs") or []):
        explanation = explain(
            "signalOverlap", pair["correlation"],
            a=ranking.SIGNAL_BY_KEY.get(pair["a"], {}).get("label", pair["a"]),
            b=ranking.SIGNAL_BY_KEY.get(pair["b"], {}).get("label", pair["b"]))
        if explanation:
            out[f"signalOverlap.{pair['a']}.{pair['b']}"] = explanation

    return {k: v for k, v in out.items() if v is not None}


def for_ranking_row(row: dict) -> dict:
    """Explanations for one ranked name, built on demand when a row expands."""
    from . import ranking

    out = {"compositeRank": explain("compositeRank", row.get("composite"),
                                    coverage=row.get("coverage"),
                                    available=row.get("signalsAvailable"),
                                    total=row.get("signalsTotal"))}
    for key, entry in (row.get("signals") or {}).items():
        definition = ranking.SIGNAL_BY_KEY.get(key, {})
        raw = entry.get("raw")
        # Percent-shaped signals are quoted as percentages, the rest as numbers.
        raw_text = None
        if _known(raw):
            raw_text = (_signed_pct(raw) if key in ("momentum", "trend", "nearHigh",
                                                    "relativeStrength")
                        else _pct(raw) if key in ("lowVolatility", "shallowDrawdown")
                        else _num(raw, 3))
        explanation = explain("signalRank", entry.get("percentile"), signal=key,
                              raw=raw, raw_text=raw_text)
        if explanation:
            # `what` is the SIGNAL DEFINITION and is identical on every row. It
            # already ships once per scan under `signalDefinition.<key>`, and
            # repeating it here would be most of the payload: seven copies per
            # row across a hundred names is a couple of hundred kilobytes of
            # duplicated prose. The panel falls back to the definition.
            explanation = {**explanation, "what": ""}
            out[f"signal.{key}"] = explanation
        _ = definition
    return {k: v for k, v in out.items() if v is not None}


# ============================================================================ #
# The synthesis — what all four lenses add up to
#
# WHY THIS IS PROSE AND NOT A SCORE, WHICH IS THE WHOLE POINT
# -----------------------------------------------------------
# The obvious feature request is a single BUY / HOLD / SELL, or a 0-100
# conviction number. It is refused deliberately and permanently.
#
# The app spends real effort establishing that its four lenses are not four
# independent opinions (two read price, two read filings), that a seven-column
# ranking carries about 3.4 signals' worth of information, that a DCF is
# typically 60-80% perpetuity guess, and that several readings are graded weak.
# A single composite number discards every one of those findings, and it does it
# in the one field everybody would read. The moment it exists, nobody opens the
# four lenses again.
#
# So this returns SENTENCES. It says what the lenses agree on, it names the
# places they disagree, it states what this app cannot tell you about THIS
# ticker, and it lists what would change the picture. Every clause is defensible
# because every clause is a restatement of a number computed elsewhere in the
# payload — not a new claim, and never a recommendation.
#
# THE DISAGREEMENTS ARE THE PRODUCT. A reader who learns only that "value says
# cheap and quality says the accruals are flagged" has been told the single most
# useful thing available about that company, and it is precisely the sentence a
# composite score would average away.
# ============================================================================ #

# Which body of data each lens reads. Mirrors the same rule in
# `components/ConfluenceRail.tsx` (`agreementOf`), which keeps its own copy
# because it must render while legs are still loading and cannot wait for a
# server round trip. This one exists for the PROSE — it never recomputes the
# rail's vote arithmetic, so the two cannot disagree about a tally.
SYNTHESIS_FAMILY = {"flow": "price", "trend": "price",
                    "value": "filings", "quality": "filings"}

# The GROUPING above stays a declared assumption — nothing measures which data a
# lens reads, and nothing could. What is now measured is its CONSEQUENCE: how
# often the two families' verdicts actually coincide once each family's own
# habits are accounted for. `lensagreement` holds that measurement and
# `_warrant` below is where it either earns this app's central claim or takes it
# away. See §15 of RESEARCH_ROADMAP.md.
FAMILY_LABEL = {"price": "price and volume", "filings": "the filings"}

# Verbatim from the app's own framing. A DCF whose terminal value is more than
# this share of the answer is mostly a statement about the perpetuity.
TERMINAL_SHARE_WARN = 0.60


def _plain(text: Optional[str]) -> str:
    """Strip the `**bold**` markers the technical headline carries for the UI."""
    return (text or "").replace("**", "").strip()


def _leg(payload: dict, name: str) -> Optional[dict]:
    """One confluence leg's data, or None if it failed or is absent.

    Every read below goes through this. A synthesis that raises because one
    engine returned an unexpected shape would take down the one panel whose job
    is to explain the others.
    """
    leg = (payload or {}).get(name)
    if not isinstance(leg, dict) or not leg.get("ok"):
        return None
    data = leg.get("data")
    return data if isinstance(data, dict) else None


def _reading(lens: str, key: str, verdict: str, sentence: str, tone: str,
             vote: int) -> dict:
    return {"lens": lens, "key": key, "family": SYNTHESIS_FAMILY[key],
            "familyLabel": FAMILY_LABEL[SYNTHESIS_FAMILY[key]],
            "verdict": verdict, "sentence": sentence, "tone": tone, "vote": vote}


def _read_flow(data: dict) -> Optional[dict]:
    stats = data.get("stats") or {}
    recent = stats.get("recentCount")
    days = stats.get("recentDays")
    if recent is None or days is None:
        return None
    bias = (stats.get("recentFlowBias") or "Neutral").lower()

    episode = ((data.get("accumulation") or {}).get("current")) or None
    tail = ""
    if isinstance(episode, dict) and episode.get("direction"):
        tail = (f" A sustained {str(episode['direction']).lower()} regime is running "
                f"underneath the day-to-day noise, which is the pattern a patient "
                f"buyer leaves and a single-day detector cannot see.")

    if not recent:
        total = stats.get("anomalyCount")
        extra = f" ({total} unusual days across the whole window.)" if total else ""
        return _reading(
            "Flow", "flow", "Quiet",
            f"Nothing unusual has traded in the last {days} days.{extra}{tail}",
            "neutral", 0)

    plural = "" if recent == 1 else "s"
    vote = 1 if bias == "accumulation" else -1 if bias == "distribution" else 0
    word = {"accumulation": "buying", "distribution": "selling"}.get(bias, "mixed")
    return _reading(
        "Flow", "flow", word.capitalize(),
        f"{recent} unusual day{plural} in the last {days}, leaning {word}. "
        f"Unusual means statistically unlike this stock's other days — it does not "
        f"mean an institution was behind it.{tail}",
        "good" if vote > 0 else "bad" if vote < 0 else "neutral", vote)


def _read_trend(data: dict) -> Optional[dict]:
    long_term = data.get("longTerm") or {}
    view = long_term.get("view") or {}
    # Prefer the LONG-HORIZON verdict when there is enough history for one. The
    # 50/200-day trend label describes the last few months wearing the same word,
    # and a reader asking "what does this add up to" is asking the longer question.
    if data.get("hasLongTerm") and view.get("verdict"):
        tone = {"bull": "good", "bear": "bad"}.get(view.get("tone"), "neutral")
        passed, scored = view.get("passed"), view.get("scored")
        count = f" ({passed} of {scored} checks point that way.)" if scored else ""
        return _reading(
            "Trend", "trend", str(view["verdict"]).capitalize(),
            f"{_plain(view.get('headline'))}{count}",
            tone, 1 if tone == "good" else -1 if tone == "bad" else 0)

    summary = data.get("summary") or {}
    if not summary.get("trend"):
        return None
    tone = {"bull": "good", "bear": "bad"}.get(summary.get("trend_tone"), "neutral")
    return _reading(
        "Trend", "trend", str(summary["trend"]).capitalize(),
        _plain(summary.get("headline")).split(". ")[0] + ".",
        tone, 1 if tone == "good" else -1 if tone == "bad" else 0)


ENGINE_WORDS = {"DCF": "cash-flow model", "DDM": "dividend model",
                "RI": "book-value model"}


def _read_value(data: dict) -> Optional[dict]:
    verdict = data.get("verdict")
    monte = data.get("monteCarlo") or {}
    if not verdict or monte.get("p50Label") is None:
        return None
    upside = monte.get("upside")
    engine = ENGINE_WORDS.get(data.get("engine"), "model")

    where = ""
    if _known(upside):
        side = "below" if upside >= 0 else "above"
        where = f", putting the market price {_pct(abs(upside), 0)} {side} that"
    prob = monte.get("probUndervalued")
    runs = (f" {_pct(prob, 0)} of the simulated runs came out cheap."
            if _known(prob) else "")

    vote = 1 if verdict == "UNDERVALUED" else -1 if verdict == "OVERVALUED" else 0
    # The wire verdict is an enum; the LABEL is deliberately not the word
    # "overvalued". Rendered large beside a price, that word is read as a
    # forecast of a fall, which is the one thing a discounted cash flow cannot
    # be. Mirrors `verdictLabel` in lib/utils.ts.
    label = {"UNDERVALUED": "Below model range",
             "OVERVALUED": "Above model range",
             "FAIRLY VALUED": "Within model range"}.get(verdict, str(verdict).capitalize())
    return _reading(
        "Value", "value", label,
        f"The {engine} puts fair value near {monte['p50Label']}{where}.{runs}",
        "good" if vote > 0 else "bad" if vote < 0 else "neutral", vote)


def _read_quality(data: dict) -> Optional[dict]:
    if not data.get("applicable"):
        return _reading(
            "Quality", "quality", "Not applicable",
            "Piotroski, Altman and Beneish were all built on non-financial firms and "
            "none of them transfers to a bank or insurer, so no score is reported here. "
            "That is a refusal, not a gap in the data.",
            "none", 0)

    parts = []
    piotroski = data.get("piotroski") or {}
    if piotroski.get("score") is not None:
        parts.append(f"{piotroski['score']} of {piotroski.get('maxScore', 9)} "
                     f"health checks passed")
    words = {"safe": "the balance sheet is clear of the distress zone",
             "grey": "the balance sheet sits in the grey zone",
             "distress": "the balance sheet is inside the distress zone"}
    band = (data.get("altman") or {}).get("band")
    if band in words:
        parts.append(words[band])
    flags = {"clean": "no sign of massaged earnings",
             "borderline": "accruals close to the manipulation threshold",
             "flagged": "the accrual pattern is flagged for a closer look"}
    beneish = (data.get("beneish") or {}).get("band")
    if beneish in flags:
        parts.append(flags[beneish])
    if not parts:
        return None

    verdict = data.get("verdict") or "NEUTRAL"
    tone = {"SOUND": "good", "CONCERNS": "bad"}.get(verdict, "neutral")
    return _reading(
        "Quality", "quality", verdict.capitalize(),
        (", ".join(parts) + ".").capitalize(),
        tone, 1 if tone == "good" else -1 if tone == "bad" else 0)


def _family_votes(readings: Sequence[dict]) -> dict:
    """One vote per BODY OF DATA, not one per panel.

    Four lenses over two datasets are not four opinions. A family whose members
    disagree votes zero and is recorded as split, because two readings of one
    dataset pointing opposite ways is itself a finding worth a sentence.
    """
    out: dict = {}
    for family in ("price", "filings"):
        members = [r for r in readings if r["family"] == family and r["tone"] != "none"]
        if not members:
            continue
        up = sum(1 for r in members if r["vote"] > 0)
        down = sum(1 for r in members if r["vote"] < 0)
        out[family] = {"vote": 1 if up > down else -1 if down > up else 0,
                       "split": bool(up and down), "members": [r["lens"] for r in members]}
    return out


def _warrant(measured: Optional[dict]) -> str:
    """WHY agreement between the two families is worth anything — the clause
    that carries this app's central claim, written from the measurement.

    Until §15 this was an assertion: "the price record and the filings share no
    inputs — so agreement between them is not one fact counted twice." Nothing
    checked it. The grouping into families is still a declared assumption and
    always will be, but its CONSEQUENCE is now measured across four index
    universes, and this is where the measurement either earns the claim or
    takes it away.

    Three branches, and all three ship. A module that could only phrase the
    result it hoped for would have decided the answer before running it.
    """
    if not measured:
        # Never measured, or measured on too few names. Back to the stated
        # assumption, said as an assumption — which is what the confluence rail
        # has always admitted in smaller type.
        return ("because the price record and the filings read different data — though "
                "how far their verdicts actually overlap is a stated assumption here "
                "rather than something this app has measured")

    families = measured["families"]
    kappa, n = families["kappa"], families["n"]
    where = f"across {n} names in {measured['scope']}"

    if not families.get("excludesZero"):
        return (f"and that is measured rather than assumed: {where}, the two reach the "
                f"same verdict no more often than their own separate habits already "
                f"put them there (κ = {kappa:+.2f}), so agreement between them really "
                f"is two facts and not one counted twice")
    if kappa > 0:
        return (f"with one measured qualification: {where}, the two agree rather more "
                f"often than chance alone would produce (κ = {kappa:+.2f}), so the "
                f"second reading is partly predictable from the first and this is "
                f"worth less than two independent readings")
    return (f"with one measured oddity: {where}, the two agree LESS often than chance "
            f"alone would produce (κ = {kappa:+.2f}), which is a finding in its own "
            f"right rather than reassurance about either of them")


def _agreement(readings: Sequence[dict], families: dict,
               measured: Optional[dict] = None) -> dict:
    """The cross-check sentence — the one claim this whole app is built on."""
    reading_count = len([r for r in readings if r["tone"] != "none"])
    if not families:
        return {"text": "No lens returned a usable reading, so there is nothing to "
                        "cross-check.", "tone": "none",
                "independentSources": 0, "lensesReading": reading_count}

    if len(families) == 1:
        only = next(iter(families))
        return {"text": (
            f"Only {FAMILY_LABEL[only]} could be read here, so there is no cross-check. "
            f"Everything below rests on one body of data, which is exactly the situation "
            f"this app exists to avoid."),
            "tone": "warn", "independentSources": 1, "lensesReading": reading_count}

    price, filings = families["price"]["vote"], families["filings"]["vote"]
    base = {"independentSources": len(families), "lensesReading": reading_count}

    if price and price == filings:
        direction = "the same constructive direction" if price > 0 else "the same negative direction"
        return {**base, "tone": "good" if price > 0 else "bad", "text": (
            f"Both bodies of data point in {direction}. That is the strongest thing this "
            f"app can say, {_warrant(measured)}.")}

    if price and filings and price != filings:
        up = "price and volume" if price > 0 else "the filings"
        down = "the filings" if price > 0 else "price and volume"
        return {**base, "tone": "warn", "text": (
            f"They disagree: {up} read constructively while {down} do not. The "
            f"disagreement is the finding, and this page cannot settle which side is "
            f"right.")}

    active = "price and volume" if price else "the filings"
    quiet = "the filings" if price else "price and volume"
    return {**base, "tone": "neutral", "text": (
        f"Only {active} has a directional view; {quiet} come out neutral. A single "
        f"leaning reading is a weaker claim than agreement between two.")}


def _tensions(readings: dict, payload: dict, families: dict) -> list[dict]:
    """The named conflicts. Each one is a specific, recognised failure shape."""
    out = []
    value, quality = readings.get("value"), readings.get("quality")
    trend, flow = readings.get("trend"), readings.get("flow")

    if value and quality and value["vote"] > 0 and quality["vote"] < 0:
        out.append({"title": "Cheap, with the accounts flagged", "text": (
            "The valuation says the price is below what the cash flows support, and the "
            "accounting screens raise a flag on the same filings. This is the shape of a "
            "value trap: cheap because it deserves to be. Resolve the accounting question "
            "before trusting the valuation, because both are computed from the same "
            "statements and only one of them assumes they are honest.")})

    if value and trend and value["vote"] < 0 and trend["vote"] > 0:
        out.append({"title": "Rising past what the business supports", "text": (
            "The price trend is constructive and the model says the price has run beyond "
            "what the cash flows justify. Both can be true, and both can persist for "
            "years — momentum and valuation operate on completely different clocks. "
            "Nothing here tells you which one turns first.")})

    if value and quality and value["vote"] < 0 and quality["vote"] > 0:
        out.append({"title": "A sound business at a demanding price", "text": (
            "Quality is good and the valuation says expensive. That is a different "
            "problem from a weak business — the risk is the price paid, not the company. "
            "The growth assumption is the lever worth testing here.")})

    for family, info in families.items():
        if info.get("split"):
            out.append({"title": f"Split within {FAMILY_LABEL[family]}", "text": (
                f"{' and '.join(info['members'])} read the same data and point opposite "
                f"ways. That is not two independent opinions cancelling out — it is one "
                f"dataset supporting two readings, which usually means the signal is weak "
                f"rather than balanced.")})

    if flow and trend and flow["vote"] and not trend["vote"]:
        out.append({"title": "Flow moved before the trend did", "text": (
            "Unusual trading has shown up while the price trend itself is unresolved. "
            "This is the case the Flow lens exists for, and also the case where it is "
            "most often wrong — index rebalances, expiries and earnings all leave the "
            "same footprint. The event study on the Flow tab is how you check whether "
            "these flags have ever predicted anything on this ticker.")})

    return out


def _blind_spots(payload: dict, readings: dict) -> list[dict]:
    """What this app cannot tell you about THIS ticker, specifically.

    Not a generic disclaimer. Every entry is switched on by a number in the
    payload, so it names the actual limit in force right now — which is the
    difference between a caveat a reader skips and one they use.
    """
    out = []

    technical = _leg(payload, "technical")
    if technical:
        hurst = ((technical.get("longTerm") or {}).get("hurstReading")) or {}
        if hurst.get("verdict") == "indistinguishable":
            out.append({"title": "The trend tools may be describing noise", "text": (
                "This price history cannot be told apart from a random walk, so discount "
                "every price-based reading here. The filings lenses are unaffected.")})
        if not technical.get("hasLongTerm"):
            out.append({"title": "No long-horizon reading", "text": (
                "Not enough history for the multi-year section — the part with the "
                "strongest evidence. Set the range to 5y or more.")})

    valuation = _leg(payload, "valuation")
    if valuation:
        share = (valuation.get("baseCase") or {}).get("terminalShare")
        if _known(share) and share >= TERMINAL_SHARE_WARN:
            out.append({"title": "Most of the valuation is a perpetuity guess", "text": (
                f"{_pct(share, 0)} of the fair value comes from the terminal assumption — "
                f"what the business is worth forever after year five — rather than from "
                f"the forecast years. The valuation is mostly a statement about that one "
                f"input, and it is editable on the Value tab.")})

    anomaly = _leg(payload, "anomaly")
    if anomaly:
        liquidity = anomaly.get("liquidity") or {}
        if liquidity.get("spreadResolved") is False:
            out.append({"title": "Trading cost is a ceiling, not a measurement", "text": (
                "The bid-ask spread on this name sits below what daily bars can resolve, "
                "so the panel reports an upper bound instead of a figure. Quoting the "
                "estimator's own noise as a cost would overstate what this stock actually "
                "charges to trade.")})

    for name, label in (("anomaly", "Flow"), ("technical", "Trend"),
                        ("valuation", "Value"), ("quality", "Quality")):
        leg = (payload or {}).get(name)
        if isinstance(leg, dict) and not leg.get("ok"):
            detail = leg.get("error")
            if isinstance(detail, dict):
                detail = detail.get("message") or "the engine could not run"
            out.append({"title": f"{label} did not run", "text": (
                f"{str(detail)[:220]} Everything below is missing that lens, so the "
                f"cross-check is weaker than it looks.")})

    if readings.get("quality") and readings["quality"]["tone"] == "none":
        out.append({"title": "No accounting screen for this company", "text": (
            "The three quality models do not apply to banks and insurers, so half of the "
            "filings-side evidence is unavailable here and the valuation carries it alone.")})

    return out


def _next_checks(payload: dict, readings: dict) -> list[str]:
    """What to do next. Concrete, tied to this ticker, and never 'buy'."""
    out = []
    valuation = _leg(payload, "valuation")
    technical = _leg(payload, "technical")
    quality = _leg(payload, "quality")

    if valuation:
        share = (valuation.get("baseCase") or {}).get("terminalShare")
        if _known(share) and share >= TERMINAL_SHARE_WARN:
            out.append("On the Value tab, move terminal growth by half a point and watch "
                       "the fair value move further than the gap you are looking at. If it "
                       "does, the gap is an artefact of that assumption.")
        else:
            out.append("On the Value tab, change the growth assumption to whatever you "
                       "actually believe. The default is a default, not a forecast.")

    if quality and quality.get("applicable") and \
            (quality.get("beneish") or {}).get("band") == "flagged":
        out.append("Read the cash-flow statement against the income statement. A Beneish "
                   "flag means the profit and the cash have diverged, and it is a screen "
                   "rather than a finding — most flags are false alarms.")

    if technical:
        drawdown = ((technical.get("longTerm") or {}).get("drawdown")) or {}
        worst = drawdown.get("maxDrawdown")
        if _known(worst):
            out.append(f"Size any position so that a repeat of the {_pct(abs(worst), 0)} "
                       f"fall in this history would not force you out. That is the single "
                       f"decision the drawdown number exists for.")

    out.append("Run the event study on the Flow tab. It measures whether this ticker's "
               "anomaly flags have predicted anything at all, and a null result there is "
               "the most useful thing it can return.")
    return out


# `for_synthesis(payload)` loads the stamped agreement measurement from disk;
# `for_synthesis(payload, agreement_measurement=None)` says there is none. Those
# are different situations and one default could not tell them apart — the
# second is a state the panel renders honestly rather than a bug to paper over.
# Same device as `pretrade._LOAD_FROM_DISK`, and what lets the synthesis tests
# exercise both warrants without a file on disk.
_LOAD_FROM_DISK = object()


def for_synthesis(payload: dict, market: Optional[str] = None,
                  agreement_measurement=_LOAD_FROM_DISK) -> dict:
    """Everything the four lenses add up to, in sentences.

    `payload` is the `/api/confluence` response — each leg carrying its own
    `ok` flag — so this reads exactly the figures the panels render rather than
    recomputing them, and a failed leg becomes a stated blind spot instead of an
    exception.

    `market` selects which population the agreement measurement describes, for
    the reason `pretrade` takes one: the filings lenses read on a very different
    share of Indonesian names than US ones, so the two families' agreement is
    measured on a different population in each market and a blend describes
    neither.
    """
    # LOCAL, deliberately. Nothing else in this module imports from `_lib` at
    # module level, and that is what keeps the dependency one-directional —
    # `pretrade` imports `explain`, so `explain` acquiring imports of its own is
    # how a cycle would start.
    from . import lensagreement

    if agreement_measurement is _LOAD_FROM_DISK:
        agreement_measurement = lensagreement.for_synthesis(market)
    readers = {"flow": ("anomaly", _read_flow), "trend": ("technical", _read_trend),
               "value": ("valuation", _read_value), "quality": ("quality", _read_quality)}

    readings: dict = {}
    for key, (leg_name, fn) in readers.items():
        data = _leg(payload, leg_name)
        if data is None:
            continue
        try:
            result = fn(data)
        except (TypeError, ValueError, KeyError, ZeroDivisionError, AttributeError):
            result = None
        if result:
            readings[key] = result

    ordered = [readings[k] for k in ("flow", "trend", "value", "quality") if k in readings]
    families = _family_votes(ordered)
    agreement = _agreement(ordered, families, agreement_measurement)
    # The measurement rides along beside the sentence it justifies, so the panel
    # can show the arithmetic behind the clause rather than asking the reader to
    # take a Greek letter on trust. It is never consumed by anything else: the
    # moment a measured agreement started scaling a verdict, this app would have
    # the composite score it refuses to have.
    if agreement_measurement:
        agreement = {**agreement, "measured": agreement_measurement}

    lenses = agreement["lensesReading"]
    sources = agreement["independentSources"]
    if not lenses:
        headline = "No lens returned a usable reading for this ticker."
    else:
        plural = "" if lenses == 1 else "es"
        headline = (f"{lenses} lens{plural} reporting, resting on "
                    f"{sources} independent "
                    f"{'source' if sources == 1 else 'sources'} of data.")

    return {
        "headline": headline,
        "tone": agreement["tone"],
        "readings": ordered,
        "agreement": agreement,
        "tensions": _tensions(readings, payload, families),
        "blindSpots": _blind_spots(payload, readings),
        "nextChecks": _next_checks(payload, readings),
        "caveat": (
            "This is a description of what the four lenses reported, not a recommendation. "
            "Every sentence restates a number computed elsewhere on this page — nothing "
            "here is a forecast, and no combination of these readings is a reason to buy "
            "or sell on its own."),
    }


# ============================================================================ #
# Peer comparison — where one name sits among its own index
#
# THE PROBLEM THIS SOLVES IS CALIBRATION, NOT RANKING.
#
# The single-ticker view reports every figure in absolute terms: a 33% worst
# fall, 28% volatility, 16% a year. To a reader with no priors those numbers are
# unreadable — not because they are complicated, but because nothing on the page
# says whether they are ordinary or alarming. A first-time investor cannot tell
# a normal drawdown from a catastrophic one, and the app never offers a frame.
#
# The ranking tier already computes the frame. `ranking.py` argues that a
# percentile "is a claim about this universe on this date" while a score out of
# a hundred "implies an absolute scale that was never calibrated", and that
# argument applies at least as hard to a lone ticker as it does to a table.
#
# So this restates one row of a scan as sentences. "Its worst fall was milder
# than 68% of the Nasdaq-100" teaches more in one line than the drawdown section
# does in a screen, and it commits to nothing the data does not support.
#
# WHAT IT DELIBERATELY DOES NOT DO: rank the name, or imply that a high position
# is a reason to buy. The percentile is a description of where it sits among a
# named group on a named date. The composite is carried through with the same
# caveat the ranking panel prints, and the peer group is named in every sentence
# so the denominator can never go unnoticed.
# ============================================================================ #

# One phrasing per signal, written so the percentile reads as a comparison
# rather than a score. `{pct}` is the direction-adjusted percentile, so a high
# number is always the favourable end — including for the two signals where a
# LOW raw value is the good one, which is exactly the confusion this avoids.
PEER_PHRASING: dict[str, str] = {
    "momentum": "Has risen more than {pct} of {group} over the past year.",
    "trend": "Its long-run average is rising faster than {pct} of {group}.",
    "nearHigh": "Sitting closer to its 52-week high than {pct} of {group}.",
    "lowVolatility": "Calmer day to day than {pct} of {group}.",
    "shallowDrawdown": "Its worst fall was milder than {pct} of {group}.",
    "relativeStrength": "Beat the index by more than {pct} of {group}.",
    "flow": "Recent days closed stronger on volume than {pct} of {group}.",
}

# Where a percentile stops being unremarkable. Deliberately wide: the middle of a
# distribution is the most common place to be and colouring it would invent a
# verdict out of an ordinary reading.
PEER_HIGH, PEER_LOW = 75.0, 25.0


def _peer_band(percentile: float, evidence: Optional[str]) -> str:
    """A tone for one peer reading, damped by how well the signal is supported.

    A weak-evidence signal never gets a strong colour no matter where the name
    sits, because "top decile on a measure that does not predict anything" is
    not good news and should not be green. Same discipline as everywhere else
    here: the band decides the colour, and the band knows about the evidence.
    """
    if evidence in ("weak", "none"):
        return "context"
    if percentile >= PEER_HIGH:
        return "good"
    if percentile <= PEER_LOW:
        return "poor"
    return "fair"


def for_peers(row: dict, universe: dict, signals: Sequence[dict],
              correlation: Optional[dict] = None) -> dict:
    """One scanned row, restated as where this name sits among its peers."""
    # "72% of Nasdaq-100" reads like a typo; "of the Nasdaq-100" reads like
    # English. Guarded so a name that already carries an article is left alone.
    name = universe.get("name")
    group = "its peers" if not name else (
        name if name.lower().startswith("the ") else f"the {name}")
    scanned = universe.get("scanned")
    breakdown = row.get("signals") or {}

    readings = []
    for signal in signals:
        key = signal["key"]
        entry = breakdown.get(key) or {}
        percentile = entry.get("percentile")
        if not _known(percentile):
            readings.append({
                "key": key, "label": signal["label"], "percentile": None,
                "sentence": (f"Not enough history to place {row.get('ticker', 'this name')} "
                             f"against {group} on this measure."),
                "tone": "none", "band": "unavailable", "evidence": signal["evidence"],
                "rawText": None,
            })
            continue

        band = _peer_band(float(percentile), signal["evidence"])
        template = PEER_PHRASING.get(key, "Ranks above {pct} of {group} on this measure.")
        raw = entry.get("raw")
        raw_text = None
        if _known(raw):
            raw_text = (_signed_pct(raw) if key in ("momentum", "trend", "nearHigh",
                                                    "relativeStrength")
                        else _pct(raw) if key in ("lowVolatility", "shallowDrawdown")
                        else _num(raw, 3))
        readings.append({
            "key": key,
            "label": signal["label"],
            "percentile": float(percentile),
            "rawText": raw_text,
            "sentence": template.format(pct=_pct(float(percentile) / 100.0, 0), group=group),
            "tone": TONE_FOR_BAND[band],
            "band": band,
            "evidence": signal["evidence"],
        })

    composite = row.get("composite")
    rank, of = row.get("rank"), scanned
    if _known(composite) and rank and of:
        headline = (f"Against {group}, {row.get('ticker', 'this name')} places "
                    f"{rank} of {of} on the seven price signals combined.")
    else:
        headline = f"Placed against {group}, on price and volume alone."

    effective = (correlation or {}).get("effectiveSignals")
    overlap = None
    if _known(effective):
        overlap = (f"Those seven columns carry about {_num(effective, 1)} signals' worth of "
                   f"independent information — several of them are different ways of saying "
                   f"\"it went up\", so treat the combined placing as weaker than seven "
                   f"separate tests.")

    return {
        "headline": headline,
        "readings": readings,
        "overlap": overlap,
        "caveat": (
            f"Every line here is a position within {group} on this date, not a score and not "
            f"a verdict. Change the peer group and the same company moves. These seven "
            f"measures are computed from price and volume alone and know nothing about the "
            f"business — the Value and Quality lenses have no peer comparison here, because "
            f"the filings behind them cannot be fetched in batch."
        ),
    }


# ============================================================================ #
# The pre-trade panel — what would stop a careful buyer
#
# WHY A FIRING RATE IS PART OF THE EXPLANATION AND NOT A FOOTNOTE
# ----------------------------------------------------------------
# "Altman says distress" is unreadable without knowing how often Altman says
# distress. On a universe of large listed companies the answer is "rarely", which
# makes it a finding; on a screen tuned differently it could be "a third of the
# time", which would make it a description of the market wearing a warning's
# clothes. The app already applies this discipline to the anomaly screener, where
# a scan over many names produces hits by construction and Benjamini-Hochberg
# says how many were expected. This is the same correction arriving at a panel
# that would otherwise present nine conditions as nine independent alarms.
#
# THE PROSE HERE HAS ONE JOB THE CHECKS THEMSELVES CANNOT DO: say what an empty
# panel means. Every individual check is silent when it does not fire, and
# silence is exactly what a reader mistakes for a pass. So the framing sentence
# is written for the empty case FIRST and adjusted for the non-empty one, rather
# than the other way round.
# ============================================================================ #
@metric("checkFiringRate")
def _check_firing_rate(value, check_label=None, universe_label=None, **_):
    label = "How often this condition fires"
    what = ("The share of a large, published universe of companies on which this same "
            "condition is true. It is measured offline across four index membership "
            "lists and stamped with the date, not estimated.")
    if not _known(value):
        return unavailable(label, what, "this condition has never been calibrated")
    where = universe_label or "the calibration universe"
    band = _ladder(value, ((0.05, "context"), (0.15, "context"),
                           (0.33, "context"), (None, "context")))
    if value <= 0.05:
        detail = ("Uncommon enough that its presence here says something specific about "
                  "this company.")
    elif value <= 0.15:
        detail = ("Not rare, but far from typical. Worth reading as a fact about this "
                  "company rather than about the market.")
    elif value <= 0.33:
        detail = ("Common enough that it is partly a description of listed equities in "
                  "general. Weigh it as one input, not as an alarm.")
    else:
        detail = ("So common that it is a base condition of this market rather than a "
                  "finding about this company, and the panel presents it as one.")
    return make(
        label=label, what=what,
        reading=f"{_pct(value, 0)} of {where}. {detail}",
        action=("Compare it against the other conditions on the panel before weighting "
                "any of them. A rare condition and a common one presented in identical "
                "type is the mistake this number exists to prevent."),
        band=band, good_direction="none", evidence="strong",
        value_text=_pct(value, 0),
    )


# ============================================================================ #
# Portfolio context — the candidate against what is already owned
#
# THE ONE PLACE THIS APP LETS A MEASUREMENT INFORM POSITION SIZE, and it is
# earned rather than assumed. Everything else here refuses: the ranking's
# information coefficient is indistinguishable from zero, the event study
# returns nulls, and the pre-trade panel deals only in present-tense facts.
# Correlations are different, and the difference was measured before this
# shipped — one year's pairwise correlations rank-correlate 0.50 to 0.65 with
# the next year's across four index universes.
#
# THE READINGS ARE COLOURED, WHICH THE LAST TWO FEATURES WERE NOT. A candidate
# correlating 0.9 with something already held is genuinely unfavourable for the
# person holding it — not a base rate, not provenance, but a fact about their
# book with a direction. That is what `caution` and `poor` are for.
# ============================================================================ #
@metric("holdingCorrelation")
def _holding_correlation(value, ticker=None, overlap=None, **_):
    label = f"Correlation with {ticker}" if ticker else "Correlation with a holding"
    what = ("How closely these two have moved together day to day over the past year. "
            "1.0 would be lockstep, 0 would be unrelated, and negative would mean one "
            "tends to rise when the other falls.")
    if not _known(value):
        return unavailable(label, what, "too few overlapping trading days")
    band = _ladder(value, ((0.3, "good"), (0.6, "fair"), (0.8, "caution"), (None, "poor")))
    reading = f"{_num(value)} over the past year. "
    reading += {
        "good": "These have largely gone their own ways, so owning both is closer to two "
                "positions than one.",
        "fair": "They move together more often than not. Some of what looks like two "
                "positions is one.",
        "caution": "They move together most of the time. Owning both is closer to holding "
                   "a double position in one of them than to being diversified.",
        "poor": "These are effectively the same position with two ticker symbols on it. "
                "Whatever reason you have for owning one applies to the other, and so "
                "does whatever goes wrong.",
    }[band]
    if _known(overlap):
        reading += f" Measured across {int(overlap)} shared trading days."
    return make(label, what, reading,
                "If you would not double the position you already hold, think about "
                "whether adding this one amounts to the same thing.",
                band, "low", evidence="moderate", value_text=_num(value))


@metric("effectiveHoldings")
def _effective_holdings(value, names=None, before=None, gain=None, **_):
    label = "Independent positions"
    what = ("How many genuinely separate bets a set of holdings amounts to. Nine names "
            "that all rise and fall together are closer to one position than to nine, and "
            "this counts them the way their price history says they behave rather than "
            "the way the account statement lists them.")
    if not _known(value):
        return unavailable(label, what, "needs at least two holdings with shared history")
    reading = f"About {_num(value, 1)} independent bets"
    if _known(names):
        reading += f" across {int(names)} holdings"
        crowding = value / names if names else None
        if crowding is not None:
            reading += (". Close to one bet per position, so these are genuinely different "
                        "things." if crowding >= 0.7 else
                        ". Rather fewer than the position count, so some of these are "
                        "the same bet twice." if crowding >= 0.4 else
                        ". Far fewer than the position count — most of this book is one "
                        "bet held several times over.")
    else:
        reading += "."
    # THE SCALE IS ANCHORED ON WHAT AN UNCORRELATED ADDITION WOULD GIVE, which
    # is 1.0 — one more name that shares nothing is one more bet. Testing for
    # `gain <= 0` was the obvious rule and it was wrong: the participation ratio
    # creeps up slightly with ANY extra name, so a fourth clone added to three
    # clones scored a small positive gain and read as "a little more
    # independence" when it is the exact case the panel exists to catch.
    band = "context"
    if _known(gain):
        if gain >= 0.5:
            reading += (f" Adding the candidate takes it from {_num(before, 1)} to "
                        f"{_num(value, 1)} — most of a whole extra bet, so it brings "
                        f"something the book did not have.")
        elif gain >= 0.15:
            reading += (f" Adding the candidate moves it from {_num(before, 1)} to "
                        f"{_num(value, 1)}: some new ground, but well short of the whole "
                        f"extra bet an unrelated name would add.")
        else:
            band = "caution"
            reading += (f" Adding the candidate moves it from {_num(before, 1)} to "
                        f"{_num(value, 1)} — one more name, and next to no more "
                        f"independence, where an unrelated one would add a full bet. That "
                        f"is the shape of buying the fourth copy of a bet you already hold.")
    return make(label, what, reading,
                "Compare it with the number of positions. Where the two diverge, the "
                "account statement is flattering how diversified this is.",
                band, "high", evidence="moderate", value_text=_num(value, 1))


@metric("riskShare")
def _risk_share(value, ticker=None, weight=None, **_):
    label = f"{ticker}'s share of risk" if ticker else "Share of portfolio risk"
    what = ("How much of the portfolio's total price swing this one position accounts for. "
            "Compare it with how much of the money is in it: a position holding a tenth of "
            "the money and a quarter of the risk is the portfolio wearing a smaller name.")
    if not _known(value):
        return unavailable(label, what, "the risk decomposition could not be computed")
    if not _known(weight):
        return make(label, what, f"{_pct(value, 0)} of the portfolio's movement.",
                    CONTEXT_NOT_TRIGGER, "context", "none", evidence="moderate",
                    value_text=_pct(value, 0))
    # A NEGATIVE CONTRIBUTION IS A REAL AND DIFFERENT THING, not a small one.
    # Marginal risk contribution goes below zero when a position moves against
    # the rest of the book, which means it SUBTRACTS from total risk — it is
    # doing the job diversification is supposed to do. The first version put
    # that through the same ladder as everything else and told a reader holding
    # a genuine hedge that risk and money were "broadly in line", which is the
    # least useful thing that could have been said about it. Found by running it
    # against a real book with a defensive name in it.
    if value < 0:
        return make(label, what,
                    f"This position REDUCES the portfolio's movement rather than adding to "
                    f"it, offsetting about {_pct(abs(value), 0)} of what the others "
                    f"contribute, from {_pct(weight, 0)} of the money. It has been moving "
                    f"against the rest of the book — which is what diversification looks "
                    f"like when it is actually working.",
                    "Nothing to fix. Worth knowing before trimming it: a position that "
                    "offsets the others costs more to remove than its size suggests.",
                    "context", "none", evidence="moderate", value_text=_pct(value, 0))

    excess = value - weight
    band = _ladder(excess, ((0.05, "context"), (0.10, "caution"), (None, "poor")))
    reading = (f"{_pct(value, 0)} of the portfolio's movement, from {_pct(weight, 0)} of "
               f"its money. ")
    reading += ("Risk and money are broadly in line here." if band == "context" else
                "It carries noticeably more of the risk than of the money — usually "
                "because it swings harder than the rest, or moves with them." if band == "caution"
                else "It dominates the portfolio's risk out of all proportion to its size. "
                     "A bad stretch for this one name is a bad stretch for the whole book.")
    return make(label, what, reading,
                "Where risk share runs far above money share, the position is bigger than "
                "it looks. That is a reason to check the size, not a reason to sell.",
                band, "low", evidence="moderate", value_text=_pct(value, 0))


def for_portfolio(result: dict) -> dict:
    """Explanations for the portfolio panel.

    Reads the assembled result, like every other `for_*` here, so each sentence
    quotes a figure the panel renders rather than a parallel computation.
    """
    out: dict = {}
    if not result.get("usable"):
        return out

    for pair in result.get("pairs") or []:
        entry = explain("holdingCorrelation", pair.get("correlation"),
                        ticker=pair.get("ticker"), overlap=pair.get("overlapDays"))
        if entry:
            out[f"holdingCorrelation.{pair['ticker']}"] = entry

    independence = result.get("independence") or {}
    entry = explain("effectiveHoldings", independence.get("after"),
                    names=independence.get("withCandidate"),
                    before=independence.get("before"), gain=independence.get("gain"))
    if entry:
        out["effectiveHoldings"] = entry

    for row in ((result.get("contributions") or {}).get("rows") or []):
        entry = explain("riskShare", row.get("riskShare"), ticker=row.get("ticker"),
                        weight=row.get("weight"))
        if entry:
            out[f"riskShare.{row['ticker']}"] = entry
    return out


# ============================================================================ #
# What a flag is worth — the posterior, not the flag
#
# WHY THIS IS `context` AND NOT A WARNING COLOUR
# ----------------------------------------------
# The M-Score itself already carries the alarm: a flagged reading comes back
# `bad`. This number is the QUALIFIER on that alarm, and at every prior anyone
# has published it qualifies downward — an 11% chance of being real is a reason
# to look, not a finding. Colouring it amber as well would count the same fact
# twice and, worse, would make the number that DEFLATES the flag look like a
# second flag.
#
# The clean branch is the mirror hazard and is why the reading always names the
# shift rather than the level. "0.84%" beside a clean score reads as a clean
# bill of health; "2.8% before the test, 0.8% after" reads as what the test
# actually did, which is move a number that was already small.
# ============================================================================ #
@metric("manipulationPosterior")
def _manipulation_posterior(value, flagged=None, prior_text=None, robust=None,
                            partial=False, **_):
    label = "What the flag is worth"
    what = ("How likely it is that a company this screen flags really has manipulated its "
            "earnings. It combines how often the screen catches a manipulator, how often "
            "it cries wolf, and how rare manipulation is to begin with — the third being "
            "the input that decides the answer and the one nobody can measure exactly.")
    if not _known(value):
        return unavailable(label, what,
                           "no M-Score was computed, so there is nothing to condition on")

    base = f" Starting from {prior_text} before the test." if prior_text else ""
    tail = (" Built from fewer than the eight indices the published error rates were "
            "measured on, so read it as indicative." if partial else "")
    if flagged:
        reading = (f"About {_pct(value, 0)} likely to be a real manipulator — so roughly "
                   f"{_pct(1 - value, 0)} of flags like this one are false alarms.{base}"
                   f"{tail}")
        action = ("Treat a flag as a reading assignment, not a finding: go to the cash-flow "
                  "statement and the income statement and see whether profit and cash have "
                  "diverged. If you would not do that work, the flag should not change what "
                  "you do.")
    else:
        reading = (f"No flag, which leaves about {_pct(value, 2)} — down from {prior_text} "
                   f"before the test.{tail} The screen moved a number that was already small, "
                   f"and it tests one specific accrual pattern rather than honesty.")
        action = ("Nothing. A clean M-Score is the absence of one signature, not a clean "
                  "bill of health — a business can be a poor holding for reasons this "
                  "screen has no view on at all.")
    # The robust range is a sentence about what a FLAG is worth. Appended to a
    # clean reading it is a non-sequitur — it answers a question the company in
    # front of the reader did not raise. The panel still prints it in its own
    # paragraph, where it describes the screen rather than this company.
    if robust and flagged:
        reading += f" {robust}"
    return make(label, what, reading, action, "context", "none", evidence="moderate",
                value_text=_pct(value, 0 if flagged else 2))


# ============================================================================ #
# Validation domain — whether a use sits inside the sample a screen was fitted on
#
# WHY THIS IS ALWAYS `context` AND NEVER A COLOUR
# -----------------------------------------------
# Both directions would mislead, and the second is the dangerous one.
#
# OUTSIDE is not a warning. Every practical use of Piotroski, Altman and Beneish
# today is outside their samples, because the samples ended between 1965 and
# 1996. A panel that painted that amber would be crying wolf on all three scores
# for every company, forever, which is how a reader learns to ignore the colour.
#
# INSIDE is not reassurance. A green tick against "period: inside" would say the
# score can be trusted here — a claim about the model's accuracy on this company
# that nothing in this app measures. Absence of a mismatch is not evidence of
# fit, which is the same rule the pre-trade panel is built around.
#
# So the band is `context` in every case and the words carry the difference.
# ============================================================================ #
@metric("validationDomain")
def _validation_domain(value, name=None, sample=None, this_use=None, note=None, **_):
    label = name or "Validation domain"
    what = ("Which companies, in which market and in which years, the published study "
            "behind this score was actually fitted on. A model used outside that sample "
            "is not thereby wrong — it is being asked a question nobody has checked it "
            "against.")
    if not _known(value):
        # No verdict at all is a gap, and gaps take the one band that is never a
        # colour anywhere in this app.
        return unavailable(label, what, "this dimension was not evaluated")
    verdict = str(value).lower() if isinstance(value, str) else ""
    if verdict not in (INSIDE_WORD, OUTSIDE_WORD, UNKNOWN_WORD):
        # The glossary probes every interpreter with numbers. This one takes a
        # verdict string, so the numeric probe falls through to the definition
        # rather than to None — which would fail the manual's build.
        return make(label, what,
                    "This line reports whether one aspect of this company matches the "
                    "study's sample: the years, the market, the kind of business, or the "
                    "size of firm the effect was found in.",
                    "Read it as provenance. It tells you how far the number has been "
                    "carried from where it was tested, not whether the number is right.",
                    "context", "none", evidence="strong")

    where = f"Study sample: {sample}. This company: {this_use}. " if sample and this_use else ""
    heading = {
        INSIDE_WORD: "Inside the study's sample on this axis. ",
        OUTSIDE_WORD: "Outside the study's sample on this axis. ",
        UNKNOWN_WORD: "Cannot be placed against the study's sample on this axis. ",
    }[verdict]
    return make(
        label=label, what=what, reading=heading + where + (note or ""),
        action=("Nothing to act on. This is where the number came from, not a judgement "
                "about the number — and matching the sample would not make the score "
                "reliable here any more than missing it makes it wrong."),
        band="context", good_direction="none", evidence="strong",
        value_text=verdict,
    )


# The three words `screendomain` speaks. Kept here as well so the interpreter
# above does not import that module and create a cycle through `valuation`.
INSIDE_WORD, OUTSIDE_WORD, UNKNOWN_WORD = "inside", "outside", "unknown"


# The sentence the whole panel is designed around. It is a constant rather than
# inline text because `tests/test_pretrade.py` asserts its presence in EVERY
# state, including — especially — the one where nothing fired.
ABSENCE_IS_NOT_EVIDENCE = (
    "An empty panel is not a clean bill of health — only that none of the conditions "
    "this app can test fired."
)

# Appended only when something actually went untested, because a caveat that
# points at an absent section teaches a reader to skip the caveats.
NOTHING_UNTESTED_CLAUSE = (
    " Anything listed as not checked was never evaluated at all."
)


def for_pretrade(flags: Sequence[dict], base_conditions: Sequence[dict],
                 not_checked: Sequence[dict], uncalibrated: Sequence[dict],
                 calibration: Optional[dict] = None) -> dict:
    """The panel's framing, written so silence cannot be misread as a pass.

    DELIBERATELY CONTAINS NO TALLY. Not "two conditions fired", not "seven of
    nine clear" — a count is a composite in the one field everybody reads, and
    three flags on one company are not a worse reading than two on another. The
    per-check firing rates are what make the lines comparable, and they are
    attached to the lines rather than summed.
    """
    # THREE STATES, NOT TWO. The obvious two-branch version ("flags, or nothing")
    # told a company with three demoted base conditions that none of the
    # conditions was true of it, which is false: they were true and had been
    # judged ordinary. Demoting a condition changes how it should be weighed, not
    # whether it applies, and the framing has to keep that distinction.
    if flags:
        framing = (
            "Each condition below is true of this company right now. Beside each one is how "
            "often it is true across a published universe — a common condition describes "
            "the market, not this company."
        )
    elif base_conditions:
        framing = (
            "Nothing unusual fired. The conditions below are true here and true of most of "
            "this market, so they describe the market rather than this company."
        )
    else:
        framing = (
            "None of the conditions this app can test is true of this company right now. "
            "That is a narrower statement than it looks."
        )

    # KEYED, NOT A LIST. The panel needs to place each note under the section it
    # describes, and a list would force the component to identify them by
    # matching on their wording — so rewording a sentence here would silently
    # drop it from the page. A key survives an edit; a substring match does not.
    notes = {}
    if base_conditions:
        notes["base"] = (
            "True here, and true of more than "
            f"{int((calibration or {}).get('baseRateMax', 0.33) * 100)}% of the universe. "
            "Real, but not a finding about this company."
        )
    if not_checked:
        notes["notChecked"] = (
            "Never tested — a refused lens, a missing filing, an estimate the data cannot "
            "resolve. Not tested is not clear."
        )
    if uncalibrated:
        notes["uncalibrated"] = (
            "Testable, but nobody has measured how often they fire. A flag without a base "
            "rate is not readable, so it is withheld."
        )

    # The stamp deliberately does NOT name a universe. Each line carries the
    # group its own percentage is a percentage of, because those differ: a US
    # listing is scored against the US universes and an IDX one against the
    # Indonesian ones. A single scope in the footer would contradict the lines
    # above it on every second ticker.
    stamp = None
    if calibration and calibration.get("measuredOn"):
        stamp = (f"Rates measured {calibration['measuredOn']}, each against the universe "
                 f"named beside it.")

    return {
        "headline": "What would give a careful buyer pause",
        "framing": framing,
        "notes": notes,
        "measuredOn": stamp,
        "caveat": (
            ABSENCE_IS_NOT_EVIDENCE
            + (NOTHING_UNTESTED_CLAUSE if not_checked else "")
            + " None of this is a recommendation."
        ),
    }
