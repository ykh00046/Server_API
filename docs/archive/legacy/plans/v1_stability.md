# Production Data Hub - Phase 1 구현 계획서

## 1. 개요
본 문서는 **Production Data Hub (Phase 1)**의 안정성 강화 및 운영 효율화를 위한 상세 구현 계획을 기술합니다. 
기존 아키텍처(Streamlit + FastAPI + SQLite + Manager)를 유지하되, **데이터 정합성 보장**, **성능 최적화**, **운영 안전성**에 중점을 둡니다.

**핵심 제약 사항:**
- `production_analysis.db` 파일의 구조(Schema) 및 데이터는 변경하지 않음 (Read-only 정책).
- 공통 모듈 의존성을 최소화하여 파일별 독립 실행 가능성(배포 편의성) 유지.

---

## 2. 모듈별 상세 구현 계획

### 2.1. `app.py` (Streamlit Dashboard)

**목표:** 초기 로딩 속도 개선 및 데이터 파싱 예외 처리 강화.

#### [변경 1] 제품 목록 캐싱 도입 (성능 최적화)
- **현재:** 사이드바 필터 렌더링 시마다 `GROUP BY` 쿼리를 실행하여 제품 목록을 가져옴.
- **수정:** `@st.cache_data`를 적용하여 DB 부하를 줄이고 UI 반응 속도 향상.

```python
@st.cache_data(ttl=60)
def load_item_list():
    """
    제품 목록(item_code, item_name)을 로드하고 캐싱합니다.
    """
    with get_db_connection() as conn:
        return pd.read_sql("""
            SELECT item_code, MAX(item_name) AS item_name
            FROM production_records
            GROUP BY item_code
            ORDER BY item_code
        """, conn)
```

#### [변경 2] 데이터 정렬 안전성 확보
- **분석:** 현재 날짜 포맷이 문자열이고 시간이 동일한 경우가 많아 `production_date` 정렬만으로는 순서가 불안정할 수 있음.
- **수정:** `ORDER BY id DESC`를 명시적으로 포함하여 데이터 삽입 순서(최신순)를 보장.

```python
# load_records 함수 내부 SQL
sql = """
    SELECT ...
    FROM production_records
    ...
    ORDER BY production_date DESC, id DESC LIMIT ?
"""
```

#### [변경 3] 데이터 품질 방어 로직 유지
- `_parse_production_dt` 함수 유지: '오전/오후' 등 비표준 한글 날짜 문자열 파싱 로직 필수.
- 파싱 실패 건수(`bad_dt`) 집계 및 `st.warning` 표시 기능 유지.

---

### 2.2. `api.py` (FastAPI Server)

**목표:** Read-Only 연결 보장 및 비표준 데이터 환경에서의 쿼리 안전성 확보.

#### [변경 1] DB Read-Only 연결 강제 (안정성)
- **분석:** API는 조회 전용이므로 실수로 인한 데이터 변조(Lock, Write)를 원천 차단해야 함.
- **수정:** SQLite 연결 시 `uri=True` 옵션과 `mode=ro` 파라미터 사용.

```python
def get_db_connection():
    # URI 모드를 활성화하여 읽기 전용으로 연결
    # file: 경로 앞에 'file:' 접두어와 절대경로 처리 필요
    db_uri = f"file:{DB_FILE}?mode=ro"
    return sqlite3.connect(db_uri, uri=True)
```

#### [변경 2] 날짜 필터링 로직 확정 (현실적 타협)
- **전제:** DB의 `production_date`는 `YYYY-MM-DD ...` 형식으로 시작됨이 확인됨 (Prefix 일치).
- **정책:** 복잡한 파싱이나 변환 없이 SQL 문자열 비교(`>=`, `<`)를 사용하여 **일(Day) 단위 필터링** 수행. 이는 인덱스 활용(추후 추가 시)에도 유리함.

```python
# 코드 유지 (검증 완료)
if date_from_n:
    where.append("production_date >= ?") # 문자열 비교로 일 단위 필터링 안전
if date_to_n:
    where.append("production_date < ?")  # 다음날 00:00 기준 미만
```

#### [변경 3] 월별 집계 안전성 (Safe Grouping)
- **정책:** `strftime` 대신 `substr`을 사용하여 비표준(한글 포함) 날짜 문자열에서도 안전하게 `YYYY-MM` 키를 추출.

```python
# 코드 유지
sql = """
SELECT substr(production_date, 1, 7) AS year_month, ...
GROUP BY year_month ...
"""
```

---

### 2.3. `manager.py` (Server Manager)

**목표:** 프로세스 종료 신뢰성 확보.

#### [변경 1] PID 기반 트리 종료 (Tree Kill)
- **분석:** `taskkill /IM python.exe` 등 이름 기반 종료는 다른 파이썬 프로세스에 영향을 주거나 정확하지 않음.
- **확인:** 현재 구현된 `_taskkill_tree` 함수가 `PID`를 기반으로 `/T` (Tree) 옵션을 사용하고 있으므로, 이를 유지하고 주석으로 중요성 명시.

```python
def _taskkill_tree(pid: int):
    """
    지정된 PID와 그 자식 프로세스들을 강제 종료합니다.
    Streamlit/Uvicorn이 생성한 하위 프로세스까지 확실히 정리하기 위함입니다.
    """
    subprocess.run(
        ["taskkill", "/F", "/T", "/PID", str(pid)],
        # ...
    )
```

---

## 3. 데이터베이스 (production_analysis.db)

**정책:**
- **Read-Only:** Phase 1 단계에서는 애플리케이션 레벨에서 스키마 변경(Index 추가 등)을 수행하지 않음.
- **향후 계획:** 성능 이슈 발생 시, `production_date` 및 `item_code`에 대한 인덱스 생성을 최우선으로 고려 (DBA 또는 유지보수 시점).

## 4. 파일 및 폴더 구조 (예상)

```text
C:\X\Server_v1\
├── docs\
│   └── implementation_plan_v1.md  <-- (본 문서)
├── .venv\
├── api.py           <-- (수정: Read-only 연결)
├── app.py           <-- (수정: Item List 캐싱, 정렬 기준 강화)
├── manager.py       <-- (유지: PID Kill 로직 확인)
├── production_analysis.db
└── README.md
```


---

## 5. 추가 보완 사항 (권장)

> 아래 항목은 **기능을 늘리기 위한 “웹 기능 추가”가 아니라**, Phase 1의 핵심 목표인 **정확성/안정성/운영성**을 높이기 위한 보완입니다.  
> 문서의 제약(스키마/데이터 변경 금지, 파일 독립 실행 우선)을 유지하면서도 “현장에서 잘 안 깨지게” 하는 방향만 담았습니다.

### 5.1 `production_date` 형식 가드레일(조용한 오염 방지)

현재 정책은 `production_date`가 `YYYY-MM-DD ...`로 **시작한다는 전제(Prefix 일치)** 위에 “일 단위” 필터를 안전하게 올려둔 구조입니다.  
이 전제가 깨지면 **API 결과가 조용히 틀릴 수 있으므로**, 시작 시점에 짧은 검증을 넣는 것을 권장합니다.

- **권장 동작**
  - 서버 시작 시 상위 N행(예: 200개)의 `production_date`를 샘플링
  - 정규식 `^\d{4}-\d{2}-\d{2}` 매칭 실패 비율이 일정 이상이면(예: 1%↑)
    - (A) 경고 로그 + `/healthz`에서 “degraded” 표시
    - (B) API에서 날짜 필터 사용 시 경고 메시지 반환 또는 날짜 필터 비활성화(정책 택1)
- **이유**
  - 포맷이 깨지면 잘못된 결과가 “에러 없이” 나오는 게 가장 위험합니다.

(선택) API 쪽에서 `date_from/date_to`가 들어오면 **Pandas 파싱 후 필터**로 폴백하는 방법도 있지만,
데이터가 커질수록 비용이 커지므로 Phase 1 기본값은 “가드레일 + 경고”를 추천합니다.

---

### 5.2 SQLite 락(locked) 대응: “읽기 전용이어도” 발생할 수 있음

Phase 1은 Read-only 정책이지만, DB 파일을 다른 프로세스가 갱신(쓰기)하는 순간에는
읽기 프로세스에서도 **`database is locked`**가 발생할 수 있습니다.

- **권장 동작**
  - SQLite 연결에 `timeout`(예: 5~10초) 설정(잠깐의 write lock은 기다렸다가 읽기)
  - Streamlit/FASTAPI 모두 “짧은 재시도(예: 2~3회)” 또는 사용자 메시지(잠시 후 재시도)를 표준화
- **운영 가이드(문서화 권장)**
  - DB 갱신 프로세스(쓰기)가 있다면 “갱신 시간대”를 정해 짧게 끝내거나, 야간/비업무 시간에 수행

> DB 자체 설정(WAL 모드 등)은 DB 파일 변경이 수반될 수 있어 Phase 1 제약에 걸릴 수 있습니다.  
> 따라서 **앱/서버 레벨에서 timeout + 재시도**로 현실적인 대응을 먼저 권장합니다.

---

### 5.3 API/대시보드 “기동 자기진단(Self-check)” 추가(초기 장애 감소)

운영 중 가장 흔한 장애는 “DB 경로/테이블/컬럼 바뀜”입니다.  
기동 시점에 아래를 확인하면 현장 장애를 크게 줄일 수 있습니다.

- DB 파일 존재 여부
- `production_records` 테이블 존재 여부
- 최소 컬럼 존재 여부: `production_date`, `item_code`, `item_name`, `good_quantity`, `lot_number`
- (선택) “깨진 View” 목록 확인(의존 테이블 누락 등) 후 **Phase 1에서 조회하지 않도록 명시**

API는 `/healthz`(또는 `/readyz`) 엔드포인트 하나만 추가해도
외부 시스템이 “살아있는지/DB 접근 가능한지”를 안정적으로 판단할 수 있습니다.

---

### 5.4 `manager.py` 운영성 보강(현장 친화)

현재 Manager는 PID 기반 종료로 신뢰성이 높습니다. 여기에 아래 2가지를 더하면 운영이 쉬워집니다.

- **포트 충돌 사전 체크**
  - 8501/8000이 이미 사용 중이면 “시작” 대신 경고 팝업(원인 파악 시간 절약)
- **접속 주소 안내 강화**
  - `localhost`뿐 아니라 “현재 PC의 로컬 IP”를 함께 표시(팀원이 접속해야 하는 상황 대비)

---

### 5.5 배포 재현성: `requirements.txt`(버전 고정) 권장

Phase 1에서 설치/업데이트 중 버전 차이로 깨지는 경우가 생각보다 많습니다.

- `requirements.txt`(또는 `requirements.lock`)를 두고, 검증된 버전 조합을 고정
- 문서에 “업데이트 시나리오”(예: 분기 1회 업데이트 + 롤백 방법)만 짧게라도 명시

---

### 5.6 성능이슈가 생겼을 때의 “DB 인덱스” 원칙 명시(Phase 2 연결)

문서에 이미 “성능 이슈 시 인덱스 고려”가 있으므로, 여기서는 원칙만 더 명확히 권장합니다.

- 가장 효과가 큰 후보(우선순위)
  1) `production_records(production_date)`
  2) `production_records(item_code)`
  3) (검색이 잦다면) `production_records(lot_number)`
- 단, Phase 1은 DB 변경 금지이므로 “DBA/유지보수 시점에 적용”이라는 문구를 유지합니다.

