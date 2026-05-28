"""AI tool — execute_custom_query (free-form SELECT).

Note: Do NOT use 'from __future__ import annotations' here.
Gemini SDK requires actual type hints, not stringified ones.
"""

import re
from typing import Dict, Any

from shared import (
    DBRouter,
    DBTargets,
    get_logger,
)
from shared.database import attach_archive_safe
from shared.logging_config import QueryLogger

logger = get_logger(__name__)


def _strip_sql_comments(sql: str) -> str:
    """Remove SQL comments (block and line) to prevent validation bypass."""
    sql = re.sub(r'/\*.*?\*/', ' ', sql, flags=re.DOTALL)  # block comments
    sql = re.sub(r'--[^\n]*', ' ', sql)                      # line comments
    return sql.strip()


def _validate_custom_query_params(params) -> tuple:
    """Validate execute_custom_query params input.

    Accepts None or list[str]. Returns a tuple suitable for sqlite3 bind.
    Any other type or non-string element raises ValueError.

    Why str-only: Gemini tool schema stays simple (list[str] has trivial
    representation), and SQLite dynamic typing auto-casts string values to
    the column's native type for comparison. Clients must convert numbers
    to strings ("1000") before passing — explicit over ambiguous union types.
    """
    if params is None:
        return ()
    if not isinstance(params, list):
        raise ValueError(
            f"params must be a list or None (got {type(params).__name__})"
        )
    for i, p in enumerate(params):
        if not isinstance(p, str):
            raise ValueError(
                f"params[{i}] must be a string (got {type(p).__name__}); "
                f"convert numbers to str - SQLite auto-casts for comparison"
            )
    return tuple(params)


def execute_custom_query(
    sql: str,
    params: list[str] | None = None,
    description: str = ""
) -> Dict[str, Any]:
    """
    Execute a custom SQL query for flexible data analysis.
    Use this tool when other tools cannot handle complex filtering conditions
    (e.g., lot_number patterns, multiple conditions, custom aggregations).

    IMPORTANT RULES:
    - Only SELECT queries are allowed (database is read-only)
    - Only 'production_records' table is available (use 'archive.production_records' for pre-2026)
    - Available columns: production_date, item_code, item_name, good_quantity, lot_number
    - Always include LIMIT clause (max 1000 rows)
    - **Use ? placeholders + params for any values (SQL injection safe)**
    - For date ranges spanning multiple years, use UNION ALL with archive.production_records

    Args:
        sql: The SELECT SQL query. Use ? for each parameter, e.g. "... WHERE item_code = ?".
        params: List of string values bound to ? placeholders in order. Optional (default: None).
            All values must be strings; SQLite dynamically casts for numeric comparisons.
            Example: params=["BW0021", "2026-01-01", "1000"].
        description: Brief description of what this query does (for logging only).

    Returns:
        Dict with query results or error message.

    Example queries:
        - sql="SELECT SUM(good_quantity) as total FROM production_records WHERE item_code = ? AND production_date >= ?"
          params=["BW0021", "2026-01-20"]
        - sql="SELECT lot_number, SUM(good_quantity) as qty FROM production_records WHERE item_code = ? GROUP BY lot_number ORDER BY qty DESC LIMIT 10"
          params=["ABC001"]
    """
    import sqlite3
    import threading
    from shared.config import (
        DB_FILE,
        DB_TIMEOUT,
        CUSTOM_QUERY_TIMEOUT_SEC,
    )
    from shared.database import _apply_pragma_settings

    try:
        # Validate bind parameters first (fast-fail before SQL parsing)
        try:
            bound_params = _validate_custom_query_params(params)
        except ValueError as e:
            return {
                "status": "error",
                "code": "INVALID_PARAMS",
                "message": str(e),
            }

        # Strip SQL comments before any validation (prevent bypass via comments)
        sql_clean = _strip_sql_comments(sql.strip())
        sql_upper = sql_clean.upper()

        # Validation 1: No semicolons (prevent multi-statement execution)
        if ";" in sql_clean:
            return {
                "status": "error",
                "message": "Multiple statements are not allowed (semicolon detected)."
            }

        # Validation 2: SELECT only (checked after comment stripping)
        if not sql_upper.startswith("SELECT"):
            return {
                "status": "error",
                "message": "Only SELECT queries are allowed."
            }

        # Validation 3: No dangerous keywords (extra safety layer)
        # Word-boundary check prevents false positives (e.g. LAST_UPDATED matching UPDATE)
        _forbidden_words = [
            "DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE",
            "CREATE", "REPLACE", "PRAGMA", "ATTACH", "DETACH", "VACUUM", "REINDEX",
            "EXECUTE", "SYSTEM", "SCRIPT", "JAVASCRIPT", "EVAL",
        ]
        _forbidden_substrings = ["LOAD_EXTENSION", "SQLITE_", "EXEC("]
        for word in _forbidden_words:
            if re.search(r'\b' + word + r'\b', sql_upper):
                return {
                    "status": "error",
                    "message": f"Forbidden keyword detected: {word}"
                }
        for pat in _forbidden_substrings:
            if pat in sql_upper:
                return {
                    "status": "error",
                    "message": f"Forbidden keyword detected: {pat}"
                }

        # Validation 4: Must reference production_records
        if "PRODUCTION_RECORDS" not in sql_upper:
            return {
                "status": "error",
                "message": "Query must reference 'production_records' table."
            }

        # Add LIMIT if not present
        if "LIMIT" not in sql_upper:
            sql_clean = sql_clean + " LIMIT 1000"

        # Determine if archive is needed
        use_archive = "ARCHIVE.PRODUCTION_RECORDS" in sql_upper

        with QueryLogger("custom_query", DBTargets(use_archive=use_archive, use_live=True), logger) as ql:
            ql.add_info("description", description or "custom query")

            # Execute with timeout (CUSTOM_QUERY_TIMEOUT_SEC).
            # Dedicated connection required for conn.interrupt() — cannot use thread-local cache.
            # Apply PRAGMA settings so custom queries get same perf as regular API queries.
            # check_same_thread=False: conn is created on the main thread but
            # run_query executes on a worker thread. mode=ro makes write-race
            # concerns moot, so cross-thread use is safe here.
            db_uri = f"file:{DB_FILE.absolute()}?mode=ro"
            conn = sqlite3.connect(
                db_uri, uri=True, timeout=DB_TIMEOUT, check_same_thread=False
            )
            conn.row_factory = sqlite3.Row
            _apply_pragma_settings(conn)

            if use_archive:
                # Whitelist-enforced ATTACH via shared helper (security-hardening-v3)
                try:
                    attach_archive_safe(conn)
                except (ValueError, FileNotFoundError) as e:
                    conn.close()
                    return {
                        "status": "error",
                        "code": "INVALID_ARCHIVE_PATH",
                        "message": f"Invalid archive DB: {e}",
                    }

            result = {"rows": [], "error": None}

            def run_query(connection):
                try:
                    cursor = connection.execute(sql_clean, bound_params)
                    rows = cursor.fetchall()
                    result["rows"] = [dict(r) for r in rows]
                    result["columns"] = [desc[0] for desc in cursor.description] if cursor.description else []
                except sqlite3.Error as e:  # noqa: BLE001 — Gemini tool boundary: 모든 예외를 error로 변환 (LLM 계약)
                    result["error"] = str(e)
                    logger.exception("[custom_query] run_query failed")

            # daemon=True: if run_query gets stuck past timeout + 1s grace, the
            # thread must not keep the Python process alive. Connection is left
            # for GC rather than explicit close() to avoid a cross-thread
            # close/execute race (M-NEW-1, custom-query-thread-safety).
            thread = threading.Thread(target=run_query, args=(conn,), daemon=True)
            thread.start()
            thread.join(timeout=CUSTOM_QUERY_TIMEOUT_SEC)

            if thread.is_alive():
                conn.interrupt()  # Cancel the running SQLite query
                thread.join(timeout=1.0)
                # Do NOT close conn here — run_query may still be in C-level
                # fetchall(). Daemon thread exits with process; GC releases conn.
                logger.warning(
                    f"[custom_query] timeout after {CUSTOM_QUERY_TIMEOUT_SEC}s; "
                    f"leaked connection pending GC (daemon thread still alive)"
                )
                return {
                    "status": "error",
                    "code": "QUERY_TIMEOUT",
                    "message": f"Query timeout (exceeded {CUSTOM_QUERY_TIMEOUT_SEC:.0f} seconds). Please simplify your query."
                }

            conn.close()

            if result["error"]:
                ql.set_row_count(0)
                logger.error(f"[Tool Error] execute_custom_query failed: {result['error']}")
                return {
                    "status": "error",
                    "message": result["error"]
                }

            ql.set_row_count(len(result["rows"]))

        logger.info(f"[Tool] execute_custom_query: {description or 'custom'} rows={len(result['rows'])}")
        return {
            "status": "success",
            "description": description,
            "row_count": len(result["rows"]),
            "columns": result["columns"],
            "data": result["rows"]
        }

    except Exception as e:  # noqa: BLE001 — Gemini tool boundary: 모든 예외를 error dict로 변환 (LLM 계약)
        logger.exception(f"[Tool Error] execute_custom_query failed: {str(e)}")
        return {"status": "error", "message": str(e)}
