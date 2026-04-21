# tests/test_session_store.py
"""SessionStore unit tests (IP binding, TTL sliding, per-IP evict).

Tests exercise the module-level _sessions dict + helpers in api/chat.py.
"""

import time

import pytest

from api import chat as chat_mod
from api import _session_store as sstore


@pytest.fixture(autouse=True)
def clean_sessions():
    sstore._sessions.clear()
    sstore._cleanup_counter = 0
    yield
    sstore._sessions.clear()


def test_returns_empty_when_no_session():
    assert sstore.get_session_history(None, "1.1.1.1") == []
    assert sstore.get_session_history("nope", "1.1.1.1") == []
    # Re-export shim still works
    assert chat_mod._get_session_history("nope", "1.1.1.1") == []


def test_save_and_get_same_ip():
    sstore.save_session_history("sid1", ["a", "b"], "1.1.1.1")
    assert sstore.get_session_history("sid1", "1.1.1.1") == ["a", "b"]


def test_cross_ip_isolation():
    sstore.save_session_history("sid1", ["secret"], "1.1.1.1")
    assert sstore.get_session_history("sid1", "2.2.2.2") == []


def test_per_ip_limit_evicts_oldest(monkeypatch):
    monkeypatch.setattr(sstore, "CHAT_SESSION_MAX_PER_IP", 3)
    for i in range(3):
        sstore.save_session_history(f"s{i}", [i], "1.1.1.1")
        time.sleep(0.001)
    # Adding a 4th forces eviction of the oldest ("s0")
    sstore.save_session_history("s3", [3], "1.1.1.1")
    remaining = {
        sid for sid, d in sstore._sessions.items()
        if d.get("owner_ip") == "1.1.1.1"
    }
    assert "s0" not in remaining
    assert {"s1", "s2", "s3"}.issubset(remaining)


def test_trims_to_max_turns():
    long_history = list(range(100))
    sstore.save_session_history("sid1", long_history, "1.1.1.1")
    stored = sstore._sessions["sid1"]["history"]
    assert len(stored) == sstore.SESSION_MAX_TURNS * 2


def test_last_access_updates_on_get():
    sstore.save_session_history("sid1", ["a"], "1.1.1.1")
    first = sstore._sessions["sid1"]["last_access"]
    time.sleep(0.01)
    sstore.get_session_history("sid1", "1.1.1.1")
    second = sstore._sessions["sid1"]["last_access"]
    assert second > first
