# ui-design-overhaul-v1 — Design

> **Cycle**: ui-design-overhaul-v1
> **PDCA Phase**: Design
> **Date**: 2026-06-11
> **Plan**: [[ui-design-overhaul-v1.plan]]

## 0. 설계 원칙

1. **config.toml이 테마의 정본** — 색·폰트·radius·차트색은 전부 `[theme.*]`에서. 파이썬 코드는 plotly 전용 팔레트만 보유(Streamlit이 plotly에 테마를 강제하지 못하는 부분).
2. **CSS는 네이티브 불가 항목만** — 1.58 네이티브로 해결되는 것(카드 border, 스파크라인, badge, 아이콘, 다크 전환)에 CSS 금지. 잔여 CSS는 한 블록 ≤30줄.
3. **공개 함수 시그니처 보존** — `get_colors()`, `init_theme()`, `apply_custom_css()` 등 호출부 37곳이 의존하는 이름은 유지하되 내부를 교체(빈 함수 허용). 호출부 대량 수정 회피.
4. **고대비 모드 제거 결정** — 새 팔레트가 라이트/다크 모두 WCAG AA 충족하도록 산정하고, 모드 선택 라디오 자체를 제거(네이티브 설정 메뉴가 대체). 접근성은 팔레트 기본값으로 보장.

## 1. `.streamlit/config.toml` — 풀 테마 (정본)

```toml
[theme]
base = "light"

[theme.light]
primaryColor = "#2563eb"
backgroundColor = "#ffffff"
secondaryBackgroundColor = "#f8fafc"
textColor = "#0f172a"
linkColor = "#2563eb"
borderColor = "#e2e8f0"
showWidgetBorder = true
showSidebarBorder = true
baseRadius = "8px"
buttonRadius = "8px"
linkUnderline = false
font = "'Noto Sans KR':https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;600;700&display=swap"
baseFontSize = 14
headingFontSizes = ["28px", "22px", "18px", "16px", "14px", "12px"]
headingFontWeights = [700, 600, 600, 600, 500, 500]
codeFontSize = "13px"
chartCategoricalColors = ["#2563eb", "#0d9488", "#f59e0b", "#7c3aed", "#dc2626", "#0891b2", "#64748b"]
blueColor = "#2563eb"
greenColor = "#059669"
redColor = "#dc2626"
orangeColor = "#ea580c"
yellowColor = "#ca8a04"
violetColor = "#7c3aed"
grayColor = "#64748b"
dataframeBorderColor = "#e2e8f0"
dataframeHeaderBackgroundColor = "#f8fafc"

[theme.light.sidebar]
backgroundColor = "#f8fafc"
secondaryBackgroundColor = "#eef2f7"
borderColor = "#e2e8f0"

[theme.dark]
primaryColor = "#3b82f6"
backgroundColor = "#0f172a"
secondaryBackgroundColor = "#1e293b"
textColor = "#e2e8f0"
linkColor = "#60a5fa"
borderColor = "#334155"
showWidgetBorder = true
showSidebarBorder = true
baseRadius = "8px"
buttonRadius = "8px"
linkUnderline = false
font = "'Noto Sans KR':https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;600;700&display=swap"
baseFontSize = 14
headingFontSizes = ["28px", "22px", "18px", "16px", "14px", "12px"]
headingFontWeights = [700, 600, 600, 600, 500, 500]
codeFontSize = "13px"
chartCategoricalColors = ["#60a5fa", "#2dd4bf", "#fbbf24", "#a78bfa", "#f87171", "#22d3ee", "#94a3b8"]
blueColor = "#60a5fa"
greenColor = "#34d399"
redColor = "#f87171"
orangeColor = "#fb923c"
yellowColor = "#facc15"
violetColor = "#a78bfa"
grayColor = "#94a3b8"
dataframeBorderColor = "#334155"
dataframeHeaderBackgroundColor = "#1e293b"

[theme.dark.sidebar]
backgroundColor = "#0b1220"
secondaryBackgroundColor = "#1e293b"
borderColor = "#334155"
```

- 대비 검증: light `#0f172a`/`#ffffff` ≈ 17:1, dark `#e2e8f0`/`#0f172a` ≈ 13:1 — AA(4.5:1) 충족. primary 위 흰 텍스트: `#2563eb` ≈ 5.2:1 충족.
- `[theme.light]`+`[theme.dark]` 동시 정의 → **설정 메뉴에 라이트/다크 토글 자동 노출** (custom 라디오 대체 근거). Playwright 실측으로 System/Light/Dark 라디오 노출 확인(2026-06-11).

> **구현 중 확정(2026-06-11, 기동 로그 실측)**: Streamlit 1.58에서 `showSidebarBorder`/`baseFontSize`/`chartCategoricalColors` 3개 키는 `[theme.light]`/`[theme.dark]` 변형 섹션에서 "not a valid config option" — **top-level `[theme]` 전용**. 위 TOML에서 해당 3키는 `[theme]`로 이동(다크 전용 chartCategoricalColors는 포기 — plotly 차트는 어차피 python 팔레트 사용).

## 2. `shared/ui/theme.py` 슬림화 (351 → ~110줄)

**제거**: `TOKENS_LIGHT/DARK/HIGH_CONTRAST`(3×~25줄), `_BASE_RULES` 165줄, `ThemeMode`의 high-contrast, `render_theme_toggle()`의 라디오 본문.

**유지/교체**:

```python
CHART_COLORS = {
    "light": {"chart_template": "plotly_white",
              "primary": "#2563eb", "secondary": "#0d9488", "accent": "#f59e0b"},
    "dark":  {"chart_template": "plotly_dark",
              "primary": "#60a5fa", "secondary": "#2dd4bf", "accent": "#fbbf24"},
}
CHART_SERIES_COLORS = ["#2563eb", "#0d9488", "#f59e0b", "#7c3aed",
                       "#dc2626", "#0891b2", "#64748b", "#60a5fa",
                       "#2dd4bf", "#94a3b8"]

def get_theme():        # st.context.theme.base 단일 소스
def get_colors():       # CHART_COLORS[get_theme()]
def init_theme():       # 잔여 세션키 정리만 (no-op에 가깝게)
def render_theme_toggle():  # 라디오 제거 → 설정 메뉴 안내 caption 1줄, False 반환(시그니처 보존)
def apply_dark_mode_css():  # 기존 no-op 유지
def apply_custom_css():     # 잔여 CSS 1블록만 주입 (§2.1)
```

### 2.1 잔여 CSS (네이티브 불가 항목만, ≤30줄)

| 항목 | 사유 |
|------|------|
| AI 스타터 카드 버튼 `min-height:120px; text-align:left; white-space:pre-wrap` | 버튼 높이/멀티라인은 네이티브 미지원 — `st.html` + `.st-key-*` 셀렉터 방식(공식 권장 fallback)으로 전환 |
| (그 외 전부 삭제) | 채팅 말풍선 테두리/표 그라데이션 헤더/KPI 카드/사이드바 로고 CSS는 네이티브 대체(§3~§5) |

## 3. KPI 카드 — `st.metric` 네이티브화 (`kpi_cards.py`)

```python
with st.container(horizontal=True):
    st.metric("총 생산량", _format_number(total), delta=mom_str, border=True,
              chart_data=sparkline_data, chart_type="line")
    st.metric("배치 수", f"{n:,}", border=True,
              chart_data=batch_sparkline, chart_type="bar")
    st.metric("활성 제품", str(active), border=True)
    st.metric("평균 배치 크기", f"{avg:,}", border=True,
              chart_data=top_product_sparkline, chart_type="line")
```

- `calculate_kpis`/`get_sparkline_*` 순수 로직은 **불변** (후속 테스트 사이클 대상).
- `_render_sparkline_bars`(CSS 스파크라인)와 HTML 카드 빌더 삭제. `colors` 파라미터는 호환 위해 받되 미사용 처리 또는 호출부 동시 정리(전파 커밋에서).
- `st.container(horizontal=True)`가 `st.columns(4)`보다 반응형 우수 — 좁은 화면에서 자동 wrap.

## 4. 아이콘 매핑 (이모지 → Material)

| 위치 | 현재 | 변경 |
|------|------|------|
| page_icon | 🏭 | `:material/factory:` |
| nav 종합 현황 | 📊 | `:material/dashboard:` |
| nav 생산 추세 | 📈 | `:material/trending_up:` |
| nav 배치 내역 | 📋 | `:material/list_alt:` |
| nav 제품별 분석 | 📦 | `:material/inventory_2:` |
| nav Webhook 관리 | 🔔 | `:material/notifications:` |
| 사이드바 검색 필터 | 🔍 | `:material/filter_list:` (헤더 텍스트 아이콘) |
| 새로고침 버튼 | 🔄 | `icon=":material/refresh:"` |
| 에러/경고 배너 | 🚨 | `st.error(..., icon=":material/error:")` |
| KPI 아이콘 박스 | 📦🧪🏷️📏 | st.metric 전환으로 자체 소멸 |

pages/components 내 잔여 이모지는 동일 원칙(상태=Status 계열, 데이터=Data 계열)으로 교체. 단 **사용자 노출 데이터 문자열**(AI 응답 등)은 건드리지 않음.

## 5. 전파 — unsafe_allow_html 18곳 처리표

| 위치 | 현재 | 대체 |
|------|------|------|
| app.py 사이드바 로고 | HTML div 2단 | `st.markdown("### :material/factory: 생산 데이터 허브")` + `st.caption("Production Data Hub")` |
| kpi_cards.py 카드 4종 | HTML 문자열 | §3 st.metric |
| ai_section 그라데이션 헤더 | `.bkit-ai-header` | `st.title`+`st.caption` (그라데이션 텍스트 제거 — 절제 원칙) |
| ai_section 모델 태그 헤더 | `.bkit-gradient-header` | `st.caption` + `st.badge`(모델명) |
| zero-state(대/소) | `.bkit-zero-state` | `st.container(horizontal_alignment="center")` + Material 아이콘 + `st.caption` |
| hint 배지 | `.bkit-hint-badge` | `st.badge` 또는 `:blue-badge[...]` |
| 채팅 말풍선 스타일 | CSS 전역 | 삭제 — `st.chat_message` 기본 + config 테마로 충분 |
| markdown 표 그라데이션 헤더 | CSS 전역 | 삭제 — `dataframeHeaderBackgroundColor`/기본 표 스타일 |
| 상태 점/뱃지류 (notifications, webhook_admin) | HTML span | `st.badge(color=...)` / `:green-badge[...]` |
| loading.py 스켈레톤 | (확인 후) 네이티브 `st.spinner`/`st.skeleton` 가능 시 교체, 불가 시 잔여 허용 |

잔여 허용 한도 5곳 — 구현 중 네이티브 대체가 과도한 왜곡을 만들면 잔여로 남기고 사유 주석.

## 6. 시각 검증 (AC9)

1. QA 전용 포트로 기동(운영 8502와 충돌 회피): `python -m streamlit run dashboard/app.py --server.port 8503 --server.headless true` (백그라운드).
2. Playwright MCP: `http://localhost:8503` 접속 → 5페이지 순회 스크린샷(라이트) → 설정 메뉴 다크 전환(또는 `?embed_options=dark_theme` / config base 임시 변경) → 5페이지 재캡처.
3. 검수 체크: 핑크 잔재 0(스크린샷 + `grep -i 'ec4899|f472b6|0ea5e9|38bdf8|f9a8d4|7dd3fc|fda4af|bae6fd|fce7f3|e0f2fe|fdf2f8|f0f9ff'` 0건), 다크 모드 차트 가독성, KPI 스파크라인 렌더, 한글 폰트 적용.
4. 스크린샷은 `docs/archive` 외부 임시 폴더(.playwright-mcp/) — 커밋하지 않음(분석 문서에 결과 요약만).

## 7. 구현 순서 (커밋 계층)

| # | 커밋 | 내용 | 게이트 |
|---|------|------|--------|
| 1 | `feat(ui): config.toml 풀 테마(블루/슬레이트 light+dark) + theme.py 슬림화` | §1+§2 | pytest+ruff |
| 2 | `feat(ui): KPI 카드 st.metric 네이티브화 (border+sparkline)` | §3 + overview 호출부 | pytest+ruff |
| 3 | `feat(ui): 내비/사이드바 Material 아이콘 + 로고 네이티브화` | §4 + app.py §5 일부 | pytest+ruff |
| 4 | `feat(ui): pages/components 팔레트 전파 + unsafe_allow_html 축소` | §5 잔여 (ai_section, webhook_admin, notifications, loading, pages) | pytest+ruff |
| 5 | (검증) Playwright 스크린샷 10장 + 수정 발견분 | §6 | AC9 |
| 6 | `docs(pdca): ...` | PDCA 문서 | CI green |

## 8. AC 매핑

AC1→§1 / AC2→§2 / AC3→§5+§6.3 grep / AC4→§5 / AC5→§3+§6 / AC6→§4 / AC7·AC8→커밋별 게이트 / AC9→§6 / AC10→Check.

## 9. 리스크 대응

- `test_webhook_admin_ui`의 app.py 소스 검사: §4에서 `st.Page("pages/webhooks.py", ...)` 문자열 보존(아이콘 인자만 변경).
- `render_theme_toggle` 시그니처 보존으로 호출부(app.py) 변경 최소 — 단 app.py에서 호출 자체를 제거하고 함수는 deprecated 잔류(다른 호출부 없음 확인 후).
- plotly 차트가 `get_colors()["chart_template"]` 사용 — high-contrast 키 제거로 KeyError 위험 → `get_theme()`이 light/dark만 반환하도록 보장.
- Noto Sans KR CDN 실패 시: config `font` 폴백은 Streamlit이 sans-serif로 처리 — 기존 `_BASE_RULES`의 `@import`+`!important`보다 오히려 안전.
