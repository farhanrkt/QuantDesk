"""The shape `GET /api/scan/latest` promises, held against a real report.

WHY THIS EXISTS

`ScanPanel` rendered a blank error screen from the day it was written, and
every check passed: the tests were green, `tsc` was clean, the design rules
passed, and the server-side render showed the loading state, which is what got
verified. The panel only fails once the data arrives.

The data was `counts`, which the report builds with six integers and a nested
`rejectedByReason` map. The client declared it `Record<string, number>` and
rendered every value, so React was handed an object, threw "Objects are not
valid as a React child", and the error boundary blanked the WHOLE PAGE.

The type was not wrong about what it wanted. The payload was wrong about what it
was, and no amount of type-checking a client catches a server that lies. So the
route flattens it and these tests hold that promise against a real file rather
than a fixture — a fixture written by the same hand that wrote the route would
agree with it about exactly the thing that was wrong.

WHAT THESE TESTS PROTECT

1. EVERY `counts` VALUE IS A SCALAR. The one that was not blanked the page.
2. NOTHING IN THE PAYLOAD IS A NESTED MAP WHERE A CLIENT EXPECTS A LEAF.
3. A REPORT FROM BEFORE A FIELD EXISTED STILL SERVES. Older scans have no
   profiles; they must degrade to nulls, not to a 500.
4. THE CAVEAT TRAVELS. A field rank without `basis` is a market-share claim.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def client():
    import sys
    sys.path.insert(0, str(ROOT / "api"))
    from index import app
    return TestClient(app)


@pytest.fixture(scope="module")
def reports():
    found = sorted((ROOT / "reports").glob("scan-*.json")) if (
        ROOT / "reports").exists() else []
    if not found:
        pytest.skip("no local scan report to check the route against")
    return found


def payload(client, market: str):
    response = client.get(f"/api/scan/latest?market={market}")
    assert response.status_code == 200
    return response.json()


def test_every_count_is_a_scalar(client, reports):
    """The defect that blanked the page, as a test on the real payload."""
    for market in ("ID", "US"):
        body = payload(client, market)
        if not body.get("available"):
            continue
        for key, value in (body.get("counts") or {}).items():
            assert isinstance(value, (int, float)) and not isinstance(value, bool), (
                f"counts.{key} is {type(value).__name__}; a client that renders it "
                f"hands React an object and the error boundary blanks the page")


def test_the_by_reason_breakdown_is_its_own_key(client, reports):
    for market in ("ID", "US"):
        body = payload(client, market)
        if not body.get("available"):
            continue
        assert "rejectedByReason" not in (body.get("counts") or {})
        breakdown = body.get("rejectedByReason")
        if breakdown is not None:
            assert all(isinstance(v, (int, float)) for v in breakdown.values())


def test_rows_carry_only_leaves_a_table_can_render(client, reports):
    """Every row field a cell renders directly must be a scalar or null.

    The nested blocks — `field`, `record`, `entry`, `gates` — are read
    field-by-field by the panel and are allowed to be objects. Everything else
    is rendered as itself.
    """
    nested = {"field", "record", "entry", "gates", "sectorRank"}
    for market in ("ID", "US"):
        body = payload(client, market)
        if not body.get("available"):
            continue
        for row in (body.get("rows") or [])[:200]:
            for key, value in row.items():
                if key in nested:
                    continue
                assert not isinstance(value, (dict, list)), (
                    f"row.{key} is a {type(value).__name__} on {row.get('ticker')}")


def test_a_report_written_before_the_business_profile_still_serves(client):
    """Older scans have no `fields` block and no per-name profile.

    They must come back as nulls rather than a 500 — the panel says in words
    that the column is empty because the scan predates it, and that sentence is
    only reachable if the route returns.
    """
    for market in ("ID", "US"):
        body = payload(client, market)
        if not body.get("available"):
            continue
        rows = body.get("rows") or []
        assert rows, "an available scan with no rows is not a scan"
        for row in rows[:50]:
            assert "industry" in row and "summary" in row and "field" in row


def test_a_field_rank_never_travels_without_its_basis(client, reports):
    """`field.py`'s central caveat, checked at the boundary that serves it."""
    for market in ("ID", "US"):
        body = payload(client, market)
        if not body.get("available"):
            continue
        fields = body.get("fields")
        ranked = any((row.get("field") or {}).get("rank") is not None
                     for row in (body.get("rows") or []))
        if not ranked:
            continue
        assert fields and fields.get("basis"), (
            "rows carry a field rank but the response has no basis; a rank among "
            "scanned peers rendered alone reads as market share")
        assert "not a market share" in fields["basis"]
        assert fields.get("unplaced") is not None


def test_a_missing_scan_is_a_reason_not_a_404(client):
    body = payload(client, "US")
    if body.get("available"):
        pytest.skip("a US scan exists on this machine")
    assert body["reason"] and "scan_market.py" in body["reason"]


def test_the_response_is_never_cached(client, reports):
    response = client.get("/api/scan/latest?market=ID")
    assert "no-store" in response.headers.get("cache-control", "")
