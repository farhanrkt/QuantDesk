#!/usr/bin/env python3
"""
hang.py
=======
What one company read costs when the provider accepts a connection and then
says nothing.

WHY THIS AND NOT A BLOCKED NETWORK
-----------------------------------
`tests/test_outages.py` plants a provider that FAILS, which is the easy
outage: every call returns at once and the page says so in a sentence. The
outage that hurts is the one where nothing fails. A socket that completes its
handshake and never answers costs each provider call its full timeout, the
calls inside a lens run one after another, and nothing above them is counting.

This starts such a socket, points the process's proxy settings at it BEFORE
the app is imported (the HTTP library reads them once), and times
`GET /api/confluence`. On 14 November 2026 the request had not returned after
380 seconds; the platform allows the function 60 (docs/AUDIT.md, REL-1).

    python scripts/audit/hang.py            # give up after 120 seconds
    python scripts/audit/hang.py 400

It touches no real network: every request goes to the silent socket.
"""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
from pathlib import Path

PORT = 45999


def silent_server() -> None:
    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", PORT))
    server.listen(64)
    held = []
    while True:
        connection, _ = server.accept()
        held.append(connection)          # keep it open, read nothing, answer nothing


def main() -> int:
    give_up = float(sys.argv[1]) if len(sys.argv) > 1 else 120.0
    threading.Thread(target=silent_server, daemon=True).start()
    for name in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        os.environ[name] = f"http://127.0.0.1:{PORT}"
    os.environ.pop("ALL_PROXY", None)
    os.environ.pop("NO_PROXY", None)

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "api"))
    import index
    from fastapi.testclient import TestClient

    client = TestClient(index.app)
    outcome: dict = {}

    def ask() -> None:
        started = time.monotonic()
        response = client.get("/api/confluence", params={"ticker": "AAPL"})
        outcome["seconds"] = time.monotonic() - started
        outcome["body"] = response.json()
        outcome["cache"] = response.headers.get("cache-control")

    worker = threading.Thread(target=ask, daemon=True)
    worker.start()
    worker.join(give_up)
    if worker.is_alive():
        print(f"No answer after {give_up:.0f} seconds. The platform kills the function at 60.",
              flush=True)
        # The request is still waiting on the silent socket and its threads are
        # not ours to stop, so leave without joining them.
        os._exit(1)
    body = outcome["body"]
    print(f"Answered after {outcome['seconds']:.0f} seconds "
          f"(providerAnswering={body.get('providerAnswering')}, {outcome['cache']}).")
    for leg in ("anomaly", "technical", "valuation", "quality", "news", "company"):
        value = body.get(leg) or {}
        print(f"  {leg:10} ok={value.get('ok')}  {str(value.get('error'))[:100]}")
    return 0 if outcome["seconds"] < 60 else 1


if __name__ == "__main__":
    raise SystemExit(main())
