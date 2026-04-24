# custom-query-bind-params-v1 Planning Document

> **Summary**: `execute_custom_query`에 named/positional bind parameter 지원 추가 — AI가 사용자 입력을 SQL 리터럴로 직접 삽입하는 패턴을 안전한 placeholder 방식으로 전환
>
> **Project**: Server_API (Production Data Hub)
> **Version**: custom-query-bind-params-v1
> **Author**: interojo
> **Date**: 2026-04-24
> **Status**: Plan

---

## 1. Overview

### 1.1 Purpose

종합 검토(2026-04-23)에서 High로 도출된 H2 잔여 이슈:
> `execute_custom_query`는 다층 보안 검증(SELECT-only, forbidden keyword, production_records 강제)이 있으나, **bind parameter 미지원**으로 AI가 SQL 본문에 literal을 삽입해야 한다. AI tool 입력자 = AI라 직접 위협도는 낮지만, 향후 사용자 raw 입력이 그대로 통과될 경우 SQLi 가능.

현재 AI는 `sql = "SELECT * FROM production_records WHERE item_code = 'BW0021'"` 처럼 literal을 박아서 전달. 이를 `sql = "... WHERE item_code = ?"` + `params = ["BW0021"]` 분리 형태로 전환.

### 1.2 Background

- `api/tools.py:execute_custom_query(sql, description="")` — 현재 시그니처
- 내부는 `conn.execute(sql_clean)` 로 bind parameter 없이 실행
- Gemini tool schema는 Python 함수 시그니처 + docstring에서 자동 생성 (`google-genai` SDK 동작)
- `list[str]`은 Gemini tool 파라미터 타입으로 지원 (Context7 확인 완료)

### 1.3 Related

- 선행 사이클: `security-and-test-improvement` (whitelist + word-boundary keyword), `security-hardening-v3` (ATTACH helper)
- 메모리: `project_sse_contract.md` (도구 변경 시 spec 동기화)
- 메모리: `project_review_fixes_202604_part2.md` ("spec 문서는 매 PDCA 사이클의 AC에 포함")

---

## 2. Scope

### 2.1 In Scope

| ID | Item | Source | Effort |
|----|------|--------|--------|
| B1 | `execute_custom_query` 시그니처 확장: `(sql, params=None, description="")` | H2 | 20min |
| B2 | `params` 타입 검증: `list[str]` 또는 None만 허용 (dict/nested/None-in-list 차단) | H2 | 15min |
| B3 | SQL 실행 시점에 params 바인딩 적용 (`conn.execute(sql, params or ())`) | H2 | 10min |
| B4 | System prompt 업데이트 (`api/chat.py:_build_system_instruction` rule 9) — ? placeholder + params 사용 가이드 + 예시 | spec sync | 15min |
| B5 | `docs/specs/ai_architecture.md §4.7` 도구 명세 갱신 | spec sync | 15min |
| B6 | `docs/specs/api_guide.md §6` 외부 사용자용 가이드 갱신 (예시 `sql`과 `params` 함께) | spec sync | 15min |
| B7 | `tests/test_sql_validation.py` 확장 — params 성공/실패 시나리오 | 안전성 | 25min |

### 2.2 Out of Scope

| Item | Reason |
|------|--------|
| Named bind (`:name` + dict params) | `list[str]` + `?` positional이 더 단순, Gemini ergonomic, SQLite native. Named는 후속 사이클 필요 시 |
| AI에게 params 강제 (literal 전면 금지) | 기존 동작 호환 유지. `params` None일 때 기존 경로 그대로 — gradual adoption |
| Placeholder count vs params length 사전 검증 | SQLite가 `sqlite3.ProgrammingError` 발생시키므로 중복. 에러 메시지만 개선 |
| 숫자/boolean/None 타입 지원 확장 | `list[str]`만 수용. SQLite dynamic typing으로 대부분 numeric 비교 자동 cast. 필요 시 `list[str \| int \| float]` 후속 사이클 |

---

## 3. Acceptance Criteria

| AC | 내용 | 검증 |
|----|------|------|
| AC1 | `execute_custom_query`의 시그니처가 `(sql, params=None, description="")`이고 docstring에 params 설명 있음 | inspect |
| AC2 | `params=None` / `params=[]`일 때 기존 호출 패턴 100% 호환 (backward compat) | pytest (기존 test_sql_validation 모두 pass) |
| AC3 | `params=["BW0021", "2026-01-20"]` + `WHERE item_code = ? AND production_date >= ?` 쿼리 정상 실행, 바인딩됨 | 신규 pytest |
| AC4 | `params`가 list 아닌 타입(dict, str, tuple)일 때 명확한 에러 반환 (`code: INVALID_PARAMS`) | 신규 pytest |
| AC5 | `params`에 dict/list/None 원소 포함 시 에러 반환 (str만 허용) | 신규 pytest |
| AC6 | `_build_system_instruction()` 반환 문자열에 `?` placeholder 및 `params` 키워드 포함 | grep test |
| AC7 | `ai_architecture.md §4.7`에 params 사용법 + 예시, `api_guide.md §6`에 동일 반영 | grep |
| AC8 | 전체 pytest 163 + 신규 테스트 모두 통과 | pytest |
| AC9 | gap-detector 재실행 시 본 사이클 일치율 ≥ 95% | bkit:gap-detector |

---

## 4. Risks

| Risk | Mitigation |
|------|-----------|
| Gemini가 새 `params` 파라미터를 이해하지 못하고 기존 방식(literal 박기)으로 회귀 | system prompt 명시 + 예시. 하지만 backward compat라 최악의 경우에도 정확성 회귀는 없음 |
| `list[str]`로 모든 값을 string으로 받으면 numeric 비교 실패 (`good_quantity > "1000"` TEXT vs INTEGER) | SQLite는 dynamic typing — TEXT param이 INTEGER 컬럼과 비교 시 자동 cast 시도. `good_quantity`는 INTEGER라 OK. 컬럼 정의 기반 안전 판단. 확실하지 않으면 SQL 본문에 `CAST(? AS INTEGER)` 권장 — system prompt에 명시 |
| 기존 테스트 회귀 | backward compat 유지 (params=None 기본값). 기존 테스트 모두 pass 확인 (AC2) |
| Gemini schema 생성 실패 (list[str] 지원 문제) | Context7 확인 결과 Gemini는 `list[str]` 지원. 실제 client 초기화 로그 + /healthz/ai 로 검증 |

---

## 5. Timeline

| Phase | Duration | Owner |
|-------|---------|-------|
| Plan + Design | 0.4h | interojo |
| Act-1: B1+B2+B3 (도구 시그니처 + 검증 + 바인딩) | 0.5h | interojo |
| Act-2: B4 (system prompt) | 0.3h | interojo |
| Act-3: B5+B6 (spec docs) | 0.4h | interojo |
| Act-4: B7 (tests) | 0.4h | interojo |
| Check: gap-detector + pytest | 0.3h | gap-detector |
| Report | 0.2h | report-generator |

총 예상: ~2.5h
