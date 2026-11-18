"""Headless launcher for the non-HTTP roles under Task Scheduler (stdlib only).

Two things the manager GUI used to provide and a scheduled task does not:

* the root `.env`: the manager loaded it and the bot inherited it as a child
  (MATERIALS_API_KEY and friends), so it is loaded here before the bot starts;
* a liveness signal: each role writes `deploy-ops/logs/<role>.pid` (pid + start time)
  so the manager can show "running" without reading SYSTEM-owned process details.

The role's own entry script then runs in-process (same interpreter, no extra child).

Usage (see ops-run.bat):
    python deploy-ops/ops_launch.py portal        # webcloring-pdf main.py --schedule
    python deploy-ops/ops_launch.py portal-once   # webcloring-pdf main.py --auto
    python deploy-ops/ops_launch.py watcher       # tools/watcher.py --daemon --interval 3600
"""
from __future__ import annotations

import json
import os
import runpy
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOT_DIR = ROOT / "webcloring-pdf"
PID_DIR = Path(__file__).resolve().parent / "logs"

# role -> (working directory, entry script, arguments, pid-file role or None)
ROLES: dict[str, tuple[Path, Path, list[str], str | None]] = {
    "portal": (BOT_DIR, BOT_DIR / "main.py", ["--schedule"], "portal"),
    "portal-once": (BOT_DIR, BOT_DIR / "main.py", ["--auto"], None),
    "watcher": (ROOT, ROOT / "tools" / "watcher.py", ["--daemon", "--interval", "3600"], "watcher"),
}


def _load_root_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:  # the bot loads its own .env anyway; only the inherited keys are lost
        print("[ops_launch] python-dotenv missing - root .env not loaded", flush=True)
        return
    load_dotenv(ROOT / ".env")


def _write_pid(pid_role: str) -> None:
    try:
        PID_DIR.mkdir(parents=True, exist_ok=True)
        (PID_DIR / f"{pid_role}.pid").write_text(
            json.dumps({"pid": os.getpid(), "started": time.time()}), encoding="utf-8"
        )
    except OSError as exc:
        print(f"[ops_launch] could not write pid file: {exc}", flush=True)


def main() -> None:
    role = sys.argv[1] if len(sys.argv) > 1 else ""
    if role not in ROLES:
        print("usage: ops_launch.py portal|portal-once|watcher", flush=True)
        raise SystemExit(2)

    cwd, script, args, pid_role = ROLES[role]
    if not script.exists():
        print(f"[ops_launch] {script} not found (portal: git submodule update --init)", flush=True)
        raise SystemExit(2)

    _load_root_env()
    if pid_role:
        _write_pid(pid_role)
    os.chdir(cwd)
    sys.path.insert(0, str(script.parent))
    sys.argv = [str(script), *args]
    runpy.run_path(str(script), run_name="__main__")


if __name__ == "__main__":
    main()
