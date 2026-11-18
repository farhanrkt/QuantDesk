"""
reporting.py
============
What the app tells its owner when something breaks: one structured log line
always, and the same event sent to an error-reporting service when one is
configured.

OFF UNTIL A KEY IS SET. With no `SENTRY_DSN` in the environment nothing leaves
the process: the event is a JSON line on stderr, which Vercel's function logs
keep. With a DSN, the event also goes to that project's envelope endpoint. The
format is Sentry's, which several services accept; choosing the service is the
owner's decision (docs/AUDIT.md), so nothing here depends on one beyond the URL.

THE STANDARD LIBRARY ONLY. The function bundle already carries numpy, pandas,
scipy and scikit-learn, and a reporting SDK would add to every cold start to
send something that happens rarely. An envelope is one HTTP POST.

WHAT AN EVENT CARRIES, AND WHAT IT NEVER DOES. The exception's type, its message
cut to a length, the stack as file, function and line, the route TEMPLATE, the
method, the status, the release and the environment. Never a query string, a
request body, a header or the client's address: a holdings list travels in a
body, and an address is a fact about a person. A ticker in a route's path is
replaced by the route's template before anything is recorded.

IT NEVER RAISES, AND NEVER WAITS. Sending happens on a daemon thread with a
two-second timeout; a reporting service that is down costs a log line, never a
reader's request.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import sys
import threading
import traceback
import urllib.request
import uuid
from typing import Optional
from urllib.parse import urlsplit

LOG = logging.getLogger("quantdesk.errors")

MESSAGE_MAX = 500
FRAMES_MAX = 30
SEND_TIMEOUT_SECONDS = 2.0


def dsn() -> Optional[str]:
    """The configured DSN, read on every call so a test or a redeploy can set it."""
    value = (os.environ.get("SENTRY_DSN") or "").strip()
    return value or None


def enabled() -> bool:
    return dsn() is not None


def _endpoint(value: str) -> Optional[tuple[str, str]]:
    """(envelope URL, auth header) from a DSN, or None when it is not one.

    A DSN reads https://<public key>@<host>/<project id>.
    """
    try:
        parts = urlsplit(value)
    except ValueError:
        return None
    project = parts.path.strip("/").split("/")[-1] if parts.path else ""
    if parts.scheme not in ("https", "http") or not parts.username or not parts.hostname \
            or not project.isdigit():
        return None
    port = f":{parts.port}" if parts.port else ""
    url = f"{parts.scheme}://{parts.hostname}{port}/api/{project}/envelope/"
    auth = (f"Sentry sentry_version=7, sentry_client=quantdesk/1, "
            f"sentry_key={parts.username}")
    return url, auth


def _frames(exc: BaseException) -> list[dict]:
    frames = []
    for summary in traceback.extract_tb(exc.__traceback__)[-FRAMES_MAX:]:
        frames.append({
            # The path from the repository root at most: an absolute path names
            # the machine's directories, which the event does not need.
            "filename": summary.filename.split("/api/")[-1] if "/api/" in summary.filename
            else os.path.basename(summary.filename),
            "function": summary.name,
            "lineno": summary.lineno,
        })
    return frames


def event(*, kind: str, message: str, exc: Optional[BaseException] = None,
          route: Optional[str] = None, method: Optional[str] = None,
          status: Optional[int] = None, source: str = "server") -> dict:
    """One event, in the shape both the log line and the service receive."""
    record = {
        "event_id": uuid.uuid4().hex,
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "level": "error",
        "platform": "python" if source == "server" else "javascript",
        "logger": "quantdesk",
        "release": os.environ.get("VERCEL_GIT_COMMIT_SHA") or None,
        "environment": os.environ.get("VERCEL_ENV") or "local",
        "tags": {"kind": kind, "source": source, "route": route or "", "method": method or "",
                 "status": str(status) if status is not None else ""},
        "message": {"formatted": message[:MESSAGE_MAX]},
    }
    if exc is not None:
        record["exception"] = {"values": [{
            "type": type(exc).__name__,
            "value": str(exc)[:MESSAGE_MAX],
            "stacktrace": {"frames": _frames(exc)},
        }]}
    return record


def _envelope(record: dict) -> bytes:
    header = {"event_id": record["event_id"], "sent_at": record["timestamp"]}
    body = json.dumps(record, default=str)
    item = {"type": "event", "length": len(body.encode())}
    return "\n".join([json.dumps(header), json.dumps(item), body]).encode()


def _send(url: str, auth: str, payload: bytes) -> None:
    try:
        request = urllib.request.Request(url, data=payload, method="POST", headers={
            "Content-Type": "application/x-sentry-envelope", "X-Sentry-Auth": auth})
        with urllib.request.urlopen(request, timeout=SEND_TIMEOUT_SECONDS) as response:
            response.read(64)
    except Exception as failure:  # reporting must never raise
        LOG.warning("error report not delivered: %s", type(failure).__name__)


def capture(record: dict, *, wait: bool = False) -> Optional[threading.Thread]:
    """Log the event, and send it when a DSN is set. Returns the sender thread.

    `wait` joins the sender, for tests and for scripts that exit straight after.
    """
    line = {"event": "error", **{k: record.get(k) for k in ("event_id", "level", "environment",
                                                           "release", "tags", "message")}}
    exception = (record.get("exception") or {}).get("values") or []
    if exception:
        line["exception"] = {"type": exception[0]["type"], "value": exception[0]["value"],
                             "where": exception[0]["stacktrace"]["frames"][-1:]}
    print(json.dumps(line, default=str), file=sys.stderr, flush=True)

    value = dsn()
    target = _endpoint(value) if value else None
    if value and not target:
        LOG.warning("SENTRY_DSN is set but is not a DSN; nothing was sent")
        return None
    if not target:
        return None
    sender = threading.Thread(target=_send, args=(*target, _envelope(record)), daemon=True)
    sender.start()
    if wait:
        sender.join(SEND_TIMEOUT_SECONDS + 1)
    return sender


def capture_exception(exc: BaseException, *, kind: str, route: Optional[str] = None,
                      method: Optional[str] = None, status: Optional[int] = None,
                      wait: bool = False) -> Optional[threading.Thread]:
    return capture(event(kind=kind, message=f"{type(exc).__name__}: {exc}", exc=exc,
                         route=route, method=method, status=status), wait=wait)
