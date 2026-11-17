"""A statement line is the line it names, or nothing.

WHY THIS EXISTS

`valuation._get_row` is how every lens finds a line in a filing — revenue, EBIT,
receivables, current liabilities — and it fell back to a bare substring test
when no alias matched exactly. The November 2026 audit recorded every lookup
the production lenses made across 198 real companies (docs/AUDIT.md, COR-1).
Seven used the fallback, all Indonesian, and all seven read the wrong line:

  * six banks (BBRI, BMRI, BBNI, BBTN, BRIS, ARTO) have no operating-income
    line, and "operating income" and "EBIT" were read from "Other Non Operating
    Income Expenses" — so the company tab charted non-operating items as what
    the business earns from operations;
  * Jasa Marga's receivables were read from "Other Receivables", which feeds
    the Beneish receivables index.

The rule as written would also have read EBIT from "EBITDA" and current
liabilities from "Total Non Current Liabilities". None of the 122 US companies
needed the fallback at all. Against all 197 cached records, the narrower rule
below changes exactly those thirteen lookups and nothing else.

The planted labels are the provider's own spellings.
"""

from __future__ import annotations

import pandas as pd
import pytest

from _lib.valuation import _get_row

YEAR = pd.to_datetime(["2025-12-31"])


def statement(*labels: str) -> pd.DataFrame:
    return pd.DataFrame({YEAR[0]: [float(i + 1) for i in range(len(labels))]}, index=list(labels))


@pytest.mark.parametrize("key, labels", [
    # The six Indonesian banks, as filed.
    ("operating_income", ("Total Revenue", "Other Non Operating Income Expenses", "Net Income")),
    ("ebit", ("Total Revenue", "Other Non Operating Income Expenses", "Net Income")),
    # Jasa Marga, as filed.
    ("receivables", ("Total Assets", "Other Receivables")),
    # What the substring rule permitted and the sweep happened not to meet.
    ("ebit", ("EBITDA", "Normalized EBITDA")),
    ("current_liabilities", ("Total Non Current Liabilities Net Minority Interest",
                             "Other Current Liabilities")),
    ("current_assets", ("Total Non Current Assets", "Other Current Assets")),
])
def test_a_line_that_means_something_else_is_not_read(key, labels):
    assert _get_row(statement(*labels), key) is None


def test_an_exact_alias_is_still_found_whatever_its_case_and_spacing():
    frame = statement("  total revenue ", "Other Non Operating Income Expenses")
    assert _get_row(frame, "revenue").iloc[0] == 1.0


def test_the_exact_alias_wins_over_a_qualified_neighbour():
    frame = statement("Other Current Liabilities", "Current Liabilities")
    assert _get_row(frame, "current_liabilities").name == "Current Liabilities"


def test_a_line_with_harmless_words_around_the_alias_is_still_found():
    """The fallback stays for the case it is for: the alias, whole, with
    nothing before it that changes what it means."""
    frame = statement("Total Assets", "Accounts Receivable Net Of Allowance")
    assert _get_row(frame, "receivables").name == "Accounts Receivable Net Of Allowance"


def test_the_direct_method_cash_flow_line_is_still_read_exactly():
    """The one alias whose comment demanded an exact match, for the reason this
    test file exists: its sibling rows are components of the total."""
    frame = statement("Other Cash Paymentsfrom Operating Activities",
                      "Cash Flowsfromusedin Operating Activities Direct")
    assert _get_row(frame, "ocf").name == "Cash Flowsfromusedin Operating Activities Direct"
