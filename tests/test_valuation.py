"""The valuation core, checked against independent arithmetic.

`pv_of_growing_stream` is the single function every DCF and DDM number in the
product flows through. It is vectorised over the Monte Carlo draws, which makes
it fast and makes an off-by-one in the exponent invisible — so it is verified
here against a plain Python loop of the textbook formula rather than against
itself.
"""

from __future__ import annotations


import numpy as np
import pandas as pd
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
    income = pd.DataFrame(
        {"2025": [1_000.0, 10_000.0]},
        index=["Tax Provision", "Pretax Income"],
    )
    assert V.effective_tax_rate(income, 0.21) == pytest.approx(0.10)

    extreme = pd.DataFrame({"2025": [9_500.0, 10_000.0]},
                           index=["Tax Provision", "Pretax Income"])
    assert V.effective_tax_rate(extreme, 0.21) == pytest.approx(0.40)   # clipped


def test_detect_engine_routes_financials_to_ddm():
    assert V.detect_engine("Financial Services", "Banks—Diversified")[0] == "DDM"
    assert V.detect_engine("Technology", "Consumer Electronics")[0] == "DCF"
    assert V.detect_engine("", "Regional Banking")[0] == "DDM"




# --------------------------------------------------------------------------- #
# Reverse DCF — what the market is already assuming
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("planted", [-0.20, -0.05, 0.0, 0.02, 0.08, 0.15, 0.25, 0.45])
@pytest.mark.parametrize("engine", ["DCF", "DDM"])
def test_implied_growth_inverts_the_forward_model_exactly(engine, planted):
    """Price the model at a KNOWN growth rate, then solve back for it.

    This is the strongest test available for an inverse: the reference is not a
    second implementation of the same formula, it is the forward function's own
    output, so the pair has to agree or one of them is wrong.
    """
    rate, terminal = 0.09, 0.025
    cash, debt, shares = 500.0, 2_000.0, 1_000.0
    growth = np.array([planted])

    if engine == "DCF":
        price = float(V.dcf_implied_price(1_000.0, growth, np.array([rate]),
                                          np.array([terminal]), cash, debt, shares)[0])
        recovered = V.implied_growth(engine, price, 1_000.0, rate, terminal,
                                     cash=cash, debt=debt, shares=shares)
    else:
        price = float(V.ddm_implied_price(4.0, growth, np.array([rate]),
                                          np.array([terminal]))[0])
        recovered = V.implied_growth(engine, price, 4.0, rate, terminal)

    assert recovered == pytest.approx(planted, abs=1e-5)


def test_a_higher_price_always_implies_higher_growth():
    """Monotonic, which is what licenses using a root finder at all."""
    args = dict(base=1_000.0, rate=0.09, terminal_growth=0.025,
                cash=0.0, debt=0.0, shares=1_000.0)
    solved = [V.implied_growth("DCF", price, **args) for price in (5.0, 10.0, 20.0, 40.0)]
    assert all(g is not None for g in solved), solved
    assert solved == sorted(solved), solved


def test_an_unreachable_price_returns_none_rather_than_a_boundary_value():
    """A price needing more than 60% compound growth is not being set on cash
    flows by anyone. Returning the bracket edge would dress that up as a
    measurement; None says the model has left its domain."""
    absurd = V.implied_growth("DCF", 1e9, 1_000.0, 0.09, 0.025,
                              cash=0.0, debt=0.0, shares=1_000.0)
    assert absurd is None
    assert V.implied_growth("DCF", 1e-9, 1_000.0, 0.09, 0.025,
                            cash=0.0, debt=0.0, shares=1_000.0) is None


@pytest.mark.parametrize("price", [0.0, -5.0, None, float("nan"), float("inf")])
def test_a_nonsense_price_is_refused(price):
    assert V.implied_growth("DCF", price, 1_000.0, 0.09, 0.025,
                            cash=0.0, debt=0.0, shares=1_000.0) is None


def test_the_reading_names_the_gap_against_the_assumption():
    """The number on its own is context; against what you assumed it is a
    decision. Both directions must be stated plainly."""
    from _lib import explain as E

    higher = E.explain("impliedGrowth", 0.18, assumedGrowth=0.10)
    assert "MORE growth than you assumed" in higher["reading"]
    lower = E.explain("impliedGrowth", 0.04, assumedGrowth=0.10)
    assert "LESS growth than you assumed" in lower["reading"]
    same = E.explain("impliedGrowth", 0.100, assumedGrowth=0.100)
    assert "the model and the market agree" in same["reading"]

    # A demanding implied rate is the CAUTIOUS end, not the good one.
    assert E.explain("impliedGrowth", 0.45)["tone"] in ("warn", "bad")
    assert E.explain("impliedGrowth", 0.02)["tone"] == "good"
    assert E.explain("impliedGrowth", None)["tone"] == "none"
