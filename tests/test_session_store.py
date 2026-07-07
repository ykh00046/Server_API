# tests/test_session_store.py
"""SessionStore unit tests (IP binding, TTL sliding, per-IP evict).

Tests exercise the module-level _sessions dict + helpers in api/chat.py.
"""

import pytest

from api import _session_store as sstore
from api import chat as chat_mod


class _FakeClock:
    """flaky-reproduce-first: sleep 기반 순서 보장은 Windows time.time()
    해상도(~15.6ms)에서 타임스탬프 동률이 될 수 있다 — 시간을 주입한다."""

    def __init__(self, start: float = 1_000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture(autouse=True)
def clean_sessions():
    sstore._sessions.clear()
    sstore._cleanup_counter = 0
    yield
    sstore._sessions.clear()


@pytest.fixture
def clock(monkeypatch):
    fake = _FakeClock()
    monkeypatch.setattr(sstore, "_clock", fake)
    return fake


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


def test_per_ip_limit_evicts_oldest(monkeypatch, clock):
    monkeypatch.setattr(sstore, "CHAT_SESSION_MAX_PER_IP", 3)
    for i in range(3):
        sstore.save_session_history(f"s{i}", [i], "1.1.1.1")
        clock.advance(1.0)
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


def test_last_access_updates_on_get(clock):
    sstore.save_session_history("sid1", ["a"], "1.1.1.1")
    first = sstore._sessions["sid1"]["last_access"]
    clock.advance(1.0)
    sstore.get_session_history("sid1", "1.1.1.1")
    second = sstore._sessions["sid1"]["last_access"]
    assert second > first


def test_save_noop_without_session_id():
    sstore.save_session_history(None, ["a"], "1.1.1.1")
    assert sstore._sessions == {}


def test_stats_shape():
    sstore.save_session_history("sid1", ["a"], "1.1.1.1")
    s = sstore.stats()
    assert s["count"] == 1
    assert {"ttl_sec", "max_per_ip", "max_total"} <= set(s)


# ----------------------------------------------------------
# cleanup_expired_sessions
# ----------------------------------------------------------
def test_cleanup_skips_until_interval():
    sstore.save_session_history("sid1", ["a"], "1.1.1.1")
    # Counter below interval -> early return, nothing removed.
    sstore._cleanup_counter = 0
    sstore.cleanup_expired_sessions()
    assert "sid1" in sstore._sessions


def test_cleanup_removes_expired(monkeypatch, clock):
    monkeypatch.setattr(sstore, "SESSION_TTL", 1)
    sstore.save_session_history("old", ["a"], "1.1.1.1")
    sstore.save_session_history("fresh", ["b"], "1.1.1.1")
    # Age out "old" only.
    sstore._sessions["old"]["last_access"] = clock() - 100
    # Trip the interval gate so cleanup actually runs this call.
    sstore._cleanup_counter = sstore.SESSION_CLEANUP_INTERVAL - 1
    sstore.cleanup_expired_sessions()
    assert "old" not in sstore._sessions
    assert "fresh" in sstore._sessions


def test_cleanup_enforces_global_cap(monkeypatch, clock):
    monkeypatch.setattr(sstore, "SESSION_MAX_COUNT", 2)
    monkeypatch.setattr(sstore, "SESSION_TTL", 10_000)  # keep all "fresh"
    for i in range(5):
        sstore.save_session_history(f"s{i}", [i], "1.1.1.1")
        sstore._sessions[f"s{i}"]["last_access"] = clock() + i  # s0 oldest
    sstore._cleanup_counter = sstore.SESSION_CLEANUP_INTERVAL - 1
    sstore.cleanup_expired_sessions()
    # Trimmed down to the global cap, oldest dropped first.
    assert len(sstore._sessions) == 2
    assert "s0" not in sstore._sessions
