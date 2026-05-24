# Production Data Hub - Phase 6: 개선 로드맵

## 1. 현재 시스템 분석

### 1.1 프로젝트 구조
```
Server_v1/
├── api/
│   ├── main.py          # FastAPI 엔드포인트 (REST API)
│   ├── chat.py          # AI Chat 엔드포인트 (Gemini)
│   └── tools.py         # AI 도구 함수 4개
├── dashboard/
│   └── app.py           # Streamlit 대시보드
├── shared/
│   ├── __init__.py      # 모듈 exports
│   ├── config.py        # 설정 상수
│   ├── database.py      # DBRouter, DBTargets
│   └── logging_config.py # 로깅 설정
├── database/
│   ├── production_analysis.db  # Live DB (2026~)
│   └── archive_2025.db         # Archive DB (~2025)
├── tools/
│   ├── create_index.py  # 인덱스 생성 유틸
│   └── check_models.py  # 모델 확인 유틸
├── docs/
│   ├── specs/           # 현행 스펙 문서
│   └── plans/           # 구현 계획 이력
├── logs/                # 로그 파일
├── manager.py           # GUI 서버 관리자 (CustomTkinter)
├── requirements.txt     # 의존성
└── .env                 # 환경 변수 (GEMINI_API_KEY)
```

### 1.2 현재 기능 현황

| 컴포넌트 | 기능 | 상태 |
|----------|------|------|
| **REST API** | /records, /items, /summary/* | ✅ 완료 |
| **AI Chat** | 4개 도구 (search, summary, trend, top) | ✅ 완료 |
| **Dashboard** | 상세 이력, 실적 추이, AI 분석 탭 | ✅ 완료 |
| **Manager** | GUI 서버 제어, DB Watcher | ✅ 완료 |
| **DB Router** | Archive/Live 자동 라우팅 | ✅ 완료 |
| **로깅** | 요청 추적, 쿼리 로깅, 토큰 사용량 | ✅ 완료 |

### 1.3 발견된 개선 필요 영역

#### 코드 품질
| 파일 | 이슈 | 심각도 |
|------|------|--------|
| `dashboard/app.py:32-36` | `get_db_connection()`이 shared.DBRouter 미사용 | 중간 |
| `dashboard/app.py:105-111` | Archive 경계 날짜 하드코딩 (`'2026-01-01'`) | 중간 |
| `api/chat.py:82` | 시스템 프롬프트 날짜 하드코딩 (수동 갱신 필요) | 낮음 |
| `README.md` | 현재 구조와 불일치 (구버전 내용) | 낮음 |

#### 안정성
| 이슈 | 설명 | 영향 |
|------|------|------|
| Rate Limit 미처리 | Gemini 429 에러 시 재시도 로직 없음 | AI Chat 실패 |
| 백업 미구현 | DB 백업 자동화 없음 | 데이터 손실 위험 |
| 헬스체크 불완전 | AI API 상태 미확인 | 장애 감지 지연 |

#### 기능 확장
| 영역 | 부재 기능 |
|------|----------|
| AI Chat | 기간 비교(`compare_periods`), 멀티턴 대화 |
| Dashboard | 실시간 갱신, 다크모드 |
| API | 인증, 버전 관리, 압축 |

---

## 2. 개선 계획 상세

### 2.1 [P0] 즉시 필요 - 안정성 확보

#### 2.1.1 Gemini API Rate Limit 자동 재시도
**파일:** `api/chat.py`

**현재 문제:**
```python
# chat.py:192-205 - 429 에러 시 즉시 실패 반환
except Exception as e:
    return ChatResponse(
        answer=f"죄송합니다. 질문을 처리하는 중에 오류가 발생했습니다: {str(e)}",
        status="error"
    )
```

**개선 방안:**
```python
import asyncio
from google.api_core.exceptions import ResourceExhausted

MAX_RETRIES = 3
BASE_DELAY = 2.0  # seconds

async def chat_with_data(request: ChatRequest):
    for attempt in range(MAX_RETRIES):
        try:
            response = client.models.generate_content(...)
            return ChatResponse(answer=response.text, ...)
        except ResourceExhausted as e:
            if attempt < MAX_RETRIES - 1:
                delay = BASE_DELAY * (2 ** attempt)  # Exponential backoff
                logger.warning(f"Rate limited. Retry {attempt+1}/{MAX_RETRIES} in {delay}s")
                await asyncio.sleep(delay)
            else:
                raise
```

**예상 효과:** 무료 API 환경에서 안정성 대폭 향상

---

#### 2.1.2 DB 백업 자동화
**신규 파일:** `tools/backup_db.py`

**구현 내용:**
```python
# 일일 백업 스크립트
# - production_analysis.db → backups/production_YYYYMMDD.db
# - archive_2025.db → backups/archive_2025_YYYYMMDD.db (주 1회)
# - 30일 이상 된 백업 자동 삭제
```

**Manager 연동:**
- `manager.py`에 백업 버튼 추가
- 또는 Windows Task Scheduler 연동 가이드 제공

---

#### 2.1.3 헬스체크 강화
**파일:** `api/main.py`

**현재:**
```python
# main.py:77-92
def health_check():
    # DB 연결만 확인
    conn.execute("SELECT 1")
```

**개선:**
```python
@app.get("/healthz")
def health_check():
    status = {
        "status": "ok",
        "database": check_db_connection(),
        "archive_db": check_archive_exists(),
        "ai_api": check_gemini_api(),  # 신규
        "disk_space": check_disk_space(),  # 신규
    }
```

---

### 2.2 [P1] 코드 품질 개선

#### 2.2.1 Dashboard DBRouter 통합
**파일:** `dashboard/app.py`

**현재 문제:**
```python
# app.py:32-36 - shared.DBRouter 미사용, 중복 구현
def get_db_connection(use_archive: bool = False):
    conn = sqlite3.connect(str(DB_FILE), timeout=10.0)
    if use_archive and ARCHIVE_DB_FILE.exists():
        conn.execute(f"ATTACH DATABASE '{str(ARCHIVE_DB_FILE)}' AS archive")
    return conn
```

**개선:**
```python
# shared 모듈 사용으로 통일
from shared import DBRouter, ARCHIVE_CUTOFF_DATE

def get_db_connection(use_archive: bool = False):
    return DBRouter.get_connection(use_archive=use_archive, read_only=True)
```

**효과:**
- Archive 경계 조건 불일치 버그 방지
- Read-only 모드 자동 적용

---

#### 2.2.2 하드코딩 제거
**파일:** `dashboard/app.py`, `api/chat.py`

**문제 위치:**
```python
# app.py:105, 109 - 날짜 하드코딩
live_sql = f"... AND production_date >= '2026-01-01'"
archive_sql = f"... AND production_date < '2026-01-01'"

# chat.py:82 - 오늘 날짜 하드코딩
SYSTEM_INSTRUCTION = """
...오늘 날짜는 2026년 1월 22일 목요일이야...
"""
```

**개선:**
```python
# app.py - shared.config 사용
from shared import ARCHIVE_CUTOFF_DATE
live_sql = f"... AND production_date >= '{ARCHIVE_CUTOFF_DATE}'"

# chat.py - 동적 날짜 생성
from datetime import date
today = date.today()
SYSTEM_INSTRUCTION = f"""
...오늘 날짜는 {today.strftime('%Y년 %m월 %d일')} {['월','화','수','목','금','토','일'][today.weekday()]}요일이야...
"""
```

---

#### 2.2.3 README.md 현행화
**파일:** `README.md`

현재 README는 Phase 1 기준으로 작성되어 있음. 업데이트 필요:
- 프로젝트 구조 (api/, dashboard/, shared/, docs/)
- 신규 기능 (AI Chat, DB Router, Archive 정책)
- API 엔드포인트 목록 갱신 (/chat 추가)
- 환경 변수 설정 (.env, GEMINI_API_KEY)

---

### 2.3 [P2] 기능 확장

#### 2.3.1 AI 도구 추가: `compare_periods`
**파일:** `api/tools.py`

**용도:** "이번 달 vs 저번 달", "올해 vs 작년" 비교 질문 처리

**인터페이스:**
```python
def compare_periods(
    period1_from: str,  # "2026-01-01"
    period1_to: str,    # "2026-01-31"
    period2_from: str,  # "2025-12-01"
    period2_to: str,    # "2025-12-31"
    item_code: Optional[str] = None
) -> Dict[str, Any]:
    """
    Compare production between two periods.
    Returns total, average, count for each period and difference percentage.
    """
```

**System Instruction 추가:**
```
9. "비교", "대비", "vs", "차이" 등의 표현이 있으면 `compare_periods`를 사용해.
```

---

#### 2.3.2 AI 도구 추가: `get_item_history`
**파일:** `api/tools.py`

**용도:** "BW0021 최근 생산 내역 10건" 처리

**인터페이스:**
```python
def get_item_history(
    item_code: str,
    limit: int = 10
) -> Dict[str, Any]:
    """
    Get recent production records for a specific item.
    Returns list of (date, lot_number, quantity).
    """
```

---

#### 2.3.3 멀티턴 대화 지원
**파일:** `api/chat.py`

**현재:** 각 요청이 독립적 (맥락 없음)

**개선 방안:**
```python
class ChatRequest(BaseModel):
    query: str
    session_id: Optional[str] = None  # 세션 식별자

# 메모리 기반 세션 저장 (간단 버전)
chat_sessions: Dict[str, List[Content]] = {}

async def chat_with_data(request: ChatRequest):
    history = chat_sessions.get(request.session_id, [])
    # history를 contents에 포함하여 맥락 유지
```

**주의:** 메모리 사용량 관리 필요 (세션 만료, 최대 턴 수 제한)

---

### 2.4 [P3] 운영 편의성

#### 2.4.1 로그 로테이션 개선
**현재:** `shared/logging_config.py`에 구현됨 (10MB, 5개 백업)

**추가 개선:**
- 일별 로테이션 옵션
- 오래된 로그 압축 (gzip)
- 로그 레벨별 분리 (error.log, access.log)

---

#### 2.4.2 모니터링 대시보드
**신규 파일:** `dashboard/pages/monitoring.py` (Streamlit 멀티페이지)

**표시 항목:**
- API 호출 횟수 (시간대별)
- AI 토큰 사용량 추이
- 에러율
- 응답 시간 분포

**데이터 소스:** `logs/app.log` 파싱 또는 별도 metrics 테이블

---

#### 2.4.3 알림 시스템
**신규 파일:** `shared/notification.py`

**기능:**
- 에러 발생 시 알림 (Slack Webhook 또는 Email)
- 일일 요약 리포트

**설정:** `.env`에 SLACK_WEBHOOK_URL 또는 SMTP 설정 추가

---

### 2.5 [P4] 문서화

#### 2.5.1 ai_architecture.md 업데이트
**파일:** `docs/specs/ai_architecture.md`

**추가 필요 내용:**
- 새 도구 2개 (get_monthly_trend, get_top_items) 명세
- google-genai 마이그레이션 반영
- 토큰 로깅 설명

#### 2.5.2 API 사용 가이드
**신규 파일:** `docs/specs/api_guide.md`

**내용:**
- 엔드포인트별 예제 (curl, Python)
- 에러 코드 설명
- Rate Limit 정책

#### 2.5.3 운영 매뉴얼
**신규 파일:** `docs/specs/operations_manual.md`

**내용:**
- 서버 시작/중지 절차
- 백업/복구 절차
- 장애 대응 체크리스트
- 연말 Archive 전환 절차

---

## 3. 우선순위 및 로드맵

### 3.1 우선순위 정의

| 등급 | 설명 | 기준 |
|------|------|------|
| **P0** | 즉시 필요 | 안정성/데이터 보호 |
| **P1** | 높음 | 코드 품질/버그 예방 |
| **P2** | 중간 | 기능 확장 |
| **P3** | 낮음 | 운영 편의성 |
| **P4** | 선택 | 문서화 |

### 3.2 구현 로드맵

```
[Week 1] P0 - 안정성 확보
├── Rate Limit 재시도 로직
├── 헬스체크 강화
└── DB 백업 스크립트

[Week 2] P1 - 코드 품질
├── Dashboard DBRouter 통합
├── 하드코딩 제거
└── README 현행화

[Week 3] P2 - 기능 확장
├── compare_periods 도구
├── get_item_history 도구
└── 멀티턴 대화 (선택)

[Week 4] P3/P4 - 운영/문서
├── 문서 업데이트
├── 모니터링 (선택)
└── 알림 시스템 (선택)
```

### 3.3 예상 작업량

| 항목 | 예상 작업량 | 영향 범위 |
|------|------------|----------|
| Rate Limit 재시도 | 소 | chat.py |
| DB 백업 스크립트 | 소 | 신규 파일 |
| 헬스체크 강화 | 소 | main.py |
| Dashboard DBRouter 통합 | 중 | app.py 전체 |
| 하드코딩 제거 | 소 | app.py, chat.py |
| compare_periods | 중 | tools.py, chat.py |
| get_item_history | 소 | tools.py, chat.py |
| 멀티턴 대화 | 대 | chat.py (구조 변경) |
| 문서 업데이트 | 중 | docs/ |

---

## 4. 리스크 및 고려사항

### 4.1 기술적 리스크

| 리스크 | 영향 | 대응 |
|--------|------|------|
| Gemini API 정책 변경 | AI Chat 중단 | 다른 모델 대체 준비 (OpenAI, Claude) |
| DB 파일 손상 | 데이터 손실 | 백업 자동화로 대응 |
| 메모리 누수 (멀티턴) | 서버 불안정 | 세션 만료 정책 필수 |

### 4.2 하위 호환성

- Dashboard의 DBRouter 통합 시 기존 동작 유지 확인 필요
- API 응답 구조 변경 시 버전 관리 고려

### 4.3 2026년 연말 준비

- 12월 전에 2027년 Archive 정책 검토
- `shared/config.py`의 `ARCHIVE_CUTOFF_YEAR` 갱신 절차 문서화

---

## 5. 결론

현재 시스템은 핵심 기능이 잘 구현되어 있으나, **안정성(P0)**과 **코드 일관성(P1)** 측면에서 개선이 필요합니다.

**즉시 실행 권장:**
1. Rate Limit 재시도 로직 (무료 API 안정성)
2. DB 백업 자동화 (데이터 보호)
3. Dashboard DBRouter 통합 (버그 예방)

**점진적 확장:**
- AI 도구 추가로 사용자 질문 커버리지 향상
- 운영 편의 기능은 필요에 따라 선택적 구현

---

## 6. 검토 결과 및 추가 보완 사항 (프로젝트 적합성 강화)

본 Phase 6 로드맵은 현재 시스템의 병목을 **P0(안정성) → P1(일관성/유지보수) → P2(질문 커버리지) → P3/P4(운영 편의/문서)**로 정리한 점에서, 우리 프로젝트 목표(“사람이 신경 안 써도 알아서 잘 돌아가게”)에 매우 적합합니다. 다만 아래 보완을 추가하면 **장애/데이터 손상/경계(Archive) 버그**가 더 확실히 줄어듭니다.

### 6.1 P0(안정성) 보강: “AI 재시도”는 `google-genai` 예외 타입 기준으로 설계
문서의 P0-RateLimit 재시도 방향은 정확합니다. 다만 `google-genai` SDK는 `google.api_core.exceptions.ResourceExhausted`가 아니라
`google.genai.errors.ClientError(4xx)` / `google.genai.errors.ServerError(5xx)`를 주로 던지는 케이스가 많아, 예외 타입을 실제 SDK에 맞추는 것이 안전합니다.

**권장(개념)**
- 429(RESOURCE_EXHAUSTED), 503/500(일시 장애)만 “재시도”
- 지수 백오프 + **jitter(난수 지연)** 추가
- 재시도 횟수/총 대기 시간 상한을 둠(예: 3회 / 총 10~15초)

추가로, 무료 티어 환경에서는 429가 “실제 쿼터/결제 설정 문제”로도 발생할 수 있어,
“지속 429(예: 1~2시간)”이면 재시도보다 **쿼터/키 상태 안내 메시지**로 분기하는 것이 운영에 유리합니다.

### 6.2 P0(데이터 보호) 보강: 백업은 “안전 복사”로(파일 교체/쓰기 중 보호)
ERP가 DB를 갱신하는 방식이 “파일에 직접 쓰기/교체”일 수 있어, 단순 `copyfile()`은 운 나쁘면 손상본을 백업할 수 있습니다.

**권장 정책**
- (A) DB 파일 `mtime`이 **N초 이상 변화 없을 때만** 백업(예: 10초)
- (B) 가능하면 `sqlite3` 백업 API 사용(열어서 `.backup()`), 불가하면 “일시적 재시도”
- (C) 백업 생성 후 `PRAGMA quick_check;` 같은 최소 검증 1회(선택)
- (D) 보관 정책: “일 1회 + 최근 30개”, Archive는 “주 1회 + 최근 12개” 등(문서 방향 유지)

### 6.3 P0(감지/복구) 보강: Watcher는 “Manager UI 의존”을 끊는 것을 권장
현재 구조가 “Manager가 켜져야 Watcher 동작”이라면, 운영 리스크가 큽니다(창 닫힘/재부팅).

**권장**
- Watcher(DB mtime 감시 + 인덱스 점검 + 캐시 키 갱신)는
  - (1) Windows Task Scheduler(부팅 시/5분 주기) 또는
  - (2) Windows 서비스(NSSM) 형태로 독립 실행
- Manager는 “상태 확인/수동 실행/로그 보기” 컨트롤 패널 역할로 축소

→ 이렇게 하면 “사람이 신경 안 써도” 목표와 정합성이 크게 올라갑니다.

### 6.4 헬스체크(`/healthz`) 보강: AI API 체크는 “가벼운 방식 + 캐시”로
`/healthz`에서 매 요청마다 실제 Gemini 호출을 하면:
- 토큰/쿼터 소모
- 장애 시 더 큰 부하
- 호출 지연으로 healthz 자체가 느려짐

**권장**
- `ai_api`는 “API 키 존재 여부 + (선택) 5~15분 캐시된 핑 결과”로 표기
- 실제 호출은 별도 `/healthz/ai` 또는 내부 스케줄러에서 주기적으로 1회만 수행

### 6.5 P1(일관성) 보강: Dashboard DBRouter 통합 시 “mtime 캐시 키”도 함께 통일
Dashboard에서 DBRouter를 쓰게 되면, 동시에 아래도 함께 표준화가 좋습니다.
- DB 캐시는 `DB_MTIME`을 키에 포함해 “DB가 바뀌면 자동 무효화”
- Archive cutoff는 `shared.config` 단일 소스

### 6.6 P2(AI 도구) 보강: “근거 없는 답변 금지” 정책을 시스템 레벨에서 고정
도구가 늘어나도 가장 중요한 운영 원칙은 **환각 차단**입니다.

**권장 정책**
- 모델 응답에서 tools 호출이 없거나, tool 결과가 비어 있으면:
  - “데이터 근거를 확보하지 못해 답변할 수 없습니다” + 필요한 조건/데이터 안내
- `data_basis`(기간/제품/집계/레코드 수)를 응답에 포함해 UI에서 “근거 박스”로 표시

### 6.7 멀티턴(선택) 보강: 메모리 기반은 TTL/LRU 또는 별도 DB 권장
문서의 주의사항처럼, 메모리 기반 세션은 누수/증가 위험이 있습니다.

**권장 2안**
- 간단: 세션 TTL(예: 30분) + 최대 턴 수 제한(예: 10턴) + LRU 제거
- 안정: `chat_history.db`(별도 SQLite)로 저장(생산 DB와 분리하여 lock 리스크 최소)

### 6.8 “연말 Archive 전환”을 자동화하는 운영 항목 추가(권장)
리스크 항목에 언급된 cutoff 갱신은 사람 실수 가능성이 큽니다.

**권장**
- `ARCHIVE_CUTOFF_DATE`는 연도 수동 갱신 대신,
  - `ARCHIVE_CUTOFF_YEAR`만 바꾸면 자동 계산되게 하거나
  - “올해=Live, 작년까지=Archive” 정책으로 자동 산출(운영정책 선택)
- 전환 작업 체크리스트(백업 → 신규 archive 생성/이관 → 인덱스 생성 → 헬스체크) 문서화(P4에 포함)

---

### 6.9 (정리) Phase 6에서 “지금 바로” 반영 Top 5
1) `google-genai` 실제 예외 타입 기반 429/5xx 재시도 + jitter
2) DB 백업을 “mtime 안정화 후” 수행(손상본 방지)
3) Watcher를 UI 의존에서 분리(스케줄러/서비스)
4) `/healthz`의 AI 체크는 캐시/경량화
5) Dashboard DBRouter 통합 시 mtime 캐시 키까지 통일


