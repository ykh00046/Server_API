# tests/test_backup_db.py
"""Unit tests for tools/backup_db.py.

Every DB path and the backup directory are redirected to tmp_path; the tool
never sees the real database/ folder. Stabilization is stubbed out (it only
sleeps) so the tests run fast; sqlite backup and quick_check run for real.
"""

import os
import sqlite3
import sys

import pytest

from tools import backup_db as bd


def _make_db(path, value="x"):
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    conn.execute("INSERT INTO t (v) VALUES (?)", (value,))
    conn.commit()
    conn.close()


def _read_values(path):
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return [r[0] for r in conn.execute("SELECT v FROM t ORDER BY id")]
    finally:
        conn.close()


@pytest.fixture
def env(tmp_path, monkeypatch):
    """All five DB paths + BACKUP_DIR under tmp_path; nothing created yet."""
    src = tmp_path / "db"
    src.mkdir()
    paths = {
        "DB_FILE": src / "production_analysis.db",
        "ARCHIVE_DB_FILE": src / "archive_2025.db",
        "MATERIALS_DB_FILE": src / "materials.db",
        "NOTIFICATIONS_DB_FILE": src / "notifications.db",
        "ANOMALY_DB_FILE": src / "anomaly.db",
    }
    for name, p in paths.items():
        monkeypatch.setattr(bd, name, p)
    backup_dir = tmp_path / "backups"
    monkeypatch.setattr(bd, "BACKUP_DIR", backup_dir)
    monkeypatch.setattr(bd, "wait_for_stabilization", lambda _p: True)
    return paths, backup_dir


def _run_main(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["backup_db.py", *argv])
    return bd.main()


# ==========================================================
# run_backup
# ==========================================================
def test_run_backup_produces_verifiable_copy(env):
    paths, backup_dir = env
    _make_db(paths["DB_FILE"], "hello")

    assert bd.run_backup(paths["DB_FILE"], "production", 30) is True

    backups = list(backup_dir.glob("production_*.db"))
    assert len(backups) == 1
    assert bd.verify_backup(backups[0]) is True
    assert _read_values(backups[0]) == ["hello"]


def test_run_backup_missing_source_returns_false(env):
    paths, backup_dir = env
    assert bd.run_backup(paths["DB_FILE"], "production", 30) is False
    assert not backup_dir.exists() or not any(backup_dir.iterdir())


def test_backup_failing_verification_is_removed(env, monkeypatch):
    paths, backup_dir = env
    _make_db(paths["MATERIALS_DB_FILE"])

    def _write_garbage(_source, backup_path):
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        backup_path.write_bytes(b"this is not a sqlite database" * 100)
        return True

    monkeypatch.setattr(bd, "backup_database", _write_garbage)

    assert bd.run_backup(paths["MATERIALS_DB_FILE"], "materials", 30) is False
    assert list(backup_dir.glob("materials_*.db")) == []


# ==========================================================
# cleanup_old_backups
# ==========================================================
def test_cleanup_removes_only_oldest_of_matching_prefix(env):
    _paths, backup_dir = env
    backup_dir.mkdir()
    prod = []
    for i in range(5):
        p = backup_dir / f"production_2026010{i}_000000.db"
        p.write_bytes(b"")
        os.utime(p, (1_000_000 + i * 100, 1_000_000 + i * 100))
        prod.append(p)
    # Other prefixes, all OLDER than every production file.
    others = [
        backup_dir / "archive_2025_20250101_000000.db",
        backup_dir / "materials_20250101_000000.db",
        backup_dir / "notifications_20250101_000000.db",
    ]
    for p in others:
        p.write_bytes(b"")
        os.utime(p, (1, 1))

    bd.cleanup_old_backups("production", 2)

    assert [p.exists() for p in prod] == [False, False, False, True, True]
    assert all(p.exists() for p in others)


def test_cleanup_within_retention_keeps_everything(env):
    _paths, backup_dir = env
    backup_dir.mkdir()
    files = [backup_dir / f"anomaly_2026010{i}_000000.db" for i in range(3)]
    for p in files:
        p.write_bytes(b"")
    bd.cleanup_old_backups("anomaly", 3)
    assert all(p.exists() for p in files)


# ==========================================================
# main()
# ==========================================================
def test_main_backs_up_all_five_dbs(env, monkeypatch):
    paths, backup_dir = env
    for p in paths.values():
        _make_db(p)

    assert _run_main(monkeypatch) == 0

    for prefix in ("production", "archive_2025", "materials", "notifications", "anomaly"):
        found = list(backup_dir.glob(f"{prefix}_*.db"))
        assert len(found) == 1, prefix
        assert bd.verify_backup(found[0]) is True
    # archive_2025_*.db must not be swept up by another prefix's glob.
    assert len(list(backup_dir.glob("*.db"))) == 5


def test_main_skips_missing_app_dbs_without_failing(env, monkeypatch, capsys):
    paths, backup_dir = env
    _make_db(paths["DB_FILE"])
    _make_db(paths["ARCHIVE_DB_FILE"])
    _make_db(paths["NOTIFICATIONS_DB_FILE"])
    # materials.db and anomaly.db are absent on this "machine".

    assert _run_main(monkeypatch) == 0

    out = capsys.readouterr().out
    assert "Skipping Materials DB - not present on this machine" in out
    assert "Skipping Anomaly DB - not present on this machine" in out
    assert "Backup Summary: 3 success, 0 failed, 2 skipped" in out
    assert len(list(backup_dir.glob("notifications_*.db"))) == 1
    assert list(backup_dir.glob("materials_*.db")) == []
    assert list(backup_dir.glob("anomaly_*.db")) == []


def test_main_missing_live_db_still_fails(env, monkeypatch):
    """Existing behaviour kept: a missing production DB is a failure."""
    paths, _backup_dir = env
    _make_db(paths["ARCHIVE_DB_FILE"])
    assert _run_main(monkeypatch) == 1


def test_main_live_flag_keeps_old_scope(env, monkeypatch):
    paths, backup_dir = env
    for p in paths.values():
        _make_db(p)

    assert _run_main(monkeypatch, "--live") == 0

    names = sorted(p.name.split("_")[0] for p in backup_dir.glob("*.db"))
    assert names == ["production"]


def test_main_failed_app_backup_counts_as_failure(env, monkeypatch):
    paths, _backup_dir = env
    for p in paths.values():
        _make_db(p)
    real_run_backup = bd.run_backup

    def _fail_anomaly(db_path, prefix, retention):
        if prefix == "anomaly":
            return False
        return real_run_backup(db_path, prefix, retention)

    monkeypatch.setattr(bd, "run_backup", _fail_anomaly)
    assert _run_main(monkeypatch) == 1


def _snapshot(directory):
    return {p.name: p.read_bytes() for p in sorted(directory.iterdir())}


# ==========================================================
# WAL-mode sources and sidecar files
# ==========================================================
@pytest.fixture
def wal_source(env):
    """A WAL-mode materials DB with an open writer; rows stay in the -wal."""
    paths, _backup_dir = env
    src = paths["MATERIALS_DB_FILE"]
    writer = sqlite3.connect(str(src))
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("PRAGMA wal_autocheckpoint=0")
    writer.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    writer.executemany("INSERT INTO t (v) VALUES (?)", [(f"r{i}",) for i in range(200)])
    writer.commit()
    yield src, writer
    writer.close()


def test_wal_source_backup_is_single_complete_file(env, wal_source):
    _paths, backup_dir = env
    src, _writer = wal_source
    # Precondition: the committed rows are only in the source's WAL.
    assert (src.parent / (src.name + "-wal")).stat().st_size > 0

    assert bd.run_backup(src, "materials", 30) is True

    names = sorted(p.name for p in backup_dir.iterdir())
    assert len(names) == 1 and names[0].startswith("materials_")
    assert names[0].endswith(".db")
    backup = backup_dir / names[0]
    assert backup.read_bytes()[18:20] == b"\x01\x01"  # rollback, not WAL
    assert bd.verify_backup(backup) is True
    assert _read_values(backup) == [f"r{i}" for i in range(200)]
    # Opening/verifying the finished backup leaves nothing beside it.
    assert sorted(p.name for p in backup_dir.iterdir()) == names


def test_backup_leaves_wal_source_unchanged(env, wal_source):
    """The database file and its -wal are byte-identical afterwards and no
    file is added or removed. The -shm is excluded from the byte compare:
    any SQLite reader (also a read-only one) updates its read-mark slots in
    that shared-memory index; it holds no database content."""
    src, writer = wal_source

    def _content(snap):
        return {k: v for k, v in snap.items() if not k.endswith("-shm")}

    before = _snapshot(src.parent)

    assert bd.run_backup(src, "materials", 30) is True

    after = _snapshot(src.parent)
    assert sorted(after) == sorted(before)
    assert _content(after) == _content(before)
    assert writer.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert [r[0] for r in writer.execute("SELECT v FROM t ORDER BY id")] == [
        f"r{i}" for i in range(200)
    ]


def test_cleanup_removes_sidecars_of_deleted_backups(env):
    _paths, backup_dir = env
    backup_dir.mkdir()
    old = backup_dir / "production_20260101_000000.db"
    new = backup_dir / "production_20260102_000000.db"
    for i, p in enumerate((old, new)):
        p.write_bytes(b"db")
        os.utime(p, (1_000_000 + i, 1_000_000 + i))
    (backup_dir / (old.name + "-shm")).write_bytes(b"\0" * 32768)
    (backup_dir / (old.name + "-wal")).write_bytes(b"")

    bd.cleanup_old_backups("production", 1)

    assert sorted(p.name for p in backup_dir.iterdir()) == [new.name]


def test_cleanup_removes_stale_sidecars_and_touches_nothing_else(env):
    _paths, backup_dir = env
    backup_dir.mkdir()
    kept = backup_dir / "production_20260101_000000.db"
    kept.write_bytes(b"kept backup bytes")
    kept_full_wal = backup_dir / "production_20260102_000000.db"
    kept_full_wal.write_bytes(b"other kept backup")
    stale = [
        backup_dir / (kept.name + "-shm"),
        backup_dir / (kept.name + "-wal"),  # empty
        backup_dir / (kept_full_wal.name + "-shm"),
        backup_dir / "production_20251231_000000.db-shm",  # orphan
        backup_dir / "production_20251231_000000.db-wal",  # orphan
    ]
    for p in stale:
        p.write_bytes(b"\0" * 32768 if p.name.endswith("-shm") else b"")
    nonempty_wal = backup_dir / (kept_full_wal.name + "-wal")
    nonempty_wal.write_bytes(b"x" * 100)
    untouched = [
        backup_dir / "materials_20260101_000000.db-shm",  # other prefix
        backup_dir / "materials_20260101_000000.db-wal",
        backup_dir / "archive_2025_20260101_000000.db-shm",
        backup_dir / "production_manual.db-wal",  # not the tool's naming
        backup_dir / "production_20260101_000000.db-journal",
        backup_dir / "notes.txt",
    ]
    for p in untouched:
        p.write_bytes(b"keep")
    dbs_before = {p: p.read_bytes() for p in (kept, kept_full_wal)}

    bd.cleanup_old_backups("production", 30)

    assert not any(p.exists() for p in stale)
    assert nonempty_wal.read_bytes() == b"x" * 100
    assert all(p.read_bytes() == b"keep" for p in untouched)
    assert {p: p.read_bytes() for p in dbs_before} == dbs_before


def test_failed_verification_removes_backup_and_sidecars(env, monkeypatch):
    """A WAL-mode copy is rejected before it is opened; it and any
    sidecars are removed."""
    paths, backup_dir = env
    src = paths["ANOMALY_DB_FILE"]
    conn = sqlite3.connect(str(src))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    conn.commit()
    conn.close()  # header stays WAL (bytes 18/19 == 2)

    def _raw_copy_with_sidecars(source, backup_path):
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        backup_path.write_bytes(source.read_bytes())
        (backup_path.parent / (backup_path.name + "-wal")).write_bytes(b"")
        (backup_path.parent / (backup_path.name + "-shm")).write_bytes(b"\0" * 32768)
        return True

    monkeypatch.setattr(bd, "backup_database", _raw_copy_with_sidecars)

    assert bd.run_backup(src, "anomaly", 30) is False
    assert list(backup_dir.iterdir()) == []


def test_main_cleanup_covers_app_prefixes(env, monkeypatch):
    _paths, backup_dir = env
    monkeypatch.setattr(bd, "APP_BACKUP_RETENTION", 1)
    backup_dir.mkdir()
    old = backup_dir / "materials_20260101_000000.db"
    new = backup_dir / "materials_20260102_000000.db"
    for i, p in enumerate((old, new)):
        p.write_bytes(b"")
        os.utime(p, (1_000_000 + i, 1_000_000 + i))

    assert _run_main(monkeypatch, "--cleanup") == 0
    assert not old.exists()
    assert new.exists()
