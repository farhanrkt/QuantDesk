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
    "amihud": (2e-4, {"currency": "USD"}),
    "anomalyRate": (0.031, {"totalDays": 500}),
    "qValue": (0.02, {}),
    "cusumEpisode": (None, {"direction": "Accumulation", "days": 27,
                            "avgRvol": 1.04, "ongoing": True}),
    "flowBias": ("Accumulation", {"days": 10, "count": 3}),
    "upside": (-0.64, {"engine": "DCF", "price_label": "$311.30", "fair_label": "$112.00"}),
    "probUndervalued": (0.04, {"iterations": 10000}),
    "terminalShare": (0.72, {}),
    "impliedGrowth": (0.18, {"assumedGrowth": 0.10, "engine": "DCF"}),
    "discountRate": (0.089, {"rate_name": "Cost of equity", "risk_free": 0.042, "beta": 1.15}),
    "valuationSpread": (0.55, {"p25_label": "$96", "p75_label": "$150"}),
    "riskReward": (2.4, {"target_label": "Next resistance (3 prior turns)"}),
    "stopDistance": (0.03, {"atr_multiple": 1.8, "basis": "structure"}),
    "positionShare": (0.33, {"risk_budget": 0.01, "uncapped": 0.33}),
    "distanceToLevel": (0.07, {"side": "resistance", "touches": 3, "price_text": "$232.06"}),
    "vwapDistance": (0.12, {"anchor": "52-week low"}),
    "squeezePercentile": (0.08, {"fired": None}),
    "volumeRatio": (1.7, {}),
    "divergenceState": (1, {"kind": "bearish"}),
    "gapState": (0.038, {"direction": "up", "size_atr": 1.4}),
    "compositeRank": (78.0, {"coverage": 1.0, "available": 7, "total": 7}),
    "signalRank": (93.0, {"signal": "lowVolatility", "raw": 0.14, "raw_text": "14.0%"}),
    "signalOverlap": (0.98, {"a": "Momentum", "b": "Trend"}),
    "checkFiringRate": (0.08, {"universe_label": "4 index universes"}),
    "manipulationPosterior": (0.113, {"flagged": True, "prior_text": "2.8%"}),
    "holdingCorrelation": (0.82, {"ticker": "MSFT", "overlap": 251}),
    "effectiveHoldings": (3.1, {"names": 9, "before": 3.0, "gain": 0.1}),
    "riskShare": (0.24, {"ticker": "NVDA", "weight": 0.10}),
    "validationDomain": ("outside", {"name": "Period", "sample": "US filings, 1976-1996",
                                     "this_use": "2025 filings",
                                     "note": "29 years after the sample ends."}),
    "sharedDirection": (0.54, {"market_share": 0.09, "weeks": 72, "holdings": 4}),
    "sharedDriver": (0.54, {"matches": [{"key": "oil", "label": "the energy complex",
                                         "correlation": 0.50, "overlapWeeks": 72}],
                            "tested": [{"key": "oil", "label": "the energy complex",
                                        "available": True, "correlation": 0.50}],
                            "ambiguous": False, "name_at": 0.45}),
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
    if key in ("cusumEpisode", "maxDrawdownRecoveryDays", "divergenceState", "gapState",
               "sharedDriver"):
        # These READ their missing case rather than lacking data: "no regime
        # detected", "never recovered", "price and momentum agree", "no unfilled
        # gap" are findings, not gaps, so they are exempt by design.
        #
        # `sharedDriver` is the same shape and the most load-bearing of them.
        # "Nothing tested explained what these holdings share" is the finding,
        # and it is the one place constraint 3 is easiest to break — an empty
        # result here reads as "diversified" unless the words deny it, which is
        # exactly what that branch does. Its genuinely-absent case, where no
        # reference had enough overlapping history to correlate at all, still
        # returns `unavailable`, and `test_shared_driver_*` below pins both.
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
    "compositeRank": [8.0, 30.0, 55.0, 80.0, 96.0],
    "signalRank": [8.0, 30.0, 55.0, 80.0, 96.0],
    "riskReward": [0.6, 1.2, 2.0, 4.0],
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
    "signalOverlap": [0.95, 0.60, 0.20],
    "terminalShare": [0.95, 0.80, 0.65, 0.40],
    "impliedGrowth": [0.50, 0.25, 0.15, 0.06, 0.01],
    "valuationSpread": [1.60, 0.90, 0.45, 0.15],
    # The list that catches the backwards-colour bug. Values run BEST to WORST,
    # so the tone must still be non-increasing in quality — the assertion is
    # identical, which is the point: direction lives in the ladder, not here.
    "volatility": [0.60, 0.42, 0.30, 0.20, 0.10],
    "downsideDeviation": [0.50, 0.33, 0.24, 0.16, 0.08],

    "ulcerIndex": [45.0, 25.0, 15.0, 7.0, 2.0],
    "timeUnderWaterDays": [900, 600, 300, 120, 20],
    "atrPct": [0.10, 0.055, 0.032, 0.02, 0.008],
    "spread": [0.035, 0.015, 0.006, 0.002, 0.0004],
    "beneish": [-1.0, -2.0, -3.0],
    "qValue": [0.5, 0.15, 0.01],
    "maxDrawdownRecoveryDays": [1500, 800, 300, 60],
    "amihud": [0.20, 0.02, 0.001, 8e-7],
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


# The five metrics whose DISPLAYED value is negative. They belong in neither
# list above: the ladder improves as the number rises toward zero, so a reader
# is looking at -33% and the arrow has to say "higher is better".
NEGATIVE_SCALE = {
    "maxDrawdown": [-0.75, -0.55, -0.40, -0.25, -0.08],
    "currentDrawdown": [-0.60, -0.35, -0.18, -0.05],
    "var95": [-0.09, -0.05, -0.03, -0.015],
    "cvar95": [-0.12, -0.07, -0.04, -0.02],
    "worstDay": [-0.30, -0.15, -0.09, -0.04],
}


@pytest.mark.parametrize("key", sorted(NEGATIVE_SCALE))
def test_metrics_shown_as_negative_numbers_point_their_arrow_upward(key):
    """The arrow has to agree with the ladder, and for these five it did not.

    A maximum drawdown reaches the panel as "-33%" and improves toward zero, so
    the honest arrow reads "higher is better". All five declared "low", which
    renders a down arrow labelled "lower is better" underneath a negative
    number — telling a reader that -60% is the better outcome. The colour was
    right the whole time; only the arrow disagreed, and the old test could not
    see it because it asserted the label against a hand-kept list rather than
    against the ladder.
    """
    _monotone(key, NEGATIVE_SCALE[key])
    assert E.explain(key, NEGATIVE_SCALE[key][-1])["goodDirection"] == "high"


def test_no_metric_declares_a_direction_its_own_ladder_contradicts():
    """The check that would have caught the above, derived rather than listed.

    For every metric with a stated direction, sweep its own sample values and
    require the tone to move the way the direction claims. Nothing here is
    maintained by hand, so a new metric is covered the day it is added.
    """
    order = {"bad": 0, "warn": 1, "neutral": 2, "good": 3}
    problems = []
    for key, values in {**HIGHER_IS_BETTER, **LOWER_IS_BETTER, **NEGATIVE_SCALE}.items():
        _value, ctx = SAMPLES[key]
        readings = [E.explain(key, v, **ctx) for v in values]
        direction = readings[-1]["goodDirection"]
        if direction == "none":
            continue
        tones = [order[r["tone"]] for r in readings if r["band"] != "unavailable"]
        improving = all(a <= b for a, b in pairwise(tones))
        if not improving:
            problems.append(f"{key}: tone does not improve across its own list")
            continue
        # The list runs worst-to-best, so the direction must match which end of
        # the numeric range "best" sits at.
        rises = values[-1] > values[0]
        expected = "high" if rises else "low"
        if direction != expected:
            problems.append(
                f"{key}: improves toward {values[-1]} (so {expected!r}) but "
                f"declares {direction!r} — the arrow contradicts the colour")
    assert not problems, "\n".join(problems)


def test_a_finished_flow_regime_is_still_explained():
    """The panel shows its regimes table whenever any episode exists.

    Emitting this only for an ONGOING regime left a ticker with two finished
    ones showing the table with nothing saying what a regime is.
    """
    ended = E.explain("cusumEpisode", None, direction="Distribution", days=31,
                      avgRvol=1.2, ongoing=False)
    assert ended["band"] != "unavailable"
    assert "since ended" in ended["reading"]
    ongoing = E.explain("cusumEpisode", None, direction="Accumulation", days=27,
                        avgRvol=1.04, ongoing=True)
    assert "ongoing" in ongoing["reading"].lower()
    assert "since ended" not in ongoing["reading"]


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


def test_a_thin_reward_for_the_risk_is_not_dressed_up():
    """0.8:1 has to read as bad, whatever the setup around it says."""
    assert tone_of("riskReward", 0.8) == "bad"
    assert "risking more than you stand to make" in E.explain("riskReward", 0.8)["reading"]
    assert tone_of("riskReward", 3.0) == "good"


def test_a_real_quantity_is_never_formatted_into_nothing():
    """Amihud on a mega-cap is about 8e-7 as a fraction-per-million.

    Printed as a percentage that rounds to the literal string "0.00%" — a real
    measurement rendered into a zero. Inverting it gives the same fact in money:
    what it costs to move the price one percent.
    """
    mega_cap = E.explain("amihud", 8.17e-07, currency="USD")
    assert mega_cap["valueText"] == "$12.2bn"
    assert "0.00" not in mega_cap["valueText"]
    thin = E.explain("amihud", 2e-2, currency="IDR")
    assert thin["valueText"].startswith("Rp")
    # A deeper book must always read as a larger sum, and the unit must scale.
    deep = E.explain("amihud", 1e-8, currency="USD")
    shallow = E.explain("amihud", 1e-3, currency="USD")
    assert deep["valueText"].endswith("tn")
    assert shallow["valueText"].endswith("m")
    assert E.explain("amihud", 1e-7, currency="USD")["valueText"].endswith("bn")


def test_a_percentile_is_never_shown_as_a_bare_number_under_a_directional_label():
    """The tile that said "How quiet it has gone: 94%" and meant *very lively*.

    A percentile carries no direction of its own, so pairing one with a label
    that does ("how quiet") inverts the reading for anyone who scans the tile
    without opening the explanation. The displayed value now leads with the
    word, and the word has to match the band.
    """
    lively = E.explain("squeezePercentile", 0.94)
    assert lively["valueText"].startswith("Volatile")
    quiet = E.explain("squeezePercentile", 0.05)
    assert quiet["valueText"].startswith("Squeezed")
    ordinary = E.explain("squeezePercentile", 0.50)
    assert ordinary["valueText"].startswith("Ordinary")
    # And the label itself must not smuggle a direction back in.
    assert "quiet" not in lively["label"].lower()


def test_a_volatility_squeeze_refuses_to_predict_a_direction():
    """The claim most write-ups smuggle in, and the one the measure cannot make."""
    reading = E.explain("squeezePercentile", 0.05)["reading"]
    assert "which direction" in reading
    action = E.explain("squeezePercentile", 0.05)["action"]
    assert "never a direction forecast" in action


def test_stop_distance_is_deliberately_non_directional():
    """Tighter is not better.

    A tight stop risks less per share and gets hit by ordinary noise more often;
    a wide one is the reverse. Grading it high-is-good or low-is-good would
    assert something the measure does not support, so it grades neither.
    """
    assert E.explain("stopDistance", 0.03, atr_multiple=1.8,
                     basis="structure")["goodDirection"] == "none"


def test_a_volatility_placed_stop_is_graded_below_a_structural_one():
    structural = E.explain("stopDistance", 0.06, atr_multiple=2.0, basis="structure")
    volatility = E.explain("stopDistance", 0.06, atr_multiple=2.0, basis="volatility")
    assert TONE_ORDER[structural["tone"]] > TONE_ORDER[volatility["tone"]]


def _hurst_ctx(value, observations=1260):
    """The reading `indicators.hurst_estimate` would produce for that value."""
    stderr = 1.92 / (observations ** 0.5)
    low, high = 0.5 - 2 * stderr, 0.5 + 2 * stderr
    verdict = ("persistent" if value >= high else "meanReverting" if value <= low
               else "indistinguishable")
    return {"stderr": stderr, "verdict": verdict, "low": low, "high": high,
            "observations": observations}


def test_hurst_near_a_random_walk_is_a_warning_not_a_verdict():
    """The honesty check: a coin-flip series must not read as neutral-fine."""
    assert tone_of("hurst", 0.50, **_hurst_ctx(0.50)) == "warn"
    assert "noise" in E.explain("hurst", 0.50, **_hurst_ctx(0.50))["reading"]
    assert tone_of("hurst", 0.72, **_hurst_ctx(0.72)) == "good"
    assert "reverse" in E.explain("hurst", 0.25, **_hurst_ctx(0.25))["reading"].lower()


def test_hurst_reports_its_own_error_bar():
    """The point estimate alone overstates what this measure can support."""
    reading = E.explain("hurst", 0.62, **_hurst_ctx(0.62))
    assert "±" in reading["reading"]


def test_a_hurst_verdict_needs_to_clear_its_own_uncertainty():
    """0.62 is 'trending' on ten years of data and 'cannot tell' on two.

    Same number, different amount of evidence behind it. The fixed 0.45-0.55
    band this used to be read against ignored that entirely and called a
    genuine random walk trending a third of the time on the app's own default
    range.
    """
    long_history = E.explain("hurst", 0.62, **_hurst_ctx(0.62, observations=2520))
    short_history = E.explain("hurst", 0.62, **_hurst_ctx(0.62, observations=500))
    assert "trending" not in short_history["reading"]
    assert "cannot tell" in short_history["reading"]
    assert "have something" in long_history["reading"]


def test_a_short_hurst_sample_says_it_is_short():
    reading = E.explain("hurst", 0.52, **_hurst_ctx(0.52, observations=400))["reading"]
    assert "400 days" in reading
    assert "widen the range" in reading


def test_overbought_is_a_caution_never_a_verdict():
    """RSI 75 must not render as 'bad' — that is a level, not a judgement."""
    assert tone_of("rsi", 75) == "warn"
    assert tone_of("rsi", 25) == "warn"
    assert tone_of("rsi", 50) == "neutral"


def test_a_ranking_percentile_always_says_which_universe_it_is_relative_to():
    """A cross-sectional rank supports one claim and it has to be stated.

    "82" looks like a score on some absolute scale. It is a position inside one
    scan on one date, and a name at the top of a falling list is still falling.
    """
    for value in (12.0, 55.0, 94.0):
        reading = E.explain("compositeRank", value)["reading"]
        assert "this scan" in reading
        assert "WITHIN this universe" in reading


def test_a_low_is_good_ranking_signal_says_so_in_words():
    """The percentile already flips the direction; the prose has to admit it."""
    steadiness = E.explain("signalRank", 93.0, signal="lowVolatility",
                           raw=0.14, raw_text="14.0%")
    assert "LOWER raw number ranks better" in steadiness["reading"]
    momentum = E.explain("signalRank", 93.0, signal="momentum",
                         raw=0.4, raw_text="+40.0%")
    assert "LOWER raw number ranks better" not in momentum["reading"]


def test_heavily_overlapping_signals_are_flagged_as_double_counting():
    duplicated = E.explain("signalOverlap", 0.95, a="Momentum", b="Trend")
    assert duplicated["tone"] == "warn"
    assert "more than once" in duplicated["reading"]
    independent = E.explain("signalOverlap", 0.15, a="Momentum", b="Money flow")
    assert independent["tone"] == "good"


def test_short_horizon_signals_are_never_graded_strong():
    """The whole shorter-horizon section rests on thin evidence and must say so."""
    for key in ("squeezePercentile", "divergenceState", "gapState", "distanceToLevel",
                "vwapDistance"):
        value, ctx = SAMPLES[key]
        assert E.explain(key, value, **ctx)["evidence"] == "weak"


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
        "hurstReading": {"hurst": 0.62, "stderr": 0.05, "observations": 1260,
                         "randomWalkLow": 0.40, "randomWalkHigh": 0.60,
                         "verdict": "persistent"},
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


def test_the_story_never_summarises_a_horizon_that_was_not_measured():
    """Unsupported horizons are now REPORTED rather than dropped, so the presence
    of a 3-year row stopped meaning there is a 3-year answer. A summary that
    picked it up by key would tell a reader the stock made money in every window
    it never measured."""
    story = E.long_horizon_story("NEW", _block(rollingReturns=[
        {"years": 1, "usable": True, "worst": -0.30, "positiveShare": 0.7, "windows": 900},
        {"years": 3, "usable": False, "windows": 0, "reason": "Needs about 776 days."},
    ]))
    text = " ".join(story["paragraphs"])
    assert "held for 1 years" in text or "held for 1 year" in text, text
    assert "held for 3" not in text


def test_simple_mode_gets_a_measured_horizon_not_an_empty_card():
    """The bare `rollingWorst` key is what Simple mode renders. Preferring the
    3-year row by key alone would hand it a 'needs more history' card while a
    perfectly good 1-year answer sat beside it."""
    out = E.for_long_term(_block(rollingReturns=[
        {"years": 1, "usable": True, "worst": -0.30, "positiveShare": 0.7, "windows": 900},
        {"years": 3, "usable": False, "windows": 0, "reason": "Needs about 776 days."},
    ]))
    assert out["rollingWorst"]["band"] != "unavailable"
    assert out["rollingWorst"] is out["rollingWorst.1"]
    # ...and the unsupported horizon still gets its own entry, quoting the fix.
    assert out["rollingWorst.3"]["band"] == "unavailable"
    assert "Needs about 776 days" in out["rollingWorst.3"]["reading"]


def test_an_unsupported_horizon_never_reads_as_a_result():
    unavailable = E.explain("rollingWorst", None, years=5,
                            reason="Needs about 1,280 trading days of history.")
    assert unavailable["band"] == "unavailable"
    assert unavailable["tone"] == "none"
    assert "1,280" in unavailable["reading"]


def test_story_says_when_the_trend_is_noise():
    story = E.long_horizon_story("XYZ", _block(
        hurst=0.50,
        hurstReading={"hurst": 0.50, "stderr": 0.05, "observations": 1260,
                      "randomWalkLow": 0.40, "randomWalkHigh": 0.60,
                      "verdict": "indistinguishable"}))
    assert "random walk" in " ".join(story["paragraphs"])


def test_story_survives_a_nearly_empty_block():
    """A ticker with almost no history must lose sentences, not the summary."""
    story = E.long_horizon_story("NEW", {"risk": {}, "drawdown": {},
                                         "rollingReturns": [], "position": {}})
    assert story["paragraphs"]                # the honesty paragraph always runs
    # The guarantee is that the closing paragraph says this lens knows nothing
    # about the business. Wording shortened in the v2 copy pass.
    assert "knows anything about the business" in story["paragraphs"][-1]


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
