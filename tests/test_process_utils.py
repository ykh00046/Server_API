"""Unit tests for shared.process_utils.kill_process_tree.

Spawns real subprocesses with a grandchild and verifies all are terminated.
Keeps tests self-contained by writing a tiny spawner script to tmp_path.
"""
from __future__ import annotations

import subprocess
import sys
import time

import psutil
import pytest

from shared.process_utils import kill_process_tree


@pytest.mark.timeout(30)
def test_kill_process_tree_removes_parent_and_descendants(tmp_path):
    """Parent sleeper + grandchild sleeper should all be gone after kill."""
    script = tmp_path / "spawner.py"
    script.write_text(
        "import subprocess, sys, time\n"
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
        "time.sleep(120)\n"
    )

    parent = subprocess.Popen([sys.executable, str(script)])
    try:
        # Wait up to 5s for grandchild to appear.
        deadline = time.time() + 5
        descendants = []
        while time.time() < deadline:
            try:
                descendants = psutil.Process(parent.pid).children(recursive=True)
            except psutil.NoSuchProcess:
                pytest.fail("parent died unexpectedly before grandchild spawned")
            if descendants:
                break
            time.sleep(0.1)
        assert descendants, "grandchild did not spawn within 5s"
        descendant_pids = [d.pid for d in descendants]

        kill_process_tree(parent.pid, timeout=3.0)

        # Give OS a moment to reap.
        time.sleep(0.5)

        assert not psutil.pid_exists(parent.pid), "parent still alive"
        for dpid in descendant_pids:
            assert not psutil.pid_exists(dpid), f"descendant {dpid} still alive"
    finally:
        # Safety net if assertions failed mid-way.
        try:
            parent.kill()
        except Exception:
            pass


def test_kill_process_tree_nonexistent_pid_is_noop():
    """Non-existent PID should not raise (idempotent cleanup behavior)."""
    # PID 999999 almost certainly missing on a fresh dev box.
    kill_process_tree(999999, timeout=0.1)
