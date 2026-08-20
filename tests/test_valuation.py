"""The valuation core, checked against independent arithmetic.

`pv_of_growing_stream` is the single function every DCF and DDM number in the
product flows through. It is vectorised over the Monte Carlo draws, which makes
it fast and makes an off-by-one in the exponent invisible — so it is verified
here against a plain Python loop of the textbook formula rather than against
itself.
"""

from __future__ import annotations

import numpy as np
import pytest

from _lib import valuation as V


def reference_pv(base, g, r, gt, years=V.PROJECTION_YEARS):
    """The textbook calculation, written the slow obvious way."""
    projected = [base * (1.0 + g) ** t for t in range(1, years + 1)]
    pv_explicit = sum(p / (1.0 + r) ** t for t, p in enumerate(projected, start=1))
    spread = max(r - gt, V.MIN_SPREAD)
    terminal = projected[-1] * (1.0 + gt) / spread
    return projected, pv_explicit, terminal / (1.0 + r) ** years, terminal


@pytest.mark.parametrize(
    ("base", "g", "r", "gt"),
    [
        (1_000.0, 0.10, 0.09, 0.025),
        (5.5, 0.05, 0.11, 0.025),
        (1e9, 0.00, 0.08, 0.00),
        (250.0, -0.05, 0.12, 0.01),
        (100.0, 0.10, 0.03, 0.025),   # gt within MIN_SPREAD of r -> spread floor
        (100.0, 0.10, 0.02, 0.05),    # gt ABOVE r -> spread floor, must stay finite
    ],
)
def test_pv_matches_closed_form(base, g, r, gt):
    projected, pv_explicit, pv_terminal, terminal = V.pv_of_growing_stream(
        base, np.array([g]), np.array([r]), np.array([gt])
    )
    exp_projected, exp_explicit, exp_pv_terminal, exp_terminal = reference_pv(base, g, r, gt)

    np.testing.assert_allclose(projected[0], exp_projected, rtol=1e-12)
    np.testing.assert_allclose(pv_explicit[0, 0], exp_explicit, rtol=1e-12)
    np.testing.assert_allclose(pv_terminal[0, 0], exp_pv_terminal, rtol=1e-12)
    np.testing.assert_allclose(terminal[0, 0], exp_terminal, rtol=1e-12)


def test_terminal_value_never_diverges():
    """The Gordon denominator is floored, so gt >= r cannot produce inf/negative."""
    rates = np.full(200, 0.05)
    terminals = np.linspace(-0.02, 0.20, 200)   # deliberately runs past r
    _, _, pv_terminal, terminal = V.pv_of_growing_stream(100.0, np.full(200, 0.05),
                                                         rates, terminals)
    assert np.isfinite(terminal).all()
    assert np.isfinite(pv_terminal).all()
    assert (terminal > 0).all()


def test_dcf_equity_bridge():
    """Implied price = (EV + cash - debt) / shares, exactly."""
    base, g, r, gt = 1_000_000.0, 0.08, 0.09, 0.02
    cash, debt, shares = 500_000.0, 200_000.0, 1_000.0

    _, pv_explicit, pv_terminal, _ = V.pv_of_growing_stream(
        base, np.array([g]), np.array([r]), np.array([gt])
    )
    expected = ((pv_explicit + pv_terminal) + cash - debt) / shares
    got = V.dcf_implied_price(base, np.array([g]), np.array([r]), np.array([gt]),
                              cash, debt, shares)
    np.testing.assert_allclose(got, expected.ravel(), rtol=1e-12)


def test_ddm_price_is_per_share_pv():
    """A DDM values the dividend stream directly — no cash/debt bridge."""
    got = V.ddm_implied_price(5.0, np.array([0.05]), np.array([0.10]), np.array([0.025]))
    _, pv_explicit, pv_terminal, _ = V.pv_of_growing_stream(
        5.0, np.array([0.05]), np.array([0.10]), np.array([0.025])
    )
    np.testing.assert_allclose(got, (pv_explicit + pv_terminal).ravel(), rtol=1e-12)


# --------------------------------------------------------------------------- #
# Monte Carlo
# --------------------------------------------------------------------------- #
def test_monte_carlo_is_reproducible():
    """The CSV route promises the JSON route's exact distribution for one query."""
    kwargs = dict(engine="DCF", base=1e9, growth=0.10, rate=0.09, terminal_growth=0.025,
                  n_sims=5_000, sd_growth=0.02, sd_rate=0.01, sd_terminal=0.005,
                  cash=0.0, debt=0.0, shares=1e6)
    first = V.run_monte_carlo(seed=42, **kwargs)
    second = V.run_monte_carlo(seed=42, **kwargs)
    third = V.run_monte_carlo(seed=43, **kwargs)

    np.testing.assert_array_equal(first["Implied Price"], second["Implied Price"])
    assert not np.array_equal(first["Implied Price"], third["Implied Price"])


@pytest.mark.parametrize("engine", ["DCF", "DDM"])
def test_monte_carlo_keeps_terminal_growth_below_the_discount_rate(engine):
    """Every single draw, not just the mean — one bad draw is an infinite price."""
    sims = V.run_monte_carlo(
        engine=engine, base=1e6, growth=0.10, rate=0.06, terminal_growth=0.05,
        n_sims=20_000, sd_growth=0.05, sd_rate=0.04, sd_terminal=0.03, seed=7,
        cash=0.0, debt=0.0, shares=1e3,
    )
    rate_column = "WACC" if engine == "DCF" else "Cost of Equity"
    spread = sims[rate_column] - sims["Terminal Growth"]
    assert (spread >= V.MIN_SPREAD - 1e-12).all()
    assert np.isfinite(sims["Implied Price"]).all()


# --------------------------------------------------------------------------- #
# Guard-rails transcribed from the original app
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(("raw", "expected"), [(0.5, 0.5), (3.0, 2.5), (0.1, 0.4),
                                              (None, 1.0), (float("nan"), 1.0)])
def test_beta_is_clipped(raw, expected):
    assert V.clip_beta(raw) == pytest.approx(expected)


def test_wacc_is_clipped_and_weights_sum_to_one():
    parts = V.compute_wacc(beta=1.2, risk_free=0.042, erp=0.055, equity_value=1e9,
                           total_debt=5e8, interest_expense=2.5e7, tax_rate=0.21)
    assert 0.02 <= parts["wacc"] <= 0.40
    assert parts["weight_equity"] + parts["weight_debt"] == pytest.approx(1.0)
    assert 0.01 <= parts["cost_debt"] <= 0.25


def test_wacc_falls_back_to_cost_of_equity_without_capital_structure():
    parts = V.compute_wacc(beta=1.0, risk_free=0.04, erp=0.05, equity_value=0.0,
                           total_debt=0.0, interest_expense=float("nan"), tax_rate=0.21)
    assert parts["weight_equity"] == 1.0
    assert parts["wacc"] == pytest.approx(parts["cost_equity"])


def test_effective_tax_rate_is_clipped(monkeypatch):
    import pandas as pd
    income = pd.DataFrame(
        {"2025": [1_000.0, 10_000.0]},
        index=["Tax Provision", "Pretax Income"],
    )
    assert V.effective_tax_rate(income, 0.21) == pytest.approx(0.10)

    extreme = pd.DataFrame({"2025": [9_500.0, 10_000.0]},
                           index=["Tax Provision", "Pretax Income"])
    assert V.effective_tax_rate(extreme, 0.21) == pytest.approx(0.40)   # clipped


def test_risk_free_rate_is_cached_per_day(monkeypatch):
    """Q7: one ^TNX fetch per day, not one per valuation. Failures are not cached."""
    calls = {"n": 0}

    class FakeTicker:
        def __init__(self, symbol):
            calls["n"] += 1

        def history(self, period):
            import pandas as pd
            return pd.DataFrame({"Close": [4.65]})

    monkeypatch.setattr(V.yf, "Ticker", FakeTicker)
    V._RISK_FREE_CACHE.clear()

    for _ in range(5):
        rate, source = V.fetch_risk_free_rate("US", 0.042)
        assert rate == pytest.approx(0.0465)
        assert "live" in source
    assert calls["n"] == 1

    # A non-US market never touches the network at all.
    before = calls["n"]
    V.fetch_risk_free_rate("ID", 0.065)
    assert calls["n"] == before


def test_risk_free_failure_is_not_cached(monkeypatch):
    class Exploding:
        def __init__(self, symbol):
            raise RuntimeError("network down")

    monkeypatch.setattr(V.yf, "Ticker", Exploding)
    V._RISK_FREE_CACHE.clear()

    rate, source = V.fetch_risk_free_rate("US", 0.042)
    assert rate == pytest.approx(0.042)
    assert "fallback" in source
    assert not V._RISK_FREE_CACHE, "a failed fetch must not pin the fallback all day"


def test_detect_engine_routes_financials_to_ddm():
    assert V.detect_engine("Financial Services", "Banks—Diversified")[0] == "DDM"
    assert V.detect_engine("Technology", "Consumer Electronics")[0] == "DCF"
    assert V.detect_engine("", "Regional Banking")[0] == "DDM"
