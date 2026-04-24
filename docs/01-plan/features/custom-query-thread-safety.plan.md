# custom-query-thread-safety Planning Document

> **Summary**: `execute_custom_query` timeout 경로의 `conn.close()` cross-thread race 해결 + run_query 예외 스택트레이스 기록
>
> **Project**: Server_API (Production Data Hub)
> **Version**: custom-query-thread-safety v1
> **Author**: interojo
> **Date**: 2026-04-24
> **Status**: Plan

---

## 1. Overview

### 1.1 Purpose

2026-04-24 재검토 code-analyzer에서 Medium 2건 신규 발견:
- **M-NEW-1** (`api/tools.py:691-698`): timeout 도달 시 main thread가 `conn.interrupt()` 후 `thread.join(1.0)`으로 대기하지만, 그 1초 안에 run_query thread가 여전히 alive일 수 있음. 이어서 `conn.close()`가 호출되면 **run_query가 아직 cursor/fetchall 진행 중일 때** connection이 닫혀 undefined behavior (SQLite `ProgrammingError` 또는 프로세스 crash 가능).
- **M-NEW-2** (`api/tools.py:682-689`): `run_query` 예외를 `str(e)`로만 보존. 스택트레이스 누락 → 중대 오류 디버깅 곤란.

### 1.2 Background

현재 흐름:
```python
conn = sqlite3.connect(...)                        # main thread (check_same_thread=True default)
thread = threading.Thread(run_query, (conn,))      # non-daemon
thread.start()
thread.join(timeout=CUSTOM_QUERY_TIMEOUT_SEC)      # 10s default

if thread.is_alive():
    conn.interrupt()         # thread-safe OK
    thread.join(timeout=1.0)
    conn.close()             # <-- M-NEW-1 race: run_query may still be running
    return timeout error

conn.close()                  # happy path
```

문제: `thread.is_alive()` 후에도 C extension(fetchall) 중이면 join 1s로 안 끝남. 그 상태에서 `conn.close()` 호출은 race.

### 1.3 Related
- `custom-query-bind-params-v1` (직전 사이클 — 시그니처 확장)
- `security-hardening-v3` (`attach_archive_safe` helper 통합)
- `M-NEW-1`, `M-NEW-2` (2026-04-24 재검토)

---

## 2. Scope

### 2.1 In Scope

| ID | Item | Source | Effort |
|----|------|--------|--------|
| T1 | `sqlite3.connect(..., check_same_thread=False)` 명시 — 이미 cross-thread 사용 중이므로 경고 제거 + 의도 명확화 | M-NEW-1 | 2min |
| T2 | `threading.Thread(..., daemon=True)` — timeout 시 stuck thread가 프로세스 종료 막지 않도록 | M-NEW-1 | 2min |
| T3 | timeout 경로에서 **`conn.close()` 제거** — stuck thread가 aliving 동안 conn 접근 가능. 대신 GC에 위임(daemon thread + circular ref 없음) | M-NEW-1 | 5min |
| T4 | timeout 시 `logger.warning` 추가 — conn leak 발생 사실을 운영 로그에 남김 | M-NEW-1 | 5min |
| T5 | `run_query` 내부 `except Exception as e:`에 `logger.exception(...)` 추가 — str만 기록하는 대신 스택트레이스 포함 | M-NEW-2 | 5min |
| T6 | 기존 pytest 전부 pass 유지 (backward compat) | 회귀 방지 | 5min |

### 2.2 Out of Scope

| Item | Reason |
|------|--------|
| ThreadPoolExecutor 전환 | 현재 패턴으로 충분. cancellation 의미 동등 |
| `asyncio` 기반 재작성 | FastAPI 라우터에서 이미 `asyncio.to_thread`로 감쌀 수 있으나 본 함수는 AI tool이라 sync 유지 적절 |
| conn leak을 psutil로 추적 | 희귀 timeout case에서만 발생, 프로세스 재시작 시 자동 정리 |
| 모든 `str(e)` 패턴 logger.exception화 | 본 함수만 범위 |

---

## 3. Acceptance Criteria

| AC | 내용 | 검증 |
|----|------|------|
| AC1 | `sqlite3.connect`에 `check_same_thread=False` 명시 | grep |
| AC2 | `threading.Thread(..., daemon=True)` | grep |
| AC3 | timeout 경로에 `conn.close()` 호출 0건 (happy path 1건만) | grep |
| AC4 | timeout 경로에 `logger.warning` 호출 존재 (메시지에 "timeout", "leak" 또는 "daemon" 키워드) | grep |
| AC5 | `run_query`의 except 블록에 `logger.exception` 호출 | grep |
| AC6 | 전체 pytest 224 passed 유지 (0 regression) | pytest |
| AC7 | gap-detector 본 사이클 일치율 ≥ 95% | bkit:gap-detector |

---

## 4. Risks

| Risk | Mitigation |
|------|-----------|
| `check_same_thread=False`로 변경 시 happy path 실행이 다른 스레드에서 일어날까 불안 | 코드상 main thread가 connect, run_query thread가 execute → 이미 cross-thread. 변경은 python warning 제거일 뿐 |
| timeout 시 conn leak | daemon thread가 결국 SQLite C-level에서 완료되면 connection 참조 카운트 0 → GC. 최악의 경우도 프로세스 재시작 시 정리. CUSTOM_QUERY_TIMEOUT_SEC 도달은 희귀 |
| `logger.exception` 로그 폭증 | `str(e)` 기존 패턴이 있었던 이유는 AI가 쿼리 실수 자주 발생하기 때문일 수 있음. 하지만 실수 쿼리는 validation 단계에서 걸러지고, run_query까지 도달한 예외는 대부분 DB 환경 이슈 → 스택트레이스 가치 큼 |
| 기존 테스트 회귀 | backward compat (시그니처·반환값 동일). pytest로 확인 |

---

## 5. Timeline

| Phase | Duration |
|-------|---------|
| Plan + Design | 0.2h |
| Act: T1~T5 구현 | 0.3h |
| Check: pytest + gap-detector | 0.1h |
| Report + commit | 0.1h |

총 예상: ~0.7h
