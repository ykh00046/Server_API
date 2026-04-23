"""Helper tests: attach_archive_safe whitelist enforcement and bind fallback.

Covers `shared.database.attach_archive_safe` introduced in security-hardening-v3.
"""
from __future__ import annotations

import sqlite3

import pytest

from shared.database import attach_archive_safe


def test_rejects_non_whitelisted_path(tmp_path):
    """Path that exists but is not in the whitelist should raise ValueError."""
    fake = tmp_path / "fake.db"
    fake.write_bytes(b"")  # exists
    other = tmp_path / "other.db"
    other.write_bytes(b"")
    # uri=True is required for ATTACH to accept URI-form paths (matches production).
    conn = sqlite3.connect("file::memory:?cache=shared", uri=True)
    try:
        with pytest.raises(ValueError, match="not in whitelist"):
            attach_archive_safe(conn, archive_path=fake, whitelist=(other.resolve(),))
    finally:
        conn.close()


def test_rejects_missing_file(tmp_path):
    """Whitelisted but non-existent path raises FileNotFoundError."""
    # uri=True is required for ATTACH to accept URI-form paths (matches production).
    conn = sqlite3.connect("file::memory:?cache=shared", uri=True)
    missing = tmp_path / "missing.db"
    try:
        with pytest.raises(FileNotFoundError):
            attach_archive_safe(conn, archive_path=missing, whitelist=(missing.resolve(),))
    finally:
        conn.close()


def test_attaches_valid_archive(tmp_path):
    """Whitelisted, existing archive is attached under the requested alias."""
    archive = tmp_path / "archive.db"
    sqlite3.connect(archive).close()  # create empty db file

    # uri=True is required for ATTACH to accept URI-form paths (matches production).
    conn = sqlite3.connect("file::memory:?cache=shared", uri=True)
    try:
        resolved = attach_archive_safe(
            conn, archive_path=archive, whitelist=(archive.resolve(),)
        )
        assert resolved == archive.resolve()

        rows = list(conn.execute("PRAGMA database_list"))
        aliases = [r[1] for r in rows]
        assert "archive" in aliases
    finally:
        conn.close()


def test_custom_alias(tmp_path):
    """Custom alias parameter is honored."""
    archive = tmp_path / "snap.db"
    sqlite3.connect(archive).close()

    # uri=True is required for ATTACH to accept URI-form paths (matches production).
    conn = sqlite3.connect("file::memory:?cache=shared", uri=True)
    try:
        attach_archive_safe(
            conn,
            archive_path=archive,
            whitelist=(archive.resolve(),),
            alias="snap2025",
        )
        rows = list(conn.execute("PRAGMA database_list"))
        aliases = [r[1] for r in rows]
        assert "snap2025" in aliases
    finally:
        conn.close()
