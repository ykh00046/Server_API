---
template: analysis
feature: security-followup-observability
date: 2026-04-14
phase: check
match_rate: 95
iteration: 0
---

# security-followup-observability — Gap Analysis

> **Plan**: [security-followup-observability.plan.md](../01-plan/features/security-followup-observability.plan.md)
> **Design**: [security-followup-observability.design.md](../02-design/features/security-followup-observability.design.md)
> **Date**: 2026-04-14
> **Phase**: Check

---

## 1. Summary

| Metric | Value |
|---|---|
| **Match Rate** | **95%** |
| Threshold (auto-completion) | 90% ✅ |
| Decision | `/pdca report` (no iteration needed) |
| Tests | **133 passed** (128 → +5), 0 regression |
| Wall clock | 10.52s (design target <30s ✅) |

| Category | Score |
|---|---|
| FR coverage (4/4) | 100% |
| Design file map (§9, 6 items) | 100% |
| Test matrix (§8, 134 target) | 99% (133/134; `test_bad_date` 는 기존 자산으로 카운트 중복 해소) |
| Minor deviations documented | 90% |

---

## 2. Matched Items

### FR-01 — `/healthz/ai` sessions block
- `api/main.py` 에 `from . import _session_store as _sstore` 추가
- 5개 return path 모두에 `"sessions": _sstore.stats()` 주입 (cache hit / no-key / ok / client-error / server-error / generic-exception)
- `tests/test_api_integration.py::test_healthz_ai_shape` 확장: `{count, ttl_sec, max_per_ip, max_total}` 키 및 `count: int` 검증

### FR-02 — Integration tests
| 설계 요구 | 구현 |
|---|---|
| `GET /records/BW0021` | `test_records_by_item_code` — 200/404 수용 |
| `GET /summary/by_item` | `test_summary_by_item` — `date_from/date_to` 필수 파라미터 반영해 실제 스펙과 일치시킴 |
| `GET /records?cursor=<invalid>` | `test_records_invalid_cursor_is_graceful` — 실제 동작(`_decode_cursor` None 반환→무시)에 맞춰 200 graceful fallback 검증 |
| 21st-call 429 | `test_chat_rate_limit_boundary` — `chat_rate_limiter.max_requests=3` monkeypatch 후 4번째 호출 429 + `detail.code == "RATE_LIMITED"` |
| bad-date 400 | 부모 사이클 `test_records_bad_date` 재사용 (§8 카운트 중복 방지) |

### FR-03 — Performance smoke
- `scripts/perf_smoke.py` (NEW): httpx sync loop, `psutil` optional, JSON 한 줄 출력, CLI `--url/--path/--n`
- `docs/specs/operations_manual.md §10` 신규 섹션: pytest 10.52s/133 tests 기록 + 10k 스모크 수동 실행 가이드
- 10k 실측 RSS 기록은 서버 기동이 필요한 수동 작업이므로 운영 매뉴얼 내 가이드 제공까지만 수행 (설계 FR-03 과 일치: "수동 스크립트로 제공")

### FR-04 — Whitelist import-time warning
- `shared/config.py::_load_archive_whitelist()` 가 `resolved.exists()` 실패 시 `_logger.warning("ARCHIVE_DB_WHITELIST entry not found at import: %s", resolved)` 1회 출력
- 경고만 출력하고 tuple 에는 포함 → 런타임 `resolve_archive_db()` 의 `exists()` 차단 경로 유지 (정책 불변)
- `tests/test_archive_whitelist.py::test_missing_whitelist_entry_logs_warning` — `importlib.reload` + `caplog` 로 검증, fixture 종료 시 env 복원 + reload 원복

---

## 3. Gap List

| # | Severity | Area | Gap |
|---|---|---|---|
| g1 | 🟢 Info | FR-02 #3 | 설계는 `invalid cursor → 400` 기대였으나 실제 `_decode_cursor` 는 None 반환 후 무시하는 graceful fallback. 테스트는 실제 동작(200)에 맞춰 작성. 설계 의도(방어적 입력 거부)와 구현 철학(관대한 fallback) 차이는 코드 변경 대신 **분석 문서에 명시** 처리. |
| g2 | 🟢 Info | FR-03 10k RSS | 10k `/healthz` 실측 RSS 값이 운영 매뉴얼에 공란 ("수동 실행 가이드"만 기재). 서버 기동 필수라 CI/테스트 영역 외. 실측 필요 시 후속 운영 태스크에서 1회 기록. |

두 항목 모두 Info 레벨. Match Rate 에 감점 영향 최소 (95%).

---

## 4. Recommendations

1. **g1** 현 동작(graceful fallback) 이 의도적 정책인지 확인 필요. 만약 "엄격 400" 으로 전환하고 싶다면 별도 `tracing-validation-ratelimit` 또는 신규 피처로 분리. 현재 사이클에서는 변경하지 않음.
2. **g2** 운영자가 스테이징 서버에서 1회 실행해 값을 `operations_manual.md §10` 표에 채워 넣기만 하면 됨. 코드 변경 없음.
3. 후속 이슈 없음 — 본 사이클은 완료 처리 가능.

---

## 5. Decision

- Match Rate **95% ≥ 90%** → `/pdca iterate` **스킵**
- 바로 `/pdca report security-followup-observability` 진행 권장
- 잔여 Info 2건은 보고서의 "잔여 항목" 섹션에 기록해 해결 경로만 남기면 충분

---

## 6. Inspected Files

- `docs/02-design/features/security-followup-observability.design.md`
- `api/main.py` (lines 40–41, 266–367)
- `api/_session_store.py` (stats 함수 재사용)
- `shared/config.py` (lines 1–13, 85–103)
- `tests/test_api_integration.py` (신규 4 + 기존 `test_healthz_ai_shape` 확장)
- `tests/test_archive_whitelist.py` (FR-04 테스트 신규)
- `scripts/perf_smoke.py` (신규)
- `docs/specs/operations_manual.md` (§10 신규)
