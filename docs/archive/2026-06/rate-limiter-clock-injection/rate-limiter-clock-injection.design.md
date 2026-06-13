# rate-limiter-clock-injection — Design

> **Cycle**: rate-limiter-clock-injection
> **PDCA Phase**: Design
> **Date**: 2026-06-12
> **Plan**: [[rate-limiter-clock-injection.plan]]

## Part A — RateLimiter clock 주입

### A-1 제품 (`shared/rate_limiter.py`)

```python
from collections.abc import Callable

class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: int = RATE_LIMIT_WINDOW,
                 clock: Callable[[], float] = time.time):
        ...
        self._clock = clock
```
- 6개 메서드의 `current_time = time.time()` → `self._clock()`. (worker.py:41 선례 동일 패턴)
- 전역 인스턴스 2개는 기본값 사용 — 프로덕션 diff 0.

### A-2 테스트 (`tests/test_rate_limiter.py`)

```python
class FakeClock:
    def __init__(self, start: float = 1000.0): self.t = start
    def __call__(self) -> float: return self.t
    def advance(self, sec: float) -> None: self.t += sec
```
- sleep 4건 전환: `time.sleep(1.1)` → `clock.advance(1.1)` (한계: window=1 유지, 의미 보존).
- 추가 경계 검증(보너스): 정확히 `window_seconds` 경과 시 만료(`<= cutoff`) 단언 1건.
- `import time` 사용처가 sleep뿐이면 제거.

## Part B — bulk_retry flaky 조사 절차

### B-0 Baseline (수정 전)
전체 스위트 **10회 반복** → 실패율/실패 테스트 기록 (`.pytest_tmp/flaky_baseline.log`).

### B-1 유력 가설 (사전 코드 분석, 2026-06-12)

| # | 가설 | 근거 | 검증 방법 |
|---|------|------|----------|
| H1 | **타임스탬프 동률 → 정렬/경계 비결정** | `_now_iso()` 연속 호출이 Windows 클럭 입도에서 동률 가능. `limit_caps_oldest_first`(정렬 의존), claim의 `next_attempt_at <= now`(경계 의존) | 실패 케이스의 시드 루프에서 timestamp 동률 재현 (tight loop로 `_now_iso()` 동률 빈도 측정) |
| H2 | **thread-local 연결 격리 누수** | `_store_connection._local`은 스레드별 — TestClient(anyio 워커 스레드)의 conn은 main 스레드 `reset_for_tests()`가 못 닫음. 단 cache_key에 경로 포함이라 잘못된 DB 접근은 아님 — WAL 스냅샷/파일 핸들 잔존 경로 의심 | 실패 재현 시 양 스레드 conn 상태 덤프 |
| H3 | 선행 모듈 잔여 상태 (`_schema_initialized` 등 전역 set) | reset이 전역 clear하지만 client 스레드와의 타이밍 | 축소 조합(의심 선행 모듈 + bulk_retry) 반복 |

### B-2 수정 방침 (조사 결과 분기)
- H1 확정 시: 제품 수정 — 시드/정렬 경로에 단조성 보장(타이브레이커 `id` 추가 ORDER BY, 또는 `_now_iso` 단조 보정) 중 **정렬 타이브레이커가 최소 침습**(쿼리 `ORDER BY next_attempt_at, id` 형태). 테스트엔 동률 강제 케이스 추가.
- H2/H3 확정 시: 테스트 격리 보강(fixture에서 client 스레드 conn까지 정리, 또는 `isolated_db`를 module-scoped client와 정합).
- **미재현 시**: H1 방어(타이브레이커)는 무해+이론 근거 충분이므로 적용하고, 분석 문서에 "원인 추정" 등급 명시.

### B-3 판정 (AC5)
수정 후 전체 스위트 **연속 10회 all green** (baseline과 동일 절차·동일 환경).

## 커밋 계층

| # | 커밋 | 내용 |
|---|------|------|
| 1 | `refactor(rate-limiter): clock 주입 + FakeClock 테스트 결정론화` | A-1+A-2 |
| 2 | `fix(notifications): bulk_retry flaky 원인 수정` (제목은 조사 결과 반영) | B-2 |
| 3 | `docs(pdca): ...` | 문서 |

## AC 매핑
AC1·AC2→A / AC3→B-1 / AC4→B-2 / AC5→B-3 / AC6→게이트+CI / AC7→Check.
