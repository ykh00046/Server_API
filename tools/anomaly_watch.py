# tools/anomaly_watch.py
"""
Production Data Hub - Anomaly Detection Runner (anomaly-detection-v1)

Periodically scans production data for anomalies (volume drop/spike, stale
items) and emits new findings as webhook events via the existing
notifications subsystem. Mirrors tools/watcher.py's run model.

Usage:
    python tools/anomaly_watch.py                # single scan + emit
    python tools/anomaly_watch.py --dry-run      # single scan, no emit
    python tools/anomaly_watch.py --daemon       # run continuously
    python tools/anomaly_watch.py --interval 1800  # custom interval (seconds)

Windows Task Scheduler: schedule the single-scan form (no --daemon) at the
desired cadence, or run with --daemon under a service wrapper.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

# Add parent directory for shared/api imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared import config as cfg
from shared import get_logger

logger = get_logger(__name__)


def log(level: str, msg: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] [{level:5}] {msg}")


def run_once(emit: bool) -> dict:
    """Run a single scan. Imported lazily so --help stays cheap."""
    from api.anomaly import run_detection

    result = run_detection(emit=emit)
    log(
        "INFO",
        f"scan done: findings={result['count']} "
        f"emitted={result['emitted_count']} enabled={result['enabled']}",
    )
    for f in result["findings"]:
        log("WARN", f"[{f['severity']}] {f['message']}")
    return result


def run_daemon(interval: int, emit: bool) -> None:
    log("INFO", f"Starting anomaly daemon: interval={interval}s emit={emit}")
    while True:
        try:
            run_once(emit=emit)
        except Exception as e:  # noqa: BLE001 — 데몬 루프는 어떤 스캔 오류에서도 살아있어야 한다
            log("ERROR", f"scan cycle failed: {e}")
        log("INFO", f"Next scan in {interval} seconds...")
        for _ in range(interval):
            time.sleep(1)


def main() -> int:
    parser = argparse.ArgumentParser(description="Production Data Hub - Anomaly Runner")
    parser.add_argument("--daemon", action="store_true", help="Run continuously")
    parser.add_argument("--dry-run", action="store_true", help="Scan without emitting")
    parser.add_argument(
        "--interval",
        type=int,
        default=cfg.ANOMALY_SCAN_INTERVAL_SEC,
        help=f"Daemon interval seconds (default: {cfg.ANOMALY_SCAN_INTERVAL_SEC})",
    )
    args = parser.parse_args()

    emit = not args.dry_run
    log("INFO", f"Anomaly Detection Runner (enabled={cfg.ANOMALY_ENABLED})")

    if args.daemon:
        run_daemon(args.interval, emit=emit)
        return 0

    result = run_once(emit=emit)
    print("\n--- Summary ---")
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
