"""The private scanner is served where its owner runs the app, and nowhere public.

WHY THIS EXISTS

PRODUCT.md constraint 1 keeps a composite buy/hold/sell off the published
single-company view, and says the scanner's per-name score and local report
live "locally". Until November 2026 nothing enforced that: `/api/verdict`
computed a score, an action and a position size for any ticker on any
deployment, and the stock page offered it as a tab. The only fence was that
`reports/` is gitignored, which hides a file and not a route that computes live.

These tests hold the fence: the flag's default follows where the app runs, both
routes refuse BEFORE running anything when it is off, the client is told the
same answer the routes act on, and a score is never stored by a shared cache.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import index
from helpers import path, steady


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ("QUANTDESK_PRIVATE_TIER", "VERCEL", "VERCEL_ENV"):
        monkeypatch.delenv(name, raising=False)
    index._RATE_HITS.clear()
    yield
    index._RATE_HITS.clear()


@pytest.fixture
def client():
    return TestClient(index.app)


# --------------------------------------------------------------------------- #
# The flag
# --------------------------------------------------------------------------- #
def test_on_where_the_owner_runs_the_app():
    assert index.private_tier_enabled() is True


@pytest.mark.parametrize("name,value", [("VERCEL", "1"), ("VERCEL_ENV", "production"),
                                        ("VERCEL_ENV", "preview")])
def test_off_on_any_deployment_previews_included(monkeypatch, name, value):
    """A preview URL is as public as production, so it gets the same answer."""
    monkeypatch.setenv(name, value)
    assert index.private_tier_enabled() is False


def test_the_override_wins_in_both_directions(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("QUANTDESK_PRIVATE_TIER", "1")
    assert index.private_tier_enabled() is True
    monkeypatch.delenv("VERCEL")
    monkeypatch.setenv("QUANTDESK_PRIVATE_TIER", "0")
    assert index.private_tier_enabled() is False


def test_a_request_through_vercels_edge_is_a_deployment_without_the_variables(client,
                                                                               monkeypatch):
    """The variables exist only when the project exposes them; the edge's own
    `x-vercel-id` header reaches every function either way."""
    monkeypatch.setattr(index.ranking, "scan", _explode)
    edge = {"x-vercel-id": "sin1::iad1::abcde-1700000000000-0123456789ab"}
    assert client.get("/api/capabilities", headers=edge).json() == {"privateTier": False}
    assert client.get("/api/verdict", params={"ticker": "AAPL"}, headers=edge).status_code == 404
    assert client.get("/api/scan/latest", headers=edge).json()["available"] is False


def test_an_unreadable_override_falls_back_to_where_the_app_runs(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("QUANTDESK_PRIVATE_TIER", "maybe")
    assert index.private_tier_enabled() is False


# --------------------------------------------------------------------------- #
# Off: both routes refuse before anything runs
# --------------------------------------------------------------------------- #
def _explode(*_args, **_kwargs):
    raise AssertionError("the private tier ran something while it was turned off")


def test_the_score_route_refuses_before_running_anything(client, monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    for target, name in ((index.ranking, "scan"), (index.universes, "containing"),
                         (index, "whale_payload"), (index, "technical_payload"),
                         (index, "valuation_payload"), (index, "quality_payload"),
                         (index.market_data, "ohlcv")):
        monkeypatch.setattr(target, name, _explode)
    response = client.get("/api/verdict", params={"ticker": "AAPL"})
    assert response.status_code == 404
    assert "not served by this deployment" in response.json()["detail"]


def test_the_local_report_is_not_read_on_a_deployment(client, monkeypatch):
    monkeypatch.setenv("VERCEL_ENV", "production")
    monkeypatch.setattr(index, "_latest_scan", _explode)
    response = client.get("/api/scan/latest", params={"market": "ID"})
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert "not served by this deployment" in body["reason"]
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("env,expected", [({}, True), ({"VERCEL": "1"}, False),
                                          ({"VERCEL": "1", "QUANTDESK_PRIVATE_TIER": "1"}, True)])
def test_the_client_is_told_what_the_routes_act_on(client, monkeypatch, env, expected):
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    body = client.get("/api/capabilities").json()
    assert body == {"privateTier": expected}
    assert index.private_tier_enabled() is expected


# --------------------------------------------------------------------------- #
# On: the score runs, and no shared cache keeps a copy
# --------------------------------------------------------------------------- #
def test_a_score_is_computed_off_the_event_loop_and_never_cached(client, monkeypatch):
    """Every lens fails and the price fetch returns a planted frame, so the route
    walks its whole post-lens path — tape, formations, profile, structure, the
    register, the regime and the chart — in the worker thread it now runs in."""
    frame = path(steady(504, seed=11))

    def no_lens(*_args, **_kwargs):
        raise HTTPException(status_code=404, detail="planted: no lens")

    monkeypatch.setattr(index.universes, "containing", lambda symbol: [])
    for name in ("whale_payload", "technical_payload", "valuation_payload", "quality_payload"):
        monkeypatch.setattr(index, name, no_lens)
    monkeypatch.setattr(index.market_data, "ohlcv", lambda *a, **k: frame.copy())
    monkeypatch.setattr(index.market_data, "share_register",
                        lambda symbol: {"ok": False, "symbol": symbol})

    response = client.get("/api/verdict", params={"ticker": "FAKE"})
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["action"] == "NO_ACTION"
    assert body["provenance"]                    # the null result travels with it
    assert body["chart"] is not None             # the frame reached the chart layers
    assert body["universe"] is None              # no peer group, so no percentile
