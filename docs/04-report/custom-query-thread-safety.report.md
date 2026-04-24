# custom-query-thread-safety Completion Report

> **Summary**: `execute_custom_query` timeout 경로의 cross-thread `conn.close()` race 제거 + `run_query` 예외 스택트레이스 기록. 재검토 Medium 2건 해소.
>
> **Date**: 2026-04-24
> **Match Rate**: 100% (7/7 AC)
> **Status**: Completed

---

## 1. 변경 요약

| ID | 변경 | 위치 |
|----|------|------|
| T1 | `sqlite3.connect(..., check_same_thread=False)` 명시 | `api/tools.py:663-669` |
| T2 | `threading.Thread(..., daemon=True)` | `api/tools.py:697-701` |
| T3 | timeout 경로 `conn.close()` 제거 + 주석으로 rationale 명시 | `api/tools.py:705-718` |
| T4 | timeout 경로 `logger.warning` 추가 ("leaked connection pending GC") | `api/tools.py:710-713` |
| T5 | `run_query` except에 `logger.exception("[custom_query] run_query failed")` | `api/tools.py:695` |

## 2. 검증 결과

- ✅ AC1~AC7 모두 PASS (7/7, 100%)
- ✅ `pytest tests/ -q --ignore=tests/test_smoke_e2e.py` → **224 passed** (0 regression)
- ✅ grep: `check_same_thread=False`/`daemon=True` 각 1건, timeout path `conn.close()` 0건, `logger.warning`/`logger.exception` 신규 1건씩

## 3. 해결한 Medium 이슈

| ID | 문제 | 해결 |
|----|------|------|
| **M-NEW-1** | `conn.interrupt() → join(1s) → conn.close()` 순서에서 run_query가 fetchall 중일 때 close() 호출 → undefined behavior | `daemon=True` + timeout 경로 close 제거. conn은 run_query가 끝나면 GC가 수거 |
| **M-NEW-2** | `except Exception as e: result["error"] = str(e)` — 스택트레이스 누락 | `logger.exception` 추가. AI-facing `str(e)`는 유지 |

## 4. PDCA 메타데이터

```yaml
cycle: custom-query-thread-safety
phase: completed
match_rate: 100
plan: docs/01-plan/features/custom-query-thread-safety.plan.md
design: docs/02-design/features/custom-query-thread-safety.design.md
analysis: docs/03-analysis/custom-query-thread-safety.analysis.md
report: docs/04-report/custom-query-thread-safety.report.md
duration_h: 0.6
trigger: 2026-04-24 재검토 code-analyzer (M-NEW-1, M-NEW-2)
```

## 5. Trade-off: conn leak on timeout

| 항목 | 영향 |
|------|------|
| Leak 규모 | timeout 1회당 SQLite `Connection` 객체 1개 |
| 복구 | run_query가 결국 완료 → 참조 해제 → GC가 회수 / 최악의 경우 process 재시작 시 자동 회수 |
| 발생 빈도 | CUSTOM_QUERY_TIMEOUT_SEC=10s는 희귀 event (AI 보통 5s 이내 완료) |
| 판단 | race 위험 < leak 비용 — 실용적 trade-off |
| 모니터링 | `logger.warning` 로그로 운영 추적 가능 |

## 6. Lessons Learned

- 희귀 timeout edge case에서 엄격한 close() 보단 GC + daemon 패턴이 실용적.
- `logger.exception` (로그용) + `str(e)` (응답용) 병행으로 양쪽 요구 충족.
- Cross-thread sqlite3 사용은 `check_same_thread=False` 명시가 정석.

## 7. 후속 후보

남은 Medium (모두 이전 사이클부터 유예):
- M1 loading.py CSS 중복 inject (→ `loading-css-dedup`)
- M3 notifications.py 멀티사용자 누설 (→ `notifications-session-state`)
- M4 presets session_state 휘발 (→ `presets-persistence`)
- M7 _session_store in-memory (→ Redis 전환, 멀티워커 확장 시)

모두 Low~Medium 우선순위. 당장 배포 영향 없음.
