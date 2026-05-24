# Production Data Hub - 성능 개선 계획 (v7)

> 작성일: 2026-01-23
> 대상: API Server, Dashboard
> 기준: 현재 코드 분석 결과

---

## 1. 현재 상태 요약

### 1.1 API Server (`api/`)

| 파일 | 주요 기능 | 현재 방식 |
|------|----------|----------|
| `main.py` | REST 엔드포인트 | 동기 SQLite, 매 요청 연결 생성 |
| `chat.py` | AI 챗봇 | Gemini API + Tool Calling |
| `tools.py` | AI 도구 함수 | DBRouter 사용, 동기 쿼리 |

### 1.2 Dashboard (`dashboard/app.py`)

| 기능 | 현재 방식 |
|------|----------|
| DB 조회 | 직접 SQLite 쿼리 (`pd.read_sql`) |
| 캐싱 | `@st.cache_data(ttl=60)` 고정 |
| 차트 데이터 | 전체 조회 후 집계 |

---

## 2. API 성능 개선

### 2.1 응답 압축 (GZip Middleware)

**현재 코드** (`api/main.py:49`)
```python
app = FastAPI(title="Production Data Hub")
```

**개선안**
```python
from fastapi.middleware.gzip import GZipMiddleware

app = FastAPI(title="Production Data Hub")
app.add_middleware(GZipMiddleware, minimum_size=500)
```

**효과**
- JSON 응답 크기 60-80% 감소
- `/records` 대용량 응답에 효과적
- 구현 난이도: ★☆☆☆☆

---

### 2.2 SELECT 컬럼 최적화

**현재 코드** (`api/main.py:289`)
```python
select_columns = "id, production_date, lot_number, item_code, item_name, good_quantity"
```

**문제점**
- `id` 컬럼은 클라이언트에서 사용하지 않을 수 있음
- 일부 엔드포인트에서 불필요한 컬럼 포함

**개선안**
- 엔드포인트별 필요 컬럼만 선택
- 요약 API는 집계 컬럼만 반환

```python
# /records - 상세 조회용
select_columns = "production_date, lot_number, item_code, item_name, good_quantity"

# /summary - 집계용 (이미 최적화됨)
```

**효과**
- 네트워크 전송량 감소
- 메모리 사용량 감소
- 구현 난이도: ★☆☆☆☆

---

### 2.3 복합 인덱스 추가

**현재 인덱스** (`tools/watcher.py:51-54`)
```python
REQUIRED_INDEXES = {
    "idx_production_date": "... ON production_records(production_date)",
    "idx_item_code": "... ON production_records(item_code)",
}
```

**개선안** - 복합 인덱스 추가
```python
REQUIRED_INDEXES = {
    "idx_production_date": "... ON production_records(production_date)",
    "idx_item_code": "... ON production_records(item_code)",
    "idx_item_date": "... ON production_records(item_code, production_date)",  # NEW
}
```

**효과**
- `item_code + 기간` 조합 쿼리 성능 향상
- `/records/{item_code}`, `get_production_summary(item_code=...)` 등에 효과
- 구현 난이도: ★☆☆☆☆

---

### 2.4 API 결과 캐싱 (In-Memory LRU)

**현재 상태**
- 캐싱 없음, 동일 요청도 매번 DB 쿼리

**개선안** - `cachetools` 라이브러리 활용
```python
from cachetools import TTLCache
from hashlib import md5

# 캐시 설정
_cache = TTLCache(maxsize=100, ttl=300)  # 5분 TTL

def _cache_key(*args) -> str:
    return md5(str(args).encode()).hexdigest()

@app.get("/items")
def list_items(q: str | None = None, limit: int = 200):
    key = _cache_key("items", q, limit)
    if key in _cache:
        return _cache[key]

    # ... 쿼리 실행 ...

    _cache[key] = results
    return results
```

**적용 대상**
| 엔드포인트 | TTL | 이유 |
|-----------|-----|------|
| `/items` | 5분 | 제품 목록 변경 드묾 |
| `/summary/monthly_total` | 5분 | 집계 데이터 |
| `/records` | 1분 | 실시간성 필요 |

**효과**
- 동일 쿼리 응답 시간 ~1ms
- DB 부하 감소
- 구현 난이도: ★★☆☆☆

---

### 2.5 Slow Query 로깅

**현재 상태** (`shared/logging_config.py`)
- QueryLogger 존재하나 실행 시간 임계값 없음

**개선안**
```python
# shared/logging_config.py
SLOW_QUERY_THRESHOLD_MS = 500  # 500ms 이상 시 경고

class QueryLogger:
    def __exit__(self, *args):
        duration_ms = (time.perf_counter() - self.start_time) * 1000

        if duration_ms > SLOW_QUERY_THRESHOLD_MS:
            self.logger.warning(
                f"[SLOW QUERY] {self.endpoint} | {duration_ms:.1f}ms | rows={self.row_count}"
            )
```

**효과**
- 병목 쿼리 자동 감지
- 성능 모니터링 기반 확보
- 구현 난이도: ★☆☆☆☆

---

### 2.6 Cursor 기반 Pagination

**현재 코드** (`api/main.py:297-308`)
```python
limit=limit + offset,  # Fetch enough for offset
# ...
results = all_results[offset:offset + limit]  # Python에서 슬라이싱
```

**문제점**
- OFFSET이 클수록 성능 저하 (10000건 이후 급격히 느려짐)
- 전체 결과를 메모리에 로드 후 슬라이싱

**개선안** - Cursor 기반 (Keyset Pagination)
```python
@app.get("/records")
def get_records(
    # ... 기존 파라미터 ...
    cursor: str | None = Query(default=None, description="이전 응답의 next_cursor"),
):
    # cursor = "2026-01-20|live|12345" (production_date|source|id)
    if cursor:
        date_cursor, source_cursor, id_cursor = cursor.split("|")
        where.append("(production_date, source, id) < (?, ?, ?)")
        params.extend([date_cursor, source_cursor, id_cursor])

    # ... 쿼리 실행 ...

    # 다음 cursor 생성
    if results:
        last = results[-1]
        next_cursor = f"{last['production_date']}|{last['source']}|{last['id']}"

    return {"data": results, "next_cursor": next_cursor}
```

**효과**
- 일정한 쿼리 성능 (OFFSET 무관)
- 메모리 효율성 향상
- 구현 난이도: ★★★☆☆

---

### 2.7 Worker 프로세스 확장

**현재 실행** (`manager.py:430`)
```python
cmd = [PY, "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", str(API_PORT)]
```

**개선안** - 멀티 워커
```python
cmd = [
    PY, "-m", "uvicorn", "api.main:app",
    "--host", "0.0.0.0", "--port", str(API_PORT),
    "--workers", "2"  # CPU 코어 수에 따라 조정
]
```

**주의사항**
- Windows에서는 `--workers` 대신 별도 프로세스 관리 필요
- 또는 Gunicorn + Uvicorn 조합 사용 (Linux 권장)

**효과**
- 동시 요청 처리량 증가
- CPU 멀티코어 활용
- 구현 난이도: ★★☆☆☆

---

## 3. Dashboard 성능 개선

### 3.1 SELECT * 제거

**현재 코드** (`dashboard/app.py:110`)
```python
live_sql = f"SELECT * FROM production_records WHERE ..."
```

**개선안**
```python
columns = "production_date, item_code, item_name, good_quantity, lot_number"
live_sql = f"SELECT {columns} FROM production_records WHERE ..."
```

**효과**
- 불필요한 컬럼 전송 방지
- pandas DataFrame 메모리 감소
- 구현 난이도: ★☆☆☆☆

---

### 3.2 캐시 TTL 차등 적용

**현재 코드**
```python
@st.cache_data(ttl=60)  # 모든 함수 동일
def load_item_list(db_ver): ...

@st.cache_data(ttl=60)
def load_records(...): ...

@st.cache_data(ttl=60)
def load_monthly_summary(...): ...
```

**개선안**
```python
@st.cache_data(ttl=300)  # 5분 - 제품 목록 변경 드묾
def load_item_list(db_ver): ...

@st.cache_data(ttl=60)   # 1분 - 실시간성 필요
def load_records(...): ...

@st.cache_data(ttl=180)  # 3분 - 집계 데이터
def load_monthly_summary(...): ...
```

**효과**
- 불필요한 DB 쿼리 감소
- 데이터 특성에 맞는 캐싱
- 구현 난이도: ★☆☆☆☆

---

### 3.3 API 활용으로 로직 통합

**현재 구조**
```
Dashboard ──직접──> SQLite DB
API Server ─────> SQLite DB
```

**개선안**
```
Dashboard ──────> API Server ──────> SQLite DB
```

**변경 예시** (`dashboard/app.py`)
```python
# Before
@st.cache_data(ttl=60)
def load_monthly_summary(date_from, date_to, db_ver):
    # 직접 DB 쿼리 (50줄)
    ...

# After
@st.cache_data(ttl=180)
def load_monthly_summary(date_from, date_to, db_ver):
    params = {}
    if date_from: params["date_from"] = date_from.isoformat()
    if date_to: params["date_to"] = date_to.isoformat()

    resp = requests.get("http://localhost:8000/summary/monthly_total", params=params)
    return pd.DataFrame(resp.json())
```

**효과**
- 쿼리 로직 중복 제거
- API 캐싱 혜택 공유
- 유지보수 단순화
- 구현 난이도: ★★☆☆☆

---

### 3.4 차트 데이터 분리

**현재 코드** (`dashboard/app.py:206-210`)
```python
# Tab1: 상세 이력
df, bad_dt = load_records(...)  # 전체 데이터 로드
st.dataframe(df[["production_date", ...]])

# Tab2: 차트 (별도 함수)
summary_df = load_monthly_summary(...)
```

**문제점**
- Tab1 진입 시 대용량 데이터 로드
- Tab2만 볼 때도 Tab1 데이터 로드됨

**개선안** - Lazy Loading
```python
with tab1:
    if st.session_state.get("tab1_loaded", False) or "tab1" in st.session_state.get("active_tab", ""):
        df, bad_dt = load_records(...)
        st.dataframe(...)
    else:
        st.info("데이터를 로드하려면 '데이터 불러오기' 버튼을 클릭하세요")
        if st.button("데이터 불러오기"):
            st.session_state["tab1_loaded"] = True
            st.rerun()
```

**효과**
- 초기 로딩 시간 단축
- 메모리 사용 최적화
- 구현 난이도: ★★☆☆☆

---

### 3.5 DataFrame 청크 처리

**현재 코드**
```python
df = pd.read_sql(final_sql, conn, params=query_params)  # 전체 로드
```

**개선안** - 대용량 데이터 청크 처리
```python
# 50,000건 이상일 때 청크 처리
chunks = pd.read_sql(final_sql, conn, params=query_params, chunksize=10000)
df = pd.concat(chunks, ignore_index=True)
```

**효과**
- 메모리 스파이크 방지
- 대용량 데이터 안정적 처리
- 구현 난이도: ★★☆☆☆

---

## 4. 공통 개선

### 4.1 DB ANALYZE 정기 실행

**추가 위치**: `tools/watcher.py`

```python
def _run_analyze(self):
    """Update query planner statistics."""
    try:
        conn = sqlite3.connect(str(DB_FILE), timeout=DB_TIMEOUT)
        conn.execute("ANALYZE production_records")
        conn.close()
        self.log_queue.put(("INFO", "📊 ANALYZE completed"))
    except Exception as e:
        self.log_queue.put(("WARN", f"ANALYZE failed: {e}"))
```

**실행 주기**: 일 1회 (백업 후)

**효과**
- SQLite 쿼리 플래너 최적화
- 인덱스 선택 정확도 향상
- 구현 난이도: ★☆☆☆☆

---

### 4.2 연결 재사용 (Connection Caching)

**현재 코드** (`shared/database.py:118-140`)
```python
@staticmethod
def get_connection(use_archive: bool = False, read_only: bool = True):
    # 매번 새 연결 생성
    conn = sqlite3.connect(db_uri, uri=True, timeout=DB_TIMEOUT)
    ...
```

**개선안** - Thread-local 연결 캐싱
```python
import threading

_local = threading.local()

@staticmethod
def get_connection(use_archive: bool = False, read_only: bool = True):
    cache_key = f"conn_{use_archive}_{read_only}"

    # 기존 연결 재사용
    conn = getattr(_local, cache_key, None)
    if conn is not None:
        try:
            conn.execute("SELECT 1")  # 연결 유효성 확인
            return conn
        except sqlite3.Error:
            pass  # 연결 끊김, 새로 생성

    # 새 연결 생성
    conn = sqlite3.connect(db_uri, uri=True, timeout=DB_TIMEOUT)
    if use_archive and ARCHIVE_DB_FILE.exists():
        conn.execute(f"ATTACH DATABASE '{archive_path}' AS archive")

    setattr(_local, cache_key, conn)
    return conn
```

**효과**
- 연결 생성 오버헤드 제거
- 요청당 ~5-10ms 절약
- 구현 난이도: ★★☆☆☆

---

## 5. 구현 우선순위

| 순위 | 항목 | 파일 | 난이도 | 효과 | 예상 작업 |
|------|------|------|--------|------|----------|
| **1** | GZip 압축 | `api/main.py` | ★☆☆☆☆ | 중 | 2줄 추가 |
| **2** | SELECT 컬럼 최적화 | `dashboard/app.py` | ★☆☆☆☆ | 중 | 변수 수정 |
| **3** | 복합 인덱스 | `tools/watcher.py` | ★☆☆☆☆ | 높 | 1줄 추가 |
| **4** | 캐시 TTL 차등화 | `dashboard/app.py` | ★☆☆☆☆ | 중 | 숫자 수정 |
| **5** | Slow Query 로깅 | `shared/logging_config.py` | ★☆☆☆☆ | 낮 | 조건 추가 |
| **6** | API 결과 캐싱 | `api/main.py` | ★★☆☆☆ | 높 | 데코레이터 추가 |
| **7** | 연결 캐싱 | `shared/database.py` | ★★☆☆☆ | 중 | 함수 수정 |
| **8** | Dashboard API 전환 | `dashboard/app.py` | ★★☆☆☆ | 중 | 함수 재작성 |
| **9** | Cursor Pagination | `api/main.py` | ★★★☆☆ | 높 | 로직 변경 |
| **10** | DB ANALYZE | `tools/watcher.py` | ★☆☆☆☆ | 낮 | 함수 추가 |

---

## 6. 단계별 실행 계획

### Phase 1: Quick Wins (1-5번)
- 코드 변경 최소화
- 즉시 적용 가능
- 테스트 간단

### Phase 2: Core Optimization (6-8번)
- 캐싱 전략 구현
- 아키텍처 개선
- 통합 테스트 필요

### Phase 3: Advanced (9-10번)
- API 인터페이스 변경
- 클라이언트 수정 필요
- 충분한 테스트 기간 확보

---

## 7. 측정 지표

### 적용 전 측정 항목
```bash
# API 응답 시간
curl -w "%{time_total}" http://localhost:8000/records?limit=1000

# 응답 크기
curl -s http://localhost:8000/records?limit=1000 | wc -c
```

### 목표
| 지표 | 현재 (예상) | 목표 |
|------|------------|------|
| `/records` 응답 시간 | 500ms | 200ms |
| `/records` 응답 크기 | 1MB | 300KB (GZip) |
| Dashboard 초기 로딩 | 3초 | 1초 |
| 캐시 히트율 | 0% | 70%+ |

---

## 부록: 의존성 추가

```txt
# requirements.txt 추가
cachetools>=5.0.0  # API 캐싱용
```

---

## 8. 검토 결과 및 추가 보완 사항 (프로젝트 적합성 강화)

본 v7 성능 개선 계획은 **현재 구조(듀얼 DB + FastAPI/Streamlit + Watcher/Manager)**에 잘 맞습니다. 특히
- API 압축(GZip)
- Cursor 기반 페이지네이션
- Dashboard에서 SELECT * 제거 / TTL 차등화
- Thread-local 연결 캐싱  
같은 항목은 “작은 수정으로 큰 효과”에 해당합니다.

다만, **우리 프로젝트의 핵심 전제(ERP가 DB 파일을 갱신/교체할 수 있음, Archive/Live 라우팅, mtime 기반 캐시 무효화)**를 고려하면
아래 보완을 추가하는 편이 안정성과 성능을 동시에 올립니다.

### 8.1 (필수) 모든 캐시의 키에 `DB_VERSION(=mtime)`를 포함
API In-Memory 캐시(TTLCache) 도입 시, DB가 갱신되었는데 캐시가 그대로 남으면 사용자는 “DB는 바뀌었는데 결과가 안 바뀜”을 경험합니다.

**권장**
- API 캐시 키: `(endpoint, params..., db_mtime)` 형태로 구성
- Dashboard `@st.cache_data`: 이미 `db_ver`(mtime) 인자를 넣는 패턴을 유지/강화
- Watcher가 DB 변경을 감지하면 (선택) API 캐시를 비우는 “캐시 버전 증가” 파일을 갱신

> 결론: TTL만으로는 부족하고, **mtime(버전) 기반 무효화가 1순위**입니다.

### 8.2 (주의) “연결 재사용(커넥션 캐싱)”은 DB 파일 교체 시나리오와 함께 설계
Thread-local 연결 캐싱은 요청당 연결 생성 비용을 줄이는 장점이 있습니다.  
하지만 ERP가 DB를 **파일 단위로 교체(rename/overwrite)**하는 형태라면, 오래된 커넥션이 “옛 파일 핸들”을 계속 보고 있을 수 있습니다.

**권장 보완**
- 연결 캐시에 `conn_db_mtime`을 함께 저장
- 요청 시 현재 mtime과 다르면:
  1) 기존 conn.close()
  2) 새로 connect + (필요 시 ATTACH)
- “read-only URI”는 유지하되, `timeout`은 짧게 + 가벼운 재시도(1~2회)로 운영

### 8.3 (권장) FastAPI 응답 직렬화 최적화: ORJSONResponse 옵션
대용량 JSON에서 병목은 DB보다 “직렬화/전송”인 경우가 많습니다. GZip과 궁합도 좋습니다.

**권장**
- FastAPI 기본 응답을 `ORJSONResponse`로 변경(또는 `/records` 같은 대용량 엔드포인트에만 적용)
- 효과: CPU 사용량 감소 + 응답 지연 감소(특히 1,000~20,000건 조회 시)

### 8.4 (권장) `/records`는 “상한(최대 limit)”을 더 보수적으로
큰 limit은 직렬화 시간/네트워크 지연/Streamlit 렌더링 병목을 유발합니다.

**권장 정책**
- API: 기본 500~1000, 최대 5000 정도로 현실적인 상한(운영 중 조정)
- 대량 다운로드는 별도 엔드포인트(예: `/records/export`)로 “파일 생성/스트리밍” 분리(필요 시)

### 8.5 (권장) Cursor Pagination은 “정렬/커서 규격”을 명확히 고정
듀얼 DB(archive+live)에서 안정적으로 동작하려면 아래를 문서에 못 박는 게 좋습니다.

**권장 보완**
- 정렬 기준을 단일 고정: `ORDER BY production_date DESC, id DESC, source DESC` 등
- cursor는 파싱 안정성을 위해 base64(JSON) 권장
  - 예: `{"d":"2026-01-20 10:11:12","id":12345,"src":"live"}`
- “동일 production_date” 타이브레이커가 반드시 있어야 함(id 또는 rowid)

### 8.6 (권장) Dashboard “API 전환” 시, 장애 격리(Graceful Degrade) 포함
Dashboard → API 구조로 통합하면 중복 제거/성능 이점이 큽니다.  
다만 운영 중 API가 잠시 죽으면 Dashboard도 같이 멈추는 문제가 생길 수 있습니다.

**권장 보완**
- Dashboard에서 API 요청 실패 시:
  - 즉시 에러 메시지 + “재시도” 버튼
  - (선택) 로컬 DB 직접 조회 fallback(운영 정책에 따라)
- API 헬스체크(`/healthz`) 결과를 Dashboard 상단에 상태등으로 표시

### 8.7 (권장) SQLite 읽기 최적화 PRAGMA는 “연결 생성 직후”에만 제한 적용
SQLite 튜닝 PRAGMA(`cache_size`, `temp_store`)는 성능에 도움이 될 수 있으나,
ERP 쓰기 동작과 충돌하거나 메모리 사용량이 튈 수 있습니다.

**권장**
- API/Dashboard는 read-only 연결에서만 최소한으로 적용
- 먼저 v7의 Quick Wins(압축/컬럼/인덱스/TTL/slow-log) 적용 후,
  측정 지표가 부족할 때만 PRAGMA 튜닝을 Phase 3(Advanced)에 포함

### 8.8 (정리) v7에서 “지금 바로” 반영 Top 6 (우리 운영 조건 반영)
1) GZip + (가능하면) ORJSONResponse  
2) SELECT 컬럼 최적화(특히 Dashboard) + TTL 차등화  
3) 복합 인덱스 추가(Watcher REQUIRED_INDEXES에 포함)  
4) API In-Memory 캐시 도입 시 **db_mtime 기반 캐시 키 필수**  
5) 커넥션 캐싱은 **db_mtime 변화 시 재연결** 로직과 함께  
6) Cursor Pagination은 커서 규격/정렬 고정 + base64(JSON)로 안정화  


