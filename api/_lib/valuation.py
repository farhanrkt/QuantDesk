"""
valuation.py
============
Engine 3 — INTRINSIC v2, extracted from the Streamlit app.

Every constant, clip, guard-rail and branch is transcribed unchanged:
MARKETS (Rf / ERP / tax / scale), ROW_ALIASES, the beta clip [0.4, 2.5], the
effective-tax clip [0.05, 0.40], the cost-of-debt clip [0.01, 0.25], the WACC
clip [0.02, 0.40], PROJECTION_YEARS = 5, MIN_SPREAD = 150bp, the Monte Carlo
draw ranges (DCF g in [-0.50, 1.00] / r in [0.02, 0.50]; DDM g in [-0.30, 0.50]
/ r in [0.03, 0.50]; gt in [-0.02, 0.06] then forced below r - MIN_SPREAD), and
the ±15% verdict bands.

What changed: `st.slider` / `st.number_input` / `st.checkbox` became function
arguments carrying the SAME default values the widgets had. Nothing else.
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

import numpy as np
import pandas as pd

from . import market_data, riskmodel, symbols
from .lang import tr

# =============================================================================
# 1. MARKET CONVENTIONS
# =============================================================================

MARKETS = {
    "US": {
        "code": "US",
        "name": "US Market",
        "suffix": "",
        "symbol": "$",
        "risk_free_default": 0.042,
        "erp": 0.055,
        "tax_rate": 0.21,
        "example": "AAPL, JPM, NVDA",
        "scale": [(1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")],
    },
    "ID": {
        "code": "ID",
        "name": "Indonesian Market (IDX)",
        "suffix": ".JK",
        "symbol": "Rp",
        "risk_free_default": 0.065,
        "erp": 0.070,
        "tax_rate": 0.22,
        "example": "BBCA, TLKM, ASII",
        "scale": [(1e12, "T"), (1e9, "B"), (1e6, "M")],
    },
}


class ValuationError(Exception):
    """Raised when an engine cannot produce a defensible number.

    `manual_required` marks the subset of failures the user can actually fix by
    supplying figures themselves — a gap in Yahoo's filings rather than a
    business the model genuinely cannot value. `suggested` carries whatever the
    fetch DID return, so the client can prefill the manual form instead of
    presenting six empty boxes.
    """

    def __init__(self, message: str, manual_required: bool = False,
                 missing=(), suggested: Optional[dict] = None,
                 engine: Optional[str] = None, cause: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.manual_required = bool(manual_required)
        self.missing = list(missing)
        self.suggested = suggested or {}
        # WHICH ENGINE FAILED, stated rather than inferred.
        #
        # The client used to work this out from the SHAPE of `suggested` — a
        # `netDebt` key meant DCF, a `payout` key meant DDM. Residual income
        # sends `payout` and no `netDebt`, so it was read as a DDM failure: the
        # rescue form asked for "annual dividend per share", the user typed a
        # BOOK VALUE, and the DDM discounted it as a dividend. A confident wrong
        # number, from guessing identity out of a dict's keys — the same mistake
        # `_lib/symbols.py` exists to prevent.
        self.engine = engine
        # WHICH REFUSAL, as a value, for the two a caller acts on: "not-a-company"
        # is final, "unknown-sector" is a throttle a sweep retries. Prose is
        # reworded; a caller sniffing it for a keyword breaks when it is.
        self.cause = cause

    def as_detail(self) -> dict:
        return {
            "message": self.message,
            "manualRequired": self.manual_required,
            "missing": self.missing,
            "suggested": self.suggested,
            "engine": self.engine,
            "cause": self.cause,
        }


def fmt_big(value, market: dict) -> str:
    if value is None or not np.isfinite(value):
        return "n/a"
    sign = "-" if value < 0 else ""
    gap = " " if market["code"] == "ID" else ""
    v = abs(float(value))
    for divisor, tag in market["scale"]:
        if v >= divisor:
            return f"{sign}{market['symbol']}{gap}{v / divisor:,.2f}{tag}"
    return f"{sign}{market['symbol']}{gap}{v:,.0f}"


def fmt_price(value, market: dict) -> str:
    if value is None or not np.isfinite(value):
        return "n/a"
    if market["code"] == "ID":
        return f"{market['symbol']} {value:,.0f}"
    return f"{market['symbol']}{value:,.2f}"


def fmt_dps(value, market: dict) -> str:
    """Dividends per share need more precision than prices — an IDX bank can
    pay Rp 172.50 per share, and rounding that to Rp 173 moves the valuation."""
    if value is None or not np.isfinite(value):
        return "n/a"
    if market["code"] == "ID":
        return f"{market['symbol']} {value:,.2f}"
    return f"{market['symbol']}{value:,.3f}"


# =============================================================================
# 2. DATA INGESTION
# =============================================================================

ROW_ALIASES = {
    "ocf": [
        "Operating Cash Flow",
        "Total Cash From Operating Activities",
        "Cash Flow From Continuing Operating Activities",
        # IDX filers report cash flow by the DIRECT method, which Yahoo labels
        # with this (unpunctuated) string. Without it `ocf` never resolved for
        # an Indonesian listing: the FCF column still populated from the
        # reported "Free Cash Flow" row, but the operating-cash-flow column
        # rendered "n/a" for every year, so the user could not check that
        # FCF = OCF - capex on the one market this product exists to cover.
        #
        # It must stay an EXACT alias. `_get_row`'s substring fallback would
        # otherwise happily match the sibling component rows that live beside
        # it — "Other Cash Paymentsfrom Operating Activities" and friends are
        # line items WITHIN the total, and picking one silently would produce a
        # confident, wrong free cash flow.
        "Cash Flowsfromusedin Operating Activities Direct",
    ],
    "capex": [
        "Capital Expenditure", "Capital Expenditures",
        "Purchase Of PPE", "Net PPE Purchase And Sale",
    ],
    "fcf": ["Free Cash Flow"],
    # Cash with the short-term investments it is usually parked in. Read first
    # by `extract_balance_items`; see there for the measurement.
    "cash_and_short_term": ["Cash Cash Equivalents And Short Term Investments"],
    "cash": [
        "Cash And Cash Equivalents",
        "Cash Cash Equivalents And Short Term Investments",
        "Cash And Cash Equivalents At Carrying Value",
    ],
    "total_debt": ["Total Debt"],
    "long_term_debt": ["Long Term Debt", "Long Term Debt And Capital Lease Obligation"],
    "short_term_debt": [
        "Current Debt", "Short Long Term Debt",
        "Current Debt And Capital Lease Obligation",
    ],
    "equity": [
        "Stockholders Equity", "Total Stockholder Equity",
        "Common Stock Equity", "Total Equity Gross Minority Interest",
    ],
    "revenue": ["Total Revenue", "Operating Revenue"],
    "net_income": ["Net Income Common Stockholders", "Net Income"],
    "pretax_income": ["Pretax Income", "Income Before Tax"],
    "tax_provision": ["Tax Provision", "Income Tax Expense"],
    "interest_expense": ["Interest Expense", "Interest Expense Non Operating"],
    "eps": ["Diluted EPS", "Basic EPS"],
    # --- rows used by _lib/quality.py (F-Score, Z''-EM, M-Score) -------------
    # They live here rather than in that module because this dict is the single
    # place that knows how Yahoo names a statement line, and that knowledge
    # should not fork.
    "total_assets": ["Total Assets"],
    "current_assets": ["Current Assets", "Total Current Assets"],
    "current_liabilities": ["Current Liabilities", "Total Current Liabilities"],
    "retained_earnings": ["Retained Earnings"],
    "ebit": ["EBIT", "Operating Income", "Earnings Before Interest And Taxes"],
    # OPERATING INCOME FIRST, which `ebit` is not: its first alias is EBIT, and
    # the two differ by non-operating items. The company view charts the line
    # the business earns from operations, so it asks for that line by name.
    "operating_income": ["Operating Income", "Total Operating Income As Reported"],
    "total_liabilities": [
        "Total Liabilities Net Minority Interest", "Total Liabilities",
    ],
    "receivables": ["Accounts Receivable", "Net Receivables", "Receivables"],
    "cogs": ["Cost Of Revenue", "Cost Of Goods Sold"],
    "ppe": [
        "Net PPE", "Net Property Plant And Equipment",
        "Property Plant And Equipment Net",
    ],
    "depreciation": [
        "Depreciation And Amortization", "Depreciation Amortization Depletion",
        "Depreciation",
    ],
    "sga": [
        "Selling General And Administration", "Selling General And Administrative",
    ],
    "shares_issued": ["Ordinary Shares Number", "Share Issued"],
}


def _get_row(df, key: str):
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return None
    lookup = {str(i).strip().lower(): i for i in df.index}
    for alias in ROW_ALIASES.get(key, []):
        hit = lookup.get(alias.strip().lower())
        if hit is not None:
            return df.loc[hit]
    for alias in ROW_ALIASES.get(key, []):
        for label_lc, original in lookup.items():
            if alias.strip().lower() in label_lc:
                return df.loc[original]
    return None


def _first_valid(series, default=np.nan):
    if series is None:
        return default
    s = pd.Series(series).dropna()
    return float(s.iloc[0]) if len(s) else default


def _safe_float(value, default=np.nan) -> float:
    try:
        if value is None:
            return default
        out = float(value)
        return out if np.isfinite(out) else default
    except (TypeError, ValueError):
        return default


def _nullable(value):
    """float for the wire, or None when the figure is missing/non-finite."""
    out = _safe_float(value)
    return float(out) if np.isfinite(out) else None


# The 10Y yield moves once a day; this used to be refetched on EVERY valuation
# request, including all three legs of a confluence run. Keyed by date so it
# expires on its own, and only successful fetches are stored — caching a failure
# would pin the fallback for the rest of the day with no retry. Module scope
# survives warm serverless invocations and costs nothing when it does not.
# Fetching lives in `_lib/market_data.py` — the only module that imports
# yfinance. It owns the company cache (per-caller copies, per-key locking), the
# risk-free rate, and the rule that the last daily bar close is the canonical
# price. See that module's header for the four bugs that arrangement fixed.
fetch_company = market_data.company
fetch_risk_free_rate = market_data.risk_free_rate


# =============================================================================
# 3. SECTOR ROUTING
# =============================================================================

def detect_engine(sector: str, industry: str):
    s = (sector or "").strip().lower()
    i = (industry or "").strip().lower()
    if s == "financial services" or "bank" in i:
        reason = tr("sector = Financial Services", "sektor = Jasa Keuangan") if s == "financial services" else tr("industry mentions banking",
                                                                                    "industrinya menyebut perbankan")
        return "DDM", reason
    return "DCF", tr("non-financial sector", "sektor nonkeuangan")


# =============================================================================
# 4. DERIVED FINANCIALS
# =============================================================================

def build_fcf_history(cashflow, years: int = 4) -> pd.DataFrame:
    if cashflow is None or not isinstance(cashflow, pd.DataFrame) or cashflow.empty:
        return pd.DataFrame()

    ocf = _get_row(cashflow, "ocf")
    capex = _get_row(cashflow, "capex")
    reported_fcf = _get_row(cashflow, "fcf")
    if ocf is None and reported_fcf is None:
        return pd.DataFrame()

    rows = []
    for col in list(cashflow.columns)[:years]:
        o = _safe_float(ocf.get(col)) if ocf is not None else np.nan
        c = _safe_float(capex.get(col)) if capex is not None else np.nan
        if np.isfinite(o) and np.isfinite(c):
            f = o - abs(c)
        elif reported_fcf is not None:
            f = _safe_float(reported_fcf.get(col))
        else:
            f = np.nan
        rows.append({
            "Fiscal Year": pd.Timestamp(col).strftime("%Y"),
            "Operating Cash Flow": o,
            "Capital Expenditure": -abs(c) if np.isfinite(c) else np.nan,
            "Free Cash Flow": f,
        })
    return pd.DataFrame(rows).dropna(subset=["Free Cash Flow"])


def extract_balance_items(balance):
    """Cash, total debt, and what the cash figure is, for the equity bridge.

    CASH AND SHORT-TERM INVESTMENTS, WHERE THE BALANCE SHEET REPORTS THEM. The
    bridge from enterprise to equity value adds what the business holds and
    does not need to operate, and a treasury bill bought with spare cash is as
    much the shareholders' as the cash was. This read "Cash And Cash
    Equivalents" alone until the November 2026 audit. Measured then across
    2,844 non-financial records in the local cache whose statements and shares
    share a currency: the short-term investments it left out were nothing for
    the median company, but at least 5% of market value for 420 (15%) and at
    least 10% for 280 — cash-rich technology and biotechnology, mostly. Longer
    holdings are still left out: a stake listed as a long-term investment is
    not always spare cash, and nothing here can tell which.
    """
    liquid = _first_valid(_get_row(balance, "cash_and_short_term"), np.nan)
    if np.isfinite(liquid):
        cash, label = liquid, tr("Cash & short-term investments", "Kas & investasi jangka pendek")
    else:
        cash, label = _first_valid(_get_row(balance, "cash"), 0.0), tr("Cash & equivalents",
                                                                       "Kas & setara kas")
    total_debt = _first_valid(_get_row(balance, "total_debt"), np.nan)
    if not np.isfinite(total_debt):
        st_debt = _first_valid(_get_row(balance, "short_term_debt"), 0.0)
        lt_debt = _first_valid(_get_row(balance, "long_term_debt"), 0.0)
        total_debt = (st_debt or 0.0) + (lt_debt or 0.0)
    return float(cash or 0.0), float(total_debt or 0.0), label


def effective_tax_rate(income, default: float) -> float:
    tax = _first_valid(_get_row(income, "tax_provision"))
    pretax = _first_valid(_get_row(income, "pretax_income"))
    if np.isfinite(tax) and np.isfinite(pretax) and pretax > 0:
        return float(np.clip(tax / pretax, 0.05, 0.40))
    return default


def _reports_cost_of_revenue(income) -> bool:
    """Whether the income statement carries a cost of revenue or gross profit line.

    No bank's does — see the unknown-sector branch of `analyze` for the count.
    """
    if not isinstance(income, pd.DataFrame) or income.empty:
        return False
    labels = {str(label).strip().lower() for label in income.index}
    return bool(labels & {"cost of revenue", "reconciled cost of revenue", "gross profit"})


def clip_beta(beta) -> float:
    """A hard sanity bound, NOT the shrinkage mechanism any more.

    This clip used to be the only thing standing between a noisy beta and the
    cost of equity, and it applied the same hard edge to a mega-cap measured
    over 500 days and an IDX small cap whose estimate is barely distinguishable
    from noise. `riskmodel.estimate_beta` now does that job properly, shrinking
    each estimate toward the market in proportion to its own standard error
    (Vasicek 1973). What remains here is a floor and ceiling that a shrunk beta
    should essentially never touch — it binds only when the shrinkage itself is
    unavailable, which is the fallback path.
    """
    b = _safe_float(beta, 1.0)
    return float(np.clip(b if np.isfinite(b) else 1.0, 0.4, 2.5))


def cost_of_equity(beta: float, risk_free: float, erp: float) -> float:
    return float(risk_free + clip_beta(beta) * erp)


def compute_wacc(beta, risk_free, erp, equity_value, total_debt,
                 interest_expense, tax_rate) -> dict:
    ke = cost_of_equity(beta, risk_free, erp)

    if total_debt > 0 and np.isfinite(interest_expense) and interest_expense > 0:
        kd = float(np.clip(interest_expense / total_debt, 0.01, 0.25))
    else:
        kd = risk_free + 0.02

    e = max(equity_value, 0.0) if np.isfinite(equity_value) else 0.0
    d = max(total_debt, 0.0)
    v = e + d
    if v <= 0:
        wacc, we, wd = ke, 1.0, 0.0
    else:
        we, wd = e / v, d / v
        wacc = we * ke + wd * kd * (1 - tax_rate)

    return {
        "beta": clip_beta(beta), "cost_equity": ke, "cost_debt": kd,
        "weight_equity": we, "weight_debt": wd,
        "wacc": float(np.clip(wacc, 0.02, 0.40)),
    }


# The two dividend-yield fields Yahoo publishes use DIFFERENT conventions, and
# that is not a guess — it is visible in any pair of tickers:
#
#             dividendYield   trailingAnnualDividendYield   actual
#   AAPL             0.3500                        0.0034    0.34%
#   KO               2.3300                        0.0230    2.30%
#
# `dividendYield` is a PERCENTAGE; `trailingAnnualDividendYield` is a FRACTION.
# One heuristic cannot serve both. The old rule — divide by 100 above 1.0 —
# happened to be right for any yield of 1% or more and was catastrophically
# wrong below it: AAPL's 0.35 stayed 0.35, so a company paying 0.34% was read as
# paying 35%, and the dividend model valued it about a hundred times too high.
# No error, a plausible-looking figure. The same shape as the currency bug.
YIELD_IS_PERCENT = {"dividend_yield_raw": True,
                    "trailing_dividend_yield_raw": False}

# Above this, a "yield" is not a yield. Even after applying the right
# convention, a garbled field should not reach a valuation — the highest
# sustained yields among listed companies sit far below this.
MAX_PLAUSIBLE_YIELD = 0.60


def normalize_yield(raw, price, is_percent: bool = False) -> float:
    """One yield field, in its own units, as a fraction.

    `is_percent` is passed explicitly by the caller rather than sniffed from the
    magnitude, because the magnitude is exactly what cannot distinguish 0.35%
    from 35%.
    """
    v = _safe_float(raw)
    if not np.isfinite(v) or v <= 0:
        return np.nan
    out = v / 100.0 if is_percent else v
    return out if 0 < out <= MAX_PLAUSIBLE_YIELD else np.nan


# A dividend per share implying a yield outside this band is not a dividend, it
# is a units problem. The floor is what catches a figure denominated in the
# wrong currency; the ceiling catches a garbled field.
PLAUSIBLE_YIELD_BAND = (0.0001, 0.60)


def _dividend_candidate(value, price: float, label: str, fx: Optional[float]):
    """Accept a dividend-per-share figure only if it implies a credible yield.

    WHY EVERY CANDIDATE IS SANITY-CHECKED AGAINST THE PRICE. Yahoo is not
    internally consistent about the currency of its dividend fields. For an
    Indonesian company that reports in dollars, `trailingAnnualDividendRate`
    comes back in USD while `dividendRate` comes back in IDR:

        ADRO.JK   paid Rp 430.09   trailingAnnualDividendRate 0.0160 (USD)
                                   dividendRate             236.52  (IDR)

    Taking the first at face value gives a dividend roughly seventeen thousand
    times too small and a dividend-model valuation to match — no error, just a
    tiny number. Rather than hard-code which field uses which currency, which is
    a fact about a scraper that has already changed once, each candidate is
    checked against the share price it will be compared with.

    Where a rate is available and the figure becomes credible once converted,
    that is strong evidence it was quoted in the reporting currency, so it is
    converted and the label says so. Otherwise it is skipped and the next
    candidate gets its turn.
    """
    dps = _safe_float(value)
    if not np.isfinite(dps) or dps <= 0 or not np.isfinite(price) or price <= 0:
        return None
    low, high = PLAUSIBLE_YIELD_BAND
    if low <= dps / price <= high:
        return dps, label
    if fx and low <= (dps * fx) / price <= high:
        return dps * fx, tr(f"{label}, converted at the reporting-currency rate",
                            f"{label}, dikonversi dengan kurs mata uang pelaporan")
    return None


def resolve_dividend(data: dict, price: float):
    fx = _safe_float(data.get("fx_rate"))
    fx = float(fx) if np.isfinite(fx) and fx > 0 else None

    # Ordered by how far each is from what the company actually paid.
    for value, label in (
        (data.get("ttm_dividend"), tr("trailing 12m payments (actual)",
                                      "pembayaran 12 bulan terakhir (aktual)")),
        (data.get("trailing_dividend_rate"), tr("trailing annual rate (yfinance)",
                                                "laju tahunan 12 bulan terakhir (yfinance)")),
        (data.get("dividend_rate"), tr("forward annual rate (yfinance)",
                                       "laju tahunan ke depan (yfinance)")),
    ):
        candidate = _dividend_candidate(value, price, label, fx)
        if candidate:
            return candidate

    for key in ("trailing_dividend_yield_raw", "dividend_yield_raw"):
        y = normalize_yield(data.get(key), price, is_percent=YIELD_IS_PERCENT[key])
        if np.isfinite(y) and y > 0 and np.isfinite(price):
            return y * price, tr("derived from dividend yield",
                                 "diturunkan dari imbal hasil dividen")

    return np.nan, "unavailable"


def complete_years(div_history) -> pd.DataFrame:
    """The dividend record's whole calendar years, newest first — never this one.

    `dividend_history` sums payments by calendar year, so the current year is a
    year to date. The DDM's "Last full year" basis used to take the SECOND row
    on the assumption that the first was always that partial year — which picked
    the year before last whenever nothing had been paid yet this year — and the
    "3-year average" averaged the partial year in, understating the base (0.90
    against 1.05 for a semi-annual payer one instalment into the year).
    """
    if not isinstance(div_history, pd.DataFrame) or div_history.empty:
        return pd.DataFrame(columns=["Year", "Dividend / Share"])
    years = pd.to_numeric(div_history["Year"], errors="coerce")
    return div_history[years < dt.date.today().year].reset_index(drop=True)


def bank_diagnostics(data: dict, dps: float, price: float, shares: float) -> dict:
    net_income = _first_valid(_get_row(data["income"], "net_income"),
                              _safe_float(data.get("net_income_info")))
    equity = _first_valid(_get_row(data["balance"], "equity"), np.nan)

    roe = _safe_float(data.get("roe_info"))
    if not np.isfinite(roe) and np.isfinite(net_income) and np.isfinite(equity) and equity > 0:
        roe = net_income / equity

    payout = _safe_float(data.get("payout_ratio"))
    if (not np.isfinite(payout) or payout <= 0) and np.isfinite(net_income) and net_income > 0 \
            and np.isfinite(dps) and np.isfinite(shares) and shares > 0:
        payout = (dps * shares) / net_income

    payout_clean = float(np.clip(payout, 0.0, 1.0)) if np.isfinite(payout) else np.nan
    sustainable = roe * (1 - payout_clean) if np.isfinite(roe) and np.isfinite(payout_clean) else np.nan

    return {
        "net_income": net_income,
        "equity": equity,
        "roe": roe,
        "payout": payout,
        "payout_clean": payout_clean,
        "sustainable_growth": sustainable,
        "dividend_yield": dps / price if np.isfinite(dps) and np.isfinite(price) and price > 0 else np.nan,
        "eps": _first_valid(_get_row(data["income"], "eps"), np.nan),
    }


# =============================================================================
# 5. THE SHARED VALUATION CORE
# =============================================================================

PROJECTION_YEARS = 5
MIN_SPREAD = 0.015


def pv_of_growing_stream(base, growth, rate, terminal_growth, years=PROJECTION_YEARS):
    g = np.asarray(growth, dtype=float).reshape(-1, 1)
    r = np.asarray(rate, dtype=float).reshape(-1, 1)
    gt = np.asarray(terminal_growth, dtype=float).reshape(-1, 1)
    t = np.arange(1, years + 1).reshape(1, -1)

    projected = base * np.power(1.0 + g, t)
    discounted = projected / np.power(1.0 + r, t)

    spread = np.maximum(r - gt, MIN_SPREAD)
    terminal_value = projected[:, -1:] * (1.0 + gt) / spread
    pv_terminal = terminal_value / np.power(1.0 + r, years)

    return projected, discounted.sum(axis=1, keepdims=True), pv_terminal, terminal_value


def dcf_implied_price(base_fcf, growth, wacc, terminal_growth, cash, debt, shares):
    _, pv_explicit, pv_terminal, _ = pv_of_growing_stream(base_fcf, growth, wacc, terminal_growth)
    enterprise_value = pv_explicit + pv_terminal
    return ((enterprise_value + cash - debt) / shares).ravel()


def ddm_implied_price(base_dps, growth, cost_eq, terminal_growth):
    _, pv_explicit, pv_terminal, _ = pv_of_growing_stream(base_dps, growth, cost_eq, terminal_growth)
    return (pv_explicit + pv_terminal).ravel()


# The widest growth rate worth solving for. Above roughly 60% sustained for five
# years the model has stopped describing a business and started describing an
# arithmetic curiosity, and reporting "the market implies 400% growth" would be
# false precision about a model that has left its domain.
IMPLIED_GROWTH_BOUNDS = (-0.60, 0.60)


def implied_growth(engine, price, base, rate, terminal_growth,
                   cash=0.0, debt=0.0, shares=1.0):
    """The growth rate that makes this model reproduce today's market price.

    THE MOST USEFUL QUESTION A DISCOUNTED CASH FLOW CAN ANSWER, AND THE ONE IT
    IS USUALLY NOT ASKED. Run forwards, a DCF says "this is worth $111" — an
    answer whose whole width comes from assumptions the reader has no basis to
    judge, and which invites being read as a price target. Run BACKWARDS it says
    "at today's price the market is assuming 14% a year for five years", which
    is a claim about the world that a reader can actually agree or disagree
    with. It converts an opinion into a testable proposition, and it is how the
    model is used by people who use it well.

    Solved rather than approximated. Implied price is continuous and strictly
    increasing in growth over the bracket — more growth is always worth more —
    so Brent's method converges on the unique crossing. Returns None when the
    price lies outside what the bracket can produce, which is itself the finding:
    a business whose market price needs more than 60% compound growth for five
    years is not being valued on its cash flows by anyone.
    """
    from scipy.optimize import brentq

    price = _safe_float(price)
    if not np.isfinite(price) or price <= 0:
        return None

    def implied_at(g: float) -> float:
        growth = np.array([float(g)])
        rates = np.array([float(rate)])
        terminals = np.array([float(terminal_growth)])
        if engine == "DCF":
            out = dcf_implied_price(base, growth, rates, terminals, cash, debt, shares)
        else:
            out = ddm_implied_price(base, growth, rates, terminals)
        value = float(np.asarray(out).ravel()[0])
        return value if np.isfinite(value) else np.nan

    low, high = IMPLIED_GROWTH_BOUNDS
    try:
        at_low, at_high = implied_at(low) - price, implied_at(high) - price
    except (ValueError, ZeroDivisionError, FloatingPointError):
        return None
    if not (np.isfinite(at_low) and np.isfinite(at_high)):
        return None
    # No sign change means the price is unreachable anywhere in the bracket.
    if at_low * at_high > 0:
        return None

    try:
        return float(brentq(lambda g: implied_at(g) - price, low, high,
                            xtol=1e-6, maxiter=100))
    except (ValueError, RuntimeError):
        return None


# =============================================================================
# 5a. SENSITIVITY: the same model across a grid of its two biggest inputs
# =============================================================================
# Growth moves in two-point steps, the discount rate in one-point steps: a
# point of discount rate moves a DCF roughly as much as two points of growth,
# so the grid spans comparable distances in both directions.
SENS_GROWTH_STEPS = (-0.06, -0.04, -0.02, 0.0, 0.02, 0.04, 0.06)
SENS_RATE_STEPS = (-0.02, -0.01, 0.0, 0.01, 0.02)
# The same bounds the /api/intrinsic-value route accepts for these inputs, so
# the grid never shows a cell nobody could type into the assumption fields.
SENS_GROWTH_BOUNDS = (-0.50, 1.00)
SENS_RATE_BOUNDS = (0.005, 0.50)

SPREAD_REFUSAL = ("Within 1.5 points of perpetual growth the terminal value diverges, so "
                  "no value is shown here rather than the clamped number the model would "
                  "otherwise produce.")
RI_IMPLIED_REASON = ("Residual income values book value plus excess returns rather than a "
                     "growing stream, so no single growth rate is the lever a price implies.")


def _axis(centre: float, steps, bounds) -> tuple[list[float], int]:
    """Centre plus each step, clipped to bounds, de-duplicated, centre kept exact."""
    low, high = bounds
    values: list[float] = []
    for step in steps:
        value = float(centre) if step == 0 else float(np.clip(centre + step, low, high))
        if not any(abs(value - v) < 1e-9 for v in values):
            values.append(value)
    values.sort()
    return values, next(i for i, v in enumerate(values) if abs(v - centre) < 1e-9)


def sensitivity_grid(engine, base, growth, rate, terminal_growth, *, cash=0.0, debt=0.0,
                     shares=1.0, payout=0.0, price=None, fmt=None,
                     growth_steps=SENS_GROWTH_STEPS, rate_steps=SENS_RATE_STEPS) -> dict:
    """The base-case value per share across a grid of growth and discount rate.

    WHY A GRID AND NOT ANOTHER NUMBER. The panel already says the answer moves
    enormously with the growth and discount rate assumed, and tells the reader
    to change an input and watch. A grid does that for them, in both directions
    at once, so "how much does this rest on my 10%?" has an answer on the page.

    THE DETERMINISTIC BASE CASE, NOT THE SIMULATION'S MEDIAN. The assumed cell
    is the same calculation as `baseCase.impliedPrice`, so the grid and the
    figure above it agree to the last digit. The Monte Carlo median differs from
    it by construction (the model is non-linear in both inputs), and a panel
    quoting two different "centres" is the kind of contradiction this codebase
    keeps having to remove.

    NOTHING IS COMPARED WITH THE PRICE HERE. The price travels beside the grid
    so the reader can do that themselves; there is no count of cells above it,
    no fill, no tone. A grid of fair values coloured against price is a buy/sell
    heat map, which PRODUCT.md constraint 1 refuses.

    A CELL TOO CLOSE TO PERPETUAL GROWTH IS REFUSED, NOT CLAMPED. The core
    silently floors the spread at MIN_SPREAD, so computing such a cell would
    print a number that is not the stated formula. It is None, and says why.

    One vectorised call: the valid cells are flattened into the draw axis of the
    same functions the simulation uses, and reshaped back.
    """
    fmt = fmt or (lambda v: f"{v:,.2f}")
    if engine == "RI":
        rows, row_at = _axis(growth, growth_steps, RI_ROE_BOUNDS)
        row_axis = {"name": "roe", "label": tr("Return on equity", "Imbal hasil ekuitas"), "values": rows, "assumedIndex": row_at}
    else:
        rows, row_at = _axis(growth, growth_steps, SENS_GROWTH_BOUNDS)
        row_axis = {"name": "growth", "label": tr("Growth, years 1-5", "Pertumbuhan, tahun 1-5"), "values": rows,
                    "assumedIndex": row_at}
    cols, col_at = _axis(rate, rate_steps, SENS_RATE_BOUNDS)
    rate_label = "WACC" if engine == "DCF" else tr("Cost of equity", "Biaya ekuitas")

    g_grid, r_grid = np.meshgrid(np.array(rows), np.array(cols), indexing="ij")
    if engine == "RI":
        valid = np.ones_like(g_grid, dtype=bool)
    else:
        valid = (r_grid - terminal_growth) >= MIN_SPREAD - 1e-12
    g_flat, r_flat = g_grid[valid], r_grid[valid]

    values = np.full(g_grid.shape, np.nan)
    if g_flat.size:
        if engine == "DCF":
            out = dcf_implied_price(base, g_flat, r_flat, np.full(g_flat.shape, terminal_growth),
                                    cash, debt, shares)
        elif engine == "DDM":
            out = ddm_implied_price(base, g_flat, r_flat, np.full(g_flat.shape, terminal_growth))
        else:
            out, _, _, _ = residual_income_value(np.full(g_flat.shape, base), g_flat, r_flat,
                                                 np.full(g_flat.shape, payout))
        values[valid] = np.asarray(out, dtype=float).ravel()

    cells = []
    for i in range(len(rows)):
        line = []
        for j in range(len(cols)):
            v = values[i, j]
            if not valid[i, j]:
                line.append({"value": None, "label": None, "refused": "spread"})
            elif not np.isfinite(v):
                line.append({"value": None, "label": None, "refused": "undefined"})
            else:
                line.append({"value": float(v), "label": fmt(float(v)), "refused": None})
        cells.append(line)

    implied_row = None
    if engine in ("DCF", "DDM"):
        implied_row = []
        for r in cols:
            if r - terminal_growth < MIN_SPREAD - 1e-12:
                implied_row.append({"rate": r, "impliedGrowth": None, "reason": "spread"})
                continue
            g = implied_growth(engine, price, base, r, terminal_growth,
                               cash=cash, debt=debt, shares=shares)
            implied_row.append({"rate": r, "impliedGrowth": g,
                                "reason": None if g is not None else "unreachable"})

    price_f = _safe_float(price)
    return {
        "engine": engine,
        "rowAxis": row_axis,
        "colAxis": {"name": "rate", "label": rate_label, "values": cols, "assumedIndex": col_at},
        "cells": cells,
        "assumed": {"row": row_at, "col": col_at},
        "terminalGrowth": float(terminal_growth),
        "price": float(price_f) if np.isfinite(price_f) else None,
        "priceLabel": fmt(float(price_f)) if np.isfinite(price_f) else None,
        "impliedRow": implied_row,
        "impliedRowReason": tr(RI_IMPLIED_REASON,
                               "Pendapatan residual menilai nilai buku ditambah imbal hasil "
                               "lebih, bukan aliran yang bertumbuh, jadi tidak ada satu tingkat "
                               "pertumbuhan pun yang menjadi tuas yang disiratkan harga.")
        if engine == "RI" else None,
        "refusals": {"spread": tr(SPREAD_REFUSAL,
                                  "Dalam jarak 1.5 poin dari pertumbuhan abadi, nilai terminal "
                                  "menjadi tak hingga, jadi tidak ada nilai yang ditampilkan di "
                                  "sini alih-alih angka terpotong yang akan dihasilkan model."),
                     "unreachable": (tr("Today's price lies outside what any growth rate between "
                                        "-60% and +60% a year can produce at this discount rate.",
                                        "Harga hari ini berada di luar jangkauan tingkat pertumbuhan berapa pun "
                                        "antara -60% dan +60% per tahun pada tingkat diskonto ini."))},
        "reading": (tr("Each cell is the model's base-case value per share at that "
                       f"{'return on equity' if engine == 'RI' else 'growth rate'} and "
                       f"{rate_label if rate_label.isupper() else rate_label.lower()}, with every "
                       "other input as assumed. It is not a "
                       "forecast, and the market price sits beside the grid rather than inside it.",
                       "Setiap sel adalah nilai kasus dasar per saham dari model pada "
                       f"{'imbal hasil ekuitas' if engine == 'RI' else 'tingkat pertumbuhan'} "
                       f"dan {rate_label if rate_label.isupper() else rate_label.lower()} "
                       "tersebut, dengan semua masukan lain sesuai asumsi. Ini bukan ramalan, "
                       "dan harga pasar berada di samping kisi, bukan di dalamnya.")),
    }


def base_case_schedule(engine, base, growth, rate, terminal_growth,
                       cash=0.0, debt=0.0, shares=1.0):
    projected, pv_explicit, pv_terminal, terminal_value = pv_of_growing_stream(
        base, np.array([growth]), np.array([rate]), np.array([terminal_growth])
    )
    projected = projected[0]
    pv_explicit = float(pv_explicit[0, 0])
    pv_terminal = float(pv_terminal[0, 0])
    terminal_value = float(terminal_value[0, 0])

    t = np.arange(1, PROJECTION_YEARS + 1)
    discount_factors = 1 / (1 + rate) ** t
    stream_label = "Projected FCF" if engine == "DCF" else "Projected DPS"

    schedule = pd.DataFrame({
        "Year": [f"Y{i}" for i in t],
        stream_label: projected,
        "Discount Factor": discount_factors,
        "Present Value": projected * discount_factors,
    })

    gross = pv_explicit + pv_terminal
    if engine == "DCF":
        equity_value = gross + cash - debt
        implied_price = equity_value / shares
    else:
        equity_value = gross
        implied_price = gross

    summary = {
        "pv_explicit": pv_explicit,
        "pv_terminal": pv_terminal,
        "terminal_value": terminal_value,
        "terminal_share": pv_terminal / gross if gross else np.nan,
        "gross": gross,
        "equity_value": equity_value,
        "implied_price": implied_price,
    }
    return schedule, summary


# =============================================================================
# 5b. RESIDUAL INCOME (Ohlson 1995)
# =============================================================================
# Persistence of abnormal earnings. Competition erodes excess returns, so
# residual income decays rather than growing forever. 0.62 is the empirical
# persistence Dechow, Hutton & Sloan (1999) estimate for a broad US sample; it
# is deliberately a fade, not a growth rate, which is why this engine does not
# suffer the terminal-value dominance the DCF and DDM have to be warned about.
RI_PERSISTENCE = 0.62

# Return on equity is mean-reverting too. Left unclipped, one exceptional year
# at a bank compounds book value into fantasy over five years.
RI_ROE_BOUNDS = (-0.30, 0.45)


def residual_income_value(book_value, roe, cost_equity, payout,
                          years: int = PROJECTION_YEARS,
                          persistence: float = RI_PERSISTENCE):
    """Ohlson's residual income model, vectorised over Monte Carlo draws.

        V0 = B0 + sum_t (ROE_t - r) * B_{t-1} / (1+r)^t + continuing value

    WHY THIS ENGINE EARNS ITS PLACE. A DDM values a bank's dividend, which is a
    policy choice a board can change; a DCF values free cash flow, which is not a
    meaningful quantity for an institution whose business IS the balance sheet.
    Residual income anchors on book value and ROE — the two figures a bank
    reports most reliably, and the two that are actually present in Yahoo's data
    for IDX banks when the dividend fields are empty.

    Book value rolls forward by clean surplus: whatever is earned and not paid
    out is retained. The continuing value fades the last explicit year's
    residual income geometrically at `persistence`, summing to
    RI_T * w / (1 + r - w).
    """
    b = np.asarray(book_value, dtype=float).reshape(-1)
    roe = np.asarray(roe, dtype=float).reshape(-1)
    r = np.asarray(cost_equity, dtype=float).reshape(-1)
    payout = np.clip(np.asarray(payout, dtype=float).reshape(-1), 0.0, 1.0)
    w = float(np.clip(persistence, 0.0, 0.99))

    book = b.copy()
    present_value = np.zeros_like(b)
    residual = np.zeros_like(b)
    schedule = []

    for year in range(1, years + 1):
        residual = (roe - r) * book
        discount = (1.0 + r) ** year
        present_value = present_value + residual / discount
        schedule.append({
            "year": year,
            "openingBook": book.copy(),
            "residual": residual.copy(),
            "discount": discount.copy(),
        })
        book = book * (1.0 + roe * (1.0 - payout))

    # RI fades at `w` forever: sum_k w^k * RI_T / (1+r)^k
    denominator = np.maximum(1.0 + r - w, MIN_SPREAD)
    continuing = residual * w / denominator
    pv_continuing = continuing / (1.0 + r) ** years

    value = b + present_value + pv_continuing
    return value, present_value, pv_continuing, schedule


def ri_inputs(data: dict, price: float, shares: float) -> dict:
    """Book value per share, ROE and payout — everything the RI engine needs.

    Deliberately reuses `bank_diagnostics`, which already computed all three for
    the DDM's diagnostics panel. The figures were there the whole time.
    """
    equity = _first_valid(_get_row(data["balance"], "equity"), np.nan)
    net_income = _first_valid(_get_row(data["income"], "net_income"),
                              _safe_float(data.get("net_income_info")))

    roe = _safe_float(data.get("roe_info"))
    if not np.isfinite(roe) and np.isfinite(net_income) and np.isfinite(equity) and equity > 0:
        roe = net_income / equity

    payout = _safe_float(data.get("payout_ratio"))
    if not np.isfinite(payout) or payout < 0:
        payout = 0.0

    book_per_share = (equity / shares
                      if np.isfinite(equity) and np.isfinite(shares) and shares > 0
                      else np.nan)

    return {
        "equity": equity,
        "netIncome": net_income,
        "roe": roe,
        "payout": float(np.clip(payout, 0.0, 1.0)),
        "bookPerShare": book_per_share,
        "usable": bool(np.isfinite(book_per_share) and book_per_share > 0
                       and np.isfinite(roe)),
    }


def run_monte_carlo(engine, base, growth, rate, terminal_growth,
                    n_sims, sd_growth, sd_rate, sd_terminal, seed,
                    cash=0.0, debt=0.0, shares=1.0, payout=0.0) -> pd.DataFrame:
    rng = np.random.default_rng(int(seed))
    n = int(n_sims)

    if engine == "RI":
        # For residual income the drawn "growth" IS the return on equity, and
        # there is no terminal growth to draw — abnormal earnings fade at a
        # fixed persistence rather than growing in perpetuity.
        roe = np.clip(rng.normal(growth, sd_growth, n), *RI_ROE_BOUNDS)
        r = np.clip(rng.normal(rate, sd_rate, n), 0.03, 0.50)
        prices, _, _, _ = residual_income_value(
            np.full(n, float(base)), roe, r, np.full(n, float(payout))
        )
        return pd.DataFrame({
            "Return on Equity": roe,
            "Cost of Equity": r,
            "Implied Price": prices,
        })

    if engine == "DCF":
        g = np.clip(rng.normal(growth, sd_growth, n), -0.50, 1.00)
        r = np.clip(rng.normal(rate, sd_rate, n), 0.02, 0.50)
    else:
        g = np.clip(rng.normal(growth, sd_growth, n), -0.30, 0.50)
        r = np.clip(rng.normal(rate, sd_rate, n), 0.03, 0.50)

    gt = np.clip(rng.normal(terminal_growth, sd_terminal, n), -0.02, 0.06)
    gt = np.minimum(gt, r - MIN_SPREAD)

    if engine == "DCF":
        prices = dcf_implied_price(base, g, r, gt, cash, debt, shares)
        rate_label = "WACC"
    else:
        prices = ddm_implied_price(base, g, r, gt)
        rate_label = "Cost of Equity"

    return pd.DataFrame({
        "Growth Rate": g,
        rate_label: r,
        "Terminal Growth": gt,
        "Implied Price": prices,
    })


# =============================================================================
# 6. ORCHESTRATION (replaces Streamlit sections 6-16)
# =============================================================================

DEFAULTS = {
    "DCF": {"growth": 0.10, "terminal": 0.025, "sd": (0.020, 0.010, 0.005)},
    "DDM": {"growth": 0.05, "terminal": 0.025, "sd": (0.015, 0.010, 0.005)},
    # For RI the "growth" slot carries the sustained ROE, which is why its
    # default is a plausible bank ROE rather than a growth rate. Terminal growth
    # is unused: abnormal earnings fade at RI_PERSISTENCE instead.
    "RI": {"growth": 0.12, "terminal": 0.0, "sd": (0.030, 0.010, 0.000)},
}


def analyze(
    ticker: str,
    market_code: str = "US",
    engine_choice: str = "auto",
    growth: Optional[float] = None,
    terminal: Optional[float] = None,
    rate_override: Optional[float] = None,
    n_sims: int = 10000,
    sd_growth: Optional[float] = None,
    sd_rate: Optional[float] = None,
    sd_terminal: Optional[float] = None,
    seed: int = 42,
    fcf_basis: str = "Latest fiscal year",
    dps_basis: str = "Trailing 12 months",
    # --- manual input mode (Yahoo has gaps, especially on smaller IDX listings) ---
    manual_base: Optional[float] = None,       # base FCF (DCF) or annual DPS (DDM)
    manual_net_debt: Optional[float] = None,   # DCF only: debt - cash
    manual_shares: Optional[float] = None,     # DCF only
    manual_price: Optional[float] = None,      # both engines
    manual_payout: Optional[float] = None,     # DDM diagnostics only
    with_simulation: bool = False,             # attach raw sims under "_simulation"
) -> dict:
    # One resolver for every engine — see _lib/symbols.py for why this matters.
    symbol = symbols.resolve(ticker, market_code)

    # AND ONE MARKET, TAKEN FROM THE SYMBOL rather than from the caller. A typed
    # suffix already beats the dropdown when the symbol is resolved; if the
    # conventions did not follow it here, this engine would fetch ITMG.JK and
    # then value it as an American company — dollar sign, US 10-year, ^GSPC.
    # Deriving it from the resolved symbol makes that unrepresentable rather
    # than merely fixed at the routes, which is what the deepen path needs.
    market = MARKETS.get(symbols.market_of(symbol), MARKETS["US"])

    data = fetch_company(symbol)
    rf_rate, rf_source = fetch_risk_free_rate(market["code"], market["risk_free_default"])

    choice = (engine_choice or "auto").lower()

    # A FUND, A COIN OR AN INDEX HAS NO BUSINESS TO VALUE. Each used to reach
    # the DCF and be refused for a missing cash-flow statement, with advice to
    # type one in — for BTC-USD and SPY alike. What the listing is decides it.
    kind = market_data.non_company(data, symbol)
    if kind and choice == "auto":
        raise ValuationError(
            tr(f"{symbol} is {kind}, not a company. A valuation discounts a business's "
               f"cash flows or dividends, and {kind} has no business of its own to "
               f"value, so this lens does not apply. That is what the listing is, not "
               f"a gap in the data.",
               f"{symbol} adalah {kind}, bukan perusahaan. Valuasi mendiskontokan arus "
               f"kas atau dividen sebuah bisnis, dan {kind} tidak punya bisnis sendiri "
               "untuk dinilai, jadi lensa ini tidak berlaku. Begitulah wujud instrumen "
               "ini, bukan celah data."), cause="not-a-company")

    # AN UNKNOWN SECTOR IS NOT A NON-FINANCIAL SECTOR — the rule `quality.py`
    # has followed since an IDX bank was scored as a manufacturer. This engine
    # did not: an empty sector routed to the DCF, so a bank whose `.info` was
    # throttled was valued as an ordinary company. Found in the November audit
    # on JPM, refused for "negative free cash flow" and offered a form to type
    # one in; a bank with positive free cash flow would have been given a fair
    # value instead.
    #
    # THE STATEMENTS CAN STILL SAY IT IS NOT A BANK. Refusing every name with no
    # sector was too blunt — the same audit throttled ITMG.JK, a coal miner, a
    # few minutes later. A bank's income statement has no cost of revenue. In
    # the local cache, 0 of 296 banks (regional and diversified) report a cost
    # of revenue or gross profit line, against 3,042 of 3,257 non-financial
    # companies; 4 of 102 insurers do (TRUP, PRCH, APIC.JK, ABX), the residue
    # this leaves. So a company that reports one is valued as an ordinary
    # company and the notice says why; one that does not is refused.
    sectorless = (choice == "auto" and not (data.get("sector") or "").strip()
                  and not (data.get("industry") or "").strip())
    if sectorless and not _reports_cost_of_revenue(data.get("income")):
        raise ValuationError(
            tr(f"No sector or industry came back for {symbol}, so there is no way to "
               f"tell whether it is a bank, and a bank cannot be valued on free cash "
               f"flow. This is the signature of a throttled fetch rather than a "
               f"company with no sector, and running the lenses again in a couple of "
               f"minutes will usually resolve it.",
               f"Tidak ada sektor atau industri yang kembali untuk {symbol}, jadi tidak "
               "ada cara mengetahui apakah ia bank, dan bank tidak bisa dinilai dengan "
               "arus kas bebas. Ini ciri pengambilan data yang dibatasi, bukan "
               "perusahaan tanpa sektor, dan menjalankan lensa lagi dalam beberapa "
               "menit biasanya menyelesaikannya."), cause="unknown-sector")

    auto_engine, route_reason = detect_engine(data.get("sector"), data.get("industry"))
    if sectorless:
        route_reason = tr("no sector came back; its income statement reports a cost of revenue, which no bank's does",
                          "tidak ada sektor yang kembali; laporan laba ruginya mencantumkan beban "
                          "pokok pendapatan, yang tidak dimiliki laporan bank mana pun")
    if choice == "dcf":
        engine, route_reason = "DCF", tr("manual override", "pilihan manual")
    elif choice == "ddm":
        engine, route_reason = "DDM", tr("manual override", "pilihan manual")
    elif choice == "ri":
        engine, route_reason = "RI", tr("manual override", "pilihan manual")
    else:
        engine = auto_engine

    manual_price_f = _safe_float(manual_price)
    if np.isfinite(manual_price_f) and manual_price_f > 0:
        # Safe to write only because `fetch_company` hands back a per-caller
        # copy. If that copy is ever removed, this line silently rewrites the
        # day's cached price for this symbol for every other request.
        data["price"] = manual_price_f

    # A COMPANY WHOSE ACCOUNTS AND SHARES USE DIFFERENT CURRENCIES IS VALUED IN
    # ONE OF THEM OR IN NEITHER. `market_data.company` converts the statements
    # into the trading currency when it can get a rate; when it cannot, the two
    # are still in different units and every figure this engine produces would be
    # out by the exchange rate. That is a factor of about seventeen thousand for
    # USD/IDR, so it does not look like a rounding error — it looks like a
    # confident answer, which is worse. Refuse instead.
    reporting = data.get("financial_currency")
    trading = (data.get("currency") or "").upper()
    if reporting and trading and reporting != trading and not data.get("fx_rate"):
        raise ValuationError(
            tr(f"{symbol} reports its accounts in {reporting} but its shares trade in "
               f"{trading}, and no {reporting}/{trading} rate could be fetched to reconcile "
               f"them. Valuing the cash flows without it would be out by the exchange rate. "
               f"Enter the figures yourself in {trading} to value it anyway.",
               f"{symbol} melaporkan keuangannya dalam {reporting} tetapi sahamnya "
               f"diperdagangkan dalam {trading}, dan tidak ada kurs {reporting}/{trading}"
               " yang bisa diambil untuk menyelaraskannya. Menilai arus kasnya tanpa "
               "kurs itu akan meleset sebesar nilai tukarnya. Masukkan angkanya sendiri "
               f"dalam {trading} untuk tetap menilainya."),
            manual_required=True,
            missing=[tr(f"{reporting}/{trading} exchange rate", f"kurs {reporting}/{trading}")],
            engine=engine,
            suggested={"price": _nullable(data.get("price")),
                       "shares": _nullable(data.get("shares"))},
        )

    if not data["ok"] or not np.isfinite(data["price"]):
        raise ValuationError(
            tr(f"No usable market data returned for '{symbol}'. {symbols.hint(symbol)} "
               f"Or supply the base figures yourself in manual input mode.",
               f"Tidak ada data pasar yang bisa dipakai untuk '{symbol}'. "
               f"{symbols.hint(symbol)} Atau masukkan sendiri angka dasarnya dalam mode "
               "masukan manual."),
            manual_required=True,
            missing=["price"],
            engine=engine,
            suggested={"price": None, "shares": _nullable(data.get("shares"))},
        )

    defaults = DEFAULTS[engine]
    growth_input = defaults["growth"] if growth is None else float(growth)
    terminal_input = defaults["terminal"] if terminal is None else float(terminal)
    sd_g = defaults["sd"][0] if sd_growth is None else float(sd_growth)
    sd_growth_calibrated = None      # filled in per engine from that engine's history

    sd_r = defaults["sd"][1] if sd_rate is None else float(sd_rate)
    sd_t = defaults["sd"][2] if sd_terminal is None else float(sd_terminal)

    price = data["price"]
    shares = data["shares"]
    tax_rate = effective_tax_rate(data["income"], market["tax_rate"])
    notices: list = []
    # Beta, measured rather than inherited. `data["beta"]` is Yahoo's number
    # against an undisclosed index over an undisclosed window; this regresses the
    # stock on its own market index and shrinks the result toward 1.0 in
    # proportion to the estimate's standard error (Vasicek 1973). The fallback
    # keeps Yahoo's figure with Blume shrinkage when the regression is not
    # possible, and says so in `notes`.
    beta_estimate = riskmodel.estimate_beta_for_symbol(
        symbol, market["code"], fallback_beta=data["beta"]
    )
    beta_used = beta_estimate.adjusted
    for note in beta_estimate.notes:
        notices.append({"tone": "info", "text": note})

    # The [0.4, 2.5] sanity bound is meant to be inert now that shrinkage does
    # the real work — but when it DOES bind it changes the cost of equity, and
    # it used to do so invisibly: the diagnostics table showed the shrunk beta
    # while the discount rate was computed from the clipped one. Two different
    # numbers on the same screen with nothing saying which was used.
    beta_final = clip_beta(beta_used)
    beta_clipped = abs(beta_final - beta_used) > 1e-6
    if beta_clipped:
        notices.append({"tone": "warn", "text":
                        tr(f"Measured beta of {beta_used:.2f} falls outside the [0.40, 2.50] "
                           f"sanity bound, so {beta_final:.2f} was used for the cost of equity. "
                           f"A beta this far from the market usually means a single-factor model "
                           f"describes this security poorly, not that its risk is really that low.",
                           f"Beta terukur {beta_used:.2f} berada di luar batas kewajaran [0.40, "
                           f"2.50], jadi {beta_final:.2f} yang dipakai untuk biaya ekuitas. Beta "
                           "sejauh ini dari pasar biasanya berarti model satu faktor menggambarkan "
                           "efek ini dengan buruk, bukan berarti risikonya memang serendah itu.")})

    if data.get("fx_rate"):
        notices.append({"tone": "warn", "text": (
            tr(f"{symbol} reports its accounts in {reporting} but trades in {trading}. The "
               f"statements were converted at the current spot rate of "
               f"{data['fx_rate']:,.0f} {trading} per {reporting} so that the model and the "
               f"share price are in the same units. A five-year projection converted at "
               f"today's rate carries the currency's risk as well as the company's, and a "
               f"move in the exchange rate moves this valuation with it.",
               f"{symbol} melaporkan keuangannya dalam {reporting} tetapi diperdagangkan "
               f"dalam {trading}. Laporan keuangannya dikonversi dengan kurs spot saat "
               f"ini {data['fx_rate']:,.0f} {trading} per {reporting} agar model dan "
               "harga saham berada dalam satuan yang sama. Proyeksi lima tahun yang "
               "dikonversi dengan kurs hari ini membawa risiko mata uang selain risiko "
               "perusahaan, dan pergerakan nilai tukar ikut menggerakkan valuasi ini."))})

    cash_used = debt_used = 0.0
    cash_label = tr("Cash & equivalents", "Kas & setara kas")
    diagnostics_rows = []
    history_table = []
    bank = None

    RATE_NAME = "WACC" if engine == "DCF" else "Cost of Equity"

    # THE MANUAL-RESCUE FORM EXISTS BECAUSE OF THIS CASE. Yahoo's dividend fields
    # are frequently empty for IDX banks, and a DDM with no dividend has nothing
    # to discount — so the engine used to stop and ask the user to type the
    # figure in. Residual income needs book value and ROE instead, both of which
    # those same filings DO report, so the honest move is to switch models
    # rather than to demand data that is not coming.
    if engine == "DDM" and choice == "auto":
        probe_dps, _ = resolve_dividend(data, price)
        if not np.isfinite(probe_dps) or probe_dps <= 0:
            probe = ri_inputs(data, price, shares)
            if probe["usable"]:
                engine = "RI"
                route_reason = tr("financial with no usable dividend data",
                                  "lembaga keuangan tanpa data dividen yang bisa dipakai")
                RATE_NAME = "Cost of Equity"
                defaults = DEFAULTS["RI"]
                if growth is None:
                    growth_input = defaults["growth"]
                if sd_growth is None:
                    sd_g = defaults["sd"][0]
                notices.append({"tone": "info", "text":
                                tr("No usable dividend data, so this is valued on residual "
                                   "income (book value plus discounted excess returns) rather "
                                   "than on dividends. Ohlson (1995).",
                                   "Tidak ada data dividen yang bisa dipakai, jadi saham ini dinilai dengan "
                                   "pendapatan residual (nilai buku ditambah imbal hasil lebih yang "
                                   "didiskontokan), bukan dengan dividen. Ohlson (1995).")})

    if sectorless:
        notices.append({"tone": "warn", "text":
                        tr("No sector or industry came back for this listing — usually a throttled "
                           "fetch. It is valued as an ordinary company because its income statement "
                           "reports a cost of revenue, which a bank's does not; if it is a financial "
                           "firm after all, this model does not describe it.",
                           "Tidak ada sektor atau industri yang kembali untuk saham ini — biasanya "
                           "karena pengambilan data dibatasi. Ia dinilai sebagai perusahaan biasa "
                           "karena laporan laba ruginya mencantumkan beban pokok pendapatan, yang "
                           "tidak dimiliki bank; jika ternyata ia perusahaan keuangan, model ini "
                           "tidak menggambarkannya.")})
    if auto_engine == "DDM" and engine == "DDM":
        notices.append({"tone": "info", "text":
                        tr("Financial institution detected. Routed from DCF to Dividend Discount Model.",
                           "Lembaga keuangan terdeteksi. Dialihkan dari DCF ke Model Diskonto "
                           "Dividen.")})
    elif auto_engine == "DDM" and engine == "DCF":
        notices.append({"tone": "warn", "text":
                        tr("This is a financial institution, but DCF has been forced. Free cash flow is "
                           "not a meaningful measure for a bank.",
                           "Ini lembaga keuangan, tetapi DCF dipaksakan. Arus kas bebas bukan "
                           "ukuran yang bermakna untuk bank.")})
    elif engine == "RI" and auto_engine == "DCF":
        notices.append({"tone": "warn", "text":
                        tr("Residual income has been forced on a non-financial company. It "
                           "anchors on book value, which understates a business whose value "
                           "is mostly intangible.",
                           "Pendapatan residual dipaksakan pada perusahaan nonkeuangan. Ia "
                           "berjangkar pada nilai buku, yang mengecilkan bisnis yang nilainya "
                           "sebagian besar tak berwujud.")})
    elif auto_engine == "DCF" and engine == "DDM":
        notices.append({"tone": "info", "text":
                        tr("DDM has been forced on a non-financial company. This values only distributed "
                           "cash, so it will understate a business that reinvests.",
                           "DDM dipaksakan pada perusahaan nonkeuangan. Ini hanya menilai kas yang "
                           "dibagikan, jadi akan mengecilkan bisnis yang menginvestasikan kembali "
                           "labanya.")})

    # ---------------- ENGINE 1 — DCF ----------------
    if engine == "DCF":
        fcf_history = build_fcf_history(data["cashflow"])
        cash_auto, debt_auto, cash_label = extract_balance_items(data["balance"])
        interest_expense = _first_valid(_get_row(data["income"], "interest_expense"), np.nan)

        vals = (fcf_history["Free Cash Flow"].astype(float).values
                if not fcf_history.empty else np.array([]))
        auto_base = float(vals[0]) if len(vals) else np.nan

        manual_base_f = _safe_float(manual_base)
        manual_shares_f = _safe_float(manual_shares)
        if np.isfinite(manual_shares_f) and manual_shares_f > 0:
            shares = manual_shares_f

        # A placeholder scaled to the company, not a flat 1e9: an IDX large cap
        # and a US small cap differ by six orders of magnitude, and a default
        # wrong by 1000x reads as a broken app.
        if np.isfinite(auto_base):
            suggested_base = float(auto_base)
        elif np.isfinite(price) and np.isfinite(shares) and price > 0 and shares > 0:
            suggested_base = round(price * shares * 0.05, 0)   # ~5% FCF yield
        else:
            suggested_base = None

        if np.isfinite(manual_base_f):
            # Manual mode mirrors the original: the user gives NET debt, so the
            # bridge carries it entirely on the debt side and cash is zero.
            base_value = float(manual_base_f)
            basis_label = tr("manual input", "masukan manual")
            net_debt = _safe_float(manual_net_debt)
            if not np.isfinite(net_debt):
                net_debt = float(debt_auto - cash_auto)
            cash_used, debt_used = 0.0, float(net_debt)
            notices.append({"tone": "info", "text":
                            tr("Manual input mode: base free cash flow, net debt, shares and price "
                               "are the figures you supplied, not Yahoo's.",
                               "Mode masukan manual: arus kas bebas dasar, utang bersih, jumlah saham, "
                               "dan harga adalah angka yang Anda masukkan, bukan dari Yahoo.")})
        else:
            if fcf_history.empty:
                raise ValuationError(
                    tr("Yahoo returned no usable cash-flow statement for this ticker, so there is "
                       "no base free cash flow to grow. Enter a normalised free cash flow in manual "
                       "input mode, force the DDM engine, or try another symbol.",
                       "Yahoo tidak mengembalikan laporan arus kas yang bisa dipakai untuk "
                       "ticker ini, jadi tidak ada arus kas bebas dasar untuk ditumbuhkan. "
                       "Masukkan arus kas bebas yang dinormalkan dalam mode masukan manual, "
                       "paksakan mesin DDM, atau coba simbol lain."),
                    manual_required=True,
                    missing=["base"],
                    engine="DCF",
                    suggested={"base": suggested_base,
                               "netDebt": float(debt_auto - cash_auto),
                               "shares": _nullable(shares), "price": _nullable(price)},
                )
            if fcf_basis == "3-year average" and len(vals) >= 3:
                base_value = float(np.mean(vals[:3]))
            elif fcf_basis == "3-year weighted (3/2/1)" and len(vals) >= 3:
                base_value = float(np.average(vals[:3], weights=[3, 2, 1]))
            elif fcf_basis == "2-year average" and len(vals) >= 2:
                base_value = float(np.mean(vals[:2]))
            else:
                base_value = float(vals[0])
                fcf_basis = "Latest fiscal year"
            basis_label = fcf_basis
            cash_used, debt_used = cash_auto, debt_auto

        if not np.isfinite(base_value) or base_value <= 0:
            raise ValuationError(
                tr("Base free cash flow is negative or zero. A growth-multiple DCF cannot value "
                   "this — the model would simply scale a negative number. Enter a normalised free "
                   "cash flow in manual input mode, or value the company on another basis.",
                   "Arus kas bebas dasarnya negatif atau nol. DCF berbasis kelipatan "
                   "pertumbuhan tidak bisa menilai ini — model hanya akan menskalakan angka "
                   "negatif. Masukkan arus kas bebas yang dinormalkan dalam mode masukan "
                   "manual, atau nilai perusahaan ini dengan dasar lain."),
                manual_required=True,
                missing=["base"],
                engine="DCF",
                suggested={"base": suggested_base,
                           "netDebt": float(debt_auto - cash_auto),
                           "shares": _nullable(shares), "price": _nullable(price)},
            )
        if not np.isfinite(shares) or shares <= 0:
            raise ValuationError(
                tr("Shares outstanding unavailable for this ticker. Enter it in manual input mode.",
                   "Jumlah saham beredar tidak tersedia untuk ticker ini. Masukkan dalam "
                   "mode masukan manual."),
                manual_required=True,
                missing=["shares"],
                engine="DCF",
                suggested={"base": suggested_base,
                           "netDebt": float(debt_auto - cash_auto),
                           "shares": None, "price": _nullable(price)},
            )

        rate_parts = compute_wacc(
            beta=beta_used, risk_free=rf_rate, erp=market["erp"],
            equity_value=price * shares, total_debt=max(debt_used, 0.0),
            interest_expense=interest_expense, tax_rate=tax_rate,
        )
        discount_rate = float(rate_override) if rate_override is not None else rate_parts["wacc"]

        diagnostics_rows = [
            (tr("Base FCF anchor", "Jangkar FCF dasar"), basis_label),
            (tr("Cost of equity (CAPM)", "Biaya ekuitas (CAPM)"), f"{rate_parts['cost_equity']:.2%}"),
            (tr("Cost of debt (pre-tax)", "Biaya utang (sebelum pajak)"), f"{rate_parts['cost_debt']:.2%}"),
            (tr("Effective tax rate", "Tarif pajak efektif"), f"{tax_rate:.1%}"),
            (tr("Equity / debt weight", "Bobot ekuitas / utang"), f"{rate_parts['weight_equity']:.0%} / {rate_parts['weight_debt']:.0%}"),
            (tr("Beta (clipped)", "Beta (dipotong)"), f"{rate_parts['beta']:.2f}"),
            (tr("Risk-free source", "Sumber suku bunga bebas risiko"), rf_source),
        ]

        history_table = [
            {
                "period": row["Fiscal Year"],
                "operatingCashFlow": fmt_big(row["Operating Cash Flow"], market),
                "capex": fmt_big(row["Capital Expenditure"], market),
                "freeCashFlow": fmt_big(row["Free Cash Flow"], market),
            }
            for _, row in fcf_history.iterrows()
        ]
        # `sd_growth=0.02` was a constant with no provenance, and it sets the
        # entire width of the fan chart. Estimate it from this company's own FCF
        # record instead, shrunk hard toward a prior because four filings give
        # three growth observations. `vals` is newest-first; growth needs
        # chronological order.
        if sd_growth is None:
            sd_growth_calibrated = riskmodel.shrunk_growth_volatility(list(vals)[::-1])
            sd_g = sd_growth_calibrated["sd"]

        basis_options = ["Latest fiscal year"]
        if len(vals) >= 2:
            basis_options.append("2-year average")
        if len(vals) >= 3:
            basis_options += ["3-year average", "3-year weighted (3/2/1)"]

        manual_defaults = {
            "base": suggested_base,
            "netDebt": float(debt_auto - cash_auto),
            "shares": _nullable(shares),
            "price": _nullable(price),
            "payout": None,
        }

    # ---------------- ENGINE 4 — RESIDUAL INCOME ----------------
    elif engine == "RI":
        inputs = ri_inputs(data, price, shares)
        manual_base_f = _safe_float(manual_base)

        if np.isfinite(manual_base_f) and manual_base_f > 0:
            book_per_share = float(manual_base_f)
            basis_label = tr("manual input", "masukan manual")
            notices.append({"tone": "info", "text":
                            tr("Manual input mode: book value per share is the figure you "
                               "supplied, not Yahoo's.",
                               "Mode masukan manual: nilai buku per saham adalah angka yang Anda "
                               "masukkan, bukan dari Yahoo.")})
        elif inputs["usable"]:
            book_per_share = float(inputs["bookPerShare"])
            basis_label = tr("book value per share (latest balance sheet)",
                             "nilai buku per saham (neraca terbaru)")
        else:
            raise ValuationError(
                tr("Residual income needs book value per share and a return on equity, and "
                   "neither could be derived from these filings. Supply book value per share "
                   "in manual input mode, or force the DCF engine.",
                   "Pendapatan residual butuh nilai buku per saham dan imbal hasil ekuitas, "
                   "dan keduanya tidak bisa diturunkan dari laporan keuangan ini. Masukkan "
                   "nilai buku per saham dalam mode masukan manual, atau paksakan mesin DCF."),
                manual_required=True,
                missing=["base"],
                engine="RI",
                suggested={"base": _nullable(inputs["bookPerShare"]),
                           "price": _nullable(price), "payout": inputs["payout"]},
            )

        manual_payout_f = _safe_float(manual_payout)
        payout_used = (float(np.clip(manual_payout_f, 0.0, 1.0))
                       if np.isfinite(manual_payout_f) else inputs["payout"])

        roe_used = float(np.clip(inputs["roe"], *RI_ROE_BOUNDS)) \
            if np.isfinite(inputs["roe"]) else DEFAULTS["RI"]["growth"]
        if growth is not None:
            roe_used = float(growth)
        growth_input = roe_used
        base_value = book_per_share

        bank = bank_diagnostics(data, np.nan, price, shares)
        rate_parts = {
            "beta": clip_beta(beta_used),
            "cost_equity": cost_of_equity(beta_used, rf_rate, market["erp"]),
        }
        discount_rate = float(rate_override) if rate_override is not None else rate_parts["cost_equity"]

        if sd_growth is None:
            # Dispersion of the SUSTAINED ROE, from the equity and income record.
            equity_row = _get_row(data["balance"], "equity")
            income_row = _get_row(data["income"], "net_income")
            roe_history = []
            if equity_row is not None and income_row is not None:
                for column in list(data["balance"].columns)[:5]:
                    eq = _safe_float(equity_row.get(column))
                    ni = _safe_float(income_row.get(column)) if column in income_row.index else np.nan
                    if np.isfinite(eq) and eq > 0 and np.isfinite(ni):
                        roe_history.append(ni / eq)
            if len(roe_history) >= 3:
                sd_growth_calibrated = riskmodel.shrunk_growth_volatility(
                    [1.0 + r for r in roe_history][::-1]
                )
                sd_g = sd_growth_calibrated["sd"]
            else:
                sd_g = DEFAULTS["RI"]["sd"][0]

        excess = roe_used - discount_rate
        if excess <= 0:
            notices.append({"tone": "warn", "text":
                            tr(f"Return on equity of {roe_used:.1%} is at or below the "
                               f"{discount_rate:.1%} cost of equity, so residual income is "
                               f"negative and the model values the company below its book. "
                               f"That is a real result, not an error.",
                               f"Imbal hasil ekuitas {roe_used:.1%} berada di bawah atau setara biaya "
                               f"ekuitas {discount_rate:.1%}, jadi pendapatan residualnya negatif dan "
                               "model menilai perusahaan di bawah nilai bukunya. Itu hasil sungguhan, "
                               "bukan kesalahan.")})

        diagnostics_rows = [
            (tr("Book value per share", "Nilai buku per saham"), fmt_price(book_per_share, market)),
            (tr("Return on equity (sustained)", "Imbal hasil ekuitas (berkelanjutan)"), f"{roe_used:.1%}"),
            (tr("Cost of equity (CAPM)", "Biaya ekuitas (CAPM)"), f"{rate_parts['cost_equity']:.2%}"),
            (tr("Excess return (ROE - r)", "Imbal hasil lebih (ROE - r)"), f"{excess:+.1%}"),
            (tr("Retention ratio", "Rasio laba ditahan"), f"{1 - payout_used:.0%}"),
            (tr("Abnormal earnings persistence", "Persistensi laba abnormal"), f"{RI_PERSISTENCE:.2f} (Dechow-Hutton-Sloan 1999)"),
            (tr("Beta (clipped)", "Beta (dipotong)"), f"{rate_parts['beta']:.2f}"),
            (tr("Risk-free source", "Sumber suku bunga bebas risiko"), rf_source),
        ]

        div_history = data.get("dividend_history", pd.DataFrame())
        history_table = [
            {"period": row["Year"], "dividendPerShare": fmt_dps(row["Dividend / Share"], market)}
            for _, row in div_history.iterrows()
        ] if isinstance(div_history, pd.DataFrame) and not div_history.empty else []
        basis_options = [basis_label]
        manual_defaults = {
            "base": _nullable(book_per_share),
            "netDebt": None,
            "shares": _nullable(shares),
            "price": _nullable(price),
            "payout": payout_used,
        }

    # ---------------- ENGINE 2 — DDM ----------------
    else:
        auto_dps, dps_source = resolve_dividend(data, price)
        div_history = data.get("dividend_history", pd.DataFrame())
        complete = complete_years(div_history)

        manual_base_f = _safe_float(manual_base)
        suggested_dps = (float(auto_dps) if np.isfinite(auto_dps) and auto_dps > 0
                         else (round(float(price) * 0.03, 4)
                               if np.isfinite(price) and price > 0 else None))

        if np.isfinite(manual_base_f) and manual_base_f > 0:
            base_value = float(manual_base_f)
            dps_source = tr("manual input", "masukan manual")
            basis_label = tr("manual input", "masukan manual")
            notices.append({"tone": "info", "text":
                            tr("Manual input mode: the dividend per share is the figure you "
                               "supplied, not Yahoo's.",
                               "Mode masukan manual: dividen per saham adalah angka yang Anda masukkan, "
                               "bukan dari Yahoo.")})
        else:
            if not np.isfinite(auto_dps) or auto_dps <= 0:
                raise ValuationError(
                    tr("No usable dividend data returned, so a Dividend Discount Model has nothing "
                       "to discount. Bank dividend fields are frequently empty on Yahoo, especially "
                       "for IDX listings — enter the figure in manual input mode. If the company "
                       "genuinely pays no dividend, force the DCF engine instead.",
                       "Tidak ada data dividen yang bisa dipakai, jadi Model Diskonto Dividen "
                       "tidak punya apa pun untuk didiskontokan. Kolom dividen bank sering "
                       "kosong di Yahoo, terutama untuk saham BEI — masukkan angkanya dalam "
                       "mode masukan manual. Jika perusahaan memang tidak membagikan dividen, "
                       "paksakan mesin DCF."),
                    manual_required=True,
                    missing=["base"],
                    engine="DDM",
                    suggested={"base": suggested_dps, "price": _nullable(price),
                               "payout": 0.40},
                )
            if dps_basis == "Last full year" and len(complete) >= 1:
                base_value = float(complete["Dividend / Share"].iloc[0])
                dps_source = tr(f"FY{complete['Year'].iloc[0]} declared",
                                f"FY{complete['Year'].iloc[0]} diumumkan")
            elif dps_basis == "3-year average" and len(complete) >= 3:
                base_value = float(complete["Dividend / Share"].iloc[:3].mean())
                dps_source = tr("3-year average of declared dividends",
                                "rata-rata 3 tahun dividen yang diumumkan")
            else:
                base_value = float(auto_dps)
                dps_basis = "Trailing 12 months"
            basis_label = dps_basis

        bank = bank_diagnostics(data, base_value, price, shares)

        # A supplied payout ratio feeds the sustainable-growth diagnostic only;
        # it never touches the valuation itself.
        manual_payout_f = _safe_float(manual_payout)
        if np.isfinite(manual_payout_f):
            bank["payout"] = manual_payout_f
            bank["payout_clean"] = float(np.clip(manual_payout_f, 0.0, 1.0))
            if np.isfinite(bank["roe"]):
                bank["sustainable_growth"] = bank["roe"] * (1 - bank["payout_clean"])

        rate_parts = {
            "beta": clip_beta(beta_used),
            "cost_equity": cost_of_equity(beta_used, rf_rate, market["erp"]),
        }
        discount_rate = float(rate_override) if rate_override is not None else rate_parts["cost_equity"]

        diagnostics_rows = [
            (tr("Base DPS source", "Sumber DPS dasar"), dps_source),
            (tr("Current dividend yield", "Imbal hasil dividen saat ini"),
             f"{bank['dividend_yield']:.2%}" if np.isfinite(bank["dividend_yield"]) else "n/a"),
            (tr("Payout ratio", "Rasio pembayaran dividen"), f"{bank['payout']:.1%}" if np.isfinite(bank["payout"]) else "n/a"),
            (tr("Return on equity", "Imbal hasil ekuitas"), f"{bank['roe']:.1%}" if np.isfinite(bank["roe"]) else "n/a"),
            (tr("Sustainable growth (ROE x retention)",
                "Pertumbuhan berkelanjutan (ROE x laba ditahan)"),
             f"{bank['sustainable_growth']:.1%}" if np.isfinite(bank["sustainable_growth"]) else "n/a"),
            (tr("Cost of equity (CAPM)", "Biaya ekuitas (CAPM)"), f"{rate_parts['cost_equity']:.2%}"),
            (tr("Beta (clipped)", "Beta (dipotong)"), f"{rate_parts['beta']:.2f}"),
            (tr("Risk-free source", "Sumber suku bunga bebas risiko"), rf_source),
        ]

        history_table = [
            {"period": row["Year"], "dividendPerShare": fmt_dps(row["Dividend / Share"], market)}
            for _, row in div_history.iterrows()
        ] if isinstance(div_history, pd.DataFrame) and not div_history.empty else []
        # Complete years only: a year to date read as a year is a dividend cut,
        # and one of those among three observations sets the fan's whole width.
        if sd_growth is None and not complete.empty:
            declared = list(complete["Dividend / Share"].astype(float))[::-1]
            sd_growth_calibrated = riskmodel.shrunk_growth_volatility(declared)
            sd_g = sd_growth_calibrated["sd"]

        basis_options = ["Trailing 12 months"]
        if len(complete) >= 1:
            basis_options.append("Last full year")
        if len(complete) >= 3:
            basis_options.append("3-year average")

        manual_defaults = {
            "base": suggested_dps,
            "netDebt": None,
            "shares": _nullable(shares),
            "price": _nullable(price),
            "payout": _nullable(bank.get("payout_clean")),
        }

    # ---------------- Terminal growth guard-rail ----------------
    if engine == "RI":
        # No Gordon terminal here: abnormal earnings FADE at RI_PERSISTENCE
        # rather than growing forever, so there is nothing to cap and no
        # divergence to guard against. This is the structural reason residual
        # income does not inherit the terminal-value dominance problem.
        terminal_growth = 0.0
    else:
        terminal_growth = min(terminal_input, discount_rate - MIN_SPREAD)
        if terminal_growth < terminal_input:
            notices.append({"tone": "warn", "text":
                            tr(f"Perpetual growth capped at {terminal_growth:.2%} to hold 150bp below the "
                               f"{discount_rate:.2%} {RATE_NAME}. At or above it the Gordon Growth terminal "
                               f"value diverges to infinity.",
                               f"Pertumbuhan abadi dibatasi {terminal_growth:.2%} agar tetap 150bp di "
                               f"bawah {RATE_NAME} {discount_rate:.2%}. Pada atau di atasnya, nilai "
                               "terminal Gordon Growth menjadi tak hingga.")})

    # ---------------- Run ----------------
    if engine == "RI":
        value, pv_explicit, pv_continuing, ri_schedule = residual_income_value(
            np.array([base_value]), np.array([growth_input]),
            np.array([discount_rate]), np.array([payout_used]),
        )
        implied = float(value[0])
        summary = {
            "pv_explicit": float(pv_explicit[0]),
            "pv_terminal": float(pv_continuing[0]),
            "terminal_value": float(pv_continuing[0]),
            "terminal_share": (float(pv_continuing[0]) / implied) if implied else np.nan,
            "gross": implied,
            "equity_value": implied,
            "implied_price": implied,
        }
        schedule = pd.DataFrame({
            "Year": [f"Y{step['year']}" for step in ri_schedule],
            "Opening Book": [float(step["openingBook"][0]) for step in ri_schedule],
            "Residual Income": [float(step["residual"][0]) for step in ri_schedule],
            "Discount Factor": [1.0 / float(step["discount"][0]) for step in ri_schedule],
            "Present Value": [float(step["residual"][0]) / float(step["discount"][0])
                              for step in ri_schedule],
        })
    else:
        schedule, summary = base_case_schedule(
            engine, base_value, growth_input, discount_rate, terminal_growth,
            cash=cash_used, debt=debt_used, shares=shares if engine == "DCF" else 1.0,
        )

    # WHAT THE MARKET IS ALREADY ASSUMING. The forward model answers "what is it
    # worth?"; inverting it answers "what would have to be true for today's price
    # to be right?" — which is the question a reader can actually take a view on.
    # Residual income is excluded: its value is book value plus excess returns
    # rather than a discounted growing stream, so a single growth rate is not the
    # lever that moves it and solving for one would be a number without meaning.
    implied_g = None
    if engine in ("DCF", "DDM"):
        implied_g = implied_growth(
            engine, price, base_value, discount_rate, terminal_growth,
            cash=cash_used, debt=debt_used,
            shares=shares if engine == "DCF" else 1.0,
        )

    # The same model across a grid of its two biggest inputs. Computed from the
    # inputs actually used above, so its assumed cell IS the base case.
    sensitivity = sensitivity_grid(
        engine, base_value, growth_input, discount_rate, terminal_growth,
        cash=cash_used, debt=debt_used, shares=shares if engine == "DCF" else 1.0,
        payout=payout_used if engine == "RI" else 0.0, price=price,
        fmt=lambda v: fmt_price(v, market),
    )

    sims = run_monte_carlo(
        engine, base_value, growth_input, discount_rate, terminal_growth,
        n_sims=n_sims, sd_growth=sd_g, sd_rate=sd_r, sd_terminal=sd_t,
        seed=seed, cash=cash_used, debt=debt_used,
        shares=shares if engine == "DCF" else 1.0,
        payout=payout_used if engine == "RI" else 0.0,
    )

    prices = sims["Implied Price"].values
    p05, p25, p50, p75, p95 = np.percentile(prices, [5, 25, 50, 75, 95])
    prob_undervalued = float((prices > price).mean())
    upside = (p50 - price) / price if price else np.nan

    verdict = ("UNDERVALUED" if upside > 0.15 else
               "OVERVALUED" if upside < -0.15 else "FAIRLY VALUED")

    # Histogram is built server-side so the wire carries 60 bins, not N floats.
    lo, hi = np.percentile(prices, [0.5, 99.5])
    display = prices[(prices >= lo) & (prices <= hi)]
    counts, edges = np.histogram(display, bins=60)
    histogram = [
        {"value": float((edges[i] + edges[i + 1]) / 2), "count": int(counts[i])}
        for i in range(len(counts))
    ]

    # ---------------- Post-run sanity checks ----------------
    if np.isfinite(summary["terminal_share"]) and summary["terminal_share"] > 0.80:
        notices.append({"tone": "warn", "text":
                        tr(f"Terminal value is {summary['terminal_share']:.0%} of total value. The answer "
                           f"rests on the perpetuity assumption rather than the five-year forecast.",
                           f"Nilai terminal adalah {summary['terminal_share']:.0%} dari total nilai. "
                           "Jawabannya bertumpu pada asumsi perpetuitas, bukan ramalan lima tahun.")})

    if engine == "DDM" and bank is not None:
        sustainable = _safe_float(bank.get("sustainable_growth"))
        if np.isfinite(sustainable) and growth_input > sustainable + 0.03:
            notices.append({"tone": "warn", "text":
                            tr(f"Dividend growth of {growth_input:.1%} exceeds the sustainable rate of "
                               f"{sustainable:.1%} (ROE x retention). The bank would have to raise equity "
                               f"or run down its capital ratios to fund that path.",
                               f"Pertumbuhan dividen {growth_input:.1%} melampaui laju berkelanjutan "
                               f"{sustainable:.1%} (ROE x laba ditahan). Bank harus menambah modal atau "
                               "menggerus rasio permodalannya untuk mendanai jalur itu.")})
        payout_check = _safe_float(bank.get("payout"))
        if np.isfinite(payout_check) and payout_check > 0.90:
            notices.append({"tone": "warn", "text":
                            tr(f"Payout ratio is {payout_check:.0%}. There is little retained earnings "
                               f"cushion, so the dividend growth assumption is fragile.",
                               f"Rasio pembayaran dividen {payout_check:.0%}. Bantalan laba ditahan "
                               "tipis, jadi asumsi pertumbuhan dividennya rapuh.")})

    if beta_estimate.method == "vasicek":
        trail = (tr(f"{beta_estimate.raw:.2f} raw (se {beta_estimate.stderr:.2f}, "
                    f"R2 {beta_estimate.r_squared:.0%}, {beta_estimate.observations}d vs "
                    f"{beta_estimate.index_symbol}) -> {beta_estimate.adjusted:.2f} shrunk",
                    f"{beta_estimate.raw:.2f} mentah (se {beta_estimate.stderr:.2f}, R2 "
                    f"{beta_estimate.r_squared:.0%}, {beta_estimate.observations}h vs "
                    f"{beta_estimate.index_symbol}) -> {beta_estimate.adjusted:.2f} disusutkan"))
        if beta_clipped:
            trail += tr(f" -> {beta_final:.2f} clipped (used)",
                        f" -> {beta_final:.2f} dipotong (dipakai)")
        diagnostics_rows.append((tr("Beta estimate", "Estimasi beta"), trail))
    if sd_growth_calibrated is not None:
        source = sd_growth_calibrated["source"]
        diagnostics_rows.append((
            tr("Growth dispersion (sigma)", "Sebaran pertumbuhan (sigma)"),
            tr(f"{sd_growth_calibrated['sd']:.1%} from {source}",
               f"{sd_growth_calibrated['sd']:.1%} dari {source}")
            + (tr(f", {sd_growth_calibrated['observations']} observations",
                  f", {sd_growth_calibrated['observations']} pengamatan")
               if sd_growth_calibrated["observations"] else ""),
        ))

    diagnostics_rows += [
        (tr("Terminal value as % of total", "Nilai terminal sebagai % dari total"),
         f"{summary['terminal_share']:.0%}" if np.isfinite(summary["terminal_share"]) else "n/a"),
        (tr("P5 - P95 range", "Rentang P5 - P95"), f"{fmt_price(p05, market)} - {fmt_price(p95, market)}"),
    ]

    if engine == "RI":
        stream_label = "Residual income / share"
        schedule_rows = [
            {
                "year": row["Year"],
                "stream": fmt_dps(row["Residual Income"], market),
                "streamRaw": float(row["Residual Income"]),
                "openingBook": fmt_price(row["Opening Book"], market),
                "discountFactor": f"{row['Discount Factor']:.4f}",
                "presentValue": fmt_dps(row["Present Value"], market),
                "presentValueRaw": float(row["Present Value"]),
            }
            for _, row in schedule.iterrows()
        ]
        bridge = [
            (tr("Book value per share", "Nilai buku per saham"), fmt_price(base_value, market)),
            (tr("+ PV of Year 1-5 residual income", "+ PV pendapatan residual tahun 1-5"), fmt_dps(summary["pv_explicit"], market)),
            (tr(f"+ PV of fading residual income (w={RI_PERSISTENCE:.2f})",
                f"+ PV pendapatan residual yang memudar (w={RI_PERSISTENCE:.2f})"),
             fmt_dps(summary["pv_terminal"], market)),
            (tr("Implied price (base case)", "Harga tersirat (kasus dasar)"), fmt_price(summary["implied_price"], market)),
            (tr("Implied price / book", "Harga tersirat / nilai buku"),
             f"{summary['implied_price'] / base_value:.2f}x" if base_value else "n/a"),
            (tr("Market price", "Harga pasar"), fmt_price(price, market)),
        ]
        stream_label_out = stream_label
    else:
        stream_label_out = None

    stream_label = stream_label_out or ("Projected FCF" if engine == "DCF" else "Projected DPS")
    fmt_stream = fmt_big if engine == "DCF" else fmt_dps
    if engine != "RI":
            schedule_rows = [
            {
                "year": row["Year"],
                "stream": fmt_stream(row[stream_label], market),
                "streamRaw": float(row[stream_label]),
                "discountFactor": f"{row['Discount Factor']:.4f}",
                "presentValue": fmt_stream(row["Present Value"], market),
                "presentValueRaw": float(row["Present Value"]),
            }
            for _, row in schedule.iterrows()
        ]

    if engine == "RI":
        pass                      # bridge already built above
    elif engine == "DCF":
        bridge = [
            (tr("PV of Year 1-5 FCF", "PV FCF tahun 1-5"), fmt_big(summary["pv_explicit"], market)),
            (tr("PV of terminal value", "PV nilai terminal"), fmt_big(summary["pv_terminal"], market)),
            (tr("Enterprise value", "Nilai perusahaan"), fmt_big(summary["gross"], market)),
            (f"+ {cash_label}", fmt_big(cash_used, market)),
            (tr("- Total debt", "- Total utang"), fmt_big(debt_used, market)),
            (tr("Equity value", "Nilai ekuitas"), fmt_big(summary["equity_value"], market)),
            (tr("/ Shares outstanding", "/ Saham beredar"), f"{shares:,.0f}"),
            (tr("Implied price (base case)", "Harga tersirat (kasus dasar)"), fmt_price(summary["implied_price"], market)),
        ]
    else:
        bridge = [
            (tr("PV of Year 1-5 dividends", "PV dividen tahun 1-5"), fmt_dps(summary["pv_explicit"], market)),
            (tr("PV of terminal value", "PV nilai terminal"), fmt_dps(summary["pv_terminal"], market)),
            (tr("Implied price (base case)", "Harga tersirat (kasus dasar)"), fmt_price(summary["implied_price"], market)),
            (tr("Terminal value at Y5", "Nilai terminal pada T5"), fmt_dps(summary["terminal_value"], market)),
            (tr("Implied forward yield", "Imbal hasil ke depan tersirat"),
             f"{base_value * (1 + growth_input) / summary['implied_price']:.2%}"
             if summary["implied_price"] else "n/a"),
            (tr("Market price", "Harga pasar"), fmt_price(price, market)),
        ]

    manual_applied = {
        "base": np.isfinite(_safe_float(manual_base)),
        "netDebt": np.isfinite(_safe_float(manual_net_debt)),
        "shares": np.isfinite(_safe_float(manual_shares)),
        "price": np.isfinite(_safe_float(manual_price)),
        "payout": np.isfinite(_safe_float(manual_payout)),
    }

    payload = {
        "ticker": symbol,
        "name": data["name"],
        "sector": data["sector"] or None,
        "industry": data["industry"] or None,
        "market": {"code": market["code"], "name": market["name"], "symbol": market["symbol"]},
        "engine": engine,
        "autoEngine": auto_engine,
        "routeReason": route_reason,
        "rateName": RATE_NAME,
        "price": float(price),
        "priceLabel": fmt_price(price, market),
        # Where this price came from and which bar it belongs to. On the panel
        # so a reader can tell a Friday close from a live quote rather than
        # assuming the number is current.
        # Currency provenance. Null unless the accounts and the shares disagree.
        "reportingCurrency": reporting if reporting and reporting != trading else None,
        "fxRate": _nullable(data.get("fx_rate")),
        # THE APP OVERRODE THE SOURCE'S CURRENCY LABEL ON THIS NAME. Present
        # only when `market_data._apply_fx` could show that converting would put
        # the company's revenue far out of line with its own market value while
        # the unconverted figures are in line with it. It is a rare and loud
        # thing to do, so it is said rather than done quietly — a reader must
        # not meet it as an unexplained difference from the filing.
        # The provider record is cached for every reader, so it carries both
        # languages and this request takes its own.
        "fxLabelOverride": ({**data["fx_skipped"],
                             "reason": tr(data["fx_skipped"].get("reason"),
                                          data["fx_skipped"].get("reasonId")
                                          or data["fx_skipped"].get("reason"))}
                            if data.get("fx_skipped") else None),
        "priceSource": (tr("manual entry", "entri manual") if np.isfinite(manual_price_f) and manual_price_f > 0
                        else data.get("price_source")),
        "priceAsOf": (None if np.isfinite(manual_price_f) and manual_price_f > 0
                      else data.get("price_as_of")),
        "discountRate": float(discount_rate),
        "riskFree": float(rf_rate),
        "riskFreeSource": rf_source,
        "erp": market["erp"],
        "beta": float(rate_parts["beta"]),
        "betaEstimate": {**beta_estimate.as_dict(),
                         "used": float(beta_final),
                         "clipped": bool(beta_clipped)},
        "assumptions": {
            "growth": growth_input,
            "terminalGrowth": terminal_growth,
            "terminalRequested": terminal_input,
            "sdGrowth": sd_g,
            "sdRate": sd_r,
            "sdTerminal": sd_t,
            "iterations": int(n_sims),
            "seed": int(seed),
            "basis": basis_label,
            "basisOptions": basis_options,
            "rateOverridden": rate_override is not None,
            "sdGrowthCalibration": sd_growth_calibrated,
            "manualApplied": {k: bool(v) for k, v in manual_applied.items()},
            "manualDefaults": manual_defaults,
        },
        "baseCase": {
            "impliedPrice": float(summary["implied_price"]),
            "impliedPriceLabel": fmt_price(summary["implied_price"], market),
            "terminalShare": float(summary["terminal_share"])
            if np.isfinite(summary["terminal_share"]) else None,
            # The growth rate today's price implies, and the one you assumed, so
            # the panel can put them side by side. `None` means the price is not
            # reachable anywhere in the solver's bracket, which is itself worth
            # saying rather than hiding.
            "impliedGrowth": _nullable(implied_g),
            "assumedGrowth": float(growth_input),
        },
        "monteCarlo": {
            "p05": float(p05), "p25": float(p25), "p50": float(p50),
            "p75": float(p75), "p95": float(p95),
            "p05Label": fmt_price(p05, market), "p25Label": fmt_price(p25, market),
            "p50Label": fmt_price(p50, market), "p75Label": fmt_price(p75, market),
            "p95Label": fmt_price(p95, market),
            "probUndervalued": prob_undervalued,
            "upside": float(upside) if np.isfinite(upside) else None,
            "histogram": histogram,
        },
        "verdict": verdict,
        "sensitivity": sensitivity,
        "schedule": schedule_rows,
        "streamLabel": stream_label,
        "bridge": [{"component": k, "amount": v} for k, v in bridge],
        "diagnostics": [{"metric": k, "value": v} for k, v in diagnostics_rows],
        "history": history_table,
        "notices": notices,
    }

    if with_simulation:
        # A DataFrame, not JSON. The CSV route pops it before serialisation;
        # `clean()` never sees it.
        payload["_simulation"] = sims

    return payload
