# tests/test_archive_whitelist.py
"""Archive DB whitelist and path validation tests."""

import pytest

from shared.validators import validate_db_path, resolve_archive_db


def test_validate_db_path_rejects_quotes():
    with pytest.raises(ValueError):
        validate_db_path("a'b.db")
    with pytest.raises(ValueError):
        validate_db_path('a"b.db')


def test_validate_db_path_rejects_nul_and_control():
    with pytest.raises(ValueError):
        validate_db_path("file\x00.db")
    with pytest.raises(ValueError):
        validate_db_path("file\n.db")


def test_validate_db_path_rejects_empty():
    with pytest.raises(ValueError):
        validate_db_path("")


def test_validate_db_path_accepts_posix():
    assert validate_db_path("/tmp/archive_2025.db") is True


def test_validate_db_path_accepts_windows():
    assert validate_db_path("C:/X/Server_API/database/archive_2025.db") is True


def test_resolve_archive_db_rejects_unlisted(tmp_path):
    allowed = tmp_path / "allowed.db"
    allowed.write_bytes(b"")
    intruder = tmp_path / "evil.db"
    intruder.write_bytes(b"")
    with pytest.raises(ValueError):
        resolve_archive_db(intruder, (allowed,))


def test_resolve_archive_db_accepts_listed(tmp_path):
    allowed = tmp_path / "allowed.db"
    allowed.write_bytes(b"")
    got = resolve_archive_db(allowed, (allowed,))
    assert got == allowed.resolve()


def test_resolve_archive_db_rejects_missing(tmp_path):
    ghost = tmp_path / "ghost.db"
    with pytest.raises(FileNotFoundError):
        resolve_archive_db(ghost, (ghost,))


def test_resolve_archive_db_rejects_relative_traversal(tmp_path):
    # Attempt traversal: ../ghost
    allowed = tmp_path / "allowed.db"
    allowed.write_bytes(b"")
    traversal = tmp_path / "sub" / ".." / "allowed.db"
    # Traversal resolves to the allowed path, so it should be accepted.
    got = resolve_archive_db(traversal, (allowed,))
    assert got == allowed.resolve()
    # But an unrelated path must fail.
    with pytest.raises(ValueError):
        resolve_archive_db(tmp_path / "other.db", (allowed,))


def test_missing_whitelist_entry_logs_warning(monkeypatch, caplog, tmp_path):
    """FR-04: import-time warning when a whitelisted path does not exist."""
    import importlib
    import logging
    missing = tmp_path / "does_not_exist.db"
    monkeypatch.setenv("ARCHIVE_DB_WHITELIST", str(missing))
    import shared.config as cfg
    with caplog.at_level(logging.WARNING, logger="shared.config"):
        importlib.reload(cfg)
    try:
        assert any(
            "not found at import" in rec.getMessage() for rec in caplog.records
        ), caplog.text
    finally:
        monkeypatch.delenv("ARCHIVE_DB_WHITELIST", raising=False)
        importlib.reload(cfg)
