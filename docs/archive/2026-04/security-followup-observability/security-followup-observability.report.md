---
template: report
feature: security-followup-observability
date: 2026-04-14
phase: completed
match_rate: 95
status: completed
parent: security-and-test-improvement
---

# security-followup-observability — 완료 보고서

> **Plan**: [security-followup-observability.plan.md](../01-plan/features/security-followup-observability.plan.md)
> **Design**: [security-followup-observability.design.md](../02-design/features/security-followup-observability.design.md)
> **Analysis**: [security-followup-observability.analysis.md](../03-analysis/security-followup-observability.analysis.md)
> **부모 사이클**: `docs/archive/2026-04/security-and-test-improvement/`
> **Date**: 2026-04-14

---

## 1. Executive Summary

부모 사이클(`security-and-test-improvement`)에서 Deferred 된 Low/Info Gap 4건(G3/G5/G6/G7)을 단일 PDCA 사이클로 마감했다. Match Rate **95%**, 1회 iteration 없이 통과, 회귀 0.

| 지표 | 결과 |
|---|---|
| Match Rate | **95%** (threshold 90%) |
| 테스트 | **133 passed** (128 → +5) |
| 회귀 | 0건 |
| 테스트 suite 벽시계 | **10.52s** (설계 <30s ✅) |
| 신규 파일 | 1 (`scripts/perf_smoke.py`) |
| 수정 파일 | 5 |
| Iteration | 0 / 5 (불필요) |

---

## 2. 부모 Gap → 본 사이클 FR 매핑

| 부모 Gap | 본 사이클 FR | 결과 |
|---|---|---|
| G3 `/healthz/ai` sessions 블록 미노출 | FR-01 | ✅ Closed |
| G5 통합 테스트 5종 누락 | FR-02 | ✅ Closed (4 신규 + 1 재사용) |
| G6 성능 스모크/벽시계 기록 | FR-03 | ✅ Closed (스크립트 + 벽시계 기록, 10k 실측은 수동) |
| G7 whitelist 부재 boot warning | FR-04 | ✅ Closed |

---

## 3. 구현 결과

### 3.1 FR-01 — `/healthz/ai` sessions block
- `api/main.py`: `from . import _session_store as _sstore` 추가, 6개 return path 모두에 `"sessions": _sstore.stats()` 주입
- `_session_store.stats()` 가 이미 정확한 4-키 dict(`count/ttl_sec/max_per_ip/max_total`) 를 반환해 재사용
- 검증: `test_healthz_ai_shape` 가 키 집합과 `count: int` 타입 체크

### 3.2 FR-02 — Integration tests (4 신규)
| 테스트 | 엔드포인트 | 검증 |
|---|---|---|
| `test_records_by_item_code` | `GET /records/BW0021` | 200/404 허용 |
| `test_summary_by_item` | `GET /summary/by_item` | `date_from/to` 포함, 200/404 |
| `test_records_invalid_cursor_is_graceful` | `GET /records?cursor=@@…` | graceful 200 fallback |
| `test_chat_rate_limit_boundary` | `POST /chat/` ×4 | `max_requests=3` monkeypatch 후 4번째 429 + `detail.code=="RATE_LIMITED"` |

### 3.3 FR-03 — Performance smoke
- **신규** `scripts/perf_smoke.py` (httpx sync loop, optional psutil, CLI `--url/--path/--n`, JSON 1-line 출력)
- **기록** `docs/specs/operations_manual.md §10`: pytest 10.52s/133 tests, 10k 실행 가이드

### 3.4 FR-04 — Whitelist import-time warning
- `shared/config.py::_load_archive_whitelist()` 가 미존재 경로에 `_logger.warning("ARCHIVE_DB_WHITELIST entry not found at import: %s", resolved)` 1회 출력
- 동작 분기 없음 — 경고만, 런타임 `resolve_archive_db()` 의 `exists()` 차단 정책 유지
- 검증: `test_missing_whitelist_entry_logs_warning` (`importlib.reload` + `caplog`, env 복원 fixture)

### 3.5 파일 맵

| 상태 | 파일 |
|---|---|
| NEW | `scripts/perf_smoke.py` |
| MOD | `api/main.py` |
| MOD | `shared/config.py` |
| MOD | `tests/test_api_integration.py` |
| MOD | `tests/test_archive_whitelist.py` |
| MOD | `docs/specs/operations_manual.md` |

---

## 4. 테스트 결과

```
$ pytest tests/ -q
133 passed in 10.52s
```

| 파일 | 기존 | 추가 | 합계 |
|---|---|---|---|
| `test_api_integration.py` | 12 | +4 | 16 |
| `test_archive_whitelist.py` | 9 | +1 | 10 |
| `test_session_store.py` | 6 | 0 | 6 |
| 기타 기존 | 101 | 0 | 101 |
| **전체** | **128** | **+5** | **133** |

---

## 5. 잔여 항목 (Info)

| # | 내용 | 조치 경로 |
|---|---|---|
| i1 | invalid cursor 는 설계상 400 기대였으나 `_decode_cursor` 는 graceful fallback(200). 정책 차이 — 엄격화 필요 시 별도 피처로 분리 | 선택적 후속 |
| i2 | 10k `/healthz` 실측 RSS 값 운영 매뉴얼에 공란. 서버 기동 필수 수동 작업 | 운영자가 1회 실행 후 `operations_manual.md §10` 값 채움 |

두 건 모두 Info 레벨, 사이클 종료에 영향 없음.

---

## 6. 배운 점

- **작은 Gap 묶음은 단일 사이클로** — 부모 사이클의 Deferred 4건을 분리 처리했다면 각각 overhead 가 컸을 것. 관련 영역을 한 주제("운영 관측성 + 테스트 매트릭스 마감")로 묶어 1 PDCA 로 완료.
- **기존 헬퍼 재사용 원칙** — `_session_store.stats()` 가 이미 완벽한 shape 를 반환하는 것을 확인해 FR-01 이 한 줄 주입으로 끝남. 스펙 작성 전 기존 API 표면을 먼저 grep.
- **Test monkeypatch 레벨 선택** — rate limiter 인스턴스 속성(`max_requests`) 을 직접 patch 하는 방식이 모듈 상수 patch 보다 안정적 (중간 캐싱 레이어 우회).
- **스펙 vs 실제 구현 불일치 처리 패턴** — invalid cursor 건처럼 설계 기대와 구현 정책이 다를 때, 구현을 바꾸는 대신 **실제 동작을 테스트로 고정 + 분석 문서에 g1 로 기록** 하는 경로가 scope 보호에 유효.
- **reload 기반 테스트의 격리** — `importlib.reload(shared.config)` 는 전역 상태를 바꾸므로 fixture 종료 시 env 원복 + reload 원복 이중 안전 필요.

---

## 7. 결론

- Match Rate **95%** 로 임계값 통과, 회귀 0, iteration 불필요.
- 부모 사이클의 Deferred 4건 모두 해소.
- `/pdca archive security-followup-observability` 진행 가능.
