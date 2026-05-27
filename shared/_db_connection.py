"""Thread-local SQLite connection cache and PRAGMA optimization.

Extracted from shared/database.py (structure-cleanup, 2026-05-27). DBRouter
imports from here and tests reach in via ``shared.database._local`` (which
re-exports this module's _local for backwards compatibility).
"""
from __future__ import annotations

import atexit
import logging
import os
import sqlite3
import threading

from .config import ARCHIVE_DB_FILE, DB_FILE, DB_TIMEOUT

logger = logging.getLogger(__name__)


_local = threading.local()
_all_connections: list[sqlite3.Connection] = []
_connection_lock = threading.Lock()

_wal_enabled_dbs: set[str] = set()
_wal_lock = threading.Lock()


def _cleanup_all_connections() -> None:
    """Cleanup all cached connections on program exit."""
    with _connection_lock:
        for conn in _all_connections:
            try:
                conn.close()
            except sqlite3.Error:
                pass
        _all_connections.clear()
    logger.debug("All database connections cleaned up")


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
