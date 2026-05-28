# webhook-bulk-retry-v1 Design Document

> **Cycle**: webhook-bulk-retry-v1
> **Date**: 2026-05-28
> **Status**: Design (locked for Do phase)
> **Companion**: [Plan](../../01-plan/features/webhook-bulk-retry-v1.plan.md)

---

## 1. Architecture Overview

```
   ┌─────────────────────────────┐
   │ Admin UI 큐 상태 섹션        │  운영자
   │  [💀 dead 전체 재시도] 버튼  │
   └──────────────┬──────────────┘
                  │ api_client.bulk_retry_dead()
                  ▼
   POST /notifications/deliveries/bulk-retry
        body: {statuses:["dead"], webhook_id:null, limit:500, dry_run:false}
                  │
                  ▼
   ┌──────────────────────────────────────────────┐
   │ router.bulk_retry_deliveries                  │
   │  1) statuses ⊆ {"dead","failure"} 검증 (400)  │
   │  2) dry_run? → store.list_retryable_delivery_ids
   │     else    → store.requeue_deliveries        │
   └──────────────┬───────────────────────────────┘
                  ▼
   ┌──────────────────────────────────────────────┐
   │ deliveries_repo (단일 트랜잭션)              │
   │  BEGIN IMMEDIATE                              │
   │  SELECT id WHERE status IN (...) [AND wh=?]   │
   │         ORDER BY id LIMIT ?                   │
   │  UPDATE ... SET status='queued', attempt=1,   │
   │         next_attempt_at=now, resp=NULL        │
   │   WHERE id IN (선택된 id들)                   │
   │  COMMIT  → return [ids]                       │
   └──────────────┬───────────────────────────────┘
                  ▼
   webhook_deliveries: dead/failure → queued (즉시 due)
                  │  (다음 worker tick)
                  ▼
   WebhookDispatchWorker.claim_due_deliveries → dispatch
```

**계층 책임**
- `deliveries_repo.py` — 일괄 SELECT/UPDATE (단일 SQLite write 경로, 트랜잭션 원자성).
- `store.py` — facade re-export only (수정 아님, import 추가만).
- `routers/notifications.py` — 입력 검증(400) + dry_run 분기 + 응답 매핑.
- `api_client.py` — HTTP 래퍼 (pure IO).
- `views.py` — 버튼 + toast (Streamlit only).

---

## 2. Store 레이어 (`api/notifications/deliveries_repo.py`)

### 2.1 상수

```python
# 일괄 재시도가 허용되는 "터미널 실패" 상태의 단일 진실원.
# - dead    : 5xx/네트워크 재시도 소진 (attempt >= MAX)
# - failure : 4xx 영구 실패 또는 v1 sync 단발 실패
# queued/in_flight/retrying/success/skipped 는 일괄 재시도 금지:
#   in_flight 재설정은 double-dispatch, success 재설정은 재발송 위험.
RETRYABLE_TERMINAL_STATUSES: tuple[str, ...] = ("dead", "failure")

_BULK_LIMIT_MAX = 5000
```

### 2.2 읽기 전용 — `list_retryable_delivery_ids`

```python
def list_retryable_delivery_ids(
    *,
    statuses: list[str] | tuple[str, ...],
    webhook_id: int | None = None,
    limit: int,
) -> list[int]:
    """Return ids of deliveries in the given terminal-failure statuses,
    capped at `limit`, ordered by id ASC (oldest first).

    `statuses` is intersected with RETRYABLE_TERMINAL_STATUSES defensively.
    Returns [] if the effective status set is empty.
    """
    eff = _effective_statuses(statuses)
    if not eff:
        return []
    limit = max(1, min(int(limit), _BULK_LIMIT_MAX))
    placeholders = ",".join("?" for _ in eff)
    params: list[Any] = list(eff)
    where_wh = ""
    if webhook_id is not None:
        where_wh = " AND webhook_id = ?"
        params.append(int(webhook_id))
    params.append(limit)
    rows = _get_conn().execute(
        f"""
        SELECT id FROM webhook_deliveries
        WHERE status IN ({placeholders}){where_wh}
        ORDER BY id ASC
        LIMIT ?
        """,
        params,
    ).fetchall()
    return [int(r["id"]) for r in rows]
```

### 2.3 Mutation — `requeue_deliveries`

```python
def requeue_deliveries(
    *,
    statuses: list[str] | tuple[str, ...],
    webhook_id: int | None = None,
    limit: int,
) -> list[int]:
    """Bulk-reset terminal-failure deliveries back to status='queued'
    (attempt=1, next_attempt_at=now, response fields NULL) in a single
    IMMEDIATE transaction. Returns the list of requeued ids.

    Atomicity: ids are SELECTed and UPDATEd inside one BEGIN IMMEDIATE so
    rows that become dead between select and update are simply handled by a
    later call — the returned ids reflect exactly what changed.
    """
    eff = _effective_statuses(statuses)
    if not eff:
        return []
    limit = max(1, min(int(limit), _BULK_LIMIT_MAX))
    conn = _get_conn()
    now = _now_iso()
    try:
        conn.execute("BEGIN IMMEDIATE")
        placeholders = ",".join("?" for _ in eff)
        params: list[Any] = list(eff)
        where_wh = ""
        if webhook_id is not None:
            where_wh = " AND webhook_id = ?"
            params.append(int(webhook_id))
        params.append(limit)
        rows = conn.execute(
            f"""
            SELECT id FROM webhook_deliveries
            WHERE status IN ({placeholders}){where_wh}
            ORDER BY id ASC
            LIMIT ?
            """,
            params,
        ).fetchall()
        ids = [int(r["id"]) for r in rows]
        if ids:
            id_ph = ",".join("?" for _ in ids)
            conn.execute(
                f"""
                UPDATE webhook_deliveries
                SET status='queued', attempt=1, next_attempt_at=?,
                    response_status=NULL, response_body=NULL, error=NULL,
                    duration_ms=0
                WHERE id IN ({id_ph})
                """,
                [now, *ids],
            )
        conn.commit()
        return ids
    except sqlite3.Error as e:
        conn.rollback()
        logger.warning("[notifications.store] bulk requeue failed: %s", e)
        return []


def _effective_statuses(
    statuses: list[str] | tuple[str, ...] | None,
) -> list[str]:
    """Intersect requested statuses with the allow-list, preserving order
    and de-duplicating. Unknown/forbidden statuses are silently dropped
    (router enforces 400; this is defense-in-depth)."""
    if not statuses:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for s in statuses:
        s2 = str(s).strip().lower()
        if s2 in RETRYABLE_TERMINAL_STATUSES and s2 not in seen:
            seen.add(s2)
            out.append(s2)
    return out
```

> `requeue_deliveries`의 UPDATE 컬럼 세트는 단건 `requeue_delivery`(line 246-255)와 **동일**하게 유지 — 동작 일관성(AC10).

### 2.4 store.py facade re-export

```python
# deliveries 블록에 추가
from .deliveries_repo import (
    ...,
    list_retryable_delivery_ids,
    requeue_deliveries,
    RETRYABLE_TERMINAL_STATUSES,
)
```

`__all__` 갱신.

---

## 3. 라우트 (`api/routers/notifications.py`)

### 3.1 스키마 (모듈 내, `QueueStats` 선례)

```python
from pydantic import BaseModel, Field

class BulkRetryRequest(BaseModel):
    statuses: list[str] = Field(default_factory=lambda: ["dead"])
    webhook_id: int | None = None
    limit: int = Field(default=500, ge=1, le=5000)
    dry_run: bool = False

class BulkRetryResult(BaseModel):
    requeued: int
    ids: list[int]
    dry_run: bool
    statuses: list[str]
    webhook_id: int | None = None
```

### 3.2 엔드포인트 (단건 retry 라우트 **위에** 등록)

```python
_ALLOWED_BULK_STATUSES = set(store.RETRYABLE_TERMINAL_STATUSES)  # {"dead","failure"}

@router.post("/deliveries/bulk-retry", response_model=BulkRetryResult)
def bulk_retry_deliveries(req: BulkRetryRequest):
    # normalize + validate
    requested = [str(s).strip().lower() for s in req.statuses if str(s).strip()]
    if not requested:
        raise HTTPException(
            status_code=400,
            detail="statuses must contain at least one of: "
                   + ", ".join(sorted(_ALLOWED_BULK_STATUSES)),
        )
    invalid = [s for s in requested if s not in _ALLOWED_BULK_STATUSES]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported statuses {invalid}; allowed: "
                   + ", ".join(sorted(_ALLOWED_BULK_STATUSES)),
        )
    if req.dry_run:
        ids = store.list_retryable_delivery_ids(
            statuses=requested, webhook_id=req.webhook_id, limit=req.limit,
        )
    else:
        ids = store.requeue_deliveries(
            statuses=requested, webhook_id=req.webhook_id, limit=req.limit,
        )
    return BulkRetryResult(
        requeued=len(ids),
        ids=ids,
        dry_run=req.dry_run,
        statuses=requested,
        webhook_id=req.webhook_id,
    )
```

> `limit` le=5000 / ge=1 위반은 FastAPI가 422 자동 반환(AC8 후반).

---

## 4. Admin UI

### 4.1 api_client (`dashboard/components/webhook_admin/api_client.py`)

```python
def bulk_retry_dead(
    self,
    *,
    statuses: list[str] | None = None,
    webhook_id: int | None = None,
    limit: int = 500,
    dry_run: bool = False,
) -> dict:
    body: dict[str, Any] = {
        "statuses": statuses if statuses is not None else ["dead"],
        "limit": limit,
        "dry_run": dry_run,
    }
    if webhook_id is not None:
        body["webhook_id"] = webhook_id
    return self._request("POST", "/notifications/deliveries/bulk-retry", json=body)
```

### 4.2 views (`dashboard/components/webhook_admin/views.py`)

`render_queue_stats_section`에 dead 카운트 > 0이면 버튼 추가:

```python
def render_queue_stats_section(client: WebhookAdminClient) -> None:
    st.subheader("📊 큐 상태")
    try:
        stats = client.queue_stats()
    except WebhookAdminError as e:
        toast_error(f"큐 상태 조회 실패: {e}")
        stats = {}
    cards = formatters.format_queue_stats_cards(stats)
    cols = st.columns(len(cards))
    for col, (label, value, _hint) in zip(cols, cards):
        col.metric(label, value)

    dead_n = 0
    try:
        dead_n = int(stats.get("dead", 0) or 0)
    except (TypeError, ValueError):
        dead_n = 0
    if dead_n > 0:
        st.caption(f"포기됨(dead) {dead_n}건이 있습니다.")
        if st.button(f"💀 dead {dead_n}건 전체 재시도", key="webhook_bulk_retry_dead"):
            _do_bulk_retry_dead(client)


def _do_bulk_retry_dead(client: WebhookAdminClient) -> None:
    try:
        out = client.bulk_retry_dead(statuses=["dead"])
    except WebhookAdminError as e:
        toast_error(f"일괄 재시도 실패: {e}")
        return
    n = out.get("requeued", 0)
    toast_success(f"dead delivery {n}건을 재시도 큐로 복귀시켰습니다.")
    st.rerun()
```

- 모듈 레벨 api 호출 0 유지(`test_views_module_does_not_call_api_client_at_import_time` 통과).
- `_do_bulk_retry_dead`는 함수 내부에서만 client 호출.

---

## 5. 테스트 계획

### 5.1 `tests/test_notifications_bulk_retry.py` (신규)

기존 `tests/test_notifications_async.py`의 `isolated_db` / `_create_wh` / `client` 패턴 재사용.

| # | 케이스 | AC |
|---|--------|----|
| B1 | dead 3건 시드 → bulk-retry(기본) → requeued=3, 모두 queued, ids 일치 | AC1 |
| B2 | dead 2 + failure 2 + success 1 → statuses=["dead","failure"] → 4건 재큐잉, success 미변경 | AC2 |
| B3 | dead 2건 → dry_run=true → DB 미변경(여전히 dead) + ids 2개 반환 | AC3 |
| B4 | wh#1 dead 2 + wh#2 dead 1 → webhook_id=wh1 → wh1 2건만 queued, wh2 dead 유지 | AC4 |
| B5 | statuses=["success"] → 400 / statuses=["queued","dead"] → 400 | AC5 |
| B6 | statuses=[] → 400 | AC6 |
| B7 | dead 0건 상태 → 200, requeued=0, ids=[] | AC7 |
| B8 | dead 5건 + limit=2 → 2건만(id ASC) 재큐잉, 나머지 dead / limit=6000 → 422 | AC8 |
| B9 | dead 1건 bulk-retry 후 worker.tick_once(ok transport) → status='success' | AC9 |
| B10 | dead 1건 bulk-retry 후 raw row: attempt=1, next_attempt_at != NULL, response_status NULL | AC10 |
| B11 | OpenAPI paths에 `/notifications/deliveries/bulk-retry` 포함 | AC11 |

시드 헬퍼: 직접 INSERT (test_notifications_async.py AC8/AC9 패턴 — `webhook_deliveries`에 status별 row).

### 5.2 `tests/test_webhook_admin_ui.py` (추가)

| # | 케이스 | AC |
|---|--------|----|
| U1 | `bulk_retry_dead(statuses=["dead"])` → POST `/notifications/deliveries/bulk-retry`, body 확인, 응답 반환 | AC12 |
| U2 | `bulk_retry_dead(webhook_id=7, dry_run=True)` → body에 webhook_id/dry_run 반영 | AC12 |
| U3 | views.py 소스에 `bulk_retry_dead`/`bulk-retry` 버튼 와이어링 존재 + 모듈 레벨 호출 0 | AC13 |

---

## 6. Error Handling

| Layer | 정책 |
|-------|------|
| `list_retryable_delivery_ids` | 빈 effective statuses → [] (라우트가 400 선처리). sqlite 예외는 propagate(읽기) |
| `requeue_deliveries` | sqlite 예외 시 rollback + logger.warning + [] 반환(부분 커밋 없음) |
| 라우트 검증 | 빈/허용외 statuses 400, limit 범위 422(FastAPI), 그 외 500 |
| api_client | 기존 `_request` 규약(4xx/5xx→WebhookAdminError, 타임아웃 status=None) |
| views | try/except로 toast_error, 페이지 크래시 방지 |

---

## 7. 신규 vs 변경 파일 요약

| Path | Type | 추정 lines |
|------|------|-----:|
| `api/notifications/deliveries_repo.py` | MODIFIED | +75 (상수 + 2 함수 + _effective_statuses) |
| `api/notifications/store.py` | MODIFIED | +4 (re-export) |
| `api/routers/notifications.py` | MODIFIED | +45 (2 스키마 + 라우트 + 검증) |
| `dashboard/components/webhook_admin/api_client.py` | MODIFIED | +18 (bulk_retry_dead) |
| `dashboard/components/webhook_admin/views.py` | MODIFIED | +25 (버튼 + _do_bulk_retry_dead) |
| `tests/test_notifications_bulk_retry.py` | NEW | ~230 |
| `tests/test_webhook_admin_ui.py` | MODIFIED | +35 (3 케이스) |

신규 외부 의존성: **0**.

---

## 8. Out-of-Scope (재확인)

- dead row 영구 삭제/housekeeping — `webhook-housekeeping-v1`.
- `is_retryable_status`의 `failed`↔`failure` 불일치 수정 — 리포트 기록만.
- dry_run 결과 프리뷰 테이블 UI — 후속.
- 재시도 진행률 스트리밍 — 동기 일괄로 충분.
