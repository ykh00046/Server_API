# shared/database.py
"""
Production Data Hub - Database Routing and Connection Management

Provides:
- DBTargets: Dataclass indicating which DBs to query
- DBRouter: Unified DB connection, routing, and query utilities

Key Design (Section 6.1, 6.2):
- pick_targets() returns explicit DBTargets(use_archive, use_live)
- UNION queries include 'source' column for debugging and cursor pagination
- Cutoff date passed as parameter where possible

v8 Performance Optimizations:
- WAL mode for better concurrency
- Optimized PRAGMA settings
- Connection pooling with smart caching
"""

from __future__ import annotations

import atexit
import os
import sqlite3
import logging
import threading
from dataclasses import dataclass
from typing import Any

from .config import (
    DB_FILE,
    ARCHIVE_DB_FILE,
    ARCHIVE_CUTOFF_DATE,
    ARCHIVE_DB_WHITELIST,
    DB_TIMEOUT,
)
from .validators import resolve_archive_db

logger = logging.getLogger(__name__)


# ==========================================================
# Shared ATTACH helper (security-hardening-v3)
# ==========================================================
def attach_archive_safe(
    conn: sqlite3.Connection,
    archive_path: "str | os.PathLike | None" = None,
    *,
    alias: str = "archive",
    whitelist: "tuple | None" = None,
):
    """ATTACH archive DB safely (whitelist + bind-first + ro mode).

    Used by both `DBRouter.get_connection()` and `api/tools.execute_custom_query`
    to keep the path-validation + ATTACH pattern in one place.

    Args:
        conn: Active sqlite3 connection (any mode).
        archive_path: Requested archive DB path. Defaults to ARCHIVE_DB_FILE.
        alias: Schema alias used in `ATTACH ... AS <alias>`. Internal constant only.
        whitelist: Allowed paths. Defaults to ARCHIVE_DB_WHITELIST from config.

    Returns:
        Resolved Path of the attached archive DB.

    Raises:
        ValueError: Path not in whitelist.
        FileNotFoundError: Archive file does not exist.
        sqlite3.OperationalError: Both bind and string ATTACH variants failed.
    """
    target = archive_path if archive_path is not None else ARCHIVE_DB_FILE
    wl = whitelist if whitelist is not None else ARCHIVE_DB_WHITELIST
    resolved = resolve_archive_db(target, wl)
    archive_uri = f"file:{resolved.as_posix()}?mode=ro"
    try:
        conn.execute(f"ATTACH DATABASE ? AS {alias}", (archive_uri,))
    except sqlite3.OperationalError:
        # Some sqlite builds do not accept parameter binding for ATTACH.
        # Safe because archive_uri came from resolve_archive_db (whitelist-validated)
        # and `alias` is an internal constant, never user input.
        conn.execute(f"ATTACH DATABASE '{archive_uri}' AS {alias}")
    return resolved

# ==========================================================
# v7: Thread-local Connection Cache with mtime invalidation
# ==========================================================
_local = threading.local()
_all_connections: list[sqlite3.Connection] = []
_connection_lock = threading.Lock()


def _cleanup_all_connections() -> None:
    """Cleanup all cached connections on program exit."""
    with _connection_lock:
        for conn in _all_connections:
            try:
                conn.close()
            except Exception:
                pass
        _all_connections.clear()
    logger.debug("All database connections cleaned up")


# Register cleanup on exit
atexit.register(_cleanup_all_connections)


# ==========================================================
# v8: PRAGMA Optimization & WAL Mode
# ==========================================================
_wal_enabled_dbs: set[str] = set()  # Track which DBs have WAL enabled
_wal_lock = threading.Lock()


def _apply_pragma_settings(conn: sqlite3.Connection) -> None:
    """
    Apply optimized SQLite PRAGMA settings.

    v8 Enhancement:
    - WAL mode for better concurrency
    - Larger cache for performance
    - Memory-mapped I/O for reads
    """
    try:
        # Enable WAL mode for better concurrency
        result = conn.execute("PRAGMA journal_mode=WAL").fetchone()
        if result and result[0] == "wal":
            with _wal_lock:
                _wal_enabled_dbs.add(str(id(conn)))

        # Larger cache size (negative = KB, positive = pages)
        conn.execute("PRAGMA cache_size=-64000")  # 64MB

        # Memory-mapped I/O for read performance
        conn.execute("PRAGMA mmap_size=268435456")  # 256MB

        # Busy timeout for write conflicts
        conn.execute(f"PRAGMA busy_timeout={DB_TIMEOUT * 1000}")

        # Synchronous mode (NORMAL is safe with WAL)
        conn.execute("PRAGMA synchronous=NORMAL")

        # Temp store in memory
        conn.execute("PRAGMA temp_store=MEMORY")

        logger.debug("SQLite PRAGMA settings applied (WAL, 64MB cache, 256MB mmap)")
    except Exception as e:
        logger.warning(f"Failed to apply PRAGMA settings: {e}")


def _get_db_mtime() -> tuple[float, float]:
    """Get mtime of Live and Archive DBs."""
    live_mtime = os.path.getmtime(DB_FILE) if DB_FILE.exists() else 0
    archive_mtime = os.path.getmtime(ARCHIVE_DB_FILE) if ARCHIVE_DB_FILE.exists() else 0
    return live_mtime, archive_mtime


@dataclass(frozen=True)
class DBTargets:
    """
    Indicates which databases need to be queried.

    use_archive: Query archive.production_records (data < CUTOFF)
    use_live: Query production_records (data >= CUTOFF)
    """
    use_archive: bool
    use_live: bool

    @property
    def need_union(self) -> bool:
        """True if both DBs need to be queried (UNION ALL required)"""
        return self.use_archive and self.use_live

    @property
    def archive_only(self) -> bool:
        """True if only archive DB is needed"""
        return self.use_archive and not self.use_live

    @property
    def live_only(self) -> bool:
        """True if only live DB is needed"""
        return self.use_live and not self.use_archive


class DBRouter:
    """
    Dual DB (Live + Archive) routing and connection management.

    All database access should go through this class to ensure
    consistent handling of the 2025/2026 boundary.
    """

    @staticmethod
    def pick_targets(date_from: str | None, date_to: str | None = None) -> DBTargets:
        """
        Determine which databases need to be queried based on date range.

        Args:
            date_from: Start date (YYYY-MM-DD), inclusive. None = no lower bound.
            date_to: End date (YYYY-MM-DD), exclusive (next day of last inclusive date).
                     None = no upper bound.
                     IMPORTANT: Callers should pass date_to + 1 day for inclusive ranges.

        Returns:
            DBTargets indicating which databases to query.

        Examples (date_to is exclusive):
            - None, None -> Both (full scan)
            - 2025-12-01, 2026-01-01 -> Archive only (data up to 2025-12-31)
            - 2026-01-01, 2026-02-01 -> Live only (data 2026-01-01 ~ 2026-01-31)
            - 2025-12-15, 2026-01-11 -> Both (crosses boundary)
        """
        cutoff = ARCHIVE_CUTOFF_DATE

        # Case 1: No date range specified -> query both
        if date_from is None and date_to is None:
            return DBTargets(use_archive=True, use_live=True)

        # Case 2: Only date_to specified
        if date_from is None:
            # Archive needed (no lower bound means could include old data)
            # Live needed only if date_to reaches into live period
            return DBTargets(
                use_archive=True,
                use_live=(date_to >= cutoff)
            )

        # Case 3: Only date_from specified
        if date_to is None:
            # Archive needed if date_from is before cutoff
            # Live needed (no upper bound means could include recent data)
            return DBTargets(
                use_archive=(date_from < cutoff),
                use_live=True
            )

        # Case 4: Both date_from and date_to specified
        # Archive needed if range starts before cutoff
        # Live needed if range extends to/past cutoff
        return DBTargets(
            use_archive=(date_from < cutoff),
            use_live=(date_to >= cutoff)
        )

    @staticmethod
    def get_connection(use_archive: bool = False, read_only: bool = True) -> sqlite3.Connection:
        """
        Create or reuse a database connection with mtime-based invalidation.

        v7 Enhancement:
        - Thread-local connection caching
        - Auto-reconnect when DB file mtime changes (ERP file replacement scenario)

        Args:
            use_archive: Whether to ATTACH archive DB
            read_only: Use read-only mode (default True for safety)

        Returns:
            sqlite3.Connection with archive attached if requested
        """
        cache_key = f"conn_{use_archive}_{read_only}"
        mtime_key = f"mtime_{use_archive}_{read_only}"

        current_mtime = _get_db_mtime()
        cached_conn = getattr(_local, cache_key, None)
        cached_mtime = getattr(_local, mtime_key, None)

        # Check if cached connection is valid
        if cached_conn is not None and cached_mtime == current_mtime:
            try:
                # Verify connection is still alive
                cached_conn.execute("SELECT 1")
                return cached_conn
            except sqlite3.Error:
                # Connection broken, will create new one
                try:
                    cached_conn.close()
                except Exception:
                    pass

        # Close old connection if mtime changed
        if cached_conn is not None and cached_mtime != current_mtime:
            logger.debug(f"DB mtime changed, reconnecting... (old={cached_mtime}, new={current_mtime})")
            try:
                cached_conn.close()
            except Exception:
                pass

        # Create new connection
        mode = "ro" if read_only else "rw"
        db_uri = f"file:{DB_FILE.absolute()}?mode={mode}"

        conn = sqlite3.connect(db_uri, uri=True, timeout=DB_TIMEOUT)
        conn.row_factory = sqlite3.Row

        # v8: Apply PRAGMA optimizations
        _apply_pragma_settings(conn)

        if use_archive and ARCHIVE_DB_FILE.exists():
            try:
                resolved = attach_archive_safe(conn)
                logger.debug(f"Archive DB attached: {resolved}")
            except (ValueError, FileNotFoundError) as e:
                logger.error(f"Invalid archive database path: {e}")
                raise

        # Cache the connection
        setattr(_local, cache_key, conn)
        setattr(_local, mtime_key, current_mtime)

        # Track for cleanup
        with _connection_lock:
            _all_connections.append(conn)

        return conn

    @staticmethod
    def query(
        sql: str,
        params: list[Any] | tuple[Any, ...] = (),
        use_archive: bool = False
    ) -> list[dict]:
        """
        Execute a query and return results as list of dicts.

        Args:
            sql: SQL query string
            params: Query parameters
            use_archive: Whether archive DB is needed

        Returns:
            List of row dictionaries
        """
        with DBRouter.get_connection(use_archive=use_archive) as conn:
            cur = conn.execute(sql, params)
            rows = cur.fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def build_union_sql(
        select_columns: str,
        where_clause: str,
        targets: DBTargets,
        order_by: str = "production_date DESC, source DESC, id DESC",
        limit: int | None = None,
        include_source: bool = True
    ) -> tuple[str, bool]:
        """
        Build a UNION ALL query for archive and/or live databases.

        Args:
            select_columns: Column list (e.g., "id, production_date, item_code")
            where_clause: WHERE conditions (without WHERE keyword)
            targets: DBTargets indicating which DBs to query
            order_by: ORDER BY clause (default includes source for stable cursor)
            limit: Optional LIMIT value
            include_source: Add 'source' column to distinguish origin DB

        Returns:
            (sql_string, params_doubled): The SQL and whether params need doubling

        Note:
            The 'source' column is included by default for:
            - Debugging (know which DB a row came from)
            - Stable cursor pagination (6.2, 6.3)
        """
        cutoff = ARCHIVE_CUTOFF_DATE

        # Build source column if requested
        source_col_archive = "'archive' AS source, " if include_source else ""
        source_col_live = "'live' AS source, " if include_source else ""

        parts = []
        params_doubled = False

        if targets.use_archive and ARCHIVE_DB_FILE.exists():
            archive_sql = f"SELECT {source_col_archive}{select_columns} FROM archive.production_records WHERE {where_clause} AND production_date < ?"
            parts.append(archive_sql)

        if targets.use_live:
            live_sql = f"SELECT {source_col_live}{select_columns} FROM production_records WHERE {where_clause} AND production_date >= ?"
            parts.append(live_sql)

        if len(parts) == 2:
            final_sql = f"{parts[0]} UNION ALL {parts[1]}"
            params_doubled = True
        elif len(parts) == 1:
            final_sql = parts[0]
        else:
            # Edge case: neither DB selected (shouldn't happen normally)
            logger.warning("build_union_sql called with no target DBs")
            final_sql = f"SELECT {source_col_live}{select_columns} FROM production_records WHERE 1=0"

        if order_by:
            final_sql = f"SELECT * FROM ({final_sql}) ORDER BY {order_by}"

        if limit is not None:
            final_sql += f" LIMIT {int(limit)}"

        return final_sql, params_doubled

    @staticmethod
    def build_query_params(
        base_params: list[Any],
        targets: DBTargets,
        cutoff: str = ARCHIVE_CUTOFF_DATE
    ) -> list[Any]:
        """
        Build the full parameter list for a UNION query.

        Args:
            base_params: Base WHERE clause parameters
            targets: DBTargets indicating which DBs are queried
            cutoff: Cutoff date (passed as parameter, not hardcoded in SQL)

        Returns:
            Complete parameter list with cutoff dates appended
        """
        params = []

        if targets.use_archive and ARCHIVE_DB_FILE.exists():
            params.extend(base_params)
            params.append(cutoff)  # For production_date < ?

        if targets.use_live:
            params.extend(base_params)
            params.append(cutoff)  # For production_date >= ?

        return params

    @staticmethod
    def build_aggregation_sql(
        inner_select: str,
        inner_where: str,
        outer_select: str,
        outer_group_by: str,
        targets: DBTargets,
        outer_order_by: str = "",
        limit: int | None = None
    ) -> tuple[str, bool]:
        """
        Build a "pre-aggregate then merge" query for better performance.

        This follows the optimization from section B.1:
        Instead of UNION ALL then aggregate, we aggregate in each DB first.

        Args:
            inner_select: Columns for inner aggregation
            inner_where: WHERE clause for inner query
            outer_select: Columns for outer aggregation (merge step)
            outer_group_by: GROUP BY for outer query
            targets: DBTargets
            outer_order_by: ORDER BY for final result
            limit: Optional LIMIT

        Returns:
            (sql_string, params_doubled)
        """
        cutoff = ARCHIVE_CUTOFF_DATE
        parts = []
        params_doubled = False

        group_clause = f" GROUP BY {outer_group_by}" if outer_group_by else ""

        if targets.use_archive and ARCHIVE_DB_FILE.exists():
            archive_sql = f"SELECT {inner_select} FROM archive.production_records WHERE {inner_where} AND production_date < ?{group_clause}"
            parts.append(archive_sql)

        if targets.use_live:
            live_sql = f"SELECT {inner_select} FROM production_records WHERE {inner_where} AND production_date >= ?{group_clause}"
            parts.append(live_sql)

        if len(parts) == 2:
            union_sql = f"{parts[0]} UNION ALL {parts[1]}"
            params_doubled = True
        elif len(parts) == 1:
            union_sql = parts[0]
        else:
            union_sql = f"SELECT {inner_select} FROM production_records WHERE 1=0{group_clause}"

        final_sql = f"SELECT {outer_select} FROM ({union_sql}){group_clause}"

        if outer_order_by:
            final_sql += f" ORDER BY {outer_order_by}"

        if limit is not None:
            final_sql += f" LIMIT {int(limit)}"

        return final_sql, params_doubled
