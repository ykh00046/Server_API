"""Pure formatters for the webhook admin UI.

No Streamlit, no IO, no global state. All functions are deterministic
given their inputs so they can be unit-tested in isolation.
"""
from __future__ import annotations

from typing import Any

# Status emoji lookup — keep wide enough to gracefully handle unknowns.
_STATUS_EMOJI = {
    "success": "✅",
    "pending": "⏳",
    "queued": "📨",
    "in_flight": "🚀",
    "retrying": "🔁",
    "failed": "⚠️",
    "dead": "💀",
    "permanent_failure": "💀",
}

# Card definitions: (stats_key, label, hint). Order is the rendered order.
_STATS_CARDS: tuple[tuple[str, str, str], ...] = (
    ("queued", "대기 중", "neutral"),
    ("in_flight", "발송 중", "info"),
    ("retrying", "재시도 대기", "warn"),
    ("success_24h", "24h 성공", "ok"),
    ("failure_24h", "24h 실패", "warn"),
    ("dead", "포기됨", "danger"),
)


def truncate(text: str | None, limit: int) -> str:
    """Trim text to `limit` chars and append a single '…' if shortened.

    `None` → empty string. `limit <= 0` → empty string.
    """
    if not text:
        return ""
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    if limit == 1:
        return "…"
    return text[: limit - 1] + "…"


def format_queue_stats_cards(stats: dict | None) -> list[tuple[str, int, str]]:
    """Return [(label, value, hint), ...] in fixed 6-card order.

    Missing keys default to 0 — keeps the UI stable when the backend adds
    new stats or returns a partial payload.
    """
    stats = stats or {}
    out: list[tuple[str, int, str]] = []
    for key, label, hint in _STATS_CARDS:
        raw = stats.get(key, 0)
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = 0
        out.append((label, value, hint))
    return out


def format_webhook_row(wh: dict) -> dict:
    """Project a WebhookPublic dict into row-ready strings.

    UI-safe defaults for missing fields so the table never raises.
    """
    events = wh.get("event_types") or []
    if not isinstance(events, list):
        events = []
    return {
        "id": wh.get("id", "-"),
        "url": truncate(str(wh.get("url", "")), 60),
        "events": ", ".join(events) if events else "(전체)",
        "active": "✅" if wh.get("active") else "⛔",
        "description": truncate(str(wh.get("description") or ""), 40),
        "created_at": str(wh.get("created_at") or "")[:19],  # ISO 'YYYY-MM-DDTHH:MM:SS'
    }


def format_delivery_row(d: dict) -> dict:
    """Project a DeliveryPublic dict into row-ready strings."""
    status = str(d.get("status") or "")
    emoji = _STATUS_EMOJI.get(status, "❔")
    dur_ms = d.get("duration_ms")
    try:
        dur_str = f"{int(dur_ms)} ms" if dur_ms is not None else "-"
    except (TypeError, ValueError):
        dur_str = "-"
    resp_status = d.get("response_status")
    resp_str = "-" if resp_status is None else str(resp_status)
    err = d.get("error")
    summary = truncate(str(err), 80) if err else truncate(str(d.get("response_body") or ""), 80)
    return {
        "id": d.get("id", "-"),
        "event_type": str(d.get("event_type") or "-"),
        "status": f"{emoji} {status}" if status else emoji,
        "response_status": resp_str,
        "duration": dur_str,
        "attempted_at": str(d.get("attempted_at") or "")[:19],
        "summary": summary,
    }


def parse_event_types_input(raw: str | None) -> list[str]:
    """Convert comma/newline-separated user input into a normalized list.

    Empties are dropped; entries are stripped and de-duplicated (order
    preserved). Returns [] for None / blank input.
    """
    if not raw:
        return []
    tokens: list[str] = []
    for line in raw.replace(",", "\n").splitlines():
        t = line.strip()
        if not t:
            continue
        if t not in tokens:
            tokens.append(t)
    return tokens


def is_retryable_status(status: Any) -> bool:
    """Whether a delivery's status warrants a 'retry' button in the UI."""
    return str(status or "").lower() in {"failed", "dead", "permanent_failure"}


__all__ = [
    "format_queue_stats_cards",
    "format_webhook_row",
    "format_delivery_row",
    "truncate",
    "parse_event_types_input",
    "is_retryable_status",
]
