# webhook-bulk-retry-v1 Completion Report

> **Cycle**: webhook-bulk-retry-v1
> **Date**: 2026-05-28
> **Status**: ✅ Complete (gap 100%, 13/13 AC, iterate 0)
> **Author**: interojo (Claude assisted)
> **Docs**: [Plan](../01-plan/features/webhook-bulk-retry-v1.plan.md) · [Design](../02-design/features/webhook-bulk-retry-v1.design.md) · [Analysis](../03-analysis/webhook-bulk-retry-v1.analysis.md)

---

## 1. 무엇을 / 왜

webhook delivery의 **터미널 실패(dead/failure) 일괄 재시도** API + admin UI 버튼을 추가했다.

기존엔 단건 `POST /notifications/deliveries/{id}/retry` 하나뿐이라, 외부 수신 시스템 장애로 dead-letter가 수십~수백 건 쌓이면 1건씩 재시도해야 했고 admin UI는 webhook당 최근 10개 버튼만 노출했다. 본 사이클로 **장애 복구 시 한 번의 호출(또는 버튼 1클릭)로 전량 재큐잉**이 가능해졌다.

5개 후보(테스트 커버리지 게이트 / delivery 모니터링 SSE / Prometheus metrics / 헬스·레디니스 분리 / dead-letter 일괄 재시도) 중 선정 근거: webhook 서브시스템이 최근 집중 투자 영역이고, 단건 `requeue_delivery` primitive가 이미 있어 batch는 저위험 자연 확장이며, "장애 후 대량 재처리"라는 구체적·즉각적 운영 가치를 준다.

## 2. 산출물

### API
- `POST /notifications/deliveries/bulk-retry` — body `{statuses, webhook_id, limit, dry_run}`, 응답 `{requeued, ids, dry_run, statuses, webhook_id}`.
- 허용 상태 `{dead, failure}` (allow-list). 그 외/빈 리스트 → 400. limit 1..5000(le 위반 422).
- dry_run → 무변경 프리뷰(대상 ids 반환).

### Store (`api/notifications/deliveries_repo.py`)
- `RETRYABLE_TERMINAL_STATUSES = ("dead","failure")` 단일 진실원.
- `list_retryable_delivery_ids(*, statuses, webhook_id, limit)` — 읽기 전용(dry_run).
- `requeue_deliveries(*, statuses, webhook_id, limit)` — 단일 `BEGIN IMMEDIATE` SELECT→UPDATE, 재큐잉 id 반환. 컬럼 리셋셋은 단건 `requeue_delivery`와 동일(parity).
- `_effective_statuses` 교집합 방어(라우트 400과 이중 방어).
- store.py facade re-export + `__all__` 갱신.

### Admin UI (`dashboard/components/webhook_admin/`)
- `api_client.bulk_retry_dead(*, statuses, webhook_id, limit, dry_run)`.
- `views.render_queue_stats_section` — dead>0일 때 "💀 dead N건 전체 재시도" 버튼 + `_do_bulk_retry_dead`(spinner+toast+rerun). 모듈 레벨 api 호출 0 유지.

### 테스트 (신규 15, 전부 통과)
- `tests/test_notifications_bulk_retry.py` 11건 (AC1~AC11 통합, httpx 0건).
- `tests/test_webhook_admin_ui.py` +4건 (api_client 3 + views 와이어링 1).

## 3. 품질 결과

| 항목 | 결과 |
|------|------|
| gap-detector (AC1~AC13) | **100% (13/13)** + 설계 결정 8/8 |
| 신규 테스트 | 15 passed |
| 전체 회귀 | 305 passed, 1 failed(사전 존재·범위 밖) |
| 라이브 in-process 스모크 | dry_run 무변경 / 400 / 422 / 실행 3건 / 재실행 0건(멱등) 확인 |
| 신규 외부 의존성 | 0 |
| iterate 횟수 | 0 (임계 90% 초과) |

**사전 존재 실패 1건**: `test_rate_limiter.py::...retry_after_returns_positive_when_exceeded` (`assert 61 <= 60`). 원인 `shared/rate_limiter.py:132`의 `+1` off-by-one — 본 사이클 diff에 없는 HEAD 파일, webhook과 무관.

## 4. 핵심 설계 결정

- **allow-list 상태 제한**: `queued/in_flight/retrying/success`는 일괄 재시도 금지(in_flight double-dispatch·success 재발송 위험). dead-letter 본래 의미에 맞춰 기본 `["dead"]`.
- **단일 IMMEDIATE 트랜잭션**: SELECT한 id만 UPDATE → 반환 ids = 실제 변경분 정확. select↔update 사이 신규 dead 유입은 다음 호출에서 처리.
- **dry_run 분리**: mutation 전 영향 범위 확인(운영 안전).
- **비활성 webhook 재큐잉**: 의도적으로 허용하되 워커 `claim_due`가 active=1만 집으므로 재발송 안 됨(재활성화 시 자동 처리). plan Risk에 문서화.

## 5. Carry-over (후속)

1. `webhook-ui-status-fix-v1`(후보): `is_retryable_status`/`_DELIVERY_STATUSES`가 실제 DB값 `failure` 대신 `failed` 참조 → 단건 retry 버튼이 failure row 미노출. 본 사이클 Out-of-Scope.
2. `shared/rate_limiter.py` retry_after `+1` off-by-one 버그픽스(독립).
3. 일괄 재시도 dry_run 결과 프리뷰 테이블 UI.

## 6. 커밋 (레이어별 분할)

1. `feat(api): webhook dead-letter 일괄 재시도 store + 라우트` (deliveries_repo, store, routers/notifications)
2. `feat(dashboard): webhook 큐 상태 dead 일괄 재시도 버튼` (api_client, views)
3. `test: webhook-bulk-retry 통합 + admin UI 테스트` (test_notifications_bulk_retry, test_webhook_admin_ui)
4. `docs(pdca): webhook-bulk-retry-v1 plan/design/analysis/report`
