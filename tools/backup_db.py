# tools/backup_db.py
"""
Production Data Hub - Database Backup Script

Features (Section 6.2):
- Wait for mtime stabilization before backup (prevents corrupted backups)
- Use sqlite3 backup API for safe copying
- PRAGMA quick_check validation after backup
- Retention policy (counted in files, not days): latest 30 backups for Live DB,
  latest 12 for Archive DB, latest 30 for each app DB (materials,
  notifications, anomaly). Run daily, that is 30 / 12 / 30 days.
- App DBs that do not exist on this machine are skipped (not a failure)
- Optional mirror: BACKUP_MIRROR_DIR (.env) or --mirror-dir copies each
  verified backup into a second directory (e.g. another disk), verifies the
  copy and applies the same retention there. A mirror failure keeps the
  primary backup but makes the exit code 1. Unset/empty = off.

Usage:
    python tools/backup_db.py              # Backup all DBs (Live, Archive, app DBs)
    python tools/backup_db.py --live       # Backup Live DB only
    python tools/backup_db.py --archive    # Backup Archive DB only
    python tools/backup_db.py --cleanup    # Only run cleanup (no backup)
    python tools/backup_db.py --mirror-dir PATH  # Also mirror to PATH

Can be scheduled via Windows Task Scheduler for automated daily backups.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory for shared imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import contextlib

from shared import ARCHIVE_DB_FILE, DATABASE_DIR, DB_FILE, DB_TIMEOUT
from shared.config import (
    ANOMALY_DB_FILE,
    BACKUP_MIRROR_DIR,
    MATERIALS_DB_FILE,
    NOTIFICATIONS_DB_FILE,
)
from shared.db_maintenance import wait_for_stabilization

# ==========================================================
# Configuration
# ==========================================================
BACKUP_DIR = DATABASE_DIR / "backups"

# Retention policy
LIVE_BACKUP_RETENTION = 30  # Keep the latest 30 backups (30 days when run daily)
ARCHIVE_BACKUP_RETENTION = 12  # Keep the latest 12 backups (12 days when run daily)
APP_BACKUP_RETENTION = 30  # Keep last 30 backups of each app DB

# Mirror copies are written as ".<name>.partial" first, renamed when verified.
PARTIAL_SUFFIX = ".partial"


# ==========================================================
# Logging (Simple stdout for script usage)
# ==========================================================
def log(level: str, msg: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {msg}")


def backup_database(source_path: Path, backup_path: Path) -> bool:
    """
    Backup a SQLite database using the backup API.
    Returns True on success, False on failure.
    """
    source_conn = None
    backup_conn = None
    try:
        log("INFO", f"Starting backup: {source_path.name} -> {backup_path.name}")

        # Ensure backup directory exists
        backup_path.parent.mkdir(parents=True, exist_ok=True)

        # Open source database (read-only)
        source_conn = sqlite3.connect(
            f"file:{source_path}?mode=ro",
            uri=True,
            timeout=DB_TIMEOUT
        )

        # Create new backup database
        backup_conn = sqlite3.connect(str(backup_path), timeout=DB_TIMEOUT)

        # Use SQLite backup API
        source_conn.backup(backup_conn)

        # The backup API copies page 1 verbatim, so a WAL-mode source yields a
        # copy whose header says WAL. Any later open of that copy (even
        # read-only verification) then creates -wal/-shm beside it, and a
        # read-only connection cannot remove them on close. Switch the COPY
        # (never the source) to rollback mode: SQLite checkpoints fully and
        # only then rewrites the header, and refuses (returns "wal") if it
        # cannot, so the result is one self-contained .db file.
        mode = backup_conn.execute("PRAGMA journal_mode=DELETE").fetchone()
        if not mode or str(mode[0]).lower() != "delete":
            raise sqlite3.OperationalError(
                f"could not set backup journal_mode=DELETE (got {mode})"
            )

        log("INFO", f"Backup created: {backup_path}")
        return True

    except sqlite3.Error as e:
        log("ERROR", f"SQLite error during backup: {e}")
        # Close BEFORE unlink — Windows cannot delete an open file
        # (WinError 32), which left corrupt partial backups in retention.
        _close_quietly(backup_conn)
        backup_conn = None
        _remove_backup_files(backup_path)
        return False

    except OSError as e:
        log("ERROR", f"Unexpected error during backup: {e}")
        return False

    finally:
        _close_quietly(source_conn)
        _close_quietly(backup_conn)


def _close_quietly(conn: sqlite3.Connection | None) -> None:
    if conn is not None:
        with contextlib.suppress(sqlite3.Error):
            conn.close()


# SQLite sidecar files that an open of a WAL-mode file leaves next to it.
SIDECAR_SUFFIXES = ("-wal", "-shm")


def _sidecars(db_path: Path) -> list[Path]:
    return [db_path.with_name(db_path.name + s) for s in SIDECAR_SUFFIXES]


def _remove_backup_files(backup_path: Path) -> None:
    """Delete a backup and its sidecars (best effort)."""
    for p in (backup_path, *_sidecars(backup_path)):
        if p.exists():
            with contextlib.suppress(OSError):
                p.unlink()


def _is_wal_header(path: Path) -> bool:
    """True if the SQLite header says WAL (bytes 18/19 == 2)."""
    try:
        with open(path, "rb") as f:
            header = f.read(20)
    except OSError:
        return False
    return len(header) == 20 and header[:16] == b"SQLite format 3\x00" and (
        header[18] == 2 or header[19] == 2
    )


def verify_backup(backup_path: Path) -> bool:
    """
    Verify backup integrity using PRAGMA quick_check.
    Returns True if valid, False otherwise.
    """
    conn = None
    try:
        log("INFO", f"Verifying backup: {backup_path.name}")

        # A backup must not depend on a -wal file. Reject a WAL-mode copy
        # before opening it, so verification itself never creates sidecars.
        if _is_wal_header(backup_path):
            log("ERROR", f"Backup verification failed: {backup_path.name} is in WAL mode")
            return False

        conn = sqlite3.connect(
            f"file:{backup_path}?mode=ro",
            uri=True,
            timeout=DB_TIMEOUT
        )
        cursor = conn.cursor()
        cursor.execute("PRAGMA quick_check;")
        result = cursor.fetchone()
        conn.close()
        conn = None

        if result and result[0] == "ok":
            log("INFO", f"Backup verification passed: {backup_path.name}")
            return True
        else:
            log("ERROR", f"Backup verification failed: {result}")
            return False

    except sqlite3.Error as e:
        log("ERROR", f"Error verifying backup: {e}")
        return False
    finally:
        _close_quietly(conn)


def cleanup_old_backups(prefix: str, retention: int, directory: Path | None = None):
    """
    Remove old backups exceeding retention policy.
    Keeps the most recent 'retention' number of backups matching the prefix.
    `directory` defaults to BACKUP_DIR (the mirror directory passes its own).
    """
    directory = BACKUP_DIR if directory is None else directory
    if not directory.exists():
        return

    # Find all backups matching prefix. Only this tool's own file names
    # (<prefix>_YYYYMMDD_HHMMSS.db) count: a hand-made copy such as
    # production_analysis.db in the same folder (likely in a mirror directory
    # that already holds manual copies) must never be deleted by retention.
    own_name = re.compile(rf"^{re.escape(prefix)}_\d{{8}}_\d{{6}}\.db$")
    backups = sorted(
        (p for p in directory.glob(f"{prefix}_*.db") if own_name.match(p.name)),
        key=lambda p: p.stat().st_mtime,
        reverse=True  # Newest first
    )

    if len(backups) <= retention:
        log(
            "INFO",
            f"Cleanup: {len(backups)} backups found, retention={retention}. No cleanup needed.",
        )
    else:
        # Remove old backups (and their sidecars once the .db itself is gone)
        to_remove = backups[retention:]
        for backup in to_remove:
            try:
                backup.unlink()
                log("INFO", f"Removed old backup: {backup.name}")
            except OSError as e:
                log("WARN", f"Failed to remove {backup.name}: {e}")
                continue
            for side in _sidecars(backup):
                _remove_sidecar(side)

        log("INFO", f"Cleanup complete: removed {len(to_remove)} old backups")

    _cleanup_stale_sidecars(prefix, directory)


def _remove_sidecar(path: Path) -> None:
    if not path.exists():
        return
    try:
        path.unlink()
        log("INFO", f"Removed stale sidecar: {path.name}")
    except OSError as e:
        log("WARN", f"Failed to remove {path.name}: {e}")


def _cleanup_stale_sidecars(prefix: str, directory: Path | None = None) -> None:
    """Remove -wal/-shm files left beside this prefix's backups by earlier runs.

    Only names of the form <prefix>_YYYYMMDD_HHMMSS.db-wal|-shm directly in
    `directory` (default BACKUP_DIR) are considered. The .db files are never
    touched here.
    - Orphan (its .db is gone): removed.
    - Beside an existing backup: -shm is removed (it is only an index);
      -wal is removed only if it is empty. A non-empty -wal could hold data
      of that backup, so it is kept and reported instead.
    Leftover mirror temp files (.<prefix>_YYYYMMDD_HHMMSS.db.partial, e.g.
    from a killed run) are removed too.
    """
    directory = BACKUP_DIR if directory is None else directory
    pattern = re.compile(rf"^{re.escape(prefix)}_\d{{8}}_\d{{6}}\.db(-wal|-shm)$")
    partial = re.compile(rf"^\.{re.escape(prefix)}_\d{{8}}_\d{{6}}\.db{re.escape(PARTIAL_SUFFIX)}$")
    for side in sorted(directory.iterdir()):
        if partial.match(side.name) and side.is_file():
            try:
                side.unlink()
                log("INFO", f"Removed stale temp file: {side.name}")
            except OSError as e:
                log("WARN", f"Failed to remove {side.name}: {e}")
            continue
        m = pattern.match(side.name)
        if not m or not side.is_file():
            continue
        db_path = side.with_name(side.name[: -len(m.group(1))])
        if db_path.exists() and m.group(1) == "-wal":
            try:
                size = side.stat().st_size
            except OSError:
                continue
            if size > 0:
                log("WARN", f"Kept non-empty WAL beside backup: {side.name} ({size} bytes)")
                continue
        _remove_sidecar(side)


def run_backup(db_path: Path, prefix: str, retention: int) -> bool:
    """
    Complete backup workflow for a single database.
    """
    return _run_backup_to_path(db_path, prefix, retention) is not None


def _run_backup_to_path(db_path: Path, prefix: str, retention: int) -> Path | None:
    """run_backup() that returns the verified backup's path (None on failure)."""
    if not db_path.exists():
        log("WARN", f"Skipping backup - file not found: {db_path}")
        return None

    # 1. Wait for stabilization
    if not wait_for_stabilization(db_path):
        log("ERROR", f"Failed to stabilize {db_path.name}. Aborting backup.")
        return None

    # 2. Generate backup filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"{prefix}_{timestamp}.db"
    backup_path = BACKUP_DIR / backup_name

    # 3. Perform backup
    if not backup_database(db_path, backup_path):
        return None

    # 4. Verify backup
    if not verify_backup(backup_path):
        log("ERROR", "Backup verification failed. Removing corrupted backup.")
        _remove_backup_files(backup_path)
        return None

    # 5. Cleanup old backups
    cleanup_old_backups(prefix, retention)

    log("INFO", f"Backup successful: {backup_name}")
    return backup_path


# ==========================================================
# Mirror copy (optional second directory, e.g. another disk)
# ==========================================================
def _resolve_mirror_dir(cli_value: str | None) -> Path | None:
    """--mirror-dir overrides BACKUP_MIRROR_DIR; empty/unset = mirror off."""
    raw = cli_value if cli_value is not None else BACKUP_MIRROR_DIR
    raw = (raw or "").strip()
    return Path(raw) if raw else None


def mirror_backup(backup_path: Path, prefix: str, retention: int, mirror_dir: Path) -> bool:
    """Copy a verified backup into mirror_dir under the same name.

    Only the backup .db file is read (never the source DB, never sidecars).
    The copy is written to a hidden temp name, verified like the primary
    backup, checked for sidecars and only then renamed to its final name.
    On failure the temp file (and anything beside it) is removed and False
    is returned; the primary backup is never touched.
    """
    final = mirror_dir / backup_path.name
    tmp = mirror_dir / f".{backup_path.name}{PARTIAL_SUFFIX}"
    try:
        if mirror_dir.resolve() == backup_path.parent.resolve():
            log("ERROR", f"Mirror directory is the backup directory itself: {mirror_dir}")
            return False
        mirror_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup_path, tmp)
        if not verify_backup(tmp):
            raise OSError("mirror copy failed verification")
        left = [p.name for p in _sidecars(tmp) if p.exists()]
        if left:
            raise OSError(f"sidecar files beside mirror copy: {left}")
        os.replace(tmp, final)
        left = [p.name for p in _sidecars(final) if p.exists()]
        if left:
            # Cannot happen for a verified rollback-mode file; fail loudly.
            _remove_backup_files(final)
            raise OSError(f"sidecar files beside mirror copy: {left}")
    except OSError as e:
        log("ERROR", f"Mirror copy failed for {backup_path.name} -> {mirror_dir}: {e}")
        _remove_backup_files(tmp)
        return False

    log("INFO", f"Mirror copy verified: {final}")
    cleanup_old_backups(prefix, retention, directory=mirror_dir)
    return True


def _backup_target(
    db_path: Path, prefix: str, retention: int, mirror_dir: Path | None
) -> tuple[bool, bool]:
    """Back up one DB (and mirror it when enabled).
    Returns (primary_ok, mirror_failed)."""
    if mirror_dir is None:
        return run_backup(db_path, prefix, retention), False
    backup_path = _run_backup_to_path(db_path, prefix, retention)
    if backup_path is None:
        return False, False
    return True, not mirror_backup(backup_path, prefix, retention, mirror_dir)


def _app_db_targets() -> list[tuple[str, Path, str, int]]:
    """App-owned DBs (label, path, prefix, retention). Resolved at call time
    so tests can monkeypatch the module-level paths."""
    return [
        ("Materials DB", MATERIALS_DB_FILE, "materials", APP_BACKUP_RETENTION),
        ("Notifications DB", NOTIFICATIONS_DB_FILE, "notifications", APP_BACKUP_RETENTION),
        ("Anomaly DB", ANOMALY_DB_FILE, "anomaly", APP_BACKUP_RETENTION),
    ]


def _run_app_backups(mirror_dir: Path | None = None) -> tuple[int, int, int, int]:
    """Back up every app DB. A missing file is skipped, not counted as failed.
    Returns (success, failed, skipped, mirror_failed)."""
    success = fail = skipped = mirror_fail = 0
    for label, db_path, prefix, retention in _app_db_targets():
        log("INFO", "-" * 30)
        log("INFO", f"Backing up {label}...")
        if not db_path.exists():
            log("INFO", f"Skipping {label} - not present on this machine: {db_path}")
            skipped += 1
            continue
        ok, m_fail = _backup_target(db_path, prefix, retention, mirror_dir)
        if ok:
            success += 1
        else:
            fail += 1
        mirror_fail += int(m_fail)
    return success, fail, skipped, mirror_fail


def _run_cleanup_only(mirror_dir: Path | None) -> None:
    log("INFO", "Running cleanup only...")
    targets = [
        ("production", LIVE_BACKUP_RETENTION),
        ("archive_2025", ARCHIVE_BACKUP_RETENTION),
        *((prefix, retention) for _l, _p, prefix, retention in _app_db_targets()),
    ]
    for prefix, retention in targets:
        cleanup_old_backups(prefix, retention)
    if mirror_dir is not None:
        log("INFO", "Running mirror cleanup...")
        for prefix, retention in targets:
            cleanup_old_backups(prefix, retention, directory=mirror_dir)
    log("INFO", "Cleanup complete.")


# ==========================================================
# Main
# ==========================================================
def main():
    parser = argparse.ArgumentParser(description="Production Data Hub - Database Backup")
    parser.add_argument("--live", action="store_true", help="Backup Live DB only")
    parser.add_argument("--archive", action="store_true", help="Backup Archive DB only")
    parser.add_argument("--cleanup", action="store_true", help="Only run cleanup, no backup")
    parser.add_argument(
        "--mirror-dir",
        default=None,
        metavar="PATH",
        help="Also copy each verified backup here (overrides BACKUP_MIRROR_DIR; empty = off)",
    )
    args = parser.parse_args()
    mirror_dir = _resolve_mirror_dir(args.mirror_dir)

    log("INFO", "=" * 50)
    log("INFO", "Production Data Hub - Database Backup")
    log("INFO", "=" * 50)

    # Ensure backup directory exists
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    log("INFO", f"Backup directory: {BACKUP_DIR}")
    if mirror_dir is not None:
        log("INFO", f"Mirror directory: {mirror_dir}")

    if args.cleanup:
        _run_cleanup_only(mirror_dir)
        return 0

    success_count = 0
    fail_count = 0
    mirror_fail_count = 0

    # Backup Live DB
    if not args.archive:  # Default or --live
        log("INFO", "-" * 30)
        log("INFO", "Backing up Live DB...")
        ok, m_fail = _backup_target(DB_FILE, "production", LIVE_BACKUP_RETENTION, mirror_dir)
        if ok:
            success_count += 1
        else:
            fail_count += 1
        mirror_fail_count += int(m_fail)

    # Backup Archive DB
    if not args.live:  # Default or --archive
        log("INFO", "-" * 30)
        log("INFO", "Backing up Archive DB...")
        ok, m_fail = _backup_target(
            ARCHIVE_DB_FILE, "archive_2025", ARCHIVE_BACKUP_RETENTION, mirror_dir
        )
        if ok:
            success_count += 1
        else:
            fail_count += 1
        mirror_fail_count += int(m_fail)

    # Backup app DBs (default run only; --live / --archive keep their old scope)
    skip_count = 0
    if not args.live and not args.archive:
        app_success, app_fail, skip_count, app_mirror_fail = _run_app_backups(mirror_dir)
        success_count += app_success
        fail_count += app_fail
        mirror_fail_count += app_mirror_fail

    # Summary
    summary = f"Backup Summary: {success_count} success, {fail_count} failed, {skip_count} skipped"
    if mirror_dir is not None:
        summary += f", {mirror_fail_count} mirror failed"
    log("INFO", "=" * 50)
    log("INFO", summary)
    log("INFO", "=" * 50)

    return 0 if fail_count == 0 and mirror_fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
