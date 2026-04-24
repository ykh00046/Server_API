# manager-orphan-prevention-v1 Completion Report

> **Summary**: manager 종료 시 자식 프로세스 잔존 가능성 완화 — psutil 기반 kill helper + SIGINT 핸들러 + tray 실패 fallback. 신규 의존성 없음.
>
> **Date**: 2026-04-24
> **Match Rate**: 100% (9/9 AC PASS)
> **Status**: Completed

---

## 1. 변경 요약

| 파일 | 변경 |
|------|------|
| `shared/process_utils.py` (신규) | `kill_process_tree(pid, timeout=3.0)` — psutil snapshot-before-kill + wait_procs + taskkill fallback |
| `manager.py` | `_taskkill_tree` 제거 (-6 lines), import 추가, `signal` 핸들러 추가, `_setup_tray` try/except 래핑, `on_close` confirmation dialog fallback |
| `tests/test_process_utils.py` (신규) | 2 tests — parent+grandchild spawn/kill 검증 + non-existent PID idempotent |

## 2. 검증 결과

- ✅ AC1~AC9 모두 PASS (9/9, 100%)
- ✅ `pytest tests/test_process_utils.py -v` → **2 passed in 1.01s**
- ✅ `pytest tests/ -q` → **224 passed** (222 기존 + 2 신규, 0 regression)
- ✅ `python -c "import py_compile; py_compile.compile('manager.py', doraise=True)"` → ok
- ✅ grep: `_taskkill_tree` 0건, `kill_process_tree` 호출 4건 (atexit + stop_web/api/portal)

## 3. PDCA 메타데이터

```yaml
cycle: manager-orphan-prevention-v1
phase: completed
match_rate: 100
plan: docs/01-plan/features/manager-orphan-prevention-v1.plan.md
design: docs/02-design/features/manager-orphan-prevention-v1.design.md
analysis: docs/03-analysis/manager-orphan-prevention-v1.analysis.md
report: docs/04-report/manager-orphan-prevention-v1.report.md
duration_h: 1.3
trigger: 2026-04-24 사용자 보고 "매니저 닫아도 프로세스 종료 안 되는 것 같다"
```

## 4. 개선 효과

| 시나리오 | Before | After |
|---------|--------|-------|
| 정상 종료 ("완전 종료" tray 메뉴) | `taskkill /T` snapshot race로 grandchild 누락 가능 | psutil snapshot-before-kill로 descendant 전체 terminate 후 wait_procs 확인 |
| Tray 초기화 실패 | 창이 숨겨지고 복귀 불가 → 작업 관리자 필요 | `messagebox.askyesno` fallback으로 정상 종료 가능 |
| 콘솔 Ctrl+C | 핸들러 없음 → SIGINT 무시 또는 강제 종료 → atexit 불발 가능 | `signal.SIGINT` → `self.after(0, cleanup)` → 정상 종료 |
| VBS 배경 실행 (콘솔 없음) | 동일 | `(ValueError, OSError)` 흡수로 silent skip (breaking 없음) |

## 5. 수동 Smoke 검증 권장

사용자 환경에서 다음 시나리오 확인:

1. **완전 종료 경로**:
   - manager 실행 → Dashboard + API 시작
   - Tray 우클릭 "완전 종료"
   - 5초 후 `netstat -ano | findstr ":8000"`, `netstat -ano | findstr ":8502"` — 포트 free 확인

2. **강제 종료 경로**:
   - manager 실행 → Dashboard + API 시작
   - 작업 관리자에서 manager 프로세스 강제 종료
   - atexit이 실행되지 않으므로 이 경로는 본 사이클의 범위 밖 — 후속 `manager-pid-recovery-v2`에서 startup 정리로 커버 예정

3. **Tray fallback**:
   - pystray가 실패하도록 일시적으로 unset (개발자 환경에서만)
   - manager 실행 → X 버튼 클릭 → "종료 확인" dialog 노출 검증

## 6. 후속 후보

| 사이클 | 우선순위 | 근거 |
|--------|:-------:|------|
| `manager-pid-recovery-v2` | Low | 강제 종료(작업 관리자)로 남은 orphan PID를 재실행 시 감지/정리. 본 사이클로 충분히 예방되면 불필요 |
| `manager-gui-smoke-tests` | Low | pytest-qt 기반 GUI 자동화 테스트 (현재 수동) |
| 기타 chart-tokens, observability-v3 등 | Low | 원 검토의 Critical/High는 모두 해결 상태 |

## 7. Lessons Learned

- **Pure-Python 대안이 네이티브 의존성을 대체**: Windows Job Object(pywin32) 없이도 psutil snapshot + wait_procs로 동등 효과. requirements.txt 변경 불필요.
- **GUI 코드는 helper 추출로 테스트 가능**: `manager.py`의 Tk/pystray 의존성은 pytest를 어렵게 하지만 kill 로직 분리 후 실제 subprocess spawn 테스트 가능.
- **Fallback을 계층화**: psutil → taskkill / tray init → confirmation dialog / SIGINT → silent skip. 각 layer 실패가 다음 layer에 흡수.
