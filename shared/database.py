# shared/database.py
"""
Production Data Hub - Database Routing and Connection Management

Provides:
- DBTargets: Dataclass indicating which DBs to query
- DBRouter: Unified DB connection, routing, and query utilities

Connection pooling, PRAGMA tuning, and the safe ATTACH helper live in
``shared._db_connection`` and ``shared._db_attach`` respectively
(structure-cleanup, 2026-05-27). They are re-exported here so existing
imports keep working.

Key Design:
- pick_targets() returns explicit DBTargets(use_archive, use_live)
- UNION queries include 'source' column for debugging and cursor pagination
- Cutoff date passed as parameter where possible
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from typing import Any

from .config import (
    ARCHIVE_CUTOFF_DATE,
    ARCHIVE_DB_FILE,
    DB_FILE,
    DB_TIMEOUT,
)
from ._db_attach import attach_archive_safe  # noqa: F401 (back-compat)
from ._db_connection import (  # noqa: F401 (back-compat)
    _all_connections,
    _apply_pragma_settings,
    _connection_lock,
    _get_db_mtime,
    _local,
)

logger = logging.getLogger(__name__)


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

        if date_from is None and date_to is None:
            return DBTargets(use_archive=True, use_live=True)

        if date_from is None:
            return DBTargets(
                use_archive=True,
                use_live=(date_to >= cutoff)
            )

        if date_to is None:
            return DBTargets(
                use_archive=(date_from < cutoff),
                use_live=True
            )

        return DBTargets(
            use_archive=(date_from < cutoff),
            use_live=(date_to >= cutoff)
        )

    @staticmethod
    def get_connection(use_archive: bool = False, read_only: bool = True) -> sqlite3.Connection:
        """
        Create or reuse a database connection with mtime-based invalidation.

        Thread-local connection caching with auto-reconnect when the DB file
        mtime changes (ERP file replacement scenario).

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

        if cached_conn is not None and cached_mtime == current_mtime:
            try:
                cached_conn.execute("SELECT 1")
                return cached_conn
            except sqlite3.Error:
                try:
                    cached_conn.close()
                except sqlite3.Error:
                    pass

        if cached_conn is not None and cached_mtime != current_mtime:
            logger.debug(
                f"DB mtime changed, reconnecting... (old={cached_mtime}, new={current_mtime})"
            )
            try:
                cached_conn.close()
            except sqlite3.Error:
                pass

        mode = "ro" if read_only else "rw"
        db_uri = f"file:{DB_FILE.absolute()}?mode={mode}"

        conn = sqlite3.connect(db_uri, uri=True, timeout=DB_TIMEOUT)
        conn.row_factory = sqlite3.Row

        _apply_pragma_settings(conn)

        if use_archive and ARCHIVE_DB_FILE.exists():
            try:
                resolved = attach_archive_safe(conn)
                logger.debug(f"Archive DB attached: {resolved}")
            except (ValueError, FileNotFoundError) as e:
                logger.error(f"Invalid archive database path: {e}")
                raise

        setattr(_local, cache_key, conn)
        setattr(_local, mtime_key, current_mtime)

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
            - Stable cursor pagination
        """
        source_col_archive = "'archive' AS source, " if include_source else ""
        source_col_live = "'live' AS source, " if include_source else ""

        parts = []
        params_doubled = False

        if targets.use_archive and ARCHIVE_DB_FILE.exists():
            archive_sql = (
                f"SELECT {source_col_archive}{select_columns} "
                f"FROM archive.production_records "
                f"WHERE {where_clause} AND production_date < ?"
            )
            parts.append(archive_sql)

        if targets.use_live:
            live_sql = (
                f"SELECT {source_col_live}{select_columns} "
                f"FROM production_records "
                f"WHERE {where_clause} AND production_date >= ?"
            )
            parts.append(live_sql)

        if len(parts) == 2:
            final_sql = f"{parts[0]} UNION ALL {parts[1]}"
            params_doubled = True
        elif len(parts) == 1:
            final_sql = parts[0]
        else:
            logger.warning("build_union_sql called with no target DBs")
            final_sql = (
                f"SELECT {source_col_live}{select_columns} "
                f"FROM production_records WHERE 1=0"
            )

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
        params: list[Any] = []

        if targets.use_archive and ARCHIVE_DB_FILE.exists():
            params.extend(base_params)
            params.append(cutoff)

        if targets.use_live:
            params.extend(base_params)
            params.append(cutoff)

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
        parts = []
        params_doubled = False

        group_clause = f" GROUP BY {outer_group_by}" if outer_group_by else ""

        if targets.use_archive and ARCHIVE_DB_FILE.exists():
            archive_sql = (
                f"SELECT {inner_select} FROM archive.production_records "
                f"WHERE {inner_where} AND production_date < ?{group_clause}"
            )
            parts.append(archive_sql)

        if targets.use_live:
            live_sql = (
                f"SELECT {inner_select} FROM production_records "
                f"WHERE {inner_where} AND production_date >= ?{group_clause}"
            )
            parts.append(live_sql)

        if len(parts) == 2:
            union_sql = f"{parts[0]} UNION ALL {parts[1]}"
            params_doubled = True
        elif len(parts) == 1:
            union_sql = parts[0]
        else:
            union_sql = (
                f"SELECT {inner_select} FROM production_records "
                f"WHERE 1=0{group_clause}"
            )

        final_sql = f"SELECT {outer_select} FROM ({union_sql}){group_clause}"

        if outer_order_by:
            final_sql += f" ORDER BY {outer_order_by}"

        if limit is not None:
            final_sql += f" LIMIT {int(limit)}"

        return final_sql, params_doubled
