# api-router-split Gap Analysis Report

> **Design**: [api-router-split.design.md](../02-design/features/api-router-split.design.md)
> **Plan**: [api-router-split.plan.md](../01-plan/features/api-router-split.plan.md)
> **Date**: 2026-05-22
> **Phase**: Check
> **Agent**: bkit:gap-detector

---

## Overall Scores

| Category | Score | Status |
|----------|:-----:|:------:|
| Design Match (file tree, routing, re-exports) | 100% | OK |
| Architecture Compliance (router/tools layering) | 100% | OK |
| Convention Compliance (naming, imports) | 100% | OK |
| **Overall match rate** | **98%** | **OK (≥ 90%)** |

2% reserve covers a single doc-vs-impl deviation that does not block any AC (test-helper re-exports beyond design §5 minimum).

## Acceptance Criteria Scorecard

| AC | Target | Result | Evidence |
|----|--------|--------|----------|
| AC1 | `api/main.py` ≤ 250 lines, only app + middleware + include_router | PASS | 126 lines; matches design §8 |
| AC2 | 3 routers each expose exactly one `APIRouter()` | PASS | grep: `system.py:30`, `records.py:28`, `summary.py:22` |
| AC3 | `from api.tools import ...` 7 functions | PASS | smoke import (pre-verified) |
| AC4 | `_tool_dispatch.PRODUCTION_TOOLS` unchanged (7 objs, same order) | PASS | order: search_production_items, get_production_summary, get_monthly_trend, get_top_items, compare_periods, get_item_history, execute_custom_query |
| AC5 | OpenAPI diff = 0 | PASS | byte-identical (12528 bytes) — `tags=`/`prefix=` correctly omitted per design §1 Q5 |
| AC6 | pytest baseline maintained | PASS | 214 passed, 10 errors — identical to pre-refactor baseline |
| AC7 | py_compile passes | PASS | all new modules |
| AC8 | gap-detector ≥ 90% | PASS | 98% (this report) |
| AC9 | `api/tools.py` deleted, `main.py` slim | PASS | tools.py absent; main.py = 126 lines |

**9/9 ACs met.**

## Design vs Implementation Comparison

### Missing Features
None.

### Added Features (positive deviation)

| Item | Location | Note |
|------|----------|------|
| `_strip_sql_comments`, `_validate_custom_query_params` re-exported in `api/tools/__init__.py` | `api/tools/__init__.py:21-25, 36-37` | Design §5 listed only the 7 public tools. Impl re-exports two private helpers for `tests/test_sql_validation.py`. Severity: low (pragmatic improvement, not regression). |

### Changed Features

| Item | Design | Impl | Impact |
|------|--------|------|--------|
| Re-export comment style in `api/main.py` | `# noqa: F401 (compat)` inline | Block comment + `# noqa: F401` on import block | Cosmetic |
| `routers/__init__.py` content | "빈 파일 또는 router 노출용" | Docstring only (1 line) | Acceptable (design allowed either) |

## Module-by-Module Verification

### `api/main.py` (126 lines)
- FastAPI app construction (`title`, `default_response_class=ORJSONResponse`) — matches design §8
- Middleware order: GZip → CORS → request-id/rate-limit — matches design §8
- `include_router` order: chat → system → records → summary — matches design §8
- Compat re-export of helpers from `_http_helpers` — matches design §6
- Rate-limiter skip list `["/", "/healthz", "/healthz/ai", "/docs", "/openapi.json"]` — matches plan C5
- `/chat*` short-circuit preserved — matches plan C5

### `api/_http_helpers.py` (50 lines)
- All three helpers present, signatures match design §6
- HTTPException wrapping preserved

### `api/routers/system.py` (226 lines)
- `_ai_health_cache` / lock / TTL co-located (design §3)
- 5 endpoints: `/`, `/metrics/performance`, `/metrics/cache`, `/healthz`, `/healthz/ai`
- `from .. import _session_store as _sstore` — clean dependency, no back-ref to main

### `api/routers/records.py` (258 lines)
- `_encode_cursor`/`_decode_cursor` co-located (design §3)
- 3 endpoints + 2 cached helpers
- Uses `_http_helpers` for validation

### `api/routers/summary.py` (195 lines)
- 3 endpoints + 3 cached helpers
- Uses `_http_helpers` for validation

### `api/tools/__init__.py` (38 lines)
- All 7 public tools re-exported under correct names
- 2 private helpers re-exported for test compat

### `api/tools/_common.py` (11 lines)
- Delegates to `shared.validators.validate_date_range_exclusive` (design §4)

### `api/tools/{items,summary,custom}.py`
- Function mapping matches design §4 1:1
- No `from __future__ import annotations` (Gemini SDK requirement — `feedback_gemini_tool_schema.md`)
- `execute_custom_query(sql, params: list[str] | None = None, description="")` signature preserved

## Convention Compliance

| Convention | Status |
|------------|--------|
| File naming (snake_case .py) | OK |
| Module-private prefix `_` for internal modules | OK |
| Import order (stdlib → third-party → shared → relative) | OK |
| Single `APIRouter()` per router module | OK |
| Type-annotated public APIs preserved | OK |

## Risk Re-evaluation (vs Design §11)

| Risk | Resolution |
|------|------------|
| Middleware omission | OK — order preserved in main.py:48-57, 75-126 |
| Cache key collisions | OK — string literals unchanged |
| Circular imports | OK — routers only import `_http_helpers`/`_session_store`/`shared`; main only imports routers |
| `_tool_dispatch` import path | OK — `from .tools import ...` resolved via package `__init__.py` |
| `tests/test_input_validation.py` direct import | OK — compat re-export at main.py:28-32 |
| `api/tools.py` name collision | OK — deleted |

## Recommended Actions

### Proceed to Report
Match rate 98% (≥ 90%), all 9 ACs pass. **No iterate cycle needed.**

### Optional Documentation Polish (non-blocking)
Update design §5 `__all__` example to include `_strip_sql_comments`/`_validate_custom_query_params` to reflect the actual re-export contract. Or treat as implementation detail. Either is fine.

## Conclusion

Faithful 1:1 application of design with one positive deviation (test-helper re-exports). Match rate **98%**, **9/9 ACs pass**. Proceed to **Report**.
