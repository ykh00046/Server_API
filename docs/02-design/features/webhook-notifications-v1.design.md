# webhook-notifications-v1 Design Document

> **Cycle**: webhook-notifications-v1
> **Date**: 2026-05-24
> **Status**: Design (locked for Act phase)
> **Companion**: [Plan](../../01-plan/features/webhook-notifications-v1.plan.md)

---

## 1. Architecture Overview

```
                ┌────────────────────────────────────────────┐
                │  api/routers/notifications.py              │
                │   APIRouter(prefix="/notifications",       │
                │             tags=["Notifications"])        │
                └──────────────┬──────────────┬──────────────┘
                               │              │
                ┌──────────────▼──┐   ┌───────▼──────────────┐
                │ schemas.py      │   │ store.py             │
                │ Pydantic models │   │ SQLite repository    │
                └─────────────────┘   │ (notifications.db)   │
                                      └──────────┬───────────┘
                                                 │
                ┌──────────────────────┐    ┌────▼─────────────────┐
                │ events.py            │    │ dispatcher.py        │
                │  emit_event(type,    │───▶│  send(url, body,     │
                │             payload) │    │       secret) → res  │
                │  KNOWN_EVENT_TYPES   │    │  HMAC-SHA256 + httpx │
                └──────────────────────┘    └──────────────────────┘
```

**계층 책임**
- `routers/notifications.py` — HTTP 라우팅, 입력 검증, store/events 호출. 비즈니스 로직 없음.
- `schemas.py` — 입력/출력 모양만 정의. 검증 로직(validator)은 자체 메서드로 캡슐화.
- `store.py` — SQLite read/write. 다른 모듈은 직접 sqlite3에 접근하지 않음.
- `dispatcher.py` — 외부 호출(httpx). store와 events는 dispatcher의 결과만 본다.
- `events.py` — "어떤 webhook이 이 이벤트를 받아야 하는가"의 라우팅 로직.

---

## 2. Data Model

### 2.1 `database/notifications.db`

```sql
CREATE TABLE IF NOT EXISTS webhooks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    url             TEXT NOT NULL,
    secret          TEXT NOT NULL,
    event_types     TEXT NOT NULL,            -- JSON array, e.g. '["webhook.test"]'
    description     TEXT NOT NULL DEFAULT '',
    active          INTEGER NOT NULL DEFAULT 1, -- 0/1
    created_at      TEXT NOT NULL,            -- ISO-8601 UTC
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_webhooks_active ON webhooks(active);

CREATE TABLE IF NOT EXISTS webhook_deliveries (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    webhook_id      INTEGER NOT NULL,
    event_type      TEXT NOT NULL,
    payload         TEXT NOT NULL,            -- JSON
    status          TEXT NOT NULL,            -- 'success' | 'failure' | 'skipped'
    response_status INTEGER,                  -- HTTP status (nullable on network failure)
    response_body   TEXT,                     -- up to 1024 chars
    error           TEXT,                     -- exception text on failure (nullable)
    attempted_at    TEXT NOT NULL,            -- ISO-8601 UTC
    duration_ms     INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (webhook_id) REFERENCES webhooks(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_deliveries_webhook ON webhook_deliveries(webhook_id, attempted_at DESC);
```

**왜 별도 DB?**
- production_analysis.db는 ERP 파일로부터 주기적으로 재배포될 수 있어([[user_role]] 운영 패턴 참고), 알림 메타가 섞이면 안 됨.
- `DBRouter`의 cutoff/archive 로직과 무관 → 라우팅 복잡도 0.
- 파일 분리로 백업·삭제·이전이 독립적.

**connection 전략**
- thread-local cache (DBRouter와 동일 패턴), 다만 단일 DB 단순화.
- `PRAGMA foreign_keys=ON`, `PRAGMA journal_mode=WAL`, `busy_timeout=10000`.
- 진입점 호출 시 `init_schema()` lazy 호출 — 이미 존재하면 no-op.

### 2.2 Pydantic Schemas (`schemas.py`)

```python
class WebhookCreate(BaseModel):
    url: str = Field(..., max_length=2048)
    event_types: list[str] = Field(default_factory=list, max_length=64)
    description: str = Field(default="", max_length=500)
    active: bool = True

class WebhookUpdate(BaseModel):
    event_types: list[str] | None = None
    description: str | None = Field(default=None, max_length=500)
    active: bool | None = None
    rotate_secret: bool = False

class WebhookPublic(BaseModel):
    id: int
    url: str
    event_types: list[str]
    description: str
    active: bool
    created_at: str
    updated_at: str
    # NOTE: secret intentionally excluded

class WebhookCreated(WebhookPublic):
    secret: str  # one-time disclosure

class DeliveryPublic(BaseModel):
    id: int
    webhook_id: int
    event_type: str
    status: str             # success | failure | skipped
    response_status: int | None = None
    response_body: str | None = None
    error: str | None = None
    attempted_at: str
    duration_ms: int

class EventTypeInfo(BaseModel):
    name: str
    description: str
```

---

## 3. HTTP API

| Path | Method | Body | Response |
|------|--------|------|----------|
| `/notifications/webhooks` | POST | `WebhookCreate` | `WebhookCreated` (201) |
| `/notifications/webhooks` | GET | — `?active=true|false` (optional) | `list[WebhookPublic]` |
| `/notifications/webhooks/{id}` | GET | — | `WebhookPublic` (404 if absent) |
| `/notifications/webhooks/{id}` | PATCH | `WebhookUpdate` | `WebhookPublic` or `WebhookCreated` if `rotate_secret=true` |
| `/notifications/webhooks/{id}` | DELETE | — | `{"deleted": true}` (404 if absent) |
| `/notifications/webhooks/{id}/test` | POST | optional `{ "payload": <obj> }` | `DeliveryPublic` |
| `/notifications/webhooks/{id}/deliveries` | GET | `?limit=50&status=success` | `list[DeliveryPublic]` |
| `/notifications/events` | GET | — | `list[EventTypeInfo]` |

**Status codes**
- 400 — URL 검증 실패, event_types 비-문자열, payload too large
- 404 — webhook id missing
- 422 — Pydantic 검증 실패(FastAPI 자동)
- 200/201 — 정상

---

## 4. URL Validation (`schemas.py` validator)

```python
ALLOWED_SCHEMES = {"http", "https"}

def _validate_webhook_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise ValueError("url scheme must be http or https")
    if not parsed.netloc:
        raise ValueError("url must include a host")
    blocked = {h.strip() for h in os.getenv("WEBHOOK_BLOCKED_HOSTS", "").split(",") if h.strip()}
    if blocked and parsed.hostname in blocked:
        raise ValueError(f"host {parsed.hostname!r} is blocked")
    return url
```

라우터에서 ValueError를 `HTTPException(400)`로 wrap (의도된 동작; 422가 아닌 400을 쓰는 이유는 기존 `_http_helpers` 일관성).

---

## 5. Dispatcher

```python
SIGNATURE_HEADER = "X-Webhook-Signature"
EVENT_HEADER     = "X-Webhook-Event"
DELIVERY_HEADER  = "X-Webhook-Delivery"
TIMESTAMP_HEADER = "X-Webhook-Timestamp"
MAX_BODY_CAPTURE = 1024  # bytes preserved in delivery.response_body

def compute_signature(secret: str, body: bytes) -> str:
    mac = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={mac}"

def send(
    *, url: str, secret: str, event_type: str,
    delivery_id: int, payload: Mapping[str, Any],
    timeout: float = WEBHOOK_TIMEOUT_SEC,
    transport: httpx.BaseTransport | None = None,   # test seam
) -> DispatchResult:
    body = orjson.dumps(payload)
    sig = compute_signature(secret, body)
    headers = {
        SIGNATURE_HEADER: sig,
        EVENT_HEADER: event_type,
        DELIVERY_HEADER: str(delivery_id),
        TIMESTAMP_HEADER: str(int(time.time())),
        "User-Agent": WEBHOOK_USER_AGENT,
        "Content-Type": "application/json",
    }
    started = time.perf_counter()
    try:
        with httpx.Client(timeout=timeout, transport=transport) as cli:
            resp = cli.post(url, content=body, headers=headers)
        captured = resp.text[:MAX_BODY_CAPTURE]
        return DispatchResult(
            status="success" if 200 <= resp.status_code < 300 else "failure",
            response_status=resp.status_code,
            response_body=captured,
            error=None,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
    except Exception as e:
        return DispatchResult(
            status="failure",
            response_status=None,
            response_body=None,
            error=f"{type(e).__name__}: {e}"[:1024],
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
```

**Test seam**: `transport` 파라미터로 `httpx.MockTransport` 주입 가능. 테스트는 외부망 호출 0건.

---

## 6. Event Dispatch (`events.py`)

```python
KNOWN_EVENT_TYPES: dict[str, str] = {
    "webhook.test": "Manual test ping (POST /notifications/webhooks/{id}/test)",
    "production.record.created": "A new production record was inserted",
    "production.threshold.exceeded": "Production volume crossed a configured threshold",
}

def register_event_type(name: str, description: str) -> None:
    KNOWN_EVENT_TYPES.setdefault(name, description)

def emit_event(
    event_type: str,
    payload: Mapping[str, Any],
    *,
    transport: httpx.BaseTransport | None = None,  # test seam
) -> list[DeliveryPublic]:
    register_event_type(event_type, KNOWN_EVENT_TYPES.get(event_type, ""))
    results: list[DeliveryPublic] = []
    for wh in store.list_webhooks(active_only=True):
        if event_type not in wh.event_types:
            continue
        delivery_id = store.create_pending_delivery(wh.id, event_type, payload)
        outcome = dispatcher.send(
            url=wh.url, secret=wh.secret, event_type=event_type,
            delivery_id=delivery_id, payload=payload, transport=transport,
        )
        store.finalize_delivery(delivery_id, outcome)
        results.append(store.get_delivery(delivery_id))
    return results
```

**왜 active_only?** 비활성 webhook은 emit에서 완전히 건너뜀(delivery 기록도 안 함). 사용자가 비활성화한 webhook이 이력에 등장하면 혼란.

---

## 7. Router Mounting

`api/main.py` (diff)
```python
- from .routers import system, records, summary
+ from .routers import system, records, summary, notifications
  ...
  app.include_router(summary.router)
+ app.include_router(notifications.router)
```
- net +2 lines (AC11 만족).
- chat 라우터 first 원칙 유지.

---

## 8. Config Additions (`shared/config.py`)

```python
# ----- Webhook notifications (webhook-notifications-v1) -----
NOTIFICATIONS_DB_FILE = DATABASE_DIR / "notifications.db"
WEBHOOK_TIMEOUT_SEC = float(os.getenv("WEBHOOK_TIMEOUT_SEC", 5.0))
WEBHOOK_USER_AGENT = os.getenv("WEBHOOK_USER_AGENT", "Server_API-Webhook/1.0")
WEBHOOK_MAX_PAYLOAD_BYTES = int(os.getenv("WEBHOOK_MAX_PAYLOAD_BYTES", 65536))
```

위 4개를 `shared/__init__.py` `__all__`에는 추가하지 않음(내부 사용만; 라우터/모듈은 `shared.config`에서 직접 import).

---

## 9. Error Handling

| Layer | 정책 |
|-------|------|
| schemas validator | `ValueError` raise → 라우터가 `HTTPException(400)`로 wrap |
| store | sqlite OperationalError 시 그대로 propagate → FastAPI 기본 500. 본 사이클은 별도 변환 안 함 |
| dispatcher | 예외를 잡아 `DispatchResult(status="failure", error=...)`로 반환. 라우터/events는 절대 raise 안 함 |
| events.emit_event | dispatcher 실패는 results에 status="failure"로 포함. 호출자는 raise를 받지 않음 |
| router /test | dispatcher 실패도 200 응답 (delivery.status가 실패를 표현). HTTP 200 = "기록은 됐다" |

---

## 10. Concurrency & Thread Safety

- store는 thread-local sqlite connection 사용. `PRAGMA journal_mode=WAL`로 read concurrency 확보.
- emit_event는 동기 호출 — FastAPI는 동기 라우터를 threadpool에서 실행하므로 worker thread 1개 점유. 본 사이클의 명시적 emit 호출만 있으므로 동시 emit 폭주 시나리오 없음.
- dispatcher는 호출마다 `httpx.Client` 컨텍스트 매니저 사용(connection pool은 호출 범위 한정). 동시 다발 호출 시 socket 누수 0.

---

## 11. Test Plan

`tests/test_notifications.py` (신규):

| # | 케이스 | 검증 항목 |
|---|--------|-----------|
| T1 | webhook CRUD (create → get → list → delete) | AC1, RG1 |
| T2 | URL scheme 검증 (ftp/javascript) | AC6 |
| T3 | `/test` 발송 + 서명 일치 + 이력 기록 | AC2, AC3 |
| T4 | event_types 미일치 webhook은 emit 시 dispatcher 미호출 | AC4 |
| T5 | active=false webhook은 emit 시 dispatcher 미호출 | AC5 |
| T6 | `PATCH rotate_secret=true` 후 이전 secret 서명 검증 실패 | AC7 |
| T7 | `/notifications/events` 3종 이상 포함 | AC8 |
| T8 | 디스패처 실패(500 응답)도 delivery 기록되고 라우터는 200 | error path |
| T9 | 디스패처 네트워크 예외도 delivery 기록 | error path |
| T10 | `GET /notifications/webhooks` 응답에 `secret` 키 없음 | AC1 |

**Test infrastructure**
- `tests/conftest.py`에 fixture 추가 없음 — `test_notifications.py` 내부에서 `monkeypatch.setattr(shared.config, "NOTIFICATIONS_DB_FILE", tmp_path / "wh.db")` + store 모듈 캐시 리셋.
- dispatcher는 `httpx.MockTransport`로 가짜 응답 주입.

---

## 12. Out-of-Scope (재확인)

- 비동기 발송 / 재시도 / 자동 housekeeping → 후속
- 도메인 이벤트 자동 emit (ERP intake hook) → 후속
- 인증 → 사이트 전체 보안 사이클 별도
- dashboard UI → 후속
