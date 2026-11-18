"""Error reporting: silent until a key is set, and never carrying a reader's data.

Offline. The "service" is a listener on 127.0.0.1 started by the test, so what
the app would send is read back byte for byte without touching a network.
"""

from __future__ import annotations

import http.server
import json
import threading

import pytest
from fastapi.testclient import TestClient

import index
from _lib import reporting


@pytest.fixture
def listener():
    received: list[dict] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            received.append({"path": self.path, "auth": self.headers.get("X-Sentry-Auth", ""),
                             "body": body.decode()})
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://publickey@127.0.0.1:{server.server_port}/42", received
    server.shutdown()


@pytest.fixture
def client():
    index._RATE_HITS.clear()
    with TestClient(index.app, raise_server_exceptions=False) as c:
        yield c
    index._RATE_HITS.clear()


def _boom():
    raise ValueError("planted failure")


def test_with_no_key_nothing_is_sent(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    monkeypatch.setattr(reporting.urllib.request, "urlopen",
                        lambda *a, **k: pytest.fail("sent without a key"))
    try:
        _boom()
    except ValueError as exc:
        assert reporting.capture_exception(exc, kind="test", wait=True) is None
    assert reporting.enabled() is False


def test_with_a_key_the_event_reaches_the_service(monkeypatch, listener):
    dsn, received = listener
    monkeypatch.setenv("SENTRY_DSN", dsn)
    try:
        _boom()
    except ValueError as exc:
        reporting.capture_exception(exc, kind="test", route="/api/health", wait=True)
    assert len(received) == 1
    assert received[0]["path"] == "/api/42/envelope/"
    assert "sentry_key=publickey" in received[0]["auth"]
    _header, item, body = received[0]["body"].split("\n")
    event = json.loads(body)
    assert json.loads(item)["type"] == "event"
    assert event["exception"]["values"][0]["type"] == "ValueError"
    assert event["exception"]["values"][0]["stacktrace"]["frames"][-1]["function"] == "_boom"
    assert event["tags"]["route"] == "/api/health"


def test_a_malformed_key_sends_nothing(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "not a dsn")
    monkeypatch.setattr(reporting.urllib.request, "urlopen",
                        lambda *a, **k: pytest.fail("sent to a malformed DSN"))
    assert reporting.capture(reporting.event(kind="test", message="x"), wait=True) is None


def test_a_service_that_is_down_costs_nothing(monkeypatch):
    # Nothing listens on port 9; the send fails on its own thread and is logged.
    monkeypatch.setenv("SENTRY_DSN", "http://k@127.0.0.1:9/1")
    sender = reporting.capture(reporting.event(kind="test", message="x"), wait=True)
    assert sender is not None and not sender.is_alive()


def test_an_unhandled_exception_is_answered_in_words_and_reported(client, monkeypatch):
    seen: list[dict] = []
    monkeypatch.setattr(reporting, "capture", lambda record, **k: seen.append(record))
    monkeypatch.setattr(index, "ok", lambda *a, **k: _boom())
    response = client.get("/api/health", params={"ticker": "SECRETHOLDING", "lang": "id"})
    assert response.status_code == 500
    assert response.json()["detail"].startswith("Ada yang salah di dalam aplikasi")
    assert len(seen) == 1
    event = seen[0]
    assert event["tags"]["route"] == "/api/health" and event["tags"]["status"] == "500"
    # The query string, the body, the headers and the address never reach it.
    flat = json.dumps(event)
    assert "SECRETHOLDING" not in flat
    assert "testclient" not in flat and "request" not in event and "user" not in event


def test_a_broken_lens_is_reported_as_one(monkeypatch):
    seen: list[dict] = []
    monkeypatch.setattr(reporting, "capture", lambda record, **k: seen.append(record))
    try:
        _boom()
    except ValueError as exc:
        index.lens_broke("valuation", exc)
    assert seen[0]["tags"]["kind"] == "lens" and seen[0]["tags"]["route"] == "lens:valuation"


def test_frames_name_files_without_the_machine_path():
    try:
        _boom()
    except ValueError as exc:
        frames = reporting._frames(exc)
    assert all(not f["filename"].startswith("/") for f in frames)


# --------------------------------------------------------------------------- #
# The browser's reports
# --------------------------------------------------------------------------- #
REPORT = {"kind": "render", "message": "TypeError: x is undefined at https://q.example/stock/AAPL?tab=flow",
          "stack": "at draw (https://q.example/_next/static/chunks/1.js?v=SECRET:1:20)",
          "route": "/stock/[symbol]"}


def test_the_browser_is_told_whether_to_report(client, monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    assert client.get("/api/capabilities").json()["errorReporting"] is False
    monkeypatch.setenv("SENTRY_DSN", "https://k@example.invalid/1")
    assert client.get("/api/capabilities").json()["errorReporting"] is True


def test_a_browser_report_is_ignored_while_reporting_is_off(client, monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    monkeypatch.setattr(reporting, "capture", lambda *a, **k: pytest.fail("captured while off"))
    assert client.post("/api/client-error", json=REPORT).status_code == 204


def test_a_browser_report_loses_its_query_strings_and_keeps_only_a_template(client, monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://k@example.invalid/1")
    seen: list[dict] = []
    monkeypatch.setattr(reporting, "capture", lambda record, **k: seen.append(record))
    assert client.post("/api/client-error", json=REPORT).status_code == 204
    flat = json.dumps(seen[0])
    assert "SECRET" not in flat and "tab=flow" not in flat
    assert seen[0]["tags"]["route"] == "/stock/[symbol]" and seen[0]["tags"]["source"] == "browser"
    seen.clear()
    client.post("/api/client-error", json={**REPORT, "route": "/stock/AAPL"})
    assert seen[0]["tags"]["route"] == "/other", "a path that is not a template is not kept"


def test_a_browser_report_is_bounded(client, monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://k@example.invalid/1")
    monkeypatch.setattr(reporting, "capture", lambda *a, **k: None)
    assert client.post("/api/client-error", json={**REPORT, "message": "x" * 501}).status_code == 422
    assert client.post("/api/client-error", json={**REPORT, "kind": "anything"}).status_code == 422
    codes = [client.post("/api/client-error", json=REPORT).status_code for _ in range(12)]
    assert codes.count(429) >= 2, "a page that breaks in a loop cannot flood the log"
