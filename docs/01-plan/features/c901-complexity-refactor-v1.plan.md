# C901 Complexity Refactor V1 계획서

> **요약**: C901 복잡도 4중 위반(복잡도/분기/문장/인자수) 함수 2개를 동작 보존하며 분해한다.
> **프로젝트**: Server_API | **작성일**: 2026-06-19 | **상태**: 완료

## Executive Summary

| 관점 | 내용 |
|---|---|
| Problem | `execute_custom_query`(C901 17)와 `get_records`(C901 14)가 검증·빌드·실행을 한 함수에서 처리해 분기(PLR0912)·문장(PLR0915)·인자수(PLR0913) 위반까지 동반한다. |
| Solution | 외부 계약(HTTP 쿼리 파라미터, AI tool 반환 형태)을 유지한 채 가드절/검증/빌드/실행 단계를 비공개 헬퍼로 분리한다. |
| Function/UX Effect | API 응답·검증 메시지·SSE 무관 동작은 동일하고, 검증 규칙·페이지네이션 수정 시 영향 범위가 좁아진다. |
| Core Value | 핵심 데이터 조회 경로의 변경 안전성과 회귀 차단성을 높인다. |

## Context Anchor

| Key | Value |
|---|---|
| WHY | R7 이후 남은 C901 5건 중 4중 위반이 겹쳐 ROI가 가장 높은 2건 우선 해소 |
| WHO | `/records` HTTP 소비자, `execute_custom_query` AI tool 호출 경로, 유지보수 개발자 |
| RISK | 리팩터링 중 SQL 검증 규칙, 바인드 파라미터, 커서/offset 페이지네이션, 타임아웃 동작 변경 |
| SUCCESS | 대상 2파일 C901 0건, 기존 + 신규 회귀 테스트 통과, Ruff 게이트 0건, CI C901 게이트 확장 |
| SCOPE | `api/tools/custom.py`, `api/routers/records.py`, 관련 테스트, CI 복잡도 게이트 |

## 1. 개요

직전 PDCA(chat-stream-complexity-v1)에서 `run_stream`을 해소했고, 남은 C901 5건 중 검증·빌드·실행 책임이 한 함수에 응축돼 분기·문장·인자수 위반까지 동반하는 2건을 다음 대상으로 선정한다.

## 2. 범위

- 포함: 두 함수의 책임 분리(헬퍼 추출), `get_records` 쿼리 파라미터의 Pydantic 모델화, 신규 회귀 테스트, 대상 파일 C901 CI 게이트 확장.
- 제외: `run_stream`(SSE 계약, 이미 해소됨), `ruff format` 채택, G004/DTZ005 일괄정리, 남은 C901 3건(`_extract_tool_info`, `render_ai_chat`, `run_check`).

## 3. 요구사항

| ID | 요구사항 | 우선순위 |
|---|---|---|
| FR-01 | `execute_custom_query`의 검증 규칙(세미콜론·SELECT only·금지 키워드·테이블 참조·LIMIT 자동추가)을 그대로 보존한다. | 높음 |
| FR-02 | 바인드 파라미터 검증과 INVALID_PARAMS/QUERY_TIMEOUT/INVALID_ARCHIVE_PATH 코드 및 반환 형태를 보존한다. | 높음 |
| FR-03 | 타임아웃 시 daemon thread + GC 위임(연결 누수 허용) 동작을 보존한다. | 높음 |
| FR-04 | `/records`의 필터·검색·lot prefix·수량범위·날짜범위·커서/offset 페이지네이션 결과를 보존한다. | 높음 |
| FR-05 | `/records` 쿼리 파라미터의 HTTP 계약(이름·기본값·제약·deprecated offset 경고)을 보존한다. | 높음 |
| NFR-01 | 두 함수의 C901/PLR0912/PLR0915/PLR0913 위반을 제거하고 CI에서 재발을 차단한다. | 높음 |

## 4. 성공 기준

- [x] `api/tools/custom.py`, `api/routers/records.py` C901 검사 통과
- [x] PLR0912/PLR0915/PLR0913 대상 위반 제거
- [x] 기존 records(11)·sql_validation(30+) 테스트 + 신규 회귀 테스트 통과
- [x] 전체 테스트 및 Ruff 게이트 통과
- [x] PDCA 문서 완료

## 5. 위험 및 완화

| 위험 | 영향 | 완화 |
|---|---|---|
| 검증 규칙 누락/순서 변경 | 높음 | 기존 sql_validation 테스트 전건 실행 + 헬퍼 경계 단위 테스트 추가 |
| 페이지네이션 결과 변경 | 높음 | cursor/offset/has_more/next_cursor 기존 테스트 + WHERE 빌더 단위 테스트 |
| Pydantic 모델화로 OpenAPI/검증 동작 변경 | 중간 | FastAPI 0.133 `Annotated[Model, Query()]`로 쿼리 파라미터 계약 동일 유지, TestClient 회귀로 검증 |
| 타임아웃 경로 동작 변경 | 중간 | 헬퍼는 연결 close/interrupt 책임만 이전, 반환 분기는 호출부에 유지 |

## 6. 영향 분석

- `execute_custom_query` 소비자: AI tool 레지스트리(`api/chat.py`)와 `test_sql_validation.py`, `test_ai_tools_db.py`. 공개 시그니처·반환 dict 유지.
- `get_records` 소비자: HTTP 클라이언트, `test_routers_db.py`, `test_api_integration.py`. 쿼리 파라미터 계약 유지.
- DB·인증·환경변수 변경 없음. 신규 비공개 헬퍼만 추가.

## 7. 아키텍처 결정

Dynamic 수준의 Python/FastAPI 구조를 유지한다. 새 모듈을 만들지 않고 동일 파일의 비공개 헬퍼로 분리하는 실용적 균형안을 채택한다. `get_records`의 PLR0913는 FastAPI 권장 패턴인 쿼리 파라미터 모델(`Annotated[RecordsFilters, Query()]`)로 해소한다.

## 8. 규칙

Ruff 기존 게이트(F/BLE001/I/UP/B/SIM/E501)와 Python 3.12 타입 표기를 따른다. provider/tool 경계의 광범위 예외만 근거 있는 `BLE001` 예외로 유지한다. `custom.py`의 lazy import(테스트 monkeypatch 호환)는 유지한다.

## 9. 다음 단계

Design → Do → Check → Iterate → QA → Report를 연속 실행한다.
