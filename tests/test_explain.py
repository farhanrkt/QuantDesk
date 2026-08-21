"""The plain-language layer, and above all its COLOUR DIRECTION.

The failure this file exists to catch is a metric coloured backwards — a 60%
drawdown shown green because the number is large, or an Ulcer index of 2 shown
red because it is small. Roughly a third of the metrics in the app are "low is
good" and they render in the same grid as the "high is good" ones, so the
mistake is invisible by inspection and obvious to a test.

The tests are written against the PROPERTY, not against a copy of the ladder:
each one asserts that moving the value in the favourable direction never makes
the tone worse. That holds no matter what the thresholds are, so it keeps
working when a threshold is retuned — which is exactly when a hand-copied
expected value would silently stop testing anything.
"""

from __future__ import annotations

from itertools import pairwise

import pytest

from _lib import explain as E

# Ordinal severity, worst to best. Only used by the monotonicity assertions.
TONE_ORDER = {"bad": 0, "warn": 1, "neutral": 2, "good": 3}


def tone_of(key, value, **ctx):
    result = E.explain(key, value, **ctx)
    assert result is not None, f"no interpreter registered for {key!r}"
    return result["tone"]


# ============================================================================ #
# The contract every explanation must satisfy
# ============================================================================ #
# One representative value per registered metric. A metric added without a row
# here fails `test_every_registered_metric_is_exercised`, which is the only
# thing stopping a new number from reaching the screen unexplained.
SAMPLES: dict[str, tuple] = {
    "cagr": (0.16, {}),
    "volatility": (0.28, {}),
    "downsideDeviation": (0.19, {}),
    "sharpe": (0.9, {"riskFree": 0.042}),
    "sortino": (1.35, {"riskFree": 0.042}),
    "calmar": (0.7, {}),
    "var95": (-0.031, {}),
    "cvar95": (-0.048, {"var95": -0.031}),
    "skew": (-0.4, {}),
    "kurtosis": (4.2, {}),
    "positiveDays": (0.53, {}),
    "worstDay": (-0.11, {}),
    "bestDay": (0.09, {}),
    "maxDrawdown": (-0.33, {}),
    "currentDrawdown": (-0.07, {}),
    "timeUnderWaterDays": (354, {}),
    "ulcerIndex": (12.4, {}),
    "maxDrawdownRecoveryDays": (195, {}),
    "hurst": (0.52, {}),
    "momentum12_1": (0.22, {}),
    "roc252": (18.0, {}),
    "roc63": (-4.0, {}),
    "faberDistance": (0.06, {"signal": "invested", "monthsInStance": 7}),
    "fromHigh52w": (-0.08, {}),
    "fromAllTimeHigh": (-0.12, {}),
    "rangePosition": (0.78, {}),
    "regressionSlope": (0.14, {"rSquared": 0.62}),
    "regressionR2": (0.62, {}),
    "relativeExcess": (0.11, {"period": "36m", "benchmark": "^GSPC"}),
    "benchmarkCorrelation": (0.71, {}),
    "rollingWorst": (0.004, {"years": 3, "positiveShare": 1.0}),
    "sma200": (180.0, {"price": 195.0}),
    "sma100": (188.0, {"price": 195.0}),
    "sma50": (191.0, {"price": 195.0}),
    "adx": (27.0, {"plusDi": 30.0, "minusDi": 15.0}),
    "aroon": (85.0, {"aroonDown": 15.0}),
    "rsi": (61.0, {}),
    "stochastic": (72.0, {"stochD": 68.0}),
    "williamsR": (-32.0, {}),
    "cci": (60.0, {}),
    "macd": (1.4, {"macdSignal": 1.1}),
    "bbPercentB": (0.72, {}),
    "bbBandwidth": (0.06, {"squeezePercentile": 0.1}),
    "atrPct": (0.021, {"atr": 4.1}),
    "mfi": (55.0, {}),
    "cmf": (0.09, {}),
    "volumeTrend": (1.3, {}),
    "coppock": (-8.0, {"previous": -11.0}),
    "piotroski": (7, {"maxScore": 9}),
    "altman": (6.4, {}),
    "beneish": (-2.6, {"indicesAvailable": 8, "indicesTotal": 8}),
    "altmanComponent": (0.21, {"part": "ebitToAssets"}),
    "beneishIndex": (1.05, {"part": "DSRI"}),
    "spread": (0.0018, {"source": "Abdi-Ranaldo"}),
    "moveVsSpread": (4.2, {}),
    "yangZhangVol": (0.27, {}),
    "amihud": (0.002, {"currency": "USD"}),
    "anomalyRate": (0.031, {"totalDays": 500}),
    "qValue": (0.02, {}),
    "cusumEpisode": (None, {"direction": "Accumulation", "days": 27, "avgRvol": 1.04}),
    "flowBias": ("Accumulation", {"days": 10, "count": 3}),
    "upside": (-0.64, {"engine": "DCF", "price_label": "$311.30", "fair_label": "$112.00"}),
    "probUndervalued": (0.04, {"iterations": 10000}),
    "terminalShare": (0.72, {}),
    "discountRate": (0.089, {"rate_name": "Cost of equity", "risk_free": 0.042, "beta": 1.15}),
    "valuationSpread": (0.55, {"p25_label": "$96", "p75_label": "$150"}),
}


def test_every_registered_metric_is_exercised():
    """A metric with no sample here has never been checked for direction."""
    assert set(E._REGISTRY) == set(SAMPLES), (
        "add the new metric to SAMPLES so its direction and prose get tested"
    )


@pytest.mark.parametrize("key", sorted(SAMPLES))
def test_explanation_answers_all_three_questions(key):
    value, ctx = SAMPLES[key]
    result = E.explain(key, value, **ctx)
    assert result is not None
    assert isinstance(result["label"], str) and result["label"].strip()
    # The three questions the brief demands. A one-liner cannot answer any of
    # them, so the length floor is what stops a placeholder shipping.
    for field in ("what", "reading", "action"):
        assert isinstance(result[field], str) and len(result[field]) > 30, (
            f"{key}: {field} is missing or too short to be an explanation"
        )
    assert result["tone"] in ("good", "bad", "warn", "neutral", "none")
    assert result["goodDirection"] in ("high", "low", "none")
    assert result["band"] in E.TONE_FOR_BAND


@pytest.mark.parametrize("key", sorted(SAMPLES))
def test_reading_quotes_the_actual_value(key):
    """The reading must interpret THIS number, not lecture about the concept.

    Enforced structurally: every interpreter fills `valueText` with the number
    as the panel will show it, and that string has to appear in the reading —
    which is only possible if the sentence was written around the value.
    """
    value, ctx = SAMPLES[key]
    result = E.explain(key, value, **ctx)
    if result["band"] == "unavailable" or result["valueText"] is None:
        return
    # Numbers are rendered with separators and signs; compare on the digits.
    digits = "".join(c for c in result["valueText"] if c.isdigit())
    if digits:
        assert digits in "".join(c for c in result["reading"] if c.isdigit()), (
            f"{key}: reading does not contain the value it is meant to interpret"
        )


@pytest.mark.parametrize("key", sorted(SAMPLES))
def test_missing_values_never_get_a_colour(key):
    """An absent number must never be rendered as good or bad news."""
    _value, ctx = SAMPLES[key]
    if key in ("cusumEpisode", "maxDrawdownRecoveryDays"):
        # These two READ their missing case: "no regime detected" and "never
        # recovered" are findings, not gaps, so they are exempt by design.
        return
    result = E.explain(key, None, **ctx)
    assert result["band"] == "unavailable"
    assert result["tone"] == "none"


# ============================================================================ #
# Direction — the whole reason this module is in Python
# ============================================================================ #
def _monotone(key, values, ctx=None, improving=True):
    """Tone must never get worse as `values` moves in the favourable direction."""
    ctx = ctx or {}
    tones = [TONE_ORDER[tone_of(key, v, **ctx)] for v in values]
    ordered = all(a <= b for a, b in pairwise(tones))
    assert ordered, f"{key}: tone went backwards across {values} -> {tones}"


HIGHER_IS_BETTER = {
    "upside": [-0.50, -0.20, 0.0, 0.20, 0.50],
    "probUndervalued": [0.05, 0.30, 0.60, 0.90],
    "cagr": [-0.20, -0.02, 0.03, 0.08, 0.15, 0.30],
    "sharpe": [-0.4, 0.2, 0.7, 1.4, 2.5],
    "sortino": [-0.4, 0.2, 0.7, 1.4, 2.5],
    "calmar": [-0.3, 0.2, 0.7, 1.5, 4.0],
    "piotroski": [0, 2, 5, 7, 9],
    "altman": [2.0, 4.0, 5.0, 7.0],
    "rangePosition": [0.05, 0.30, 0.60, 0.90],
    "fromHigh52w": [-0.70, -0.40, -0.20, -0.10, -0.01],
    "fromAllTimeHigh": [-0.80, -0.50, -0.30, -0.10, -0.01],
    "moveVsSpread": [0.5, 1.5, 3.0, 9.0],
}

LOWER_IS_BETTER = {
    "terminalShare": [0.95, 0.80, 0.65, 0.40],
    "valuationSpread": [1.60, 0.90, 0.45, 0.15],
    # The list that catches the backwards-colour bug. Values run BEST to WORST,
    # so the tone must still be non-increasing in quality — the assertion is
    # identical, which is the point: direction lives in the ladder, not here.
    "volatility": [0.60, 0.42, 0.30, 0.20, 0.10],
    "downsideDeviation": [0.50, 0.33, 0.24, 0.16, 0.08],
    "maxDrawdown": [-0.75, -0.55, -0.40, -0.25, -0.08],
    "ulcerIndex": [45.0, 25.0, 15.0, 7.0, 2.0],
    "timeUnderWaterDays": [900, 600, 300, 120, 20],
    "atrPct": [0.10, 0.055, 0.032, 0.02, 0.008],
    "spread": [0.035, 0.015, 0.006, 0.002, 0.0004],
    "var95": [-0.09, -0.05, -0.03, -0.015],
    "cvar95": [-0.12, -0.07, -0.04, -0.02],
    "worstDay": [-0.30, -0.15, -0.09, -0.04],
    "beneish": [-1.0, -2.0, -3.0],
    "qValue": [0.5, 0.15, 0.01],
    "maxDrawdownRecoveryDays": [1500, 800, 300, 60],
    "amihud": [0.20, 0.02, 0.001],
}


@pytest.mark.parametrize("key", sorted(HIGHER_IS_BETTER))
def test_higher_is_better_metrics_improve_upward(key):
    _monotone(key, HIGHER_IS_BETTER[key])
    assert E.explain(key, HIGHER_IS_BETTER[key][-1])["goodDirection"] == "high"


@pytest.mark.parametrize("key", sorted(LOWER_IS_BETTER))
def test_low_is_good_metrics_are_not_coloured_backwards(key):
    _monotone(key, LOWER_IS_BETTER[key])
    assert E.explain(key, LOWER_IS_BETTER[key][-1])["goodDirection"] == "low", (
        f"{key} is a low-is-good metric but declares goodDirection 'high'"
    )


def test_the_extremes_land_where_a_person_would_put_them():
    """Spot checks in ordinary language, independent of the ladders above."""
    assert tone_of("maxDrawdown", -0.72) == "bad"          # lost three-quarters
    assert tone_of("maxDrawdown", -0.06) == "good"         # barely a dip
    assert tone_of("ulcerIndex", 2.0) == "good"            # LOW ulcer is good
    assert tone_of("ulcerIndex", 45.0) == "bad"
    assert tone_of("volatility", 0.08) == "good"           # LOW vol is good
    assert tone_of("volatility", 0.70) == "bad"
    assert tone_of("sortino", 2.6) == "good"
    assert tone_of("sortino", -0.3) == "bad"
    assert tone_of("beneish", -0.9) == "bad"               # HIGH M-score is bad
    assert tone_of("beneish", -3.1) == "good"
    assert tone_of("altman", 2.0) == "bad"                 # LOW Z-score is bad
    assert tone_of("piotroski", 9, maxScore=9) == "good"
    assert tone_of("piotroski", 1, maxScore=9) == "bad"


def test_a_valuation_gap_is_never_stated_as_a_price_target():
    """The failure mode this lens is most prone to.

    A DCF is an opinion with arithmetic attached. Every reading on the panel has
    to point back at an assumption rather than forward at a price, and a very
    large gap has to say out loud that it is more likely a broken input than a
    discovery.
    """
    huge = E.explain("upside", 1.8, price_label="$50", fair_label="$140")
    assert "assumptions are wrong" in huge["reading"]
    assert "range, not a target" in huge["action"]

    prob = E.explain("probUndervalued", 0.97, iterations=10000)
    assert "NOT a probability that the price will rise" in prob["reading"]


def test_terminal_value_share_warns_when_it_dominates():
    """80% of the answer coming from a perpetuity guess is not a good reading."""
    assert tone_of("terminalShare", 0.90) == "bad"
    assert tone_of("terminalShare", 0.40) == "good"


def test_beneish_and_altman_point_opposite_ways():
    """The pair most likely to be coloured identically by mistake.

    Both are 'accounting quality' scores on the quality panel, but Altman
    rewards a HIGH number and Beneish punishes one. Colouring them the same way
    would tell a reader that a manipulation flag is good news.
    """
    assert E.explain("altman", 7.0)["goodDirection"] == "high"
    assert E.explain("beneish", -3.0)["goodDirection"] == "low"
    assert tone_of("altman", 7.0) == "good"
    assert tone_of("beneish", -0.5) == "bad"


def test_hurst_near_a_random_walk_is_a_warning_not_a_verdict():
    """The honesty check: a coin-flip series must not read as neutral-fine."""
    assert tone_of("hurst", 0.50) == "warn"
    assert "noise" in E.explain("hurst", 0.50)["reading"]
    assert tone_of("hurst", 0.68) == "good"
    assert "reverse" in E.explain("hurst", 0.30)["reading"].lower()


def test_overbought_is_a_caution_never_a_verdict():
    """RSI 75 must not render as 'bad' — that is a level, not a judgement."""
    assert tone_of("rsi", 75) == "warn"
    assert tone_of("rsi", 25) == "warn"
    assert tone_of("rsi", 50) == "neutral"


def test_weak_signals_are_labelled_weak():
    """Evidence strength has to differ, or the field is decoration."""
    assert E.explain("momentum12_1", 0.2)["evidence"] == "strong"
    assert E.explain("rsi", 55)["evidence"] == "weak"
    assert E.explain("stochastic", 55)["evidence"] == "weak"
    assert E.explain("maxDrawdown", -0.3)["evidence"] == "strong"


def test_unknown_metric_returns_none_rather_than_guessing():
    assert E.explain("no_such_metric", 1.0) is None


def test_make_rejects_an_unknown_band():
    with pytest.raises(ValueError):
        E.make("x", "what", "reading", "action", band="excellentish")


# ============================================================================ #
# The plain-English story
# ============================================================================ #
def _block(**overrides):
    base = {
        "risk": {"usable": True, "cagr": 0.16, "observations": 5 * 252,
                 "sortino": 1.35, "riskFree": 0.042},
        "drawdown": {"usable": True, "maxDrawdown": -0.33,
                     "maxDrawdownRecoveryDays": 195, "timeUnderWaterDays": 354,
                     "currentDrawdown": -0.01, "maxDrawdownRecovered": "2021-01-05",
                     "ulcerIndex": 9.0},
        "rollingReturns": [
            {"years": 1, "worst": -0.30, "positiveShare": 0.7, "windows": 1000},
            {"years": 3, "worst": 0.004, "positiveShare": 1.0, "windows": 500},
        ],
        "relativeStrength": {"usable": True, "benchmark": "^GSPC",
                             "periods": {"36m": {"excess": 0.22}}, "correlation": 0.7},
        "position": {"usable": True, "fromHigh52w": -0.03},
        "faber": {"usable": True, "signal": "invested"},
        "hurst": 0.62,
    }
    base.update(overrides)
    return base


def test_story_states_the_numbers_the_tables_state():
    """The paragraph and the table beside it must describe the same history."""
    story = E.long_horizon_story("AAPL", _block())
    text = " ".join(story["paragraphs"])
    assert "AAPL" in text
    assert "16%" in text                      # the CAGR
    assert "33%" in text                      # the worst fall
    assert "195 days" in text                 # the recovery
    assert "354-day" in text                  # the underwater stretch
    assert "every single time" in text        # 100% positive 3-year windows
    assert "break-even" in text               # worst 3y window ~0%


def test_story_says_when_the_trend_is_noise():
    story = E.long_horizon_story("XYZ", _block(hurst=0.50))
    assert "random walk" in " ".join(story["paragraphs"])


def test_story_survives_a_nearly_empty_block():
    """A ticker with almost no history must lose sentences, not the summary."""
    story = E.long_horizon_story("NEW", {"risk": {}, "drawdown": {},
                                         "rollingReturns": [], "position": {}})
    assert story["paragraphs"]                # the honesty paragraph always runs
    assert "price history alone" in story["paragraphs"][-1]


def test_story_admits_a_loss_rather_than_softening_it():
    story = E.long_horizon_story("BAD", _block(
        risk={"usable": True, "cagr": -0.11, "observations": 5 * 252},
        relativeStrength={"usable": True, "benchmark": "^GSPC",
                          "periods": {"36m": {"excess": -0.40}}}))
    text = " ".join(story["paragraphs"])
    assert "LOST" in text
    assert "an index fund would have done better" in text


def test_story_reports_an_unrecovered_fall_as_such():
    story = E.long_horizon_story("STILLDOWN", _block(
        drawdown={"usable": True, "maxDrawdown": -0.62, "maxDrawdownRecovered": None,
                  "maxDrawdownRecoveryDays": None, "timeUnderWaterDays": 900,
                  "currentDrawdown": -0.55}))
    text = " ".join(story["paragraphs"])
    assert "still not climbed back" in text
    assert "55% below its best price" in text


def test_simple_mode_shows_a_handful_of_metrics_that_all_exist():
    """Simple mode is only useful if its keys resolve on a real payload."""
    story = E.long_horizon_story("AAPL", _block())
    assert 4 <= len(story["simpleMetrics"]) <= 7
    built = E.for_long_term(_block(), ticker="AAPL", risk_free=0.042)
    for key in story["simpleMetrics"]:
        assert key in built, f"Simple mode names {key!r} but nothing builds it"


def test_for_long_term_covers_the_panel_and_nothing_is_uncoloured():
    built = E.for_long_term(_block(), ticker="AAPL", risk_free=0.042)
    for key in ("cagr", "maxDrawdown", "ulcerIndex", "sortino", "hurst",
                "timeUnderWaterDays", "relativeExcess.36m", "rollingWorst.3"):
        assert key in built, f"{key} has no explanation"
        assert built[key]["tone"] in ("good", "bad", "warn", "neutral", "none")
