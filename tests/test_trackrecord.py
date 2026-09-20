"""What the filings say the business has done — profits, cash and growth.

WHY THESE TESTS EXIST

"Profitable" sounds like a quality filter and is not one. Measured on the 523
Indonesian listings in the local cache with three or more years of statements,
350 of them — 67% — are profitable in every year their filings cover. A flag
that admits two thirds of a market is not a distinction, and shipping one as
though it were is the mistake this repository has made before under other names.

The narrowing is the conjunction, and each step's base rate is reported with it:
67% profitable every year, 58% also cash-backed, 14% also growing revenue at or
above the market's own top quartile (14.8%, hence GROWING_AT = 0.15).

WHAT THESE TESTS PROTECT

1. THE BASE RATES TRAVEL WITH THE FLAGS. A client cannot render "profitable
   every year" without being handed how ordinary that is.
2. A SHORT WINDOW IS NAMED, NEVER IMPLIED AWAY. Two years of statements is not
   a track record and the module refuses rather than reporting "2 of 2".
3. NEGATIVE FREE CASH FLOW IS REPORTED, NOT PENALISED. KETR.JK — the name this
   was built for — is profitable in all four years and grew revenue at 28.6% a
   year while free cash flow was negative in three of them, because it was
   laying cable. A screen that demoted it for that would be wrong about the one
   company it exists to find.
4. ONE HEAVY YEAR IS NOT A BUILD-OUT. Calling a single negative year a pattern
   is a story told over one observation.
5. A ZERO BASE HAS NO GROWTH RATE. `(new/0) ** (1/n)` is an infinity that sorts
   to the top of any list of fast growers.
6. FREE CASH FLOW IS WITHHELD FOR FINANCIALS. Capital spending on a lender's
   accounts is premises and software, so the figure describes nothing.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from _lib import trackrecord as T


def statements(net_income, revenue=None, ocf=None, fcf=None, equity=None,
               **extra):
    """Newest year first, which is how the provider serves them."""
    years = [pd.Timestamp(f"{2025 - i}-12-31") for i in range(len(net_income))]

    def frame(rows):
        return pd.DataFrame({year: {label: values[i] for label, values in rows.items()}
                             for i, year in enumerate(years)})

    income = {"Net Income": net_income}
    if revenue is not None:
        income["Total Revenue"] = revenue
    cash = {}
    if ocf is not None:
        cash["Operating Cash Flow"] = ocf
    if fcf is not None:
        cash["Free Cash Flow"] = fcf
    out = {"income": frame(income),
           "cashflow": frame(cash) if cash else pd.DataFrame(),
           "balance": frame({"Stockholders Equity": equity}) if equity else pd.DataFrame(),
           "sector": "Technology", "industry": "Communication Equipment"}
    out.update(extra)
    return out


def test_a_short_window_is_refused_rather_than_reported():
    out = T.read(statements([10.0, 8.0]))
    assert out["available"] is False
    assert out["yearsAvailable"] == 2
    assert "3 is the fewest" in out["reason"]


def test_every_year_profitable_is_reported_with_how_ordinary_it_is():
    out = T.read(statements([10.0, 8.0, 6.0, 5.0], revenue=[100.0, 90.0, 80.0, 70.0]))
    assert out["everyYearProfitable"] is True
    assert out["yearsProfitable"] == 4 and out["yearsAvailable"] == 4
    assert out["baseRates"]["everyYearProfitable"] == pytest.approx(0.67, abs=0.01)
    assert "two thirds" in out["reading"]


def test_a_loss_year_is_counted_not_hidden():
    out = T.read(statements([10.0, -3.0, 6.0, 5.0], revenue=[100.0, 90.0, 80.0, 70.0]))
    assert out["everyYearProfitable"] is False
    assert out["yearsProfitable"] == 3
    assert "3 of 4" in out["reading"]


def test_the_window_is_always_named():
    out = T.read(statements([10.0, 8.0, 6.0, 5.0], revenue=[100.0, 90.0, 80.0, 70.0]))
    assert "4 years is a short window" in out["reading"]
    assert "does not span a cycle" in out["reading"]


# --------------------------------------------------------------------------- #
# growth
# --------------------------------------------------------------------------- #
def test_growth_is_compounded_over_the_years_available():
    # 70 -> 100 over three periods.
    out = T.read(statements([10.0, 8.0, 6.0, 5.0], revenue=[100.0, 90.0, 80.0, 70.0]))
    assert out["revenueCagr"] == pytest.approx((100 / 70) ** (1 / 3) - 1)


def test_growing_is_the_markets_own_top_quartile():
    assert T.GROWING_AT == pytest.approx(0.15)
    slow = T.read(statements([10.0, 9.0, 8.0, 7.0], revenue=[110.0, 107.0, 104.0, 100.0]))
    assert slow["growing"] is False
    assert "market median of about 5%" in slow["reading"]

    fast = T.read(statements([10.0, 8.0, 6.0, 5.0], revenue=[200.0, 150.0, 120.0, 100.0]))
    assert fast["growing"] is True
    assert "top quartile" in fast["reading"]


def test_a_zero_base_has_no_growth_rate_rather_than_an_infinite_one():
    out = T.read(statements([10.0, 8.0, 6.0, 5.0], revenue=[100.0, 50.0, 10.0, 0.0]))
    assert out["revenueCagr"] is None
    assert out["growing"] is False
    assert np.isfinite(out["latestNetMargin"] or 0.0)


def test_shrinking_revenue_is_a_negative_rate_not_a_refusal():
    out = T.read(statements([10.0, 8.0, 6.0, 5.0], revenue=[70.0, 80.0, 90.0, 100.0]))
    assert out["revenueCagr"] < 0
    assert out["growing"] is False


# --------------------------------------------------------------------------- #
# cash
# --------------------------------------------------------------------------- #
def test_profit_that_did_not_arrive_as_cash_is_said_so():
    out = T.read(statements([10.0, 8.0, 6.0, 5.0], revenue=[100.0, 90.0, 80.0, 70.0],
                            ocf=[-4.0, 3.0, 2.0, 1.0]))
    assert out["operatingCashFlowPositive"] is False
    assert out["consistentlyProfitable"] is False
    assert "has not arrived as cash" in out["reading"]


def test_a_build_out_is_described_not_penalised():
    """KETR.JK's shape: profitable and growing, free cash flow negative."""
    out = T.read(statements([10.0, 8.0, 6.0, 5.0], revenue=[200.0, 150.0, 120.0, 100.0],
                            ocf=[9.0, 7.0, 5.0, 4.0], fcf=[5.0, -8.0, -12.0, -9.0]))
    assert out["everyYearProfitable"] is True
    assert out["growing"] is True
    assert out["consistentlyProfitable"] is True     # not demoted for the spending
    assert out["freeCashFlowYears"] == 1
    assert "build-out" in out["reading"]


def test_one_negative_year_is_not_called_a_build_out():
    out = T.read(statements([10.0, 8.0, 6.0, 5.0], revenue=[100.0, 90.0, 80.0, 70.0],
                            ocf=[9.0, 7.0, 5.0, 4.0], fcf=[5.0, 4.0, -1.0, 3.0]))
    assert "build-out" not in out["reading"]
    assert "single heavy year" in out["reading"]


def test_free_cash_flow_is_withheld_for_a_lender():
    out = T.read(statements([10.0, 8.0, 6.0, 5.0], revenue=[100.0, 90.0, 80.0, 70.0],
                            ocf=[9.0, 7.0, 5.0, 4.0], fcf=[5.0, -8.0, -12.0, -9.0],
                            sector="Financial Services", industry="Banks—Regional"))
    assert out["financial"] is True
    assert out["freeCashFlowYears"] is None
    assert "would describe nothing" in out["reading"]
    # Everything that DOES transfer to a bank still reports.
    assert out["everyYearProfitable"] is True
    assert out["operatingCashFlowPositive"] is True


# --------------------------------------------------------------------------- #
# margins and returns
# --------------------------------------------------------------------------- #
def test_margin_and_return_on_equity_come_from_the_latest_year():
    out = T.read(statements([10.0, 8.0, 6.0, 5.0], revenue=[100.0, 90.0, 80.0, 70.0],
                            equity=[50.0, 45.0, 40.0, 35.0]))
    assert out["latestNetMargin"] == pytest.approx(0.10)
    assert out["returnOnEquity"] == pytest.approx(0.20)


def test_no_statements_at_all_is_a_stated_refusal():
    out = T.read({})
    assert out["available"] is False
    assert out["yearsAvailable"] == 0
    assert "came back" in out["reason"]


def test_none_is_not_an_error():
    assert T.read(None)["available"] is False
