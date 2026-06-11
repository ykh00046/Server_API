# nav-routing-fix-v1 Completion Report

> **Summary**: 콜드 세션 딥링크가 사이드바 없는 화면으로 빠지던 O1 버그를 `dashboard/pages/` → `views/` 개명으로 근본 해소 — 원인은 Streamlit 1.58의 v1 유산 플래그(`uses_pages_directory`)가 디렉터리 존재만으로 활성화되는 것
>
> **Project**: Server_API (Production Data Hub)
> **Date**: 2026-06-11
> **Match Rate**: 100% (AC 7/7 PASS)
> **Status**: Completed

---

## 1. 변경 요약

| ID | 변경 | 파일 | 커밋 |
|----|------|------|------|
| R1 | `dashboard/pages/` 5파일 → `dashboard/views/` (git mv, 내용 무변경) + 잔존 `__pycache__` 제거 | views/{overview,trends,batches,products,webhooks}.py | 7ee7514 |
| R2 | `st.Page` 경로 5곳 + docstring(재발 방지 경고 주석 포함) | `dashboard/app.py` | 7ee7514 |
| R3 | 테스트 경로 동기화 + **신규 재발 가드** `test_no_legacy_pages_directory` (빈 pages/ 디렉터리도 버그 재발) | `tests/test_webhook_admin_ui.py` | 7ee7514 |

## 2. 근본 원인 (1.58 소스 직접 규명)

1. `pages_manager.py:58-61` — `main_script_parent/"pages"` **존재만으로** `uses_pages_directory=True` (클래스 속성, 프로세스 전역).
2. `script_runner.py:786` — True면 `_mpa_v1()` 분기: 매칭 파일 직접 실행, app.py(사이드바/필터/`st.navigation`) 건너뜀.
3. `navigation.py:327` — `st.navigation()` 호출 시점에야 False → **첫 요청이 딥링크면 v1로 빠지는 콜드 스타트 경합**.

## 3. 검증 결과

- ✅ AC1~AC7 전부 PASS (**100%**)
- ✅ **콜드 딥링크 실측**: 서버 재기동 → 첫 요청 `/batches` → 풀 사이드바 렌더(수정 전 동일 절차에서 2회 재현됐던 버그 해소). 클릭 경로 회귀 + URL 전수 불변(`/batches` 등 북마크 보존)
- ✅ pytest **362 passed** (+1 재발 가드), ruff 클린, **CI run 27355978686 success** (1m3s)

## 4. PDCA 메타데이터

```yaml
cycle: nav-routing-fix-v1
phase: completed
match_rate: 100
plan: docs/archive/2026-06/nav-routing-fix-v1/nav-routing-fix-v1.plan.md
design: docs/archive/2026-06/nav-routing-fix-v1/nav-routing-fix-v1.design.md
analysis: docs/archive/2026-06/nav-routing-fix-v1/nav-routing-fix-v1.analysis.md
report: docs/archive/2026-06/nav-routing-fix-v1/nav-routing-fix-v1.report.md
duration_h: 0.6
trigger: ui-design-overhaul-v1 Check 부수 관찰 O1 (High)
```

## 5. 후속 사이클 권장

| Item | 사이클 | 우선순위 |
|------|--------|---------|
| bulk_retry 순서 의존 flaky(누적 4회) + rate limiter clock 주입 | rate-limiter-clock-injection | Medium↑ |
| kpi_cards/ai_section/watcher 순수 로직 테스트 | coverage-blindspots-v1 | Medium |
| webcloring-pdf 분리, R6 린트 램프 | (기존 예고) | Medium |
| **운영 반영**: Manager에서 대시보드 재시작(새 테마+라우팅 픽스 동시 적용) | — | 즉시 가능 |

## 6. Lessons Learned

- **프레임워크의 "디렉터리명 규약"은 숨은 전역 스위치다** — `pages/`라는 이름 자체가 v1 라우팅을 켰다. 규약 이름과 우연히 겹치는 디렉터리는 명시적 기능 사용(st.navigation)과 경합할 수 있다.
- **git mv 후 `__pycache__` 잔존 확인 필수** — 트래킹 파일만 옮기면 빈 디렉터리(pycache)가 남아 "존재 검사" 기반 동작이 그대로 재발한다. 디렉터리 존재가 의미를 갖는 픽스는 **존재 자체를 테스트로 가드**(`test_no_legacy_pages_directory`).
- **버그 증상의 역추적 지표**: "필터 적용된 0건"과 "필터 없는 5,000건"의 차이가 app.py 실행 여부를 즉시 판별해 줬다 — 상태 의존 화면은 그 자체로 진단 신호다.
