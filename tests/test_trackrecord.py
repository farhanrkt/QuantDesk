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
               cash=None, debt=None, ebit=None, **extra):
    """Newest year first, which is how the provider serves them."""
    years = [pd.Timestamp(f"{2025 - i}-12-31") for i in range(len(net_income))]

    def frame(rows):
        return pd.DataFrame({year: {label: values[i] for label, values in rows.items()}
                             for i, year in enumerate(years)})

    income = {"Net Income": net_income}
    if revenue is not None:
        income["Total Revenue"] = revenue
    if ebit is not None:
        income["EBIT"] = ebit
    flows = {}
    if ocf is not None:
        flows["Operating Cash Flow"] = ocf
    if fcf is not None:
        flows["Free Cash Flow"] = fcf
    sheet = {}
    if equity:
        sheet["Stockholders Equity"] = equity
    if cash is not None:
        sheet["Cash And Cash Equivalents"] = cash
    if debt is not None:
        sheet["Long Term Debt"] = debt
    out = {"income": frame(income),
           "cashflow": frame(flows) if flows else pd.DataFrame(),
           "balance": frame(sheet) if sheet else pd.DataFrame(),
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


# --------------------------------------------------------------------------- #
# what it owes
#
# NO "TOO MUCH DEBT" FLAG EXISTS, AND THE MEASUREMENT IS WHY. Across the 467
# non-financial Indonesian listings in the local cache with an EBIT line, 181 —
# 39% — carry net cash, and of the 242 that borrow the MEDIAN is 3.0x EBITDA.
# The textbook line for "levered" is 3x, which here is the middle of the
# distribution: a flag there would mark half the borrowers and say nothing.
# --------------------------------------------------------------------------- #
def test_net_cash_is_reported_against_how_common_it_is():
    out = T.read(statements([10.0, 8.0, 6.0, 5.0], revenue=[100.0, 90.0, 80.0, 70.0],
                            cash=[500.0, 400.0, 300.0, 200.0],
                            debt=[100.0, 100.0, 100.0, 100.0],
                            ebit=[20.0, 16.0, 12.0, 10.0]))
    assert out["netCash"] is True
    assert out["netDebt"] == pytest.approx(-400.0)
    assert "39% of this market" in out["reading"]


def test_leverage_is_quoted_against_the_markets_own_median():
    out = T.read(statements([10.0, 8.0, 6.0, 5.0], revenue=[100.0, 90.0, 80.0, 70.0],
                            cash=[10.0, 10.0, 10.0, 10.0],
                            debt=[210.0, 200.0, 190.0, 180.0],
                            ebit=[20.0, 16.0, 12.0, 10.0]))
    assert out["netCash"] is False
    assert out["netDebtToEbitda"] == pytest.approx(10.0)
    assert "median of 3.0" in out["reading"]
    assert "more levered" in out["reading"]
    assert "comparison and not a verdict" in out["reading"]


def test_no_arbitrary_over_indebted_flag_ships():
    """Measured and refused; see the block comment above.

    A boolean here would put a line through the middle of the distribution and
    read as a warning. The ratio and the market's median ship instead.
    """
    out = T.read(statements([10.0, 8.0, 6.0, 5.0], revenue=[100.0, 90.0, 80.0, 70.0],
                            cash=[10.0, 10.0, 10.0, 10.0], debt=[900.0] * 4,
                            ebit=[20.0, 16.0, 12.0, 10.0]))
    assert "overLevered" not in out
    assert "distressed" not in out


def test_borrowings_are_withheld_for_a_lender():
    """A bank's borrowings ARE its business; netting them describes nothing."""
    out = T.read(statements([10.0, 8.0, 6.0, 5.0], revenue=[100.0, 90.0, 80.0, 70.0],
                            cash=[10.0] * 4, debt=[900.0] * 4, ebit=[20.0] * 4,
                            sector="Financial Services", industry="Banks—Regional"))
    assert out["netDebt"] is None and out["netCash"] is None
    assert out["netDebtToEbitda"] is None


def test_borrowings_without_earnings_to_measure_them_against_say_so():
    out = T.read(statements([10.0, 8.0, 6.0, 5.0], revenue=[100.0, 90.0, 80.0, 70.0],
                            cash=[10.0] * 4, debt=[900.0] * 4))
    assert out["netCash"] is False
    assert out["netDebtToEbitda"] is None
    assert "not established here" in out["reading"]


def test_a_missing_balance_sheet_is_not_reported_as_net_cash():
    """The bug this review found, as a test.

    Each of the three lines defaulted to zero, so subtracting gave net debt of
    zero for a company whose balance sheet never arrived — and zero net debt
    reads as `netCash: True`, so the app told a reader it "holds more cash than
    borrowings, which 39% of this market also does". A fabricated fact about a
    company nothing was known about.
    """
    out = T.read(statements([10.0, 8.0, 6.0, 5.0], revenue=[100.0, 90.0, 80.0, 70.0]))
    assert out["netCash"] is None
    assert out["netDebt"] is None
    assert "unknown here rather than settled either way" in out["reading"]
    assert "holds more cash than borrowings" not in out["reading"]


def test_a_partial_balance_sheet_reads_the_missing_lines_as_zero():
    """A sheet that reports cash and carries no debt line is debt-free.

    That is the conventional reading and the one `valuation.py` takes; the
    refusal above is for a sheet where NOTHING arrived, which is a different
    thing from a sheet that says nothing is owed.
    """
    out = T.read(statements([10.0, 8.0, 6.0, 5.0], revenue=[100.0, 90.0, 80.0, 70.0],
                            cash=[500.0, 400.0, 300.0, 200.0]))
    assert out["netCash"] is True
    assert out["netDebt"] == pytest.approx(-500.0)


def test_a_lender_and_an_unread_sheet_are_both_none_but_read_differently():
    lender = T.read(statements([10.0, 8.0, 6.0, 5.0], revenue=[100.0] * 4,
                               cash=[10.0] * 4, debt=[900.0] * 4,
                               sector="Financial Services", industry="Banks—Regional"))
    unread = T.read(statements([10.0, 8.0, 6.0, 5.0], revenue=[100.0] * 4))
    assert lender["netCash"] is None and unread["netCash"] is None
    assert "would describe nothing" in lender["reading"]
    assert "No balance sheet came back" in unread["reading"]
