"""
quality.py
==========
Engine 4 — accounting quality, financial strength and solvency.

WHY A FOURTH LENS
-----------------
Flow, trend and value all read the same company from the outside. None of them
opens the filings and asks whether the business is sound. That gap matters most
exactly where the other three are loudest: a discounted cash flow on a company
sliding toward insolvency is arithmetic, not a valuation, and the DCF will
happily return a large "undervalued" number for a firm whose equity is about to
be worth nothing.

Three published scores, each answering a different question:

  Piotroski F-Score   Is the fundamental trend improving?      0-9, higher better
  Altman Z''-EM       How far from financial distress?         higher better
  Beneish M-Score     Do the accruals look manipulated?        lower better

APPLICABILITY IS ENFORCED, NOT ASSUMED
--------------------------------------
None of the three applies to banks or insurers, and this module refuses rather
than returning a number that looks fine. Piotroski (2000) explicitly excluded
financial firms; Altman built Z on manufacturers, and the working-capital and
current-ratio terms are meaningless for an institution with no operating cycle;
Beneish's indices assume a receivables-and-inventory revenue model. Silence is
the correct output for BBCA. The bank instead gets the residual income engine
(see `valuation.py`), which is built for exactly that balance sheet.

References
----------
Piotroski, J. D. (2000). "Value Investing: The Use of Historical Financial
    Statement Information to Separate Winners from Losers." Journal of
    Accounting Research 38, 1-41.
Altman, E. I. (1968). "Financial Ratios, Discriminant Analysis and the
    Prediction of Corporate Bankruptcy." Journal of Finance 23(4), 589-609.
Altman, E. I. (2005). "An emerging market credit scoring system for corporates."
    Emerging Markets Review 6(4), 311-323.
Beneish, M. D. (1999). "The Detection of Earnings Manipulation." Financial
    Analysts Journal 55(5), 24-36.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from .valuation import _get_row, _safe_float

# Sectors and industry keywords the three models were never fitted on.
_FINANCIAL_SECTORS = {"financial services", "financials"}
_FINANCIAL_KEYWORDS = ("bank", "insurance", "insurer", "capital markets",
                       "asset management", "credit services", "reinsurance")

# Beneish combines eight indices; a score assembled from half of them is not a
# Beneish score. Below this many, the module declines to report one.
_MIN_BENEISH_INDICES = 6


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def is_financial(sector: str, industry: str) -> bool:
    """Same routing rule the valuation engine uses, applied for exclusion."""
    s = (sector or "").strip().lower()
    i = (industry or "").strip().lower()
    return s in _FINANCIAL_SECTORS or any(k in i for k in _FINANCIAL_KEYWORDS)


def _series(statement, key: str) -> Optional[pd.Series]:
    row = _get_row(statement, key)
    return row if row is not None else None


def _at(statement, key: str, period: int = 0) -> float:
    """One line item at `period` (0 = most recent fiscal year, 1 = prior)."""
    row = _series(statement, key)
    if row is None or period >= len(row):
        return np.nan
    return _safe_float(row.iloc[period])


def _ratio(numerator: float, denominator: float) -> float:
    if not np.isfinite(numerator) or not np.isfinite(denominator) or denominator == 0:
        return np.nan
    return numerator / denominator


def _nullable(value) -> Optional[float]:
    out = _safe_float(value)
    return float(out) if np.isfinite(out) else None


# --------------------------------------------------------------------------- #
# Piotroski F-Score
# --------------------------------------------------------------------------- #
def piotroski_f_score(income, balance, cashflow) -> dict:
    """Nine binary fundamental signals, scored 0-9.

    Each signal is scored only if BOTH years it needs are available; an
    unavailable signal scores nothing and is reported as such, so a 5/9 built
    from nine tests reads differently from a 5/7 built from seven. Awarding a
    point for missing data would be the easy bug here and it inflates every
    thin-coverage listing.
    """
    signals: list[dict] = []

    def record(name: str, passed, detail: str = "") -> None:
        signals.append({
            "name": name,
            "passed": None if passed is None else bool(passed),
            "detail": detail,
        })

    assets_now, assets_prior = _at(balance, "total_assets", 0), _at(balance, "total_assets", 1)
    income_now, income_prior = _at(income, "net_income", 0), _at(income, "net_income", 1)
    cfo_now = _at(cashflow, "ocf", 0)

    roa_now = _ratio(income_now, assets_now)
    roa_prior = _ratio(income_prior, assets_prior)

    # --- profitability ---
    record("Return on assets positive", roa_now > 0 if np.isfinite(roa_now) else None,
           f"ROA {roa_now:.1%}" if np.isfinite(roa_now) else "unavailable")
    record("Operating cash flow positive", cfo_now > 0 if np.isfinite(cfo_now) else None,
           "" if np.isfinite(cfo_now) else "unavailable")
    record("Return on assets improving",
           roa_now > roa_prior if np.isfinite(roa_now) and np.isfinite(roa_prior) else None,
           f"{roa_prior:.1%} -> {roa_now:.1%}"
           if np.isfinite(roa_now) and np.isfinite(roa_prior) else "unavailable")

    cfo_over_assets = _ratio(cfo_now, assets_now)
    record("Cash flow exceeds accounting profit",
           cfo_over_assets > roa_now
           if np.isfinite(cfo_over_assets) and np.isfinite(roa_now) else None,
           "earnings backed by cash rather than accruals")

    # --- leverage, liquidity, source of funds ---
    ltd_now, ltd_prior = _at(balance, "long_term_debt", 0), _at(balance, "long_term_debt", 1)
    leverage_now = _ratio(ltd_now, assets_now)
    leverage_prior = _ratio(ltd_prior, assets_prior)
    record("Leverage falling",
           leverage_now < leverage_prior
           if np.isfinite(leverage_now) and np.isfinite(leverage_prior) else None,
           f"{leverage_prior:.1%} -> {leverage_now:.1%}"
           if np.isfinite(leverage_now) and np.isfinite(leverage_prior) else "unavailable")

    current_now = _ratio(_at(balance, "current_assets", 0), _at(balance, "current_liabilities", 0))
    current_prior = _ratio(_at(balance, "current_assets", 1), _at(balance, "current_liabilities", 1))
    record("Current ratio improving",
           current_now > current_prior
           if np.isfinite(current_now) and np.isfinite(current_prior) else None,
           f"{current_prior:.2f} -> {current_now:.2f}"
           if np.isfinite(current_now) and np.isfinite(current_prior) else "unavailable")

    shares_now, shares_prior = _at(balance, "shares_issued", 0), _at(balance, "shares_issued", 1)
    record("No dilution",
           shares_now <= shares_prior * 1.001
           if np.isfinite(shares_now) and np.isfinite(shares_prior) else None,
           "share count did not rise" if np.isfinite(shares_now) else "unavailable")

    # --- operating efficiency ---
    revenue_now, revenue_prior = _at(income, "revenue", 0), _at(income, "revenue", 1)
    cogs_now, cogs_prior = _at(income, "cogs", 0), _at(income, "cogs", 1)
    margin_now = _ratio(revenue_now - cogs_now, revenue_now)
    margin_prior = _ratio(revenue_prior - cogs_prior, revenue_prior)
    record("Gross margin expanding",
           margin_now > margin_prior
           if np.isfinite(margin_now) and np.isfinite(margin_prior) else None,
           f"{margin_prior:.1%} -> {margin_now:.1%}"
           if np.isfinite(margin_now) and np.isfinite(margin_prior) else "unavailable")

    turnover_now = _ratio(revenue_now, assets_now)
    turnover_prior = _ratio(revenue_prior, assets_prior)
    record("Asset turnover improving",
           turnover_now > turnover_prior
           if np.isfinite(turnover_now) and np.isfinite(turnover_prior) else None,
           f"{turnover_prior:.2f}x -> {turnover_now:.2f}x"
           if np.isfinite(turnover_now) and np.isfinite(turnover_prior) else "unavailable")

    scored = [s for s in signals if s["passed"] is not None]
    score = sum(1 for s in scored if s["passed"])

    if not scored:
        band, reading = "unknown", "No usable statement history."
    elif score >= 8:
        band, reading = "strong", "Fundamentals improving on almost every axis."
    elif score >= 6:
        band, reading = "solid", "More improving than deteriorating."
    elif score >= 4:
        band, reading = "mixed", "No clear fundamental direction."
    else:
        band, reading = "weak", "Deteriorating on most axes Piotroski measures."

    return {
        "score": int(score),
        "maxScore": len(scored),
        "signalsAvailable": len(scored),
        "signalsTotal": len(signals),
        "band": band,
        "reading": reading,
        "signals": signals,
    }


# --------------------------------------------------------------------------- #
# Altman Z''-score, emerging-market variant
# --------------------------------------------------------------------------- #
def altman_z_em(income, balance) -> dict:
    """Altman's Z''-score with the emerging-market constant.

        Z'' = 3.25 + 6.56*X1 + 3.26*X2 + 6.72*X3 + 1.05*X4

    X1 working capital / total assets      X3 EBIT / total assets
    X2 retained earnings / total assets    X4 book equity / total liabilities

    The Z'' form drops the sales/assets term of the original Z, which makes it
    comparable across industries with very different asset turnover. The +3.25
    constant is Altman's emerging-market adjustment, calibrated so the score maps
    onto US bond-equivalent ratings; it is the right variant for an IDX listing
    and harmless for a US one.
    """
    assets = _at(balance, "total_assets")
    if not np.isfinite(assets) or assets <= 0:
        return {"score": None, "band": "unknown",
                "reading": "Total assets unavailable, so no solvency score.",
                "components": {}}

    working_capital = _at(balance, "current_assets") - _at(balance, "current_liabilities")
    retained = _at(balance, "retained_earnings")
    ebit = _at(income, "ebit")
    equity = _at(balance, "equity")
    liabilities = _at(balance, "total_liabilities")

    x1 = _ratio(working_capital, assets)
    x2 = _ratio(retained, assets)
    x3 = _ratio(ebit, assets)
    x4 = _ratio(equity, liabilities)

    components = {"workingCapitalToAssets": _nullable(x1), "retainedToAssets": _nullable(x2),
                  "ebitToAssets": _nullable(x3), "equityToLiabilities": _nullable(x4)}

    if not all(np.isfinite(v) for v in (x1, x2, x3, x4)):
        missing = [name for name, value in
                   zip(("working capital", "retained earnings", "EBIT", "total liabilities"),
                       (x1, x2, x3, x4), strict=True) if not np.isfinite(value)]
        return {"score": None, "band": "unknown",
                "reading": f"Cannot score: {', '.join(missing)} unavailable.",
                "components": components}

    score = 3.25 + 6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4

    # Altman's Z'' zones (2.6 / 1.1) shifted by the +3.25 EM constant.
    if score > 5.85:
        band, reading = "safe", "Comfortably outside Altman's distress zone."
    elif score >= 4.35:
        band, reading = "grey", "Altman's grey zone — neither safe nor distressed."
    else:
        band, reading = "distress", ("Inside Altman's distress zone. A going-concern "
                                     "question outranks any valuation.")

    return {"score": float(score), "band": band, "reading": reading,
            "components": components}


# --------------------------------------------------------------------------- #
# Beneish M-Score
# --------------------------------------------------------------------------- #
def beneish_m_score(income, balance, cashflow) -> dict:
    """Eight-index earnings-manipulation model.

        M = -4.84 + 0.920*DSRI + 0.528*GMI + 0.404*AQI + 0.892*SGI
            + 0.115*DEPI - 0.172*SGAI + 4.679*TATA - 0.327*LVGI

    M above -1.78 flags a company with characteristics common among known
    manipulators. It is a SCREEN, not an accusation: Beneish reports it
    correctly classifying about three-quarters of manipulators, which also means
    a large false-positive rate on a population where manipulation is rare.

    Missing indices default to 1.0 (the "no change year over year" value) so a
    partial score stays on scale, but the module refuses to report at all below
    `_MIN_BENEISH_INDICES` — an M-Score assembled from three of eight indices is
    not evidence of anything.
    """
    def pair(statement, key):
        return _at(statement, key, 0), _at(statement, key, 1)

    revenue_now, revenue_prior = pair(income, "revenue")
    receivables_now, receivables_prior = pair(balance, "receivables")
    cogs_now, cogs_prior = pair(income, "cogs")
    assets_now, assets_prior = pair(balance, "total_assets")
    current_now, current_prior = pair(balance, "current_assets")
    ppe_now, ppe_prior = pair(balance, "ppe")
    depreciation_now, depreciation_prior = pair(cashflow, "depreciation")
    sga_now, sga_prior = pair(income, "sga")
    ltd_now, ltd_prior = pair(balance, "long_term_debt")
    curliab_now, curliab_prior = pair(balance, "current_liabilities")
    net_income_now = _at(income, "net_income", 0)
    cfo_now = _at(cashflow, "ocf", 0)

    indices: dict[str, Optional[float]] = {}

    def index_of(name: str, value: float) -> float:
        if np.isfinite(value) and value > 0:
            indices[name] = float(value)
            return float(value)
        indices[name] = None
        return 1.0

    dsri = index_of("DSRI", _ratio(_ratio(receivables_now, revenue_now),
                                   _ratio(receivables_prior, revenue_prior)))
    margin_now = _ratio(revenue_now - cogs_now, revenue_now)
    margin_prior = _ratio(revenue_prior - cogs_prior, revenue_prior)
    gmi = index_of("GMI", _ratio(margin_prior, margin_now))

    soft_now = _ratio(assets_now - current_now - ppe_now, assets_now)
    soft_prior = _ratio(assets_prior - current_prior - ppe_prior, assets_prior)
    aqi = index_of("AQI", _ratio(soft_now, soft_prior))

    sgi = index_of("SGI", _ratio(revenue_now, revenue_prior))

    rate_now = _ratio(depreciation_now, depreciation_now + ppe_now)
    rate_prior = _ratio(depreciation_prior, depreciation_prior + ppe_prior)
    depi = index_of("DEPI", _ratio(rate_prior, rate_now))

    sgai = index_of("SGAI", _ratio(_ratio(sga_now, revenue_now),
                                   _ratio(sga_prior, revenue_prior)))

    leverage_now = _ratio((curliab_now or 0) + (ltd_now or 0), assets_now)
    leverage_prior = _ratio((curliab_prior or 0) + (ltd_prior or 0), assets_prior)
    lvgi = index_of("LVGI", _ratio(leverage_now, leverage_prior))

    # TATA is a level, not a ratio of ratios, so it defaults to 0 not 1.
    tata_value = _ratio(net_income_now - cfo_now, assets_now)
    tata = float(tata_value) if np.isfinite(tata_value) else 0.0
    indices["TATA"] = _nullable(tata_value)

    available = sum(1 for v in indices.values() if v is not None)
    if available < _MIN_BENEISH_INDICES:
        return {
            "score": None, "band": "unknown", "indices": indices,
            "indicesAvailable": available, "indicesTotal": len(indices),
            "reading": (f"Only {available} of {len(indices)} Beneish indices could be "
                        "computed from these filings — too few to report a score."),
        }

    score = (-4.84 + 0.920 * dsri + 0.528 * gmi + 0.404 * aqi + 0.892 * sgi
             + 0.115 * depi - 0.172 * sgai + 4.679 * tata - 0.327 * lvgi)

    if score > -1.78:
        band = "flagged"
        reading = ("Accrual and growth patterns resemble those Beneish found among "
                   "manipulators. A screen, not a finding — read the filings.")
    elif score > -2.22:
        band = "borderline"
        reading = "Close to Beneish's threshold; worth a look at the accruals."
    else:
        band = "clean"
        reading = "No Beneish manipulation signature."

    return {"score": float(score), "band": band, "indices": indices,
            "indicesAvailable": available, "indicesTotal": len(indices),
            "reading": reading}


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def analyze(company: dict) -> dict:
    """The whole quality lens for one company.

    `company` is the dict `valuation.fetch_company` already returns, so this
    costs no additional network calls — the statements have been fetched.
    """
    sector = company.get("sector") or ""
    industry = company.get("industry") or ""
    income = company.get("income")
    balance = company.get("balance")
    cashflow = company.get("cashflow")

    if is_financial(sector, industry):
        return {
            "applicable": False,
            "reason": (
                "Piotroski, Altman and Beneish were all built on non-financial "
                "firms and none of them transfers to a bank or insurer: there is "
                "no operating cycle for working capital or a current ratio to "
                "describe, and revenue is not a receivables-and-inventory "
                "process. A score here would be arithmetic without meaning."
            ),
            "sector": sector or None,
            "industry": industry or None,
            "piotroski": None, "altman": None, "beneish": None,
        }

    have_statements = any(
        isinstance(s, pd.DataFrame) and not s.empty for s in (income, balance, cashflow)
    )
    if not have_statements:
        return {
            "applicable": False,
            "reason": "No financial statements came back for this listing.",
            "sector": sector or None, "industry": industry or None,
            "piotroski": None, "altman": None, "beneish": None,
        }

    piotroski = piotroski_f_score(income, balance, cashflow)
    altman = altman_z_em(income, balance)
    beneish = beneish_m_score(income, balance, cashflow)

    # One headline the confluence rail can vote with.
    concerns = []
    if altman["band"] == "distress":
        concerns.append("solvency")
    if beneish["band"] == "flagged":
        concerns.append("accruals")
    if piotroski["band"] == "weak":
        concerns.append("fundamental trend")

    if concerns:
        verdict, tone = "CONCERNS", "bear"
        headline = "Flagged on " + " and ".join(concerns) + "."
    elif piotroski["band"] in {"strong", "solid"} and altman["band"] == "safe":
        verdict, tone = "SOUND", "bull"
        headline = "Improving fundamentals and no solvency or accrual flags."
    else:
        verdict, tone = "NEUTRAL", "neutral"
        headline = "Nothing alarming, nothing outstanding."

    return {
        "applicable": True,
        "sector": sector or None,
        "industry": industry or None,
        "verdict": verdict,
        "tone": tone,
        "headline": headline,
        "piotroski": piotroski,
        "altman": altman,
        "beneish": beneish,
    }
