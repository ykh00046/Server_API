# manager-orphan-prevention-v1 Design Document

> **Summary**: psutil 기반 kill helper 추출 + manager.py 종료 경로 강화 구현 설계
>
> **Date**: 2026-04-24
> **Status**: Design

---

## 1. Architecture Decisions

### AD-1: Kill 로직을 `shared/process_utils.py`로 추출

**선택지**

| 옵션 | 장점 | 단점 | 결정 |
|------|------|------|------|
| A. `manager.py` 내 함수 유지 + psutil 교체 | 범위 최소 | 테스트 어려움 (manager 전체 import 시 Tk/pystray 필요) | ✗ |
| B. `shared/process_utils.py`로 추출 | 순수 함수, 독립 테스트 가능 | 신규 모듈 1개 추가 | **✓** |

**선택 근거**: B
- `manager.py`는 GUI 의존성(customtkinter, pystray)이 많아 단위 테스트가 사실상 불가.
- kill 로직은 pure process-level이므로 분리가 자연스럽다.

### AD-2: psutil snapshot-before-kill 패턴

```
1. parent = psutil.Process(pid)          # 존재하지 않으면 조기 return
2. descendants = parent.children(recursive=True)   # 죽이기 전 스냅샷
3. all = [parent] + descendants
4. for p in all: p.terminate()           # 모두에게 graceful signal
5. gone, alive = psutil.wait_procs(all, timeout=3.0)
6. for p in alive: p.kill()              # 강제 종료
7. taskkill /F /T /PID <pid>             # Windows 엣지 케이스용 fallback
```

**`wait_procs` 이유**: `terminate()`는 비동기. `wait_procs`가 graceful exit 여부를 시간 내에 판정. 여전히 살아있는 건 `kill()`로 즉시 종료.

**taskkill fallback**: psutil이 접근 못하는 system-level GUI 프로세스를 위한 안전망. 이미 죽었으면 no-op이므로 부작용 없음.

### AD-3: Tray 실패 fallback

```python
def _setup_tray(self) -> None:
    self.tray_icon = None
    try:
        icon_image = _create_tray_icon()
        menu = pystray.Menu(...)
        self.tray_icon = pystray.Icon(...)
    except Exception as e:
        logger.error(f"Tray icon init failed: {e}")
        # self.tray_icon는 None으로 유지

def on_close(self) -> None:
    if self.tray_icon is not None:
        self._hide_to_tray()
    else:
        if messagebox.askyesno(
            "종료 확인",
            "트레이 아이콘을 사용할 수 없습니다.\n"
            "서버를 모두 종료하고 매니저를 닫으시겠습니까?"
        ):
            self._cleanup_and_exit()
        # else: 창 유지 (사용자가 Yes 안 누르면 닫히지 않음)
```

### AD-4: SIGINT 핸들러

```python
import signal

def __init__(self):
    super().__init__()
    ...
    # Console Ctrl+C → main thread에 cleanup schedule
    try:
        signal.signal(signal.SIGINT, self._on_sigint)
    except (ValueError, OSError):
        # signal.signal은 메인 스레드에서만 가능. VBS/배경 실행 등 콘솔 없는 환경에서 실패 가능.
        pass

def _on_sigint(self, signum, frame) -> None:
    """Schedule graceful exit on main Tk thread."""
    self.after(0, self._cleanup_and_exit)
```

**Windows 주의**: `SIGINT`는 콘솔 프로세스에서만 수신됨. `start_services_hidden.vbs` 경로는 콘솔 없음 → 이 핸들러 미동작. 그래도 직접 `python manager.py` 실행 시 Ctrl+C가 cleanly 종료.

### AD-5: `os._exit` vs `sys.exit`

`sys.exit(0)` 유지 (현재 코드 그대로). 이유:
- `atexit._cleanup_all_processes`가 safety net 역할
- pystray daemon thread이므로 mainloop 종료 시 process 자연 종료 기대 가능
- 기존 동작을 바꾸면 UI 상태 저장 등 다른 atexit hook에 영향 가능성 (보수적 변경)

---

## 2. File-Level Changes

### 2.1 `shared/process_utils.py` (신규)

```python
"""Process management utilities shared between manager and other services.

Extracted for independent unit testing — `manager.py` has heavy GUI deps
(customtkinter, pystray) that make its functions hard to test.

Primary export: `kill_process_tree(pid, timeout)` — reliable cross-platform
process-tree termination using psutil snapshot + wait + fallback.
"""
from __future__ import annotations

import logging
import subprocess

import psutil

logger = logging.getLogger(__name__)


def kill_process_tree(pid: int, timeout: float = 3.0) -> None:
    """Terminate a process and all its descendants reliably.

    Uses psutil to snapshot descendants BEFORE killing the parent (prevents
    reparenting race), then graceful-terminate-wait-kill sequence, then
    taskkill /F /T as a Windows fallback.

    Args:
        pid: Target process PID.
        timeout: Seconds to wait for graceful exit before force-kill.

    Notes:
        - Silently returns if PID does not exist (idempotent).
        - Never raises — all exceptions suppressed to keep UI callers safe.
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

    # Windows fallback for GUI subsystem processes psutil can't signal.
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
```

### 2.2 `manager.py` 변경

**Imports 추가**:
```python
import signal
from shared.process_utils import kill_process_tree
```

**`_taskkill_tree` 삭제** (line 277-282).

**`_cleanup_all_processes` 내부 갱신**:
```python
def _cleanup_all_processes() -> None:
    with _process_lock:
        for proc in _active_processes:
            try:
                if proc.poll() is None:
                    kill_process_tree(proc.pid)
            except Exception:
                pass
        _active_processes.clear()
```

**`stop_web`, `stop_api`, `stop_portal` 내부 `_taskkill_tree` → `kill_process_tree` 교체** (3 지점).

**`_setup_tray` 전체**:
```python
def _setup_tray(self) -> None:
    """Setup system tray icon (best-effort)."""
    self.tray_icon = None
    try:
        icon_image = _create_tray_icon()
        menu = pystray.Menu(
            pystray.MenuItem("창 보이기", self._show_window, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("완전 종료", self._quit_app),
        )
        self.tray_icon = pystray.Icon(
            "production_hub", icon_image, "Production Hub", menu
        )
    except Exception as e:
        # Tray unavailable — on_close will fallback to confirmation dialog.
        print(f"[Manager] Tray init failed: {e}", flush=True)
```

**`on_close` 전체**:
```python
def on_close(self) -> None:
    """Handle window close button.

    - If tray available: hide to tray (original behavior).
    - If tray unavailable: ask user to confirm full exit.
    """
    if self.tray_icon is not None:
        self._hide_to_tray()
        return

    if messagebox.askyesno(
        "종료 확인",
        "트레이 아이콘을 사용할 수 없습니다.\n"
        "서버를 모두 종료하고 매니저를 닫으시겠습니까?"
    ):
        self._cleanup_and_exit()
```

**`__init__` 끝에 SIGINT 등록**:
```python
# Safety on close
self.protocol("WM_DELETE_WINDOW", self.on_close)

# Setup system tray
self._setup_tray()

# Console Ctrl+C → schedule cleanup on main Tk thread
try:
    signal.signal(signal.SIGINT, self._on_sigint)
except (ValueError, OSError):
    pass  # Non-console env (VBS background launch) — silent skip
```

**`_on_sigint` method 추가** (아무 위치):
```python
def _on_sigint(self, signum, frame) -> None:
    """SIGINT handler — schedule graceful exit on main Tk thread."""
    self.after(0, self._cleanup_and_exit)
```

### 2.3 `tests/test_process_utils.py` (신규)

```python
"""Unit tests for shared.process_utils.kill_process_tree.

Spawns real subprocesses with a grandchild and verifies both are terminated.
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
        deadline = time.time() + 5
        descendants = []
        while time.time() < deadline:
            try:
                descendants = psutil.Process(parent.pid).children(recursive=True)
            except psutil.NoSuchProcess:
                pytest.fail("parent died unexpectedly")
            if descendants:
                break
            time.sleep(0.1)
        assert descendants, "grandchild did not spawn within 5s"
        descendant_pids = [d.pid for d in descendants]

        kill_process_tree(parent.pid, timeout=3.0)
        time.sleep(0.5)  # OS reap

        assert not psutil.pid_exists(parent.pid), "parent still alive"
        for dpid in descendant_pids:
            assert not psutil.pid_exists(dpid), f"descendant {dpid} still alive"
    finally:
        try:
            parent.kill()
        except Exception:
            pass


def test_kill_process_tree_nonexistent_pid_is_noop():
    """Non-existent PID should not raise."""
    kill_process_tree(999999, timeout=0.1)  # PID 999999 almost certainly missing
```

---

## 3. Test Plan

| Test | 명령 | 기대 |
|------|------|------|
| 신규 helper 단위 | `pytest tests/test_process_utils.py -v` | 2 passed (~3초) |
| 전체 회귀 | `pytest tests/ -q` | 222 + 2 = 224 passed |
| manager 구문 체크 | `python -c "import manager"` (GUI 의존성 있으나 import 가능 여부만) | no ImportError |
| grep 검증 | `grep -n "_taskkill_tree\|kill_process_tree" manager.py` | `_taskkill_tree` 0건, `kill_process_tree` 호출 3+ 건 |

수동 smoke (사용자):
1. manager 실행 → Dashboard + API 시작
2. 작업 관리자에서 manager 프로세스 강제 종료
3. 5초 후 `netstat -ano \| findstr 8000`, `netstat -ano \| findstr 8502` — 자식이 종료됐으면 포트 free
4. 또는: manager X 버튼 → 트레이 우클릭 "완전 종료" → 동일 검증

---

## 4. Rollback

| Commit | Revert 영향 |
|--------|-----------|
| plan + design | 기능 영향 없음 |
| shared/process_utils.py + test | 헬퍼 파일 제거. manager가 이 사이클 전이면 기존 동작 |
| manager.py 통합 | 예전 `_taskkill_tree` 경로 복구 |

각 레이어 독립, 부분 revert 가능.

---

## 5. Open Questions

- (해결됨) Job Object 도입 여부 → AD-1의 B 선택으로 psutil만으로 충분.
- (해결됨) `os._exit(0)` 전환 → AD-5에서 보수적으로 `sys.exit(0)` 유지.
- (deferred) PID 파일 기반 stale cleanup → 재발 시 `manager-pid-recovery-v2` 후보.
