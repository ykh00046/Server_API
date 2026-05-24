"""HTTP dispatch + HMAC-SHA256 signing for webhook deliveries.

The dispatcher NEVER raises — every failure is captured into DispatchResult.
A `transport` keyword argument lets tests inject httpx.MockTransport so
no real network calls are made.
"""
from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from typing import Any, Mapping

import httpx
import orjson

from shared import get_logger
from shared.config import WEBHOOK_TIMEOUT_SEC, WEBHOOK_USER_AGENT

logger = get_logger(__name__)


SIGNATURE_HEADER = "X-Webhook-Signature"
EVENT_HEADER = "X-Webhook-Event"
DELIVERY_HEADER = "X-Webhook-Delivery"
TIMESTAMP_HEADER = "X-Webhook-Timestamp"
MAX_BODY_CAPTURE = 1024  # response body chars persisted


@dataclass
class DispatchResult:
    status: str  # success | failure
    response_status: int | None
    response_body: str | None
    error: str | None
    duration_ms: int
    retry_after_sec: float | None = None  # webhook-async-dispatch-v2


def compute_signature(secret: str, body: bytes) -> str:
    mac = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={mac}"


def _parse_retry_after_header(raw: str | None) -> float | None:
    """Accept integer-seconds form of Retry-After only (HTTP-date OOS in v2)."""
    if not raw:
        return None
    try:
        v = float(raw)
    except ValueError:
        return None
    return v if v > 0 else None


def send(
    *,
    url: str,
    secret: str,
    event_type: str,
    delivery_id: int,
    payload: Mapping[str, Any],
    timeout: float | None = None,
    transport: httpx.BaseTransport | None = None,
) -> DispatchResult:
    """Send one webhook POST. Returns DispatchResult — never raises."""
    body = orjson.dumps(dict(payload))
    sig = compute_signature(secret, body)
    headers = {
        SIGNATURE_HEADER: sig,
        EVENT_HEADER: event_type,
        DELIVERY_HEADER: str(delivery_id),
        TIMESTAMP_HEADER: str(int(time.time())),
        "User-Agent": WEBHOOK_USER_AGENT,
        "Content-Type": "application/json",
    }
    effective_timeout = float(timeout if timeout is not None else WEBHOOK_TIMEOUT_SEC)
    started = time.perf_counter()
    try:
        client_kwargs: dict[str, Any] = {"timeout": effective_timeout}
        if transport is not None:
            client_kwargs["transport"] = transport
        with httpx.Client(**client_kwargs) as cli:
            resp = cli.post(url, content=body, headers=headers)
        captured = (resp.text or "")[:MAX_BODY_CAPTURE]
        ok = 200 <= resp.status_code < 300
        return DispatchResult(
            status="success" if ok else "failure",
            response_status=resp.status_code,
            response_body=captured,
            error=None,
            duration_ms=int((time.perf_counter() - started) * 1000),
            retry_after_sec=_parse_retry_after_header(resp.headers.get("Retry-After")),
        )
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"[:1024]
        logger.warning(
            "[webhook.dispatch] delivery_id=%s event=%s url=%s failed: %s",
            delivery_id, event_type, url, msg,
        )
        return DispatchResult(
            status="failure",
            response_status=None,
            response_body=None,
            error=msg,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
