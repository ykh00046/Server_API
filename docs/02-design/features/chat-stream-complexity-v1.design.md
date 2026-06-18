# Chat Stream Complexity V1 설계서

> **계획서**: `docs/01-plan/features/chat-stream-complexity-v1.plan.md` | **작성일**: 2026-06-19 | **상태**: 완료

## Context Anchor

| Key | Value |
|---|---|
| WHY | 복잡도 22인 핵심 스트림 함수의 회귀 위험 축소 |
| WHO | `/chat/stream` 소비자와 유지보수 개발자 |
| RISK | SSE 순서, fallback, 세션 저장 동작 변경 |
| SUCCESS | C901·Ruff·관련/전체 테스트 통과 |
| SCOPE | 스트림 내부 책임 분리와 회귀 게이트 |

## 1. 설계 목표

공개 `run_stream`은 오케스트레이션만 담당하고 provider 호출, 청크 변환, 가변 상태를 분리한다. 공개 시그니처와 SSE 스키마는 바꾸지 않는다.

## 2. 아키텍처 옵션

| 옵션 | 방식 | 복잡도 | 유지보수성 | 위험 |
|---|---|---:|---:|---:|
| A 최소 변경 | 일부 조건문만 추출 | 낮음 | 중간 | 중간 |
| B Clean | 새 모듈과 인터페이스 계층 도입 | 높음 | 높음 | 중간 |
| C 실용적 균형 | 동일 파일의 상태 객체·내부 헬퍼 분리 | 중간 | 높음 | 낮음 |

**선택: C.** 단일 소비자와 안정된 계약에 새 계층은 과도하며, 동일 파일 내부 분리만으로 목표를 달성할 수 있다.

## 3. 구성 요소와 흐름

`run_stream` → `_open_model_stream` → `_consume_stream` → `_frames_from_chunk` → `_tool_calls_from_chunk`. `_StreamState`가 텍스트 버퍼, tool 호출, 실패 여부를 소유한다.

## 4. API 명세

`POST /chat/stream`과 `run_stream(query, session_id, client_ip, request_id, system_instruction)`는 변경하지 않는다. 이벤트 종류와 payload도 동일하다.

## 5. UI/UX

해당 없음. 첫 token 즉시 전송, heartbeat, timeout 동작을 그대로 유지한다.

## 6. 오류 처리

- AI 비활성: `ai_disabled`
- 모델/fallback 생성 실패: `model_error`
- timeout: `timeout`
- 소비 중 예외: `internal`
- `_StreamState.failed`가 오류 후 `done` 및 세션 저장을 차단한다.

## 7. 보안

입력, 인증, rate limit 경계는 변경하지 않는다. provider 오류 메시지는 기존처럼 500자로 제한한다.

## 8. 테스트 계획

| 수준 | 시나리오 | 기대값 |
|---|---|---|
| L1 | 정상 token/tool/done | 이벤트 순서 유지 |
| L1 | primary/fallback 오류 | 기존 오류 코드 유지 |
| L1 | timeout/heartbeat | error 또는 comment 정상 송출 |
| L1 | 잘못된 tool args | `{}`로 정규화 후 done |
| 정적 | Ruff + C901 | 0건 |
| 회귀 | 전체 pytest | 전부 통과 |

## 9. 구현 순서

1. 결과·상태 dataclass 추가
2. 모델 열기와 fallback 추출
3. tool/청크 변환 추출
4. stream 소비와 오류 경계 추출
5. malformed args 테스트 및 CI C901 게이트 추가

## 10. 추적성

FR-01~03은 기존 15개 스트림 테스트와 fallback 테스트, FR-04는 신규 테스트, NFR-01은 CI 명령으로 검증한다.

## 11. Implementation Guide

### 11.1 변경 파일

- 수정: `api/_chat_stream.py`, `tests/test_chat_stream.py`, `.github/workflows/ci.yml`
- 생성: PDCA 문서 5종

### 11.2 완료 조건

공개 계약 변화 없이 모든 품질 명령이 성공해야 한다.

### 11.3 Session Guide

| 모듈 | 작업 | 세션 |
|---|---|---|
| module-1 | 코드·테스트·CI·문서 | 단일 세션 |
