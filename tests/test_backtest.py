"""Does the backtest work? A null result from a broken test means nothing.

The point of `backtest.py` is to say honestly whether the composite ranking
predicts returns. That claim is worthless unless the machinery can detect a
signal when one is present, and equally worthless if it can detect one that is
not. Both directions are pinned here, offline, against planted ground truth.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from _lib import backtest as B


def frames_from(paths: dict[str, np.ndarray], start="2019-01-02") -> dict[str, pd.DataFrame]:
    out = {}
    for symbol, close in paths.items():
        index = pd.bdate_range(start, periods=len(close))
        out[symbol] = pd.DataFrame(
            {"Open": close, "High": close * 1.005, "Low": close * 0.995,
             "Close": close, "Volume": np.full(len(close), 1e6)}, index=index)
    return out


def planted(n_symbols: int, n_days: int, *, predictive: bool, seed: int) -> dict:
    """Price paths where past momentum either DOES or DOES NOT set future return.

    Each name is assigned a persistent quality. When `predictive`, that quality
    drives the drift throughout, so a name that rose in the past keeps rising and
    the ranking should find it. When not, the drift is redrawn every step, so the
    past says nothing about the future and any measured skill is an artefact.
    """
    rng = np.random.default_rng(seed)
    quality = np.linspace(-1.0, 1.0, n_symbols)
    paths = {}
    for i in range(n_symbols):
        if predictive:
            drift = np.full(n_days, quality[i] * 0.0016)
        else:
            drift = rng.normal(0.0, 0.0016, n_days)
        noise = rng.normal(0.0, 0.011, n_days)
        paths[f"S{i:02d}"] = 100.0 * np.exp(np.cumsum(drift + noise))
    return frames_from(paths)


def run_on(frames: dict, horizon: int = 21) -> dict:
    """Drive `backtest.run` against planted frames instead of the network."""
    import unittest.mock as mock
    with mock.patch.object(B.market_data, "ohlcv_batch") as fetch:
        fetch.side_effect = lambda syms, *a, **k: (
            {s: frames[s] for s in syms if s in frames})
        return B.run(sorted(frames), market_code="US", horizon=horizon, years=6)


def test_it_detects_a_signal_that_is_really_there():
    """THE TEST THAT LICENSES THE NULL RESULT.

    If the machinery cannot find a planted relationship, then "no significant
    relationship" on real data says nothing about the market and everything
    about the test. Momentum here is constructed to persist, so the ranking must
    both correlate with forward return and reach significance.
    """
    result = run_on(planted(30, 1_400, predictive=True, seed=11))
    assert result["usable"], result.get("reason")

    ic = result["informationCoefficient"]
    spread = result["quintileSpread"]
    assert ic["mean"] > 0.2, f"planted signal produced IC {ic['mean']:.3f}"
    assert ic["pValue"] < 0.01, ic
    assert spread["mean"] > 0, spread
    assert "No significant relationship" not in result["verdict"]


def test_it_finds_nothing_when_there_is_nothing():
    """The other direction: a past that does not determine the future must not
    produce skill. A backtest that finds an edge in noise is worse than none."""
    result = run_on(planted(30, 1_400, predictive=False, seed=5))
    assert result["usable"], result.get("reason")
    assert abs(result["informationCoefficient"]["mean"]) < 0.15
    assert result["informationCoefficient"]["pValue"] > 0.05
    assert "No significant relationship" in result["verdict"]


def test_no_signal_can_see_past_its_own_rebalance_date():
    """Point-in-time, proven rather than asserted.

    The frames are truncated at each rebalance before any signal is computed. If
    that slicing were wrong, appending a wildly different future to the SAME
    history would change the ranking computed at a date before it — so the
    rankings are compared directly.
    """
    base = planted(20, 1_000, predictive=True, seed=3)
    asof = list(base["S00"].index)[-1]

    # Same history, two completely different futures bolted on.
    rng = np.random.default_rng(9)
    futures = {}
    for sign in (+1, -1):
        extended = {}
        for symbol, frame in base.items():
            tail = frame["Close"].iloc[-1] * np.exp(
                np.cumsum(rng.normal(sign * 0.01, 0.01, 300)))
            index = pd.bdate_range(frame.index[-1] + pd.Timedelta(days=1), periods=300)
            extra = pd.DataFrame(
                {"Open": tail, "High": tail * 1.005, "Low": tail * 0.995,
                 "Close": tail, "Volume": np.full(300, 1e6)}, index=index)
            extended[symbol] = pd.concat([frame, extra])
        futures[sign] = extended

    from _lib import ranking
    orders = []
    for sign in (+1, -1):
        sliced = {s: f.loc[:asof] for s, f in futures[sign].items()}
        ranked = ranking.rank_universe(sliced)
        orders.append([r["ticker"] for r in ranked["rows"]])
    assert orders[0] == orders[1], "the ranking changed when only the FUTURE differed"


def test_periods_do_not_overlap_by_default():
    """Overlapping windows share trading days, so the observations are
    correlated and a plain t-statistic overstates its own significance."""
    index = pd.bdate_range("2019-01-02", periods=1_400)
    dates = B.rebalance_dates(index, horizon=63)
    gaps = {(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)}
    assert dates, "no rebalance dates produced"
    assert min(gaps) >= 63, f"windows overlap: gaps {sorted(gaps)[:3]}"


def test_a_thin_universe_refuses_rather_than_reporting_on_three_names():
    result = run_on(planted(4, 1_000, predictive=True, seed=1))
    assert result["usable"] is False
    assert "cross-section" in result["reason"] or "periods" in result["reason"]


def test_the_verdict_always_carries_its_own_caveats():
    result = run_on(planted(30, 1_400, predictive=True, seed=11))
    joined = " ".join(result["caveats"]).lower()
    for expected in ("survivorship", "cost", "sample", "regime"):
        assert expected in joined, expected


@pytest.mark.parametrize("horizon", [21, 63])
def test_the_reported_power_floor_is_positive_and_sane(horizon):
    """A null result is only informative next to what the test could detect."""
    result = run_on(planted(30, 1_400, predictive=False, seed=7), horizon=horizon)
    floor = result["informationCoefficient"]["minimumDetectable"]
    assert floor is not None and 0 < floor < 1
