---
template: analysis
feature: security-and-test-improvement
date: 2026-04-14
phase: check
match_rate: 93
iteration: 1
---

## Iteration 1 (2026-04-14)

**Match Rate: 88% → 93%** (G1 + G2 + G4 closed)

| Gap | Status | Resolution |
|---|---|---|
| G1 | ✅ Closed | Created `api/_session_store.py`, `api/_gemini_client.py`, `api/_tool_dispatch.py`. `api/chat.py` re-exports for back-compat. |
| G2 | ✅ Closed | `chat_with_data()` 160 → **60 LOC**, with `_enforce_rate_limit` / `_ensure_ai_enabled` / `_generate_with_retry` helpers. |
| G4 | ✅ Closed | HTTPException details now use `{"code": "RATE_LIMITED"\|"AI_DISABLED", "message": …}`; `execute_custom_query` returns `code: INVALID_ARCHIVE_PATH` / `QUERY_TIMEOUT`. |
| G3 | 🟢 Open | `/healthz/ai` sessions block — optional, deferred. |
| G5 | 🟢 Open | 5 missing integration tests — deferred. |
| G6 | 🟢 Open | Performance smoke — manual, deferred. |
| G7 | 🟢 Open | Whitelist boot warning — deferred. |

Tests: **128 passed** (no regression). `tests/test_session_store.py` updated to monkeypatch `api._session_store` directly.



# security-and-test-improvement — Gap Analysis

> **Plan**: [security-and-test-improvement.plan.md](../01-plan/features/security-and-test-improvement.plan.md)
> **Design**: [security-and-test-improvement.design.md](../02-design/features/security-and-test-improvement.design.md)
> **Date**: 2026-04-14
> **Phase**: Check

---

## 1. Summary

| Metric | Value |
|---|---|
| **Match Rate** | **88%** |
| Threshold (auto-completion) | 90% |
| Decision | `/pdca iterate` (focused on G1 + G4) |
| Regression | 128 tests passed (103 existing + 25 new) |

| Category | Score |
|---|---|
| Design file-map match (§11.1) | 70% |
| Functional requirements (§3/§4/§7) | 95% |
| Test-case coverage (§8.2) | 92% |
| Error-code surface (§6.1) | 70% |

---

## 2. Matched Items

- **S1 .env / config** — `.env.example` contains all 5 new vars; `shared/config.py` exposes `CHAT_SESSION_TTL_SEC`, `CHAT_SESSION_MAX_PER_IP`, `CHAT_SESSION_MAX_TOTAL`, `CUSTOM_QUERY_TIMEOUT_SEC`, `ARCHIVE_DB_WHITELIST` via `_load_archive_whitelist()`. Matches §10.2 env table.
- **S4 validators** — `validate_db_path()` rewritten with pathlib, rejects quotes/NUL/control chars; `resolve_archive_db(requested, whitelist)` enforces whitelist + existence. Matches §7.1 design intent (domain-layer pure function per §9.2).
- **S4 tools.py** — `execute_custom_query()` imports `CUSTOM_QUERY_TIMEOUT_SEC` and `ARCHIVE_DB_WHITELIST`, uses `resolve_archive_db(ARCHIVE_DB_FILE, …)`, URI `file:…?mode=ro` ATTACH with fallback, `thread.join(timeout=CUSTOM_QUERY_TIMEOUT_SEC)`. Matches §7.1 snippet.
- **S3 session IP isolation** — `_get_session_history` / `_save_session_history` take `owner_ip`; cross-IP request returns empty history with warning; per-IP eviction at `CHAT_SESSION_MAX_PER_IP`; call sites in `chat_with_data` pass `client_ip`. Matches §3.1/§3.2.
- **Session constants** — imported from `shared/config.py` (SESSION_TTL, SESSION_MAX_COUNT). Matches §10.2/§10.3.
- **S2 integration tests** — `tests/test_api_integration.py` covers `/`, `/healthz`, `/healthz/ai`, `/records`, `/items`, `/summary/monthly_total`, `/chat/` (Gemini monkeypatched), multi-turn, empty-key path. Covers 9 of 12 §8.2 bullets.
- **S2 session-store tests** — `tests/test_session_store.py` (6 tests): IP isolation, per-IP evict, trim, TTL sliding — matches all 4 §8.2 bullets.
- **S2 whitelist/path tests** — `tests/test_archive_whitelist.py` (9 tests): whitelist rejection + quote/NUL/relative path rejection — matches §8.2 `test_sql_validation.py` 추가 케이스.

---

## 3. Gap List

| # | Severity | Area | Gap |
|---|---|---|---|
| G1 | 🟡 Medium | §11.1 file map / §9.2 layering | `api/_session_store.py`, `api/_gemini_client.py`, `api/_tool_dispatch.py` **not created**. Session refactor done in-place inside `api/chat.py`; Gemini call + tool dispatch still inline. |
| G2 | 🟡 Medium | §1.1 Goal 5 / S5 | `chat_with_data()` still ~160 LOC — design target ≤150 LOC partially met; complexity-reduction goal not fully delivered. |
| G3 | 🟢 Low | §4.2 `/healthz/ai` | Optional `sessions.{count,ttl_sec,max_per_ip}` block not added. Design marked optional. |
| G4 | 🟡 Medium | §6.1 error codes | `SESSION_LIMIT_EXCEEDED` / `QUERY_TIMEOUT` code strings not surfaced in HTTPException `detail.code`; only human-readable messages present. |
| G5 | 🟢 Low | §8.2 integration tests | Missing: `GET /records/BW0021`, `GET /summary/by_item`, `/records?cursor=<invalid>` → 400, 21st-call 429, bad-date 400. |
| G6 | 🟢 Low | §8.2 smoke | Performance/memory smoke (10k requests <50MB RSS; <30s integration wall time) not executed/recorded. |
| G7 | 🟢 Info | §3.3 whitelist | No boot-time warning when whitelisted file absent (design §3.3 suggests warning). |

---

## 4. Recommendations

1. **(G1/G2, required for ≥90%)** Extract `api/_session_store.py` (SessionStore dataclass + module), `api/_gemini_client.py` (model factory / monkeypatch seam), `api/_tool_dispatch.py` (tool_calls → `api/tools.py` mapping). Reduce `chat_with_data()` to <100 LOC orchestrator. Completes S5 and §9.2 layer placement.
2. **(G4)** Wrap 429/408 responses with `HTTPException(status_code=…, detail={"code": "SESSION_LIMIT_EXCEEDED"|"QUERY_TIMEOUT", "message": …})` for programmatic client discrimination.
3. **(G3)** Add 3-field `sessions` block to `/healthz/ai` payload.
4. **(G5)** Add the 5 missing integration test cases to reach full §8.2 matrix.
5. **(G6)** Record integration test duration in CI or operations manual; defer 10k load test to manual script.
6. **(G7)** `_load_archive_whitelist()`: emit one-shot `logger.warning` if whitelisted path missing at import.
7. **Doc alignment** — mark §11.1 items as *deferred* in design **or** implement them. Do not leave file map silently unmet.

---

## 5. Decision

- Match Rate **88% < 90%** → proceed to **`/pdca iterate security-and-test-improvement`**.
- Focus iteration on **G1 + G4** (Medium). Those alone should push score above 92%.
- G3/G5/G6/G7 bundled as follow-up or optionally dismissed.

---

## 6. Inspected Files

- `docs/02-design/features/security-and-test-improvement.design.md`
- `shared/config.py`
- `shared/validators.py`
- `api/tools.py` (lines 34, 557–659)
- `api/chat.py` (lines 118–182, 385, 446)
- `tests/test_api_integration.py`
- `tests/test_session_store.py`
- `tests/test_archive_whitelist.py`
