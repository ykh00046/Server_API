# rate-limiter-clock-injection — Gap Analysis

> **Cycle**: rate-limiter-clock-injection
> **PDCA Phase**: Check
> **Date**: 2026-06-13
> **Design**: [[rate-limiter-clock-injection.design]]
> **Match Rate**: **100%** (AC 7/7)

## AC별 검증

| # | Criterion | 실측 결과 | 판정 |
|---|-----------|-----------|:----:|
| AC1 | RateLimiter clock 주입, `time.time()` 직접 호출 0곳(기본값 제외) | `__init__(clock=time.time)` + 6개 메서드 `self._clock()`. 본문 `time.time()` 직접 호출 0건(L48 기본값만) | ✅ |
| AC2 | test_rate_limiter.py `time.sleep` 0건 + 시간 단축 | sleep 0건(`import time` 제거), 파일 단독 실행 **5.3s+ → 0.21s** | ✅ |
| AC3 | bulk_retry flaky 근본 원인 재현 증거와 함께 기록 | **재현 성공**(반복 실행 1회차 실패): `test_requeued_delivery_is_dispatched_by_worker`에서 `assert _status_of(did)=="queued"`가 `success` — §근본원인 참조 | ✅ |
| AC4 | 원인 수정 적용 | 타겟(테스트 자기 스레드 드레인) + 방어(conftest autouse 가드) 2중 | ✅ |
| AC5 | **전체 스위트 연속 10회 all green** | **10/10 green** (363 passed, 각 ~13-16s). baseline은 **2/10 실패** | ✅ |
| AC6 | 기존 테스트 green + ruff + CI | 363 passed, ruff All checks passed, CI(아래) | ✅ |
| AC7 | match rate ≥ 90% | 100% | ✅ |

## 근본 원인 (재현·규명)

**증상**: `test_requeued_delivery_is_dispatched_by_worker`가 bulk-retry 직후 delivery 상태를 `queued`로 기대하나 간헐적으로 `success`. 전체 스위트에서만, 단독/파일 단위는 항상 green. 누적 4회 관찰.

**메커니즘** (소스 + 재현으로 확정):
1. `test_worker_stop_timeout_does_not_raise`(test_notifications_async.py)가 `tick_sec=0.05` + **1.5초 느린 핸들러** 워커를 `worker.start()`로 실제 데몬 스레드 기동.
2. `worker.stop(timeout=0.2)` — 스레드가 느린 핸들러 안에서 블록 중이라 join 타임아웃 → `feedback_timeout_daemon_gc` 정책대로 "GC 위임", `_thread=None`. **데몬 스레드는 여전히 살아있음.**
3. ~1.5초 후 핸들러 반환 → `_finalize()` → `store.record_attempt()` → `store._get_conn()`이 `_db_path()`를 **전역 `_cfg.NOTIFICATIONS_DB_FILE`에서 호출 시점에 재해석**(monkeypatch 지원용 의도적 동작).
4. 그 시점엔 async 테스트가 끝나고 **나중 테스트(bulk_retry)의 `isolated_db`가 전역에 활성**. 양 테스트 모두 빈 DB의 첫 delivery = autoincrement **id=1**.
5. 누출 스레드가 `record_attempt(1, next_status="success")`를 **bulk_retry의 DB에** 기록 → bulk_retry가 막 `queued`로 만든 id=1이 `success`로 뒤집힘.

→ **제품 결함이 아님**(프로덕션은 단일 DB·단일 워커, 경로 스왑 없음). 테스트 격리 결함 — 워커가 monkeypatch 경계를 넘어 누출.

## 수정 (2중)

1. **타겟** (`test_notifications_async.py`): `stop()` 후 `busy_thread.join(5.0)`으로 in-flight 틱을 **자기 테스트의 isolated_db가 활성인 동안** 드레인 → 후속 write가 올바른 DB로. 테스트 본래 목적(busy 중 stop()이 non-blocking 반환)은 assert로 보존.
2. **방어** (`conftest.py`): autouse `_join_leaked_webhook_workers`가 매 테스트 후 잔존 `WebhookDispatchWorker` 스레드를 join → 미래 누출도 다음 테스트로 못 넘어감.

## 권장 조치

없음 — **100% → Report.** Part A로 스위트 실행 시간도 ~5s 단축(부수 효과).
