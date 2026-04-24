# custom-query-thread-safety Design Document

> **Summary**: `execute_custom_query` timeout 경로 race 제거 + 예외 스택트레이스 기록 구현 설계
>
> **Date**: 2026-04-24
> **Status**: Design

---

## 1. Architecture Decisions

### AD-1: conn lifecycle 변경 — timeout 시 GC에 위임

**선택지**

| 옵션 | 동작 | 단점 | 결정 |
|------|------|------|------|
| A. 현재: `conn.interrupt()` → `join(1s)` → `conn.close()` | run_query가 1s 안에 안 끝나면 race | crash 위험 | ✗ |
| B. `threading.Lock`으로 close 직렬화 | 가능하지만 run_query가 lock 안 잡는 상태 | 복잡, 검증 어려움 | ✗ |
| C. `daemon=True` thread + timeout 시 close 생략, GC에 위임 | run_query가 스스로 끝날 때까지 conn 유효. daemon이므로 process 종료 시 강제 정리 | conn leak 가능(희귀) | **✓** |

**선택 근거 (C)**:
- CUSTOM_QUERY_TIMEOUT_SEC(기본 10s) 도달은 **희귀 event** (AI가 보통 5s 이내 완료).
- Leak되는 conn 1개의 영향은 무시 가능(SQLite read-only, 매 manager 재시작 시 reset).
- 단순성 > 완벽한 리소스 회수 trade-off가 합리적.
- 운영 모니터링을 위해 `logger.warning`으로 기록.

### AD-2: `check_same_thread=False` 명시

현재 코드는 이미 main thread에서 connect + run_query thread에서 execute로 cross-thread 사용 중. Python 3.12+에서 제약이 완화되었으나 `check_same_thread=False` 명시가:
- 명시적 의도 선언 (cross-thread 사용 intentional)
- Python 이전 버전과의 호환성 방어
- 경고 메시지 회피

주의: SQLite 문서상 **write operation은 사용자가 직렬화해야** 하지만 본 함수는 `mode=ro`(read-only) 연결이라 write 없음 → 안전.

### AD-3: `logger.exception` 도입

`str(e)`만 저장하던 패턴이 디버깅 곤란의 원인. `logger.exception`은:
- 자동으로 스택트레이스 포함
- ERROR 레벨로 기록
- `result["error"] = str(e)`는 유지 (AI에게는 간결한 메시지 전달)

---

## 2. File-Level Changes

### 2.1 `api/tools.py`

```diff
  # Execute with timeout (3 seconds)
  # Dedicated connection required for conn.interrupt() — cannot use thread-local cache.
  # Apply PRAGMA settings so custom queries get same perf as regular API queries.
  db_uri = f"file:{DB_FILE.absolute()}?mode=ro"
- conn = sqlite3.connect(db_uri, uri=True, timeout=DB_TIMEOUT)
+ # check_same_thread=False: the connection is created on the main thread but
+ # execute runs on a worker thread (see run_query below). Both patterns require
+ # this flag; mode=ro makes write-race concerns moot.
+ conn = sqlite3.connect(db_uri, uri=True, timeout=DB_TIMEOUT, check_same_thread=False)
  conn.row_factory = sqlite3.Row
  _apply_pragma_settings(conn)
  ...
  def run_query(connection):
      try:
          cursor = connection.execute(sql_clean, bound_params)
          rows = cursor.fetchall()
          result["rows"] = [dict(r) for r in rows]
          result["columns"] = [desc[0] for desc in cursor.description] if cursor.description else []
      except Exception as e:
          result["error"] = str(e)
+         logger.exception("[custom_query] run_query failed")
  
- thread = threading.Thread(target=run_query, args=(conn,))
+ # daemon=True: if run_query gets stuck past the timeout + 1s grace, the thread
+ # should not keep the Python process alive. Connection is left for GC rather
+ # than explicit close() to avoid a cross-thread close/execute race.
+ thread = threading.Thread(target=run_query, args=(conn,), daemon=True)
  thread.start()
  thread.join(timeout=CUSTOM_QUERY_TIMEOUT_SEC)
  
  if thread.is_alive():
      conn.interrupt()  # Cancel the running SQLite query
      thread.join(timeout=1.0)
-     conn.close()
+     # Do NOT close conn here — run_query may still be in C-level fetch.
+     # The daemon thread will exit with the process; GC releases the connection.
+     logger.warning(
+         f"[custom_query] timeout after {CUSTOM_QUERY_TIMEOUT_SEC}s; "
+         f"leaked connection pending GC (daemon thread still alive)"
+     )
      return {
          "status": "error",
          "code": "QUERY_TIMEOUT",
          "message": f"Query timeout (exceeded {CUSTOM_QUERY_TIMEOUT_SEC:.0f} seconds). Please simplify your query."
      }
  
  conn.close()
```

### 2.2 `tests/` 변경 없음

현재 timeout path를 실제로 trigger하는 단위 테스트는 없음(실 DB 필요). 본 변경은 backward compat 유지 + 내부 lifecycle만 변경이라 기존 32 `test_sql_validation.py` tests + 전체 224 tests가 회귀 없이 pass해야 함.

---

## 3. Test Plan

| 검증 | 명령 | 기대 |
|------|------|------|
| AC1 | `grep -n "check_same_thread=False" api/tools.py` | 1건 |
| AC2 | `grep -n "daemon=True" api/tools.py` | 1건 |
| AC3 | `awk '/if thread.is_alive/,/return {/' api/tools.py \| grep "conn.close()"` | 0건 |
| AC4 | `grep -n "logger.warning.*timeout" api/tools.py` | 1건 (timeout path) |
| AC5 | `grep -n "logger.exception" api/tools.py` | 1건 (run_query) |
| AC6 | `pytest tests/ -q` | 224 passed |

---

## 4. Rollback

단일 함수(`execute_custom_query`) 내부 변경이라 commit revert로 즉시 원복.

---

## 5. Open Questions

- (해결) conn leak 감수 가능성 → AD-1에서 희귀 event + 프로세스 재시작 회수 전제로 OK.
- (해결) `check_same_thread=False` 안전성 → read-only connection이라 write race 없음.
