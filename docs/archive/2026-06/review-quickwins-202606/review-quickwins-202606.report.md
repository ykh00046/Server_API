# review-quickwins-202606 Completion Report

> **Summary**: 2026-06-10 전체 검토 Quick wins 4건 — 공개경로 SSOT 통일, cache 가드 의도 문서화(재검증 정정), 인덱스 도구 REQUIRED_INDEXES 통합, chat.py 죽은 코드 제거
>
> **Project**: Server_API (Production Data Hub)
> **Date**: 2026-06-10
> **Match Rate**: 100% (AC 8/8 PASS)
> **Status**: Completed

---

## 1. 변경 요약

| ID | 변경 | 파일 | 커밋 |
|----|------|------|------|
| QW-1 | rate-limit 스킵 인라인 리스트(5개, `/redoc` 누락) → `is_public_path()` 재사용. 공개경로 정의가 `shared.auth.PUBLIC_PATHS` 단일 원천으로 수렴. `/redoc`이 auth 면제와 정합되게 rate-limit도 스킵 | `api/main.py:165-167` | 92d2139 |
| QW-1t | 신규 테스트 `test_public_paths_skip_rate_limit` — PUBLIC_PATHS **전체 순회**로 SSOT 정합을 집합 단위 고정(개별 경로 하드코딩 재발 방지) | `tests/test_api_integration.py` | 92d2139 |
| QW-2 | `get_db_version`의 `id()` source-guard에 의도 주석 — **기능 변경 0**. 검토 시 "죽은 가드 → 제거" 결론이었으나 재검증에서 `test_cache.py`의 `@patch("shared.cache.DB_FILE")` 감지용 실동작 확인 → 삭제 대신 문서화로 정정 | `shared/cache.py:47-51` | 94586f5 |
| QW-3 | `create_indexes.py` 로컬 4종 dict → `db_maintenance.REQUIRED_INDEXES`(6종, 기존 "single source of truth") import. 구버전 `create_index.py`(2종, 참조처 0) 삭제 — 인덱스 구성이 스크립트별로 갈라지던 문제 해소 | `tools/create_indexes.py`, `tools/create_index.py`(삭제) | c2996cf, 92d2139* |
| QW-4 | 호출처 0인 `_get/_set_cleanup_counter` wrapper + 실존하지 않는 `__getattr__/__setattr__` 언급 주석 제거. 사용 중인 re-export(`_sessions`, `_get_session_history`)는 유지 | `api/chat.py` | 96086a5 |

\* `create_index.py` 삭제는 staging 실수로 92d2139에 선반영(커밋 메시지 기록, 최종 트리 동일 — gap 분석에서 "의도적·문서화된 편차" 분류).

## 2. 검증 결과

- ✅ AC1~AC8 모두 PASS (8/8, **100%**)
- ✅ `pytest tests/ -q` → **361 passed** (360 + 신규 1, 회귀 0)
- ✅ `ruff check .` → All checks passed
- ✅ **GitHub Actions run 27267105258 success** — 이번 사이클부터 CI가 강제 게이트로 동작한 첫 코드 변경
- ✅ grep: main.py 인라인 공개경로 0건 / `_get_cleanup_counter` 호출처 0건 / create_indexes.py 자체 인덱스 dict 0건

## 3. PDCA 메타데이터

```yaml
cycle: review-quickwins-202606
phase: completed
match_rate: 100
plan: docs/archive/2026-06/review-quickwins-202606/review-quickwins-202606.plan.md
design: docs/archive/2026-06/review-quickwins-202606/review-quickwins-202606.design.md
analysis: docs/archive/2026-06/review-quickwins-202606/review-quickwins-202606.analysis.md
report: docs/archive/2026-06/review-quickwins-202606/review-quickwins-202606.report.md
duration_h: 0.7
trigger: 프로젝트 전체 검토 (2026-06-10) Quick wins 4건
```

## 4. 후속 사이클 권장 (검토 잔여 항목)

| Item | 사이클 | 우선순위 |
|------|--------|---------|
| webcloring-pdf submodule 분리 + 의존성 이관 | webcloring-pdf-separation | Medium |
| R6 린트 램프 (B나머지+SIM) | R6-ruff-bugbear-sim-ramp | Medium |
| `run_stream` 분해 + chat/stream 폴백 정책 헬퍼 통합 | chat-stream-refactor | Medium |
| dashboard/manager/tools 순수 로직 단위 테스트 (SSE 파싱, markdown→Excel, watcher 상태전이) | coverage-blindspots-v1 | Medium |
| rate limiter clock 주입 + bulk_retry 순서 의존 flaky | rate-limiter-clock-injection | Low |

## 5. Lessons Learned

- **"죽은 코드" 판정은 테스트의 패치 방식까지 봐야 한다** — `id()` 비교가 프로덕션에선 항상 참이라도, 테스트가 `@patch`로 모듈 속성을 갈아끼우면 살아있는 가드다. 정적 추론만으로 삭제했다면 1초 TTL 내 연속 테스트에서 캐시 오염이 생겼을 것. 이런 코드는 **의도 주석이 최선의 방어**.
- **SSOT는 "있는 것"이 아니라 "참조되는 것"** — `REQUIRED_INDEXES`는 이미 "single source of truth" 주석까지 있었지만 두 스크립트가 각자 부분집합을 하드코딩하고 있었다. 정본을 만들 때 기존 중복 정의를 같은 커밋에서 수렴시키지 않으면 분열은 그대로 남는다.
- **재발 방지 테스트는 집합 단위로** — `/redoc` 한 경로를 고치는 테스트가 아니라 `PUBLIC_PATHS` 전체를 순회하는 테스트로 작성해, 향후 공개경로 추가 시에도 자동으로 정합이 검증되게 함.
- **연속 커밋은 staging 상태를 확인하고** — `git rm`으로 미리 스테이징된 삭제가 다음 `git add+commit`에 휩쓸려 들어감. 커밋 계층 분리를 의도할 때는 커밋 직전 `git status`로 인덱스를 확인할 것.
