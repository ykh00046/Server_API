# Archive Index - 2026년 4월

> 이 폴더는 2026년 4월에 완료된 PDCA 사이클의 문서를 보관합니다.

## 📁 아카이브 목록

### 1. 보안·테스트 개선 (security-and-test-improvement)
- **경로**: `security-and-test-improvement/`
- **완료일**: 2026-04-14
- **상태**: ✅ 완료 (Match Rate 93%)
- **요약**: Top 5 이슈(.env, API 통합 테스트, 세션 IP 격리, custom query 경로 검증, chat.py 모듈 분리) 해소. 128 tests pass.
- **문서**: plan / design / analysis / report

### 3. SQL 검증 테스트 + 멀티턴 챗 (sql-tests-and-multiturn-chat)
- **경로**: `sql-tests-and-multiturn-chat/`
- **완료일**: 2026-02-13 (작성) / 2026-04-14 (아카이브)
- **상태**: ✅ 완료 (Match Rate 97%)
- **요약**: SQL injection 방어 단위 테스트 + Gemini 멀티턴 세션. 부모 사이클(security-and-test-improvement) 의 기반이 된 피처.
- **문서**: plan / design / analysis / report

### 5. API 정합성 + 스모크 (server-api-consistency-and-smoke)
- **경로**: `server-api-consistency-and-smoke/`
- **완료일**: 2026-04-14 (소급), 원 작업 2026-03-31
- **상태**: ✅ 완료 (Match Rate 100%, iteration 0)
- **요약**: README/ops manual 정합성, `requirements-smoke.txt`, `tools/smoke_api.sh`, 스모크 검증 리포트. Design 없는 doc-중심 피처라 소급 Check 로 마감.
- **문서**: plan / analysis / report (design 생략)
- **별도 산출물**: `docs/04-report/server-api-smoke-2026-03-31.report.md` (heartbeat 검증 로그, 의도적으로 flat 유지)

### 9. UI/UX 개선 (ui-ux-enhancement)
- **경로**: `ui-ux-enhancement/` (+ `screenshots/`)
- **완료일**: 2026-04-15
- **상태**: ✅ 완료 (Match Rate 73%, 구현 11/15 + Defer 4/15, iteration 0)
- **요약**: 2026-02-25 plan 의 15개 항목 중 11개가 선행 사이클에서 이미 구현됨 (skeleton, toast, zoom/pan, export, responsive 등). playwright MCP 로 데스크탑 + 1024×768 태블릿 + 추세 탭 fullpage 렌더링 검증 (0 errors). 4개 항목(UX-03 keyboard shortcut, DV-05 real-time, MA-04 high contrast, MA-05 offline) 은 Streamlit 프레임워크 제약 또는 운영 요구 부재로 명시적 Defer.
- **문서**: plan / design / analysis / report + screenshots (3장)
- **의의**: `docs/01-plan/features/` + `docs/02-design/features/` + `docs/03-analysis/` **모두 0건** 달성 — 2026-04 아카이브 정리 사이클 전체 완료

### 8. DB 성능 최적화 (db-performance-optimization)
- **경로**: `db-performance-optimization/`
- **완료일**: 2026-04-15
- **상태**: ✅ 완료 (Match Rate 92%, 축소안 scope 100%, iteration 0)
- **요약**: Phase A 합의 축소안 — `shared/metrics.py` PerformanceMonitor + `/metrics/performance` + `/metrics/cache` 엔드포인트 + api_cache 계측. 베이스라인 측정(avg 0.37–1.47ms, p99 3.5–14.5ms, hit 90%)으로 Phase B(Parallel/SWR/SmartInvalidation) 불필요 확정. 선행 사이클(v8 WAL/인덱스, performance-and-filter-enhancement P1/P2/S1)과 중첩 확인 후 잔여 관측성 격차만 구현.
- **문서**: plan / design / analysis / report

### 7. 성능 + 필터 개선 (performance-and-filter-enhancement)
- **경로**: `performance-and-filter-enhancement/`
- **완료일**: 2026-04-14 (소급), 원 작업 2026-02-13
- **상태**: ✅ 완료 (Match Rate 100%, iteration 0)
- **요약**: P1/P2 집계 엔드포인트 캐싱, S1 Slow Query 500ms 임계값 WARNING, F1 lot_number 필터, F2 min/max_quantity 필터.
- **문서**: plan / design / analysis / report

### 6. Server API 인수 (server-api-intake)
- **경로**: `server-api-intake/`
- **완료일**: 2026-04-14 (소급), 원 plan 2026-03-31
- **상태**: ✅ 완료 (Match Rate 100%, iteration 0)
- **요약**: 문서 체계 확인 + 인수용 plan 자체가 deliverable + README/changelog 링크 정합화. 본 사이클에서 README 아카이브 링크 재지정으로 I3 재확정.
- **문서**: plan / analysis (design/report 생략 — doc-only 피처)

### 4. Tracing + Validation + RateLimit (tracing-validation-ratelimit)
- **경로**: `tracing-validation-ratelimit/`
- **완료일**: 2026-04-14 (Act-1), 설계 원본 2026-02-13
- **상태**: ✅ 완료 (Match Rate 88% → 97%, iteration 1)
- **요약**: Rate Limiter 모듈 + Input Validation + Request Tracing. 후속 보안 사이클에서 대부분 incidentally 해소되어 있었고 G1/G2 (min_length, max_length drift) 만 1회 iteration 으로 마감.
- **문서**: plan / design / analysis / report

### 2. 보안·관측성 후속 (security-followup-observability)
- **경로**: `security-followup-observability/`
- **완료일**: 2026-04-14
- **상태**: ✅ 완료 (Match Rate 95%, iteration 0)
- **부모**: security-and-test-improvement (Deferred G3/G5/G6/G7 마감)
- **요약**: `/healthz/ai` sessions 블록, 4개 통합 테스트, `scripts/perf_smoke.py`, whitelist import warning. 128 → 133 tests.
- **문서**: plan / design / analysis / report

---

## 📊 요약

| 기능 | Match Rate | 테스트 | 상태 |
|------|-----------|--------|------|
| 보안·테스트 개선 | 93% | 128 pass | ✅ 완료 |
| 보안·관측성 후속 | 95% | 133 pass | ✅ 완료 |
| SQL 테스트 + 멀티턴 챗 | 97% | - | ✅ 완료 (소급 아카이브) |
| Tracing + Validation + RateLimit | 97% | 134 pass | ✅ 완료 (Act-1) |
| API 정합성 + 스모크 | 100% | 134 pass | ✅ 완료 (소급) |
| Server API 인수 | 100% | - | ✅ 완료 (소급) |
| 성능 + 필터 개선 | 100% | 134 pass | ✅ 완료 (소급) |
| DB 성능 최적화 | 92% | 136 pass | ✅ 완료 (축소안) |
| UI/UX 개선 | 73% | 0 browser errors | ✅ 완료 (11 impl + 4 Defer) |

---

*생성일: 2026-04-14*
