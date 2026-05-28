# tools/watcher.py
"""
Production Data Hub - Independent DB Watcher Script

Features (Section 6.3):
- Runs independently from Manager UI
- Monitors DB file changes and auto-heals indexes
- Can be scheduled via Windows Task Scheduler

Usage:
    python tools/watcher.py              # Single check and heal
    python tools/watcher.py --daemon     # Run continuously (1 hour interval)
    python tools/watcher.py --interval 300  # Custom interval (seconds)

Windows Task Scheduler Setup:
    1. Open Task Scheduler
    2. Create Basic Task
    3. Trigger: At startup / Daily / Every 5 minutes
    4. Action: Start a program
       - Program: python.exe (or full path)
       - Arguments: C:\\X\\Server_v1\\tools\\watcher.py
       - Start in: C:\\X\\Server_v1
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

# Add parent directory for shared imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared import DB_FILE, ARCHIVE_DB_FILE, DATABASE_DIR, DB_TIMEOUT
from shared.config import LOGS_DIR
from shared.db_maintenance import (
    wait_for_stabilization,
    check_and_heal_indexes,
    run_analyze,
    get_file_state,
    REQUIRED_INDEXES,
)


# ==========================================================
# Configuration
# ==========================================================
STATE_FILE = DATABASE_DIR / ".watcher_state.json"
DEFAULT_INTERVAL = 3600  # 1 hour
ANALYZE_INTERVAL = 86400  # 24 hours


# ==========================================================
# Logging
# ==========================================================
LOG_FILE = LOGS_DIR / "watcher.log"


def log(level: str, msg: str):
    """Log to both stdout and file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] [{level:5}] {msg}"
    print(log_line)

    # Also write to log file
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_line + "\n")
    except (OSError, IOError):
        pass  # Don't fail if logging fails


# ==========================================================
# State Management
# ==========================================================
def load_state() -> dict:
    """Load last known state from file."""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            pass
    return {"live_mtime": 0, "live_size": 0, "archive_mtime": 0, "archive_size": 0, "last_analyze_ts": 0}


def save_state(state: dict):
    """Save current state to file."""
    try:
        DATABASE_DIR.mkdir(parents=True, exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
    except (OSError, json.JSONDecodeError) as e:
        log("WARN", f"Failed to save state: {e}")


def get_file_state(path: Path) -> tuple[float, int]:
    """Get mtime and size of a file. Returns (0, 0) if not exists."""
    if not path.exists():
        return 0, 0
    try:
        return os.path.getmtime(path), os.path.getsize(path)
    except OSError:
        return 0, 0


# ==========================================================
# Core Functions (imported from shared.db_maintenance)
# -- wait_for_stabilization, check_and_heal_indexes,
#    get_file_state are now imported above.
# ==========================================================


def run_check() -> dict:
    """
    Run a single check cycle.
    Returns summary of actions taken.
    """
    log("INFO", "=" * 50)
    log("INFO", "Starting DB check cycle")
    log("INFO", "=" * 50)

    state = load_state()
    summary = {
        "timestamp": datetime.now().isoformat(),
        "live": {"changed": False, "result": None},
        "archive": {"changed": False, "result": None},
        "analyze": {"ran": False, "results": []},
    }

    # Check Live DB
    live_mtime, live_size = get_file_state(DB_FILE)

    if DB_FILE.exists():
        if live_mtime != state["live_mtime"] or live_size != state["live_size"]:
            log("INFO", f"Live DB changed: mtime={live_mtime}, size={live_size}")
            summary["live"]["changed"] = True

            if wait_for_stabilization(DB_FILE):
                summary["live"]["result"] = check_and_heal_indexes(DB_FILE)
                # Update state with new values
                live_mtime, live_size = get_file_state(DB_FILE)
            else:
                log("WARN", "Live DB not stable, skipping index check")
        else:
            log("INFO", "Live DB unchanged")
            # Still do a periodic check even if unchanged
            summary["live"]["result"] = check_and_heal_indexes(DB_FILE)

    # Check Archive DB
    archive_mtime, archive_size = get_file_state(ARCHIVE_DB_FILE)

    if ARCHIVE_DB_FILE.exists():
        if archive_mtime != state["archive_mtime"] or archive_size != state["archive_size"]:
            log("INFO", f"Archive DB changed: mtime={archive_mtime}, size={archive_size}")
            summary["archive"]["changed"] = True

            if wait_for_stabilization(ARCHIVE_DB_FILE):
                summary["archive"]["result"] = check_and_heal_indexes(ARCHIVE_DB_FILE)
                archive_mtime, archive_size = get_file_state(ARCHIVE_DB_FILE)
            else:
                log("WARN", "Archive DB not stable, skipping index check")
        else:
            log("INFO", "Archive DB unchanged")
    else:
        log("INFO", "Archive DB not found (may not exist yet)")

    # ANALYZE: run once per day
    last_analyze_ts = state.get("last_analyze_ts", 0)
    now = time.time()
    if now - last_analyze_ts >= ANALYZE_INTERVAL:
        log("INFO", f"Running ANALYZE (last run: {int((now - last_analyze_ts) / 3600)}h ago)")
        analyze_results = []
        for db_path in [DB_FILE, ARCHIVE_DB_FILE]:
            if db_path.exists():
                result = run_analyze(db_path)
                analyze_results.append(result)
                if result["success"]:
                    log("INFO", f"ANALYZE OK: {result['db']} ({result['duration_ms']}ms)")
                else:
                    log("WARN", f"ANALYZE failed: {result['db']} - {result['error']}")
        summary["analyze"]["ran"] = True
        summary["analyze"]["results"] = analyze_results
        last_analyze_ts = now
    else:
        remaining_h = int((ANALYZE_INTERVAL - (now - last_analyze_ts)) / 3600)
        log("INFO", f"ANALYZE skipped (next in ~{remaining_h}h)")

    # Save updated state
    save_state({
        "live_mtime": live_mtime,
        "live_size": live_size,
        "archive_mtime": archive_mtime,
        "archive_size": archive_size,
        "last_analyze_ts": last_analyze_ts,
    })

    log("INFO", "=" * 50)
    log("INFO", "Check cycle complete")
    log("INFO", "=" * 50)

    return summary


def run_daemon(interval: int):
    """
    Run continuously with specified interval.
    """
    log("INFO", f"Starting daemon mode with interval={interval}s")

    while True:
        try:
            run_check()
        except Exception as e:
            log("ERROR", f"Check cycle failed: {e}")

        log("INFO", f"Next check in {interval} seconds...")

        # Sleep in small increments for graceful shutdown
        for _ in range(interval):
            time.sleep(1)


# ==========================================================
# Main
# ==========================================================
def main():
    parser = argparse.ArgumentParser(description="Production Data Hub - DB Watcher")
    parser.add_argument("--daemon", action="store_true", help="Run continuously")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL,
                        help=f"Check interval in seconds (default: {DEFAULT_INTERVAL})")
    args = parser.parse_args()

    log("INFO", "Production Data Hub - DB Watcher")
    log("INFO", f"Live DB: {DB_FILE}")
    log("INFO", f"Archive DB: {ARCHIVE_DB_FILE}")

    if args.daemon:
        run_daemon(args.interval)
    else:
        summary = run_check()

        # Print summary
        print("\n--- Summary ---")
        print(json.dumps(summary, indent=2, default=str))

        # Return non-zero if any errors
        if summary["live"]["result"] and summary["live"]["result"].get("error"):
            return 1
        if summary["archive"]["result"] and summary["archive"]["result"].get("error"):
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
