# api-router-split Planning Document

> **Summary**: 단일 거대 파일이 된 `api/main.py`(802줄)와 `api/tools.py`(740줄)를 도메인별 FastAPI router / tool 모듈로 분해하여, `dashboard-pages-refactor` 사이클에서 검증된 분리 패턴을 API 계층에도 동일하게 적용.
>
> **Project**: Server_API (Production Data Hub)
> **Version**: api-router-split v1
> **Author**: interojo
> **Date**: 2026-05-22
> **Status**: Plan

---

## 1. Overview

### 1.1 Purpose

대시보드(`dashboard/pages/*`)와 동일한 결로 API 계층을 도메인 경계로 분해한다. FastAPI는 `APIRouter` + `app.include_router(...)`라는 1급 분해 메커니즘을 제공하므로, 기존 동작은 유지하면서 단일 책임 / 경로 그룹별 응집도 / 추후 미들웨어·인증·rate limit 변경의 영향 범위를 좁힌다.

### 1.2 Background

- 현재 파일 크기:
  - `api/main.py` — 802줄 (FastAPI app + middleware + 8개 엔드포인트 + 5개 헬퍼 + 7개 캐시 래퍼)
  - `api/tools.py` — 740줄 (7개 AI 도구 함수 + 검증 헬퍼 + custom-query 보조 헬퍼)
- `api/chat.py`는 이미 자체 `APIRouter`로 분리되어 있고 `app.include_router(chat.router)` 패턴(`api/main.py:82`)이 이미 정착됨 → 동일 패턴 확장이 자연스러움.
- `api/_tool_dispatch.py`는 이미 tools.py에서 `PRODUCTION_TOOLS` 레지스트리를 분리해 두었으므로(`api/_tool_dispatch.py:20`), tools 모듈을 분해해도 dispatch 레이어가 한 곳에서 흡수해 줌.
- 검증된 선행 사이클:
  - `products-refactor` (2026-04-23, 100%) — Streamlit 거대 페이지를 helper로 분해
  - `dashboard-pages-refactor` (2026-04-24, 100%) — 같은 패턴을 3개 페이지에 일괄 적용
  - `manager-orphan-prevention-v1`, `custom-query-thread-safety` — 도메인 로직만 분리, 인터페이스(외부 API) 무변경

### 1.3 Related

- 선행 사이클: `dashboard-pages-refactor` (archived target, 100%)
- 메모리:
  - `feedback_commit_style.md` — phase별 logical layer 단위로 커밋 분할
  - `feedback_default_shadowing.md` — 라우터 분리 시 wrapper의 기본 인자가 inner route 기본값을 가리지 않도록 주의
  - `project_review_fixes_202604_part2.md` — `products.py` 분해 사례

---

## 2. Scope

### 2.1 In Scope

#### A. `api/main.py` → `api/routers/` 분해

| ID | 신규 모듈 | 흡수 대상 라우트 | 비고 |
|----|----------|-----------------|------|
| R1 | `api/routers/system.py` | `GET /`, `GET /healthz`, `GET /healthz/ai`, `GET /metrics/performance`, `GET /metrics/cache` | AI-health 캐시(`_ai_health_cache`)와 lock 동봉 |
| R2 | `api/routers/records.py` | `GET /records`, `GET /records/{item_code}`, `GET /items` | cursor 인코딩 헬퍼(`_encode_cursor`/`_decode_cursor`)와 `_*_cached` 래퍼 동봉 |
| R3 | `api/routers/summary.py` | `GET /summary/monthly_total`, `GET /summary/by_item`, `GET /summary/monthly_by_item` | 월별/품목별 집계 캐시 래퍼 동봉 |
| R4 | `api/main.py` (슬림화) | FastAPI app 구성 + 미들웨어 + `include_router` 호출만 | 200줄 이하 목표 |
| R5 | `api/_http_helpers.py` (신규) | `_normalize_date`, `_validate_date_range`, `_validate_length` | 라우터들이 공유하는 HTTPException-wrapping 헬퍼 |

#### B. `api/tools.py` → `api/tools/` 패키지 분해

| ID | 신규 모듈 | 흡수 대상 함수 | 비고 |
|----|----------|---------------|------|
| T1 | `api/tools/__init__.py` | re-export: 기존 7개 tool 함수 동일 시그니처/이름 | `_tool_dispatch.py`와 외부 import 경로 무변경 |
| T2 | `api/tools/items.py` | `search_production_items`, `get_item_history` | 품목 검색·이력 |
| T3 | `api/tools/summary.py` | `get_production_summary`, `get_monthly_trend`, `get_top_items`, `compare_periods` | 기간 집계·트렌드·비교 |
| T4 | `api/tools/custom.py` | `execute_custom_query`, `_strip_sql_comments`, `_validate_custom_query_params` | 자유 SQL — 격리도가 가장 높은 도메인 |
| T5 | `api/tools/_common.py` | `_validate_date_range` (tools 전용 래퍼) | tools 내부 공유 헬퍼 |

#### C. 호환성 / 회귀 방어

| ID | 항목 |
|----|------|
| C1 | `from api.tools import X` 경로 100% 유지 (외부 import는 `api/tools/__init__.py`가 흡수) |
| C2 | `from api.main import app` 경로 100% 유지 |
| C3 | OpenAPI 스키마 path/method/parameter 동등 — `/openapi.json` diff 0 |
| C4 | 미들웨어 등록 순서 동등 (GZip → CORS → request-id/rate-limit) |
| C5 | rate-limiter 경로 예외 목록 동등 (`/`, `/healthz`, `/healthz/ai`, `/docs`, `/openapi.json`, `/chat*`) |

### 2.2 Out of Scope

| Item | Reason |
|------|--------|
| `api/chat.py` 추가 분해 | 이미 자체 router로 분리됨. 별도 `chat-refactor` 사이클 후보 |
| `_chat_stream.py` / `_session_store.py` / `_gemini_client.py` 재배치 | chat 내부 helper, 본 사이클 경계 외부 |
| 라우트 prefix / API 버저닝(`/api/v1/...`) 도입 | 외부 호환성 깨짐 → 별도 사이클 |
| dashboard "batches" 페이지에 대응하는 API 신설 | 현재 API에 `/batches` 엔드포인트는 존재하지 않음. 요청에 포함되었지만 신설은 본 사이클 범위 밖 (Design 단계에서 confirm 필요) |
| tool 함수 시그니처 변경 / 신규 파라미터 | Gemini tool schema 동결 — `feedback_gemini_tool_schema.md` |
| custom-query 동시성·timeout 추가 보강 | 직전 `custom-query-thread-safety`(100%)에서 완료 |
| `_*_cached` 함수의 inline 합치기 | 캐시 데코레이터 경계 유지 |

### 2.3 Naming Decision Notes

- **`routers/system.py` vs `routers/health.py`**: health/metrics/root까지 한 묶음이므로 의미상 `system`이 더 정확. Design 단계에서 최종 확정.
- **`tools/items.py` vs `tools/products.py`**: 코드 내부 어휘는 `item_code`/`item_name`이 우세 → `items.py` 우선 제안. User 요청 어휘는 "products"였으므로 Design에서 confirm.
- **`tools/custom.py` vs `tools/quality.py`**: 함수는 자유 SQL 실행이며 품질지표 도메인이 아님 → `custom.py` 우선. User 요청은 "quality"였으나 의미적으로 일치 안 함 — Design 결정.

---

## 3. Acceptance Criteria

| AC | 내용 | 검증 |
|----|------|------|
| AC1 | `api/main.py` ≤ 250줄, FastAPI app 구성·미들웨어·`include_router`만 포함 | `wc -l`, grep |
| AC2 | `api/routers/{system,records,summary}.py` 각각 단일 `APIRouter` 인스턴스를 노출 | grep `APIRouter()` |
| AC3 | `api/tools/` 패키지에서 `from api.tools import search_production_items, get_production_summary, get_monthly_trend, get_top_items, compare_periods, get_item_history, execute_custom_query` 가 성공 | python -c |
| AC4 | `api/_tool_dispatch.py:PRODUCTION_TOOLS`는 분해 후에도 동일 7개 함수 객체를 동일 순서로 보유 | grep / diff |
| AC5 | `/openapi.json` path·method·query parameter 셋이 분해 전과 동일 | diff (pre/post) |
| AC6 | `pytest tests/ -q` 회귀 없음 (현재 baseline 통과 수 유지) | pytest |
| AC7 | `python -m py_compile` 모든 신규 모듈 통과 | bash |
| AC8 | gap-detector 본 사이클 일치율 ≥ 90% (목표 ≥ 95%) | bkit:gap-detector |
| AC9 | `api/tools.py` 와 `api/main.py` 원본 파일은 삭제 또는 thin shim 만 남김 (라인 수 ≤ 30) | wc -l |

---

## 4. Risks

| Risk | Mitigation |
|------|-----------|
| `app` 객체와 router 분리 시 미들웨어 등록 누락 | 미들웨어는 `api/main.py`에 그대로 두고, route 만 router로 이전. include_router 단계에서 prefix/tags 변경 없음 |
| 캐시 데코레이터 키 충돌 — `@api_cache("monthly_total")` 등 key가 호출 모듈을 바꿔도 충돌하지 않아야 함 | 키는 문자열 리터럴이므로 모듈 이동과 무관. 단 Check에서 cache key 인벤토리 diff 0 확인 |
| `_tool_dispatch.py`의 import 경로 `from .tools import ...`가 패키지화되면서 의미가 바뀜 | `api/tools/__init__.py`에서 모든 공개 함수 re-export 하여 외부 import 경로 보존 |
| 순환 import 위험 (`routers/* → main.py`) | `app = FastAPI(...)`는 main에만 두고 router는 `APIRouter()` 인스턴스만 노출. router → main 역참조 없음 |
| `_normalize_date` 등 헬퍼가 라우터별로 미세하게 다르게 쓰일 우려 | 본 사이클은 동작 동일 이전만 수행. 시그니처/동작 변경은 별도 사이클 |
| 분해 도중 OpenAPI 스키마가 미세하게 흔들림 (operation_id, tag) | 라우터 등록 시 `tags=[]` 명시하지 않으면 자동 inference로 path 첫 segment가 tag가 됨 → 분해 후 OpenAPI diff에서 발견되면 Design 단계에서 명시 |
| 외부 클라이언트(192.168.200.107 dev server 등)가 모듈 경로 import 의존 | 외부 클라이언트는 HTTP 경로만 사용. `from api.main import app`/`from api.tools import ...`는 우리 코드/테스트만 사용 → C1/C2로 보존 |

---

## 5. Timeline

| Phase | Duration | Owner |
|-------|---------|-------|
| Plan + Design | 0.6h | interojo |
| Act-1: `routers/system.py` 분리 (R1) + `_http_helpers.py` (R5) | 0.5h | interojo |
| Act-2: `routers/records.py` 분리 (R2) | 0.5h | interojo |
| Act-3: `routers/summary.py` 분리 (R3) | 0.4h | interojo |
| Act-4: `tools/` 패키지화 (T1~T5) | 0.7h | interojo |
| Act-5: `api/main.py` 슬림화 (R4) + import 정리 | 0.3h | interojo |
| Check: openapi diff + py_compile + pytest + gap-detector | 0.4h | gap-detector |
| Report | 0.2h | report-generator |

총 예상: ~3.6h

---

## 6. Open Questions (Design 단계에서 확정)

| Q | 옵션 | Plan 단계 추천 |
|---|------|---------------|
| Q1. 라우터 모듈명 | `system.py` vs `health.py` | `system.py` (health + metrics + root 포괄) |
| Q2. 품목 tool 모듈명 | `tools/items.py` vs `tools/products.py` | `tools/items.py` (코드 내부 어휘 일치) |
| Q3. custom-query tool 모듈명 | `tools/custom.py` vs `tools/quality.py` | `tools/custom.py` (실제 도메인과 일치) |
| Q4. `/batches` 엔드포인트 신설 여부 | 본 사이클 포함 vs 분리 | 분리 — 본 사이클은 **재배치만**, 신규 라우트 없음 |
| Q5. APIRouter `tags`/`prefix` 사용 여부 | (a) 무변경 (b) tags만 추가 (c) prefix 도입 | (a) — OpenAPI diff 0 (AC5) 충족 위해 무변경 |
