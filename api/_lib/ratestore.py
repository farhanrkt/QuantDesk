"""
ratestore.py
============
A request counter every instance shares, for the per-address rate limit.

WHY. The limiter in `index.py` counts in the process, and on Vercel each warm
instance keeps its own count, so the cap is per instance, not per address (its
docstring says so). This moves the count to a store all instances read, when
the owner configures one.

OFF UNTIL KEYS ARE SET. With `UPSTASH_REDIS_REST_URL` and
`UPSTASH_REDIS_REST_TOKEN` in the environment the count lives in that Redis
database, reached over its REST API with the standard library. Without them,
`count` returns None and the in-process limiter decides, exactly as before.
Choosing and paying for the store is the owner's decision (docs/AUDIT.md).

NEVER THE REASON A REQUEST FAILS. A store that is slow or down, or answers
something unexpected, returns None within `TIMEOUT_SECONDS`, and the
in-process limiter takes over for that request.

THE ADDRESS DOES NOT LEAVE IN CLEAR. The key is a hash of the address with
the token as salt, so the store holds counts against opaque keys that expire
with their window.

A FIXED WINDOW, NOT A SLIDING ONE. Two commands per request (INCR, then
EXPIRE NX) in one pipeline. A client can therefore get up to twice the limit
across a window boundary; for a cap whose job is to stop a flood, not to bill,
that is the usual trade for one round trip.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from typing import Optional

TIMEOUT_SECONDS = 0.35


def configured() -> Optional[tuple[str, str]]:
    url = (os.environ.get("UPSTASH_REDIS_REST_URL") or "").strip().rstrip("/")
    token = (os.environ.get("UPSTASH_REDIS_REST_TOKEN") or "").strip()
    if not url.startswith("https://") or not token:
        return None
    return url, token


def key_for(address: str, bucket: str, token: str) -> str:
    digest = hashlib.sha256(f"{token}|{address}".encode()).hexdigest()[:20]
    return f"qd:rl:{bucket}:{digest}"


def count(address: str, bucket: str, window: int) -> Optional[tuple[int, int]]:
    """(requests in this window including this one, seconds until it resets),
    or None when no store is configured or it did not answer in time."""
    target = configured()
    if not target:
        return None
    url, token = target
    key = key_for(address, bucket, token)
    body = json.dumps([["INCR", key], ["EXPIRE", key, str(window), "NX"], ["TTL", key]]).encode()
    try:
        request = urllib.request.Request(f"{url}/pipeline", data=body, method="POST", headers={
            "Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            answer = json.loads(response.read(4096))
        hits = int(answer[0]["result"])
        ttl = int(answer[2]["result"])
    except Exception:  # a store that misbehaves hands the decision back
        return None
    return hits, ttl if ttl > 0 else window
