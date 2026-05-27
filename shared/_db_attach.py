"""Safe ATTACH helper for the archive SQLite DB.

Extracted from shared/database.py (structure-cleanup, 2026-05-27) so the
attach pattern lives in one small file shared by both DBRouter and the
ad-hoc custom-query tool path. The public symbol `attach_archive_safe`
is re-exported from `shared.database` for backwards compatibility.
"""
from __future__ import annotations

import os
import sqlite3

from .config import ARCHIVE_DB_FILE, ARCHIVE_DB_WHITELIST
from .validators import resolve_archive_db


def attach_archive_safe(
    conn: sqlite3.Connection,
    archive_path: "str | os.PathLike | None" = None,
    *,
    alias: str = "archive",
    whitelist: "tuple | None" = None,
):
    """ATTACH archive DB safely (whitelist + bind-first + ro mode).

    Used by both ``DBRouter.get_connection()`` and
    ``api/tools.execute_custom_query`` to keep the path-validation + ATTACH
    pattern in one place.

    Args:
        conn: Active sqlite3 connection (any mode).
        archive_path: Requested archive DB path. Defaults to ARCHIVE_DB_FILE.
        alias: Schema alias used in ``ATTACH ... AS <alias>``. Internal
            constant only.
        whitelist: Allowed paths. Defaults to ARCHIVE_DB_WHITELIST from
            config.

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
        # Safe because archive_uri came from resolve_archive_db
        # (whitelist-validated) and `alias` is an internal constant, never
        # user input.
        conn.execute(f"ATTACH DATABASE '{archive_uri}' AS {alias}")
    return resolved
