# rate-limiter-clock-injection Completion Report

> **Summary**: 테스트 스위트의 두 flaky 원천 제거 — (A) RateLimiter clock 주입으로 sliding-window 테스트 결정론화, (B) bulk_retry 간헐 실패(누적 4회)의 근본 원인(누출 워커 스레드의 cross-DB 오염) 규명·수정. baseline 2/10 실패 → 10/10 green.
>
> **Project**: Server_API (Production Data Hub)
> **Date**: 2026-06-13
> **Match Rate**: 100% (AC 7/7 PASS)
> **Status**: Completed

---

## 1. 변경 요약

| ID | 변경 | 파일 | 커밋 |
|----|------|------|------|
| A1 | `RateLimiter.__init__`에 `clock: Callable=time.time` 주입, 6개 메서드 `self._clock()`. 전역 인스턴스 기본값 유지(프로덕션 diff 0) | `shared/rate_limiter.py` | 00c549b |
| A2 | sleep 4테스트 → `FakeClock(advance)`. `import time` 제거. 경계 테스트 1건 추가(정확히 window 경과 시 만료) | `tests/test_rate_limiter.py` | 00c549b |
| B1 | **타겟 수정**: `test_worker_stop_timeout_does_not_raise`가 stop() 후 `busy_thread.join(5.0)`으로 in-flight 데몬 틱을 자기 DB 활성 중 드레인 | `tests/test_notifications_async.py` | e0f96d9 |
| B2 | **방어 가드**: conftest autouse `_join_leaked_webhook_workers` — 매 테스트 후 잔존 워커 스레드 join | `tests/conftest.py` | e0f96d9 |

## 2. 근본 원인 (B — 재현·규명)

`test_worker_stop_timeout_does_not_raise`가 1.5s 느린 핸들러 워커를 `start()` → `stop(timeout=0.2)`이 join 타임아웃 → 데몬 스레드가 디스패치 중 생존 → ~1.5s 후 `record_attempt()`가 `NOTIFICATIONS_DB_FILE`을 **전역에서 호출 시점 재해석** → 그때 활성인 나중 테스트(bulk_retry)의 `isolated_db`(동일 autoincrement id=1)에 `success` 기록 → bulk_retry의 `queued` delivery가 뒤집힘. **테스트 격리 결함**(프로덕션은 단일 DB·단일 워커라 무관).

## 3. 검증 결과

- ✅ AC1~AC7 전부 PASS (**100%**)
- ✅ **flaky 재현**: 수정 전 반복 실행에서 `test_requeued_delivery_is_dispatched_by_worker` 실제 실패 캡처(`assert ... == "queued"` → `success`)
- ✅ **baseline 2/10 실패 → 수정 후 10/10 green** (363 passed)
- ✅ rate_limiter 테스트 **5.3s+ → 0.21s**, ruff 클린, CI green
- ✅ 프로덕션 코드 영향: RateLimiter 시그니처에 기본값 인자 1개 추가뿐(전역 인스턴스·API 계약·한도 정책 불변)

## 4. PDCA 메타데이터

```yaml
cycle: rate-limiter-clock-injection
phase: completed
match_rate: 100
plan: docs/archive/2026-06/rate-limiter-clock-injection/rate-limiter-clock-injection.plan.md
design: docs/archive/2026-06/rate-limiter-clock-injection/rate-limiter-clock-injection.design.md
analysis: docs/archive/2026-06/rate-limiter-clock-injection/rate-limiter-clock-injection.analysis.md
report: docs/archive/2026-06/rate-limiter-clock-injection/rate-limiter-clock-injection.report.md
duration_h: 1.2
trigger: flaky 누적 4회 (ci-and-env-standardization 이후 CI가 머지 게이트가 되며 우선순위 상승)
```

## 5. 후속 사이클 권장

| Item | 사이클 | 우선순위 |
|------|--------|---------|
| kpi_cards/ai_section/watcher 순수 로직 단위 테스트 (커버리지 사각지대) | coverage-blindspots-v1 | Medium |
| webcloring-pdf submodule 분리 + 의존성 이관 | webcloring-pdf-separation | Medium |
| R6 린트 램프 (B나머지+SIM) | R6-ruff-bugbear-sim-ramp | Medium |
| FastAPI ORJSONResponse deprecation (lock 업그레이드 시) | (의존성 업그레이드 사이클) | Low |

## 6. Lessons Learned

- **flaky는 "통과할 때까지 재시도"가 아니라 재현부터** — 반복 실행으로 실제 실패를 잡으니 traceback 한 줄(`success` vs `queued`)이 "누군가 디스패치했다"는 결정적 단서가 됐다. 추측 기반 격리 보강보다 재현이 빠르고 정확했다.
- **동적 경로 해석 + 누출 스레드 = cross-test 오염** — "테스트가 monkeypatch할 수 있게" 호출 시점에 전역 config를 읽는 설계(`_db_path()`)는 편리하지만, 그 경계를 넘어 살아남는 스레드가 있으면 **남의 테스트 DB에 쓴다**. 백그라운드 스레드를 띄우는 테스트는 반드시 자기 수명 안에서 회수해야 한다.
- **autoincrement id 충돌이 증상을 키운다** — 격리된 빈 DB들이 전부 id=1부터 시작하므로 stray write가 정확히 같은 id를 덮어썼다. 격리가 완벽하지 않을 때 동일 id 공간은 오염을 "성공적으로" 만든다.
- **clock 주입은 worker가 이미 검증한 패턴** — 같은 코드베이스의 선례(worker.py:41)를 따르니 리뷰 부담 없이 결정론 + 경계값 테스트까지 덤으로 얻었다.
- **테스트 시간 단축은 부수 효과가 아니라 신뢰도** — 5초 sleep을 없애니 "10회 반복 검증"이 현실적 비용(~2.5분)이 됐고, 그게 flaky 수정의 증명을 가능하게 했다.
