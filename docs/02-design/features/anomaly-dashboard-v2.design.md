# anomaly-dashboard-v2 Design Document

> **Summary**: 발행 이력 영속화(anomaly.db) + 조회 API 2종 + what-if 미리보기 확장 + 대시보드 "이상탐지" 페이지.
>
> **Project**: Production Data Hub
> **Version**: v11
> **Author**: Claude / bkit:pdca
> **Date**: 2026-07-07
> **Status**: Draft
> **Plan**: `docs/01-plan/features/anomaly-dashboard-v2.plan.md`

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 탐지 결과를 관측할 UI가 없고, 발행 이력이 어디에도 영속화되지 않는다 |
| **CONSTRAINT** | 발행 경로 의미론 불변(성공분만 마킹, 실패는 재시도), POST /scan 서명 불변, unsafe_allow_html 신규 0 |
| **PATTERN** | notifications `_store_connection`(thread-local+WAL), dataset_page(httpx 페이지 클라이언트), `_parsing.py`(streamlit-free 순수 로직) |
| **GATE** | 전체 테스트 + ruff + C901 잠금 + 커버리지 floor 88 |

## 1. Overview

### 1.1 Design Goals

- 발행된 finding의 append-only 이력을 만들되, 기록 실패가 발행을 절대 방해하지 않는다.
- 대시보드 한 페이지에서 "지금 / 최근 30일 / 왜 안 왔나(쿨다운) / 임계치를 바꾸면(what-if)"에 답한다.
- what-if는 물리적으로 발행이 불가능한 경로(GET 전용 파라미터)로만 연다.

### 1.2 Design Principles

- v1의 계층 분리 유지: rules(순수) / detector(유일한 I/O 오케스트레이터) / store_*(영속화) / router(HTTP).
- 신규 저장소는 기존 관례 복제: 서브시스템별 SQLite 파일 분리, thread-local 커넥션, `reset_for_tests()` 훅.
- 대시보드는 기존 페이지 패턴 준수: httpx 클라이언트 + 에러 시 st.error(크래시 금지), 순수 변환은 `_parsing.py`.

## 2. Architecture

### 2.1 Component Diagram

```
                    ┌──────────────────────────────────────────┐
                    │ dashboard/views/anomaly.py (F4)          │
                    │  현재 스캔 │ 타임라인 │ 쿨다운 │ what-if │
                    └────┬─────────┬──────────┬─────────┬──────┘
              GET /scan  │         │          │         │ GET /scan?drop_pct=…
                         ▼         ▼          ▼         ▼
┌───────────────── api/routers/anomaly.py ─────────────────────┐
│ GET /scan(+overrides F5) │ POST /scan │ GET /rules            │
│ GET /findings (F2)       │ GET /state (F3)                    │
└──────┬───────────────────────┬──────────────────┬─────────────┘
       ▼                       ▼                  ▼
  detector.run_detection   store_findings     store_state
       │ emit 성공분          (F1, anomaly.db)   (.anomaly_state.json,
       ├──► notifications.emit_event            read-only 노출)
       └──► store_findings.record_findings (fire-and-forget)
```

### 2.2 Data Flow

1. (기존) anomaly_watch/POST scan → `run_detection(emit=True)` → `_emit_new` → 성공 발행분 `emitted`.
2. (신규 F1) `_emit_new`가 `store_findings.record_findings(emitted)` 호출 — try/except로 격리, 실패는 warning 로그만.
3. (신규 F2/F3) 대시보드가 `/anomaly/findings`, `/anomaly/state`를 폴링(60s 캐시).
4. (신규 F5) what-if 폼 → `GET /anomaly/scan?drop_pct=…` → `run_detection(emit=False, overrides=…)` — 상태·발행 무변경.

### 2.3 Dependencies

신규 외부 의존성 없음 (sqlite3/httpx/plotly/pandas 기존 사용분).

## 3. Data Model

### 3.1 신규 파일: `DATABASE_DIR/anomaly.db` — 테이블 `anomaly_findings`

```sql
CREATE TABLE IF NOT EXISTS anomaly_findings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT NOT NULL,            -- volume_drop | volume_spike | stale_item
    severity    TEXT NOT NULL,            -- info | warning | critical
    key         TEXT NOT NULL,            -- Finding.key (예: volume_drop:2026-07-06)
    message     TEXT NOT NULL,
    details     TEXT NOT NULL DEFAULT '{}',  -- JSON (Finding.details)
    event_type  TEXT NOT NULL,
    emitted_at  TEXT NOT NULL             -- ISO local, timespec='seconds'
);
CREATE INDEX IF NOT EXISTS idx_findings_emitted ON anomaly_findings(emitted_at);
CREATE INDEX IF NOT EXISTS idx_findings_kind    ON anomaly_findings(kind, emitted_at);
```

- append-only. UPDATE/DELETE는 보존 정리(F6)만.
- `key`는 유니크 아님 — 같은 이상이 쿨다운 만료 후 재발행되면 새 행(이력이므로 정상).

### 3.2 config 노브 (`shared/config.py`, anomaly 섹션)

```python
ANOMALY_DB_FILE = DATABASE_DIR / "anomaly.db"
ANOMALY_FINDINGS_RETENTION_DAYS = int(os.getenv("ANOMALY_FINDINGS_RETENTION_DAYS", 90))
```

### 3.3 신규 모듈: `api/anomaly/store_findings.py`

notifications `_store_connection` 패턴 경량 복제 (WAL + busy_timeout + thread-local + 스키마 lazy init):

| Function | Signature | Behavior |
|---|---|---|
| `record_findings` | `(findings: list[Finding], *, now_iso: str \| None = None) -> int` | executemany INSERT, 반환=기록 수. **예외를 밖으로 던지지 않음**(로그 후 0) — FR-6은 호출부가 아니라 여기서 1차 보장 |
| `list_findings` | `(*, days: int = 30, kind: str \| None, severity: str \| None, limit: int = 200) -> list[dict]` | emitted_at ≥ now-days, 내림차순, limit 클램프(1..500). details는 dict로 역직렬화 |
| `prune_findings` | `(*, retention_days: int \| None = None) -> int` | emitted_at < now-retention 삭제, 반환=삭제 수 |
| `reset_for_tests` | `() -> None` | thread-local conn drop + 스키마 캐시 클리어 (conftest 격리용) |

### 3.4 detector 훅 (F1 + F6)

`_emit_new` 말미(emitted 확정 후):

```python
if emitted:
    store_findings.record_findings(emitted)          # never raises (내부 격리)
    store_findings.prune_findings()                  # lazy retention, 동일 격리
```

## 4. API Specification

### 4.1 Endpoint List

| Method | Path | 변경 | Description |
|---|---|---|---|
| GET | `/anomaly/findings` | **신규** | 발행 이력 조회 (F2) |
| GET | `/anomaly/state` | **신규** | 쿨다운/스캔 상태 (F3) |
| GET | `/anomaly/scan` | **확장** | 기존 미리보기 + what-if 오버라이드 파라미터 (F5) |
| POST | `/anomaly/scan` | 불변 | 발행 트리거 — 파라미터 서명 변경 없음 |
| GET | `/anomaly/rules` | 불변 | 임계치 노출 (what-if 폼의 기본값 소스) |

### 4.2 Detailed Specification

**GET /anomaly/findings** — query: `days: int = 30 (ge=1, le=365)`, `kind: str | None`, `severity: str | None`, `limit: int = 200 (ge=1, le=500)`

```json
{
  "days": 30, "count": 2,
  "findings": [
    {"id": 42, "kind": "volume_drop", "severity": "critical",
     "key": "volume_drop:2026-07-06", "message": "…",
     "details": {"date": "2026-07-06", "qty": 120.0}, 
     "event_type": "production.anomaly.volume_drop",
     "emitted_at": "2026-07-07T06:00:00"}
  ]
}
```

**GET /anomaly/state**

```json
{
  "last_scan_ts": 1783500000.0,
  "cooldown_sec": 86400,
  "cooldowns": [
    {"key": "volume_drop:2026-07-06", "emitted_ts": 1783490000.0,
     "remaining_sec": 76400, "active": true}
  ]
}
```

- `remaining_sec = max(0, cooldown_sec - (now - emitted_ts))`, `active = remaining_sec > 0`.
- state 파일 read-only — 이 엔드포인트는 어떤 쓰기도 하지 않는다.

**GET /anomaly/scan (F5 확장)** — 신규 optional query (모두 None이면 기존과 동일):
`drop_pct: float | None (gt=0)`, `spike_pct: float | None (gt=0)`, `stale_days: int | None (ge=1)`, `min_baseline_qty: float | None (ge=0)`, `baseline_days: int | None (ge=1, le=365)`

응답에 `"overrides": {…}` 에코 추가(what-if임을 UI가 표시). **POST 라우트 함수는 이 파라미터를 받지 않는다** — FastAPI가 unknown query를 무시하므로 emit 판정은 항상 cfg 기준.

### 4.3 detector/rules 시그니처 변경

```python
@dataclass(frozen=True)
class RuleOverrides:          # api/anomaly/schemas.py
    drop_pct: float | None = None
    spike_pct: float | None = None
    stale_days: int | None = None
    min_baseline_qty: float | None = None
    baseline_days: int | None = None

collect_findings(today=None, overrides: RuleOverrides | None = None)
run_detection(emit=True, today=None, overrides: RuleOverrides | None = None)
```

- `collect_findings` 내부에서 `eff = overrides.value if not None else cfg.X` 해석. rules 함수 시그니처는 이미 파라미터화돼 있어 불변.
- **가드**: `run_detection`은 `emit and overrides` 조합을 거부(ValueError) — 라우터가 막지만 심층 방어.

## 5. UI/UX Design

### 5.1 페이지 등록

`dashboard/app.py` — "관리" 그룹, Webhook 관리 위:

```python
st.Page("views/anomaly.py", title="이상탐지", icon=":material/monitor_heart:"),
```

### 5.2 `dashboard/views/anomaly.py` 레이아웃 (위→아래)

1. **헤더 + 상태 메트릭 행**: 현재 findings 수 / 마지막 스캔 시각(state) / 활성 쿨다운 수 / 새로고침 버튼(캐시 클리어)
2. **현재 스캔 결과**: `GET /scan` → kind별 그룹, severity 배지(critical=빨강/warning=노랑 — `st.badge` 네이티브), 각 finding message + details expander. 0건이면 `st.success("현재 이상 없음")`
3. **최근 30일 타임라인**: `GET /findings?days=30` → `_parsing.findings_to_daily_counts()` → severity별 stacked bar(plotly, 기존 `get_chart_config` 재사용) + 이력 테이블(`st.dataframe`, kind/severity 필터 selectbox). 0건이면 "이력 누적 시작" 안내
4. **쿨다운 현황** (expander): `GET /state` → key / 남은 시간(휴먼 포맷) / active 배지 테이블
5. **what-if 미리보기** (expander): `GET /rules`로 현재값을 기본값으로 한 number_input 5개 + "미리보기" 버튼 → `GET /scan?…` → 결과를 섹션 2와 동일 렌더 + `st.info("미리보기 — 발행되지 않음")` 배지

### 5.3 클라이언트/캐시

- httpx 헬퍼는 dataset_page 관례(`_headers()` API 키 지원 포함, timeout 15s, `httpx.HTTPError` → `st.error` + `st.stop()` 아님 — 섹션별 독립 실패 허용: 실패한 섹션만 warning).
- `@st.cache_data(ttl=60)` for scan/findings/state fetch. what-if 호출은 캐시 없음(버튼 트리거).
- 순수 변환(타임라인 집계, 남은 시간 휴먼 포맷)은 `dashboard/components/anomaly_view_helpers.py`(신규, streamlit-free)에 배치: `findings_to_daily_counts(findings: list[dict]) -> pd.DataFrame`, `humanize_remaining(sec: float) -> str`. (구현 시 변경: `_parsing.py`는 AI 섹션 특성화 테스트 전용 모듈이라 오염 방지 차원에서 전용 모듈로 분리 — 정책 취지는 동일)

## 6. Error Handling

| 상황 | 처리 |
|---|---|
| record_findings 실패 (디스크/락) | store_findings 내부 warning 로그 + 0 반환 — 발행·마킹 흐름 무영향 (FR-6) |
| findings/state API에서 DB/파일 오류 | 빈 목록 + 200 (v1의 "호출부로 예외 안 던짐" 관례) — 단, 로그는 warning |
| 대시보드 API 다운 | 섹션별 st.warning, 페이지 전체는 살아있음 (FR-4) |
| what-if 파라미터 검증 실패 | FastAPI 422 (Query 제약) — UI는 number_input 범위로 사전 차단 |

## 7. Security Considerations

- 신규 엔드포인트 2종은 PUBLIC_PATHS 미포함 → 인증 활성 시 자동 보호 (d5b7ab8 회귀 테스트 패턴에 추가).
- what-if는 read-only 경로에만 존재 — 발행/상태 변경 불가를 테스트로 고정.
- findings details는 서버가 생성한 데이터만 포함(사용자 입력 없음). UI 렌더는 st.dataframe/markdown 기본 이스케이프.

## 8. Test Plan

### 8.1 Test Scope

| 대상 | 테스트 파일 | 케이스 |
|---|---|---|
| store_findings | `tests/test_anomaly_findings_store.py` (신규) | record/list 왕복, days·kind·severity 필터, limit 클램프, retention prune, 예외 격리(record가 raise 안 함), reset_for_tests |
| detector 훅 | `tests/test_anomaly_state.py` 확장 | emit 성공분만 기록, emit 실패분 미기록, record 실패해도 emitted 반환 불변 |
| API | `tests/test_anomaly_api.py` 확장 | /findings shape+필터, /state remaining 계산, what-if: drop_pct 오버라이드로 결과 변화 + 상태 파일 무변경, POST가 오버라이드 무시, run_detection(emit=True, overrides) ValueError |
| 순수 로직 | `tests/test_ai_table_parse.py` 또는 신규 | findings_to_daily_counts(빈/다중 severity), humanize_remaining |
| 인증 | `tests/test_audit.py` | admin 401 파라미터라이즈에 /anomaly/findings 추가 |

### 8.2 격리

- store_findings는 `cfg.ANOMALY_DB_FILE` monkeypatch + `reset_for_tests()` — conftest live_db 관례 준수 (`_close_db_connections` autouse가 커버하도록 thread-local 이름 규약 유지).

## 9. Clean Architecture

- rules(순수) ← detector(오케스트레이터) ← router(HTTP) 계층 불변. store_findings는 store_state와 나란한 영속화 계층.
- 대시보드: views(렌더) / _parsing(순수 변환) / httpx 헬퍼(IO) 분리 — webhook_admin 3계층의 축소판.

## 10. Coding Convention Reference

- except 3-class 정책(N/J/D), BLE001은 boundary에만 noqa+사유.
- 한글 콘텐츠 파일 E501 per-file-ignore 대상 여부 확인(views/anomaly.py 예상됨 — 기존 5개 파일 목록에 추가).

## 11. Implementation Guide

### 11.1 File Structure

```
shared/config.py                        # +2 노브
api/anomaly/store_findings.py           # 신규 (F1/F6)
api/anomaly/schemas.py                  # +RuleOverrides
api/anomaly/detector.py                 # collect_findings/run_detection overrides + _emit_new 훅
api/routers/anomaly.py                  # +/findings +/state, GET /scan 확장
dashboard/components/anomaly_view_helpers.py  # 신규: findings_to_daily_counts, humanize_remaining
dashboard/views/anomaly.py              # 신규 페이지
dashboard/app.py                        # nav 1줄
tests/test_anomaly_findings_store.py    # 신규
tests/{test_anomaly_api,test_anomaly_state,test_audit}.py  # 확장
```

### 11.2 Implementation Order

1. config 노브 → store_findings + 테스트 (독립 커밋)
2. RuleOverrides + detector 훅/오버라이드 + 테스트 (커밋)
3. 라우터 3종 + API/인증 테스트 (커밋)
4. _parsing 헬퍼 + views/anomaly.py + app nav + 순수 로직 테스트 (커밋)
5. 게이트 확인 → docs 갱신

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-07-07 | 최초 작성 — plan F1~F6 전체 구체화 |
| 0.2 | 2026-07-08 | 구현 반영: 순수 헬퍼를 _parsing.py 대신 전용 anomaly_view_helpers.py로 분리(특성화 모듈 오염 방지). 헬퍼 테스트는 디스크 직접 로드 경계 패턴 |
