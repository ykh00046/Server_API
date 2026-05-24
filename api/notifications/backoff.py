"""Exponential backoff schedule for webhook retries (webhook-async-dispatch-v2).

Pure functions, fully unit-testable. The `random_fn` parameter is a test
seam — passing `lambda: 0.5` makes the jitter term zero and the result
deterministic.
"""
from __future__ import annotations

import random
from typing import Callable

# attempt → base delay in seconds. Index 0 is used for attempt=1
# (i.e. "we just finished attempt 1, how long until attempt 2?").
_BASE_DELAYS: tuple[int, ...] = (1, 5, 25, 125, 625)

MAX_BACKOFF_SEC: float = 3600.0  # 60-minute cap; also enforced on Retry-After
JITTER_RATIO: float = 0.2        # ±20%


def next_delay(
    attempt: int,
    *,
    max_attempts: int,
    retry_after_sec: float | None = None,
    random_fn: Callable[[], float] = random.random,
) -> float | None:
    """Compute the delay (seconds) before the NEXT attempt, or None if no
    further attempt should be made.

    Args:
        attempt: the attempt number that just finished (1-based).
        max_attempts: total attempts allowed; if `attempt >= max_attempts`
            this returns None ("give up").
        retry_after_sec: if positive, takes priority over the base schedule.
            Useful for honoring the upstream `Retry-After` header.
        random_fn: returns a float in [0, 1). Defaults to `random.random`.

    Returns:
        Delay in seconds (clamped to [0, MAX_BACKOFF_SEC]) or None.
    """
    if attempt >= max_attempts:
        return None
    if retry_after_sec is not None and retry_after_sec > 0:
        base = min(float(retry_after_sec), MAX_BACKOFF_SEC)
    else:
        idx = min(max(attempt - 1, 0), len(_BASE_DELAYS) - 1)
        base = float(_BASE_DELAYS[idx])
    # jitter in [-JITTER_RATIO, +JITTER_RATIO)
    jitter = (random_fn() - 0.5) * (2.0 * JITTER_RATIO)
    delayed = base * (1.0 + jitter)
    return max(0.0, min(delayed, MAX_BACKOFF_SEC))
