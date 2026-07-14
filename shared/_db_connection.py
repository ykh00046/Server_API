"""Thread-local SQLite connection cache and PRAGMA optimization.

Extracted from shared/database.py (structure-cleanup, 2026-05-27). DBRouter
imports from here and tests reach in via ``shared.database._local`` (which
re-exports this module's _local for backwards compatibility).
"""
from __future__ import annotations

import atexit
import contextlib
import logging
import os
import sqlite3
import threading
import weakref

from .config import ARCHIVE_DB_FILE, DB_FILE, DB_TIMEOUT

logger = logging.getLogger(__name__)


_local = threading.local()

# Connections are cached per thread, so a thread that dies takes its cache entry
# with it and nothing ever closes those connections — Streamlit spawns a fresh
# ScriptRunner thread on every rerun, so the handles piled up for the life of the
# process. The registry tracks the owning thread (weakly, so it does not keep the
# thread alive) and _sweep_dead_thread_connections() closes what the dead ones
# left behind. Keyed by id(conn); the strong conn ref is what makes the close
# possible at all.
_conn_registry: dict[int, tuple[weakref.ref, sqlite3.Connection]] = {}
_connection_lock = threading.Lock()

_wal_enabled_dbs: set[str] = set()
_wal_lock = threading.Lock()


def _register_connection(conn: sqlite3.Connection) -> None:
    """Record a new connection against the thread that owns it."""
    with _connection_lock:
        _conn_registry[id(conn)] = (weakref.ref(threading.current_thread()), conn)


def _sweep_dead_thread_connections() -> int:
    """Close connections whose owning thread is gone. Returns how many closed.

    Called from the connection-creation path, so the cost is bounded: the
    registry holds at most (live threads × cache-key combinations) entries.
    Cross-thread close is legal because connections are created with
    check_same_thread=False and a dead owner cannot be racing us.
    """
    to_close: list[sqlite3.Connection] = []
    with _connection_lock:
        for key, (thread_ref, conn) in list(_conn_registry.items()):
            owner = thread_ref()
            if owner is None or not owner.is_alive():
                to_close.append(conn)
                del _conn_registry[key]

    for conn in to_close:  # close outside the lock — it is I/O
        with contextlib.suppress(sqlite3.Error):
            conn.close()
    if to_close:
        logger.debug(f"Swept {len(to_close)} connection(s) from dead threads")
    return len(to_close)


def _cleanup_all_connections() -> None:
    """Cleanup all cached connections on program exit.

    Only ever closed main-thread connections before: with the default
    check_same_thread=True, close() from another thread raises ProgrammingError,
    which the suppress below swallowed silently.
    """
    with _connection_lock:
        conns = [conn for _, conn in _conn_registry.values()]
        _conn_registry.clear()

    for conn in conns:
        with contextlib.suppress(sqlite3.Error):
            conn.close()
    logger.debug("All database connections cleaned up")


def _discard_connection(conn: sqlite3.Connection) -> None:
    """Close a dead/stale cached connection and drop it from the registry.

    Without the removal, every ERP DB-file swap registered a fresh connection
    per thread while the closed one stayed forever — unbounded growth on a
    long-running server."""
    with contextlib.suppress(sqlite3.Error):
        conn.close()
    with _connection_lock:
        _conn_registry.pop(id(conn), None)


atexit.register(_cleanup_all_connections)


def _apply_pragma_settings(conn: sqlite3.Connection) -> None:
    """Apply optimized SQLite PRAGMA settings (WAL, large cache, mmap)."""
    try:
        result = conn.execute("PRAGMA journal_mode=WAL").fetchone()
        if result and result[0] == "wal":
            with _wal_lock:
                _wal_enabled_dbs.add(str(id(conn)))

        conn.execute("PRAGMA cache_size=-64000")  # 64MB
        conn.execute("PRAGMA mmap_size=268435456")  # 256MB
        conn.execute(f"PRAGMA busy_timeout={DB_TIMEOUT * 1000}")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA temp_store=MEMORY")

        logger.debug(
            "SQLite PRAGMA settings applied (WAL, 64MB cache, 256MB mmap)"
        )
    except sqlite3.Error as e:
        logger.warning(f"Failed to apply PRAGMA settings: {e}")


def _get_db_mtime() -> tuple[float, float]:
    """Get mtime of Live and Archive DBs (0 if file missing)."""
    live_mtime = os.path.getmtime(DB_FILE) if DB_FILE.exists() else 0
    archive_mtime = (
        os.path.getmtime(ARCHIVE_DB_FILE) if ARCHIVE_DB_FILE.exists() else 0
    )
    return live_mtime, archive_mtime
