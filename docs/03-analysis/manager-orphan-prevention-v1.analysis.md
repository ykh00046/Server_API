# manager-orphan-prevention-v1 Analysis Document

> **Summary**: Cycle 8 갭 분석 — 9/9 AC PASS (100%)
>
> **Date**: 2026-04-24
> **Status**: Analysis (passed)

---

## 1. AC 검증

| AC | 항목 | 결과 | 근거 |
|----|------|:----:|------|
| AC1 | `kill_process_tree(pid, timeout=3.0)` export | PASS | `shared/process_utils.py:19` 시그니처 일치 |
| AC2 | snapshot → terminate → wait_procs → kill → taskkill fallback | PASS | `shared/process_utils.py:35-72` 전체 패턴 + NoSuchProcess 가드 |
| AC3 | `manager.py`에 `_taskkill_tree` 정의 0건 | PASS | grep 0건, `kill_process_tree` 호출 4건 (line 51, 546, 567, 586) |
| AC4 | `_setup_tray` try/except + `tray_icon = None` 선행 초기화 | PASS | `manager.py:640-653` |
| AC5 | `on_close` tray None 분기 + `messagebox.askyesno` | PASS | `manager.py:688-704` |
| AC6 | `signal.signal(SIGINT, ...)` + try/except | PASS | `manager.py:326-329` `(ValueError, OSError)` 흡수 |
| AC7 | `test_process_utils.py` 2 tests pass | PASS | 2 passed in 1.01s |
| AC8 | pytest 222 → 224 passed | PASS | 전체 회귀 0 |
| AC9 | gap-detector ≥ 95% | PASS | 100% 측정 |

**일치율: 9/9 = 100%**

## 2. 설계 이상 개선점

- **NoSuchProcess 가드**: design 의도에는 있었으나 구현이 추가 layer(`children(recursive=True)` 호출 중 race)로 보강 → idempotent cleanup 강화.
- **Non-console env 대응**: SIGINT 핸들러를 `(ValueError, OSError)` 이중 흡수로 래핑 — VBS 배경 실행 환경에서도 깨지지 않음.
- **Tray 실패 로그 가시화**: `print(..., flush=True)`로 콘솔에 표시되어 dev 환경에서 원인 파악 용이.

## 3. 커버리지

| 개선 대상 | 해결 방식 |
|----------|---------|
| `taskkill /T` snapshot race | psutil snapshot-before-kill |
| Async kill (정말 죽었는지 미확인) | `wait_procs(timeout)` 추가로 graceful exit 확인 |
| Windows GUI 프로세스 edge case | taskkill fallback 유지 |
| Tray 초기화 실패 시 창 사라짐 | on_close confirmation dialog fallback |
| 콘솔 Ctrl+C 시 cleanup 미실행 | SIGINT 핸들러 등록 |

## 4. Iteration 필요 여부

불필요 (100%).

## 5. Lessons Learned

- **Pure-Python 대안이 네이티브 의존성을 대체**: Windows Job Object(pywin32) 도입 대신 psutil snapshot + wait_procs 조합으로 신규 의존성 없이 동등 효과 달성.
- **GUI 코드는 helper 추출로 테스트성 확보**: `manager.py`는 Tk/pystray 의존성이 많아 pytest 불가능했으나 kill 로직을 `shared/`로 옮기면서 실제 subprocess spawn 검증 가능해짐.
- **실패 fallback을 계층화**: psutil kill 실패 → taskkill fallback / tray init 실패 → confirmation dialog / SIGINT 등록 실패 → silent skip — 각 layer 실패가 다음 layer에 의해 처리됨.
