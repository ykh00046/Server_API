# nav-routing-fix-v1 — Plan

> **Cycle**: nav-routing-fix-v1
> **PDCA Phase**: Plan
> **Date**: 2026-06-11
> **Project**: Production Data Hub Dashboard
> **Summary**: ui-design-overhaul-v1에서 발견된 **O1 — 콜드 세션 딥링크 시 레거시 v1 라우팅이 `st.navigation`을 우회**하는 문제를 `dashboard/pages/` 디렉터리 개명으로 근본 해소.

## 1. Background — 근본 원인 (Streamlit 1.58 소스로 규명, 2026-06-11)

증상(Playwright 재현 2회): 새 브라우저 세션이 `/batches` 등으로 직접 진입하면 **사이드바(로고/필터/프리셋) 없는 화면**이 뜬다. 페이지 본문은 렌더되지만 `app.py`가 실행되지 않아 `_filters` 세션 상태도 없다(기본값 동작). 루트 진입 후에는 정상.

메커니즘 (설치된 1.58 소스 직접 확인):

1. `runtime/pages_manager.py:58-61` — 서버에서 `PagesManager` 초기화 시 **`main_script_parent / "pages"` 디렉터리가 존재한다는 사실만으로** `uses_pages_directory = True` (v1 Multipage 유산 플래그, 클래스 속성).
2. `runtime/scriptrunner/script_runner.py:786-789` — 스크립트 실행 분기: `if PagesManager.uses_pages_directory: _mpa_v1(...)` → **매칭된 `pages/batches.py`를 직접 실행**, `app.py`(공통 코드)는 건너뜀.
3. `commands/navigation.py:327` — `st.navigation()`이 호출되어야 비로소 `uses_pages_directory = False`. 즉 **첫 요청이 루트(app.py 실행)면 이후 전부 정상, 첫 요청이 딥링크면 v1 경로**로 빠지는 콜드 스타트 경합.

→ 결론: `pages/`라는 디렉터리명 자체가 지뢰. **이름을 바꾸면 플래그가 처음부터 False**가 되어 v2(`st.navigation`)가 딥링크 포함 전부를 처리한다(`get_initial_active_script`: "We always run the main script in V2").

## 2. Goal

1. `dashboard/pages/` → **`dashboard/views/`** 개명 (git mv 5파일).
2. `app.py`의 `st.Page("pages/*.py")` 5곳 + docstring → `views/*.py`. **URL은 불변** — `url_path`는 파일명 stem에서 파생되므로 `/batches` 등 기존 북마크 그대로 동작.
3. `tests/test_webhook_admin_ui.py`의 경로 참조 3곳 동기화.
4. **콜드 딥링크 실증**: 서버 재기동 직후 첫 요청을 `/batches` 딥링크로 보내 풀 사이드바가 렌더됨을 Playwright로 확인 (수정 전 재현 → 수정 후 해소).

## 3. Non-Goals (defer)

- IA/페이지 구성·URL 체계 변경 — 없음(개명만).
- 레거시 `pages/` 흔적 정리 외 라우팅 고도화(`url_path` 명시화 등).

## 4. Scope

| 구분 | 대상 |
|---|---|
| **이동** | `dashboard/pages/{overview,trends,batches,products,webhooks}.py` → `dashboard/views/` |
| **수정** | `dashboard/app.py`(6곳), `tests/test_webhook_admin_ui.py`(3곳) |
| **불변** | 페이지 파일 내용, URL, components/, api/ |

## 5. Acceptance Criteria

| # | Criterion | 측정 |
|---|-----------|---|
| AC1 | `dashboard/pages/` 부재, `dashboard/views/` 5파일 | ls |
| AC2 | app.py `st.Page("views/...")` 5곳, `pages/` 문자열 잔재 0 | grep |
| AC3 | **콜드 딥링크 `/batches` 첫 요청에서 풀 사이드바 렌더** (서버 재기동 후 Playwright 실측) | 스크린샷 |
| AC4 | 루트 진입 + 내비 클릭 경로도 정상 (회귀) | Playwright |
| AC5 | pytest 361 green (test_webhook_admin_ui 경로 동기화 포함) | pytest |
| AC6 | ruff 클린 + CI run green | Actions |
| AC7 | gap match rate ≥ 90% | Check |

## 6. Constraints / Risks

- **URL 보존 검증 필수**: `st.Page` url_path가 파일명 stem 파생이라는 전제를 AC3/AC4 실측으로 확인(딥링크 URL이 바뀌면 북마크 파괴 — 발생 시 `url_path=` 명시 인자로 고정).
- `views`라는 이름: 기존 `webhook_admin/views.py`(모듈)와 동명이나 패키지 경로가 달라 충돌 없음 — import 충돌만 grep 확인.
- 페이지 파일은 서로 import하지 않고 `components`/`data`만 참조 → 내용 수정 0.
- 커밋: (a) 개명+app.py+tests 한 커밋(원자적 — 분리하면 중간 상태가 깨짐), (b) docs.

## 7. Out-of-band Notes

- 근본 원인 소스 근거: `pages_manager.py:58`, `script_runner.py:786`, `navigation.py:327` (1.58.0).
- 메모리 참조: [[project_ui_native_theme]](O1 기록), [[project_ci_env_standardization]]
