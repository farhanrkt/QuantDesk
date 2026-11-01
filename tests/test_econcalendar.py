"""The calendar of dates that move markets: the committed file and its rules.

Nothing here depends on today's date. A calendar test that fails the week a
schedule runs out would turn CI red for a reason no commit caused, so the file's
coverage is shown on the page and checked by `scripts/refresh_calendar.py`
instead.
"""

from __future__ import annotations

import datetime as dt
import json

import pytest

from _lib import econcalendar as C


def test_the_committed_file_validates_and_every_event_cites_a_source():
    doc = C.load()
    assert doc["verifiedOn"]
    for event in doc["events"]:
        assert event["source"] in doc["sources"]
        assert doc["sources"][event["source"]]["url"].startswith("https://")


def test_what_is_not_published_is_stated():
    kinds = {item["kind"] for item in C.load()["pending"]}
    assert {"bi-rate", "bps-cpi"} <= kinds


def test_an_unknown_kind_or_an_unordered_file_is_refused(tmp_path):
    good = C.load()
    bad = {**good, "events": [{**good["events"][0], "kind": "astrology"}]}
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(bad))
    with pytest.raises(C.CalendarError):
        C._validate(json.loads(path.read_text()))
    shuffled = {**good, "events": list(reversed(good["events"]))}
    with pytest.raises(C.CalendarError):
        C._validate(shuffled)


def test_a_us_release_moves_an_hour_in_utc_when_the_clocks_change():
    before = {"date": "2026-03-06", "time": "08:30", "tz": "America/New_York"}
    after = {"date": "2026-03-10", "time": "08:30", "tz": "America/New_York"}
    assert C.instant(before) == "2026-03-06T13:30:00Z"
    assert C.instant(after) == "2026-03-10T12:30:00Z"
    assert C.instant({"date": "2026-11-18", "time": None, "tz": "Asia/Jakarta"}) is None


def test_upcoming_is_a_window_and_carries_what_each_kind_is():
    events = C.upcoming(dt.date(2026, 11, 1), 45)
    assert events and all("2026-11-01" <= e["date"] <= "2026-12-16" for e in events)
    assert all(e["label"] for e in events)
    assert any(e["kind"] == "fomc" and e["date"] == "2026-12-09" for e in events)


def test_the_payload_carries_the_whole_month_and_says_where_it_ends():
    """A month view needs the month. On 20 November the jobs report (6 Nov) and
    CPI (10 Nov) have happened and are still November's; the window says where
    the data stops so a later day is never drawn as an empty one."""
    payload = C.payload(dt.date(2026, 11, 20))
    assert payload["window"] == {"from": "2026-10-31", "through": "2027-02-18"}
    dates = {(e["kind"], e["date"]) for e in payload["events"]}
    assert ("jobs", "2026-11-06") in dates and ("cpi", "2026-11-10") in dates
    assert all("2026-10-31" <= e["date"] <= "2027-02-18" for e in payload["events"])
    # The exchange clock still reads only what is ahead of it.
    assert all(c["date"] >= "2026-11-20" for c in payload["exchanges"]["US"]["closures"])


def test_the_exchanges_carry_their_hours_and_closures():
    payload = C.payload(dt.date(2026, 11, 1))
    assert payload["exchanges"]["ID"]["sessions"]["fri"][0] == ["09:00", "11:30"]
    closures = {(c["date"], c["kind"]) for c in payload["exchanges"]["US"]["closures"]}
    assert ("2026-11-26", "holiday") in closures and ("2026-11-27", "early-close") in closures


def test_a_past_bank_indonesia_decision_is_the_date_it_decided_not_the_published_one():
    """BI published 15-16 July 2026 and decided on 22 July."""
    dates = {d.isoformat() for d in C.past_dates("bi-rate", dt.date(2026, 10, 31))}
    assert "2026-07-22" in dates and "2026-07-16" not in dates
    assert "2026-06-09" in dates, "the decision between meetings is kept"
