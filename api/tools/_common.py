"""Internal helpers shared across api.tools modules.

Kept private (leading underscore) — external callers should not depend on
these. Delegates to `shared.validators` for the actual validation logic.
"""
from shared.validators import validate_date_range_exclusive


def _validate_date_range(date_from: str, date_to: str) -> tuple[str, str]:
    """Validate date range and return (date_from, next_day)."""
    return validate_date_range_exclusive(date_from, date_to)
