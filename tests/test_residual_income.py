"""The residual income engine (Ohlson 1995).

The strongest test here is `test_no_excess_return_means_exactly_book_value`.
Residual income has an invariant the DCF and DDM do not: a company earning
precisely its cost of equity creates no value beyond the capital already
invested, so the model must return book value EXACTLY — not approximately.
Any error in the discounting, the clean-surplus roll-forward or the continuing
value breaks that identity immediately.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from _lib import valuation as V


def reference_ri(book, roe, r, payout, years=5, persistence=V.RI_PERSISTENCE):
    """The model written out as a plain loop, from the paper's definition."""
    b = book
    pv = 0.0
    residual = 0.0
    for t in range(1, years + 1):
        residual = (roe - r) * b
        pv += residual / (1.0 + r) ** t
        b = b * (1.0 + roe * (1.0 - payout))
    continuing = residual * persistence / max(1.0 + r - persistence, V.MIN_SPREAD)
    return book + pv + continuing / (1.0 + r) ** years


# --------------------------------------------------------------------------- #
# The core identity
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("rate", [0.06, 0.09, 0.12, 0.18])
@pytest.mark.parametrize("payout", [0.0, 0.4, 1.0])
def test_no_excess_return_means_exactly_book_value(rate, payout):
    """ROE == cost of equity -> the company creates nothing beyond its book."""
    value, pv_explicit, pv_continuing, _ = V.residual_income_value(
        np.array([100.0]), np.array([rate]), np.array([rate]), np.array([payout])
    )
    assert float(value[0]) == pytest.approx(100.0, rel=1e-12)
    assert float(pv_explicit[0]) == pytest.approx(0.0, abs=1e-12)
    assert float(pv_continuing[0]) == pytest.approx(0.0, abs=1e-12)


@pytest.mark.parametrize(("roe", "rate", "expect_premium"), [
    (0.18, 0.10, True),      # earns above its cost of capital -> above book
    (0.05, 0.10, False),     # earns below -> below book
])
def test_excess_return_sets_the_side_of_book(roe, rate, expect_premium):
    value, *_ = V.residual_income_value(
        np.array([100.0]), np.array([roe]), np.array([rate]), np.array([0.4])
    )
    assert (float(value[0]) > 100.0) is expect_premium


def test_matches_a_hand_written_loop():
    for roe, rate, payout in ((0.18, 0.10, 0.30), (0.08, 0.11, 0.60), (0.25, 0.09, 0.0)):
        value, *_ = V.residual_income_value(
            np.array([250.0]), np.array([roe]), np.array([rate]), np.array([payout])
        )
        assert float(value[0]) == pytest.approx(reference_ri(250.0, roe, rate, payout),
                                                rel=1e-12)


def test_book_value_rolls_forward_by_clean_surplus():
    """B_t = B_{t-1} * (1 + ROE*(1-payout)) — retained earnings, nothing else."""
    roe, payout = 0.20, 0.25
    _, _, _, schedule = V.residual_income_value(
        np.array([100.0]), np.array([roe]), np.array([0.10]), np.array([payout])
    )
    expected = 100.0
    for step in schedule:
        assert float(step["openingBook"][0]) == pytest.approx(expected, rel=1e-12)
        expected *= 1.0 + roe * (1.0 - payout)


def test_full_payout_freezes_book_value():
    _, _, _, schedule = V.residual_income_value(
        np.array([100.0]), np.array([0.15]), np.array([0.10]), np.array([1.0])
    )
    books = [float(step["openingBook"][0]) for step in schedule]
    assert all(b == pytest.approx(100.0) for b in books)


def test_higher_persistence_is_worth_more():
    values = [
        float(V.residual_income_value(np.array([100.0]), np.array([0.18]),
                                      np.array([0.10]), np.array([0.4]),
                                      persistence=w)[0][0])
        for w in (0.0, 0.3, 0.62, 0.9)
    ]
    assert values == sorted(values)


def test_persistence_cannot_diverge():
    """w -> 1 with a low discount rate is where a naive formula explodes."""
    value, *_ = V.residual_income_value(
        np.array([100.0]), np.array([0.30]), np.array([0.03]), np.array([0.0]),
        persistence=0.999,
    )
    assert np.isfinite(value[0])


def test_terminal_value_does_not_dominate():
    """The structural reason to prefer RI for a bank.

    Abnormal earnings FADE, so the continuing value is a modest share of the
    total — unlike a Gordon terminal, which routinely carries 60-80% of a DDM
    or DCF and which the app has to warn users about.
    """
    value, _, pv_continuing, _ = V.residual_income_value(
        np.array([100.0]), np.array([0.16]), np.array([0.10]), np.array([0.4])
    )
    share = float(pv_continuing[0]) / float(value[0])
    assert share < 0.25, f"continuing value was {share:.0%} of total"


# --------------------------------------------------------------------------- #
# Monte Carlo
# --------------------------------------------------------------------------- #
def test_ri_monte_carlo_is_reproducible_and_labelled():
    kwargs = dict(engine="RI", base=100.0, growth=0.15, rate=0.10,
                  terminal_growth=0.0, n_sims=4000, sd_growth=0.03,
                  sd_rate=0.01, sd_terminal=0.0, payout=0.4)
    first = V.run_monte_carlo(seed=42, **kwargs)
    second = V.run_monte_carlo(seed=42, **kwargs)

    np.testing.assert_array_equal(first["Implied Price"], second["Implied Price"])
    assert "Return on Equity" in first.columns
    assert "Cost of Equity" in first.columns
    assert "Terminal Growth" not in first.columns      # RI has none
    assert np.isfinite(first["Implied Price"]).all()


def test_ri_monte_carlo_bounds_roe():
    sims = V.run_monte_carlo(
        engine="RI", base=100.0, growth=0.15, rate=0.10, terminal_growth=0.0,
        n_sims=20000, sd_growth=0.60, sd_rate=0.02, sd_terminal=0.0,
        seed=1, payout=0.3,
    )
    low, high = V.RI_ROE_BOUNDS
    assert sims["Return on Equity"].min() >= low
    assert sims["Return on Equity"].max() <= high


# --------------------------------------------------------------------------- #
# Inputs and routing
# --------------------------------------------------------------------------- #
def _bank_data(dividends=True):
    balance = pd.DataFrame({"2025": [50_000.0], "2024": [46_000.0]},
                           index=["Stockholders Equity"])
    income = pd.DataFrame({"2025": [6_000.0], "2024": [5_400.0]},
                          index=["Net Income"])
    return {
        "ok": True, "name": "Test Bank", "sector": "Financial Services",
        "industry": "Banks—Regional", "price": 900.0, "shares": 100.0,
        "beta": 1.0, "currency": "IDR", "market_cap": 90_000.0,
        "dividend_rate": 30.0 if dividends else np.nan,
        "trailing_dividend_rate": np.nan, "dividend_yield_raw": np.nan,
        "trailing_dividend_yield_raw": np.nan, "payout_ratio": 0.45,
        "roe_info": 0.12, "net_income_info": 6_000.0,
        "ttm_dividend": 30.0 if dividends else np.nan,
        "dividend_history": pd.DataFrame(),
        "income": income, "balance": balance, "cashflow": pd.DataFrame(),
    }


def test_ri_inputs_derive_book_per_share_and_roe():
    result = V.ri_inputs(_bank_data(), price=900.0, shares=100.0)
    assert result["usable"] is True
    assert result["bookPerShare"] == pytest.approx(500.0)
    assert result["roe"] == pytest.approx(0.12)


def test_ri_inputs_reports_unusable_without_equity():
    result = V.ri_inputs(
        {"balance": pd.DataFrame(), "income": pd.DataFrame(), "roe_info": np.nan,
         "payout_ratio": np.nan, "net_income_info": np.nan},
        price=10.0, shares=5.0,
    )
    assert result["usable"] is False


def test_a_dividendless_bank_routes_to_ri_instead_of_the_manual_form(monkeypatch):
    """The workaround this engine exists to retire.

    Before: no dividend -> ValuationError(manualRequired) -> the user is asked
    to type in a figure Yahoo does not have. After: switch to the model whose
    inputs those filings DO contain.
    """
    monkeypatch.setattr(V, "fetch_company", lambda ticker: _bank_data(dividends=False))
    monkeypatch.setattr(V, "fetch_risk_free_rate", lambda *a, **k: (0.065, "test"))
    monkeypatch.setattr(V.riskmodel, "estimate_beta_for_symbol",
                        lambda *a, **k: V.riskmodel.BetaEstimate(
                            raw=1.0, adjusted=1.0, stderr=0.1, r_squared=0.4,
                            observations=400, method="vasicek", index_symbol="^JKSE",
                            prior_weight=0.04))

    result = V.analyze("TESTBANK.JK", market_code="ID")
    assert result["engine"] == "RI"
    assert "dividend" in result["routeReason"]
    assert result["baseCase"]["impliedPrice"] > 0
    assert any("residual income" in n["text"].lower() for n in result["notices"])


def test_a_bank_with_dividends_still_uses_the_ddm(monkeypatch):
    """The fallback must not quietly replace the existing default."""
    monkeypatch.setattr(V, "fetch_company", lambda ticker: _bank_data(dividends=True))
    monkeypatch.setattr(V, "fetch_risk_free_rate", lambda *a, **k: (0.065, "test"))
    monkeypatch.setattr(V.riskmodel, "estimate_beta_for_symbol",
                        lambda *a, **k: V.riskmodel.BetaEstimate(
                            raw=1.0, adjusted=1.0, stderr=0.1, r_squared=0.4,
                            observations=400, method="vasicek", index_symbol="^JKSE",
                            prior_weight=0.04))
    assert V.analyze("TESTBANK.JK", market_code="ID")["engine"] == "DDM"


def test_ri_payload_is_json_safe(monkeypatch):
    import json
    from _lib.jsonsafe import clean

    monkeypatch.setattr(V, "fetch_company", lambda ticker: _bank_data(dividends=False))
    monkeypatch.setattr(V, "fetch_risk_free_rate", lambda *a, **k: (0.065, "test"))
    monkeypatch.setattr(V.riskmodel, "estimate_beta_for_symbol",
                        lambda *a, **k: V.riskmodel.BetaEstimate(
                            raw=1.0, adjusted=1.0, stderr=0.1, r_squared=0.4,
                            observations=400, method="vasicek", index_symbol="^JKSE",
                            prior_weight=0.04))
    payload = V.analyze("TESTBANK.JK", market_code="ID")
    json.dumps(clean(payload), allow_nan=False)
    assert payload["streamLabel"] == "Residual income / share"
    assert payload["schedule"] and payload["bridge"]


# --------------------------------------------------------------------------- #
# The rescue form must not have to guess which engine failed
# --------------------------------------------------------------------------- #
def _gapped_bank():
    """A financial with neither dividends nor a usable book value."""
    data = _bank_data(dividends=False)
    data["balance"] = pd.DataFrame()
    data["income"] = pd.DataFrame()
    data["roe_info"] = 0.12
    data["net_income_info"] = np.nan
    return data


def test_every_manual_required_failure_names_its_engine(monkeypatch):
    """Regression: the client used to infer the engine from `suggested`'s keys.

    Residual income sends `payout` and no `netDebt`, which the old inference read
    as a DDM failure — so the rescue form asked for "annual dividend per share",
    the user supplied a BOOK VALUE, and the DDM discounted it as a dividend.
    A confident wrong number produced by guessing identity from a dict's shape.
    """
    monkeypatch.setattr(V, "fetch_company", lambda ticker: _gapped_bank())
    monkeypatch.setattr(V, "fetch_risk_free_rate", lambda *a, **k: (0.065, "test"))
    monkeypatch.setattr(V.riskmodel, "estimate_beta_for_symbol",
                        lambda *a, **k: V.riskmodel.BetaEstimate(
                            raw=1.0, adjusted=1.0, stderr=0.1, r_squared=0.4,
                            observations=400, method="vasicek", index_symbol="^JKSE",
                            prior_weight=0.04))

    with pytest.raises(V.ValuationError) as caught:
        V.analyze("GAPBANK.JK", market_code="ID", engine_choice="ri")

    detail = caught.value.as_detail()
    assert detail["manualRequired"] is True
    assert detail["engine"] == "RI", "an RI failure must identify itself as RI"

    # And the shape alone is genuinely ambiguous, which is why it cannot be used.
    suggested = detail["suggested"]
    assert suggested.get("payout") is not None
    assert suggested.get("netDebt") is None      # identical to a DDM failure


def test_dcf_and_ddm_failures_name_their_engines_too(monkeypatch):
    monkeypatch.setattr(V, "fetch_risk_free_rate", lambda *a, **k: (0.065, "test"))
    monkeypatch.setattr(V.riskmodel, "estimate_beta_for_symbol",
                        lambda *a, **k: V.riskmodel.BetaEstimate(
                            raw=1.0, adjusted=1.0, stderr=0.1, r_squared=0.4,
                            observations=400, method="vasicek", index_symbol="^GSPC",
                            prior_weight=0.04))

    # DCF with no cash-flow statement.
    non_financial = _bank_data(dividends=False)
    non_financial.update(sector="Technology", industry="Software",
                         cashflow=pd.DataFrame(), balance=pd.DataFrame())
    monkeypatch.setattr(V, "fetch_company", lambda ticker: non_financial)
    with pytest.raises(V.ValuationError) as caught:
        V.analyze("TEST", market_code="US")
    assert caught.value.as_detail()["engine"] == "DCF"

    # DDM forced onto a company with no dividends.
    monkeypatch.setattr(V, "fetch_company", lambda ticker: _bank_data(dividends=False))
    with pytest.raises(V.ValuationError) as caught:
        V.analyze("TEST", market_code="US", engine_choice="ddm")
    assert caught.value.as_detail()["engine"] == "DDM"
