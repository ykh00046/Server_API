"""Pydantic schemas + URL validator for webhook notifications.

The validator lives in this module (not _http_helpers) because the rule
set is specific to webhook URLs and may grow (SSRF allow/block lists,
host whitelists, etc.) without affecting the generic HTTP helpers.
"""
from __future__ import annotations

import ipaddress
import os
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field

ALLOWED_SCHEMES = {"http", "https"}

# Hostnames that always resolve to the local machine.
_LOOPBACK_HOSTNAMES = {"localhost"}

_TRUTHY = {"1", "true", "yes", "on"}


def _blocked_ip_reason(hostname: str) -> str | None:
    """SSRF guard for IP-literal hosts (full-review-202607 H).

    Loopback / link-local (cloud metadata 169.254.169.254) / unspecified /
    reserved / multicast addresses are always rejected. Private ranges
    (10/8, 172.16/12, 192.168/16) are allowed by default — webhook receivers
    on this deployment live on the internal network — but can be rejected
    with WEBHOOK_BLOCK_PRIVATE_IPS=1.

    DNS names are deliberately NOT resolved here: validation must stay
    offline (no network in tests / no latency on create), so a DNS name
    pointing at a blocked IP is out of scope for this layer.
    """
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        return None  # not an IP literal
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:  # ::ffff:127.0.0.1 style
        ip = mapped
    if ip.is_loopback or ip.is_unspecified:
        return "loopback/unspecified IP is not allowed"
    if ip.is_link_local:
        return "link-local IP is not allowed"
    if ip.is_multicast or ip.is_reserved:
        return "multicast/reserved IP is not allowed"
    block_private = (
        os.getenv("WEBHOOK_BLOCK_PRIVATE_IPS", "0").strip().lower() in _TRUTHY
    )
    if block_private and ip.is_private:
        return "private-range IP is blocked (WEBHOOK_BLOCK_PRIVATE_IPS)"
    return None


def validate_webhook_url(url: str) -> str:
    """Return url if acceptable, else raise ValueError.

    Rules:
    - scheme must be http or https
    - netloc (host) must be present
    - host must not appear in WEBHOOK_BLOCKED_HOSTS env (comma-separated)
    - IP-literal hosts must pass the SSRF guard (_blocked_ip_reason)
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
    hostname = (parsed.hostname or "").rstrip(".").lower()
    if hostname in _LOOPBACK_HOSTNAMES:
        raise ValueError("loopback host is not allowed")
    reason = _blocked_ip_reason(hostname)
    if reason:
        raise ValueError(reason)
    blocked_raw = os.getenv("WEBHOOK_BLOCKED_HOSTS", "")
    blocked = {h.strip().lower() for h in blocked_raw.split(",") if h.strip()}
    if blocked and hostname in blocked:
        raise ValueError(f"host {hostname!r} is blocked")
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
