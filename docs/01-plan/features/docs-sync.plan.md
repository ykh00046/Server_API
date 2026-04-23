# docs-sync Planning Document

> **Summary**: 종합 검토에서 도출된 설계-구현 갭(89%) 회복 — 문서 4종 동기화
>
> **Project**: Server_API (Production Data Hub)
> **Version**: docs-sync v1
> **Author**: interojo
> **Date**: 2026-04-23
> **Status**: Plan

---

## 1. Overview

### 1.1 Purpose

종합 검토 gap-detector 결과 전체 일치율 **89%** (목표 90% 미달).
가장 큰 갭은 AI Architecture 70%로, v8 코드 진화(도구 7개 + 모듈 분리)를 문서가 따라가지 못함.
문서-only 작업으로 95%+ 회복.

### 1.2 갭 출처
- `bkit:gap-detector` 결과 (대화 컨텍스트, 2026-04-23)

---

## 2. Scope

### 2.1 In Scope

| ID | Item | 갭 출처 | 목표 일치율 |
|----|------|---------|------------|
| D1 | `docs/specs/ai_architecture.md` 도구 7개 + 모듈 분리(`_session_store/_tool_dispatch/_chat_stream/_gemini_client`) + `_build_system_instruction()` + multi-turn 세션 정책 + fallback 모델 + Gemini 2.5 모델명 | 70% → 95% | 25%p ↑ |
| D2 | `docs/specs/api_guide.md`에 `/metrics/performance`, `/metrics/cache`, `POST /chat/stream` 추가. `/records.has_more` 응답 필드 추가, `/chat/.model_used` 추가 | 88% → 95% | 7%p ↑ |
| D3 | `docs/specs/operations_manual.md` §7.4 `POST /cache/clear` (미구현) 안내 → "서버 재시작" 또는 "5분 TTL 대기"로 교체 | 92% → 95% | 3%p ↑ |
| D4 | `docs/specs/system_architecture.md` §2.1 Dashboard 포트 8501 → 8502 (operations_manual과 통일). AI 도구 표(§6.4 §6 도구 목록)에 7개 모두 반영 | 95% → 98% | 3%p ↑ |

### 2.2 Out of Scope

| Item | Reason |
|------|--------|
| `/cache/clear` 엔드포인트 신규 구현 | 공격 표면 증가 + 5분 TTL로 충분, 서버 재시작이 더 안전 |
| v8_consolidated_roadmap.md 갱신 | 별도 사이클(`roadmap-v9`)에서 다룸 |
| 영문 번역 / API spec OpenAPI 자동 생성 | 별도 사이클 |
| SSE 이벤트 계약 정식 명세화 | 메모리 `project_sse_contract.md`에 이미 존재, 필요 시 별도 사이클 |

---

## 3. Acceptance Criteria

| AC | 내용 | 검증 방법 |
|----|------|----------|
| AC1 | `ai_architecture.md`에 도구 7개 명세 + 4개 모듈 분리 + `_build_system_instruction` + multi-turn 세션 + fallback + `gemini-2.5-flash` 반영 | grep / read |
| AC2 | `api_guide.md`에 `/metrics/performance`, `/metrics/cache`, `POST /chat/stream` 섹션 추가 | grep |
| AC3 | `api_guide.md` `/records` 응답 예시에 `has_more`, `/chat/` 응답에 `model_used` 추가 | grep |
| AC4 | `operations_manual.md`에 `POST /cache/clear` 잔존 0건 (대체 안내로 교체) | grep |
| AC5 | `system_architecture.md` Dashboard 포트 8502, 도구표 7개 | grep / read |
| AC6 | gap-detector 재실행 시 docs 영역 가중평균 ≥ 95% | bkit:gap-detector |

---

## 4. Risks

| Risk | Mitigation |
|------|-----------|
| 문서만 수정해 코드와 라인 번호 어긋남 | 라인 번호 대신 함수명/심볼명 참조 |
| `system_architecture.md`의 "현재 도구 5개"라는 토큰 효율 분석이 7개 기준으로 재해석 필요 | "5~7개"라는 원칙 유지하되 현재 구성을 7개로 명시. 권장 상한은 그대로 유지 |
| `_session_store` 등 `_`-prefix 모듈은 internal API임이 문서 reader에게 헷갈릴 수 있음 | "내부 모듈(`_*`)" 표기로 명시 |
