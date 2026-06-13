# rate-limiter-clock-injection — Plan

> **Cycle**: rate-limiter-clock-injection
> **PDCA Phase**: Plan
> **Date**: 2026-06-12
> **Project**: Production Data Hub API
> **Summary**: 테스트 스위트의 두 flaky 원천 제거 — **(A)** `RateLimiter`에 clock 주입으로 실시간 sleep 테스트 결정론화, **(B)** `test_notifications_bulk_retry.py` 순서 의존 간헐 실패(누적 4회)의 근본 원인 조사·해소. CI가 머지 게이트가 된 지금([[project_ci_env_standardization]]) flaky는 곧 파이프라인 신뢰도 문제다.

## 1. Background (실측, 2026-06-12)

### Part A — RateLimiter 실시간 의존
- `shared/rate_limiter.py`: 6개 메서드(`is_allowed`/`remaining`/`retry_after`/`cleanup`/`get_stats` 등) 전부 `time.time()` 직접 호출.
- `tests/test_rate_limiter.py` 4건이 실제 sleep 의존: `test_window_expiration`(1.1s), `test_partial_window_expiration`(0.5+1.6s), `test_cleanup_removes_expired_ips`(1.1s), `test_cleanup_keeps_active_ips`(1.1s) — **스위트당 ~5.3초 낭비 + 부하 걸린 러너에서 경계 타이밍 실패 위험**. `pyproject.toml` 주석도 "rate-limit 60s timing" flaky를 인정.
- 선례: `api/notifications/worker.py:41`이 이미 `clock: Callable[[], float] = time.time` 주입 패턴 사용 — 동일 패턴 적용.

### Part B — bulk_retry 순서 의존 flaky (누적 4회 관찰)
| 회 | 일자 | 실패 테스트 | 조건 |
|---|------|------------|------|
| 1 | 06-10 | `test_requeued_delivery_is_dispatched_by_worker` | 전체 스위트 (py3.12 신규 venv 첫 실행) |
| 2 | 06-10 | `test_bulk_requeue_resets_attempt_and_response_fields` | 전체 스위트 (database/ 숨김 시뮬레이션) |
| 3 | 06-10 | 동일 파일 1건 (S1 재실행) | 전체 스위트 |
| 4 | 06-11 | `test_bulk_retry_limit_caps_oldest_first` | 전체 스위트 |
- **단독/파일 단위 실행은 항상 green** (14 passed, 매회 확인) → 순서/공유 상태 의존 확정.
- 1차 배제: `_now_iso()`는 마이크로초 정밀 ISO(UTC)라 동일초 문자열 비교 경합 가능성 낮음. 유력 가설(조사 대상): module-scoped `client` fixture·`isolated_db` monkeypatch와 store thread-local 연결의 상호작용, 또는 선행 모듈이 남긴 notifications 상태.

## 2. Goal

1. **A-1**: `RateLimiter.__init__`에 `clock: Callable[[], float] = time.time` 추가, 내부 6곳 `time.time()` → `self._clock()`. 기본 동작 100% 불변(전역 인스턴스 무변경).
2. **A-2**: sleep 기반 4개 테스트를 FakeClock(수동 advance)으로 결정론화 — sleep 0초, 경계값(정확히 window 경과/직전)도 검증 가능해짐.
3. **B-1**: bulk_retry flaky **근본 원인 규명** — 실패 재현(전체 스위트 반복 실행) → 최소 재현 조합 축소(실패 seed/순서 고정) → 원인 문서화.
4. **B-2**: 원인에 따른 수정(테스트 격리 보강 또는 제품 코드 결함 수정 — 조사 결과가 결정).
5. **검증**: 전체 스위트 **연속 10회 실행 all green** (수정 전 baseline 실패율도 측정).

## 3. Non-Goals (defer)

- rate limiter를 principal 단위로 전환(auth 후속) — 알고리즘/한도 정책 불변.
- 전역 인스턴스(`chat_rate_limiter`/`api_rate_limiter`) 생성 방식 변경 — 시그니처 기본값으로 흡수.
- pytest-xdist 병렬화/순서 셔플 상시 도입 — 조사 도구로만 사용.

## 4. Scope

| 구분 | 대상 |
|---|---|
| **수정(A)** | `shared/rate_limiter.py`(clock 주입), `tests/test_rate_limiter.py`(FakeClock 4건) |
| **수정(B)** | 조사 결과에 따라: `tests/test_notifications_bulk_retry.py`/`tests/conftest.py`(격리 보강) 또는 `api/notifications/*`(결함 시) |
| **불변** | 한도 정책, API 계약, worker 동작 |

## 5. Acceptance Criteria

| # | Criterion | 측정 |
|---|-----------|---|
| AC1 | RateLimiter clock 주입, `time.time()` 직접 호출 0곳(기본값 제외) | grep + diff |
| AC2 | test_rate_limiter.py에 `time.sleep` 0건, 테스트 시간 단축 실측 | grep + 시간 |
| AC3 | bulk_retry flaky 근본 원인이 분석 문서에 재현 증거와 함께 기록 | analysis |
| AC4 | 원인 수정 적용 (테스트 격리 또는 제품 결함) | diff |
| AC5 | **전체 스위트 연속 10회 all green** (단축된 시간 기준 ~3분) | 반복 실행 로그 |
| AC6 | 기존 362 테스트 green + ruff 클린 + CI run green | pytest/Actions |
| AC7 | gap match rate ≥ 90% | Check |

## 6. Constraints / Risks

- **B 조사가 미궁일 위험**: 4/수십 회 빈도라 10회 반복으로 재현 안 될 수 있음 → 재현 강화 수단 준비(`-p no:randomly` 없는 현재 순서 고정이므로, 실패했던 정확한 전체 스위트 조합을 동일 순서로 반복 + 필요시 대상 모듈 앞에 의심 선행 모듈만 배치한 축소 조합). 그래도 미재현이면: 유력 가설 기반 격리 보강(B-2)을 적용하고 "원인 추정 + 방어 적용"으로 등급 명시(과잉 확신 금지).
- **clock 주입 시 전역 인스턴스 경로**: 기본값 `time.time` 유지로 프로덕션 무변경 — `load_auth_settings`류 런타임 조회 불필요(인스턴스 생성 시 1회 바인딩이며 테스트는 자체 인스턴스 생성).
- **FakeClock 경계값**: 슬라이딩 윈도우 비교가 `<= cutoff`(만료)라 경계 정의가 바뀌지 않도록 기존 단언 의미 보존.
- 커밋 분리([[feedback_commit_style]]): (a) A 제품+테스트, (b) B 수정, (c) docs.

## 7. Out-of-band Notes

- Part B 관찰 이력 출처: ci-and-env-standardization §8, ui-design-overhaul-v1 report §4, 본 세션 게이트 로그.
- 메모리 참조: [[project_ci_env_standardization]], [[feedback_commit_style]], [[project_pytest_tmproot_strategy]](유사 격리 이슈 선례 — thread-local conn close fixture)
