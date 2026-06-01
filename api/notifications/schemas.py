"""Pydantic schemas + URL validator for webhook notifications.

The validator lives in this module (not _http_helpers) because the rule
set is specific to webhook URLs and may grow (SSRF allow/block lists,
host whitelists, etc.) without affecting the generic HTTP helpers.
"""
from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field

ALLOWED_SCHEMES = {"http", "https"}


def validate_webhook_url(url: str) -> str:
    """Return url if acceptable, else raise ValueError.

    Rules:
    - scheme must be http or https
    - netloc (host) must be present
    - host must not appear in WEBHOOK_BLOCKED_HOSTS env (comma-separated)
    """
    if not isinstance(url, str) or not url:
        raise ValueError("url must be a non-empty string")
    if len(url) > 2048:
        raise ValueError("url exceeds 2048 characters")
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise ValueError("url scheme must be http or https")
    if not parsed.netloc:
        raise ValueError("url must include a host")
    blocked_raw = os.getenv("WEBHOOK_BLOCKED_HOSTS", "")
    blocked = {h.strip().lower() for h in blocked_raw.split(",") if h.strip()}
    if blocked and parsed.hostname and parsed.hostname.lower() in blocked:
        raise ValueError(f"host {parsed.hostname!r} is blocked")
    return url


def validate_event_types(types: list[str]) -> list[str]:
    """Reject non-string entries, normalize to a deduplicated list."""
    if not isinstance(types, list):
        raise ValueError("event_types must be a list")
    if len(types) > 64:
        raise ValueError("event_types exceeds 64 entries")
    out: list[str] = []
    seen: set[str] = set()
    for t in types:
        if not isinstance(t, str):
            raise ValueError("event_types entries must be strings")
        t2 = t.strip()
        if not t2:
            continue
        if len(t2) > 128:
            raise ValueError("event_type entry exceeds 128 characters")
        if t2 in seen:
            continue
        seen.add(t2)
        out.append(t2)
    return out


class WebhookCreate(BaseModel):
    url: str = Field(..., max_length=2048)
    event_types: list[str] = Field(default_factory=list)
    description: str = Field(default="", max_length=500)
    active: bool = True


class WebhookUpdate(BaseModel):
    event_types: list[str] | None = None
    description: str | None = Field(default=None, max_length=500)
    active: bool | None = None
    rotate_secret: bool = False


class WebhookPublic(BaseModel):
    id: int
    url: str
    event_types: list[str]
    description: str
    active: bool
    created_at: str
    updated_at: str


class WebhookCreated(WebhookPublic):
    secret: str  # one-time disclosure


class DeliveryPublic(BaseModel):
    id: int
    webhook_id: int
    event_type: str
    status: str
    response_status: int | None = None
    response_body: str | None = None
    error: str | None = None
    attempted_at: str
    duration_ms: int


class EventTypeInfo(BaseModel):
    name: str
    description: str


class TestPing(BaseModel):
    payload: dict[str, Any] | None = None
