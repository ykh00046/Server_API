# api/_session_store.py
"""In-memory chat session store with IP binding, TTL, and per-IP eviction.

Extracted from api/chat.py (Act-1 of security-and-test-improvement).

The module exposes the raw `_sessions` dict plus helpers so that
existing call sites and tests that touched these names continue to
work without change after re-export from `api.chat`.
"""

from __future__ import annotations

import time

from shared import get_logger
from shared.config import (
    CHAT_SESSION_TTL_SEC as SESSION_TTL,
    CHAT_SESSION_MAX_PER_IP,
    CHAT_SESSION_MAX_TOTAL as SESSION_MAX_COUNT,
)

logger = get_logger(__name__)

SESSION_MAX_TURNS = 10
SESSION_CLEANUP_INTERVAL = 100

_sessions: dict[str, dict] = {}
_cleanup_counter = 0


def get_session_history(session_id: str | None, owner_ip: str = "unknown") -> list:
    """Return history for session bound to owner_ip. Empty on miss or IP mismatch."""
    if not session_id or session_id not in _sessions:
        return []
    session = _sessions[session_id]
    if session.get("owner_ip") != owner_ip:
        logger.warning(
            f"[Session] session_id={session_id} requested by ip={owner_ip}, "
            f"owner={session.get('owner_ip')} — isolated"
        )
        return []
    session["last_access"] = time.time()
    return session["history"]


def save_session_history(
    session_id: str | None, history: list, owner_ip: str = "unknown"
) -> None:
    """Persist trimmed history keyed by session_id, tagged with owner_ip."""
    if not session_id:
        return

    max_entries = SESSION_MAX_TURNS * 2
    if len(history) > max_entries:
        history = history[-max_entries:]

    ip_sessions = [
        (sid, data) for sid, data in _sessions.items()
        if data.get("owner_ip") == owner_ip and sid != session_id
    ]
    if len(ip_sessions) >= CHAT_SESSION_MAX_PER_IP:
        ip_sessions.sort(key=lambda kv: kv[1].get("last_access", 0))
        to_evict = len(ip_sessions) - CHAT_SESSION_MAX_PER_IP + 1
        for sid, _ in ip_sessions[:to_evict]:
            _sessions.pop(sid, None)
        logger.warning(
            f"[Session] per-IP limit ({CHAT_SESSION_MAX_PER_IP}) hit for "
            f"ip={owner_ip}, evicted={to_evict}"
        )

    _sessions[session_id] = {
        "history": history,
        "last_access": time.time(),
        "owner_ip": owner_ip,
    }


def cleanup_expired_sessions() -> None:
    """Rate-limited lazy cleanup: remove TTL-expired sessions and enforce global cap."""
    global _cleanup_counter
    _cleanup_counter += 1
    if _cleanup_counter < SESSION_CLEANUP_INTERVAL:
        return
    _cleanup_counter = 0

    now = time.time()
    expired = [
        sid for sid, data in _sessions.items()
        if now - data["last_access"] > SESSION_TTL
    ]
    for sid in expired:
        del _sessions[sid]

    if len(_sessions) > SESSION_MAX_COUNT:
        sorted_sessions = sorted(
            _sessions.items(), key=lambda x: x[1]["last_access"]
        )
        to_remove = len(_sessions) - SESSION_MAX_COUNT
        for sid, _ in sorted_sessions[:to_remove]:
            del _sessions[sid]
        logger.warning(
            f"[Session Cleanup] Session limit reached ({SESSION_MAX_COUNT}), "
            f"removed {to_remove} oldest sessions"
        )

    if expired:
        logger.debug(f"[Session Cleanup] Removed {len(expired)} expired sessions")


def stats() -> dict:
    return {
        "count": len(_sessions),
        "ttl_sec": SESSION_TTL,
        "max_per_ip": CHAT_SESSION_MAX_PER_IP,
        "max_total": SESSION_MAX_COUNT,
    }
