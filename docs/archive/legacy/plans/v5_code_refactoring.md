# Production Data Hub - Phase 5: 코드 품질 개선 및 성능 최적화

## 1. 개요
본 계획은 기존 시스템의 **코드 품질, 유지보수성, 성능**을 개선하기 위한 리팩토링 계획입니다.

**핵심 원칙:**
- **중복 제거:** DB 연결/라우팅 로직을 단일 모듈로 통합하여 2025/2026 경계 버그 방지
- **추적 가능성:** 에러 핸들링 및 로깅 강화로 운영 중 문제 추적 용이하게
- **점진적 개선:** 복잡도 증가 없이 실질적인 효과가 큰 것부터 적용

---

## 2. 현재 문제점 분석

### 2.1 코드 중복
| 파일 | 중복 코드 | 위험성 |
|------|-----------|--------|
| `api/main.py:25` | `_get_conn()` | Archive 경계 조건 불일치 가능 |
| `api/tools.py:14` | `_get_conn()` | 동일 |
| `dashboard/app.py:31` | `get_db_connection()` | Read-only 모드 미적용 |

### 2.2 에러 핸들링 부재
```python
# api/chat.py:79-80 - 현재 코드
except Exception:
    pass  # AI tool 호출 추출 실패 시 무시 -> 환각 답변 추적 불가
```

### 2.3 하드코딩된 상수
- `"2026-01-01"` - Archive 경계 날짜가 여러 파일에 산재
- `8501`, `8000` - 포트 번호 하드코딩
- Archive 필요 여부 판단 시 `date_to` 미검토

### 2.4 Archive 검색 누락
- `search_production_items()`가 Live DB만 검색
- 단종 제품, 작년 생산 여부 질문에 정확한 답변 불가

---

## 3. 개선 계획

### Phase A: 즉시 적용 (가성비 최고)

#### A.1 공통 모듈 도입 (`shared/`)

**폴더 구조 변경:**
```text
C:\X\Server_v1\
├── shared\                    # [신규] 공통 모듈
│   ├── __init__.py
│   ├── config.py              # 상수/설정 통합
│   └── database.py            # DB 연결/라우팅 통합
├── api\
│   ├── main.py                # [수정] shared 모듈 사용
│   ├── chat.py                # [수정] 로깅 강화
│   └── tools.py               # [수정] shared 모듈 사용 + archive 옵션
├── dashboard\
│   └── app.py                 # [수정] shared 모듈 사용
└── ...
```

**`shared/config.py` 설계:**
```python
from pathlib import Path

# === Paths ===
BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_DIR = BASE_DIR / "database"
DB_FILE = DATABASE_DIR / "production_analysis.db"
ARCHIVE_DB_FILE = DATABASE_DIR / "archive_2025.db"

# === Archive 정책 ===
# 연도 기준 분리 정책: 이 연도 미만 데이터는 Archive DB에 있음
ARCHIVE_CUTOFF_YEAR = 2026
ARCHIVE_CUTOFF_DATE = f"{ARCHIVE_CUTOFF_YEAR}-01-01"

# === Server Ports ===
DASHBOARD_PORT = 8501
API_PORT = 8000

# === DB Connection ===
DB_TIMEOUT = 10.0
```

**`shared/database.py` 설계:**
```python
import sqlite3
import logging
from typing import Any
from .config import DB_FILE, ARCHIVE_DB_FILE, ARCHIVE_CUTOFF_DATE, DB_TIMEOUT

logger = logging.getLogger(__name__)

class DBRouter:
    """
    듀얼 DB(Live + Archive) 라우팅을 담당하는 클래스.
    모든 DB 접근은 이 클래스를 통해 수행한다.
    """

    @staticmethod
    def need_archive(date_from: str | None, date_to: str | None = None) -> bool:
        """
        Archive DB 접근 필요 여부 판단.

        주의: date_from만 보면 안 됨!
        예: 2025-12-15 ~ 2026-01-10 → 둘 다 필요
        """
        # 기간 미지정 시 전체 조회 → Archive 필요
        if date_from is None:
            return True

        # date_from이 cutoff 이전이면 Archive 필요
        if date_from < ARCHIVE_CUTOFF_DATE:
            return True

        # date_to가 지정되지 않았으면 date_from만으로 판단
        # (이미 위에서 처리됨)

        return False

    @staticmethod
    def get_connection(use_archive: bool = False, read_only: bool = True) -> sqlite3.Connection:
        """
        DB 연결 생성.

        Args:
            use_archive: Archive DB를 ATTACH할지 여부
            read_only: 읽기 전용 모드 (기본값 True)
        """
        mode = "ro" if read_only else "rw"
        db_uri = f"file:{DB_FILE.absolute()}?mode={mode}"

        conn = sqlite3.connect(db_uri, uri=True, timeout=DB_TIMEOUT)

        if use_archive and ARCHIVE_DB_FILE.exists():
            # ATTACH 시 경로 안전하게 처리
            archive_path = str(ARCHIVE_DB_FILE.absolute()).replace("'", "''")
            conn.execute(f"ATTACH DATABASE '{archive_path}' AS archive")
            logger.debug(f"Archive DB attached: {ARCHIVE_DB_FILE}")

        return conn

    @staticmethod
    def query(
        sql: str,
        params: list[Any] | tuple[Any, ...] = (),
        use_archive: bool = False
    ) -> list[dict]:
        """
        쿼리 실행 후 dict 리스트로 반환.
        """
        with DBRouter.get_connection(use_archive=use_archive) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(sql, params)
            rows = cur.fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def build_union_query(
        base_select: str,
        where_clause: str,
        order_by: str = "",
        limit_offset: str = "",
        need_archive: bool = False
    ) -> tuple[str, bool]:
        """
        Live/Archive UNION ALL 쿼리 빌더.

        Returns:
            (sql, params_doubled): SQL문과 파라미터 복제 필요 여부
        """
        live_sql = f"""
            {base_select}
            FROM production_records
            WHERE {where_clause} AND production_date >= '{ARCHIVE_CUTOFF_DATE}'
        """

        if need_archive and ARCHIVE_DB_FILE.exists():
            archive_sql = f"""
                {base_select}
                FROM archive.production_records
                WHERE {where_clause} AND production_date < '{ARCHIVE_CUTOFF_DATE}'
            """
            final_sql = f"{archive_sql} UNION ALL {live_sql}"
            params_doubled = True
        else:
            final_sql = live_sql
            params_doubled = False

        if order_by:
            final_sql += f" {order_by}"
        if limit_offset:
            final_sql += f" {limit_offset}"

        return final_sql, params_doubled
```

#### A.2 에러 핸들링 및 로깅 강화

**`api/chat.py` 수정:**
```python
import logging

# 모듈 레벨 로거 설정
logger = logging.getLogger(__name__)

@router.post("/", response_model=ChatResponse)
async def chat_with_data(request: ChatRequest):
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="Gemini API Key is not configured.")

    try:
        model = genai.GenerativeModel(
            model_name='gemini-flash-latest',
            tools=PRODUCTION_TOOLS,
            system_instruction=SYSTEM_INSTRUCTION
        )

        chat = model.start_chat(enable_automatic_function_calling=True)
        response = chat.send_message(request.query)

        # Tool 사용 추적 (로깅 포함)
        tools_used = []
        try:
            for part in response.candidates[0].content.parts:
                if hasattr(part, 'function_call') and part.function_call:
                    tool_name = part.function_call.name
                    tools_used.append(tool_name)
                    logger.info(f"[AI Tool Called] {tool_name}")
        except (IndexError, AttributeError) as e:
            # 구체적 예외 + 로깅
            logger.warning(f"[AI Tool Extract] Failed to extract tool info: {e}")

        # Tool 미사용 시 경고 로그 (환각 가능성)
        if not tools_used:
            logger.warning(f"[AI Response] No tools used for query: {request.query[:50]}...")

        return ChatResponse(
            answer=response.text,
            tools_used=tools_used
        )

    except Exception as e:
        logger.exception(f"[Chat Error] Query: {request.query[:50]}...")
        return ChatResponse(
            answer=f"죄송합니다. 질문을 처리하는 중에 오류가 발생했습니다: {str(e)}",
            status="error"
        )
```

#### A.3 Archive 검색 옵션 추가

**`api/tools.py` 수정:**
```python
def search_production_items(
    keyword: str,
    include_archive: bool = False
) -> Dict[str, Any]:
    """
    사용자가 말한 제품명이나 키워드와 유사한 실제 제품 코드(item_code)를 찾습니다.

    Args:
        keyword: 검색 키워드
        include_archive: True면 단종 제품(Archive DB)도 검색
    """
    try:
        base_sql = """
            SELECT item_code, MAX(item_name) as item_name, COUNT(*) as record_count
            FROM production_records
            WHERE item_code LIKE ? OR item_name LIKE ?
            GROUP BY item_code
        """

        like_keyword = f"%{keyword}%"
        params = [like_keyword, like_keyword]

        if include_archive and ARCHIVE_DB_FILE.exists():
            # Archive + Live 통합 검색
            archive_sql = base_sql.replace("production_records", "archive.production_records")

            union_sql = f"""
                SELECT item_code, item_name, SUM(record_count) as record_count
                FROM (
                    {archive_sql}
                    UNION ALL
                    {base_sql}
                )
                GROUP BY item_code
                ORDER BY record_count DESC LIMIT 10
            """
            query_params = params + params  # 파라미터 복제

            with _get_conn(use_archive=True) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(union_sql, query_params).fetchall()
        else:
            sql = base_sql + " ORDER BY record_count DESC LIMIT 10"
            with _get_conn(use_archive=False) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(sql, params).fetchall()

        items = [dict(r) for r in rows]

        return {
            "status": "success",
            "search_keyword": keyword,
            "include_archive": include_archive,
            "found_items": items,
            "message": f"'{keyword}'와 유사한 제품 {len(items)}개를 찾았습니다." +
                       (" (단종 제품 포함)" if include_archive else "")
        }
    except Exception as e:
        logger.exception(f"[Tool Error] search_production_items failed: {keyword}")
        return {"status": "error", "message": str(e)}
```

**SYSTEM_INSTRUCTION 업데이트:**
```python
SYSTEM_INSTRUCTION = """
...
[데이터 조회 규칙]
1. 사용자가 제품 이름이나 키워드로 물어보면, 반드시 `search_production_items` 도구를 먼저 사용해.
2. "작년", "2025년", "단종", "예전" 같은 표현이 있으면 include_archive=True로 검색해.
3. 제품 코드를 확인한 후에만 `get_production_summary`를 사용해.
...
"""
```

#### A.4 Cursor 기반 페이지네이션 (복합 커서)

**현재 문제:**
- `OFFSET` 기반은 대용량에서 느림
- Archive + Live UNION 시 id가 겹칠 수 있음

**복합 커서 설계:**
```python
# 커서 구조: (production_date, id, source)
# source: 'live' 또는 'archive'

@app.get("/records")
def get_records(
    # ... 기존 파라미터 ...
    cursor: str | None = Query(default=None, description="마지막 조회 위치 (base64 인코딩)"),
    limit: int = Query(default=1000, ge=1, le=20000),
):
    """
    Cursor 기반 페이지네이션.

    cursor 형식: base64(json({"date": "2025-12-31", "id": 12345, "source": "archive"}))
    """
    if cursor:
        cursor_data = json.loads(base64.b64decode(cursor))
        last_date = cursor_data["date"]
        last_id = cursor_data["id"]
        last_source = cursor_data["source"]

        # 복합 조건: (date, id) 기준 다음 레코드
        # 같은 날짜면 id로 tie-break
        where.append("""
            (production_date < ? OR
             (production_date = ? AND id < ?))
        """)
        params.extend([last_date, last_date, last_id])
```

**주의사항:**
- 정렬 기준을 `production_date DESC, id DESC`로 고정
- 응답에 `next_cursor` 포함하여 다음 페이지 요청 가능하게

---

### Phase B: 데이터 증가 대비 (효과 큼)

#### B.1 UNION 후 집계 최적화

**현재 (비효율적):**
```sql
SELECT year_month, SUM(good_quantity)
FROM (
    SELECT ... FROM archive.production_records WHERE ...
    UNION ALL
    SELECT ... FROM production_records WHERE ...
)
GROUP BY year_month
```

**개선 (각 DB 선집계 후 병합):**
```sql
SELECT year_month, SUM(total) as total_production
FROM (
    -- Archive에서 먼저 집계
    SELECT substr(production_date,1,7) as year_month, SUM(good_quantity) as total
    FROM archive.production_records
    WHERE ...
    GROUP BY year_month

    UNION ALL

    -- Live에서 먼저 집계
    SELECT substr(production_date,1,7) as year_month, SUM(good_quantity) as total
    FROM production_records
    WHERE ...
    GROUP BY year_month
)
GROUP BY year_month
ORDER BY year_month
```

**효과:**
- 각 DB에서 인덱스 활용한 집계 가능
- UNION되는 행 수 대폭 감소 (전체 레코드 → 월별 요약)

#### B.2 복합 인덱스 추가

**현재 인덱스:**
- `idx_production_date`
- `idx_item_code`

**추가 권장 인덱스:**
```sql
-- 날짜 범위 + 제품 코드 동시 필터링용
CREATE INDEX idx_date_item ON production_records(production_date, item_code);

-- 제품별 기간 조회용 (순서 중요)
CREATE INDEX idx_item_date ON production_records(item_code, production_date);
```

**적용 시점:**
- 실제 쿼리 패턴 모니터링 후 적용
- `EXPLAIN QUERY PLAN`으로 인덱스 사용 여부 확인

---

### Phase C: 미래 대비 (필요 시 적용)

#### C.1 Connection Pooling

**현재 판단: 비추천**

SQLite 파일 DB에서 풀링 시 문제:
- DB 파일 교체/갱신 시 풀의 오래된 커넥션이 문제
- `read-only URI` / `ATTACH` / `check_same_thread` 옵션 조합 복잡

**권장 방식:**
- 요청당 연결 생성 + timeout + 짧은 재시도
- PostgreSQL 등으로 마이그레이션 시 풀링 도입

#### C.2 Async/aiosqlite

**현재 판단: 기대효과 과대평가 주의**

- SQLite는 파일 락/단일 writer 특성
- 트래픽 낮은 현재 단계에서는 복잡도만 증가

**적용 조건:**
- 동시 접속 50+ 이상
- API 응답 시간이 병목으로 확인될 때

#### C.3 Redis 캐싱

**현재 판단: DB mtime 키 방식으로 충분**

**현재 충분한 캐싱 전략:**
```python
# Streamlit 캐시 (이미 적용됨)
@st.cache_data(ttl=60)
def load_records(..., db_ver: float):
    ...

# FastAPI 인메모리 캐시 (권장)
from functools import lru_cache

@lru_cache(maxsize=100)
def get_monthly_summary_cached(year_month: str, db_mtime: float):
    ...
```

**Redis 적용 조건:**
- uvicorn 멀티 워커 운영 시
- 프로세스 간 캐시 공유 필요 시

---

## 4. 실행 순서 및 체크리스트

### Step 1: 공통 모듈 도입
- [ ] `shared/__init__.py` 생성
- [ ] `shared/config.py` 작성
- [ ] `shared/database.py` 작성
- [ ] 단위 테스트 작성

### Step 2: 기존 코드 마이그레이션
- [ ] `api/main.py` → shared 모듈 사용
- [ ] `api/tools.py` → shared 모듈 사용 + archive 옵션
- [ ] `api/chat.py` → 로깅 강화
- [ ] `dashboard/app.py` → shared 모듈 사용
- [ ] 통합 테스트

### Step 3: 페이지네이션 개선
- [ ] 복합 커서 설계 확정
- [ ] `/records` 엔드포인트 수정
- [ ] 대시보드 무한 스크롤 적용 (선택)

### Step 4: 쿼리 최적화
- [ ] 월별 요약 쿼리 "선집계 후 병합" 방식 적용
- [ ] `EXPLAIN QUERY PLAN` 분석
- [ ] 필요 시 복합 인덱스 추가

---

## 5. 롤백 계획

각 단계별 문제 발생 시:
1. **shared 모듈 문제:** 기존 파일의 `_get_conn()` 복원
2. **로깅 문제:** 로깅 레벨 조정 또는 핸들러 비활성화
3. **쿼리 최적화 문제:** 기존 UNION ALL 방식으로 복원

**테스트 환경:**
- 변경 전 DB 백업 필수
- 개발 환경에서 충분한 테스트 후 운영 적용

---

## 6. 검토 결과 및 추가 보완 사항 (프로젝트 적합성 강화)

본 Phase 5 계획은 “듀얼 DB(Archive+Live) + FastAPI/Streamlit + AI Chat” 구조에서 **가장 효과가 큰 개선(중복 제거/추적성/쿼리 안정화)**을 우선 배치했다는 점에서 방향이 매우 적합합니다. 다만, 아래 항목을 보완하면 **경계(2025/2026) 정확도**와 **운영 안정성**이 더 확실해집니다.

### 6.1 DB 라우팅 정책: `need_archive()` → “필요 DB 집합” 반환으로 확장
현재 설계는 `need_archive(date_from, date_to)`를 두고 있으나, 구현 예시는 사실상 `date_from` 중심 판단이라 “기간이 경계를 걸칠 때”를 완전히 일반화하진 못합니다.

**권장 변경**
- `need_archive()` 단일 bool 대신, 다음처럼 “어떤 DB가 필요한지”를 명시적으로 반환하는 함수로 확장합니다.

예시:
```python
from dataclasses import dataclass

@dataclass(frozen=True)
class DBTargets:
    use_archive: bool
    use_live: bool

def pick_targets(date_from: str | None, date_to: str | None) -> DBTargets:
    # 기간 미지정: 둘 다 가능성 -> 둘 다 조회(정책)
    if date_from is None and date_to is None:
        return DBTargets(use_archive=True, use_live=True)

    # date_to만 있는 경우도 고려
    if date_from is None:
        return DBTargets(use_archive=True, use_live=(date_to >= ARCHIVE_CUTOFF_DATE))

    if date_to is None:
        # from만 있을 때: cutoff 이전이면 archive+live 둘 다 가능
        return DBTargets(use_archive=(date_from < ARCHIVE_CUTOFF_DATE), use_live=True)

    # 둘 다 있을 때: 기간이 cutoff를 “가로지르는지”로 판단
    return DBTargets(
        use_archive=(date_from < ARCHIVE_CUTOFF_DATE),
        use_live=(date_to >= ARCHIVE_CUTOFF_DATE),
    )
```

**효과**
- “아카이브만”, “라이브만”, “둘 다”가 명확해져서 이후 UNION/집계/검색/페이지네이션 로직이 단순해집니다.

### 6.2 `build_union_query()` 개선: SQL 문자열 주입 최소화 + “source 컬럼” 추가
현재 빌더는 cutoff를 문자열로 직접 삽입하고, (필요 시) 파라미터를 두 번 복제하는 구조입니다. 또한 archive/live UNION 결과를 후속 로직에서 구분하기가 어렵습니다.

**권장 변경**
1) cutoff는 가능하면 파라미터로 처리 (일관성/테스트 용이성)
2) UNION 결과에 `source`(archive/live) 컬럼을 포함해 **정렬/커서/디버깅**이 가능하게 합니다.

예시(컨셉):
```sql
SELECT 'archive' AS source, ...
FROM archive.production_records
WHERE ... AND production_date < ?
UNION ALL
SELECT 'live' AS source, ...
FROM production_records
WHERE ... AND production_date >= ?
ORDER BY production_date DESC, source DESC, id DESC
```

**효과**
- 복합 커서 설계(6.3)에서 source를 안정적으로 활용 가능
- “이 레코드가 어디 DB에서 왔는지”를 로그/디버깅에서 즉시 확인 가능

### 6.3 Cursor 기반 페이지네이션: (date, source, id)로 완전 고정
문서의 커서 구조 제안은 방향이 좋습니다. 다만 실제 WHERE 절은 `(date,id)`만으로 next page를 계산하는 예시가 포함되어 있어, archive/live가 섞일 때 경계에서 흔들릴 수 있습니다.

**권장 고정**
- 정렬을 `production_date DESC, source DESC, id DESC`로 고정
- 커서 조건도 동일한 키 순서로 구성

예시(컨셉):
```sql
WHERE
  (production_date < :d)
  OR (production_date = :d AND source < :s)
  OR (production_date = :d AND source = :s AND id < :id)
ORDER BY production_date DESC, source DESC, id DESC
LIMIT :limit
```

### 6.4 “비표준 날짜 문자열(오전/오후)” 환경에서의 안전장치(정책 확정)
Phase 1에서 `_parse_production_dt` 유지가 중요했던 만큼, Phase 5에서도 아래 정책을 문서에 명시해두면 좋습니다.

- **SQL 필터는 Day 단위**로만 수행
- 월별 집계 키는 `substr(production_date, 1, 7)` 사용(비표준 문자열 대응)
- API 입력 `date_from/date_to`는 normalize 후 `YYYY-MM-DD`로 강제

### 6.5 “Archive 포함 검색”의 기본값 정책을 명확히
`search_production_items(include_archive)`는 아주 좋은 추가입니다. 운영적으로는 아래 중 하나를 권장합니다.

- 기본값 `include_archive=True`
- 또는 질문에 “작년/2025/예전/단종”이 들어갈 때만 True

둘 중 무엇이든 좋지만, **한 번 정하면 바꾸지 않는** 것이 UX 일관성에 도움이 됩니다.

### 6.6 운영 안정성: 로그 파일 롤링 + 장애 원인 추적용 최소 필드
로깅 강화(A.2)는 매우 적합합니다. 추가로 아래만 더하면 “현장에서 원인 찾기”가 쉬워집니다.

- RotatingFileHandler로 로그 파일 크기/기간 제한
- 공통 로그 필드(최소): `request_id`, `db_targets(archive/live)`, `sql_kind(records/summary/search)`, `duration_ms`, `row_count`

### 6.7 테스트 최소 세트(권장)
대규모 테스트까지는 필요 없고, “경계 버그/퇴행”만 잡는 최소 세트면 충분합니다.

- `pick_targets()` 경계 테스트(2025-12-31, 2026-01-01, 기간 미지정)
- archive/live UNION 결과 정렬 안정성(동일 날짜에서 source/id tie-break)
- `search_production_items(include_archive=True)`가 live-only 대비 결과가 확장되는지
- 월별 요약 쿼리(선집계 후 병합) 결과가 기존 방식과 동일한지(샘플 데이터 기준)

---

### 6.8 (정리) Phase 5에서 “지금 바로” 반영 권장 Top 3
1) 라우팅을 bool → `DBTargets(use_archive, use_live)`로 확장 (경계 정확도)
2) UNION 결과에 `source` 컬럼 추가 + 정렬/커서 키에 포함 (페이지네이션 안정성)
3) 로그 파일 롤링 + 최소 공통 필드 (운영 추적성)


