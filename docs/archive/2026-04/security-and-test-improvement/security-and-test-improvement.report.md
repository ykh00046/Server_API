---
template: report
feature: security-and-test-improvement
date: 2026-04-14
phase: completed
match_rate: 93
status: completed
---

# security-and-test-improvement — 완료 보고서

> **Plan**: [security-and-test-improvement.plan.md](../01-plan/features/security-and-test-improvement.plan.md)
> **Design**: [security-and-test-improvement.design.md](../02-design/features/security-and-test-improvement.design.md)
> **Analysis**: [security-and-test-improvement.analysis.md](../03-analysis/security-and-test-improvement.analysis.md)
> **Date**: 2026-04-14

---

## 1. Executive Summary

Production Data Hub의 Top 5 보안·테스트 이슈(S1~S5)를 PDCA 사이클로 해소했다. Match Rate **88% → 93%** (Iteration 1 완료, 임계값 90% 달성), 회귀 없음(128/128 pass).

| 지표 | 결과 |
|---|---|
| Match Rate | **93%** (threshold 90%) |
| 테스트 | **128 passed** (103 기존 + 25 신규) |
| 회귀 | 0건 |
| `chat_with_data()` LOC | 160 → **60** (design target ≤150) |
| 신규 모듈 | 3 (`_session_store`, `_gemini_client`, `_tool_dispatch`) |
| Iteration | 1 / 5 |

---

## 2. Plan 요약 (Top 5)

| ID | 이슈 | 요구사항 |
|---|---|---|
| S1 | `.env.example` 노후 / 누락 | 신규 5개 환경변수 추가 |
| S2 | API 통합 테스트 부재 | FastAPI TestClient 기반 12+ 케이스 |
| S3 | 세션 IP 격리 및 용량 제한 부재 | per-IP isolation + TTL sliding + eviction |
| S4 | `execute_custom_query` ATTACH 경로 검증 부실 | whitelist + pathlib + URI 파라미터 바인딩 |
| S5 | `chat.py` 단일 파일 비대화 (≈800 LOC) | 모듈 추출, `chat_with_data()` ≤150 LOC |

---

## 3. Design 요약

- **§3 세션**: `owner_ip` 바인딩, 교차 IP 요청 시 empty history + warning, `CHAT_SESSION_MAX_PER_IP` 초과 시 LRU eviction
- **§6.1 에러 코드**: `RATE_LIMITED` / `AI_DISABLED` / `SESSION_LIMIT_EXCEEDED` / `INVALID_ARCHIVE_PATH` / `QUERY_TIMEOUT`
- **§7.1 쿼리**: `resolve_archive_db()` pure function, URI `file:…?mode=ro` ATTACH + fallback
- **§9.2 레이어링**: `api/chat.py` 는 orchestrator로 축소, 세션/Gemini/툴 디스패치 분리
- **§11.1 file map**: `api/_session_store.py`, `api/_gemini_client.py`, `api/_tool_dispatch.py`

---

## 4. Do — 구현 결과

### 4.1 신규/수정 파일

**신규**
- `api/_session_store.py` — `_sessions`, `get/save_session_history()`, `cleanup_expired_sessions()`, `stats()`
- `api/_gemini_client.py` — `get_client()` lazy factory, `reset_for_tests()` (테스트 seam)
- `api/_tool_dispatch.py` — `PRODUCTION_TOOLS` 레지스트리
- `tests/test_api_integration.py` — TestClient 12 tests, Gemini `_FakeClient` monkeypatch
- `tests/test_session_store.py` — 6 tests (IP 격리 / evict / trim / TTL)
- `tests/test_archive_whitelist.py` — 9 tests (quote/NUL/control char/traversal)

**수정**
- `.env.example` — `CHAT_SESSION_TTL_SEC`, `CHAT_SESSION_MAX_PER_IP`, `CHAT_SESSION_MAX_TOTAL`, `CUSTOM_QUERY_TIMEOUT_SEC`, `ARCHIVE_DB_WHITELIST`
- `shared/config.py` — 상수 + `_load_archive_whitelist()` → `ARCHIVE_DB_WHITELIST: tuple[Path, ...]`
- `shared/validators.py` — `validate_db_path()` pathlib 재작성 + `resolve_archive_db()`
- `api/tools.py` — `execute_custom_query` 에 whitelist / URI ATTACH / timeout / `INVALID_ARCHIVE_PATH`·`QUERY_TIMEOUT` 코드
- `api/chat.py` — 세션/Gemini/툴 분리, `_enforce_rate_limit` / `_ensure_ai_enabled` / `_generate_with_retry` 추출, `chat_with_data()` 60 LOC, back-compat re-export 유지

### 4.2 테스트 커버리지

| 파일 | 케이스 | 상태 |
|---|---|---|
| `test_api_integration.py` | 12 (/, /healthz, /healthz/ai, /records, /items, /summary/monthly_total, /chat 단일/다중턴/빈키) | ✅ |
| `test_session_store.py` | 6 (empty / same-IP / cross-IP / per-IP evict / trim / last_access) | ✅ |
| `test_archive_whitelist.py` | 9 (quote/NUL/control/relative/whitelist/existence) | ✅ |
| **합계 (신규)** | **25** | ✅ |
| **전체** | **128** | **pass** |

---

## 5. Check — Gap 분석

### 5.1 초기 분석 (Match Rate 88%)

| Gap | Severity | 내용 |
|---|---|---|
| G1 | 🟡 Medium | `api/_session_store.py` / `_gemini_client.py` / `_tool_dispatch.py` 미생성, `chat.py` 인라인 |
| G2 | 🟡 Medium | `chat_with_data()` ~160 LOC (target ≤150) |
| G3 | 🟢 Low | `/healthz/ai` 에 `sessions` 블록 미추가 (optional) |
| G4 | 🟡 Medium | `SESSION_LIMIT_EXCEEDED` / `QUERY_TIMEOUT` 코드 미노출 |
| G5 | 🟢 Low | 5 개 통합 테스트 누락 |
| G6 | 🟢 Low | 성능 스모크 미실행 |
| G7 | 🟢 Info | whitelist 부재 boot warning 미구현 |

### 5.2 Iteration 1 (88 → 93%)

| Gap | 상태 | 조치 |
|---|---|---|
| G1 | ✅ Closed | 3 모듈 추출 + `api/chat.py` re-export shim |
| G2 | ✅ Closed | `chat_with_data()` 160 → 60 LOC |
| G4 | ✅ Closed | HTTPException dict detail `{code, message}` 적용 |
| G3/G5/G6/G7 | 🟢 Deferred | Low/Info, 후속 이슈로 이관 |

---

## 6. 잔여 항목 (후속)

1. **G3** `/healthz/ai` 에 `sessions.{count,ttl_sec,max_per_ip}` 블록 추가 — 운영 관측성 개선
2. **G5** 추가 통합 테스트 5종: `GET /records/BW0021`, `/summary/by_item`, `/records?cursor=<invalid>`, 21st-call 429, bad-date 400
3. **G6** 성능 스모크 (10k req <50MB RSS, 통합 suite <30s 벽시계) 기록
4. **G7** `_load_archive_whitelist()` 부재 경로에 대한 one-shot `logger.warning`

---

## 7. 배운 점

- **모듈 경계를 먼저 확정하라** — `_session_store`/`_gemini_client`/`_tool_dispatch` 분리를 Do 단계에서 미룬 결과 G1+G2 가 한 묶음으로 발생. Iteration 1 에서 일괄 해소 가능했던 것은 re-export shim 덕분.
- **에러 코드 surface 는 Design 체크리스트화** — 메시지만 있고 `code` 필드가 빠지면 프로그래매틱 클라이언트 분기 불가. §6.1 표를 그대로 HTTPException dict 로 매핑하는 패턴이 유효.
- **테스트 monkeypatch 대상은 실제 정의 모듈** — `chat.py` 에서 re-export 한 상수를 monkeypatch 해도 `_session_store` 내부 함수에는 영향 없음. 이를 반영해 테스트가 `_session_store` 모듈을 직접 patch 하도록 수정.
- **SQLite ATTACH 보안** — URI 파라미터 바인딩 + whitelist 이중 방어가 구형 SQLite 빌드에서도 안정적이다 (fallback 경로 포함).

---

## 8. 결론

- Match Rate **93%** 로 임계값 통과, 회귀 0.
- Top 5 이슈(S1~S5) 모두 해소 혹은 완화.
- 잔여 4개 gap 은 Low/Info 로 백로그 이관 가능.
- **Phase**: `completed` → `/pdca archive` 진행 가능.
