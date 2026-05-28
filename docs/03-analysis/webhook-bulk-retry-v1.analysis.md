# webhook-bulk-retry-v1 Gap Analysis

> **Cycle**: webhook-bulk-retry-v1
> **Date**: 2026-05-28
> **Phase**: Check (gap-detector)
> **Companion**: [Plan](../01-plan/features/webhook-bulk-retry-v1.plan.md) · [Design](../02-design/features/webhook-bulk-retry-v1.design.md)

---

## 1. 산출 기준

- AC1~AC13 대상. AC14(gap-detector ≥90%)는 self-referential이므로 제외.
- 도구: bkit:gap-detector (읽기 전용 설계-구현 대조).

## 2. AC 매핑 (13/13 충족)

| AC | 결과 | 근거 (심볼/테스트) |
|----|:----:|------|
| AC1 기본 dead 일괄 재큐잉 | ✅ | `requeue_deliveries` / `test_bulk_retry_default_requeues_all_dead` |
| AC2 dead+failure만, 타 상태 불변 | ✅ | `_effective_statuses` 교집합 / `test_bulk_retry_dead_and_failure_only` |
| AC3 dry_run 무변경 | ✅ | 라우트 dry_run 분기→`list_retryable_delivery_ids` / `test_bulk_retry_dry_run_does_not_mutate` |
| AC4 webhook_id 스코핑 | ✅ | `where_wh` 절 / `test_bulk_retry_webhook_id_scopes` |
| AC5 허용외 status 400 | ✅ | 라우트 `invalid` 검증 / `test_bulk_retry_forbidden_status_400` (3 케이스) |
| AC6 빈 statuses 400 | ✅ | 라우트 `if not requested` / `test_bulk_retry_empty_statuses_400` |
| AC7 대상 0건 200/requeued=0 | ✅ | `test_bulk_retry_no_targets_returns_zero` |
| AC8 limit clamp(id ASC) + le5000 422 | ✅ | `ORDER BY id ASC LIMIT` + `Field(le=5000)` / caps + 422 테스트 |
| AC9 워커 즉시 dispatch→success | ✅ | `tick_once()` / `test_requeued_delivery_is_dispatched_by_worker` |
| AC10 raw row attempt=1/NULL parity | ✅ | UPDATE 컬럼셋 단건 동일 / `test_bulk_requeue_resets_attempt_and_response_fields` |
| AC11 OpenAPI 신규 path + 기존 유지 | ✅ | `test_openapi_includes_bulk_retry_path` |
| AC12 api_client path/method/body | ✅ | `bulk_retry_dead` / UI 테스트 3건 |
| AC13 views 와이어링 + 모듈레벨 호출 0 | ✅ | `_do_bulk_retry_dead`/버튼 key / `test_views_wires_bulk_retry_button_in_queue_stats` |

**설계 결정 일치: 8/8** (keyword-only, 교집합 방어, BEGIN IMMEDIATE, 400/422 이중 방어, facade re-export, UI 조건부 버튼, 라우트 등록 순서, attempt/응답필드 리셋 parity).

## 3. 전체 일치율

**AC1~AC13 = 13/13 → 100%** · 설계 결정 8/8. 미충족/부분 항목 0건 → **iterate 불필요**.

## 4. 테스트 결과

- 신규/관련: `tests/test_notifications_bulk_retry.py`(11) + `tests/test_webhook_admin_ui.py`(+4) = **15 신규, 전부 통과**.
- 전체 회귀: **305 passed, 1 failed**.
  - 유일 실패 `tests/test_rate_limiter.py::...test_retry_after_returns_positive_when_exceeded` (`assert 61 <= 60`).
  - **사전 존재 + 범위 밖**: `shared/rate_limiter.py:132` `int(retry_at - current_time) + 1` off-by-one. 해당 파일은 본 사이클 diff에 없음(HEAD 상태). webhook 영역과 무관.

## 5. 의도적 미세 편차 (개선 아님)

- `_do_bulk_retry_dead`에 `st.spinner` 래핑 추가 (UX, 동작 동일).
- caption 문구 설계 대비 미세 상이 (표시 문자열, 기능 무관).

## 6. Carry-over 권고 (후속 사이클)

1. UI `formatters.is_retryable_status` / `views._DELIVERY_STATUSES`가 실제 DB 상태 `failure` 대신 `failed`를 참조 — 단건 retry 버튼이 `failure` row에 노출되지 않는 잠재 불일치. 본 사이클 Out-of-Scope(기존 동작/테스트 변경 회피). → `webhook-ui-status-fix-v1` 후보.
2. `shared/rate_limiter.py` retry_after off-by-one (`+1`로 window 초과). → 독립 버그픽스.
