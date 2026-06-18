# C901 Complexity Refactor V1 완료 보고서

> **요약**: C901 4중 위반 함수 2개를 동작 보존하며 분해, 복잡도 게이트 확장.
> **프로젝트**: Server_API | **작성일**: 2026-06-19 | **상태**: 완료(PASS)

## 1. 목표 및 결과

R7 이후 남은 C901 5건 중 검증·빌드·실행 책임이 한 함수에 응축돼 분기(PLR0912)·문장(PLR0915)·인자수(PLR0913) 위반까지 동반하던 2건을 해소했다. 외부 계약(HTTP 쿼리 파라미터, AI tool 반환 dict)을 보존하면서 비공개 헬퍼로 책임을 분리했다.

## 2. 변경 요약

### `api/tools/custom.py` — `execute_custom_query` (C901 17 → 9)
- `_validate_custom_query_sql(sql_clean, sql_upper) -> str | None` 추출: 검증 4종(세미콜론/SELECT only/금지 키워드/테이블 참조), 에러 메시지 문자열 보존.
- `_run_query_with_timeout(conn, sql, params, timeout) -> dict` 추출: daemon thread 실행·timeout·interrupt·close/GC 위임 캡슐화.
- `sqlite3`/`threading` import 모듈 최상단 승격. `shared.config` lazy import는 테스트 monkeypatch 호환 위해 유지.

### `api/routers/records.py` — `get_records` (C901 14 → 3, PLR0913 10 → 1)
- `RecordsFilters(BaseModel)` 도입: 쿼리 파라미터 10종을 `Field`로 이전, `Annotated[RecordsFilters, Query()]`로 주입. FastAPI 0.133이 필드를 개별 쿼리 파라미터로 평면화 → HTTP/OpenAPI 계약 동일.
- `_build_records_filters(...) -> (where, params)` 추출: WHERE 8조건 + 커서절 누적.
- cursor/offset 중복 분기를 단일 union SQL 빌드로 통합(`if not cursor_data and offset > 0` 가드).

### 회귀 방지
- `.github/workflows/ci.yml`: 복잡도 게이트를 3파일(`_chat_stream` + `custom` + `records`)로 확장.
- 신규 테스트: `TestValidateCustomQuerySql`(7), `TestBuildRecordsFilters`(7).

## 3. 검증 결과

| 항목 | 결과 |
|---|---|
| 대상 2파일 C901 | 0건 (17→9, 14→3) |
| PLR0912/0915/0913 (대상) | 해소 |
| Ruff 전체 게이트 | 0건 |
| 백엔드 전체 테스트 | 514 passed, 0 failed |
| 신규 회귀 테스트 | +14 통과 |

## 4. 범위 밖 (차기 라운드)

- 잔여 C901 3건: `_extract_tool_info`(api/chat.py), `render_ai_chat`(dashboard), `run_check`(tools/watcher.py).
- `run_stream`(이미 해소), `ruff format` 채택, G004/DTZ005 일괄정리.

## 5. 학습 및 메모

- FastAPI 0.115+ `Annotated[Model, Query()]`는 다인자 라우트의 PLR0913을 계약 변경 없이 해소하는 정석 패턴.
- 4중 위반(C901+0912+0915+0913)은 대개 "WHERE/검증 빌더" 한 곳에 분기가 몰려 있어, 빌더 추출 한 번으로 동반 위반이 함께 해소됨.
- 동작 보존의 안전망은 기존 통합 테스트(records 11 + sql_validation 30+)였고, 헬퍼 단위 테스트는 분해 경계를 고정하는 보조 역할.

## 6. 커밋 가이드 (레이어별 분할)

1. `refactor(tools): execute_custom_query 검증/실행 헬퍼 분리 (C901 17→9)` — custom.py
2. `refactor(records): RecordsFilters 모델 + 필터 빌더 분리 (C901 14→3, PLR0913 해소)` — records.py
3. `test: C901 리팩터 회귀 테스트 추가` — tests 2파일
4. `ci: 복잡도 게이트를 custom/records로 확장` — ci.yml
5. `docs: c901-complexity-refactor-v1 PDCA 문서` — docs 5종
