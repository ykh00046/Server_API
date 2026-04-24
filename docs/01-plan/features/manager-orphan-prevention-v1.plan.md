# manager-orphan-prevention-v1 Planning Document

> **Summary**: manager 종료 시 자식 프로세스(uvicorn/streamlit/portal) 잔존 가능성 완화 — psutil 기반 kill + SIGINT 핸들러 + tray 실패 fallback
>
> **Project**: Server_API (Production Data Hub)
> **Version**: manager-orphan-prevention-v1
> **Author**: interojo
> **Date**: 2026-04-24
> **Status**: Plan

---

## 1. Overview

### 1.1 Purpose

종합 검토 후속. 사용자 보고: "매니저 닫아도 프로세스 종료 안 되는 것 같다". 현재 manager.py의 종료 경로가 몇 가지 시나리오에서 자식 프로세스를 놓칠 위험이 있어 예방 조치.

### 1.2 Background

`manager.py` 분석 (`line 277-282`):

```python
def _taskkill_tree(pid: int):
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], ...)
```

`taskkill /T`는 **호출 시점의 snapshot**만 순회하므로:
- 새로 spawn된 손자/증손자가 누락 가능 (streamlit watchdog, uvicorn reloader 등)
- parent가 먼저 죽으면 descendants가 reparent되어 /T가 놓침
- 응답 대기 없음 → async kill, 후속 코드가 live process를 가정하고 진행

추가 위험:
- `_setup_tray()`가 실패하면 `self.tray_icon`이 None이 되나 `on_close()`는 여전히 `_hide_to_tray`를 호출 → 창이 사라지고 트레이도 없어 사용자가 작업 관리자로 강제 종료 → `atexit` 불발 가능
- 콘솔에서 Ctrl+C 시 signal 핸들러 없어 `_cleanup_all_processes` 미실행

### 1.3 Related
- 2026-04-24 세션 내 manager 확인 context
- `requirements.txt:psutil` (이미 존재, 추가 의존성 없음)

---

## 2. Scope

### 2.1 In Scope

| ID | Item | Effort |
|----|------|--------|
| M1 | `shared/process_utils.py` 신규 — `kill_process_tree(pid, timeout=3.0)`: psutil로 descendants **snapshot-before-kill** + graceful terminate + force kill + taskkill fallback | 20min |
| M2 | `manager.py`에서 `_taskkill_tree` 제거, 모든 호출 지점을 `shared.process_utils.kill_process_tree`로 교체 | 15min |
| M3 | `_setup_tray()`에 try/except 래핑 — 실패 시 `self.tray_icon = None` | 5min |
| M4 | `on_close()` 수정 — tray 없으면 `messagebox.askyesno`로 "정말 종료?" fallback | 10min |
| M5 | `SIGINT` 핸들러 등록 — 콘솔 Ctrl+C 시 main thread에 `_cleanup_and_exit` schedule | 10min |
| M6 | `tests/test_process_utils.py` 신규 — psutil 기반 kill helper 단위 테스트 (실제 subprocess spawn + grandchild 검증) | 25min |

### 2.2 Out of Scope

| Item | Reason |
|------|--------|
| Windows Job Object (pywin32 기반) | psutil snapshot 방식이 pure Python으로 충분. pywin32 의존성 추가 회피 |
| PID 파일 기반 startup 정리 (stale process 재실행 시 감지) | 추후 문제 재발 시 `manager-pid-recovery-v2`로 별도 |
| X 버튼 UX 재설계 (close vs hide-to-tray 혼동) | 기존 디자인 존중. tray 실패 시만 fallback |
| `os._exit(0)` 도입 | atexit 안전망 유지를 위해 `sys.exit(0)` 유지 |
| manager.py GUI 자동 테스트 | GUI 테스트 프레임워크(pytest-qt 등) 도입 범위 |

---

## 3. Acceptance Criteria

| AC | 내용 | 검증 |
|----|------|------|
| AC1 | `shared/process_utils.py` 존재, `kill_process_tree(pid, timeout=3.0)` export | inspect |
| AC2 | psutil으로 descendants 순회 → terminate → `wait_procs` → kill → taskkill fallback 패턴 | code review |
| AC3 | `manager.py`에 `_taskkill_tree` 정의 0건 (전부 `kill_process_tree`로 교체) | grep |
| AC4 | `_setup_tray` 내부 try/except로 예외 흡수, 실패 시 `self.tray_icon = None` | grep/read |
| AC5 | `on_close()`에서 `self.tray_icon is None` 분기로 `messagebox.askyesno` 호출 | grep/read |
| AC6 | `signal.signal(signal.SIGINT, ...)` 등록 | grep |
| AC7 | `tests/test_process_utils.py` — parent + grandchild 모두 kill 검증 테스트 통과 | pytest |
| AC8 | 전체 pytest 222 → 224 (신규 2) passed, 회귀 없음 | pytest |
| AC9 | gap-detector 본 사이클 일치율 ≥ 95% | bkit:gap-detector |

---

## 4. Risks

| Risk | Mitigation |
|------|-----------|
| 테스트가 실제 subprocess를 spawn하므로 Windows AV/CI 환경에서 flaky 가능 | `@pytest.mark.timeout(30)`로 상한, spawner script를 tmp_path에 작성해 격리 |
| psutil `terminate()`가 Windows GUI process에 효과 없는 케이스 | `taskkill /F /T` fallback 유지 |
| SIGINT 핸들러가 Tk mainloop와 경합 | `self.after(0, self._cleanup_and_exit)`로 main thread에 schedule |
| tray 실패 시 `messagebox.askyesno`가 다시 실패 | fallback의 fallback은 생략. 사용자에게 console 에러로 노출되면 Task Manager 사용 유도 |

---

## 5. Timeline

| Phase | Duration |
|-------|---------|
| Plan + Design | 0.3h |
| Act: shared helper + test | 0.4h |
| Act: manager.py 통합 | 0.3h |
| Check: pytest + gap-detector | 0.2h |
| Report | 0.2h |

총 예상: ~1.4h
