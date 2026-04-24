# docs-sync-v2 Design Document

> **Summary**: 문서화 lag 4건의 구체 수정 내용
>
> **Date**: 2026-04-24
> **Status**: Design

---

## 1. File-Level Changes

### 1.1 `docs/specs/system_architecture.md §5.3`

**Before** (line 113-116):
```
### 5.3 공통 모듈
`shared/` 디렉토리의 모듈은 양쪽 서버에서 공유:
- `database.py`: DBRouter, 연결 관리
- `__init__.py`: 공통 상수 (DB 경로, 컷오프 날짜 등)
```

**After**:
```
### 5.3 공통 모듈
`shared/` 디렉토리의 모듈은 양쪽 서버에서 공유:
- `database.py`: DBRouter, 연결 관리, ATTACH helper (`attach_archive_safe`)
- `__init__.py`: 공통 상수 (DB 경로, 컷오프 날짜 등)
- `process_utils.py`: `kill_process_tree` — psutil 기반 프로세스 트리 종료 (manager.py, atexit에서 사용)
- `validators.py`: 날짜 파싱, LIKE escape, ARCHIVE_DB whitelist 검증
- `cache.py`, `metrics.py`, `rate_limiter.py`, `logging_config.py`: 운영 유틸
```

### 1.2 `docs/specs/operations_manual.md` — 신규 §2.3 소절

§2.2 "Windows 부팅 시 자동 시작 (선택)" 뒤에 추가.

```markdown
### 2.3 Manager 종료 동작 (manager-orphan-prevention-v1)

**정상 종료 경로:**
- Tray 메뉴 "완전 종료" → `shared.process_utils.kill_process_tree`로 API/Dashboard/Portal 자식 프로세스 트리 모두 정리 (psutil로 descendants 사전 스냅샷 → graceful terminate → wait_procs → 강제 kill → taskkill fallback)
- 콘솔에서 `Ctrl+C` (직접 `python manager.py` 실행 시) → `signal.SIGINT` 핸들러가 main Tk thread에 `_cleanup_and_exit` schedule
- 창 X 버튼 → 트레이로 숨김 (원래 디자인). 트레이 초기화 실패 시 `messagebox.askyesno`로 종료 확인 dialog fallback

**확인 방법:**
```bash
# 종료 후 5초 뒤 포트가 free인지 검증
netstat -ano | findstr ":8000"
netstat -ano | findstr ":8502"
```

**강제 종료 시 주의:**
- 작업 관리자로 manager 프로세스를 강제 종료하면 `atexit`이 실행되지 않아 자식 프로세스가 남을 수 있음 → 다음 manager 실행 전에 `taskkill /F /IM python.exe` 또는 개별 PID 종료 필요
- 이 edge case는 후속 사이클 `manager-pid-recovery-v2` (조건부)에서 startup PID 정리로 커버 예정
```

### 1.3 `docs/specs/operations_manual.md §10` 테스트 수 갱신

실측 대상 (변경 적용 전에 먼저 수집).

**Before**:
```
| `pytest tests/ -q` | **10.52s / 133 tests** (설계 목표 <30s ✅) |
```

**After** (실측값 대체):
```
| `pytest tests/ -q --ignore=tests/test_smoke_e2e.py` | **<측정값>s / 224 tests** (2026-04-24 기준, 설계 목표 <30s ✅) |
```

측정일 뱅커(`**측정일**: 2026-04-14`)도 함께 갱신.

### 1.4 `docs/archive/2026-04/_INDEX.md` 7개 사이클 추가

**추가 대상** (일자 역순, 최신이 앞):

```markdown
### 18. Manager 고아 프로세스 방지 (manager-orphan-prevention-v1)
- **완료일**: 2026-04-24
- **상태**: ✅ 완료 (Match Rate 100%)
- **요약**: `shared/process_utils.py` 신규 — psutil 기반 `kill_process_tree`로 taskkill /T snapshot race 해결. manager.py에 SIGINT 핸들러 + tray 실패 fallback. 222 → 224 tests.
- **문서**: plan / design / analysis / report

### 17. Tool Schema Smoke Test (tool-schema-smoke-test)
- **완료일**: 2026-04-24
- **상태**: ✅ 완료 (Match Rate 100%)
- **요약**: PRODUCTION_TOOLS 7개의 Gemini FunctionDeclaration을 `_FakeClient` stub으로 offline 검증. 44 tests 추가 — ARRAY `items` 누락, TYPE_UNSPECIFIED, description 공백 등 drift 조기 감지. 178 → 222 tests.
- **문서**: plan / design / analysis / report

### 16. Custom Query Bind Parameters (custom-query-bind-params-v1)
- **완료일**: 2026-04-23
- **상태**: ✅ 완료 (Match Rate 100%)
- **요약**: `execute_custom_query(sql, params=list[str]|None, description)` 시그니처 확장 — `?` placeholder 바인딩으로 AI의 SQL literal 삽입 경로 제거. `_validate_custom_query_params` helper + system prompt rule 9 갱신 + spec 동기화. 163 → 178 tests.
- **문서**: plan / design / analysis / report

### 15. Dashboard Pages Refactor (dashboard-pages-refactor)
- **완료일**: 2026-04-23
- **상태**: ✅ 완료 (Match Rate 100%)
- **요약**: overview/batches/trends 3개 페이지를 products-refactor의 `_render_*` hybrid 패턴으로 분해 (8 helpers 추가). 대시보드 4개 페이지 모두 동일 패턴 통일(총 13 helpers).
- **문서**: plan / design / analysis / report

### 14. Security Hardening v3 (security-hardening-v3)
- **완료일**: 2026-04-23
- **상태**: ✅ 완료 (Match Rate 100%)
- **요약**: `shared.database.attach_archive_safe` helper 추출로 `DBRouter`와 `execute_custom_query` 두 곳의 ATTACH 패턴 통일. legacy offset에 `logger.warning("[Deprecated] ... use cursor pagination")`. `test_db_attach.py` 4 tests 추가.
- **문서**: plan / design / analysis / report

### 13. Products Page Refactor (products-refactor)
- **완료일**: 2026-04-23
- **상태**: ✅ 완료 (Match Rate 100%)
- **요약**: `dashboard/pages/products.py` 5개 `_render_*` helper 분해 + drill-down tab key 안정화 (`selected_cat` 기반). `shared/ui/responsive.py`에서 dead viewport-detection chain 제거 (-175 lines).
- **문서**: plan / design / analysis / report

### 12. Docs Sync v1 (docs-sync)
- **완료일**: 2026-04-23
- **상태**: ✅ 완료 (Match Rate 100%)
- **요약**: 4개 spec 문서를 v8 code ground truth에 동기화. AI Architecture 70% → 100% (도구 5→7개, 모듈 분리, SSE/fallback 정책 반영). Dashboard 포트 8501→8502 통일. 선행 `critical-fixes` 사이클과 함께 수행.
- **문서**: plan / design / analysis / report

### 11.5. Critical Fixes (critical-fixes)
- **완료일**: 2026-04-23
- **상태**: ✅ 완료 (Match Rate 100%)
- **요약**: `GEMINI_FALLBACK_MODEL` 기본값을 preview(`gemini-3.1-flash-lite`)에서 GA(`gemini-2.5-flash-lite`)로 정렬 — preview deprecate 위험 제거. `dashboard/components/ai_section.py`의 brittle regex sanitizer 제거 + `unsafe_allow_html=False` 명시.
- **문서**: plan / design / analysis / report
```

요약 표도 함께 갱신:

```markdown
| 기능 | Match Rate | 테스트 | 상태 |
|------|-----------|--------|------|
| ... (기존 항목 유지) ... |
| Critical Fixes | 100% | 7 pass | ✅ 완료 |
| Docs Sync v1 | 100% | - | ✅ 완료 |
| Products Page Refactor | 100% | - | ✅ 완료 |
| Security Hardening v3 | 100% | 163 pass | ✅ 완료 |
| Dashboard Pages Refactor | 100% | 163 pass | ✅ 완료 |
| Custom Query Bind Params | 100% | 178 pass | ✅ 완료 |
| Tool Schema Smoke Test | 100% | 222 pass (+44) | ✅ 완료 |
| Manager Orphan Prevention | 100% | 224 pass (+2) | ✅ 완료 |
```

최종 갱신일: `2026-04-21` → `2026-04-24`.

---

## 2. Test Plan

| 검증 | 명령 | 기대 |
|------|------|------|
| AC1 | `grep -n "process_utils" docs/specs/system_architecture.md` | 1건 이상 |
| AC2 | `grep -En "psutil\|SIGINT\|고아" docs/specs/operations_manual.md` | 3건 이상 |
| AC3 | 실측 pytest 시간과 _manual §10 값 일치 | manual 비교 |
| AC4 | `grep -c "manager-orphan-prevention-v1\|tool-schema-smoke-test\|custom-query-bind-params-v1\|dashboard-pages-refactor\|security-hardening-v3\|products-refactor\|critical-fixes\|docs-sync" docs/archive/2026-04/_INDEX.md` | 8 (docs-sync는 docs-sync-v2 사이클 마감 후 추가 예정이라 이번엔 포함) |
| AC5 | gap-detector rerun | ≥ 99% |

---

## 3. Rollback

각 변경이 독립 파일에 국한. 문제 시 3 commit 개별 revert.

---

## 4. Open Questions

- (해결) §10 pytest 수 — 실측 즉시 반영 (Act 단계에서 수행).
