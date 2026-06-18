# anomaly-detection-v1 Design Document

> **Summary**: 생산 이상 탐지를 "순수 규칙 함수 + 오케스트레이터 + 쿨다운 상태 + 스케줄 러너 + 조회 API"로 구성하고, 발행은 기존 `emit_event`로 위임한다.
>
> **Project**: Production Data Hub
> **Version**: v10
> **Author**: Claude / bkit:pdca
> **Date**: 2026-06-19
> **Status**: Approved

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 이상 징후 능동 감지 + 알림. 발행 인프라는 재사용. |
| **WHO** | 운영자 / 생산관리. |
| **RISK** | 오탐·스팸·운영 DB 부하. |
| **SUCCESS** | 규칙 정확성 + dedup + read-only + 테스트/ruff 통과. |
| **SCOPE** | rules / detector / schemas / state / runner / router / config / tests. |

## 1. Overview

### 1.1 Design Goals

- 탐지 로직(순수)과 I/O(쿼리·발행·상태)를 분리해 단위 테스트를 쉽게 한다.
- 알림 발행은 신규 코드 없이 `emit_event`로 위임한다.
- 기능을 OFF로 둘 수 있고, 스캔은 read-only·idempotent하다.

### 1.2 Design Principles

- **SRP**: `rules.py`는 계산만, `detector.py`는 조율만, `store_state.py`는 영속만.
- **Fail-safe**: 탐지기 내부 예외는 잡아 로깅하고 부분 결과를 반환(러너/API 비중단).
- **Reuse over rebuild**: DBRouter 쿼리 패턴, watcher 상태파일 패턴, webhook emit 재사용.

## 2. Architecture Options

### 2.0 Architecture Comparison

| Option | 설명 | 장점 | 단점 | 채택 |
|--------|------|------|------|------|
| A. record.created 훅에 인라인 탐지 | 적재 시 즉시 평가 | 지연 최소 | 적재 경로 오염, 일 단위 기준선 산출 어려움, stale 탐지 불가 | ✗ |
| B. 독립 주기 스캐너(별도 러너) | watcher처럼 주기 스캔 | 적재 경로 무오염, 일 집계/ stale 자연스러움, watcher 패턴 재사용 | 탐지까지 최대 1주기 지연 | ✓ |
| C. APScheduler 등 신규 의존성 | 인앱 스케줄러 | 운영 단순 | 의존성·복잡도 추가, 기존 watcher 운영 모델과 불일치 | ✗ |

**채택: B** — 기존 `tools/watcher.py` 운영 모델(Task Scheduler/데몬)과 일치하고 적재 경로를 건드리지 않는다.

### 2.1 Component Diagram

```
tools/anomaly_watch.py (스케줄 러너: 단발/--daemon)
        │ run_detection(emit=True)
        ▼
api/anomaly/detector.py  ── 읽기 쿼리 ─▶ shared.database.DBRouter (read_only)
        │                                   └ production_records
        │ 1) 일별 수량 시계열 + 품목 마지막 생산일 조회
        │ 2) rules.detect_volume_anomalies(...)         (순수)
        │    rules.detect_stale_items(...)              (순수)
        │ 3) store_state: 쿨다운 필터(신규만)
        │ 4) emit_event(type, payload)  ──▶ api/notifications (큐→재시도→전달)
        ▼
api/routers/anomaly.py
   GET /anomaly/scan?emit=false   (dry-run 미리보기)
   GET /anomaly/rules             (활성 임계치)
```

### 2.2 Data Flow

1. 러너/엔드포인트 → `detector.run_detection(emit)`.
2. detector가 read-only로 (a) 최근 `BASELINE_DAYS+1`일 일별 양품 합계, (b) 품목별 마지막 생산일·기간 내 생산여부를 조회.
3. 순수 규칙이 Finding 리스트 산출.
4. `emit=True`면 store_state로 쿨다운 내 중복 키 제거 후 신규 Finding만 `emit_event` 비동기 발행, 발행분의 쿨다운 타임스탬프 기록.
5. 모든 Finding(발행 여부 플래그 포함) 반환.

### 2.3 Dependencies

- 신규 런타임 의존성 **없음**. 표준 라이브러리 + 기존 `shared`, `api.notifications`만 사용.

## 3. Data Model

스키마 변경 없음. 읽기 대상: `production_records(production_date, item_code, item_name, good_quantity)`.

상태파일 `database/.anomaly_state.json` (watcher 상태파일과 동급, gitignore):

```json
{
  "cooldowns": { "<finding_key>": <epoch_seconds> },
  "last_scan_ts": <epoch_seconds>
}
```

`Finding` (dataclass, `schemas.py`):

| 필드 | 타입 | 설명 |
|------|------|------|
| `kind` | str | `volume_drop` / `volume_spike` / `stale_item` |
| `severity` | str | `info` / `warning` / `critical` |
| `key` | str | dedup 키 (예: `volume_drop:2026-06-18`, `stale_item:BW0021`) |
| `message` | str | 사람이 읽는 한국어 요약 |
| `details` | dict | 근거 수치(current, baseline, change_pct, days_idle 등) |
| `event_type` | str | 매핑된 webhook 이벤트 타입 |

이벤트 타입(매핑):

| kind | event_type |
|------|------------|
| volume_drop | `production.anomaly.volume_drop` |
| volume_spike | `production.anomaly.volume_spike` |
| stale_item | `production.anomaly.stale_item` |

→ `register_event_type`로 KNOWN_EVENT_TYPES에 등록(emit 시 자동 등록되지만 모듈 임포트 시 선등록해 관리 UI 노출).

## 4. API Specification

### 4.1 Endpoint List

| Method | Path | 설명 |
|--------|------|------|
| GET | `/anomaly/scan` | 현재 Finding 미리보기. `emit` 쿼리(기본 false)면 발행 안 함 |
| GET | `/anomaly/rules` | 활성 임계치/설정 + 등록된 이벤트 타입 |

### 4.2 Detailed Specification

**GET /anomaly/scan?emit=false**

```json
{
  "scanned_at": "2026-06-19T...",
  "enabled": true,
  "emitted": false,
  "emitted_count": 0,
  "count": 2,
  "findings": [
    {"kind":"volume_drop","severity":"warning","key":"volume_drop:2026-06-18",
     "message":"2026-06-18 양품 12,000개 — 최근 14일 평균 30,000개 대비 60.0% 급감",
     "details":{"date":"2026-06-18","current":12000,"baseline":30000,"change_pct":-60.0},
     "event_type":"production.anomaly.volume_drop"}
  ]
}
```

- `emit=true`는 명시적으로만 발행(운영자 수동 트리거용). 일상 발행은 러너가 담당.

**GET /anomaly/rules**

```json
{
  "enabled": true,
  "baseline_days": 14,
  "drop_pct": 50.0, "spike_pct": 100.0,
  "stale_days": 7, "min_baseline_qty": 1, "cooldown_sec": 86400,
  "event_types": ["production.anomaly.volume_drop","production.anomaly.volume_spike","production.anomaly.stale_item"]
}
```

## 5. UI/UX Design

신규 화면 없음. 알림 표현은 webhook 구독자(외부 채널) 책임. 대시보드 시각화는 후속.

## 6. Error Handling

| 상황 | 처리 |
|------|------|
| DB 조회 실패 | 로깅 후 빈 Finding 반환(러너/ API 200/계속) |
| 상태파일 손상/부재 | 빈 상태로 간주, 재생성 |
| `emit_event` 내부 실패 | 기존 계약상 예외 없음, 발행 실패는 webhook delivery 상태로 관찰 |
| `ANOMALY_ENABLED=false` | 스캔은 빈 결과, 발행 0 |

## 7. Security Considerations

- 읽기 전용 연결만 사용, 사용자 입력 SQL 없음(파라미터 바인딩).
- 페이로드에 민감정보 없음(집계 수치·품목코드만).
- `/anomaly/*`는 기존 auth 미들웨어(opt-in) 정책을 그대로 따름(공개 경로 추가 안 함).

## 8. Test Plan

### 8.1 Test Scope

| 레벨 | 대상 |
|------|------|
| L1 단위 | `rules.detect_volume_anomalies`, `rules.detect_stale_items` 경계값 |
| L1 단위 | `store_state` 쿨다운 필터/기록/손상복구 |
| L2 통합 | `detector.run_detection` (live_db fixture, emit=False) → Finding |
| L2 API | `GET /anomaly/scan`, `GET /anomaly/rules` |
| 회귀 | 전체 pytest + ruff |

### 8.2 L1/L2 Scenarios

- 급감: current=baseline*(1-drop_pct/100) 경계에서 판정/미판정.
- 급증: current=baseline*(1+spike_pct/100) 경계.
- min_baseline_qty 미만 기준선은 급감/급증 모두 skip(0 나눗셈/노이즈 방지).
- stale: 기간 내 생산 이력 有 + 마지막 생산 ≥ stale_days → 판정. 이력 無 품목은 skip.
- 쿨다운: 동일 key 연속 스캔 시 2회차 발행 제외.
- detector: 합성 데이터로 급감+stale 동시 검출.

## 9. Clean Architecture

```
api/anomaly/
  __init__.py        # run_detection, Finding 재노출
  schemas.py         # Finding dataclass, KIND→event_type 매핑, 상수
  rules.py           # 순수 탐지 함수 (no I/O)
  store_state.py     # 쿨다운 상태 로드/저장/필터 (파일 I/O)
  detector.py        # 조율: 쿼리 → 규칙 → dedup → emit
api/routers/anomaly.py   # GET /anomaly/scan, /anomaly/rules
tools/anomaly_watch.py   # 스케줄 러너 (watcher.py 패턴)
```

의존 방향: router/runner → detector → (rules | store_state | DBRouter | emit_event). rules는 순수(무의존).

## 10. Coding Convention Reference

- 탐지/조율 모듈은 `from __future__ import annotations` 사용. (단, AI tool 모듈 아님 — Gemini 제약 무관)
- ruff 게이트(F/BLE001/I/UP/B/SIM/E501) 준수. 광범위 `except`는 `_store_*` 패턴처럼 좁히고 사유 주석.
- 한국어 메시지/주석 허용(기존 per-file-ignore 정책).

## 11. Implementation Guide

### 11.1 File Structure

위 9절 구조. 테스트: `tests/test_anomaly_rules.py`, `tests/test_anomaly_detector.py`, `tests/test_anomaly_api.py`.

### 11.2 Implementation Order

1. `shared/config.py` 노브 추가
2. `api/anomaly/schemas.py` (Finding + 매핑 + 상수)
3. `api/anomaly/rules.py` (순수 함수)
4. `api/anomaly/store_state.py` (쿨다운)
5. `api/anomaly/detector.py` (조율 + 쿼리)
6. `api/anomaly/__init__.py` (재노출 + 이벤트 타입 선등록)
7. `api/routers/anomaly.py` + `main.py` 라우터 등록
8. `tools/anomaly_watch.py`
9. 테스트 3종
10. 문서/`.env.example`/`.gitignore`

### 11.3 Session Guide

PDCA 한 세션 내 Do→Check→Act→QA→Report 일괄. 커밋은 논리 계층별 분할(메모리 `feedback_commit_style` 준수).

## Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-06-19 | Claude / bkit:pdca | 최초 작성 |
