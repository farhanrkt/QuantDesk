"""Piotroski / Altman / Beneish, checked against hand arithmetic.

Statements are built by hand here so every input is known, which means the
score can be computed independently on paper and compared. The published
coefficients are the contract: if someone mistypes 6.72 as 6.27, these fail.
"""

from __future__ import annotations

import pandas as pd
import pytest

from _lib import quality as Q

YEARS = ["2025", "2024"]


def statements(**rows) -> pd.DataFrame:
    """Two fiscal years, newest first — the orientation yfinance returns."""
    return pd.DataFrame({YEARS[0]: [v[0] for v in rows.values()],
                         YEARS[1]: [v[1] for v in rows.values()]},
                        index=list(rows.keys()))


@pytest.fixture
def healthy():
    """A clean, improving, non-financial manufacturer."""
    income = statements(**{
        "Total Revenue": (1200.0, 1000.0),
        "Cost Of Revenue": (600.0, 550.0),
        "Net Income": (150.0, 100.0),
        "EBIT": (200.0, 150.0),
        "Selling General And Administration": (200.0, 180.0),
    })
    balance = statements(**{
        "Total Assets": (2000.0, 1900.0),
        "Current Assets": (800.0, 700.0),
        "Current Liabilities": (400.0, 420.0),
        "Retained Earnings": (600.0, 500.0),
        "Total Liabilities Net Minority Interest": (900.0, 950.0),
        "Stockholders Equity": (1100.0, 950.0),
        "Long Term Debt": (300.0, 400.0),
        "Accounts Receivable": (180.0, 160.0),
        "Net PPE": (900.0, 880.0),
        "Ordinary Shares Number": (100.0, 100.0),
    })
    cashflow = statements(**{
        "Operating Cash Flow": (250.0, 180.0),
        "Depreciation And Amortization": (90.0, 85.0),
    })
    return income, balance, cashflow


# --------------------------------------------------------------------------- #
# Applicability
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(("sector", "industry"), [
    ("Financial Services", "Banks—Diversified"),
    ("", "Regional Banks"),
    ("Financial Services", ""),
    ("", "Insurance—Life"),
    ("", "Capital Markets"),
])
def test_financials_are_excluded(sector, industry):
    assert Q.is_financial(sector, industry) is True


@pytest.mark.parametrize(("sector", "industry"), [
    ("Technology", "Consumer Electronics"),
    ("Consumer Defensive", "Beverages—Non-Alcoholic"),
    ("Communication Services", "Telecom Services"),
])
def test_non_financials_are_included(sector, industry):
    assert Q.is_financial(sector, industry) is False


def test_analyze_refuses_a_bank_rather_than_scoring_it(healthy):
    income, balance, cashflow = healthy
    result = Q.analyze({"sector": "Financial Services", "industry": "Banks",
                        "income": income, "balance": balance, "cashflow": cashflow})
    assert result["applicable"] is False
    assert result["piotroski"] is None and result["altman"] is None
    assert "bank" in result["reason"].lower()
    # The CAUSE is a value, not a keyword to be sniffed out of the prose. A
    # designed refusal and a data gap are different facts and callers act on
    # the difference — see `_lib/pretrade.py`, which words its "not checked"
    # reason per model for one and quotes the gap verbatim for the other.
    assert result["cause"] == "financial"


def test_analyze_refuses_when_statements_are_empty():
    result = Q.analyze({"sector": "Technology", "industry": "Software",
                        "income": pd.DataFrame(), "balance": pd.DataFrame(),
                        "cashflow": pd.DataFrame()})
    assert result["applicable"] is False
    assert result["cause"] == "no-statements", "a data gap must not read as a refusal"


# --------------------------------------------------------------------------- #
# Piotroski
# --------------------------------------------------------------------------- #
def test_piotroski_scores_a_healthy_company_high(healthy):
    result = Q.piotroski_f_score(*healthy)
    assert result["signalsAvailable"] == 9
    assert result["score"] >= 8
    assert result["band"] in {"strong", "solid"}


def test_piotroski_penalises_a_deteriorating_company(healthy):
    income, balance, cashflow = healthy
    # Flip every trend: profits down, leverage up, dilution, margins compressing.
    income.loc["Net Income"] = [40.0, 100.0]
    income.loc["Cost Of Revenue"] = [900.0, 550.0]
    balance.loc["Long Term Debt"] = [600.0, 400.0]
    balance.loc["Current Liabilities"] = [700.0, 420.0]
    balance.loc["Ordinary Shares Number"] = [130.0, 100.0]
    cashflow.loc["Operating Cash Flow"] = [-20.0, 180.0]

    result = Q.piotroski_f_score(income, balance, cashflow)
    assert result["score"] <= 2
    assert result["band"] == "weak"


def test_piotroski_never_awards_a_point_for_missing_data():
    """The inflation bug: an unavailable signal must score nothing, not a pass."""
    empty = pd.DataFrame()
    result = Q.piotroski_f_score(empty, empty, empty)
    assert result["score"] == 0
    assert result["signalsAvailable"] == 0
    assert result["maxScore"] == 0
    assert all(s["passed"] is None for s in result["signals"])
    assert result["band"] == "unknown"


def test_piotroski_reports_the_denominator_it_actually_used(healthy):
    """5/7 and 5/9 mean different things and must not be conflated."""
    income, balance, cashflow = healthy
    balance = balance.drop(index=["Current Assets", "Current Liabilities"])
    result = Q.piotroski_f_score(income, balance, cashflow)
    assert result["signalsAvailable"] < 9
    assert result["maxScore"] == result["signalsAvailable"]
    assert result["score"] <= result["maxScore"]


# --------------------------------------------------------------------------- #
# Altman Z''-EM
# --------------------------------------------------------------------------- #
def test_altman_matches_hand_arithmetic(healthy):
    income, balance, _ = healthy
    result = Q.altman_z_em(income, balance)

    x1 = (800.0 - 400.0) / 2000.0
    x2 = 600.0 / 2000.0
    x3 = 200.0 / 2000.0
    x4 = 1100.0 / 900.0
    expected = 3.25 + 6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4

    assert result["score"] == pytest.approx(expected, rel=1e-12)
    assert result["components"]["workingCapitalToAssets"] == pytest.approx(x1)
    assert result["band"] == "safe"


def test_altman_flags_a_distressed_balance_sheet():
    income = statements(**{"EBIT": (-300.0, -100.0), "Total Revenue": (500.0, 600.0)})
    balance = statements(**{
        "Total Assets": (1000.0, 1200.0),
        "Current Assets": (100.0, 150.0),
        "Current Liabilities": (700.0, 600.0),
        "Retained Earnings": (-400.0, -200.0),
        "Total Liabilities Net Minority Interest": (1100.0, 1000.0),
        "Stockholders Equity": (-100.0, 200.0),
    })
    result = Q.altman_z_em(income, balance)
    assert result["band"] == "distress"
    assert result["score"] < 4.35


def test_altman_declines_without_total_assets():
    result = Q.altman_z_em(pd.DataFrame(), pd.DataFrame())
    assert result["score"] is None
    assert result["band"] == "unknown"


def test_altman_names_what_is_missing():
    balance = statements(**{"Total Assets": (1000.0, 1000.0)})
    result = Q.altman_z_em(pd.DataFrame(), balance)
    assert result["score"] is None
    assert "EBIT" in result["reading"]


# --------------------------------------------------------------------------- #
# Beneish
# --------------------------------------------------------------------------- #
def test_beneish_matches_hand_arithmetic(healthy):
    income, balance, cashflow = healthy
    result = Q.beneish_m_score(income, balance, cashflow)
    idx = result["indices"]

    dsri = (180.0 / 1200.0) / (160.0 / 1000.0)
    gmi = ((1000.0 - 550.0) / 1000.0) / ((1200.0 - 600.0) / 1200.0)
    sgi = 1200.0 / 1000.0
    tata = (150.0 - 250.0) / 2000.0

    assert idx["DSRI"] == pytest.approx(dsri)
    assert idx["GMI"] == pytest.approx(gmi)
    assert idx["SGI"] == pytest.approx(sgi)
    assert idx["TATA"] == pytest.approx(tata)

    expected = (-4.84 + 0.920 * idx["DSRI"] + 0.528 * idx["GMI"] + 0.404 * idx["AQI"]
                + 0.892 * idx["SGI"] + 0.115 * idx["DEPI"] - 0.172 * idx["SGAI"]
                + 4.679 * tata - 0.327 * idx["LVGI"])
    assert result["score"] == pytest.approx(expected, rel=1e-12)


def test_beneish_flags_aggressive_accruals(healthy):
    """Profit far above cash flow with receivables ballooning is the signature."""
    income, balance, cashflow = healthy
    income.loc["Net Income"] = [400.0, 100.0]
    balance.loc["Accounts Receivable"] = [600.0, 160.0]
    cashflow.loc["Operating Cash Flow"] = [20.0, 180.0]

    result = Q.beneish_m_score(income, balance, cashflow)
    assert result["score"] > -1.78
    assert result["band"] == "flagged"


def test_beneish_refuses_a_partial_score():
    """Three of eight indices is not a Beneish score."""
    income = statements(**{"Total Revenue": (1200.0, 1000.0)})
    result = Q.beneish_m_score(income, pd.DataFrame(), pd.DataFrame())
    assert result["score"] is None
    assert result["band"] == "unknown"
    assert result["indicesAvailable"] < Q._MIN_BENEISH_INDICES
    assert "too few" in result["reading"]


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def test_analyze_produces_a_votable_verdict(healthy):
    income, balance, cashflow = healthy
    result = Q.analyze({"sector": "Industrials", "industry": "Machinery",
                        "income": income, "balance": balance, "cashflow": cashflow})
    assert result["applicable"] is True
    assert result["verdict"] in {"SOUND", "NEUTRAL", "CONCERNS"}
    assert result["tone"] in {"bull", "neutral", "bear"}
    assert result["headline"]


def test_distress_dominates_the_verdict():
    income = statements(**{"EBIT": (-300.0, -100.0), "Total Revenue": (500.0, 600.0),
                           "Net Income": (-250.0, -80.0), "Cost Of Revenue": (450.0, 500.0)})
    balance = statements(**{
        "Total Assets": (1000.0, 1200.0), "Current Assets": (100.0, 150.0),
        "Current Liabilities": (700.0, 600.0), "Retained Earnings": (-400.0, -200.0),
        "Total Liabilities Net Minority Interest": (1100.0, 1000.0),
        "Stockholders Equity": (-100.0, 200.0), "Long Term Debt": (400.0, 300.0),
        "Ordinary Shares Number": (150.0, 100.0), "Accounts Receivable": (50.0, 60.0),
        "Net PPE": (500.0, 600.0),
    })
    cashflow = statements(**{"Operating Cash Flow": (-100.0, 20.0),
                             "Depreciation And Amortization": (50.0, 55.0)})
    result = Q.analyze({"sector": "Industrials", "industry": "Machinery",
                        "income": income, "balance": balance, "cashflow": cashflow})
    assert result["verdict"] == "CONCERNS"
    assert "solvency" in result["headline"]


def test_quality_payload_is_json_safe(healthy):
    import json
    from _lib.jsonsafe import clean

    income, balance, cashflow = healthy
    result = Q.analyze({"sector": "Industrials", "industry": "Machinery",
                        "income": income, "balance": balance, "cashflow": cashflow})
    json.dumps(clean(result), allow_nan=False)
