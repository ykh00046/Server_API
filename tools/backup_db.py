# tools/backup_db.py
"""
Production Data Hub - Database Backup Script

Features (Section 6.2):
- Wait for mtime stabilization before backup (prevents corrupted backups)
- Use sqlite3 backup API for safe copying
- PRAGMA quick_check validation after backup
- Retention policy: 30 daily backups for Live DB, 12 weekly for Archive DB

Usage:
    python tools/backup_db.py              # Backup both DBs
    python tools/backup_db.py --live       # Backup Live DB only
    python tools/backup_db.py --archive    # Backup Archive DB only
    python tools/backup_db.py --cleanup    # Only run cleanup (no backup)

Can be scheduled via Windows Task Scheduler for automated daily backups.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory for shared imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import contextlib

from shared import ARCHIVE_DB_FILE, DATABASE_DIR, DB_FILE, DB_TIMEOUT
from shared.db_maintenance import wait_for_stabilization

# ==========================================================
# Configuration
# ==========================================================
BACKUP_DIR = DATABASE_DIR / "backups"

# Retention policy
LIVE_BACKUP_RETENTION = 30  # Keep last 30 daily backups
ARCHIVE_BACKUP_RETENTION = 12  # Keep last 12 weekly backups


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

        source_conn.close()
        backup_conn.close()

        log("INFO", f"Backup created: {backup_path}")
        return True

    except sqlite3.Error as e:
        log("ERROR", f"SQLite error during backup: {e}")
        # Clean up partial backup if it exists
        if backup_path.exists():
            with contextlib.suppress(OSError):
                backup_path.unlink()
        return False

    except OSError as e:
        log("ERROR", f"Unexpected error during backup: {e}")
        return False


def verify_backup(backup_path: Path) -> bool:
    """
    Verify backup integrity using PRAGMA quick_check.
    Returns True if valid, False otherwise.
    """
    try:
        log("INFO", f"Verifying backup: {backup_path.name}")

        conn = sqlite3.connect(
            f"file:{backup_path}?mode=ro",
            uri=True,
            timeout=DB_TIMEOUT
        )
        cursor = conn.cursor()
        cursor.execute("PRAGMA quick_check;")
        result = cursor.fetchone()
        conn.close()

        if result and result[0] == "ok":
            log("INFO", f"Backup verification passed: {backup_path.name}")
            return True
        else:
            log("ERROR", f"Backup verification failed: {result}")
            return False

    except sqlite3.Error as e:
        log("ERROR", f"Error verifying backup: {e}")
        return False


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
        log("INFO", f"Cleanup: {len(backups)} backups found, retention={retention}. No cleanup needed.")
        return

    # Remove old backups
    to_remove = backups[retention:]
    for backup in to_remove:
        try:
            backup.unlink()
            log("INFO", f"Removed old backup: {backup.name}")
        except OSError as e:
            log("WARN", f"Failed to remove {backup.name}: {e}")

    log("INFO", f"Cleanup complete: removed {len(to_remove)} old backups")


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
        with contextlib.suppress(OSError):
            backup_path.unlink()
        return False

    # 5. Cleanup old backups
    cleanup_old_backups(prefix, retention)

    log("INFO", f"Backup successful: {backup_name}")
    return True


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

    # Summary
    log("INFO", "=" * 50)
    log("INFO", f"Backup Summary: {success_count} success, {fail_count} failed")
    log("INFO", "=" * 50)

    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
