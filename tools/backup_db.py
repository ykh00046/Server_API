# tools/backup_db.py
"""
Production Data Hub - Database Backup Script

Features (Section 6.2):
- Wait for mtime stabilization before backup (prevents corrupted backups)
- Use sqlite3 backup API for safe copying
- PRAGMA quick_check validation after backup
- Retention policy: 30 daily backups for Live DB, 12 weekly for Archive DB,
  30 for each app DB (materials, notifications, anomaly)
- App DBs that do not exist on this machine are skipped (not a failure)

Usage:
    python tools/backup_db.py              # Backup all DBs (Live, Archive, app DBs)
    python tools/backup_db.py --live       # Backup Live DB only
    python tools/backup_db.py --archive    # Backup Archive DB only
    python tools/backup_db.py --cleanup    # Only run cleanup (no backup)

Can be scheduled via Windows Task Scheduler for automated daily backups.
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory for shared imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import contextlib

from shared import ARCHIVE_DB_FILE, DATABASE_DIR, DB_FILE, DB_TIMEOUT
from shared.config import ANOMALY_DB_FILE, MATERIALS_DB_FILE, NOTIFICATIONS_DB_FILE
from shared.db_maintenance import wait_for_stabilization

# ==========================================================
# Configuration
# ==========================================================
BACKUP_DIR = DATABASE_DIR / "backups"

# Retention policy
LIVE_BACKUP_RETENTION = 30  # Keep last 30 daily backups
ARCHIVE_BACKUP_RETENTION = 12  # Keep last 12 weekly backups
APP_BACKUP_RETENTION = 30  # Keep last 30 backups of each app DB


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


def cleanup_old_backups(prefix: str, retention: int):
    """
    Remove old backups exceeding retention policy.
    Keeps the most recent 'retention' number of backups matching the prefix.
    """
    if not BACKUP_DIR.exists():
        return

    # Find all backups matching prefix
    backups = sorted(
        BACKUP_DIR.glob(f"{prefix}_*.db"),
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

    _cleanup_stale_sidecars(prefix)


def _remove_sidecar(path: Path) -> None:
    if not path.exists():
        return
    try:
        path.unlink()
        log("INFO", f"Removed stale sidecar: {path.name}")
    except OSError as e:
        log("WARN", f"Failed to remove {path.name}: {e}")


def _cleanup_stale_sidecars(prefix: str) -> None:
    """Remove -wal/-shm files left beside this prefix's backups by earlier runs.

    Only names of the form <prefix>_YYYYMMDD_HHMMSS.db-wal|-shm directly in
    BACKUP_DIR are considered. The .db files are never touched here.
    - Orphan (its .db is gone): removed.
    - Beside an existing backup: -shm is removed (it is only an index);
      -wal is removed only if it is empty. A non-empty -wal could hold data
      of that backup, so it is kept and reported instead.
    """
    pattern = re.compile(rf"^{re.escape(prefix)}_\d{{8}}_\d{{6}}\.db(-wal|-shm)$")
    for side in sorted(BACKUP_DIR.iterdir()):
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
    if not db_path.exists():
        log("WARN", f"Skipping backup - file not found: {db_path}")
        return False

    # 1. Wait for stabilization
    if not wait_for_stabilization(db_path):
        log("ERROR", f"Failed to stabilize {db_path.name}. Aborting backup.")
        return False

    # 2. Generate backup filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"{prefix}_{timestamp}.db"
    backup_path = BACKUP_DIR / backup_name

    # 3. Perform backup
    if not backup_database(db_path, backup_path):
        return False

    # 4. Verify backup
    if not verify_backup(backup_path):
        log("ERROR", "Backup verification failed. Removing corrupted backup.")
        _remove_backup_files(backup_path)
        return False

    # 5. Cleanup old backups
    cleanup_old_backups(prefix, retention)

    log("INFO", f"Backup successful: {backup_name}")
    return True


def _app_db_targets() -> list[tuple[str, Path, str, int]]:
    """App-owned DBs (label, path, prefix, retention). Resolved at call time
    so tests can monkeypatch the module-level paths."""
    return [
        ("Materials DB", MATERIALS_DB_FILE, "materials", APP_BACKUP_RETENTION),
        ("Notifications DB", NOTIFICATIONS_DB_FILE, "notifications", APP_BACKUP_RETENTION),
        ("Anomaly DB", ANOMALY_DB_FILE, "anomaly", APP_BACKUP_RETENTION),
    ]


def _run_app_backups() -> tuple[int, int, int]:
    """Back up every app DB. A missing file is skipped, not counted as failed.
    Returns (success, failed, skipped)."""
    success = fail = skipped = 0
    for label, db_path, prefix, retention in _app_db_targets():
        log("INFO", "-" * 30)
        log("INFO", f"Backing up {label}...")
        if not db_path.exists():
            log("INFO", f"Skipping {label} - not present on this machine: {db_path}")
            skipped += 1
        elif run_backup(db_path, prefix, retention):
            success += 1
        else:
            fail += 1
    return success, fail, skipped


# ==========================================================
# Main
# ==========================================================
def main():
    parser = argparse.ArgumentParser(description="Production Data Hub - Database Backup")
    parser.add_argument("--live", action="store_true", help="Backup Live DB only")
    parser.add_argument("--archive", action="store_true", help="Backup Archive DB only")
    parser.add_argument("--cleanup", action="store_true", help="Only run cleanup, no backup")
    args = parser.parse_args()

    log("INFO", "=" * 50)
    log("INFO", "Production Data Hub - Database Backup")
    log("INFO", "=" * 50)

    # Ensure backup directory exists
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    log("INFO", f"Backup directory: {BACKUP_DIR}")

    if args.cleanup:
        log("INFO", "Running cleanup only...")
        cleanup_old_backups("production", LIVE_BACKUP_RETENTION)
        cleanup_old_backups("archive_2025", ARCHIVE_BACKUP_RETENTION)
        for _label, _path, prefix, retention in _app_db_targets():
            cleanup_old_backups(prefix, retention)
        log("INFO", "Cleanup complete.")
        return 0

    success_count = 0
    fail_count = 0

    # Backup Live DB
    if not args.archive:  # Default or --live
        log("INFO", "-" * 30)
        log("INFO", "Backing up Live DB...")
        if run_backup(DB_FILE, "production", LIVE_BACKUP_RETENTION):
            success_count += 1
        else:
            fail_count += 1

    # Backup Archive DB
    if not args.live:  # Default or --archive
        log("INFO", "-" * 30)
        log("INFO", "Backing up Archive DB...")
        if run_backup(ARCHIVE_DB_FILE, "archive_2025", ARCHIVE_BACKUP_RETENTION):
            success_count += 1
        else:
            fail_count += 1

    # Backup app DBs (default run only; --live / --archive keep their old scope)
    skip_count = 0
    if not args.live and not args.archive:
        app_success, app_fail, skip_count = _run_app_backups()
        success_count += app_success
        fail_count += app_fail

    # Summary
    log("INFO", "=" * 50)
    log(
        "INFO",
        f"Backup Summary: {success_count} success, {fail_count} failed, {skip_count} skipped",
    )
    log("INFO", "=" * 50)

    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
