"""Service mode: Task Scheduler owns the service lifecycle, the manager only observes.

`deploy-ops/ops-install` registers boot tasks for the API, the portal scheduler and the
DB watcher and drops the marker file `deploy-ops/.service-mode`. While the marker
exists the manager must not start its own copies (a second portal scheduler would run
every job twice; a second API cannot bind the port).

Liveness of the non-HTTP roles comes from the pid files `deploy-ops/ops_launch.py`
writes (`deploy-ops/logs/<role>.pid`): the services run as SYSTEM and a non-elevated
manager cannot read their command lines, but it can still ask whether a pid exists
and when that process started.

Kept free of GUI imports so it can be unit tested.
"""
from __future__ import annotations

import json
from pathlib import Path

import psutil

MARKER_RELATIVE = Path("deploy-ops") / ".service-mode"
PID_DIR_RELATIVE = Path("deploy-ops") / "logs"
SERVICE_ROLES = ("portal", "watcher")

# ops_launch stamps time.time() right after interpreter start, so the stamp is a
# little later than the OS process creation time. A reused pid would be far outside.
_START_TOLERANCE_SECONDS = 120.0


def is_service_mode(base_dir: Path) -> bool:
    return (Path(base_dir) / MARKER_RELATIVE).exists()


def role_pid_path(base_dir: Path, role: str) -> Path:
    return Path(base_dir) / PID_DIR_RELATIVE / f"{role}.pid"


def is_role_running(base_dir: Path, role: str) -> bool:
    """True when the process recorded in the role's pid file is still that process."""
    try:
        record = json.loads(role_pid_path(base_dir, role).read_text(encoding="utf-8"))
        pid = int(record["pid"])
        started = float(record["started"])
    except (OSError, ValueError, KeyError, TypeError):
        return False
    try:
        created = psutil.Process(pid).create_time()
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        return False
    return -5.0 <= started - created <= _START_TOLERANCE_SECONDS
