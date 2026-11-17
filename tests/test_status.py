"""The status route an uptime check reads. Offline: the provider is planted."""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient

import index


@pytest.fixture
def client(monkeypatch):
    index._RATE_HITS.clear()
    # The day the committed files were current, so the test does not age.
    monkeypatch.setattr(index, "_today", lambda: dt.date(2026, 11, 17))
    with TestClient(index.app) as c:
        yield c
    index._RATE_HITS.clear()


def test_a_healthy_deployment_reads_ok(client, monkeypatch):
    monkeypatch.setattr(index.market_data, "provider_answering", lambda market="US": True)
    monkeypatch.setattr(index.econcalendar, "coverage",
                        lambda: {"fomc": "2027-12-08", "idx": "2027-12-31", "bi-rate": "2026-10-21"})
    body = client.get("/api/status").json()
    assert body["status"] == "ok", body["problems"]
    assert body["provider"]["answering"] is True
    assert set(body["stamps"]) == set(index.PUBLISHED_STAMPS)
    assert all(s["measuredOn"] for s in body["stamps"].values())
    assert body["calendar"]["daysAhead"] >= index.CALENDAR_AHEAD_DAYS


def test_a_silent_provider_reads_degraded_and_says_so(client, monkeypatch):
    monkeypatch.setattr(index.market_data, "provider_answering", lambda market="US": False)
    body = client.get("/api/status").json()
    assert body["status"] == "degraded"
    assert any("provider" in p for p in body["problems"])


def test_a_hung_provider_costs_the_canary_budget_not_the_request(client, monkeypatch):
    import time
    monkeypatch.setattr(index, "CANARY_BUDGET_SECONDS", 0.2)
    monkeypatch.setattr(index.market_data, "provider_answering", lambda market="US": time.sleep(1.0))
    started = time.monotonic()
    body = client.get("/api/status").json()
    assert body["status"] == "degraded" and time.monotonic() - started < 0.9


def test_old_files_need_attention(client, monkeypatch):
    monkeypatch.setattr(index.market_data, "provider_answering", lambda market="US": True)
    monkeypatch.setattr(index, "_today", lambda: dt.date(2028, 1, 1))
    body = client.get("/api/status").json()
    assert body["status"] == "attention"
    assert any("listing file" in p for p in body["problems"])
    assert any("calendar" in p for p in body["problems"])


def test_the_private_tier_stays_out_of_the_status():
    assert not any(name in index.PUBLISHED_STAMPS for name in
                   ("verdict_backtest", "patterns_calibration", "tape_calibration",
                    "volume_profile_calibration"))


def test_the_committed_calendar_runs_short_of_bank_indonesia_dates_this_month(client, monkeypatch):
    # True of the file on 17 November 2026: Bank Indonesia had not published its
    # 2027 meetings, and its schedule ends on 16 December. The check names it;
    # the record of past decisions ("bi-rate") is not expected to reach ahead.
    monkeypatch.setattr(index.market_data, "provider_answering", lambda market="US": True)
    body = client.get("/api/status").json()
    assert body["status"] == "attention"
    assert any("bi-schedule" in p and "bi-rate" not in p for p in body["problems"])
