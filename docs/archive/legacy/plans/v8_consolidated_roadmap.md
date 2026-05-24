# Production Data Hub - 통합 로드맵 v8

> 작성일: 2026-02-26
> 이전 버전: v6(개선 로드맵), v7(성능 개선 계획)
> 목적: v6+v7 항목 구현 현황 통합 정리 및 잔여 작업 정의

---

## 1. v6 + v7 구현 현황 전체 목록

### 1.1 ✅ 완료 항목

#### API 서버 (`api/`)

| 항목 | 출처 | 파일 | 완료 버전 |
|------|------|------|----------|
| GZip 응답 압축 | v7 §2.1 | `api/main.py:66` | v7 |
| ORJSONResponse (빠른 직렬화) | v7 §8.3 | `api/main.py:64` | v7 |
| API 결과 캐싱 (TTLCache + db_mtime 무효화) | v7 §2.4, §8.1 | `shared/cache.py` | v7 |
| IP 기반 Rate Limiting (슬라이딩 윈도우) | v6 §2.1 | `shared/rate_limiter.py` | v7 |
| Cursor 기반 Pagination (base64 JSON) | v7 §2.6, §8.5 | `api/main.py:188+` | v7 |
| SELECT 컬럼 최적화 | v7 §2.2 | `api/main.py:289+` | v7 |
| Slow Query 로깅 (임계값 기반) | v7 §2.5 | `shared/logging_config.py:177` | v7 |

#### AI Chat (`api/chat.py`, `api/tools.py`)

| 항목 | 출처 | 파일 | 완료 버전 |
|------|------|------|----------|
| Gemini API 재시도 (지수 백오프 + jitter) | v6 §2.1.1, §6.1 | `api/chat.py:245+` | v7 |
| google-genai 실제 예외 타입 기반 재시도 | v6 §6.1 | `api/chat.py:390` | v7 |
| 동적 날짜 (시스템 프롬프트) | v6 §2.2.2 | `api/chat.py:214` | v7 |
| 멀티턴 대화 (세션 관리 + TTL 만료 + LRU) | v6 §2.3.3, §6.7 | `api/chat.py:112+` | v7 |
| AI 도구: `compare_periods` (기간 비교) | v6 §2.3.1 | `api/tools.py:340+` | **v8** |
| AI 도구: `get_item_history` (품목 이력) | v6 §2.3.2 | `api/tools.py:430+` | **v8** |
| "근거 없는 답변 금지" 시스템 프롬프트 | v6 §6.6 | `api/chat.py:228+` | v7 |

#### DB / 공유 모듈 (`shared/`, `tools/`)

| 항목 | 출처 | 파일 | 완료 버전 |
|------|------|------|----------|
| 복합 인덱스 `idx_item_date` | v7 §2.3 | `shared/db_maintenance.py:36` | v7 |
| Thread-local 연결 캐싱 + mtime 재연결 | v7 §4.2, §8.2 | `shared/database.py:240+` | v7 |
| DB ANALYZE 주기 실행 (24시간) | v7 §4.1 | `shared/db_maintenance.py` + `tools/watcher.py` | **v8** |
| DB 백업 스크립트 (mtime 안정화 + quick_check) | v6 §2.1.2, §6.2 | `tools/backup_db.py` | v7 |
| Watcher 독립 실행 구조 (Manager UI 비의존) | v6 §6.3 | `tools/watcher.py` | v7 |
| `shared/db_maintenance.py` 공통 모듈 | v6 §P1 | `shared/db_maintenance.py` | v7 |
| `shared/validators.py` 입력 검증 | v6 §P1 | `shared/validators.py` | v7 |

#### Dashboard (`dashboard/app.py`)

| 항목 | 출처 | 파일 | 완료 버전 |
|------|------|------|----------|
| DBRouter 완전 통합 (중복 구현 제거) | v6 §2.2.1, §8.5 | `dashboard/app.py:20+` | v7 |
| 캐시 TTL 차등 적용 (300 / 60 / 180초) | v7 §3.2 | `dashboard/app.py:99,163,215` | v7 |
| SELECT * 제거 (컬럼 명시) | v7 §3.1 | `dashboard/app.py:168+` | v7 |
| 하드코딩 날짜 제거 (ARCHIVE_CUTOFF_DATE 사용) | v6 §2.2.2 | `dashboard/app.py:190` | v7 |
| db_mtime 기반 캐시 키 | v7 §8.1, §6.5 | `shared/cache.py` + `dashboard/app.py` | v7 |

#### 헬스체크 (`api/main.py`)

| 항목 | 출처 | 파일 | 완료 버전 |
|------|------|------|----------|
| `/healthz` AI 상태 캐시 경량화 | v6 §6.4 | `api/main.py:272` | v7 |
| 디스크 / DB 상태 통합 헬스체크 | v6 §2.1.3 | `api/main.py:212` | v7 |

---

### 1.2 ❌ 미완료 항목 (잔여 작업)

#### [A] 아키텍처 — Dashboard API 전환

| 항목 | 출처 | 현재 상태 | 우선순위 |
|------|------|----------|---------|
| Dashboard → API 전환 (DB 직접 쿼리 → API 호출) | v6 §2.4, v7 §3.3 | Dashboard가 여전히 DB 직접 쿼리 | 낮음 |
| API 장애 시 Graceful Degrade | v6 §6.6 | 미구현 | 낮음 |

> **보류 이유**: 현재 단일 서버 운영 환경에서 Dashboard→API 전환은 오히려 레이턴시가 증가할 수 있음. 다중 서버/분산 환경으로 확장 시 재검토.

#### [B] 운영 자동화

| 항목 | 출처 | 현재 상태 | 우선순위 |
|------|------|----------|---------|
| 연말 Archive 전환 자동화 (cutoff 자동 산출) | v6 §6.8, v7 §3.6 | `ARCHIVE_CUTOFF_YEAR` 수동 변경 필요 | 중간 |
| Worker 프로세스 확장 (uvicorn --workers) | v7 §2.7 | 단일 워커 운영 중 | 낮음 |

#### [C] 모니터링 / 알림

| 항목 | 출처 | 현재 상태 | 우선순위 |
|------|------|----------|---------|
| 모니터링 대시보드 (Streamlit 멀티페이지) | v6 §2.4.2 | 미구현 | 낮음 |
| 알림 시스템 (Slack Webhook / Email) | v6 §2.4.3 | 미구현 | 낮음 |

#### [D] 문서화

| 항목 | 출처 | 현재 상태 | 우선순위 |
|------|------|----------|---------|
| README.md 현행화 | v6 §2.2.3 | 구버전 내용 | 중간 |
| API 사용 가이드 (`docs/specs/api_guide.md`) | v6 §2.5.2 | 미작성 | 중간 |
| 운영 매뉴얼 (`docs/specs/operations_manual.md`) | v6 §2.5.3 | 미작성 | 중간 |

---

## 2. v8 기준 시스템 아키텍처

```
[ERP 시스템]
    │ DB 파일 갱신
    ▼
[database/]
 ├── production_analysis.db  (Live: 당해 연도)
 └── archive_2025.db         (Archive: 전년도 이하)
    │
    ├── [tools/watcher.py]  ─────────────────────────────────
    │    독립 실행 (Task Scheduler 권장)                      │
    │    · DB mtime 감시 → 인덱스 자동 복구                   │
    │    · 24시간마다 ANALYZE 실행 (쿼리 플래너 최적화)        │
    │    · state: .watcher_state.json                        │
    │                                                        │
    ├── [tools/backup_db.py]                                 │
    │    · mtime 안정화 확인 후 sqlite3.backup() API 사용     │
    │    · PRAGMA quick_check 검증                            │
    │    · 보관: Live 30개, Archive 12개                      │
    │                                                        │
    └── [shared/]  ──────────────────────────────────────────
         · database.py    : DBRouter, DBTargets, Thread-local 연결
         · cache.py       : TTLCache + db_mtime 무효화
         · rate_limiter.py: 슬라이딩 윈도우
         · validators.py  : 입력 검증
         · db_maintenance.py: 인덱스 복구, ANALYZE, 안정화 대기
         · logging_config.py: Slow Query 로깅

[api/]  ←──── shared/ 사용
 ├── main.py  : FastAPI REST (GZip + ORJSON + Rate Limit + Cursor Pagination + API Cache)
 ├── chat.py  : AI Chat (멀티턴 + 재시도 + Rate Limit)
 └── tools.py : AI 도구 7개
      · search_production_items  (품목 검색)
      · get_production_summary   (기간 통계)
      · get_monthly_trend        (월별 추이)
      · get_top_items            (상위 품목)
      · compare_periods          (기간 비교) ← v8 신규
      · get_item_history         (품목 이력) ← v8 신규
      · execute_custom_query     (커스텀 SQL)

[dashboard/app.py]  ←──── shared/ 사용
 · DBRouter 직접 연결 (읽기 전용)
 · TTL 차등 캐싱 (300 / 60 / 180초)
 · db_mtime 기반 캐시 키 자동 무효화

[manager.py]
 · GUI 서버 제어 (CustomTkinter + 시스템 트레이)
 · API / Dashboard / Watcher 프로세스 관리
```

---

## 3. 잔여 작업 로드맵

### 3.1 단기 권장 (문서화)

```
[ 문서화 ]
├── README.md 현행화
│    · 현재 프로젝트 구조 반영
│    · AI Chat, DBRouter, Archive 정책 설명
│    · API 엔드포인트 목록 갱신
│    └── 예상 작업: 1~2시간
│
├── docs/specs/api_guide.md
│    · 엔드포인트별 curl 예제
│    · AI 도구 7개 트리거 키워드
│    └── 예상 작업: 1~2시간
│
└── docs/specs/operations_manual.md
     · 서버 시작/중지 절차
     · 백업/복구 절차
     · 연말 Archive 전환 체크리스트
     └── 예상 작업: 1~2시간
```

### 3.2 중기 선택 (운영 자동화)

```
[ 연말 Archive 전환 자동화 ]
· shared/config.py: ARCHIVE_CUTOFF_YEAR → 자동 산출 로직
· 전환 체크리스트 자동 실행 스크립트
· 예상 작업: 2~3시간
```

### 3.3 장기 선택 (필요 시)

```
[ 모니터링 ]          [ 알림 ]              [ Dashboard API 전환 ]
Streamlit 멀티페이지  Slack Webhook         분산 환경 확장 시 재검토
API 호출 추이 차트    일일 요약 리포트       현재는 DB 직접 연결 유지
토큰 사용량 추이      에러 알림
```

---

## 4. 구현 완료율

| 카테고리 | 완료 | 전체 | 완료율 |
|----------|------|------|--------|
| API 서버 성능 | 7 | 7 | 100% |
| AI Chat / 도구 | 7 | 7 | 100% |
| DB / 공유 모듈 | 8 | 8 | 100% |
| Dashboard | 5 | 5 | 100% |
| 헬스체크 | 2 | 2 | 100% |
| 아키텍처 전환 | 0 | 2 | 0% (보류) |
| 운영 자동화 | 0 | 2 | 0% |
| 모니터링/알림 | 0 | 2 | 0% |
| 문서화 | 0 | 3 | 0% |
| **합계 (핵심)** | **29** | **29** | **100%** |
| **합계 (전체)** | **29** | **38** | **76%** |

> 핵심 기능(성능·안정성·AI) 전체 완료. 잔여 9개는 모두 선택적 개선 항목.

---

## 5. 버전 히스토리

| 버전 | 날짜 | 주요 내용 |
|------|------|----------|
| v1 | 2026-01 초 | 안정성 확보 (기본 구조) |
| v2 | 2026-01 | DB 최적화 (DBRouter, Archive 분리) |
| v3 | 2026-01 | 자동화 (Watcher, Backup) |
| v4 | 2026-01 | AI Chat (Gemini Tool Calling) |
| v5 | 2026-01 | 코드 리팩토링 (shared 모듈화) |
| v6 | 2026-01-23 | 개선 로드맵 (P0~P4 계획) |
| v7 | 2026-01-23 | 성능 개선 계획 (GZip, Cache, Pagination 등) |
| **v8** | **2026-02-26** | **v6+v7 통합 · AI 도구 2개 추가 · DB ANALYZE 자동화** |
