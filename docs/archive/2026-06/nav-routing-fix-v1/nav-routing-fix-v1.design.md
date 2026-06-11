# nav-routing-fix-v1 — Design

> **Cycle**: nav-routing-fix-v1
> **PDCA Phase**: Design
> **Date**: 2026-06-11
> **Plan**: [[nav-routing-fix-v1.plan]] (근본 원인 소스 규명 포함 — §1 참조)

## 0. 설계 결정

**디렉터리 개명 단일 해법** — `dashboard/pages/` → `dashboard/views/`. 대안(사적 API로 `PagesManager.uses_pages_directory` 선강제)은 내부 구현 의존이라 기각. 개명은 v1 플래그 초기화 조건(`main_script_parent / "pages"` 존재 검사)을 원천 제거한다.

## 1. 변경 목록 (전수)

| # | 파일 | 변경 |
|---|------|------|
| 1 | `dashboard/pages/*.py` 5종 | `git mv` → `dashboard/views/` (내용 무변경) |
| 2 | `dashboard/app.py:5` | docstring `dashboard/pages/` → `dashboard/views/` |
| 3 | `dashboard/app.py:62-70` | `st.Page("pages/X.py")` ×5 → `"views/X.py"` (title/icon/default 불변) |
| 4 | `tests/test_webhook_admin_ui.py:359,366,371` | docstring·assert 문자열·경로를 `views/webhooks.py` 기준으로 |

`views` 명칭 충돌 검사: `webhook_admin/views.py`는 `components.webhook_admin.views`로 import — 새 디렉터리는 import 대상이 아님(파일 경로 문자열로만 참조) → 충돌 없음.

## 2. 검증 절차 (AC3/AC4 핵심)

1. **수정 전 재현은 기확보** (ui-design-overhaul-v1 Check O1, Playwright 2회).
2. 수정 후: 서버 기동(8503) → **브라우저 첫 요청을 `http://localhost:8503/batches` 딥링크로** → 풀 사이드바(로고+필터+프리셋+내비) 렌더 스크린샷 = AC3.
3. 루트 진입 → 내비 클릭으로 2개 페이지 이동 = AC4 회귀.
4. URL 불변 확인: 딥링크 주소창이 `/batches` 그대로 동작(리다이렉트/404 없음).

## 3. 커밋 계층

| # | 커밋 | 내용 |
|---|------|------|
| 1 | `fix(dashboard): pages/ -> views/ 개명으로 v1 레거시 라우팅 비활성화` | 이동 5 + app.py + tests (원자적) |
| 2 | `docs(pdca): ...` | PDCA 문서 |

## 4. AC 매핑

AC1·AC2 → §1 / AC3·AC4 → §2 / AC5·AC6 → 게이트+CI / AC7 → Check.
