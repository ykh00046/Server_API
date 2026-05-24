# webhook-async-dispatch-v2 Design Document

> **Cycle**: webhook-async-dispatch-v2
> **Date**: 2026-05-25
> **Status**: Design (locked for Act phase)
> **Companion**: [Plan](../../01-plan/features/webhook-async-dispatch-v2.plan.md)

---

## 1. Architecture Overview

```
   ┌──────────────────┐
   │ emit_event()     │  caller (e.g. router, future ERP hook)
   │  sync=False(기본)│
   └────────┬─────────┘
            │ store.enqueue_delivery(...) — fast, returns delivery_id
            ▼
   ┌──────────────────────────────────────────────┐
   │ webhook_deliveries   (SQLite, status='queued',│
   │                       attempt=1,              │
   │                       next_attempt_at=now)    │
   └──────────────────┬───────────────────────────┘
                      │
                      │ tick (every 0.5s)
                      ▼
   ┌──────────────────────────────────────────────┐
   │ WebhookDispatchWorker (daemon thread)        │
   │  while not _shutdown.is_set():               │
   │    due = store.claim_due_deliveries(now)     │
   │    for d in due:                             │
   │      r = dispatcher.send(...)                │
   │      store.record_attempt(d.id, r, ...)      │
   └──────────────────┬───────────────────────────┘
                      │
                      │ Pass: status='success'
                      │ Fail+attempt<MAX: status='retrying',
                      │                   next_attempt_at=now+backoff(attempt)
                      │ Fail+attempt>=MAX: status='dead'
                      ▼
   ┌──────────────────┐
   │ webhook_deliveries (final row state) │
   └──────────────────┘

   sync=True / /test endpoint:
     emit_event → dispatcher.send (직접) → finalize  (v1과 동일)
```

**계층 책임**
- `store.py` — 큐 적재·claim·attempt 기록 (단일 SQLite write 경로).
- `backoff.py` — 순수 함수. 다음 지연 계산, jitter 적용. DI 가능한 `random_fn`.
- `worker.py` — 스레드 루프 + 셧다운. 비즈니스 결정 0 (claim → dispatch → record).
- `events.py` — sync/async 분기, 호출자에게 즉시 또는 동기적으로 결과 반환.
- `routers/notifications.py` — `/queue/stats`, `/deliveries/{id}/retry` 2 라우트 추가.
- `main.py` — FastAPI lifespan에서 worker.start/stop.

---

## 2. Data Model Migration

### 2.1 `webhook_deliveries` 컬럼 추가

```sql
-- Idempotent migration in store._ensure_schema after the v1 CREATE TABLE block.
-- For each column, PRAGMA table_info(webhook_deliveries) is checked; if the
-- column is absent, ALTER TABLE ... ADD COLUMN is executed.

ALTER TABLE webhook_deliveries ADD COLUMN attempt INTEGER NOT NULL DEFAULT 1;
ALTER TABLE webhook_deliveries ADD COLUMN next_attempt_at TEXT;
ALTER TABLE webhook_deliveries ADD COLUMN enqueued_at TEXT;

-- Optional index for the worker's hot query
CREATE INDEX IF NOT EXISTS idx_deliveries_due
    ON webhook_deliveries(status, next_attempt_at);
```

**왜 idempotent ALTER?**
- 기존 `notifications.db`가 운영 환경에 이미 존재할 수 있음 (v1 배포 후).
- `_ensure_schema_v2()`는 한 번만 실행되도록 `_schema_v2_initialized` set로 가드.
- `ALTER TABLE ADD COLUMN`은 SQLite에서 안전 (NOT NULL DEFAULT만 허용).

### 2.2 Status 값 확장

| 값 | 의미 | 사용처 |
|----|------|-------|
| `queued` | enqueue 직후, 워커 처리 대기 | async emit_event |
| `in_flight` | 워커가 잡았지만 dispatcher 호출 중 (잠시) | worker 내부 |
| `retrying` | 한 번 이상 실패 + 재시도 대기 (next_attempt_at 미래) | worker |
| `success` | 2xx 응답 | worker / sync |
| `failure` | 4xx 또는 단발성 실패 — attempt < MAX 시는 `retrying`으로 덮어씀; **응답이 4xx**면 즉시 failure로 종결 (재시도 안 함) | worker / sync |
| `dead` | attempt ≥ MAX인 영구 실패 | worker |
| `skipped` | (v1) 비활성/미구독 — 본 사이클 변경 없음 | (현재 미사용) |

**왜 4xx는 재시도 안 하나?** 외부 시스템이 명시적으로 "이 요청을 받지 않겠다"는 신호 (400 invalid signature, 401 auth, 410 gone). 재시도해도 같은 결과 → 큐만 막힘. 5xx와 네트워크 예외만 재시도 대상.

### 2.3 신규 store 함수

```python
# All keyword-only after the first positional, per feedback_default_shadowing.

def enqueue_delivery(
    webhook_id: int,
    event_type: str,
    payload: Mapping[str, Any],
    *,
    now_iso: str | None = None,
) -> int:
    """Insert a queued delivery row. Returns delivery_id."""

def claim_due_deliveries(
    *, now_iso: str, limit: int
) -> list[ClaimedDelivery]:
    """
    Atomically transition up-to-`limit` rows where
      status in ('queued','retrying') AND next_attempt_at <= now_iso
    to status='in_flight', returning the claimed rows joined with webhook
    (url, secret) so dispatcher can be called without re-querying.
    """

def record_attempt(
    delivery_id: int,
    *,
    outcome: DispatchResult,
    next_status: str,                 # 'success' | 'failure' | 'retrying' | 'dead'
    next_attempt_at: str | None,      # ISO, only for 'retrying'
    attempt: int,
) -> None:
    """Finalize one attempt — update status/response/duration/attempt/next_attempt_at."""

def queue_stats() -> dict[str, int]:
    """
    Returns:
      {"queued": n, "in_flight": n, "retrying": n,
       "success_24h": n, "failure_24h": n, "dead": n}
    """

def requeue_delivery(delivery_id: int) -> bool:
    """
    Move a delivery (regardless of current status) back to status='queued',
    attempt=1, next_attempt_at=now. Returns False if id not found.
    """
```

`ClaimedDelivery` (dataclass): `id, webhook_id, event_type, payload, attempt, url, secret`.

### 2.4 claim 원자성

```sql
-- Inside a single transaction
BEGIN IMMEDIATE;
SELECT d.id, d.webhook_id, d.event_type, d.payload, d.attempt,
       w.url, w.secret
  FROM webhook_deliveries d
  JOIN webhooks w ON w.id = d.webhook_id
 WHERE d.status IN ('queued','retrying')
   AND (d.next_attempt_at IS NULL OR d.next_attempt_at <= ?)
   AND w.active = 1
 ORDER BY d.next_attempt_at ASC, d.id ASC
 LIMIT ?;

-- For each row r in the SELECT above:
UPDATE webhook_deliveries SET status='in_flight' WHERE id=? AND status IN ('queued','retrying');
COMMIT;
```

**왜 BEGIN IMMEDIATE?** 단일 워커 가정이지만 운영에서 가끔 외부 ad-hoc 스크립트가 DB를 만질 수 있음. IMMEDIATE는 write lock 즉시 획득 — race window 0.

---

## 3. Backoff (`api/notifications/backoff.py`)

```python
from __future__ import annotations
import random
from typing import Callable

# attempt → base delay (seconds). attempt is 1-based and indicates the
# attempt that just FINISHED (so attempt=1 result needs delay before
# attempt=2 begins).
_BASE_DELAYS = [1, 5, 25, 125, 625]  # seconds; index 0 used for attempt=1

MAX_BACKOFF_SEC = 3600  # 60-minute cap (also enforced on Retry-After)


def next_delay(
    attempt: int,
    *,
    max_attempts: int,
    retry_after_sec: float | None = None,
    random_fn: Callable[[], float] = random.random,
) -> float | None:
    """
    Returns delay in seconds before the NEXT attempt, or None if no further
    attempt should be made (attempt >= max_attempts).

    If retry_after_sec is provided (positive), it takes priority over the
    base schedule (still subject to MAX_BACKOFF_SEC cap and ±20% jitter).
    """
    if attempt >= max_attempts:
        return None
    if retry_after_sec is not None and retry_after_sec > 0:
        base = min(float(retry_after_sec), float(MAX_BACKOFF_SEC))
    else:
        idx = min(attempt - 1, len(_BASE_DELAYS) - 1)
        base = float(_BASE_DELAYS[idx])
    # ±20% jitter
    jitter = (random_fn() - 0.5) * 0.4  # in [-0.2, +0.2)
    delayed = base * (1.0 + jitter)
    return max(0.0, min(delayed, float(MAX_BACKOFF_SEC)))
```

**Test seam**: `random_fn=lambda: 0.5` → jitter=0 → deterministic delays for tests.

---

## 4. Worker (`api/notifications/worker.py`)

```python
from __future__ import annotations
import threading
import time
from typing import Callable

import httpx

from shared import get_logger
from shared.config import (
    WEBHOOK_MAX_ATTEMPTS,
    WEBHOOK_WORKER_TICK_SEC,
    WEBHOOK_WORKER_BATCH,
)
from . import store, dispatcher
from .backoff import next_delay

logger = get_logger(__name__)


class WebhookDispatchWorker:
    def __init__(
        self,
        *,
        tick_sec: float | None = None,
        batch_size: int | None = None,
        max_attempts: int | None = None,
        transport: httpx.BaseTransport | None = None,  # test seam
        clock: Callable[[], float] = time.time,        # test seam
        now_iso_fn: Callable[[], str] | None = None,   # test seam
    ) -> None:
        self.tick_sec = float(tick_sec if tick_sec is not None else WEBHOOK_WORKER_TICK_SEC)
        self.batch_size = int(batch_size if batch_size is not None else WEBHOOK_WORKER_BATCH)
        self.max_attempts = int(max_attempts if max_attempts is not None else WEBHOOK_MAX_ATTEMPTS)
        self._transport = transport
        self._clock = clock
        self._now_iso = now_iso_fn or store._now_iso
        self._shutdown = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._shutdown.clear()
        t = threading.Thread(
            target=self._run, name="WebhookDispatchWorker", daemon=True
        )
        self._thread = t
        t.start()
        logger.info("[webhook.worker] started tick=%.2fs batch=%d max_attempts=%d",
                    self.tick_sec, self.batch_size, self.max_attempts)

    def stop(self, *, timeout: float = 2.0) -> None:
        self._shutdown.set()
        t = self._thread
        if t is not None:
            t.join(timeout=timeout)
            if t.is_alive():
                logger.warning(
                    "[webhook.worker] stop timeout — leaving daemon thread to GC"
                )  # feedback_timeout_daemon_gc
        self._thread = None

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def tick_once(self) -> int:
        """One iteration of the loop body. Returns # of deliveries processed.
        Public for tests so they don't have to time-race against the loop."""
        claimed = store.claim_due_deliveries(
            now_iso=self._now_iso(), limit=self.batch_size
        )
        for cd in claimed:
            outcome = dispatcher.send(
                url=cd.url, secret=cd.secret,
                event_type=cd.event_type,
                delivery_id=cd.id, payload=cd.payload,
                transport=self._transport,
            )
            self._finalize(cd, outcome)
        return len(claimed)

    def _finalize(self, cd, outcome) -> None:
        if outcome.status == "success":
            store.record_attempt(
                cd.id, outcome=outcome, next_status="success",
                next_attempt_at=None, attempt=cd.attempt,
            )
            return
        # Failure path — decide retry vs dead vs final-failure (4xx).
        # 4xx (client error): no retry, mark 'failure' immediately.
        rs = outcome.response_status
        if rs is not None and 400 <= rs < 500:
            store.record_attempt(
                cd.id, outcome=outcome, next_status="failure",
                next_attempt_at=None, attempt=cd.attempt,
            )
            return
        # 5xx or network: maybe retry.
        retry_after = _parse_retry_after(outcome)
        delay = next_delay(
            cd.attempt, max_attempts=self.max_attempts,
            retry_after_sec=retry_after,
        )
        if delay is None:
            store.record_attempt(
                cd.id, outcome=outcome, next_status="dead",
                next_attempt_at=None, attempt=cd.attempt,
            )
        else:
            naa = _iso_offset(self._now_iso(), delay)
            store.record_attempt(
                cd.id, outcome=outcome, next_status="retrying",
                next_attempt_at=naa, attempt=cd.attempt + 1,
            )

    def _run(self) -> None:
        while not self._shutdown.is_set():
            try:
                self.tick_once()
            except Exception as e:  # never let worker die
                logger.exception("[webhook.worker] tick error: %s", e)
            self._shutdown.wait(self.tick_sec)


# --- helpers ---
def _parse_retry_after(outcome) -> float | None:
    """Look at response_body? No — dispatcher captures body, not headers,
    in v2 we extend DispatchResult to also expose retry_after_sec when
    the upstream sets Retry-After. See dispatcher change in §5."""
    return getattr(outcome, "retry_after_sec", None)


def _iso_offset(now_iso: str, seconds: float) -> str:
    import datetime as dt
    base = dt.datetime.fromisoformat(now_iso)
    return (base + dt.timedelta(seconds=seconds)).isoformat()
```

---

## 5. Dispatcher 변경 (Retry-After 캡처만)

`DispatchResult`에 `retry_after_sec: float | None = None` 추가.
`dispatcher.send`는 응답 헤더에서 `Retry-After`를 파싱해 채움:

```python
@dataclass
class DispatchResult:
    status: str
    response_status: int | None
    response_body: str | None
    error: str | None
    duration_ms: int
    retry_after_sec: float | None = None  # NEW


# inside send(), after a non-2xx response:
ra = resp.headers.get("Retry-After")
retry_after_sec = None
if ra:
    try:
        v = float(ra)
        if v > 0:
            retry_after_sec = v
    except ValueError:
        pass  # HTTP-date format ignored in v2 (OOS)
```

기존 사용처(`emit_event` sync, `/test`)는 신규 필드 기본값 무시 → 호환 0 영향.

---

## 6. events.py 분기

```python
def emit_event(
    event_type: str,
    payload: Mapping[str, Any],
    *,
    sync: bool = False,                          # NEW
    transport: httpx.BaseTransport | None = None,
) -> list[DeliveryPublic]:
    register_event_type(event_type)
    if sync:
        return _emit_sync(event_type, payload, transport)
    return _emit_async(event_type, payload)


def _emit_sync(event_type, payload, transport):
    # v1 동작 그대로 (copy of current emit_event body)
    ...

def _emit_async(event_type, payload):
    results: list[DeliveryPublic] = []
    for rec in store.list_records(active_only=True):
        if event_type not in rec.event_types:
            continue
        did = store.enqueue_delivery(rec.id, event_type, payload)
        d = store.get_delivery(did)
        if d is not None:
            results.append(d)
    return results
```

`/test` 라우터는 `sync=True`로 호출하도록 변경(또는 dispatcher 직접 호출 유지 — 그대로 둔다).

---

## 7. 라우트 추가 (`api/routers/notifications.py`)

```python
class QueueStats(BaseModel):
    queued: int
    in_flight: int
    retrying: int
    success_24h: int
    failure_24h: int
    dead: int


@router.get("/queue/stats", response_model=QueueStats)
def queue_stats():
    return QueueStats(**store.queue_stats())


@router.post("/deliveries/{delivery_id}/retry", response_model=DeliveryPublic)
def retry_delivery(delivery_id: int):
    if not store.requeue_delivery(delivery_id):
        raise HTTPException(404, f"delivery {delivery_id} not found")
    d = store.get_delivery(delivery_id)
    assert d is not None
    return d
```

OpenAPI 추가: `/notifications/queue/stats`, `/notifications/deliveries/{delivery_id}/retry`. AC9 검증 시 신규 path 집합에 포함.

---

## 8. App 라이프사이클 (`api/main.py` diff)

```python
+ from contextlib import asynccontextmanager
+ from .notifications.worker import WebhookDispatchWorker
+ from shared.config import WEBHOOK_WORKER_ENABLED
+
+ _worker = WebhookDispatchWorker()
+
+ @asynccontextmanager
+ async def _lifespan(app):
+     if WEBHOOK_WORKER_ENABLED:
+         _worker.start()
+     try:
+         yield
+     finally:
+         _worker.stop()

- app = FastAPI(title="...", default_response_class=ORJSONResponse)
+ app = FastAPI(title="...", default_response_class=ORJSONResponse, lifespan=_lifespan)
```

추가 라인 ≤ 12 (AC12 만족).

---

## 9. Config 추가 (`shared/config.py`)

```python
# ----- Webhook async dispatch (webhook-async-dispatch-v2) -----
WEBHOOK_MAX_ATTEMPTS = int(os.getenv("WEBHOOK_MAX_ATTEMPTS", 5))
WEBHOOK_WORKER_TICK_SEC = float(os.getenv("WEBHOOK_WORKER_TICK_SEC", 0.5))
WEBHOOK_WORKER_BATCH = int(os.getenv("WEBHOOK_WORKER_BATCH", 16))
WEBHOOK_WORKER_ENABLED = os.getenv("WEBHOOK_WORKER_ENABLED", "1") not in {
    "0", "false", "False", "no", "off"
}
```

테스트 conftest 또는 fixture에서 `monkeypatch.setenv("WEBHOOK_WORKER_ENABLED", "0")` 호출 가능. 또는 더 깔끔하게 v2의 conftest 추가 fixture로 worker 자동 정지.

---

## 10. 테스트 계획 (`tests/test_notifications_async.py` 신규)

| # | 케이스 | 검증 AC |
|---|--------|---------|
| A1 | `emit_event(...)` 호출 직후 dispatcher.send 호출 0 + queued row 1 | AC1 |
| A2 | worker.tick_once() 1회 → dispatcher 1회 호출, row status='success' | AC1 |
| A3 | 5xx 응답 후 worker tick → status='retrying', attempt=2, next_attempt_at 미래 | AC2 |
| A4 | MAX=2 + 5xx 반복 + 3 tick → status='dead', dispatcher 호출 ≤ 2 | AC3 |
| A5 | `next_delay(1..5, max_attempts=5, random_fn=lambda: 0.5)` = [1,5,25,125,None] (jitter 0) | AC4 |
| A6 | 100회 호출 분포: 모든 값이 base×[0.8, 1.2) 범위 | AC4 |
| A7 | 응답 `Retry-After: 7` 시 next_attempt_at ≈ now+7s±20% | AC5 |
| A8 | `emit_event(..., sync=True)` v1과 동일 (dispatcher 즉시 호출, results status='success') | AC6 |
| A9 | worker 미시작 상태에서 `/test` 200 응답 + delivery success | AC7 |
| A10 | 각 status별 row 삽입 → `GET /queue/stats` 카운트 일치 | AC8 |
| A11 | dead delivery 1건 → `POST /deliveries/{id}/retry` → status='queued', attempt=1 | AC9 |
| A12 | worker.stop(timeout=0.2) — slow handler 주입해도 raise 없이 반환 | AC10 |
| A13 | 4xx 응답 시 status='failure' 한 번, 재시도 0 | (extra) |
| A14 | OpenAPI에 신규 2 path 추가됨 (`/notifications/queue/stats`, `/notifications/deliveries/{delivery_id}/retry`) | (extra) |

**Fixtures**:
- `isolated_db` — v1과 동일 (tmp_path + monkeypatch + store.reset_for_tests)
- `worker_off` — `monkeypatch.setenv("WEBHOOK_WORKER_ENABLED", "0")` + 기존 동작 보장
- `manual_worker(ok_transport)` — `WebhookDispatchWorker(transport=..., max_attempts=..., random_fn=lambda: 0.5)` 인스턴스를 직접 만들고 `tick_once()` 호출하는 패턴
- `fail_transport_5xx` / `fail_transport_4xx` / `retry_after_transport(seconds)` — 응답 헤더 시뮬

기존 `tests/test_notifications.py`는 무수정 — v1 AC11 회귀 보장.

---

## 11. Error Handling

| Layer | 정책 |
|-------|------|
| store.enqueue_delivery | sqlite OperationalError propagate — 호출자(emit_event)가 try/except로 logger.warning 처리 |
| store.claim_due_deliveries | sqlite OperationalError 시 빈 리스트 반환 + logger.warning. 워커는 다음 tick 계속 |
| worker._run | 모든 예외 catch → logger.exception, 다음 tick 계속 (워커 자살 금지) |
| worker.stop | join timeout 초과 시 logger.warning + GC 위임 (raise 안 함) |
| dispatcher.send | v1과 동일 — 절대 raise 안 함 |
| /retry 라우트 | 404만 명시. 그 외는 FastAPI 기본 500 |

---

## 12. 신규 vs 변경 파일 요약

| Path | Type | 추정 lines |
|------|------|-----:|
| `api/notifications/backoff.py` | NEW | 50 |
| `api/notifications/worker.py` | NEW | 140 |
| `api/notifications/store.py` | MODIFIED | +180 (마이그레이션 + 4 신규 함수 + ClaimedDelivery dataclass) |
| `api/notifications/dispatcher.py` | MODIFIED | +12 (Retry-After 파싱) |
| `api/notifications/events.py` | MODIFIED | +25 (sync/async 분기) |
| `api/notifications/__init__.py` | MODIFIED | +1 (worker export 안 함 — internal) |
| `api/routers/notifications.py` | MODIFIED | +30 (2 라우트) |
| `api/main.py` | MODIFIED | +10 (lifespan + worker singleton) |
| `shared/config.py` | MODIFIED | +6 (4 vars) |
| `tests/test_notifications_async.py` | NEW | 320 |

신규 외부 의존성: **0**.

---

## 13. Out-of-Scope (재확인)

- 다중 워커 / 다중 프로세스 — 단일 워커, 단일 process 가정.
- HTTP-date 형식의 `Retry-After` — 정수 초만.
- 자동 housekeeping (성공 delivery 정리) — `webhook-housekeeping-v1`.
- 도메인 emit hook 자동 트리거 — `webhook-domain-emit-v1`.
- Prometheus exporter — 별도 사이클.
- 대시보드 UI — 별도 사이클.
- skipped status 활용 (현재 미사용) — v3 검토.
