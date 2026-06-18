# C901 Complexity Refactor V1 설계서

> **요약**: 두 함수의 검증/빌드/실행 책임을 비공개 헬퍼로 분리하는 구조 설계.
> **프로젝트**: Server_API | **작성일**: 2026-06-19 | **상태**: 완료

## 1. 설계 목표

동작(behavior)을 1바이트도 바꾸지 않으면서 순환 복잡도를 임계치(10) 아래로 낮추고, 분기·문장·인자수 위반을 제거한다. 분해 단위는 "한 가지 책임 = 한 헬퍼"이며, 호출부는 오케스트레이션만 남긴다.

## 2. 대상 1 — `api/tools/custom.py::execute_custom_query` (C901 17 → 목표 ≤10)

### 2.1 현재 책임 (한 함수에 응축)
바인드 검증 → 주석 제거 → SQL 검증 4종(세미콜론/SELECT only/금지 키워드/테이블 참조) → LIMIT 자동추가 → archive 판단 → RO 연결 + PRAGMA + ATTACH → daemon thread 실행 + 타임아웃 + interrupt → 결과 dict 빌드.

### 2.2 추출 헬퍼

| 헬퍼 | 시그니처 | 책임 | 제거 효과 |
|---|---|---|---|
| `_validate_custom_query_sql` | `(sql_clean: str, sql_upper: str) -> str \| None` | 검증 4종 수행, 위반 시 에러 **메시지 문자열** 반환, 통과 시 `None`. | 분기 ~7개 + 금지 키워드 2 루프 제거 |
| `_run_query_with_timeout` | `(conn, sql_clean: str, bound_params: tuple, timeout_sec: float) -> dict` | daemon thread 실행, join/timeout, interrupt, 성공·SQL오류 시 `conn.close()`, 타임아웃 시 GC 위임. 결과 `{"rows","columns","error","timed_out"}` 반환. | 문장 ~25개 + 타임아웃 분기 제거 |

### 2.3 호출부(잔여) 흐름
```
bound_params = _validate_custom_query_params(params)   # ValueError → INVALID_PARAMS dict
sql_clean = _strip_sql_comments(sql.strip()); sql_upper = sql_clean.upper()
err = _validate_custom_query_sql(sql_clean, sql_upper)  # err → {"status":"error","message":err}
if "LIMIT" not in sql_upper: sql_clean += " LIMIT 1000"
use_archive = "ARCHIVE.PRODUCTION_RECORDS" in sql_upper
with QueryLogger(...) as ql:
    conn 생성 + PRAGMA (+ archive attach: 실패 시 INVALID_ARCHIVE_PATH dict)
    result = _run_query_with_timeout(conn, sql_clean, bound_params, CUSTOM_QUERY_TIMEOUT_SEC)
    if result["timed_out"]: return QUERY_TIMEOUT dict
    if result["error"]: return error dict
    ql.set_row_count(...)
return success dict
```

### 2.4 보존 불변식
- **검증 순서·메시지 문자열** 동일(테스트가 메시지 부분문자열 검사).
- **lazy import** 유지: `DB_FILE/DB_TIMEOUT/CUSTOM_QUERY_TIMEOUT_SEC/_apply_pragma_settings`는 호출부에서 함수 내 import(테스트 monkeypatch 호환). `sqlite3`/`threading`만 모듈 최상단으로 승격(stdlib, 부작용 없음, 헬퍼가 사용).
- `BLE001` noqa(sqlite3.Error 변환)와 daemon/GC 주석 유지.

## 3. 대상 2 — `api/routers/records.py::get_records` (C901 14 / PLR0913 10 → 목표 ≤10 / ≤5)

### 3.1 현재 책임
날짜 정규화/검증 → targets 결정 → WHERE 8조건 누적 → 커서 디코드/조건 → union SQL 빌드(커서/offset 분기 중복) → 결과 슬라이스 → next_cursor 인코딩.

### 3.2 추출 헬퍼

| 헬퍼 | 시그니처 | 책임 | 제거 효과 |
|---|---|---|---|
| `_build_records_filters` | `(f: RecordsFilters, date_from_n, date_to_n, cursor_data) -> tuple[list[str], list[Any]]` | item_code/q/lot/날짜/수량/커서 WHERE절 + params 누적. | 분기 ~8개 제거 (C901·PLR0912 핵심) |
| `RecordsFilters` (BaseModel) | 쿼리 파라미터 10종을 `Field`로 모델화 | PLR0913 해소 — 라우트 인자 10 → 1. | 인자수 위반 제거 |

### 3.3 라우트(잔여) 흐름 — union SQL 분기 통합
커서/offset 두 분기가 동일한 `build_union_sql` 호출을 중복하므로 단일화한다:
```
def get_records(filters: Annotated[RecordsFilters, Query()]):
    date_from_n = _normalize_date(filters.date_from)
    date_to_n   = _normalize_date(filters.date_to, add_days=1)
    _validate_date_range(date_from_n, date_to_n if not date_to_n else filters.date_to)
    targets = DBRouter.pick_targets(date_from_n, date_to_n)
    cursor_data = _decode_cursor(filters.cursor) if filters.cursor else None
    where, params = _build_records_filters(filters, date_from_n, date_to_n, cursor_data)
    where_clause = " AND ".join(where) if where else "1=1"
    with QueryLogger(...) as ql:
        sql, _ = DBRouter.build_union_sql(..., limit=filters.limit + 1, include_source=True)
        if not cursor_data and filters.offset > 0:
            logger.warning("[Deprecated] ... offset=...")
            sql += f" OFFSET {int(filters.offset)}"
        query_params = DBRouter.build_query_params(params, targets)
        all_results = DBRouter.query(sql, query_params, use_archive=targets.use_archive)
        has_more = len(all_results) > filters.limit
        results = all_results[:filters.limit]
        ql.set_row_count(len(results))
    next_cursor = _encode_cursor(...) if (has_more and results) else None
    return {...}
```
- **동등성 근거**: 원본 커서 분기는 offset을 추가하지 않았고(`if not cursor_data` 가드가 동일), offset 분기만 경고+OFFSET을 붙였다. 통합 흐름은 이 동작을 그대로 재현한다. WHERE/params 빌드는 양 분기가 이미 동일했다.

### 3.4 `RecordsFilters` 모델 (FastAPI 0.133 — `Annotated[Model, Query()]`)
각 필드는 기존 `Query(default=..., max_length/ge/le=..., description=...)`를 `Field(...)`로 1:1 이전. FastAPI 0.115+는 모델 필드를 개별 쿼리 파라미터로 평면화하므로 HTTP 계약·OpenAPI·검증(422)·기본값이 동일하게 유지된다.

### 3.5 보존 불변식
- `from __future__ import annotations` 유지(Annotated 호환). 커서 인코딩/디코딩, 정렬 순서, has_more/next_cursor 로직 동일.

## 4. 회귀 방지 — CI C901 게이트 확장

`.github/workflows/ci.yml`의 단일 파일 게이트를 대상 파일 목록으로 확장:
```yaml
- name: Complexity gate (C901-clean files)
  run: ruff check api/_chat_stream.py api/tools/custom.py api/routers/records.py --select C901
```

## 5. 테스트 설계 (신규 회귀)

| 테스트 | 대상 | 목적 |
|---|---|---|
| `_validate_custom_query_sql` 단위 4종 | custom.py | 검증 헬퍼가 위반 메시지/None을 정확히 반환 |
| `_build_records_filters` 단위 | records.py | 필터 조합별 WHERE절/params 개수·순서 |
| 기존 `test_routers_db.py`(11) / `test_sql_validation.py`(30+) | 양쪽 | 동작 보존 검증(주 회귀 안전망) |

## 6. 구현 순서

1. `custom.py`: 헬퍼 2개 추출 + 호출부 재구성 + import 승격.
2. `records.py`: `RecordsFilters` + `_build_records_filters` + 라우트 통합.
3. 신규 회귀 테스트 추가.
4. CI 게이트 확장.
5. Ruff + 전체 테스트 검증.
