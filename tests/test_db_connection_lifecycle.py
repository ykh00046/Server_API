# tests/test_db_connection_lifecycle.py
"""Connection lifecycle tests (F-03).

Connections are cached per thread. Streamlit runs every rerun on a fresh
ScriptRunner thread and compare_periods used to spawn a thread pool per call, so
each of those threads left a connection behind that no code path could close —
the registry (and the file handles) grew for the life of the process.
"""

from __future__ import annotations

import sqlite3
import threading

import pytest

from api.tools.summary import compare_periods
from shared import _db_connection as dbc
from shared.database import DBRouter


def _registry_snapshot() -> list[tuple[threading.Thread | None, sqlite3.Connection]]:
    with dbc._connection_lock:
        return [(ref(), conn) for ref, conn in dbc._conn_registry.values()]


def test_dead_thread_connections_are_swept(live_db):
    """A connection whose owning thread has exited is closed on the next
    get_connection() — not merely forgotten."""
    held: list[sqlite3.Connection] = []

    def worker():
        held.append(DBRouter.get_connection(use_archive=False))

    for _ in range(5):
        t = threading.Thread(target=worker)
        t.start()
        t.join()

    assert len(held) == 5
    DBRouter.get_connection(use_archive=False)  # main thread: creation → sweep

    owners = [owner for owner, _ in _registry_snapshot()]
    assert owners, "the live main-thread connection must survive the sweep"
    assert all(o is not None and o.is_alive() for o in owners)

    for conn in held:  # actually closed, not just unregistered
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")


def test_sweep_spares_live_thread_connections(live_db):
    """A connection held by a *running* thread stays registered and usable."""
    started = threading.Event()
    release = threading.Event()
    worker_conn: list[sqlite3.Connection] = []

    def worker():
        worker_conn.append(DBRouter.get_connection(use_archive=False))
        started.set()
        release.wait(timeout=5)

    t = threading.Thread(target=worker)
    t.start()
    try:
        assert started.wait(timeout=5)
        DBRouter.get_connection(use_archive=False)  # triggers a sweep

        registered = [conn for _, conn in _registry_snapshot()]
        assert worker_conn[0] in registered
        assert worker_conn[0].execute("SELECT 1").fetchone()[0] == 1
    finally:
        release.set()
        t.join(timeout=5)


def test_same_thread_reuses_cached_connection(live_db):
    """The point of the cache survives the fix: one connection per thread/key."""
    first = DBRouter.get_connection(use_archive=False)
    second = DBRouter.get_connection(use_archive=False)
    assert first is second


def test_registry_stays_bounded_under_thread_churn(live_db):
    """100 rerun-like cycles leave no residue: registry ≈ live threads only."""
    def worker():
        DBRouter.get_connection(use_archive=False)

    for _ in range(100):
        t = threading.Thread(target=worker)
        t.start()
        t.join()

    DBRouter.get_connection(use_archive=False)  # final sweep

    owners = [owner for owner, _ in _registry_snapshot()]
    assert all(o is not None and o.is_alive() for o in owners)
    # bound: live threads × cache-key combinations (use_archive × read_only)
    assert len(owners) <= threading.active_count() * 4


def test_cleanup_all_closes_cross_thread_connections(live_db):
    """atexit cleanup really closes other threads' connections.

    It could not before: with the default check_same_thread=True, close() from a
    different thread raises ProgrammingError, which the cleanup swallowed.
    """
    held: list[sqlite3.Connection] = []

    def worker():
        held.append(DBRouter.get_connection(use_archive=False))

    t = threading.Thread(target=worker)
    t.start()
    t.join()

    dbc._cleanup_all_connections()

    assert not _registry_snapshot()
    with pytest.raises(sqlite3.ProgrammingError):
        held[0].execute("SELECT 1")


def test_compare_periods_spawns_no_threads(live_db):
    """Sequential now — same numbers, and no per-call thread pool leaving two
    more connections stranded on every call."""
    before = threading.active_count()

    result = compare_periods("2026-03-01", "2026-03-31", "2026-04-01", "2026-04-30")

    assert result["status"] == "success"
    assert result["period1"]["total_quantity"] == 300  # seeded 100 + 200 in March
    assert result["period2"]["total_quantity"] == 350  # seeded 300 + 50 in April
    assert threading.active_count() == before


