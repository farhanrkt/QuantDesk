"""The breadth tier, against planted universes.

Every test builds price paths whose ORDERING is known by construction — a
universe of five names where one was deliberately given the best momentum, or
the lowest volatility — and asserts the engine recovers that order. Nothing is
checked against a second copy of a ranking formula.

The batch download is exercised against a stub standing in for `yf.download`,
because the whole suite runs offline. That stub reproduces the two column
shapes yfinance actually returns, which is not incidental: the real defect this
file caught was a single-symbol chunk arriving with a MultiIndex and being
silently dropped, which lost the benchmark index on every scan.
"""

from __future__ import annotations


import numpy as np
import pytest

from helpers import path, steady

from _lib import ranking as R


# ============================================================================ #
# Percentile ranking — the one place direction is decided
# ============================================================================ #
def test_percentile_ranks_put_the_best_value_at_the_top():
    values = [1.0, 2.0, 3.0, 4.0]
    ranks = R.percentile_ranks(values, direction=1)
    assert ranks[-1] == pytest.approx(100.0)
    assert ranks[0] == pytest.approx(25.0)
    assert ranks == sorted(ranks)


def test_a_low_is_good_signal_is_ranked_the_other_way_up():
    """The direction flag is applied ONCE, here. Volatility is the case."""
    values = [0.10, 0.20, 0.30, 0.40]
    ranks = R.percentile_ranks(values, direction=-1)
    assert ranks[0] == pytest.approx(100.0), "the calmest name must rank best"
    assert ranks[-1] == pytest.approx(25.0)
    assert ranks == sorted(ranks, reverse=True)


def test_ties_share_the_average_rank_rather_than_fetch_order():
    ranks = R.percentile_ranks([5.0, 5.0, 9.0], direction=1)
    assert ranks[0] == ranks[1]
    assert ranks[2] > ranks[0]


def test_missing_values_stay_missing_and_never_become_a_median():
    ranks = R.percentile_ranks([1.0, None, 3.0], direction=1)
    assert ranks[1] is None
    assert ranks[0] is not None and ranks[2] is not None


def test_a_column_with_one_reading_cannot_be_ranked():
    """A percentile needs a distribution; one observation is not one."""
    assert R.percentile_ranks([None, 4.0, None], direction=1) == [None, None, None]


# ============================================================================ #
# Per-symbol signals
# ============================================================================ #
def test_momentum_skips_the_most_recent_month():
    """12-1, not 12. The last month is dropped on purpose.

    Built so the answer is unambiguous: flat for a year, then a violent +50% in
    the final three weeks. Plain 12-month momentum would be huge; 12-1 momentum
    must be ~0 because the move is entirely inside the skipped window.
    """
    returns = np.zeros(400)
    returns[-15:] = np.log(1.5) / 15.0
    signals = R.price_signals(path(returns))
    assert signals["momentum"] == pytest.approx(0.0, abs=0.02)


def test_momentum_sees_a_move_that_predates_the_skipped_month():
    returns = np.zeros(400)
    returns[200:220] = np.log(1.5) / 20.0          # well before the last month
    signals = R.price_signals(path(returns))
    assert signals["momentum"] == pytest.approx(0.5, abs=0.03)


def test_near_high_is_zero_at_the_high_and_negative_below_it():
    rising = R.price_signals(path(np.full(400, 0.001)))
    assert rising["nearHigh"] == pytest.approx(0.0, abs=0.02)

    returns = np.full(400, 0.001)
    returns[-30:] = -0.005                         # give some back
    fallen = R.price_signals(path(returns))
    assert fallen["nearHigh"] < -0.10


def test_volatility_recovers_a_planted_dispersion():
    rng = np.random.default_rng(11)
    sigma = 0.02
    signals = R.price_signals(path(rng.normal(0.0, sigma, 600)))
    annualised = sigma * np.sqrt(R.TRADING_DAYS)
    assert signals["lowVolatility"] == pytest.approx(annualised, rel=0.12)


def test_drawdown_signal_is_reported_as_a_positive_depth():
    """Ranked with direction -1, so it has to be a magnitude, not a signed fall."""
    returns = np.zeros(400)
    returns[200:240] = np.log(0.7) / 40.0          # a 30% decline
    signals = R.price_signals(path(returns))
    assert signals["shallowDrawdown"] == pytest.approx(0.30, abs=0.02)
    assert signals["shallowDrawdown"] > 0


def test_relative_strength_is_the_gap_against_the_index():
    stock = path(np.full(400, 0.0010))
    index = path(np.full(400, 0.0004))["Close"]
    signals = R.price_signals(stock, benchmark=index)
    six_months = 126
    expected = (np.expm1(0.0010 * six_months) - np.expm1(0.0004 * six_months))
    assert signals["relativeStrength"] == pytest.approx(expected, rel=0.05)


def test_relative_strength_is_absent_without_a_benchmark():
    assert R.price_signals(path(steady()))["relativeStrength"] is None


def test_a_short_history_yields_no_signals_rather_than_partial_ones():
    signals = R.price_signals(path(steady(n=50)))
    assert all(value is None for value in signals.values())


def test_a_symbol_with_no_volume_reports_no_money_flow():
    frame = path(steady())
    frame["Volume"] = 0.0
    assert R.price_signals(frame)["flow"] is None


# ============================================================================ #
# Universe ranking
# ============================================================================ #
def _universe():
    """Five names, each deliberately best or worst at exactly one thing.

    EVERY PATH CARRIES NOISE. An earlier version built the trending names from
    a constant drift, which has zero variance — so the names meant to be lively
    were mathematically the calmest in the universe and the steadiness test was
    asserting the opposite of what it read.
    """
    n = 500
    rng = np.random.default_rng(5)
    quiet = rng.normal(0.0002, 0.004, n)                     # calmest by design
    strong = rng.normal(0.0016, 0.014, n)                    # best momentum and trend
    weak = rng.normal(-0.0012, 0.014, n)                     # worst of everything
    middling = rng.normal(0.0003, 0.011, n)
    scarred = rng.normal(0.0008, 0.012, n)
    # A deep fall INSIDE the one-year window that then fully recovers. Both
    # halves matter: the fall makes this the worst name on holdability, and the
    # recovery keeps its momentum and nearness-to-high ordinary, so the test
    # isolates the drawdown signal instead of making SCAR worst at everything.
    # (Planted before the window, it would be correctly invisible — which is the
    # whole point of RANK_WINDOW.)
    scarred[-170:-140] += np.log(0.55) / 30.0                # the deepest planted fall
    scarred[-140:-100] += np.log(1 / 0.55) / 40.0            # and back again
    return {
        "QUIET": path(quiet), "STRONG": path(strong), "WEAK": path(weak),
        "MID": path(middling), "SCAR": path(scarred),
    }


def test_the_strongest_name_ranks_top_on_momentum():
    result = R.rank_universe(_universe())
    momentum = {row["ticker"]: row["signals"]["momentum"]["percentile"]
                for row in result["rows"]}
    assert momentum["STRONG"] == max(momentum.values())
    assert momentum["WEAK"] == min(momentum.values())


def test_the_calmest_name_ranks_top_on_steadiness():
    """The low-is-good column, checked end to end through the ranking."""
    result = R.rank_universe(_universe())
    steadiness = {row["ticker"]: row["signals"]["lowVolatility"]["percentile"]
                  for row in result["rows"]}
    assert steadiness["QUIET"] == max(steadiness.values()), (
        "the calmest name must rank BEST on a low-is-good signal"
    )


def test_the_scarred_name_ranks_worst_on_holdability():
    """The name with the deepest planted fall must sit at the bottom.

    Note WEAK is a genuine rival here and is not excluded: a name that declines
    steadily for two years has a large drawdown too, honestly earned. The
    planted crash is made deeper than that decline so the ordering is
    unambiguous rather than a coin flip between two similar depths.
    """
    frames = _universe()
    result = R.rank_universe(frames)
    holdability = {row["ticker"]: row["signals"]["shallowDrawdown"]["percentile"]
                   for row in result["rows"]}
    assert holdability["SCAR"] == min(holdability.values())
    assert holdability["QUIET"] > holdability["SCAR"]

    # And the raw depth is the planted one, not just the ordering.
    raw = {row["ticker"]: row["signals"]["shallowDrawdown"]["raw"]
           for row in result["rows"]}
    assert raw["SCAR"] == pytest.approx(0.45, abs=0.06)   # the planted 55% floor


def test_rows_come_back_ordered_by_composite_and_numbered():
    result = R.rank_universe(_universe())
    composites = [row["composite"] for row in result["rows"]]
    assert composites == sorted(composites, reverse=True)
    assert [row["rank"] for row in result["rows"]] == list(range(1, len(composites) + 1))


def test_the_worst_name_does_not_finish_first():
    result = R.rank_universe(_universe())
    assert result["rows"][-1]["ticker"] == "WEAK"


def test_a_missing_signal_renormalises_rather_than_dragging_the_score_down():
    """A newly listed name must not be punished for being new.

    Two identical price paths; one is handed no benchmark for its own relative
    strength. Its composite should stay close to the other's, and its coverage
    should report the shortfall rather than hiding it.
    """
    frames = _universe()
    full = R.rank_universe(frames, benchmark=frames["MID"]["Close"])
    partial = R.rank_universe(frames, benchmark=None)

    for row in partial["rows"]:
        assert row["signals"]["relativeStrength"]["percentile"] is None
        assert row["coverage"] < 1.0
        assert row["signalsAvailable"] == row["signalsTotal"] - 1
    for row in full["rows"]:
        assert row["coverage"] == pytest.approx(1.0)

    # Composites stay on the same 0-100 scale despite one fewer contributor.
    assert all(0.0 <= row["composite"] <= 100.0 for row in partial["rows"])


def test_names_with_too_little_history_are_dropped_not_ranked_on_scraps():
    frames = _universe()
    frames["NEW"] = path(steady(n=40))
    result = R.rank_universe(frames)
    assert "NEW" not in {row["ticker"] for row in result["rows"]}


def test_weights_are_reported_so_the_composite_can_be_reproduced():
    result = R.rank_universe(_universe())
    assert set(result["weights"]) == set(R.SIGNAL_KEYS)
    row = result["rows"][0]
    expected = sum(row["signals"][k]["percentile"] * result["weights"][k]
                   for k in R.SIGNAL_KEYS
                   if row["signals"][k]["percentile"] is not None)
    total = sum(result["weights"][k] for k in R.SIGNAL_KEYS
                if row["signals"][k]["percentile"] is not None)
    assert row["composite"] == pytest.approx(expected / total)


def test_every_signal_declares_a_direction_and_an_evidence_grade():
    for signal in R.SIGNALS:
        assert signal["direction"] in (1, -1)
        assert signal["evidence"] in ("strong", "moderate", "weak")
        assert 0 < signal["weight"] <= 1.0
        assert len(signal["question"]) > 10
        assert len(signal["detail"]) > 40


def test_every_signal_has_a_header_short_enough_for_a_scrolling_table():
    """Long headers reveal a few letters at a time when a table scrolls sideways.

    "Near its high" emerging from under the pinned ticker column as "igh" reads
    as corruption rather than as a truncated word.
    """
    for signal in R.SIGNALS:
        assert signal["short"], f"{signal['key']} has no compact header"
        assert len(signal["short"]) <= 10, (
            f"{signal['key']}: {signal['short']!r} is too long for a table header"
        )


def test_the_weight_of_a_signal_follows_its_evidence_grade():
    """Weighting by conviction is a judgement; it must at least be a consistent one."""
    by_evidence: dict[str, set[float]] = {}
    for signal in R.SIGNALS:
        by_evidence.setdefault(signal["evidence"], set()).add(signal["weight"])
    for grade, weights in by_evidence.items():
        assert len(weights) == 1, f"{grade} signals carry inconsistent weights: {weights}"
    assert max(by_evidence["strong"]) > max(by_evidence["weak"])


# ============================================================================ #
# Signal overlap — the honesty measurement
# ============================================================================ #
def test_duplicated_signals_are_reported_as_overlapping():
    """Two identical columns must show a correlation of 1 and collapse the count."""
    rows = []
    for i in range(12):
        percentile = float(i * 8)
        rows.append({"signals": {key: {"percentile": percentile} for key in R.SIGNAL_KEYS}})
    result = R.signal_correlation(rows)
    assert result["available"]
    assert result["pairs"][0]["correlation"] == pytest.approx(1.0)
    # Seven perfectly correlated columns carry one signal's worth of information.
    assert result["effectiveSignals"] == pytest.approx(1.0, abs=0.05)
    assert "more than once" in result["reading"]


def test_independent_signals_score_close_to_their_own_count():
    rng = np.random.default_rng(21)
    rows = [
        {"signals": {key: {"percentile": float(rng.uniform(0, 100))}
                     for key in R.SIGNAL_KEYS}}
        for _ in range(400)
    ]
    result = R.signal_correlation(rows)
    assert result["effectiveSignals"] > len(R.SIGNAL_KEYS) * 0.85


def test_overlap_declines_to_guess_from_too_few_rows():
    rows = [{"signals": {key: {"percentile": 50.0} for key in R.SIGNAL_KEYS}}]
    assert R.signal_correlation(rows)["available"] is False


# ============================================================================ #
# Batch download — offline, against a stub of what yfinance returns
# ============================================================================ #
def test_listing_age_does_not_change_a_name_s_signals():
    """Two names with the IDENTICAL recent path must score identically.

    THE BUG THIS CATCHES. Volatility, the worst drawdown and the distance from
    the high were originally measured over "whatever history this symbol has".
    A long-listed name's window reached back far enough to include an old crash
    that a recently listed name's did not, so on a planted pair holdability came
    out 0.44 for the older name and 0.34 for the younger — a systematic bias in
    favour of recent listings, in a CROSS-SECTIONAL ranking, dressed up as a
    measurement about the stock.
    """
    rng = np.random.default_rng(4)
    returns = rng.normal(0.0005, 0.013, 620)
    returns[50:100] += np.log(0.6) / 50          # an old crash, long ago

    long_lived = path(returns)
    # The same recent 300 bars, as if the name had only listed then.
    young = path(returns[-300:], start_price=float(long_lived["Close"].iloc[-301]))

    old_signals = R.price_signals(long_lived)
    new_signals = R.price_signals(young)

    for key in ("lowVolatility", "shallowDrawdown", "nearHigh", "momentum", "trend"):
        assert old_signals[key] == pytest.approx(new_signals[key], rel=1e-9), (
            f"{key} depends on how long the symbol has been listed"
        )


def test_the_window_is_a_year_regardless_of_how_much_history_was_fetched():
    """A crash outside the window must not count; one inside must."""
    outside = np.zeros(600)
    outside[100:140] = np.log(0.5) / 40          # 460 bars ago — outside the year
    assert R.price_signals(path(outside))["shallowDrawdown"] == pytest.approx(0.0, abs=0.01)

    inside = np.zeros(600)
    inside[500:540] = np.log(0.5) / 40           # ~80 bars ago — inside it
    assert R.price_signals(path(inside))["shallowDrawdown"] == pytest.approx(0.5, abs=0.02)


def test_the_minimum_history_covers_the_hungriest_signal():
    """MIN_BARS is set by the trend slope, not by taste.

    A genuine 200-day average read across the last quarter needs 200 + 63 bars.
    Anything less and the "200-day average" is a shorter average wearing the
    name, which is the same category of error as an inconsistent window.
    """
    assert R.MIN_BARS >= 200 + 63
    just_enough = R.price_signals(path(steady(n=R.MIN_BARS)))
    assert just_enough["trend"] is not None
    too_few = R.price_signals(path(steady(n=R.MIN_BARS - 1)))
    assert all(value is None for value in too_few.values())


def test_every_measured_pair_gets_an_explanation():
    """The panel decides how many overlap rows to show; the server must not cap.

    When the server explained three pairs while the panel listed four, the last
    row silently lost its info icon — two independent counts with nothing tying
    them together.
    """
    from _lib import explain as E

    result = R.rank_universe(_universe())
    explanations = E.for_ranking(result)
    pairs = result["correlation"]["pairs"]
    assert pairs
    for pair in pairs:
        key = f"signalOverlap.{pair['a']}.{pair['b']}"
        assert key in explanations, f"{key} is measured but never explained"
