---
template: plan
feature: security-followup-observability
date: 2026-04-14
phase: plan
parent: security-and-test-improvement
---

# security-followup-observability — Plan

> **부모 사이클**: [security-and-test-improvement](../../archive/2026-04/security-and-test-improvement/)
> **유래**: 부모 분석에서 Deferred 처리된 Low/Info gap 4건(G3/G5/G6/G7)을 한 묶음으로 소화하는 후속 피처.
> **범위 원칙**: "운영 관측성 + 테스트 매트릭스 마감" — 새 기능 추가 없음.

---

## 1. 배경

`security-and-test-improvement` PDCA 1회차에서 Match Rate 93%로 종료하면서 다음 4건을 백로그로 이관했다.

| 원 Gap | Severity | 영역 | 요약 |
|---|---|---|---|
| G3 | 🟢 Low | `/healthz/ai` | `sessions.{count,ttl_sec,max_per_ip}` 블록 미노출 |
| G5 | 🟢 Low | 통합 테스트 | 5개 엔드포인트/오류 케이스 누락 |
| G6 | 🟢 Low | 성능 스모크 | 10k req RSS, suite 벽시계 측정 미기록 |
| G7 | 🟢 Info | whitelist boot | 존재하지 않는 경로에 대한 one-shot warning 부재 |

각각 단독으로는 작지만 운영/테스트 커버리지 측면에서 공백이다. 함께 처리해 한 번의 PDCA 비용으로 마감한다.

---

## 2. 목표 (Goal)

1. `/healthz/ai` 응답에 세션 통계 블록을 추가해 운영자가 세션 누수를 즉시 관찰할 수 있게 한다.
2. 부모 §8.2 테스트 매트릭스를 100%로 맞춘다 (5개 케이스 추가).
3. 통합 테스트 suite 벽시계 시간을 CI 로그/운영 매뉴얼에 기록한다. 10k 요청 메모리 스모크는 수동 스크립트로 제공.
4. `ARCHIVE_DB_WHITELIST` 항목 중 실파일이 없는 것을 import 시 1회 경고.

---

## 3. 범위

### 3.1 In Scope

- **FR-01** `GET /healthz/ai` payload 확장: `sessions: {count:int, ttl_sec:int, max_per_ip:int, max_total:int}` 필드 추가. `api/_session_store.stats()` 이미 존재 — 재사용.
- **FR-02** `tests/test_api_integration.py` 에 다음 5개 추가:
  1. `GET /records/BW0021` (단건 상세)
  2. `GET /summary/by_item`
  3. `GET /records?cursor=<invalid>` → 400
  4. 레이트리밋 경계(21번째 호출 429) — `RATE_LIMIT_PER_MIN` monkeypatch
  5. `GET /records?date=bad-date` → 400
- **FR-03** `docs/specs/operations_manual.md` 에 "테스트 suite 벽시계" 섹션 추가, CI 로그에서 측정한 최근 값 1회 기록. `scripts/perf_smoke.py` (신규, 수동) — httpx 로 10k 요청 후 RSS 출력.
- **FR-04** `shared/config.py::_load_archive_whitelist()` 에 미존재 경로 `logger.warning("ARCHIVE_DB_WHITELIST entry not found: %s", p)` 1회 출력.

### 3.2 Out of Scope

- 신규 에러 코드 추가
- `chat.py` 추가 리팩터
- 부하 테스트 자동화 (GitHub Actions 에 스모크 스크립트 편입은 후속 티켓)
- Streamlit/Manager 테스트

---

## 4. 성공 기준

| 항목 | 기준 |
|---|---|
| Match Rate | ≥ 90% (1회 iteration 안에서) |
| 테스트 | 128 → **133+** pass, 회귀 0 |
| `/healthz/ai` | sessions 4-키 응답, 스키마 테스트로 검증 |
| 운영 매뉴얼 | 벽시계 값 기록 1줄 이상 |
| whitelist 경고 | 테스트에서 `caplog` 로 검증 |

---

## 5. 리스크 및 완화

| 리스크 | 완화 |
|---|---|
| 레이트리밋 21번째 호출 테스트의 시간 의존성 | `_RATE_LIMIT_PER_MIN` monkeypatch + `time.monotonic` 고정 대신 패치 없이 연속 호출만으로 경계 도달하도록 상수 낮춤 |
| whitelist 경고가 부모 기존 동작을 바꾸지 않아야 함 | `logger.warning` 만 추가, 동작 분기 없음. 기존 `test_archive_whitelist.py` 회귀 확인 |
| 10k 스모크가 CI 에서 과도한 시간 소모 | 수동 스크립트로만 제공, CI 자동 실행 제외 |

---

## 6. 구현 순서 (제안)

1. **FR-04** whitelist 경고 (가장 가볍고 격리)
2. **FR-01** `/healthz/ai` sessions 블록 + 스키마 테스트
3. **FR-02** 통합 테스트 5종
4. **FR-03** `scripts/perf_smoke.py` + 운영 매뉴얼 섹션
5. `/pdca analyze security-followup-observability`

---

## 7. 참고

- 부모 보고서: `docs/archive/2026-04/security-and-test-improvement/security-and-test-improvement.report.md`
- 부모 Design §4.2 `/healthz/ai`, §8.2 테스트 매트릭스, §3.3 whitelist
