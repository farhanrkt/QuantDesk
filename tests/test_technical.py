"""Indicator golden tests.

`technical.py` deliberately hand-rolls SMA / RSI / MACD / Bollinger instead of
depending on pandas_ta (see its EXTRACTION NOTE). That is a sound call for a
serverless bundle, but it means the formulas are now this project's
responsibility — and they are the numbers the narrative readout, the chips and
the confluence vote are all derived from.

Each indicator is therefore checked against a reference written independently
here, in plain loops, from the textbook definition. Comparing pandas to pandas
would only prove the code equals itself.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from _lib import technical as T


@pytest.fixture(scope="module")
def close(ohlcv) -> pd.Series:
    return ohlcv["Close"].astype("float64")


def reference_wilder_rsi(values, length=14):
    """Wilder's RSI, written as the original recurrence rather than an ewm call."""
    values = np.asarray(values, dtype=float)
    out = np.full(len(values), np.nan)
    if len(values) <= length:
        return out

    deltas = np.diff(values)
    gains = np.clip(deltas, 0, None)
    losses = -np.clip(deltas, None, 0)

    # Wilder seeds with a simple average, then smooths with alpha = 1/length.
    # technical.py uses adjust=False ewm seeded on the first value, which is the
    # same recurrence; both converge, so the comparison starts after a burn-in.
    avg_gain, avg_loss = gains[0], losses[0]
    for i in range(1, len(deltas)):
        avg_gain = (avg_gain * (length - 1) + gains[i]) / length
        avg_loss = (avg_loss * (length - 1) + losses[i]) / length
        if avg_loss == 0:
            out[i + 1] = 100.0
        else:
            rs = avg_gain / avg_loss
            out[i + 1] = 100.0 - 100.0 / (1.0 + rs)
    return out


def reference_ema(values, span):
    alpha = 2.0 / (span + 1.0)
    out = np.full(len(values), np.nan)
    running = values[0]
    out[0] = running
    for i in range(1, len(values)):
        running = alpha * values[i] + (1 - alpha) * running
        out[i] = running
    return out


# --------------------------------------------------------------------------- #
def test_sma_matches_explicit_mean(close):
    sma = T._sma(close, 50)
    values = close.to_numpy()
    for position in (60, 200, 400, len(values) - 1):
        expected = values[position - 49: position + 1].mean()
        assert sma.iloc[position] == pytest.approx(expected, rel=1e-12)
    assert sma.iloc[:49].isna().all(), "SMA must not emit a value before its window fills"


def test_rsi_matches_wilder_recurrence(close):
    got = T._rsi(close, 14).to_numpy()
    expected = reference_wilder_rsi(close.to_numpy(), 14)
    # Both seed differently and converge; compare after a generous burn-in.
    start = 120
    np.testing.assert_allclose(got[start:], expected[start:], rtol=1e-6, atol=1e-6)


def test_rsi_is_bounded(close):
    rsi = T._rsi(close, 14).dropna()
    assert rsi.between(0, 100).all()


def test_rsi_is_100_when_nothing_falls():
    """The `where(avg_loss != 0, 100.0)` branch — a monotonic series has no losses."""
    rising = pd.Series(np.linspace(10, 50, 60))
    assert T._rsi(rising, 14).dropna().iloc[-1] == pytest.approx(100.0)


def test_macd_matches_reference_emas(close):
    line, signal, hist = T._macd(close, 12, 26, 9)
    values = close.to_numpy()
    expected_line = reference_ema(values, 12) - reference_ema(values, 26)

    start = 120
    np.testing.assert_allclose(line.to_numpy()[start:], expected_line[start:],
                               rtol=1e-6, atol=1e-6)
    np.testing.assert_allclose((line - signal).to_numpy()[start:],
                               hist.to_numpy()[start:], rtol=1e-12, atol=1e-12)


def test_bollinger_uses_sample_stddev(close):
    """BB_DDOF is documented as 1; pandas_ta defaults to 0. Pin the choice."""
    assert T.BB_DDOF == 1
    lower, middle, upper = T._bbands(close, 20, 2.0)
    values = close.to_numpy()
    position = 300
    window = values[position - 19: position + 1]
    assert middle.iloc[position] == pytest.approx(window.mean(), rel=1e-12)
    assert upper.iloc[position] == pytest.approx(
        window.mean() + 2.0 * window.std(ddof=1), rel=1e-12)
    assert lower.iloc[position] == pytest.approx(
        window.mean() - 2.0 * window.std(ddof=1), rel=1e-12)


def test_bands_bracket_the_middle(close):
    lower, middle, upper = T._bbands(close, 20, 2.0)
    frame = pd.DataFrame({"l": lower, "m": middle, "u": upper}).dropna()
    assert (frame["l"] <= frame["m"]).all()
    assert (frame["m"] <= frame["u"]).all()


# --------------------------------------------------------------------------- #
def test_golden_and_death_cross_detection():
    """A crossover fires once, on the bar where it happens, in the right direction.

    The decline up front is load-bearing: SMA_200 only becomes valid on bar 200,
    and `generate_signals` requires BOTH averages to be valid on the bar and the
    one before it. Without a long enough runway the fast average is already
    above the slow one the moment the slow one exists, so the golden cross
    happened in the unobservable prefix and correctly never fires.
    """
    values = np.concatenate([
        np.linspace(200, 120, 260),   # long decline: fast settles below slow
        np.linspace(120, 340, 220),   # sustained rally: golden cross
        np.linspace(340, 110, 220),   # sustained selloff: death cross
    ])
    n = len(values)
    frame = pd.DataFrame({"Close": values}, index=pd.bdate_range("2024-01-01", periods=n))
    frame = T.calculate_indicators(frame)
    signals = T.generate_signals(frame)

    fired = signals.loc[signals["Signal"] != "", "Signal"].tolist()
    assert "Buy" in fired and "Sell" in fired
    assert fired.index("Buy") < fired.index("Sell")
    # A cross is an event, not a state: it must not repeat on every later bar.
    assert len(fired) <= 4


def test_no_signal_without_enough_history():
    frame = pd.DataFrame({"Close": np.linspace(10, 20, 80)},
                         index=pd.bdate_range("2024-01-01", periods=80))
    signals = T.generate_signals(T.calculate_indicators(frame))
    assert (signals["Signal"] == "").all()


def test_support_resistance_levels_are_sorted_and_in_range(ohlcv):
    levels = T.calculate_support_resistance(ohlcv, window=10, max_levels=6)
    assert levels == sorted(levels)
    assert len(levels) <= 6
    assert min(levels) >= ohlcv["Low"].min() * 0.9
    assert max(levels) <= ohlcv["High"].max() * 1.1


def test_support_resistance_handles_short_frames():
    tiny = pd.DataFrame({"High": [1, 2], "Low": [0.5, 1], "Close": [1, 1.5]})
    assert T.calculate_support_resistance(tiny, window=10) == []


def test_summary_splits_levels_around_the_price(ohlcv):
    frame = T.generate_signals(T.calculate_indicators(ohlcv))
    levels = T.calculate_support_resistance(frame, window=10, max_levels=6)
    summary = T.summarise_market(frame, levels, "USD", "TEST")
    price = float(frame["Close"].iloc[-1])

    if summary["resistance"] is not None:
        assert summary["resistance"] > price
    if summary["support"] is not None:
        assert summary["support"] < price
    assert summary["trend"] in {"Uptrend", "Downtrend", "Sideways", "Rising",
                                "Falling", "Flat", "Too early to call"}
    # The headline is emitted as **bold** markers, never raw HTML.
    assert "<b>" not in summary["headline"] and "<script" not in summary["headline"]
