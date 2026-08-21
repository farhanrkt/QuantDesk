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

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from _lib import ranking as R


def path(returns, start_price=100.0, start="2023-01-02"):
    """An OHLCV frame from a return series, with a mild fixed intraday range."""
    close = start_price * np.exp(np.cumsum(np.asarray(returns, dtype="float64")))
    index = pd.bdate_range(start, periods=len(close))
    return pd.DataFrame({
        "Open": close,
        "High": close * 1.01,
        "Low": close * 0.99,
        "Close": close,
        "Volume": np.full(len(close), 1_000_000.0),
    }, index=index)


def steady(n=400, drift=0.0004, sigma=0.010, seed=3):
    rng = np.random.default_rng(seed)
    return rng.normal(drift, sigma, n)


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
    scarred[150:200] += np.log(0.40) / 50.0                  # the deepest planted fall
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
    assert raw["SCAR"] > 0.5


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
class _Stub:
    """Stands in for `yf.download`, reproducing both real column shapes."""

    def __init__(self, frames: dict[str, pd.DataFrame], multiindex: bool = True):
        self.frames = frames
        self.multiindex = multiindex
        self.calls: list[list[str]] = []

    def __call__(self, chunk, **_kwargs):
        symbols = list(chunk) if isinstance(chunk, (list, tuple)) else [chunk]
        self.calls.append(symbols)
        available = [s for s in symbols if s in self.frames]
        if not available:
            return pd.DataFrame()
        if self.multiindex:
            return pd.concat({s: self.frames[s] for s in available}, axis=1)
        return self.frames[available[0]]


def test_batch_download_returns_one_frame_per_symbol(monkeypatch):
    frames = {"AAA": path(steady(n=300)), "BBB": path(steady(n=300, seed=9))}
    stub = _Stub(frames)
    monkeypatch.setattr(R.yf, "download", stub)

    out = R.batch_download(["AAA", "BBB"], dt.date(2023, 1, 1), dt.date(2024, 1, 1))
    assert set(out) == {"AAA", "BBB"}
    assert not out["AAA"].empty


def test_a_single_symbol_chunk_survives_the_multiindex_shape(monkeypatch):
    """The defect this file was written to catch.

    `group_by="ticker"` returns a TWO-LEVEL column index even for one symbol.
    The original code branched on `len(chunk) == 1` and handed the MultiIndex
    frame to the flat-column normaliser, which failed its check and dropped the
    symbol without a word — losing the benchmark index on every single scan.
    """
    stub = _Stub({"^GSPC": path(steady(n=300))})
    monkeypatch.setattr(R.yf, "download", stub)

    out = R.batch_download(["^GSPC"], dt.date(2023, 1, 1), dt.date(2024, 1, 1))
    assert "^GSPC" in out, "a one-symbol batch must not be silently dropped"
    assert len(out["^GSPC"]) > 200


def test_a_flat_single_symbol_response_still_works(monkeypatch):
    """The other shape, in case yfinance changes its mind again."""
    stub = _Stub({"AAA": path(steady(n=300))}, multiindex=False)
    monkeypatch.setattr(R.yf, "download", stub)
    out = R.batch_download(["AAA"], dt.date(2023, 1, 1), dt.date(2024, 1, 1))
    assert "AAA" in out


def test_the_universe_is_split_into_chunks(monkeypatch):
    frames = {f"S{i:03d}": path(steady(n=300, seed=i)) for i in range(120)}
    stub = _Stub(frames)
    monkeypatch.setattr(R.yf, "download", stub)

    out = R.batch_download(sorted(frames), dt.date(2023, 1, 1), dt.date(2024, 1, 1),
                           chunk_size=50)
    assert len(out) == 120
    assert [len(c) for c in stub.calls] == [50, 50, 20]


def test_the_last_chunk_of_a_51_symbol_universe_is_not_lost(monkeypatch):
    """The regression the single-symbol bug would also have caused.

    51 symbols at a chunk size of 50 leaves a final chunk of exactly one, which
    is the case that used to vanish.
    """
    frames = {f"S{i:03d}": path(steady(n=300, seed=i)) for i in range(51)}
    stub = _Stub(frames)
    monkeypatch.setattr(R.yf, "download", stub)
    out = R.batch_download(sorted(frames), dt.date(2023, 1, 1), dt.date(2024, 1, 1),
                           chunk_size=50)
    assert len(out) == 51


def test_a_failing_chunk_does_not_abort_the_whole_scan(monkeypatch):
    frames = {"AAA": path(steady(n=300)), "BBB": path(steady(n=300, seed=2))}

    def flaky(chunk, **kwargs):
        symbols = list(chunk) if isinstance(chunk, (list, tuple)) else [chunk]
        if "AAA" in symbols:
            raise RuntimeError("upstream is having a day")
        return pd.concat({s: frames[s] for s in symbols if s in frames}, axis=1)

    monkeypatch.setattr(R.yf, "download", flaky)
    out = R.batch_download(["AAA", "BBB"], dt.date(2023, 1, 1), dt.date(2024, 1, 1),
                           chunk_size=1)
    assert set(out) == {"BBB"}


def test_duplicate_symbols_are_requested_once(monkeypatch):
    stub = _Stub({"AAA": path(steady(n=300))})
    monkeypatch.setattr(R.yf, "download", stub)
    R.batch_download(["AAA", "aaa", "AAA"], dt.date(2023, 1, 1), dt.date(2024, 1, 1))
    assert stub.calls == [["AAA"]]


def test_scan_names_the_symbols_it_could_not_rank(monkeypatch):
    """A count is unactionable; a typo and a delisting look different."""
    frames = {"AAA": path(steady(n=400)), "BBB": path(steady(n=400, seed=2))}
    monkeypatch.setattr(R.yf, "download", _Stub(frames))

    result = R.scan(["AAA", "BBB", "GHOST"], market_code="US")
    assert result["requested"] == 3
    assert result["ranked"] == 2
    assert result["missing"] == ["GHOST"]
