"""Service mode marker + pid-file liveness (shared/service_mode.py, deploy-ops/ops_launch.py)."""
from __future__ import annotations

import json
import os
import runpy
import sys
import time
from pathlib import Path

import psutil
import pytest

from shared import service_mode

REPO_ROOT = Path(__file__).resolve().parent.parent


def _write_pid(base: Path, role: str, payload) -> None:
    path = service_mode.role_pid_path(base, role)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload if isinstance(payload, str) else json.dumps(payload), encoding="utf-8")


def test_service_mode_follows_marker(tmp_path: Path) -> None:
    assert service_mode.is_service_mode(tmp_path) is False
    marker = tmp_path / service_mode.MARKER_RELATIVE
    marker.parent.mkdir(parents=True)
    marker.write_text("x", encoding="ascii")
    assert service_mode.is_service_mode(tmp_path) is True


def test_role_running_for_live_process_with_matching_start(tmp_path: Path) -> None:
    created = psutil.Process(os.getpid()).create_time()
    _write_pid(tmp_path, "portal", {"pid": os.getpid(), "started": created + 2.0})
    assert service_mode.is_role_running(tmp_path, "portal") is True


def test_role_not_running_without_pid_file(tmp_path: Path) -> None:
    assert service_mode.is_role_running(tmp_path, "watcher") is False


def test_role_not_running_when_pid_was_reused(tmp_path: Path) -> None:
    # Same pid, but the recorded start is hours away from this process's creation:
    # the original service died and the OS handed its pid to something else.
    created = psutil.Process(os.getpid()).create_time()
    _write_pid(tmp_path, "portal", {"pid": os.getpid(), "started": created + 7200.0})
    assert service_mode.is_role_running(tmp_path, "portal") is False
    _write_pid(tmp_path, "portal", {"pid": os.getpid(), "started": created - 7200.0})
    assert service_mode.is_role_running(tmp_path, "portal") is False


def test_role_not_running_when_process_is_gone(tmp_path: Path) -> None:
    dead_pid = 4_000_000  # above the Windows pid range in practice
    assert not psutil.pid_exists(dead_pid)
    _write_pid(tmp_path, "watcher", {"pid": dead_pid, "started": time.time()})
    assert service_mode.is_role_running(tmp_path, "watcher") is False


@pytest.mark.parametrize("payload", ["", "{bad", "[]", '{"pid": "x", "started": 1}', '{"pid": 1}'])
def test_role_not_running_on_corrupt_pid_file(tmp_path: Path, payload: str) -> None:
    _write_pid(tmp_path, "portal", payload)
    assert service_mode.is_role_running(tmp_path, "portal") is False


def test_ops_launch_pid_file_is_readable_by_service_mode(tmp_path: Path, monkeypatch) -> None:
    """The launcher's pid record and the manager's reader must agree on the format."""
    launch = runpy.run_path(str(REPO_ROOT / "deploy-ops" / "ops_launch.py"), run_name="ops_launch_under_test")
    pid_dir = tmp_path / service_mode.PID_DIR_RELATIVE
    monkeypatch.setitem(launch["_write_pid"].__globals__, "PID_DIR", pid_dir)

    launch["_write_pid"]("portal")

    assert service_mode.role_pid_path(tmp_path, "portal").exists()
    assert service_mode.is_role_running(tmp_path, "portal") is True


def test_ops_launch_roles_point_at_existing_entry_scripts() -> None:
    launch = runpy.run_path(str(REPO_ROOT / "deploy-ops" / "ops_launch.py"), run_name="ops_launch_under_test")
    roles = launch["ROLES"]
    assert set(roles) == {"portal", "portal-once", "watcher"}
    # The watcher entry lives in this repo; the bot entry is a submodule (may be absent in CI).
    assert roles["watcher"][1] == REPO_ROOT / "tools" / "watcher.py"
    assert roles["watcher"][1].exists()
    assert roles["portal"][2] == ["--schedule"]
    assert roles["portal-once"][2] == ["--auto"]
    assert {roles[r][3] for r in roles} == {"portal", "watcher", None}
    assert sys.version_info >= (3, 10)
