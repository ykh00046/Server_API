# shared/db_maintenance.py
"""
Production Data Hub - DB Maintenance Utilities

Shared functions for database stabilization checks and index healing.
Used by: tools/watcher.py, tools/backup_db.py, manager.py
"""

from __future__ import annotations

import logging
import os
import sqlite3
import time
from pathlib import Path

from .config import DB_TIMEOUT

logger = logging.getLogger(__name__)


# ==========================================================
# Required Indexes (single source of truth - v8 Optimized)
# ==========================================================
REQUIRED_INDEXES = {
    "idx_production_date": (
        "CREATE INDEX IF NOT EXISTS idx_production_date "
        "ON production_records(production_date)"
    ),
    "idx_item_code": (
        "CREATE INDEX IF NOT EXISTS idx_item_code "
        "ON production_records(item_code)"
    ),
    "idx_production_date_item": (
        "CREATE INDEX IF NOT EXISTS idx_production_date_item "
        "ON production_records(production_date, item_code)"
    ),
    "idx_lot_number": (
        "CREATE INDEX IF NOT EXISTS idx_lot_number "
        "ON production_records(lot_number)"
    ),
    "idx_agg_covering": (
        "CREATE INDEX IF NOT EXISTS idx_agg_covering "
        "ON production_records(item_code, production_date, good_quantity)"
    ),
    "idx_date_qty": (
        "CREATE INDEX IF NOT EXISTS idx_date_qty "
        "ON production_records(production_date, good_quantity)"
    ),
}


# ==========================================================
# File State Helpers
# ==========================================================
def get_file_state(path: Path) -> tuple[float, int]:
    """Get (mtime, size) of a file. Returns (0, 0) if not exists."""
    if not path.exists():
        return 0, 0
    try:
        return os.path.getmtime(path), os.path.getsize(path)
    except Exception:
        return 0, 0


# ==========================================================
# Stabilization
# ==========================================================
STABILIZATION_WAIT = 5       # seconds between checks
STABILIZATION_CHECKS = 3     # consecutive stable checks required
MAX_STABILIZATION_RETRIES = 5  # prevent infinite recursion


def wait_for_stabilization(
    db_path: Path,
    *,
    wait_seconds: float = STABILIZATION_WAIT,
    checks: int = STABILIZATION_CHECKS,
    _retry_count: int = 0,
) -> bool:
    """
    Wait until the DB file's mtime/size stops changing.

    Args:
        db_path: Path to the database file.
        wait_seconds: Seconds between each stability check.
        checks: Number of consecutive stable checks required.
        _retry_count: Internal recursion counter (do not set externally).

    Returns:
        True if stabilized, False if file missing or max retries exceeded.
    """
    if not db_path.exists():
        logger.warning("DB file not found: %s", db_path)
        return False

    if _retry_count >= MAX_STABILIZATION_RETRIES:
        logger.warning("Max stabilization retries reached for %s", db_path.name)
        return False

    last_mtime, last_size = get_file_state(db_path)

    for _ in range(checks):
        time.sleep(wait_seconds)

        current_mtime, current_size = get_file_state(db_path)

        if current_mtime != last_mtime or current_size != last_size:
            logger.info("DB still changing, waiting... (%s)", db_path.name)
            return wait_for_stabilization(
                db_path,
                wait_seconds=wait_seconds,
                checks=checks,
                _retry_count=_retry_count + 1,
            )

    logger.info("DB stabilized: %s (mtime=%s, size=%s)", db_path.name, last_mtime, last_size)
    return True


# ==========================================================
# Index Healing
# ==========================================================
def check_and_heal_indexes(
    db_path: Path,
    indexes: dict[str, str] | None = None,
) -> dict:
    """
    Check and restore missing indexes on a database.

    Args:
        db_path: Path to the SQLite database file.
        indexes: Optional custom index definitions.
                 Defaults to REQUIRED_INDEXES.

    Returns:
        Dict with keys: db, checked, healed (list), error (str|None).
    """
    if indexes is None:
        indexes = REQUIRED_INDEXES

    result: dict = {
        "db": db_path.name,
        "checked": False,
        "healed": [],
        "error": None,
    }

    if not db_path.exists():
        result["error"] = "File not found"
        return result

    try:
        conn = sqlite3.connect(str(db_path), timeout=DB_TIMEOUT)
        cursor = conn.cursor()

        # Get existing index names
        cursor.execute("SELECT name FROM sqlite_master WHERE type = 'index'")
        existing = {row[0] for row in cursor.fetchall()}

        result["checked"] = True

        for name, sql in indexes.items():
            if name not in existing:
                logger.info("Creating missing index: %s on %s", name, db_path.name)
                cursor.execute(sql)
                result["healed"].append(name)

        if result["healed"]:
            conn.commit()
            logger.info("Healed %d indexes on %s", len(result["healed"]), db_path.name)
        else:
            logger.info("All indexes OK on %s", db_path.name)

        conn.close()

    except sqlite3.Error as e:
        result["error"] = str(e)
        logger.error("SQLite error on %s: %s", db_path.name, e)

    except Exception as e:
        result["error"] = str(e)
        logger.error("Error checking %s: %s", db_path.name, e)

    return result


# ==========================================================
# Maintenance (ANALYZE & VACUUM)
# ==========================================================
def run_analyze(db_path: Path) -> dict:
    """
    Run ANALYZE on production_records to update query planner statistics.

    Should be called once per day after DB stabilization.
    Effect: SQLite picks better indexes for queries with combined filters.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        Dict with keys: db, success (bool), duration_ms (float), error (str|None).
    """
    result: dict = {
        "db": db_path.name,
        "success": False,
        "duration_ms": 0.0,
        "error": None,
    }

    if not db_path.exists():
        result["error"] = "File not found"
        return result

    try:
        start = time.perf_counter()
        conn = sqlite3.connect(str(db_path), timeout=DB_TIMEOUT)
        conn.execute("ANALYZE production_records")
        conn.commit()
        conn.close()

        result["duration_ms"] = round((time.perf_counter() - start) * 1000, 1)
        result["success"] = True
        logger.info("ANALYZE completed: %s (%.1fms)", db_path.name, result["duration_ms"])

    except sqlite3.Error as e:
        result["error"] = str(e)
        logger.error("ANALYZE failed on %s: %s", db_path.name, e)

    except Exception as e:
        result["error"] = str(e)
        logger.error("ANALYZE error on %s: %s", db_path.name, e)

    return result


def run_vacuum(db_path: Path) -> dict:
    """
    Run VACUUM to reclaim space and defragment the database.

    Note: This can be a slow operation and locks the DB completely.
    Should be run during maintenance windows or after large deletions.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        Dict with keys: db, success (bool), duration_ms (float), error (str|None).
    """
    result: dict = {
        "db": db_path.name,
        "success": False,
        "duration_ms": 0.0,
        "error": None,
    }

    if not db_path.exists():
        result["error"] = "File not found"
        return result

    try:
        start = time.perf_counter()
        conn = sqlite3.connect(str(db_path), timeout=DB_TIMEOUT)
        # VACUUM cannot be run within a transaction
        conn.execute("VACUUM")
        conn.close()

        result["duration_ms"] = round((time.perf_counter() - start) * 1000, 1)
        result["success"] = True
        logger.info("VACUUM completed: %s (%.1fms)", db_path.name, result["duration_ms"])

    except sqlite3.Error as e:
        result["error"] = str(e)
        logger.error("VACUUM failed on %s: %s", db_path.name, e)

    except Exception as e:
        result["error"] = str(e)
        logger.error("VACUUM error on %s: %s", db_path.name, e)

    return result
