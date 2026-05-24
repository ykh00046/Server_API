"""HTTP-layer wrappers around shared validators.

Raise HTTPException so route handlers stay free of try/except boilerplate.
Each route module imports the helpers it needs; api/main.py re-exports them
for backward compatibility with tests that imported from api.main directly.
"""
from __future__ import annotations

import datetime as dt

from fastapi import HTTPException

from shared.validators import (
    validate_date_range as _validate_date_range_pure,
    validate_length as _validate_length_pure,
)


def _normalize_date(date_str: str | None, add_days: int = 0) -> str | None:
    """Normalize YYYY-MM-DD string; optionally add days for inclusive-end handling."""
    if not date_str:
        return None
    try:
        d = dt.date.fromisoformat(date_str)
        if add_days:
            d = d + dt.timedelta(days=add_days)
        return d.isoformat()
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid date format: '{date_str}'. Expected YYYY-MM-DD (e.g., 2026-01-15)."
        )


def _validate_date_range(date_from: str | None, date_to: str | None) -> None:
    """Validate date_from <= date_to. Wraps shared validator with HTTPException."""
    if not date_from or not date_to:
        return
    try:
        _validate_date_range_pure(date_from, date_to)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _validate_length(value: str | None, max_length: int, field_name: str) -> str | None:
    """Validate string length. Wraps shared validator with HTTPException."""
    try:
        return _validate_length_pure(value, max_length, field_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
