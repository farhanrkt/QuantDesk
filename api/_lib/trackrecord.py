"""
trackrecord.py
==============
What the filings say the business has actually done — profits, cash, growth.

WHY THIS IS SEPARATE FROM `quality.py`
---------------------------------------
The accounting screens answer "is anything wrong here": Piotroski counts nine
improving-or-not signals, Altman asks about solvency, Beneish about
manipulation. All three compress into a number, and all three REFUSE on a bank,
correctly, because none was built on one.

The owner's question is simpler and the refusal does not apply to it. "Is it
profitable, and is it growing" is meaningful for a bank, a miner and a cable
layer alike; it is the working-capital and receivables machinery inside the
screens that does not transfer, not the concept of earning money. So this module
applies to everyone, reports the raw record rather than a score, and suppresses
only the measures that genuinely do not travel.

"PROFITABLE" ON ITS OWN IS NOT A SCREEN, AND THE NUMBER SAYS SO
-----------------------------------------------------------------
Measured on the 523 Indonesian listings in the local cache with three or more
years of statements:

    profitable in EVERY available year        350   67%
    operating cash flow positive, latest       418   80%
    revenue CAGR over the available years      median 5.0%, p75 14.8%

Two thirds of the exchange is profitable every year. A flag that admits two
thirds of the market is not a finding, and shipping one as a "quality" filter
would be the same mistake this codebase has made before under a different name.

So profitability ships as DESCRIPTION. The narrowing is the conjunction, and it
is reported with its own base rate at every step:

    every year profitable                      350   67%
    + operating cash flow positive             301   58%
    + revenue CAGR >= 15%                       73   14%

GROWING_AT IS THE MARKET'S OWN TOP QUARTILE, not a round number that looked
right: p75 of the revenue CAGR distribution is 14.8%.

FOUR YEARS IS NOT A TRACK RECORD, AND CALLING IT ONE WOULD BE THE LIE
-----------------------------------------------------------------------
The median listing here has FOUR annual columns. That does not span a business
cycle, it does not include 2020, and on this exchange those particular years
were a commodity upswing — so "profitable every year" on an Indonesian coal name
is close to a statement about the coal price. `yearsAvailable` is reported
beside every consistency figure for that reason, and the reading names the
window rather than implying a history it does not have.

PROFIT THAT HAS NOT ARRIVED AS CASH IS REPORTED, NOT NETTED OFF
------------------------------------------------------------------
KETR.JK — the name this whole line of work was asked for — is profitable in all
four available years and grew revenue at 28.6% a year. Its FREE cash flow was
NEGATIVE in three of those four, because it was spending more on laying cable
than the business threw off. That is not a contradiction and it is not a
red flag: it is what a company building out an asset base looks like, and
whether it is good or bad depends on what the spending buys.

Which is exactly why it is reported as its own line rather than folded into a
verdict. A screen that quietly demoted KETR for negative free cash flow would
have been wrong about the one company it was built to find, and a screen that
ignored the figure would be hiding the main thing a reader should ask about.

NO PREDICTIVE CLAIM
-------------------
Nothing here scores, gates or moves a verdict. `PRODUCT.md` constraint 2 applies
to features that imply returns and this one describes the past. The same
point-in-time wall `neglect.py` publishes applies if anyone tries to backtest
it: these statements are as restated today, not as they stood.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from .quality import is_financial
from .valuation import _get_row

# Fewer years than this and "every year" means almost nothing. Three is the
# floor; the median listing has four, which is itself short — see the docstring.
MIN_YEARS = 3

# Revenue growth at or above which the record counts as growing. This is p75 of
# the measured distribution across 520 Indonesian listings (14.8%), rounded to
# the nearest whole point. It is the market's own top quartile rather than a
# threshold picked because it sounded ambitious.
GROWING_AT = 0.15

# The median net-debt-to-EBITDA of the Indonesian listings that borrow at all.
# NOT A THRESHOLD — nothing is flagged against it. It is carried so the reading
# can say where a company sits in its own market rather than against a textbook
# line that happens to fall on this exchange's median.
MARKET_MEDIAN_LEVERAGE = 3.0


def _series(frame, key: str) -> Optional[pd.Series]:
    row = _get_row(frame, key)
    if row is None:
        return None
    clean = pd.Series(row).dropna()
    return clean if len(clean) else None


def _finite(value) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if np.isfinite(out) else None


def _cagr(newest: float, oldest: float, periods: int) -> Optional[float]:
    """Compound annual growth, or None where the arithmetic has no meaning.

    A NEGATIVE OR ZERO BASE HAS NO GROWTH RATE. Revenue rarely goes negative but
    it does reach zero, and `(new/0) ** (1/n)` is an infinity that would sort to
    the top of any list of fast growers.
    """
    if periods < 1 or oldest <= 0 or newest <= 0:
        return None
    return float((newest / oldest) ** (1.0 / periods) - 1.0)


def read(company: Optional[dict]) -> dict:
    """Profits, cash and growth over the years the statements cover."""
    record = company if isinstance(company, dict) else {}
    income = record.get("income")
    net_income = _series(income, "net_income")
    revenue = _series(income, "revenue")

    if net_income is None or len(net_income) < MIN_YEARS:
        got = 0 if net_income is None else len(net_income)
        return {
            "available": False,
            "yearsAvailable": got,
            "reason": (f"only {got} year{'' if got == 1 else 's'} of income statement "
                       f"came back, and {MIN_YEARS} is the fewest on which "
                       f"'every year' means anything"),
        }

    years = len(net_income)
    profitable = int(sum(1 for v in net_income.values if v > 0))
    every_year = profitable == years

    ocf = _series(record.get("cashflow"), "ocf")
    ocf_latest = _finite(ocf.values[0]) if ocf is not None and len(ocf) else None
    fcf = _series(record.get("cashflow"), "fcf")
    fcf_years = (int(sum(1 for v in fcf.values if v > 0)) if fcf is not None else None)

    latest_profit = _finite(net_income.values[0])
    latest_revenue = (_finite(revenue.values[0])
                      if revenue is not None and len(revenue) else None)
    margin = (latest_profit / latest_revenue
              if latest_profit is not None and latest_revenue and latest_revenue > 0
              else None)

    equity = _series(record.get("balance"), "equity")
    book = _finite(equity.values[0]) if equity is not None and len(equity) else None
    roe = (latest_profit / book if latest_profit is not None and book and book > 0
           else None)

    growth = None
    if revenue is not None and len(revenue) >= MIN_YEARS:
        growth = _cagr(_finite(revenue.values[0]) or 0.0,
                       _finite(revenue.values[-1]) or 0.0, len(revenue) - 1)
    profit_growth = _cagr(_finite(net_income.values[0]) or 0.0,
                          _finite(net_income.values[-1]) or 0.0, years - 1)

    # WHAT IT OWES, AND WHETHER THE PROFIT IS BEING BORROWED AGAINST.
    #
    # A small profitable company with net cash and one with six times its
    # earnings in debt are not the same proposition, and nothing else on this
    # panel separates them: Altman scores solvency on a combined index, and the
    # growth and margin figures are identical for both.
    #
    # NO "TOO MUCH DEBT" FLAG, AND THE MEASUREMENT IS WHY. Across the 467
    # non-financial Indonesian listings in the local cache with an EBIT line,
    # 181 — 39% — carry net cash, and of the 242 that carry net debt the MEDIAN
    # is 3.0x EBITDA. The textbook line for "levered" is 3x, which on this
    # exchange is the middle of the distribution: a flag there would mark half
    # the borrowers and mean nothing. So the ratio is reported with the market's
    # own median beside it and the reader draws the line.
    # AT LEAST ONE OF THE THREE LINES HAS TO HAVE ARRIVED.
    #
    # Defaulting each missing line to zero and subtracting gives net debt of
    # zero for a company whose balance sheet did not come back at all — and zero
    # net debt reads as `netCash: True`, so the reading told a reader it "holds
    # more cash than borrowings, which 39% of this market also does". That is a
    # fabricated fact about a company nothing was known about, which is the
    # gap-reported-as-a-finding this codebase keeps having to undo.
    #
    # Where SOME of the three arrived, zero is the right default for the rest: a
    # balance sheet that reports cash and carries no long-term debt line is a
    # company without long-term debt, and `valuation.py` reads it the same way.
    cash_line = _latest(record.get("balance"), "cash")
    long_term = _latest(record.get("balance"), "long_term_debt")
    short_term = _latest(record.get("balance"), "short_term_debt")
    balance_read = any(line is not None
                       for line in (cash_line, long_term, short_term))

    cash = cash_line or 0.0
    borrowings = (long_term or 0.0) + (short_term or 0.0)
    ebit = _latest(income, "ebit")
    depreciation = abs(_latest(record.get("cashflow"), "depreciation") or 0.0)
    net_debt = (borrowings - cash) if balance_read else None
    ebitda = (ebit + depreciation) if ebit is not None else None
    leverage = (net_debt / ebitda
                if net_debt is not None and net_debt > 0
                and ebitda is not None and ebitda > 0 else None)

    # FREE CASH FLOW DOES NOT TRAVEL TO A BANK. Capital expenditure on a lender's
    # cash flow statement is premises and software, not the engine of the
    # business, so FCF describes nothing about whether it is working. Reported as
    # not applicable rather than as a number nobody should read.
    financial = is_financial(record.get("sector") or "", record.get("industry") or "")

    cash_backed = bool(ocf_latest is not None and ocf_latest > 0)
    growing = bool(growth is not None and growth >= GROWING_AT)
    # THE CONJUNCTION IS THE SCREEN; the first condition alone admits 67% of the
    # market. See the docstring for each step's own base rate.
    consistent = bool(every_year and years >= MIN_YEARS and cash_backed)

    return {
        "available": True,
        "yearsAvailable": years,
        "yearsProfitable": profitable,
        "everyYearProfitable": every_year,
        "latestNetMargin": margin,
        "returnOnEquity": roe,
        "operatingCashFlowPositive": cash_backed,
        "freeCashFlowYears": None if financial else fcf_years,
        "freeCashFlowOf": None if financial or fcf is None else len(fcf),
        "revenueCagr": growth,
        "profitCagr": profit_growth,
        # Suppressed for lenders for the same reason free cash flow is: a bank's
        # borrowings ARE its business, so netting them against its cash
        # describes nothing about whether it is working.
        # `None` on all three where the question does not apply (a lender) OR
        # where the balance sheet never arrived. False would say "this company
        # borrows"; None says nothing, which is the truth in both cases.
        "netDebt": None if financial else net_debt,
        "netCash": (None if financial or net_debt is None
                    else bool(net_debt <= 0)),
        "netDebtToEbitda": None if financial else leverage,
        "growing": growing,
        "consistentlyProfitable": consistent,
        "financial": financial,
        "thresholds": {"minYears": MIN_YEARS, "growingAt": GROWING_AT},
        "baseRates": BASE_RATES,
        "reading": _reading(years, profitable, every_year, cash_backed, growth,
                            growing, margin, fcf_years,
                            None if fcf is None else len(fcf), financial,
                            (None if financial or net_debt is None
                             else bool(net_debt <= 0)),
                            None if financial else leverage),
    }


# The base rates travel with the flags, so a reader is never shown "profitable
# every year" without being shown how ordinary that is. Measured on the 523
# Indonesian listings in the local cache carrying three or more years.
BASE_RATES = {
    "sample": 523,
    "market": "ID",
    "everyYearProfitable": 0.67,
    "operatingCashFlowPositive": 0.80,
    "everyYearAndCashBacked": 0.58,
    "everyYearCashBackedAndGrowing": 0.14,
    "note": ("Two thirds of this exchange is profitable in every year its filings "
             "cover, so that alone is not a distinction. The narrowing is the "
             "conjunction: 58% add positive operating cash flow, and 14% add "
             "revenue growth at or above the market's own top quartile."),
}


def _latest(frame, key: str) -> Optional[float]:
    series = _series(frame, key)
    return None if series is None else _finite(series.values[0])


def _reading(years: int, profitable: int, every_year: bool, cash_backed: bool,
             growth: Optional[float], growing: bool, margin: Optional[float],
             fcf_years: Optional[int], fcf_of: Optional[int],
             financial: bool, net_cash: Optional[bool] = None,
             leverage: Optional[float] = None) -> str:
    window = (f"across the {years} years the filings cover"
              if years > 1 else "in the one year the filings cover")

    if every_year:
        head = (f"Profitable in every one of the {years} years the statements cover, "
                f"which two thirds of this market also manages")
    else:
        head = (f"Profitable in {profitable} of {years} years {window}")

    if margin is not None:
        head += f", on a {margin * 100:.1f}% net margin last year"
    head += "."

    if growth is None:
        pace = " Revenue growth could not be computed from these statements."
    elif growing:
        pace = (f" Revenue compounded at {growth * 100:.1f}% a year over that window, "
                f"which is inside this market's top quartile.")
    else:
        pace = (f" Revenue compounded at {growth * 100:.1f}% a year over that window, "
                f"against a market median of about 5%.")

    cash = (" Operating cash flow was positive last year."
            if cash_backed else
            " Operating cash flow was NOT positive last year, so the profit has not "
            "arrived as cash.")

    spend = ""
    if not financial and fcf_years is not None and fcf_of:
        short = fcf_of - fcf_years
        if short > fcf_of / 2:
            # THE MAJORITY OF YEARS. Sustained spending beyond what the business
            # generates is a build-out, and describing it that way is a reading.
            spend = (f" Free cash flow was negative in {short} of those {fcf_of} years "
                     f"— the business has consistently spent more on assets than it "
                     f"threw off, which is what a build-out looks like and is neither "
                     f"good nor bad without knowing what the spending bought.")
        elif short:
            # A MINORITY OF YEARS IS NOT A PATTERN, and calling one heavy year a
            # build-out would be a story told over a single observation.
            spend = (f" Free cash flow was negative in {short} of those {fcf_of} years, "
                     f"which is a single heavy year rather than a pattern."
                     if short == 1 else
                     f" Free cash flow was negative in {short} of those {fcf_of} years.")
        else:
            spend = (f" Free cash flow was positive in all {fcf_of} years, so the "
                     f"spending on assets stayed inside what the business generated.")
    elif financial:
        spend = (" Free cash flow is not reported here: capital spending on a lender's "
                 "accounts is premises and software rather than the engine of the "
                 "business, so the figure would describe nothing.")

    owed = ""
    if net_cash is True:
        owed = (" It holds more cash than borrowings, which 39% of this market's "
                "non-financial listings also do.")
    elif leverage is not None:
        owed = (f" Net borrowings are {leverage:.1f} times EBITDA, against a median of "
                f"3.0 for the listings here that borrow at all — so this is "
                f"{'more' if leverage > 3.0 else 'less'} levered than the typical "
                f"borrower on this exchange, which is a comparison and not a verdict.")
    elif net_cash is False:
        owed = (" It carries net borrowings, and there is no EBITDA to measure them "
                "against, so how heavy they are is not established here.")
    elif not financial:
        # net_cash is None on a non-financial: the balance sheet did not arrive.
        owed = (" No balance sheet came back, so whether it holds cash or borrowings "
                "is unknown here rather than settled either way.")

    return head + pace + cash + spend + owed + (
        f" {years} years is a short window — it does not span a cycle, and on this "
        f"exchange those years were a commodity upswing.")
