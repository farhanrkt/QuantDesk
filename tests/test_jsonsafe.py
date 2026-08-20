"""The wire format's last line of defence.

`json.dumps` renders NaN as the bare token `NaN`, which is valid Python and
invalid JSON — `JSON.parse` throws on it, so a single missing figure anywhere in
a payload blanks an entire panel with a parse error rather than an empty cell.
Every response goes through `clean()`, so these are the cases it must survive.
"""

from __future__ import annotations

import datetime as dt
import json
import math

import numpy as np
import pandas as pd
import pytest

from _lib.jsonsafe import clean


@pytest.mark.parametrize("value", [np.nan, math.inf, -math.inf,
                                   np.float64("nan"), np.float32("inf")])
def test_non_finite_floats_become_null(value):
    assert clean(value) is None


def test_nat_and_none_become_null():
    assert clean(pd.NaT) is None
    assert clean(None) is None


@pytest.mark.parametrize(("value", "expected_type"), [
    (np.int64(7), int), (np.int32(7), int), (np.float64(1.5), float),
    (np.bool_(True), bool), (True, bool), (b"bytes", str),
])
def test_numpy_scalars_become_python_primitives(value, expected_type):
    result = clean(value)
    assert type(result) is expected_type


def test_bool_is_checked_before_int():
    """np.bool_ is an integer subtype; order matters or True serialises as 1."""
    assert clean(np.bool_(True)) is True
    assert clean(np.bool_(False)) is False


def test_timestamps_become_iso_dates():
    assert clean(pd.Timestamp("2026-08-20 13:45")) == "2026-08-20"
    assert clean(dt.date(2026, 8, 20)) == "2026-08-20"
    assert clean(dt.datetime(2026, 8, 20, 13, 45)) == "2026-08-20"


def test_nested_structures_are_cleaned_throughout():
    payload = {
        "stats": {"rate": np.nan, "count": np.int64(3)},
        "series": [{"close": np.float64(1.5), "mfi": np.nan}],
        "matrix": np.array([1.0, np.inf, 3.0]),
        "tags": {"a", "b"},
        np.int64(2026): "int keys are stringified",
    }
    result = clean(payload)

    assert result["stats"]["rate"] is None
    assert result["stats"]["count"] == 3
    assert result["series"][0]["mfi"] is None
    assert result["matrix"] == [1.0, None, 3.0]
    assert sorted(result["tags"]) == ["a", "b"]
    assert "2026" in result


def test_cleaned_payload_is_strict_json():
    """The property that actually matters: the client can parse it."""
    payload = {"a": np.nan, "b": [np.inf, np.int64(1)], "c": pd.NaT,
               "d": pd.Timestamp("2026-01-01")}
    encoded = json.dumps(clean(payload), allow_nan=False)   # raises on NaN/Infinity
    assert json.loads(encoded) == {"a": None, "b": [None, 1], "c": None, "d": "2026-01-01"}
