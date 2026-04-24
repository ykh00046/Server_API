# Archive Index - 2026년 4월

> 이 폴더는 2026년 4월에 완료된 PDCA 사이클의 문서를 보관합니다.

## 📁 아카이브 목록

### 19. Manager 고아 프로세스 방지 (manager-orphan-prevention-v1)
- **완료일**: 2026-04-24
- **상태**: ✅ 완료 (Match Rate 100%)
- **요약**: `shared/process_utils.py` 신규 — psutil snapshot-before-kill 기반 `kill_process_tree`로 `taskkill /T` snapshot race 해결. `manager.py`에 `signal.SIGINT` 핸들러 + `_setup_tray` try/except + `on_close` confirmation dialog fallback. 222 → 224 tests.
- **문서**: plan / design / analysis / report

### 18. Tool Schema Smoke Test (tool-schema-smoke-test)
- **완료일**: 2026-04-24
- **상태**: ✅ 완료 (Match Rate 100%)
- **요약**: PRODUCTION_TOOLS 7개의 Gemini FunctionDeclaration을 `_FakeClient` stub으로 offline 검증. 44 tests 추가 — ARRAY `items` 누락, TYPE_UNSPECIFIED, description 공백 등 drift 조기 감지. 178 → 222 tests.
- **문서**: plan / design / analysis / report

### 17. Custom Query Bind Parameters (custom-query-bind-params-v1)
- **완료일**: 2026-04-23
- **상태**: ✅ 완료 (Match Rate 100%)
- **요약**: `execute_custom_query(sql, params=list[str]|None, description)` 시그니처 확장 — `?` placeholder 바인딩으로 AI의 SQL literal 삽입 경로 제거. `_validate_custom_query_params` helper + system prompt rule 9 갱신 + spec 동기화. 163 → 178 tests.
- **문서**: plan / design / analysis / report

### 16. Dashboard Pages Refactor (dashboard-pages-refactor)
- **완료일**: 2026-04-23
- **상태**: ✅ 완료 (Match Rate 100%)
- **요약**: overview/batches/trends 3개 페이지를 products-refactor의 `_render_*` hybrid 패턴으로 분해 (8 helpers 추가). 대시보드 4개 페이지 모두 동일 패턴 통일(총 13 helpers).
- **문서**: plan / design / analysis / report

### 15. Security Hardening v3 (security-hardening-v3)
- **완료일**: 2026-04-23
- **상태**: ✅ 완료 (Match Rate 100%)
- **요약**: `shared.database.attach_archive_safe` helper 추출로 `DBRouter.get_connection`과 `execute_custom_query` 두 곳의 ATTACH 패턴 통일. legacy offset에 `logger.warning("[Deprecated] /records called with offset=... use cursor pagination")`. `tests/test_db_attach.py` 4 tests 추가.
- **문서**: plan / design / analysis / report

### 14. Products Page Refactor (products-refactor)
- **완료일**: 2026-04-23
- **상태**: ✅ 완료 (Match Rate 100%)
- **요약**: `dashboard/pages/products.py` 5개 `_render_*` helper 분해 + drill-down tab selectbox/chart key를 `selected_cat` 기반으로 안정화(H5 충돌 방지). `shared/ui/responsive.py`에서 dead viewport-detection chain(`detect_viewport`/`get_optimal_columns`/`responsive_grid`/wrapper 3종) 제거 — 270 → 95 lines.
- **문서**: plan / design / analysis / report

### 13. Docs Sync v1 (docs-sync)
- **완료일**: 2026-04-23
- **상태**: ✅ 완료 (Match Rate 100%)
- **요약**: 4개 spec 문서를 v8 code ground truth에 동기화. AI Architecture 70% → 100% (도구 5→7개, 모듈 분리, SSE/fallback 정책 반영). Dashboard 포트 8501→8502 통일. `critical-fixes` 사이클과 함께 수행하여 89% → 100% 달성.
- **문서**: plan / design / analysis / report

### 12. Critical Fixes (critical-fixes)
- **완료일**: 2026-04-23
- **상태**: ✅ 완료 (Match Rate 100%)
- **요약**: `GEMINI_FALLBACK_MODEL` 기본값을 preview(`gemini-3.1-flash-lite`)에서 GA(`gemini-2.5-flash-lite`)로 정렬 — preview deprecate 위험 제거 (WebFetch로 사전 검증). `dashboard/components/ai_section.py`의 brittle regex sanitizer 제거 + `unsafe_allow_html=False` 명시화.
- **문서**: plan / design / analysis / report

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

### 10. UI 현대화 (ui-modernization-streamlit-extras)
- **경로**: `ui-modernization-streamlit-extras/`
- **완료일**: 2026-04-15
- **상태**: ✅ 완료 (Match Rate 97%, iteration 0)
- **요약**: FastAPI SSE `/chat/stream` + Gemini async streaming, CSS 토큰 테마 시스템(라이트/다크/고대비 WCAG AA), streamlit-shadcn-ui 스타터 카드. 136 → 142 tests, Playwright E2E 4 시나리오 통과.
- **문서**: plan / design / analysis / report

### 11. Gemini 모델 폴백 (gemini-fallback)
- **경로**: `gemini-fallback/`
- **완료일**: 2026-04-17
- **상태**: ✅ 완료 (Match Rate 98%, iteration 0)
- **요약**: Gemini 2.5 Flash 429/503 시 3.1 Flash Lite 자동 폴백. sync/stream 양쪽 지원. RPD 20→500 확보. 149 tests pass (폴백 전용 7개 포함).
- **문서**: plan / design / analysis / report

### 12. 대시보드 사이드바 리디자인 (dashboard-sidebar-redesign)
- **경로**: `dashboard-sidebar-redesign/`
- **완료일**: 2026-04-17
- **상태**: ✅ 완료 (Match Rate 96%, iteration 0)
- **요약**: 탭 기반 UI → `st.navigation` 멀티페이지 + 사이드바 네비 + 토글 가능 우측 AI 패널. app.py 536→149줄(72% 감축), data.py 분리, 4개 페이지 파일 신규. 색상 보라-블루 → 핑크-스카이(#ec4899/#0ea5e9). segmented_control 집계 단위, xaxis category 타입 강제.
- **문서**: plan / analysis / report (design 생략 — 소급 PDCA)

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
| UI 현대화 (streamlit-extras) | 97% | 142 pass | ✅ 완료 |
| Gemini 모델 폴백 | 98% | 149 pass | ✅ 완료 |
| 대시보드 사이드바 리디자인 | 96% | 0 browser errors | ✅ 완료 (소급 PDCA) |

### 13. 대시보드 코드 품질 (dashboard-code-quality)
- **경로**: `dashboard-code-quality/`
- **완료일**: 2026-04-18
- **상태**: ✅ 완료 (Match Rate 78% → 95%, Act-1)
- **요약**: `dashboard-sidebar-redesign` 코드 리뷰(Quality Score 68/100) 후속. 인라인 style ~30+ → 6(동적만), sys.path.insert 2→1, mutable default 3→0, 미사용 key 파라미터 3→0, UI 문자열 15+ English→Korean. theme.py `_BASE_RULES` CSS 유틸리티 클래스 ~60줄 추가.
- **문서**: plan / design / analysis / report

### 14. SSE 스트리밍 최적화 (sse-streaming-optimization)
- **경로**: `sse-streaming-optimization/`
- **완료일**: 2026-04-21
- **상태**: ✅ 완료 (Match Rate 96%, iteration 0)
- **요약**: SSE /chat/stream 최적화 6건. Heartbeat(10초 코멘트), 스트림 타임아웃(120초), 클라이언트 자동 재연결(1회), 토큰 버퍼링(50ms 병합, TTFT 보장), 구조화된 에러 코드(5종+한글 매핑), tool_call 중복 허용. asyncio.wait 패턴으로 heartbeat 중 청크 유실 방지. 9개 신규 테스트 추가(22 pass).
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
| UI 현대화 (streamlit-extras) | 97% | 142 pass | ✅ 완료 |
| Gemini 모델 폴백 | 98% | 149 pass | ✅ 완료 |
| 대시보드 사이드바 리디자인 | 96% | 0 browser errors | ✅ 완료 (소급 PDCA) |
| 대시보드 코드 품질 | 95% | 149 pass | ✅ 완료 (Act-1) |
| SSE 스트리밍 최적화 | 96% | 22 pass (SSE) | ✅ 완료 |
| Critical Fixes | 100% | 7 pass | ✅ 완료 |
| Docs Sync v1 | 100% | - | ✅ 완료 |
| Products Page Refactor | 100% | 163 pass | ✅ 완료 |
| Security Hardening v3 | 100% | 163 pass (+4) | ✅ 완료 |
| Dashboard Pages Refactor | 100% | 163 pass | ✅ 완료 |
| Custom Query Bind Params | 100% | 178 pass (+15) | ✅ 완료 |
| Tool Schema Smoke Test | 100% | 222 pass (+44) | ✅ 완료 |
| Manager Orphan Prevention | 100% | 224 pass (+2) | ✅ 완료 |

---

*최종 갱신: 2026-04-24*
