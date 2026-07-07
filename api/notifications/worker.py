"""Background worker for asynchronous webhook dispatch (webhook-async-dispatch-v2).

Single daemon thread, single-process assumption. The worker loops over due
deliveries, calls the dispatcher, then either marks success, schedules a
retry with exponential backoff, or marks the row dead when attempts run out.

The class exposes `tick_once()` so tests can drive the loop deterministically
without sleeping for `tick_sec`.
"""
from __future__ import annotations

import datetime as dt
import threading
import time
from collections.abc import Callable

import httpx

from shared import get_logger
from shared.config import (
    WEBHOOK_MAX_ATTEMPTS,
    WEBHOOK_TIMEOUT_SEC,
    WEBHOOK_WORKER_BATCH,
    WEBHOOK_WORKER_TICK_SEC,
)

from . import dispatcher, store
from .backoff import next_delay
from .dispatcher import DispatchResult

logger = get_logger(__name__)

# A live worker finalizes a claimed row within one dispatch timeout, so any
# in_flight row older than this lease is an orphan from a killed process.
IN_FLIGHT_LEASE_SEC = max(60.0, WEBHOOK_TIMEOUT_SEC * 4)


class WebhookDispatchWorker:
    def __init__(
        self,
        *,
        tick_sec: float | None = None,
        batch_size: int | None = None,
        max_attempts: int | None = None,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] = time.time,
        random_fn: Callable[[], float] | None = None,
    ) -> None:
        self.tick_sec = float(
            tick_sec if tick_sec is not None else WEBHOOK_WORKER_TICK_SEC
        )
        self.batch_size = int(
            batch_size if batch_size is not None else WEBHOOK_WORKER_BATCH
        )
        self.max_attempts = int(
            max_attempts if max_attempts is not None else WEBHOOK_MAX_ATTEMPTS
        )
        self._transport = transport
        self._clock = clock
        self._random_fn = random_fn
        self._shutdown = threading.Event()
        self._thread: threading.Thread | None = None

    # ----- lifecycle -----
    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        # Single-process assumption: at start no dispatch can be in flight,
        # so every in_flight row is an orphan from the previous run.
        store.recover_stale_in_flight(older_than_sec=0.0)
        self._shutdown.clear()
        t = threading.Thread(
            target=self._run, name="WebhookDispatchWorker", daemon=True
        )
        self._thread = t
        t.start()
        logger.info(
            "[webhook.worker] started tick=%.2fs batch=%d max_attempts=%d",
            self.tick_sec, self.batch_size, self.max_attempts,
        )

    def stop(self, *, timeout: float | None = None) -> None:
        # Default join window must outlast one in-flight HTTP attempt —
        # a shorter join abandons the batch mid-dispatch (orphaned in_flight).
        if timeout is None:
            timeout = WEBHOOK_TIMEOUT_SEC + 2.0
        self._shutdown.set()
        t = self._thread
        if t is not None:
            t.join(timeout=timeout)
            if t.is_alive():
                # feedback_timeout_daemon_gc: leave to GC, never raise
                logger.warning(
                    "[webhook.worker] stop timeout — leaving daemon thread to GC"
                )
        self._thread = None

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ----- single iteration (public for tests) -----
    def tick_once(self) -> int:
        """Process one batch of due deliveries. Returns # finalized."""
        now = store._now_iso()
        store.recover_stale_in_flight(
            older_than_sec=IN_FLIGHT_LEASE_SEC, now_iso=now
        )
        claimed = store.claim_due_deliveries(now_iso=now, limit=self.batch_size)
        done = 0
        for i, cd in enumerate(claimed):
            if self._shutdown.is_set():
                # Shutdown mid-batch: hand unprocessed claims back to the
                # queue so the next start redelivers them immediately.
                store.release_claims([c.id for c in claimed[i:]])
                break
            try:
                outcome = dispatcher.send(
                    url=cd.url,
                    secret=cd.secret,
                    event_type=cd.event_type,
                    delivery_id=cd.id,
                    payload=cd.payload,
                    transport=self._transport,
                )
            except Exception as e:  # noqa: BLE001 — belt-and-suspenders: dispatcher가 raise하더라도 worker는 죽지 않는다
                logger.exception("[webhook.worker] dispatcher raised: %s", e)
                outcome = DispatchResult(
                    status="failure",
                    response_status=None,
                    response_body=None,
                    error=f"{type(e).__name__}: {e}"[:1024],
                    duration_ms=0,
                )
            self._finalize(cd, outcome)
            done += 1
        return done

    def _finalize(self, cd, outcome: DispatchResult) -> None:
        # Success path
        if outcome.status == "success":
            store.record_attempt(
                cd.id,
                outcome=outcome,
                next_status="success",
                next_attempt_at=None,
                attempt=cd.attempt,
            )
            return
        # 4xx → permanent client error; do not retry.
        rs = outcome.response_status
        if rs is not None and 400 <= rs < 500:
            store.record_attempt(
                cd.id,
                outcome=outcome,
                next_status="failure",
                next_attempt_at=None,
                attempt=cd.attempt,
            )
            return
        # 5xx or network error → maybe retry
        random_fn = self._random_fn
        delay = next_delay(
            cd.attempt,
            max_attempts=self.max_attempts,
            retry_after_sec=outcome.retry_after_sec,
            **({"random_fn": random_fn} if random_fn is not None else {}),
        )
        if delay is None:
            store.record_attempt(
                cd.id,
                outcome=outcome,
                next_status="dead",
                next_attempt_at=None,
                attempt=cd.attempt,
            )
            return
        naa = _iso_offset(store._now_iso(), delay)
        store.record_attempt(
            cd.id,
            outcome=outcome,
            next_status="retrying",
            next_attempt_at=naa,
            attempt=cd.attempt + 1,
        )

    # ----- background loop -----
    def _run(self) -> None:
        while not self._shutdown.is_set():
            try:
                self.tick_once()
            except Exception as e:  # noqa: BLE001 — worker tick은 어떤 예외에서도 살아남아야 한다
                # Never let the worker die — log and continue.
                logger.exception("[webhook.worker] tick error: %s", e)
            self._shutdown.wait(self.tick_sec)


def _iso_offset(now_iso: str, seconds: float) -> str:
    """Return `now_iso + seconds` as ISO-8601. Tolerant to bare 'Z' suffix."""
    s = now_iso[:-1] + "+00:00" if now_iso.endswith("Z") else now_iso
    base = dt.datetime.fromisoformat(s)
    return (base + dt.timedelta(seconds=seconds)).isoformat()
