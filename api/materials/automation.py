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
    """Raised when a run cannot be started.

    ``status_code``로 사유별 HTTP 매핑 (roadmap-2026h2 B-5 — 일괄 409는
    클라이언트가 모든 실패를 '이미 실행 중'으로 오인하게 했다):
    409 중복 실행 / 503 기능 비활성 / 500 설정 오류(봇 진입점 없음)."""

    def __init__(self, message: str, *, status_code: int = 409) -> None:
        super().__init__(message)
        self.status_code = status_code


# Makes the check-then-insert in trigger_automation atomic — two nearly
# simultaneous 지금 실행 clicks both saw "no active run" and spawned two bots.
_trigger_lock = threading.Lock()


def _run_subprocess(python: str, bot_dir: str, keyword: str | None = None) -> tuple[int, str]:
    """Run `python main.py --auto [--keyword KW]` in bot_dir.

    Returns (exit_code, output_tail). Isolated for testability — tests
    monkeypatch this to avoid a real launch. keyword가 주어지면 해당 검색어로,
    None이면 봇 기본 키워드(자재)로 실행한다.
    """
    cmd = [python, "main.py", "--auto"]
    if keyword:
        cmd += ["--keyword", keyword]
    proc = subprocess.run(
        cmd,
        cwd=bot_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, output[-_MESSAGE_TAIL:]


def _worker(run_id: int, keyword: str | None, runs_table: str) -> None:
    python = _cfg.MATERIALS_BOT_PYTHON
    bot_dir = str(_cfg.MATERIALS_BOT_DIR)
    try:
        exit_code, tail = _run_subprocess(python, bot_dir, keyword)
        status = "success" if exit_code == 0 else "failed"
        runs.finish_run(run_id, status, runs_table=runs_table,
                        exit_code=exit_code, message=tail or None)
        logger.info("[materials] automation run %d finished: %s (exit=%s)",
                    run_id, status, exit_code)
    except Exception as e:  # noqa: BLE001 — background thread: 어떤 오류든 run에 기록
        runs.finish_run(run_id, "failed", runs_table=runs_table,
                        message=f"trigger error: {e}")
        logger.exception("[materials] automation run %d crashed", run_id)


def trigger_automation(
    keyword: str | None = None,
    runs_table: str = runs.DEFAULT_DATASET.runs_table,
) -> int:
    """Start a manual automation run in the background. Returns the run id.

    Args:
        keyword: 봇에 전달할 검색 키워드 (데이터셋별). None이면 기본 자재.
        runs_table: 실행 이력을 기록할 데이터셋 runs 테이블.

    Raises TriggerError if disabled or another automation is already running.
    """
    if not _cfg.MATERIALS_RUN_ENABLED:
        raise TriggerError(
            "수동 실행이 비활성화되어 있습니다 (MATERIALS_RUN_ENABLED=1 필요).",
            status_code=503,
        )
    bot_dir = _cfg.MATERIALS_BOT_DIR
    if not (bot_dir / "main.py").exists():
        raise TriggerError(
            f"봇 진입점을 찾을 수 없습니다: {bot_dir / 'main.py'}",
            status_code=500,
        )
    with _trigger_lock:
        reaped = runs.reap_stale_running(runs_table=runs_table)
        if reaped:
            logger.warning(
                "[materials] reaped %d stale running run(s) in %s",
                reaped, runs_table,
            )
        if runs.has_active_automation(runs_table=runs_table):
            raise TriggerError("이미 실행 중인 자동화가 있습니다.")
        run_id = runs.start_run("automation", runs_table=runs_table)
    threading.Thread(
        target=_worker, args=(run_id, keyword, runs_table),
        name=f"MaterialsAutomation-{run_id}", daemon=True,
    ).start()
    logger.info("[materials] automation run %d started (keyword=%s)", run_id, keyword)
    return run_id
