# Chat Stream Complexity V1 계획서

> **요약**: `/chat/stream` 핵심 오케스트레이터의 순환 복잡도를 낮추고 회귀 방지 게이트를 추가한다.
> **프로젝트**: Server_API | **작성일**: 2026-06-19 | **상태**: 완료

## Executive Summary

| 관점 | 내용 |
|---|---|
| Problem | `run_stream`이 모델 선택, fallback, 청크 해석, 버퍼링, 오류 처리를 한 함수에서 수행해 C901 복잡도 22를 기록했다. |
| Solution | 외부 계약을 유지하면서 모델 스트림 생성, 청크 변환, 스트림 소비 상태를 내부 헬퍼로 분리한다. |
| Function/UX Effect | SSE 이벤트 순서와 응답은 유지되고, 오류·heartbeat·fallback 수정 시 영향 범위가 명확해진다. |
| Core Value | 핵심 AI 스트리밍 경로의 변경 안전성과 검증 가능성을 높인다. |

## Context Anchor

| Key | Value |
|---|---|
| WHY | 복잡도 22인 핵심 스트림 함수의 회귀 위험 축소 |
| WHO | `/chat/stream` 소비자와 유지보수 개발자 |
| RISK | 리팩터링 중 SSE 순서, fallback, 세션 저장 동작 변경 |
| SUCCESS | `run_stream` C901 0건, 관련 테스트 및 전체 테스트 통과, Ruff 0건 |
| SCOPE | `api/_chat_stream.py`, 스트림 회귀 테스트, CI 복잡도 게이트 |

## 1. 개요

기존 R7 품질 개선 이후 남은 C901 6건 중 가장 복잡하고 사용자 요청 경로에 직접 연결된 `run_stream`을 첫 대상으로 선정한다.

## 2. 범위

- 포함: 내부 책임 분리, 잘못된 tool args 회귀 테스트, 대상 파일 C901 CI 게이트.
- 제외: SSE 공개 계약 변경, 다른 C901 5건, 성능 튜닝, 라이브 Gemini 호출.

## 3. 요구사항

| ID | 요구사항 | 우선순위 |
|---|---|---|
| FR-01 | `meta → tool_call/token → done` 계약을 보존한다. | 높음 |
| FR-02 | primary/fallback 및 구조화 오류 코드를 보존한다. | 높음 |
| FR-03 | 성공한 세션만 저장한다. | 높음 |
| FR-04 | 잘못된 tool args는 빈 객체로 정규화한다. | 중간 |
| NFR-01 | `run_stream`의 C901 위반을 제거하고 CI에서 재발을 차단한다. | 높음 |

## 4. 성공 기준

- [x] 대상 C901 검사 통과
- [x] 스트림·fallback 테스트 통과
- [x] 전체 테스트 및 Ruff 통과
- [x] PDCA 문서 완료

## 5. 위험 및 완화

| 위험 | 영향 | 완화 |
|---|---|---|
| 이벤트 순서 변경 | 높음 | 기존 계약 테스트 전체 실행 |
| 부분 응답 저장 | 높음 | 실패 상태를 명시하고 성공 경로에서만 저장 |
| fallback 메타데이터 변경 | 중간 | 결과 객체에 모델/fallback 상태를 함께 반환 |

## 6. 영향 분석

직접 소비자는 `api.chat.chat_stream` 하나이며 공개 함수 시그니처는 유지한다. 테스트 소비자는 `test_chat_stream.py`, `test_chat_fallback.py`이다. 데이터베이스·인증·환경변수 변경은 없다.

## 7. 아키텍처 결정

Dynamic 수준의 Python/FastAPI 구조를 유지한다. 새 모듈을 만들지 않고 동일 파일의 비공개 헬퍼로 분리하는 실용적 균형안을 채택한다.

## 8. 규칙

Ruff 기존 규칙과 Python 3.12 타입 표기를 따른다. provider SDK 경계의 광범위 예외만 근거가 있는 `BLE001` 예외로 유지한다.

## 9. 다음 단계

Design → Do → Check → Iterate → QA → Report를 연속 실행한다.
