"""
jsonsafe.py
===========
pandas hands back NaN, numpy scalars and Timestamps. `json.dumps` turns NaN
into the literal token `NaN`, which is valid Python and invalid JSON —
`JSON.parse` on the client throws on it. Every payload goes through `clean()`
so NaN and +/-inf become `null` and numpy scalars become Python primitives.
"""

from __future__ import annotations

import datetime as dt
import math

import numpy as np
import pandas as pd


def clean(obj):
    if obj is None:
        return None
    if isinstance(obj, (bool, np.bool_)):
        return bool(obj)
    if isinstance(obj, (int, np.integer)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        value = float(obj)
        return value if math.isfinite(value) else None
    if isinstance(obj, (str, bytes)):
        return obj.decode() if isinstance(obj, bytes) else obj
    if isinstance(obj, (pd.Timestamp, dt.datetime, dt.date)):
        return obj.strftime("%Y-%m-%d")
    if isinstance(obj, np.ndarray):
        return [clean(v) for v in obj.tolist()]
    if isinstance(obj, dict):
        return {str(k): clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [clean(v) for v in obj]
    if obj is pd.NaT:
        return None
    return obj
