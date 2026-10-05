# System Architecture & Operation Guide

## 1. 개요
본 문서는 `Production Data Hub` 시스템의 전체 아키텍처와 운영 지침을 기술합니다.

---

## 2. 시스템 구성

### 2.1 서버 구성
| 서버 | 포트 (기본) | env override | 역할 | 기술 스택 |
|------|-----------|--------------|------|-----------|
| API Server | 8000 | `API_PORT` | REST API, webhook, 이상탐지, 자재/바인더 데이터셋 | FastAPI |

> SoT: `shared/config.py:API_PORT` (operations_manual.md와 통일).
> 화면은 Dashboard-Raw_material(8503)이 서빙한다 — 자체 Streamlit 대시보드(8502)·Gemini 챗 API는 2026-10 폐지됨.

### 2.2 데이터베이스
| DB | 파일 | 용도 |
|----|------|------|
| Live DB | `data/production.db` | 현재 연도 데이터 (2026~) |
| Archive DB | `data/archive.db` | 과거 데이터 (~2025) |

---

## 3. 아키텍처 다이어그램

```
┌──────────────────────────┐   HTTP    ┌─────────────────┐   ┌──────────────┐
│ Dashboard-Raw_material   │ ────────▶ │  API Server     │ ◀─│ Manager GUI  │
│ (별도 프로젝트, :8503)   │           │  (FastAPI)      │   │ (API/Portal) │
└──────────────────────────┘           │  :8000          │   └──────────────┘
                                       └────────┬────────┘
                                                │
                                                ▼
┌─────────────────────────────────────────┐
│           shared/database.py            │
│              (DBRouter)                 │
└────────────────┬────────────────────────┘
                 │
        ┌────────┴────────┐
        ▼                 ▼
   ┌─────────┐       ┌─────────┐
   │ Live DB │       │ Archive │
   │  .db    │       │   .db   │
   └─────────┘       └─────────┘
```

---

## 4. 분리 운영 설계 원칙

> 2026-10 이전에는 자체 Streamlit 대시보드가 `shared/DBRouter`로 DB에 직접 접근하고 채팅만 API를 호출하는
> "독립 접근" 구조였다. dashboard-8502-sunset으로 대시보드가 폐지되어 이 절의 분리 근거(장애 격리·독립 배포·직접 접근 성능)는
> 더 이상 적용되지 않는다. 현재는 **API 서버가 유일한 서버**이고, 화면(Dashboard-Raw_material)은 API를 경유해 조회한다.
> 이전 설계 근거는 git 이력(v1.6 이하)을 참조한다.

---

## 5. 운영 지침

### 5.1 서버 시작 순서
```bash
# API 서버 (운용 PC는 매니저가 기동)
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```

### 5.2 서버 의존성
화면(Dashboard-Raw_material)은 API 서버에 의존한다. API 중단 시 화면의 Server_API 연동 기능(상태·문서 조회·수동 실행)이 함께 멈춘다.

### 5.3 공통 모듈
`shared/` 디렉토리의 모듈은 API 서버·매니저·`tools/`에서 공유:
- `database.py`: DBRouter, 연결 관리, ATTACH helper (`attach_archive_safe`)
- `__init__.py`: 공통 상수 (DB 경로, 컷오프 날짜 등)
- `process_utils.py`: `kill_process_tree` — psutil 기반 프로세스 트리 종료 (manager.py / atexit 사용, 2026-04-24)
- `validators.py`: 날짜 파싱, LIKE escape, ARCHIVE_DB whitelist 검증
- `cache.py` / `metrics.py` / `rate_limiter.py` / `logging_config.py`: 운영 유틸

### 5.4 API 서버 보안 설계

#### 읽기 전용 아키텍처
생산 DB(Live/Archive)에 대해 API 서버는 **조회 기능만** 제공하며, 데이터 수정 기능이 없음:

| 구분 | 내용 |
|------|------|
| 엔드포인트 | 생산 데이터는 GET (조회) 전용. 쓰기 엔드포인트(자재/바인더 백업·삭제, webhook 관리)는 별도 DB(`materials.db`, notifications)만 다룸 |
| DB 연결 | `read_only=True` (SQLite `mode=ro`) |
| 쓰기 시도 시 | `sqlite3.OperationalError: attempt to write a readonly database` |

#### 데이터 조회량 제한 정책

| 사용처 | 기본값 | 최대값 | 전체 조회 |
|--------|--------|--------|-----------|
| API (`/records`) | 1,000건 | 5,000건 | ✅ 커서 페이지네이션 |

**API 사용자:**
- `limit` 파라미터로 최대 5,000건까지 조절 가능
- 커서 기반 페이지네이션으로 전체 데이터 순차 조회 가능
- 대량 데이터 처리에 적합

#### 효율적인 데이터 조회 패턴 (권장)

외부 프로젝트에서 API 사용 시 권장하는 조회 패턴:

**전략: 과거는 집계, 현재는 상세**
```
과거 데이터 (이전 월): GET /summary/monthly_total → 월별 집계
현재 데이터 (당월):    GET /records → 일자별 상세
```

**비교:**
| 방식 | 데이터량 (1년 기준) | 속도 |
|------|---------------------|------|
| 전체 일자별 조회 | ~5,000건+ | 느림 |
| 집계 + 현재월만 상세 | ~42건 | ✅ 빠름 |

**예시 코드:**
```python
import requests

API = "http://서버IP:8000"

# 과거: 월별 집계 (12건)
summary = requests.get(f"{API}/summary/monthly_total", params={
    "date_from": "2025-01-01",
    "date_to": "2025-12-31"
}).json()

# 현재월: 일자별 상세 (~30건)
records = requests.get(f"{API}/records", params={
    "date_from": "2026-01-01",
    "date_to": "2026-01-31"
}).json()["data"]
```

**효과:**
- 네트워크 전송량 대폭 감소
- API 응답 속도 향상
- 클라이언트 메모리 절약
- DB 부하 감소

---

## 6. 향후 고려사항

### 규모 확장 시 전환 검토
팀 규모가 커지거나 마이크로서비스 전환 시:
- (화면의 API 경유 통일은 2026-10 대시보드 폐지로 완료)
- API Gateway 도입으로 인증/로깅 중앙화
- 캐싱 레이어 추가 (Redis 등)

### 현재 구조 유지 조건
- 단일 서버 또는 소규모 배포
- DB 직접 접근의 성능 이점이 중요한 경우
- 장애 격리가 유지보수 편의보다 우선인 경우

> AI 도구 확장 프로세스(챗 도구 구성·추가 기준·토큰 효율)는 Gemini 챗 API 폐지(2026-10)와 함께
> [`docs/archive/2026-10/dashboard-8502-sunset/ai_architecture.md`](../archive/2026-10/dashboard-8502-sunset/ai_architecture.md)로 보관했다.

---

## 7. 변경 이력

| 날짜 | 버전 | 변경 내용 |
|------|------|-----------|
| 2026-01-23 | 1.0 | 초기 문서 작성 |
| 2026-01-23 | 1.1 | API 서버 보안 설계 (읽기 전용 아키텍처, Text-to-SQL 안전성) 추가 |
| 2026-01-23 | 1.2 | AI 도구 확장 프로세스 (로그 기반 의사결정, 도구 추가 기준) 추가 |
| 2026-01-23 | 1.3 | 토큰 효율성 고려사항 (전용 도구 vs Text-to-SQL 트레이드오프) 추가 |
| 2026-01-23 | 1.4 | 데이터 조회량 제한 정책 (API vs AI 채팅 차이, 대량 데이터 처리) 추가 |
| 2026-01-23 | 1.5 | 효율적인 데이터 조회 패턴 (집계 + 상세 조합 전략) 추가 |
| 2026-04-23 | 1.6 | docs-sync 사이클 — Dashboard 포트 8501→8502 통일, AI 도구 5→7개(compare_periods, get_item_history 추가) 반영 |
| 2026-10-05 | 1.7 | dashboard-8502-sunset — 자체 Streamlit 대시보드·Gemini 챗 API 폐지 반영(구성표·다이어그램·운영 지침), AI 챗 관련 절 제거 |
