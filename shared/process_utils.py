"""Process management utilities shared between manager and other services.

Extracted for independent unit testing - `manager.py` has heavy GUI deps
(customtkinter, pystray) that make its functions hard to test.

Primary export: `kill_process_tree(pid, timeout)` - reliable process-tree
termination using psutil snapshot-before-kill + wait + taskkill fallback.
"""
from __future__ import annotations

import logging
import subprocess

import psutil

logger = logging.getLogger(__name__)


def kill_process_tree(pid: int, timeout: float = 3.0) -> None:
    """Terminate a process and all its descendants reliably.

    Uses psutil to snapshot descendants BEFORE killing the parent (prevents
    the reparenting race where `taskkill /T` misses children that re-parent
    to System when the parent dies), then graceful-terminate-wait-kill
    sequence, then `taskkill /F /T` as a Windows safety fallback.

    Args:
        pid: Target process PID.
        timeout: Seconds to wait for graceful exit before force-kill.

    Notes:
        - Silently returns if PID does not exist (idempotent for cleanup paths).
        - Never raises - all exceptions suppressed so UI callers stay safe.
    """
    try:
        parent = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return

    try:
        descendants = parent.children(recursive=True)
    except psutil.NoSuchProcess:
        descendants = []

    all_procs = [parent] + descendants

    for p in all_procs:
        try:
            p.terminate()
        except psutil.NoSuchProcess:
            pass

    _, alive = psutil.wait_procs(all_procs, timeout=timeout)

    for p in alive:
        try:
            p.kill()
        except psutil.NoSuchProcess:
            pass

    # Windows fallback for GUI-subsystem processes psutil can't signal cleanly.
    # No-op if targets already gone.
    try:
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=5.0,
        )
    except Exception:
        pass
