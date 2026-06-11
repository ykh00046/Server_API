# ui-design-overhaul-v1 — Plan

> **Cycle**: ui-design-overhaul-v1
> **PDCA Phase**: Plan
> **Date**: 2026-06-11
> **Project**: Production Data Hub Dashboard
> **Summary**: 대시보드 UI/디자인 대폭 개선 — Pink/Sky 커스텀 CSS 체제를 **산업용 블루/슬레이트 팔레트 + Streamlit 네이티브 테마(config.toml-first)** 로 전환. 커스텀 CSS 165줄을 최소로 줄이고 이모지를 Material 아이콘으로 교체.

## 1. Background

2026-06-11 사용자 결정(AskUserQuestion): **① 산업용 블루/슬레이트 팔레트, ② 네이티브 우선 전환**.

현재 상태 실측 (Streamlit **1.58.0** — 풀 테마 기능 지원 버전):

| 항목 | 현재 | 문제 |
|------|------|------|
| 팔레트 | Pink(#ec4899)/Sky(#0ea5e9) + 그라데이션 다수 | 생산 도메인과 부조화, 그라데이션 남용 |
| `.streamlit/config.toml` | 6줄 (light 단일) | 차트색/폰트/시맨틱색/다크/사이드바 테마 전부 미활용 |
| `shared/ui/theme.py` | 351줄 — CSS 토큰 3모드 + `_BASE_RULES` 165줄 주입 | 공식 가이드가 경고하는 custom CSS 의존(업데이트 취약), `!important` 다수 |
| `unsafe_allow_html=True` | dashboard+shared/ui에 **18곳** | KPI 카드·사이드바 로고·zero-state 등 HTML 문자열 빌드 |
| 아이콘 | 이모지(🏭📊🧪📦…) | `:material/*:` 미사용 |
| 다크 모드 | 세션 라디오(auto/light/dark/high-contrast) + CSS 토큰 수동 주입 | config.toml `[theme.light]/[theme.dark]`로 네이티브 전환 가능 |
| 색상 결합 | 코드 내 hex/팔레트 참조 **37곳** | 팔레트 교체 시 전수 추적 필요 |

## 2. Goal

1. **풀 네이티브 테마** — `.streamlit/config.toml`에 `[theme.light]`/`[theme.dark]` 완전 정의: 블루/슬레이트 팔레트, Noto Sans KR(Google Fonts), heading/sizing, `baseRadius`, 시맨틱 색(red/green/...), `chartCategoricalColors`, dataframe 스타일, `[theme.*.sidebar]`. 다크 전환은 네이티브 설정 메뉴로.
2. **theme.py 대축소** — CSS 토큰 3모드 + `_BASE_RULES` 제거, 차트 팔레트(plotly용 블루/틸 계열)와 최소 잔여 CSS(네이티브로 불가능한 것만)로 슬림화. 목표 351줄 → **~120줄 이하**.
3. **KPI 카드 네이티브화** — HTML 문자열 카드 → `st.metric(border=True)` 계열(스파크라인은 1.58 네이티브 지원 범위 내에서 — Design에서 확정).
4. **아이콘 현대화** — 내비게이션/버튼/헤더 이모지 → `:material/*:` 일괄 교체.
5. **차트 팔레트 교체** — plotly 차트 색을 블루→틸→앰버 계열로(`CHART_SERIES_COLORS` 갱신 + config `chartCategoricalColors` 정합).
6. **unsafe_allow_html 축소** — 18곳 → 핵심 잔여(네이티브 대체 불가)만. 목표 **5곳 이하**.
7. **회귀 0** — 기존 361 테스트 green + CI green. 특히 `test_webhook_admin_ui.py`의 소스 텍스트 검사(app.py의 pages 선언 등) 보존.
8. **시각 검증** — 로컬 기동 + Playwright 스크린샷(라이트/다크 × 주요 페이지)으로 before/after 확보.

## 3. Non-Goals (defer)

- **정보 구조(IA)/페이지 구성 변경** — 5페이지 구조(종합현황/추세/배치/제품/Webhook)와 사이드바 필터 동작은 불변. 시각 레이어만 교체.
- **streamlit-shadcn-ui 의존 확대/제거** — 현 사용처 유지(별도 사이클).
- **고대비(high-contrast) 모드 고도화** — 유지 여부와 방식은 Design에서 결정하되, WCAG 대비는 새 팔레트 자체가 AA를 충족하도록 설계.
- **ai_section.py 기능 변경** — SSE/Excel 로직 불변, 스타일만.
- **모바일 전용 최적화** — responsive.py 현 수준 유지.

## 4. Dependencies

| 종류 | 항목 | 상태 |
|------|------|------|
| Streamlit | 1.58.0 (lock 고정) — 풀 테마/badge/Material 아이콘 지원 | ✅ |
| 폰트 | Noto Sans KR via Google Fonts (config.toml `font=` URL 방식) | 외부 CDN — 내부망 차단 시 fallback sans-serif |
| 시각 검증 | Playwright MCP + 로컬 streamlit 기동 | 세션 취약([[feedback_playwright_mcp]]) — 재시작 전제 |
| 신규 패키지 | — | **0** |

## 5. Scope

| 구분 | 대상 |
|---|---|
| **수정(핵심)** | `.streamlit/config.toml`, `shared/ui/theme.py`, `dashboard/components/kpi_cards.py`, `dashboard/app.py`(아이콘/로고/사이드바) |
| **수정(전파)** | `dashboard/components/`(ai_section, charts, layout, loading, notifications, presets, webhook_admin/views), `dashboard/pages/` 5종, `shared/ui/responsive.py`(색 참조 시) |
| **불변** | `dashboard/data.py`, api/, shared/(ui 외), tests/ 기존 단언이 깨지지 않는 범위 |
| **제외** | webcloring-pdf, manager.py GUI(customtkinter — 별도 도메인) |

## 6. Functional Requirements

| ID | 요구사항 | 우선순위 |
|----|---------|---------|
| FR-01 | config.toml에 light+dark 풀 테마 정의, 네이티브 설정 메뉴로 모드 전환 가능 | High |
| FR-02 | 모든 페이지/차트/카드가 블루/슬레이트 팔레트로 일관 렌더 (핑크 잔재 0) | High |
| FR-03 | KPI 카드 4종이 네이티브 컴포넌트로 렌더, 라이트/다크 모두 정상 | High |
| FR-04 | 내비게이션·주요 버튼·상태 표시가 Material 아이콘 사용 | Medium |
| FR-05 | 다크 모드에서 차트(plotly)가 다크 템플릿+새 팔레트로 렌더 | High |
| FR-06 | 한글 타이포(Noto Sans KR) 적용, CDN 실패 시 sans-serif 폴백 | Medium |
| FR-07 | AI 채팅 영역(말풍선/스타터 카드) 새 팔레트 정합 | Medium |

## 7. Non-Functional Requirements

| 범주 | 기준 | 측정 |
|------|------|------|
| 유지보수성 | unsafe_allow_html ≤ 5곳, theme.py ≤ 120줄 | grep/wc |
| 접근성 | 본문 텍스트 대비 WCAG AA(4.5:1) — 라이트/다크 모두 | 팔레트 산정 |
| 회귀 | 361 테스트 green + CI green | pytest/Actions |
| 시각 품질 | 주요 5페이지 × 라이트/다크 스크린샷 검수 통과 | Playwright |

## 8. Acceptance Criteria

| # | Criterion | 측정 |
|---|-----------|---|
| AC1 | config.toml `[theme.light]`+`[theme.dark]` 풀 정의(차트색·시맨틱색·사이드바·폰트·radius 포함) | 파일 |
| AC2 | theme.py ≤ 120줄, `_BASE_RULES` 165줄 블록 제거, CSS 토큰 3모드 제거 | wc/diff |
| AC3 | dashboard+shared/ui에서 `ec4899|f472b6|0ea5e9|38bdf8` 등 핑크/스카이 hex 잔재 0건 | grep |
| AC4 | unsafe_allow_html ≤ 5곳 (현 18) | grep |
| AC5 | KPI 카드가 st.metric 기반 + border, 라이트/다크 스크린샷 정상 | 코드+스크린샷 |
| AC6 | app.py 내비 5페이지 + 사이드바 버튼이 Material 아이콘 | 코드 |
| AC7 | pytest 361 green (특히 test_webhook_admin_ui 소스 검사 유지) | pytest |
| AC8 | ruff 클린 + CI run green | Actions |
| AC9 | 주요 5페이지 × 라이트/다크 = 10장 스크린샷 확보, 핑크 잔재/대비 문제 0 | Playwright |
| AC10 | gap match rate ≥ 90% | Check |

## 9. Constraints / Risks

- **test_webhook_admin_ui 소스 텍스트 검사**: `dashboard/app.py`에 `pages/webhooks.py` 선언이 있는지 텍스트로 검사함 — st.Page 선언부 수정 시 경로 문자열 보존 필수.
- **고대비 모드 사용자**: 기존 라디오(고대비 포함)를 제거하면 접근성 기능 후퇴. → Design에서 "유지(최소 CSS)" vs "제거+팔레트 자체 AA" 결정.
- **Google Fonts CDN**: 내부망(192.168.200.107) 클라이언트가 외부 CDN 차단이면 폰트 미적용 — config `font=` 폴백 체인으로 무해, 자체 호스팅(fontFaces)은 defer.
- **Playwright MCP 취약성**([[feedback_playwright_mcp]]): 세션 사망 시 재시작. 스크린샷은 Do 후반 1회 배치로.
- **18곳 unsafe_allow_html 일괄 제거의 회귀 위험**: 페이지별 점진 커밋([[feedback_commit_style]]) — (a) config.toml+theme.py 코어, (b) KPI/overview, (c) 나머지 pages, (d) ai_section+webhook_admin, (e) 스크린샷 검증.
- **차트 색상 37곳 결합**: `get_colors()`/`CHART_SERIES_COLORS` 경유가 대부분이라 정의부 교체로 전파 — 직접 hex 박힌 곳만 개별 수정(grep 전수).

## 10. Out-of-band Notes

- 사용자 결정 기록: 팔레트 = 산업용 블루(#2563eb)/슬레이트 + 틸(#0d9488) 액센트, 전략 = 네이티브 우선.
- 후속 후보: `coverage-blindspots-v1`(이번에 만지는 dashboard 순수 로직 테스트), 자체 폰트 호스팅(fontFaces).
- 메모리 참조: [[project_ci_env_standardization]](CI green 머지 조건), [[feedback_playwright_mcp]], [[feedback_commit_style]], [[feedback_powershell_text_mangling]](비ASCII 파일은 Edit/Write로)
