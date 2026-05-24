# api-router-split Design Document

> **Plan**: [api-router-split.plan.md](../../01-plan/features/api-router-split.plan.md)
> **Status**: Design (finalized)
> **Date**: 2026-05-22
> **Decisions**: 권장안 채택 — `system.py` / `items.py` / `custom.py`, batches 제외

---

## 1. Decision Recap (Plan §6 Open Questions → 확정)

| Q | 결정 | 근거 |
|---|------|------|
| Q1 라우터 모듈명 | `system.py` | health + metrics + root 통합 (`/`, `/healthz*`, `/metrics/*`) |
| Q2 품목 tool 모듈명 | `tools/items.py` | 코드 어휘(item_code/item_name) 일치 |
| Q3 custom-query tool 모듈명 | `tools/custom.py` | 자유 SQL 도메인. "quality" 의미와 불일치 |
| Q4 `/batches` 엔드포인트 | **본 사이클 제외** | 신설은 별도 PDCA. 본 사이클은 재배치만 수행 |
| Q5 APIRouter prefix/tags | **사용 안 함** | OpenAPI 호환 유지(AC5) — path/operation_id/tag 셋 무변경 |

---

## 2. Target File Tree

```
api/
├── main.py                      # ≤ 250줄. app + middleware + include_router 만
├── chat.py                      # 변경 없음 (이미 router 분리됨)
├── _chat_stream.py              # 변경 없음
├── _gemini_client.py            # 변경 없음
├── _session_store.py            # 변경 없음
├── _tool_dispatch.py            # import 경로 무변경 (api.tools 패키지가 흡수)
├── _http_helpers.py             # 신규 — 공유 HTTPException-wrapping 헬퍼
├── routers/                     # 신규 패키지
│   ├── __init__.py              # 빈 파일 또는 router 노출용
│   ├── system.py                # /, /healthz, /healthz/ai, /metrics/*
│   ├── records.py               # /records, /records/{item_code}, /items
│   └── summary.py               # /summary/*
└── tools/                       # 신규 패키지 (단일 모듈 api/tools.py → 패키지화)
    ├── __init__.py              # 7개 tool 함수 re-export
    ├── _common.py               # tools 전용 _validate_date_range 래퍼
    ├── items.py                 # search_production_items, get_item_history
    ├── summary.py               # get_production_summary, get_monthly_trend,
    │                            # get_top_items, compare_periods
    └── custom.py                # execute_custom_query + _strip_sql_comments
                                 #                       + _validate_custom_query_params
```

기존 단일 파일 처리:
- `api/tools.py` 단일 모듈 → **삭제** (Python은 동명 패키지를 우선시키지 못하므로 충돌 회피 위해 제거 필수)
- `api/main.py` → **슬림화** (re-export 라인 유지로 backward compat)

---

## 3. Route → Module Mapping (main.py)

| 현재 위치 (api/main.py) | 신규 위치 | 비고 |
|---|---|---|
| `app = FastAPI(...)` (66) | `api/main.py` | 유지 |
| GZip middleware (70) | `api/main.py` | 유지 |
| CORS middleware (73-80) | `api/main.py` | 유지 |
| `app.include_router(chat.router)` (82) | `api/main.py` | 유지 + 신규 3개 router include 추가 |
| `add_request_id_and_rate_limit` (93-144) | `api/main.py` | 유지 (전역 미들웨어) |
| `_request_counter`, `_CLEANUP_INTERVAL` (89-90) | `api/main.py` | 미들웨어 내부 사용 → 유지 |
| `_normalize_date`, `_validate_date_range`, `_validate_length` (150-187) | `api/_http_helpers.py` | 신규 위치 + `api/main.py`에서 re-export (tests 호환) |
| `_encode_cursor`, `_decode_cursor` (193-209) | `api/routers/records.py` | records 전용. 모듈-private (`_`) 유지 |
| `_ai_health_cache`, `_ai_health_cache_lock`, `AI_HEALTH_CACHE_TTL` (49-55) | `api/routers/system.py` | system router 내부 상태 |
| `@app.get("/")` read_root (215) | `system.py` `@router.get("/")` | |
| `@app.get("/metrics/performance")` (220) | `system.py` | |
| `@app.get("/metrics/cache")` (226) | `system.py` | |
| `@app.get("/healthz")` (235) | `system.py` | |
| `@app.get("/healthz/ai")` (295) | `system.py` | |
| `@app.get("/records")` get_records (404) | `records.py` | |
| `_get_item_records_cached` (551) | `records.py` | |
| `@app.get("/records/{item_code}")` (579) | `records.py` | |
| `_list_items_cached` (586) | `records.py` | `/items`는 records와 같은 도메인(생산기록 기반) |
| `@app.get("/items")` (616) | `records.py` | |
| `_monthly_total_cached` (631) | `summary.py` | |
| `@app.get("/summary/monthly_total")` (664) | `summary.py` | |
| `_summary_by_item_cached` (685) | `summary.py` | |
| `@app.get("/summary/by_item")` (723) | `summary.py` | |
| `_monthly_by_item_cached` (746) | `summary.py` | |
| `@app.get("/summary/monthly_by_item")` (791) | `summary.py` | |

---

## 4. Tool → Module Mapping (tools.py)

| 현재 위치 (api/tools.py) | 신규 위치 | 시그니처 변경 |
|---|---|---|
| `_validate_date_range` (40-42) | `api/tools/_common.py` | 없음. tools 내부 공유. shared.validators 경유는 그대로 |
| `search_production_items` (50) | `api/tools/items.py` | 없음 |
| `get_production_summary` (136) | `api/tools/summary.py` | 없음 |
| `get_monthly_trend` (217) | `api/tools/summary.py` | 없음 |
| `get_top_items` (286) | `api/tools/summary.py` | 없음 |
| `compare_periods` (348) | `api/tools/summary.py` | 없음 |
| `get_item_history` (448) | `api/tools/items.py` | 없음 |
| `_strip_sql_comments` (513) | `api/tools/custom.py` | 없음 |
| `_validate_custom_query_params` (520) | `api/tools/custom.py` | 없음 |
| `execute_custom_query` (546) | `api/tools/custom.py` | 없음 |

각 모듈 상단 import 그룹은 자기 함수만 의존하도록 정리. tool 함수의 PEP-magic은 그대로 두고(파일을 옮기는 것만 수행) Gemini tool schema와의 호환을 보장한다.

---

## 5. `api/tools/__init__.py` Re-export Contract

```python
# api/tools/__init__.py
"""Re-exports for backward-compatible imports.

External callers MUST use `from api.tools import X` (works in both the old
single-module and the new package layout). Internal callers within the
api.tools package may import siblings directly.
"""
from .items import search_production_items, get_item_history
from .summary import (
    get_production_summary,
    get_monthly_trend,
    get_top_items,
    compare_periods,
)
from .custom import execute_custom_query

__all__ = [
    "search_production_items",
    "get_item_history",
    "get_production_summary",
    "get_monthly_trend",
    "get_top_items",
    "compare_periods",
    "execute_custom_query",
]
```

→ `api/_tool_dispatch.py:10` (`from .tools import (...)`)는 **수정 불요**.
→ `tests/test_sql_validation.py:3` (`from api.tools import ...`)는 **수정 불요**.

---

## 6. `api/_http_helpers.py` Contract

```python
# api/_http_helpers.py
"""HTTP-layer wrappers around shared validators.

These helpers raise HTTPException (FastAPI-native) so route handlers can
remain free of try/except boilerplate. Each route or router module imports
them as needed.

Re-exported from api.main for backward compatibility with tests that import
_validate_date_range / _validate_length directly.
"""
from __future__ import annotations
import datetime as dt
from fastapi import HTTPException
from shared.validators import (
    validate_date_range as _validate_date_range_pure,
    validate_length as _validate_length_pure,
)


def _normalize_date(date_str: str | None, add_days: int = 0) -> str | None: ...
def _validate_date_range(date_from: str | None, date_to: str | None) -> None: ...
def _validate_length(value: str | None, max_length: int, field_name: str) -> str | None: ...
```

함수 본문은 현행 `api/main.py:150-187`를 1:1로 옮긴다(변경 없음).

`api/main.py` 상단에 호환성 re-export 추가:

```python
from ._http_helpers import (
    _normalize_date,
    _validate_date_range,
    _validate_length,
)
```

→ `tests/test_input_validation.py:12` (`from api.main import _validate_date_range, _validate_length`)는 **수정 불요**.

---

## 7. Router Skeleton (3종 공통 패턴)

```python
# api/routers/system.py
"""System endpoints: health, metrics, root."""
from __future__ import annotations
import os, time, threading
import datetime as dt

from fastapi import APIRouter
from shared import DB_FILE, ARCHIVE_DB_FILE, DATABASE_DIR, DBRouter, get_cache_stats, get_logger
from shared.metrics import performance_monitor
from .. import _session_store as _sstore

logger = get_logger(__name__)
router = APIRouter()

# AI Health Check Cache — moved from api/main.py
_ai_health_cache = {"status": "unknown", "last_check": 0, "message": "Not checked yet"}
_ai_health_cache_lock = threading.Lock()
AI_HEALTH_CACHE_TTL = 600


@router.get("/")
def read_root(): ...

@router.get("/metrics/performance")
def metrics_performance(): ...

# ... (remaining endpoints, identical bodies)
```

같은 형태로 `records.py`, `summary.py` 작성. **각 모듈은 `router = APIRouter()` 단일 인스턴스**만 노출한다.

---

## 8. `api/main.py` Final Shape (예상 ≤ 230줄)

```python
from __future__ import annotations
import itertools, sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse, JSONResponse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared import setup_logging, get_logger, api_rate_limiter
from shared.logging_config import set_request_id
from shared.config import CORS_ORIGINS

from . import chat
from .routers import system, records, summary
from ._http_helpers import _normalize_date, _validate_date_range, _validate_length  # noqa: F401 (compat)

setup_logging()
logger = get_logger(__name__)

app = FastAPI(title="Production Data API", default_response_class=ORJSONResponse)
app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(system.router)
app.include_router(records.router)
app.include_router(summary.router)


_request_counter = itertools.count()
_CLEANUP_INTERVAL = 100


@app.middleware("http")
async def add_request_id_and_rate_limit(request, call_next):
    """... (unchanged body) ..."""
```

핵심 불변량:
- 미들웨어 순서: GZip → CORS → request-id/rate-limit (등록 순서 그대로).
- `include_router` 순서: chat → system → records → summary (chat을 가장 먼저 추가하여 기존 동작과 동일).

---

## 9. Implementation Order (Do 단계)

```
Step 1: api/_http_helpers.py 생성
Step 2: api/routers/__init__.py (빈 파일)
Step 3: api/routers/system.py — _ai_health_cache + 5 endpoints
Step 4: api/routers/records.py — _encode/_decode_cursor + 3 endpoints + 2 cached helpers
Step 5: api/routers/summary.py — 3 cached helpers + 3 endpoints
Step 6: api/tools/__init__.py (re-exports)
Step 7: api/tools/_common.py — _validate_date_range
Step 8: api/tools/items.py — 2 functions
Step 9: api/tools/summary.py — 4 functions
Step 10: api/tools/custom.py — 3 functions
Step 11: api/main.py 슬림화 + compat re-exports
Step 12: 원본 api/tools.py 삭제 (패키지 이름 충돌 방지)
Step 13: __pycache__/ 정리 (오래된 .pyc로 인한 import 혼선 방지)
```

---

## 10. Verification Plan (Check 단계)

1. **Compile**: `python -m py_compile api/_http_helpers.py api/routers/*.py api/tools/*.py api/main.py`
2. **Import smoke**:
   - `python -c "from api.main import app; print(len(app.routes))"`
   - `python -c "from api.tools import search_production_items, execute_custom_query"`
   - `python -c "from api._tool_dispatch import PRODUCTION_TOOLS; print(len(PRODUCTION_TOOLS))"`
   - `python -c "from api.main import _validate_date_range, _validate_length"`
3. **OpenAPI diff**:
   - 전: 사이클 시작 전에 `python -c "from api.main import app; import json; print(json.dumps(app.openapi(), sort_keys=True))" > /tmp/openapi.pre.json` (사이클 시작 전 baseline은 git에서 복원 가능)
   - 후: 동일하게 생성 후 `diff /tmp/openapi.pre.json /tmp/openapi.post.json` → diff 0 기대
4. **pytest**: `pytest tests/ -q` — 기존 baseline 통과 수 유지
5. **gap-detector**: design vs implementation 일치율 ≥ 90% (목표 ≥ 95%)

---

## 11. Risk Re-evaluation

| Risk (Plan §4) | Design 단계 추가 결론 |
|---|---|
| 미들웨어 누락 | §8에 등록 순서 명시. main.py 최종 형태가 reference |
| 캐시 키 충돌 | 키는 문자열 리터럴, 모듈 이동 무영향. cache key 인벤토리 grep diff로 확인 |
| 순환 import | router들은 `from .. import X` 만 사용. main.py만 router를 import |
| `_tool_dispatch` import 경로 | §5의 `__init__.py` re-export로 0 변경 보장 |
| `_normalize_date` 등 헬퍼 미세 분기 | §6에서 1:1 이전 확정. 시그니처 변경 금지 |
| 외부 클라이언트 모듈 import | 외부는 HTTP만 사용. 내부 import는 §5/§6/§8로 보존 |
| **tests/test_input_validation.py 직접 import** | §6 compat re-export로 해결 (**Design 단계에서 새로 식별**) |
| **`api/tools.py` 동명 충돌** | Step 12에서 명시 삭제 (**Design 단계에서 새로 식별**) |
| **`__pycache__` 잔재** | Step 13에서 정리 (**Design 단계에서 새로 식별**) |

---

## 12. Acceptance Criteria (Plan §3 재확인)

전부 유지. 본 design 기준으로 측정 가능:

- AC1: `api/main.py` ≤ 250줄 — §8 형태 기준 ~120줄 예상
- AC2: 3개 라우터 모듈 각각 `APIRouter()` 단일 인스턴스 — §7 패턴
- AC3: 7개 tool 함수 패키지 import 성공 — §5 `__init__.py`
- AC4: `_tool_dispatch.PRODUCTION_TOOLS` 동일 7개 객체 — import 경로 무변경 (§5)
- AC5: OpenAPI diff 0 — §10 단계 3
- AC6: pytest 회귀 없음 — §6 compat re-export로 test_input_validation 보장
- AC7: py_compile 통과 — §10 단계 1
- AC8: gap-detector ≥ 90% — §10 단계 5
- AC9: 원본 `api/tools.py` 삭제, `api/main.py` ≤ 250줄 — Step 12 / §8
