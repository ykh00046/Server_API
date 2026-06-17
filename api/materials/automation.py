"""Manual automation trigger (materials-run-v1).

The dashboard "지금 실행" button POSTs to /materials/run, which spawns the
webcloring-pdf 포털 자동화 (`python main.py --auto`) on the SAME ops PC in a
background thread, recording the result in material_runs.

Safety:
- Opt-in: requires shared.config.MATERIALS_RUN_ENABLED (off by default).
- Concurrency guard: refuses if an automation run is already 'running'.
- The actual process spawn is isolated in `_run_subprocess` so tests inject a
  fake without launching a browser.
"""
from __future__ import annotations

import subprocess
import threading

import shared.config as _cfg
from shared import get_logger

from . import runs

logger = get_logger(__name__)

# How much of the subprocess output to keep in the run's message column.
_MESSAGE_TAIL = 2000


class TriggerError(RuntimeError):
    """Raised when a run cannot be started (disabled / already running)."""


def _run_subprocess(python: str, bot_dir: str) -> tuple[int, str]:
    """Run `python main.py --auto` in bot_dir. Returns (exit_code, output_tail).

    Isolated for testability — tests monkeypatch this to avoid a real launch.
    """
    proc = subprocess.run(
        [python, "main.py", "--auto"],
        cwd=bot_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, output[-_MESSAGE_TAIL:]


def _worker(run_id: int) -> None:
    python = _cfg.MATERIALS_BOT_PYTHON
    bot_dir = str(_cfg.MATERIALS_BOT_DIR)
    try:
        exit_code, tail = _run_subprocess(python, bot_dir)
        status = "success" if exit_code == 0 else "failed"
        runs.finish_run(run_id, status, exit_code=exit_code, message=tail or None)
        logger.info("[materials] automation run %d finished: %s (exit=%s)",
                    run_id, status, exit_code)
    except Exception as e:  # noqa: BLE001 — background thread: 어떤 오류든 run에 기록
        runs.finish_run(run_id, "failed", message=f"trigger error: {e}")
        logger.exception("[materials] automation run %d crashed", run_id)


def trigger_automation() -> int:
    """Start a manual automation run in the background. Returns the run id.

    Raises TriggerError if disabled or another automation is already running.
    """
    if not _cfg.MATERIALS_RUN_ENABLED:
        raise TriggerError(
            "수동 실행이 비활성화되어 있습니다 (MATERIALS_RUN_ENABLED=1 필요)."
        )
    bot_dir = _cfg.MATERIALS_BOT_DIR
    if not (bot_dir / "main.py").exists():
        raise TriggerError(f"봇 진입점을 찾을 수 없습니다: {bot_dir / 'main.py'}")
    if runs.has_active_automation():
        raise TriggerError("이미 실행 중인 자동화가 있습니다.")

    run_id = runs.start_run("automation")
    threading.Thread(
        target=_worker, args=(run_id,), name=f"MaterialsAutomation-{run_id}", daemon=True
    ).start()
    logger.info("[materials] automation run %d started", run_id)
    return run_id
