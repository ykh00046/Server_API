# Production Data Hub - 운영 매뉴얼

> 대상: 시스템 운영자
> 기준 버전: v8 (2026-02-26)
> 프로젝트 경로: 프로젝트 루트 기준 (`Server_API`, 현재 워크스페이스 예: `/mnt/c/X/Server_API`)

---

## 목차

1. [서비스 구성](#1-서비스-구성)
2. [서버 시작 / 중지](#2-서버-시작--중지)
3. [상태 확인](#3-상태-확인)
4. [로그 관리](#4-로그-관리)
5. [DB 백업 / 복구](#5-db-백업--복구)
6. [DB Watcher 운영](#6-db-watcher-운영)
7. [장애 대응](#7-장애-대응)
8. [연말 Archive 전환 절차](#8-연말-archive-전환-절차)
9. [설정 변경](#9-설정-변경)
10. [정기 점검 체크리스트](#10-정기-점검-체크리스트)

---

## 1. 서비스 구성

```
[Manager GUI]  →  API Server (port 8000)
               →  Dashboard  (port 8502)
               →  DB Watcher (백그라운드)

[DB 파일]
  database/production_analysis.db   Live DB  (당해 연도)
  database/archive_2025.db          Archive  (2025 이하)
  database/backups/                 자동 백업 디렉토리

[로그]
  logs/app.log       API + Chat 로그  (최대 10MB × 5개)
  logs/watcher.log   Watcher 로그
```

### 포트 정보

| 서비스 | 기본 포트 | 환경변수 |
|--------|---------|---------|
| API Server | 8000 | `API_PORT` |
| Dashboard | 8502 | `DASHBOARD_PORT` |

---

## 2. 서버 시작 / 중지

### 방법 1: Manager GUI (권장)

```bash
# 프로젝트 루트에서
python manager.py
```

- GUI에서 API / Dashboard / Watcher 버튼으로 개별 제어
- 시스템 트레이에서 최소화 후 백그라운드 운영 가능

### 방법 2: 개별 터미널 실행

```bash
# 가상환경 활성화
.\.venv\Scripts\activate

# API 서버
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000

# Dashboard (별도 터미널)
python -m streamlit run dashboard/app.py --server.address 0.0.0.0 --server.port 8502

# DB Watcher 데몬 (별도 터미널)
python tools/watcher.py --daemon --interval 3600
```

### Windows 부팅 시 자동 시작 (선택)

작업 스케줄러에 등록하면 재부팅 후에도 서비스가 자동으로 시작됩니다.

```
작업 스케줄러 → 기본 작업 만들기
  트리거: 컴퓨터 시작 시
  동작: 프로그램 시작
    프로그램: [프로젝트 루트]\.venv\Scripts\python.exe
    인수:     manager.py
    시작 위치: [프로젝트 루트]
```

---

## 3. 상태 확인

### 빠른 헬스체크

```bash
# 서버 상태 (DB 연결, 캐시 현황, 디스크)
curl http://localhost:8000/healthz

# AI API 상태 (10분 캐시)
curl http://localhost:8000/healthz/ai
```

**정상 응답 예시**
```json
{
  "status": "ok",
  "database": "connected",
  "db_size_mb": 4.07,
  "archive_db": "available",
  "ai_api": { "key_configured": true, "cached_status": "ok" },
  "cache": { "size": 12, "maxsize": 200 },
  "disk_free_gb": 45.2
}
```

**주의 상황**
| `status` 값 | 의미 | 대응 |
|------------|------|------|
| `ok` | 정상 | — |
| `degraded` | DB 연결 불안정 | [7.1 DB 연결 오류](#71-db-연결-오류) 참고 |
| `disk_free_gb` < 5 | 디스크 부족 | 오래된 백업/로그 정리 |

---

## 4. 로그 관리

### 로그 파일 위치

| 파일 | 내용 | 보관 정책 |
|------|------|----------|
| `logs/app.log` | API 요청, AI Chat, Slow Query | 10MB × 5개 롤링 |
| `logs/watcher.log` | DB 변경 감지, 인덱스 복구, ANALYZE | 무제한 (수동 관리) |

### 유용한 로그 패턴

```bash
# 최근 에러 확인
grep "ERROR\|WARN" logs/app.log | tail -50

# Slow Query 확인 (500ms 초과)
grep "SLOW QUERY" logs/app.log

# AI 토큰 사용량 추이
grep "Token Usage" logs/app.log | tail -100

# 특정 제품 쿼리 추적
grep "BW0021" logs/app.log | tail -30

# ANALYZE 실행 이력
grep "ANALYZE" logs/watcher.log

# 인덱스 복구 이력
grep "Healed\|Creating missing" logs/watcher.log
```

### watcher.log 정기 정리 (수동)

```bash
# 30일 이상 된 로그 백업 후 초기화
copy logs\watcher.log logs\watcher.log.bak
echo. > logs\watcher.log
```

---

## 5. DB 백업 / 복구

### 자동 백업 정책

| DB | 보관 개수 | 파일명 패턴 |
|----|----------|-----------|
| Live (`production_analysis.db`) | 최근 30개 | `production_YYYYMMDD_HHMMSS.db` |
| Archive (`archive_2025.db`) | 최근 12개 | `archive_2025_YYYYMMDD_HHMMSS.db` |

백업 디렉토리: `database/backups/`

### 수동 백업 실행

```bash
# Live + Archive 전체 백업
python tools/backup_db.py

# Live만
python tools/backup_db.py --live

# Archive만
python tools/backup_db.py --archive

# 오래된 백업 정리만 (백업 없음)
python tools/backup_db.py --cleanup
```

### 백업 스케줄링 (Windows 작업 스케줄러)

```
기본 작업 만들기
  트리거: 매일 오전 2:00
  동작: 프로그램 시작
    프로그램: [프로젝트 루트]\.venv\Scripts\python.exe
    인수:     tools/backup_db.py
    시작 위치: [프로젝트 루트]
```

### DB 복구 절차

```bash
# 1. 서비스 중지 (Manager GUI에서)

# 2. 현재 DB 임시 보관
copy database\production_analysis.db database\production_analysis.db.broken

# 3. 복구할 백업 파일 확인
dir database\backups\production_*.db

# 4. 백업으로 복구
copy database\backups\production_20260225_020000.db database\production_analysis.db

# 5. DB 무결성 확인
python -c "
import sqlite3
conn = sqlite3.connect('database/production_analysis.db')
result = conn.execute('PRAGMA integrity_check').fetchone()
print('무결성:', result[0])
conn.close()
"

# 6. 서비스 재시작
```

---

## 6. DB Watcher 운영

Watcher는 DB 파일 변경을 감지하여 인덱스를 자동 복구하고,
24시간마다 `ANALYZE`를 실행하여 쿼리 플래너 통계를 갱신합니다.

### 상태 파일

```
database/.watcher_state.json
```

```json
{
  "live_mtime": 1740512400.0,
  "live_size": 4268032,
  "archive_mtime": 1740512000.0,
  "archive_size": 9424896,
  "last_analyze_ts": 1740512400.0
}
```

### 수동 실행 (단발)

```bash
# DB 상태 점검 + 인덱스 복구 + ANALYZE (필요 시)
python tools/watcher.py
```

### ANALYZE 강제 실행

`last_analyze_ts`를 0으로 초기화하면 다음 실행 시 강제로 ANALYZE됩니다.

```bash
python -c "
import json
with open('database/.watcher_state.json', 'r') as f:
    state = json.load(f)
state['last_analyze_ts'] = 0
with open('database/.watcher_state.json', 'w') as f:
    json.dump(state, f)
print('ANALYZE will run on next watcher cycle')
"
```

### 인덱스 수동 확인

```bash
python -c "
import sqlite3
conn = sqlite3.connect('database/production_analysis.db')
rows = conn.execute(\"PRAGMA index_list('production_records')\").fetchall()
for r in rows: print(r[1])
conn.close()
"
```

정상 출력:
```
idx_production_date
idx_item_code
idx_item_date
```

---

## 7. 장애 대응

### 7.1 DB 연결 오류

**증상**: `/healthz` 응답에 `"database": "error: ..."` 또는 API 500 오류

**체크리스트**
```bash
# 1. DB 파일 존재 확인
dir database\production_analysis.db

# 2. DB 잠금 확인 (ERP가 쓰는 중일 수 있음)
python -c "
import sqlite3
try:
    conn = sqlite3.connect('file:database/production_analysis.db?mode=ro', uri=True, timeout=3)
    conn.execute('SELECT 1')
    print('연결 OK')
    conn.close()
except Exception as e:
    print('연결 실패:', e)
"

# 3. WAL 파일 확인 (크기가 과도하면 체크포인트 필요)
dir database\production_analysis.db-wal
```

**WAL 체크포인트 강제 실행**
```bash
python -c "
import sqlite3
conn = sqlite3.connect('database/production_analysis.db')
conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
conn.close()
print('WAL checkpoint complete')
"
```

---

### 7.2 API 서버 응답 없음

**증상**: 브라우저/curl에서 연결 거부 또는 타임아웃

```bash
# 1. 프로세스 확인
tasklist | findstr python

# 2. 포트 점유 확인
netstat -ano | findstr :8000

# 3. 로그 끝부분 확인
type logs\app.log | more

# 4. 서버 재시작 (Manager GUI 또는 직접)
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```

---

### 7.3 AI Chat 오류

**증상**: Chat 응답에 `"status": "error"`

**원인별 대응**

| 에러 메시지 | 원인 | 대응 |
|------------|------|------|
| "API Key not configured" | `.env` 파일 없음 | `.env`에 `GEMINI_API_KEY` 추가 |
| "일일 한도 초과" | 무료 API 쿼터 소진 | 다음 날까지 대기 또는 유료 전환 |
| "AI 서비스 일시 불안정" | Gemini 서버 장애 | 재시도 (자동 3회 내장) |
| "Rate limit exceeded" | IP당 분당 20회 초과 | `Retry-After` 헤더 시간 대기 |

**API 키 확인**
```bash
python -c "
import os
from dotenv import load_dotenv
load_dotenv()
key = os.getenv('GEMINI_API_KEY', '')
print('키 설정됨:', bool(key))
print('키 앞 10자:', key[:10] + '...' if key else '없음')
"
```

---

### 7.4 Dashboard 로딩 느림

**증상**: 페이지 로딩에 5초 이상 소요

**체크리스트**
1. `GET /healthz`에서 `cache.size` 확인 — 0이면 캐시 미적재 상태
2. 첫 로딩은 캐시 워밍업이 필요하므로 정상
3. 이후에도 느리면 쿼리 로그 확인:

```bash
grep "SLOW QUERY" logs/app.log | tail -20
```

**캐시 강제 초기화** (이상 데이터가 캐시된 경우)

```bash
curl -X POST http://localhost:8000/cache/clear
# 또는 서버 재시작
```

---

### 7.5 인덱스 누락

**증상**: 특정 쿼리가 비정상적으로 느림 (SLOW QUERY 로그 급증)

```bash
# Watcher 단발 실행으로 인덱스 자동 복구
python tools/watcher.py

# 복구 확인
grep "Healed\|Creating missing" logs/watcher.log | tail -10
```

---

### 7.6 디스크 공간 부족

**증상**: `/healthz`에서 `disk_free_gb` 5 미만

```bash
# 1. 현재 디스크 사용 확인
dir /s database\backups\ | findstr "파일"

# 2. 오래된 백업 정리 (정책 기준 초과분만 삭제)
python tools/backup_db.py --cleanup

# 3. 로그 정리
# logs/app.log.1 ~ app.log.5 는 롤링 파일, 필요 시 삭제 가능
del logs\app.log.5

# 4. WAL/SHM 파일 정리 (서비스 중지 후)
del database\production_analysis.db-wal
del database\production_analysis.db-shm
```

---

## 8. 연말 Archive 전환 절차

매년 12월 말 ~ 1월 초에 수행합니다.
**예시: 2026년 → 2027년 전환**

### 사전 확인 (12월 중)

```bash
# 현재 Live DB 레코드 수 확인
python -c "
import sqlite3
conn = sqlite3.connect('database/production_analysis.db')
count = conn.execute('SELECT COUNT(*) FROM production_records').fetchone()[0]
min_d = conn.execute('SELECT MIN(production_date) FROM production_records').fetchone()[0]
max_d = conn.execute('SELECT MAX(production_date) FROM production_records').fetchone()[0]
print(f'레코드: {count:,}건 | 기간: {min_d} ~ {max_d}')
conn.close()
"
```

### 전환 절차

#### Step 1. 서비스 중지
Manager GUI에서 API / Dashboard 중지

#### Step 2. 현재 DB 백업 (전환 전 최종 백업)

```bash
python tools/backup_db.py
```

#### Step 3. 신규 Archive DB 생성

```bash
# 기존 archive를 이전 연도로 이름 변경
rename database\archive_2025.db archive_2025_old.db

# 현재 Live DB를 새 Archive로 복사
python -c "
import sqlite3
src = sqlite3.connect('database/production_analysis.db')
dst = sqlite3.connect('database/archive_2026.db')
src.backup(dst)
src.close(); dst.close()
print('archive_2026.db 생성 완료')
"
```

#### Step 4. 신규 Live DB 생성

```bash
python -c "
import sqlite3
conn = sqlite3.connect('database/production_analysis.db')
conn.execute('''
    CREATE TABLE IF NOT EXISTS production_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        production_date TEXT NOT NULL,
        lot_number TEXT,
        item_code TEXT NOT NULL,
        item_name TEXT,
        good_quantity REAL DEFAULT 0
    )
''')
conn.commit()
conn.close()
print('신규 Live DB 생성 완료')
"
```

#### Step 5. `shared/config.py` 수정

```python
# 변경 전
ARCHIVE_CUTOFF_YEAR = 2026

# 변경 후
ARCHIVE_CUTOFF_YEAR = 2027
```

#### Step 6. `tools/backup_db.py` 파일명 수정

```python
# 변경 전
if run_backup(ARCHIVE_DB_FILE, "archive_2025", ARCHIVE_BACKUP_RETENTION):

# 변경 후
if run_backup(ARCHIVE_DB_FILE, "archive_2026", ARCHIVE_BACKUP_RETENTION):
```

#### Step 7. `ARCHIVE_DB_FILE` 경로 확인 및 수정

```python
# shared/config.py
# 변경 전
ARCHIVE_DB_FILE = DATABASE_DIR / "archive_2025.db"

# 변경 후
ARCHIVE_DB_FILE = DATABASE_DIR / "archive_2026.db"
```

#### Step 8. 인덱스 생성 및 검증

```bash
# Archive DB 인덱스 생성
python tools/watcher.py

# 무결성 확인
python -c "
import sqlite3
for db in ['database/production_analysis.db', 'database/archive_2026.db']:
    conn = sqlite3.connect(db)
    r = conn.execute('PRAGMA integrity_check').fetchone()[0]
    count = conn.execute('SELECT COUNT(*) FROM production_records').fetchone()[0]
    print(f'{db}: {r}, {count:,}건')
    conn.close()
"
```

#### Step 9. 서비스 재시작 및 검증

```bash
# 서비스 재시작 후
curl http://localhost:8000/healthz
curl "http://localhost:8000/summary/monthly_total?date_from=2026-01-01&date_to=2026-12-31"
curl "http://localhost:8000/summary/monthly_total?date_from=2027-01-01&date_to=2027-01-31"
```

#### Step 10. 기존 Archive 보관 또는 삭제

```bash
# 장기 보관이 필요한 경우 별도 저장소로 이동
# 필요 없으면 삭제
del database\archive_2025_old.db
```

### 전환 체크리스트

```
□ 전환 전 Live DB 백업 완료
□ archive_2026.db 생성 및 무결성 확인
□ 신규 Live DB 생성 완료
□ shared/config.py ARCHIVE_CUTOFF_YEAR = 2027 변경
□ shared/config.py ARCHIVE_DB_FILE 경로 변경
□ tools/backup_db.py 파일명 패턴 변경
□ 인덱스 3개 생성 확인 (watcher.py 실행)
□ /healthz 정상 확인
□ Archive 데이터 조회 정상 확인
□ Live 데이터 조회 정상 확인
```

---

## 9. 설정 변경

### 포트 변경

`.env` 파일 수정 후 서비스 재시작:

```env
API_PORT=8001
DASHBOARD_PORT=8503
```

### Slow Query 임계값 변경

`shared/config.py`:
```python
SLOW_QUERY_THRESHOLD_MS = 500  # 기본 500ms, 낮출수록 더 많이 기록
```

### 캐시 TTL / 크기 변경

`shared/cache.py`:
```python
_api_cache = TTLCache(maxsize=200, ttl=300)  # TTL: 초 단위
```

### Rate Limit 변경

`shared/config.py`:
```python
RATE_LIMIT_CHAT = 20   # Chat 분당 요청 수
RATE_LIMIT_API = 60    # 일반 API 분당 요청 수
```

### Watcher 실행 간격 변경

```bash
# 30분 간격으로 변경
python tools/watcher.py --daemon --interval 1800
```

---

## 10. 정기 점검 체크리스트

### 매일

```
□ /healthz 응답 확인 (status: ok)
□ disk_free_gb 5GB 이상 확인
□ logs/app.log 에러 없는지 확인
    grep "ERROR" logs/app.log | tail -20
```

### 매주

```
□ SLOW QUERY 로그 확인 및 분석
    grep "SLOW QUERY" logs/app.log
□ AI 토큰 사용량 추이 확인
    grep "Token Usage" logs/app.log | tail -50
□ 백업 파일 생성 확인
    dir database\backups\ | tail -10
□ Watcher ANALYZE 실행 확인
    grep "ANALYZE OK" logs/watcher.log | tail -5
```

### 매월

```
□ database/backups/ 용량 확인
□ logs/ 용량 확인 및 정리
□ DB 무결성 검사
    python -c "
    import sqlite3
    for db in ['database/production_analysis.db', 'database/archive_2025.db']:
        conn = sqlite3.connect(db)
        print(db, conn.execute('PRAGMA integrity_check').fetchone()[0])
        conn.close()
    "
□ 인덱스 상태 확인 (python tools/watcher.py)
```

### 연 1회 (12월)

```
□ Archive 전환 계획 수립 (§8 참고)
□ ARCHIVE_CUTOFF_YEAR 변경 예정일 확정
□ 백업 정책 검토 (보관 개수 적정성)
□ 요구사항 변화 반영 여부 검토
```

---

## 10. 테스트 / 스모크 벽시계 (security-followup-observability)

**측정일**: 2026-04-14
**환경**: Windows 11, pytest 로컬 실행 (API TestClient in-process)

| 항목 | 값 |
|---|---|
| `pytest tests/ -q` | **10.52s / 133 tests** (설계 목표 <30s ✅) |
| 10k `/healthz` 스모크 | 수동 — `python scripts/perf_smoke.py --n 10000` 로 측정 |
| 10k 스모크 RSS Δ 목표 | < 50 MB |

### 수동 10k 스모크 실행 방법

```bash
# Terminal 1: API 기동
python manager.py  # or: uvicorn api.main:app --port 8000 --workers 1

# Terminal 2: 스모크 실행
python scripts/perf_smoke.py --url http://localhost:8000 --path /healthz --n 10000
# 출력 예: {"elapsed_sec": 7.42, "rps": 1347.7, "rss_delta_mb": 3.1, "counts": {"2xx": 10000}}
```

`psutil` 미설치 시 `rss_delta_mb` 는 null 로 출력되며 나머지는 정상 동작한다.

### 주의

- 이 스모크는 CI 에 편입되지 않는다 (과도한 시간 소모 및 서버 기동 의존).
- 회귀 관측에 사용할 때만 리눅스 운영 환경과 수치 비교.
