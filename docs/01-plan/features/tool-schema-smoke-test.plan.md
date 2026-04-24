# tool-schema-smoke-test Planning Document

> **Summary**: PRODUCTION_TOOLS 7개의 Gemini schema 생성을 pytest로 smoke 검증 — custom-query-bind-params-v1에서 드러난 "signature drift → 400 INVALID_ARGUMENT" 재발 방지
>
> **Project**: Server_API (Production Data Hub)
> **Version**: tool-schema-smoke-test v1
> **Author**: interojo
> **Date**: 2026-04-24
> **Status**: Plan

---

## 1. Overview

### 1.1 Purpose

2026-04-24 런타임 발생한 `400 INVALID_ARGUMENT … properties[params].items: missing field`는
design에는 `list[str]`로 명세되었으나 실제 코드가 `list`로 구현된 drift 때문이었음. 런타임 전까지
감지 안 됨. 매 PR에서 schema 생성을 smoke 검증해 같은 류의 실수를 CI 단계에서 잡는다.

### 1.2 Background

- Gemini `FunctionDeclaration.from_callable(client=..., callable=fn)`은 Python 함수 시그니처
  + docstring에서 JSON Schema 생성.
- Element type 없는 `list`, 잘못된 Optional 표기, 지원 안 되는 union, docstring 누락 등이
  100% 컴파일 pass이지만 Gemini가 거부.
- 기존 178 테스트는 런타임 검증(`_validate_custom_query_params`, `execute_custom_query`)은
  하지만 **schema 생성 단계** 커버리지가 0.

### 1.3 Related
- `custom-query-bind-params-v1` (직전 사이클)
- 런타임 fix commit: `90417d6 fix(tools): specify list[str] element type...`

---

## 2. Scope

### 2.1 In Scope

| ID | Item | Effort |
|----|------|--------|
| T1 | `tests/test_tool_schemas.py` 신규 — `_FakeClient` stub으로 API key 없이 schema 생성 | 20min |
| T2 | 모든 `PRODUCTION_TOOLS` 원소를 pytest parametrize로 순회 | 포함 |
| T3 | 각 도구에 대해: name 일치, description non-empty, parameters.properties non-empty | 포함 |
| T4 | **핵심 회귀 방지**: 모든 ARRAY 타입 property의 `items`가 non-None + valid type 보유 | 10min |
| T5 | 모든 property의 `type`이 `Type.TYPE_UNSPECIFIED`가 아님 (unknown 타입 힌트 감지) | 10min |

### 2.2 Out of Scope

| Item | Reason |
|------|--------|
| Actual Gemini API round-trip 검증 | 네트워크/quota 필요. 본 테스트는 offline smoke로 충분 |
| response schema 검증 | 현재 도구는 response schema 미사용 |
| SDK 버전 pinning | requirements 별도 사이클 |
| CI integration (GitHub Actions 등) | 현재 pytest 수동 실행 구조 유지 |

---

## 3. Acceptance Criteria

| AC | 내용 | 검증 |
|----|------|------|
| AC1 | `tests/test_tool_schemas.py` 존재하고 `_FakeClient` 기반 (API key 불필요) | inspect |
| AC2 | `PRODUCTION_TOOLS` 7개 모두 parametrize 순회 (pytest `-v`에서 7 test 라인) | pytest |
| AC3 | 각 도구의 schema 생성 성공 (`FunctionDeclaration.from_callable` 예외 없음) | pytest |
| AC4 | 모든 ARRAY property의 `items`가 None 아님 (핵심 회귀 방지) | pytest |
| AC5 | 모든 property의 `type`이 `TYPE_UNSPECIFIED` 아님 | pytest |
| AC6 | 기존 178 회귀 없음 + 신규 테스트 추가 | pytest |
| AC7 | gap-detector 재실행 시 본 사이클 일치율 ≥ 95% | bkit:gap-detector |

---

## 4. Risks

| Risk | Mitigation |
|------|-----------|
| `FunctionDeclaration.from_callable` API가 google-genai 업그레이드로 변경 | 테스트가 먼저 깨지므로 오히려 조기 감지 이점 — Mitigation 불필요 |
| `_FakeClient.vertexai=False`가 향후 SDK에서 추가 속성 요구 | 속성 AttributeError 발생 시 FakeClient에 추가. 실패해도 real client fallback 가능 |
| 도구 함수에 closure/lambda 사용 시 introspection 실패 | 현재 모든 도구는 top-level `def` — 문제 없음 |

---

## 5. Timeline

| Phase | Duration |
|-------|---------|
| Plan + Design | 0.2h |
| Act: 테스트 구현 (T1~T5) | 0.4h |
| Check: pytest + gap-detector | 0.1h |
| Report | 0.1h |

총 예상: ~0.8h
