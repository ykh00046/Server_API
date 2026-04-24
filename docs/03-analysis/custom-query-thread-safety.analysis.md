# custom-query-thread-safety Analysis Document

> **Summary**: Cycle 10 갭 분석 — 7/7 AC PASS (100%)
>
> **Date**: 2026-04-24
> **Status**: Analysis (passed)

---

## 1. AC 검증

| AC | 항목 | 결과 | 근거 |
|----|------|:----:|------|
| AC1 | `check_same_thread=False` 명시 | PASS | `api/tools.py:668` |
| AC2 | `daemon=True` 스레드 | PASS | `api/tools.py:701` |
| AC3 | timeout 블록 내 `conn.close()` 제거 | PASS | grep 0건 (주석으로 명시) |
| AC4 | timeout 경로 `logger.warning` | PASS | `api/tools.py:710` — "timeout after Ns" + "leaked connection" 메시지 |
| AC5 | `run_query` except에 `logger.exception` | PASS | `api/tools.py:695` |
| AC6 | pytest 224 passed 유지 | PASS | 9.40s / 224 passed, 0 regression |
| AC7 | design AD-1/AD-2/AD-3 일치 | PASS | 모든 구현이 설계안과 라인 단위 일치 |

**일치율: 7/7 = 100%**

## 2. 해결한 Medium 이슈

| ID | 이전 위험 | 해결 방식 |
|----|----------|----------|
| **M-NEW-1** (conn cross-thread race) | timeout 1s grace 후 `conn.close()` 호출 시 run_query thread가 여전히 C-level `fetchall` 중이면 undefined behavior | `daemon=True` 스레드 + timeout 경로의 `close()` 제거 + GC 위임. `check_same_thread=False`로 python 3.11/3.12 경고 회피 |
| **M-NEW-2** (스택트레이스 누락) | `except Exception as e: result["error"] = str(e)` → 디버깅 어려움 | `logger.exception` 추가로 스택트레이스 + ERROR 레벨 기록. `str(e)`는 AI 응답용으로 유지 |

## 3. Iteration 필요 여부

불필요 (100%).

## 4. Lessons Learned

- **희귀 edge case에서는 엄격한 resource cleanup 대신 GC + daemon 패턴이 실용적**: timeout 도달이 희귀한 운영 환경(AI tool, 10s 상한)에서는 완벽한 `conn.close()`보다 cross-thread race 제거가 더 중요. daemon thread가 process 종료 시 강제 정리해 leak 확장 방지.
- **`logger.exception` vs `str(e)` 병행 사용**: 로그는 full traceback (운영자용), 반환값은 `str(e)` (AI / 사용자 메시지용) — 양쪽 요구 동시 충족.
- **cross-thread sqlite3 사용은 `check_same_thread=False` 명시가 정석**: python 버전별 동작 차이로 silent misuse가 가능하므로, 의도적 cross-thread 설계는 명시적으로 옵트인하는 것이 안전하고 readable.
