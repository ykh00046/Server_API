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
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

# Add parent directory for shared imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared import ARCHIVE_DB_FILE, DATABASE_DIR, DB_FILE
from shared.config import LOGS_DIR
from shared.db_maintenance import (
    check_and_heal_indexes,
    get_file_state,
    run_analyze,
    wait_for_stabilization,
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
    except OSError:
        pass  # Don't fail if logging fails


# ==========================================================
# State Management
# ==========================================================
def load_state() -> dict:
    """Load last known state from file."""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            pass
    return {
        "live_mtime": 0, "live_size": 0, "archive_mtime": 0,
        "archive_size": 0, "last_analyze_ts": 0,
    }


def save_state(state: dict):
    """Save current state to file."""
    try:
        DATABASE_DIR.mkdir(parents=True, exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
    except (OSError, json.JSONDecodeError) as e:
        log("WARN", f"Failed to save state: {e}")


# ==========================================================
# Core Functions (imported from shared.db_maintenance)
# -- wait_for_stabilization, check_and_heal_indexes,
#    get_file_state are now imported above.
# ==========================================================


def _check_live_db(state: dict, summary: dict) -> tuple[float, int]:
    """Live DB 검사·치료. 변경 시 heal, 미변경 시에도 주기적 heal을 수행한다.

    Returns the (possibly refreshed) (mtime, size) to persist into state.
    """
    live_mtime, live_size = get_file_state(DB_FILE)
    if not DB_FILE.exists():
        return live_mtime, live_size

    changed = live_mtime != state["live_mtime"] or live_size != state["live_size"]
    if changed:
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
    return live_mtime, live_size


def _check_archive_db(state: dict, summary: dict) -> tuple[float, int]:
    """Archive DB 검사·치료. 파일이 없으면 안내 로그만 남긴다.

    Returns the (possibly refreshed) (mtime, size) to persist into state.
    """
    archive_mtime, archive_size = get_file_state(ARCHIVE_DB_FILE)
    if not ARCHIVE_DB_FILE.exists():
        log("INFO", "Archive DB not found (may not exist yet)")
        return archive_mtime, archive_size

    changed = archive_mtime != state["archive_mtime"] or archive_size != state["archive_size"]
    if changed:
        log("INFO", f"Archive DB changed: mtime={archive_mtime}, size={archive_size}")
        summary["archive"]["changed"] = True
        if wait_for_stabilization(ARCHIVE_DB_FILE):
            summary["archive"]["result"] = check_and_heal_indexes(ARCHIVE_DB_FILE)
            archive_mtime, archive_size = get_file_state(ARCHIVE_DB_FILE)
        else:
            log("WARN", "Archive DB not stable, skipping index check")
            # Keep the last saved state so the next cycle sees the change again and
            # retries the heal (an unchanged archive is never healed). Same as
            # DBWatcher (db_watcher.py:103-105).
            return state["archive_mtime"], state["archive_size"]
    else:
        log("INFO", "Archive DB unchanged")
    return archive_mtime, archive_size


def _change_counter(db_path: Path) -> int | None:
    """SQLite header file change counter (offset 24, 4 bytes big-endian).

    Incremented once per committed write in rollback-journal mode. Returns None
    for a WAL-mode file (header bytes 18/19 == 2), where the counter is not
    bumped once per commit, or if the header cannot be read.
    """
    try:
        with open(db_path, "rb") as f:
            data = f.read(28)
    except OSError:
        return None
    if len(data) != 28 or data[18] != 1 or data[19] != 1:
        return None
    return int.from_bytes(data[24:28], "big")


def _run_periodic_analyze(
    summary: dict, last_analyze_ts: float, file_states: dict | None = None,
) -> float:
    """ANALYZE를 1일 1회 실행. last_analyze_ts 갱신값을 반환한다.

    file_states ({db_path: (mtime, size)}, 저장 예정 상태)가 주어지면 ANALYZE 자신의
    쓰기를 반영해 갱신한다. 단 (1) ANALYZE 직전 파일 상태가 저장 예정 상태와 같고
    (검사 뒤 외부 변경 없음) (2) ANALYZE 동안 파일 변경 카운터가 정확히 1 올랐을 때만
    (ANALYZE 자신의 커밋 1건뿐) 갱신한다. 아니면 그대로 두어 다음 주기가 감지하게 한다.
    WAL 모드 파일은 카운터로 판별할 수 없으므로 갱신하지 않는다(이전 동작 유지).
    """
    now = time.time()
    if now - last_analyze_ts < ANALYZE_INTERVAL:
        remaining_h = int((ANALYZE_INTERVAL - (now - last_analyze_ts)) / 3600)
        log("INFO", f"ANALYZE skipped (next in ~{remaining_h}h)")
        return last_analyze_ts

    log("INFO", f"Running ANALYZE (last run: {int((now - last_analyze_ts) / 3600)}h ago)")
    analyze_results = []
    for db_path in [DB_FILE, ARCHIVE_DB_FILE]:
        if db_path.exists():
            before = get_file_state(db_path)
            counter_before = _change_counter(db_path)
            result = run_analyze(db_path)
            if (
                file_states is not None
                and file_states.get(db_path) == before
                and counter_before is not None
                and _change_counter(db_path) == counter_before + 1
            ):
                file_states[db_path] = get_file_state(db_path)
            analyze_results.append(result)
            if result["success"]:
                log("INFO", f"ANALYZE OK: {result['db']} ({result['duration_ms']}ms)")
            else:
                log("WARN", f"ANALYZE failed: {result['db']} - {result['error']}")
    summary["analyze"]["ran"] = True
    summary["analyze"]["results"] = analyze_results
    return now


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
    live_mtime, live_size = _check_live_db(state, summary)

    # Check Archive DB
    archive_mtime, archive_size = _check_archive_db(state, summary)

    # ANALYZE: run once per day
    # (file states are refreshed after ANALYZE so its own write is not seen as a change)
    file_states = {DB_FILE: (live_mtime, live_size), ARCHIVE_DB_FILE: (archive_mtime, archive_size)}
    last_analyze_ts = _run_periodic_analyze(summary, state.get("last_analyze_ts", 0), file_states)
    live_mtime, live_size = file_states[DB_FILE]
    archive_mtime, archive_size = file_states[ARCHIVE_DB_FILE]

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
        except (OSError, RuntimeError, ValueError, json.JSONDecodeError, sqlite3.Error) as e:
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
