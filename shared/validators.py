# shared/validators.py
"""
Production Data Hub - Shared Validation Utilities

Pure validation functions that raise ValueError.
API layer wraps these to return HTTPException as needed.
"""

from __future__ import annotations

import datetime as dt


def validate_date_format(date_str: str, field_name: str = "date") -> dt.date:
    """
    Parse and validate a date string in YYYY-MM-DD format.

    Args:
        date_str: Date string to validate.
        field_name: Field name for error messages.

    Returns:
        Parsed date object.

    Raises:
        ValueError: If the format is invalid.
    """
    try:
        return dt.date.fromisoformat(date_str)
    except ValueError:
        raise ValueError(
            f"Invalid {field_name} format: '{date_str}'. Expected YYYY-MM-DD."
        )


def validate_date_range(date_from: str, date_to: str) -> None:
    """
    Validate that date_from <= date_to.

    Args:
        date_from: Start date (YYYY-MM-DD).
        date_to: End date (YYYY-MM-DD).

    Raises:
        ValueError: If date_from > date_to or format is invalid.
    """
    from_date = validate_date_format(date_from, "date_from")
    to_date = validate_date_format(date_to, "date_to")

    if from_date > to_date:
        raise ValueError(
            f"Invalid date range: date_from ({date_from}) cannot be after "
            f"date_to ({date_to})."
        )


def validate_date_range_exclusive(
    date_from: str, date_to: str
) -> tuple[str, str]:
    """
    Validate date range and compute exclusive end date (date_to + 1 day).

    This is the standard pattern for SQL queries using:
        WHERE production_date >= ? AND production_date < ?

    Args:
        date_from: Start date (YYYY-MM-DD, inclusive).
        date_to: End date (YYYY-MM-DD, inclusive).

    Returns:
        Tuple of (date_from, next_day) where next_day = date_to + 1 day.

    Raises:
        ValueError: If dates are invalid or date_from > date_to.
    """
    from_date = validate_date_format(date_from, "date_from")
    to_date = validate_date_format(date_to, "date_to")

    if from_date > to_date:
        raise ValueError(
            f"Invalid date range: date_from ({date_from}) cannot be after "
            f"date_to ({date_to})."
        )

    next_day = (to_date + dt.timedelta(days=1)).isoformat()
    return date_from, next_day


def validate_length(
    value: str | None, max_length: int, field_name: str
) -> str | None:
    """
    Validate string length constraint.

    Args:
        value: String value to validate (None passes through).
        max_length: Maximum allowed length.
        field_name: Field name for error message.

    Returns:
        Original value if valid.

    Raises:
        ValueError: If value exceeds max_length.
    """
    if value is None:
        return None

    if len(value) > max_length:
        raise ValueError(
            f"{field_name} exceeds maximum length of {max_length} characters "
            f"(got {len(value)})."
        )

    return value


def escape_like_wildcards(value: str) -> str:
    """
    Escape SQL LIKE wildcard characters (% and _) in a string.

    This prevents LIKE injection where user input contains wildcards
    that could match unintended records.

    Args:
        value: String to escape.

    Returns:
        Escaped string safe for use in LIKE patterns.

    Example:
        >>> escape_like_wildcards("test_value")
        'test\\_value'
        >>> escape_like_wildcards("100%")
        '100\\%'
    """
    if not value:
        return value
    # Escape backslash first, then percent and underscore
    return value.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")


def validate_db_path(path: str) -> bool:
    """
    Validate database file path for safe use in ATTACH statements.

    Rejects NUL, control chars, quotes, and verifies resolvable absolute path
    via pathlib. Callers needing whitelist enforcement should use
    ``resolve_archive_db`` instead.

    Raises:
        ValueError: If path contains dangerous characters or cannot be resolved.
    """
    from pathlib import Path as _P

    if not path or any(ord(c) < 32 for c in path):
        raise ValueError("Invalid database path: empty or contains control chars.")
    if any(c in path for c in ("'", '"', "\x00", "\n", "\r")):
        raise ValueError("Invalid database path: contains forbidden characters.")
    try:
        _P(path).resolve()
    except (OSError, RuntimeError) as e:
        raise ValueError(f"Invalid database path: cannot resolve ({e})")
    return True


def resolve_archive_db(requested_path, whitelist) -> "Path":
    """
    Resolve an archive DB path against a whitelist.

    Args:
        requested_path: str | Path requested by caller.
        whitelist: Iterable of allowed Path objects (already resolved).

    Returns:
        Resolved Path if it is in the whitelist AND exists.

    Raises:
        ValueError: If path is not in whitelist or does not exist.
    """
    from pathlib import Path as _P

    if requested_path is None:
        raise ValueError("archive db not requested")
    resolved = _P(requested_path).resolve()
    allowed = {_P(p).resolve() for p in whitelist}
    if resolved not in allowed:
        raise ValueError(f"archive db not in whitelist: {resolved}")
    if not resolved.exists():
        raise FileNotFoundError(f"archive db missing: {resolved}")
    return resolved
