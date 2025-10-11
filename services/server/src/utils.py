"""Small utility helpers used across the server service.

This module contains helpers for parsing small recipe fields so they are
reusable across modules (e.g. SlurmDeployer).
"""
from typing import Any


def parse_time_limit(val: Any) -> int:
    """Parse a recipe time_limit value into integer minutes.

    Supported inputs:
    - integer-like values (e.g. 15) -> 15
    - numeric strings (e.g. "15") -> 15
    - HH:MM:SS or MM:SS strings -> minutes (seconds > 0 rounds up by 1 minute)

    Returns a sane default of 15 on parse failure or None input.
    """
    if val is None:
        return 15

    # numeric
    try:
        return int(val)
    except Exception:
        pass

    # HH:MM:SS or MM:SS
    try:
        parts = str(val).split(":")
        parts = [int(p) for p in parts]
        if len(parts) == 3:
            h, m, s = parts
            return h * 60 + m + (1 if s > 0 else 0)
        elif len(parts) == 2:
            m, s = parts
            return m + (1 if s > 0 else 0)
    except Exception:
        pass

    return 15
