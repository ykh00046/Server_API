# Design: structure-cleanup

**Feature**: structure-cleanup
**Author**: PDCA-driven (Opus 4.7)
**Date**: 2026-05-27
**Phase**: Design
**Plan**: [`docs/01-plan/features/structure-cleanup.plan.md`](../../01-plan/features/structure-cleanup.plan.md)

---

## 1. 모듈 분해 설계

### 1.1 `api/notifications/store.py` (577 → facade)

```
api/notifications/
├── store.py                  ← 100% re-export facade (≤ 130 lines)
├── _store_connection.py      ← _local, _get_conn, _ensure_schema*, reset_for_tests
├── _store_models.py          ← WebhookRecord, ClaimedDelivery, _row_to_*, _now_iso
├── webhooks_repo.py          ← create/get/list/update/delete_webhook
└── deliveries_repo.py        ← create_pending/finalize/enqueue/claim/record_attempt/queue_stats/requeue/list
```

**의존 방향 (단방향)**:

```
_store_models  ← _store_connection
        ↑                ↑
        └─ webhooks_repo, deliveries_repo
                 ↑
              store.py (facade re-export)
```

**facade re-export 목록** (`store.py` 본문):

```python
"""Backward-compat facade. New code should import from the sub-modules."""
from __future__ import annotations

from ._store_connection import (  # noqa: F401
    reset_for_tests,
)
from ._store_models import (  # noqa: F401
    ClaimedDelivery,
    WebhookRecord,
)
from .webhooks_repo import (  # noqa: F401
    create_webhook,
    delete_webhook,
    get_public,
    get_record,
    list_public,
    list_records,
    update_webhook,
)
from .deliveries_repo import (  # noqa: F401
    claim_due_deliveries,
    create_pending_delivery,
    enqueue_delivery,
    finalize_delivery,
    get_delivery,
    list_deliveries,
    queue_stats,
    record_attempt,
    requeue_delivery,
)

__all__ = [
    "ClaimedDelivery",
    "WebhookRecord",
    "claim_due_deliveries",
    "create_pending_delivery",
    "create_webhook",
    "delete_webhook",
    "enqueue_delivery",
    "finalize_delivery",
    "get_delivery",
    "get_public",
    "get_record",
    "list_deliveries",
    "list_public",
    "list_records",
    "queue_stats",
    "record_attempt",
    "requeue_delivery",
    "reset_for_tests",
    "update_webhook",
]
```

### 1.2 `shared/database.py` (394 → 분리)

```
shared/
├── database.py        ← DBTargets, DBRouter (≤ 280 lines)
├── _db_connection.py  ← _local, _all_connections, _wal_*, _get_db_mtime,
│                        _apply_pragma_settings, _cleanup_all_connections, atexit
└── _db_attach.py      ← attach_archive_safe
```

**의존 방향**:

```
_db_attach  ← shared.validators.resolve_archive_db
_db_connection  ← (no internal deps)
        ↑
     database.py (re-exports attach_archive_safe for back-compat)
```

**`database.py` 본문에 추가될 re-export**:

```python
from ._db_attach import attach_archive_safe  # noqa: F401 (back-compat)
from ._db_connection import (
    _local,
    _all_connections,  # used? if yes re-export
    _apply_pragma_settings,
    _get_db_mtime,
)
```

> `_local`, `_all_connections`는 module-private이지만 conftest fixture에서 monkeypatch
> 가능성 → `_db_connection.py`에 보관하고 database.py가 import하여 사용.

---

## 2. pytest 설정 설계

### 2.1 `pyproject.toml` (신규)

프로젝트 root에 신규 생성. **테스트 설정만** 추가하고 기타 도구(ruff/black 등)는 손대지 않는다.

```toml
[tool.pytest.ini_options]
minversion = "7.0"
testpaths = ["tests"]
addopts = [
    "-ra",                       # 실패/스킵 요약을 항상 출력
    "--strict-markers",
]
tmp_path_retention_policy = "failed"     # 성공한 테스트의 tmp_path는 즉시 정리
tmp_path_retention_count = 3
filterwarnings = [
    "ignore::DeprecationWarning:google.*",
    "ignore::DeprecationWarning:httpx.*",
    "ignore::PendingDeprecationWarning",
]
```

### 2.2 `tests/conftest.py` (기존에 fixture 추가)

```python
# 기존 _reset_rate_limiters 다음에 추가
@pytest.fixture(autouse=True)
def _close_db_connections():
    """Force-close thread-local SQLite connections after each test so that
    Windows can delete the pytest tmp_path without PermissionError.

    Required because:
    - api.notifications.store and shared.database both cache sqlite3.Connection
      objects in threading.local() keyed by db path
    - When a test monkeypatches NOTIFICATIONS_DB_FILE to a tmp_path file, the
      connection survives the test but its file handle blocks rmtree on Windows
    """
    yield
    # notifications store
    try:
        from api.notifications import store as _store
        _store.reset_for_tests()
    except ImportError:
        pass
    # shared.database (DBRouter)
    try:
        from shared import database as _db
        for attr in list(vars(_db._local)):
            if attr.startswith("conn_"):
                try:
                    getattr(_db._local, attr).close()
                except (sqlite3.Error, AttributeError):
                    pass
                setattr(_db._local, attr, None)
    except ImportError:
        pass
```

---

## 3. `except Exception` 좁히기 (4 곳)

| 파일:줄 | 현재 | 변경 후 | 이유 |
|---------|------|---------|------|
| `api/notifications/store.py:60` | `except Exception: pass` (close 실패 무시) | → `_store_connection.py`로 이동하며 `except sqlite3.Error: pass` | close 실패는 sqlite3 에러만 발생 |
| `api/notifications/store.py:159` | `except Exception: pass` (reset_for_tests close) | → `_store_connection.py`로 이동하며 `except sqlite3.Error: pass` | 동일 |
| `api/routers/system.py:111-118` | 2단 nested `except Exception` | `except (AttributeError, OSError)` (statvfs 없거나 호출 실패) | Windows에서 AttributeError, 권한 문제 OSError만 발생 |
| `api/routers/records.py:44` | `except Exception: return None` | `except (ValueError, TypeError, sqlite3.Error): return None` + 주석 | 어떤 입력 변환 실패를 받아내는지 명시 |

### 명시적으로 **유지**되는 except Exception (보수적)

| 파일:줄 | 이유 |
|---------|------|
| `api/chat.py:280, 301, 333` | LLM SDK 호출 — 라이브러리가 어떤 예외 던지는지 상위 보장 없음. logger.exception 있음 |
| `api/_gemini_client.py:38` | SDK init — 동일 |
| `api/notifications/worker.py:104, 169` | "Never let the worker die" 주석 — 의도적 광범위 캐치 |
| `api/notifications/dispatcher.py:96` | HTTP 호출 — httpx/transport 다양한 예외 통합 처리 |
| `api/notifications/events.py:112` | "fire-and-forget" 의미적 광범위 캐치 |
| `api/tools/*.py` (custom/items/summary) | tool 함수 outer — JSON 에러 메시지 반환용 |
| `api/_chat_stream.py:141, 237` | SSE handler outer |
| `dashboard/*` | UI 레이어 — 광범위 캐치가 의도 |

---

## 4. 회귀 안전망

다음 호출자 중 **단 하나라도** 깨지면 facade가 잘못된 것:

- `api/notifications/events.py` — `from .store import list_records, enqueue_delivery, create_pending_delivery, finalize_delivery`
- `api/notifications/worker.py` — `from .store import claim_due_deliveries, record_attempt, queue_stats`
- `api/notifications/dispatcher.py` — (store 직접 의존 없음)
- `api/routers/notifications.py` (있다면) — webhook CRUD 호출
- `api/tools/custom.py` — `from shared.database import attach_archive_safe`
- 기타 grep으로 확인

기존 테스트 288개로 회귀 감지:

- `tests/test_notifications.py` (16건) — webhook CRUD + dispatch
- `tests/test_notifications_async.py` (12건) — 큐/워커
- `tests/test_webhook_admin_*` — UI integration
- `tests/test_database*` — DBRouter (있는 경우)

---

## 5. 구현 순서 (Do 단계)

1. **commit 1**: `pyproject.toml` 신규 + `tests/conftest.py` fixture 추가
   - 실행: `pytest tests/ -q` → AC2/AC3 확인 (PermissionError 0건)
2. **commit 2**: `shared/_db_connection.py` + `shared/_db_attach.py` 분리, `shared/database.py` 정리
   - 실행: `pytest tests/ -q`
3. **commit 3**: `api/notifications/_store_*.py` + `webhooks_repo.py` + `deliveries_repo.py` 분리
   - 실행: `pytest tests/ -q`
4. **commit 4**: `api/notifications/store.py`를 facade로 축소
   - 실행: `pytest tests/ -q`
5. **commit 5**: 4곳 `except Exception` 좁히기
   - 실행: `pytest tests/ -q`

각 commit은 독립적으로 통과해야 한다.

---

## 6. 비-목표 (재확인)

- 새 기능 추가 안 함
- `webcloring-pdf/` 손대지 않음
- 이미 의도된 광범위 except는 보존
- 신규 회귀 테스트 추가 안 함 (기존 288개로 충분)
- DB 스키마 변경 없음
