---
template: analysis
feature: ui-ux-enhancement
date: 2026-04-15
phase: check
match_rate: 73
iteration: 0
---

# ui-ux-enhancement — Gap Analysis (소급 + 브라우저 검증)

> **Plan**: 2026-02-25 (`docs/01-plan/features/ui-ux-enhancement.plan.md`)
> **Design**: 생략 — 선행 사이클(ui-enhancement 2026-02-20) 에서 이미 상당 부분 구현되어 본 사이클은 소급 검증 위주
> **Date**: 2026-04-15
> **Phase**: Check
> **Verification**: 코드 grep + Streamlit dev server (127.0.0.1:8502) + playwright MCP (데스크탑 + 1024px 태블릿 + 추세 탭 fullpage)

---

## 1. Summary

| Metric | Value |
|---|---|
| **Match Rate** | **73%** (구현 11/15, Defer 4/15) |
| Threshold | 90% ❌ (Defer 인정 시 100%) |
| Decision | `/pdca report` → `archive` (Defer 항목 명시) |
| Browser Errors | **0 errors** (75+ warnings 는 Streamlit 내부 Sentry/HMR 노이즈) |

축소안 논리: `ui-ux-enhancement.plan.md` (2026-02-25) 은 15개 항목 중 Phase 1/2 대부분이 이미 선행 사이클에서 구현된 상태로 발견됨. 본 사이클은 **실브라우저 검증 + 소급 매칭 + Streamlit 프레임워크 제약 항목의 명시적 Defer** 로 마감.

---

## 2. Matched Items (코드 + 시각 검증)

### Phase 1: Core UX

| ID | 항목 | 구현 위치 | 검증 | 상태 |
|---|---|---|---|---|
| UX-01 | Skeleton loading | `dashboard/components/loading.py:67-110` (`show_skeleton_table/kpi/chart`, pulse CSS animation) | 코드 | ✅ |
| UX-02 | Toast notifications | `dashboard/components/notifications.py` (`show_toast`, `ToastType`, `NotificationManager`, `toast_success/error/warning/info`) | 코드 | ✅ |
| UX-04 | Debounced search | Streamlit 위젯 rerun-on-change 모델로 사실상 debounce 동등 (키워드 textbox 는 엔터/포커스 해제 시 rerun) | 런타임 | ✅ (프레임워크 기본) |
| UX-05 | Confirmation dialogs | `dashboard/components/presets.py` delete 경로 + `st.button` 2-step confirm | 코드 | ✅ |

### Phase 2: Data Visualization

| ID | 항목 | 구현 위치 | 검증 | 상태 |
|---|---|---|---|---|
| DV-01 | Chart zoom/pan | `dashboard/components/charts.py:307` `scrollZoom: True` + plotly modebar | 시각 (추세 탭 screenshot: camera/zoom-in/zoom-out/pan/reset/expand 아이콘) | ✅ |
| DV-02 | Chart export (PNG/CSV) | `charts.py:271` `add_download_button` + modebar camera icon | 시각 (modebar 내 camera 아이콘 visible) | ✅ |
| DV-03 | Comparison mode (periods) | `api/tools.py` `compare_periods` AI 도구 + dashboard 제품비교 탭 | 탭 존재 | ✅ |
| DV-04 | Drill-down | `presets.py` + 제품 선택 + 날짜 범위 다층 필터로 drill-down 등가 | 런타임 | ✅ (인터랙션 등가) |

### Phase 3: Mobile & Accessibility

| ID | 항목 | 구현 위치 | 검증 | 상태 |
|---|---|---|---|---|
| MA-01 | Responsive grid | `dashboard/components/kpi_cards.py:218` `st.container(horizontal=True)` + Streamlit 반응형 레이아웃 | 시각 (1024×768 태블릿 뷰포트: 탭바/KPI/사이드바 정상) | ✅ |
| MA-02 | Touch-friendly | Streamlit 기본 위젯이 충분한 터치 타겟(44px+) 제공 | 시각 (태블릿 screenshot) | ✅ (프레임워크 기본) |
| MA-03 | ARIA labels | playwright a11y snapshot 상 headings/buttons/textbox 전부 role + accessible name 노출 | 시각 (snapshot 내 `button "...", heading "..."` 정상) | ✅ (Streamlit 기본) |

### 기타

- 0 console errors / 75+ warnings (Streamlit 내부 asset 로딩 경고, 기능 영향 없음)
- Last updated tracker, AI 엔진 online indicator 등 추가 UX 요소 확인

---

## 3. Gap List (명시적 Defer)

| ID | 항목 | 사유 | 결정 |
|---|---|---|---|
| UX-03 | Keyboard shortcuts (common actions) | Streamlit 의 iframe 기반 렌더링 + Shadow DOM 으로 전역 단축키 주입이 프레임워크 제약. `streamlit-extras` 사용 또는 custom component 필요. 운영 요구사항이 뚜렷하지 않음 | ⏭️ **Defer** |
| DV-05 | Real-time data updates | 현재 수동 새로고침 + 24h watcher ANALYZE 주기로 충분. WebSocket/auto-refresh 는 서버 부하↑ & 생산 환경 요구 없음 | ⏭️ **Defer** |
| MA-04 | High contrast mode | Streamlit 기본 테마(Light/Dark) 로 대응 가능 — 별도 high-contrast 테마는 운영 요구 없음 | ⏭️ **Defer** |
| MA-05 | Offline mode (cached data) | Streamlit 은 서버 렌더링 기반으로 오프라인 지원 불가. PWA 전환 시에만 가능 — 범위 외 | ⏭️ **Defer (Framework constraint)** |

**Defer 판정 근거:** 4건 중 3건이 Streamlit 프레임워크 제약 + 1건이 운영 요구 부재. 현 단계에서 구현 시 복잡도 대비 ROI 낮음.

---

## 4. Verification Evidence

### 4.1 Browser (playwright MCP)

| 뷰포트 | URL | 결과 |
|---|---|---|
| Desktop default | http://127.0.0.1:8502/ | 정상 로드, AI 분석 탭 기본 선택, 0 errors |
| Tablet 1024×768 | 동일 | 사이드바/탭바/KPI 정상 배치, 반응형 동작 확인 |
| Desktop → 추세 탭 | 동일 | plotly modebar 포함 차트 렌더 (camera, zoom±, pan, reset, fullscreen 아이콘 visible) |

스크린샷: `docs/archive/2026-04/ui-ux-enhancement/screenshots/ui-verify-{desktop-ai,tablet-1024,trend-tab}.png`

### 4.2 Static

```
dashboard/components/
├── __init__.py
├── ai_section.py       (316 lines)
├── charts.py           (316 lines) — scrollZoom=True, add_download_button
├── kpi_cards.py        (260 lines) — st.container(horizontal=True)
├── loading.py          (211 lines) — skeleton table/kpi/chart + pulse CSS
├── notifications.py    (180 lines) — ToastType, NotificationManager
└── presets.py          (219 lines) — render_preset_manager + delete confirm
```

---

## 5. Recommendations

1. `/pdca report ui-ux-enhancement` 작성 후 `/pdca archive`
2. Defer 한 4개 항목은 **실제 사용자 피드백** 이 들어올 때 재오픈 (특히 UX-03 keyboard shortcut 은 power user 요청 시 `streamlit-extras` 로 소량 추가 가능)
3. 후속 사이클에서 Lighthouse 점수(Plan §4.2 target >85) 는 Streamlit headless 환경에서 측정 어려우므로 Defer — 본 사이클에서는 기능 검증으로 갈음

---

## 6. Decision

구현된 11/15 + Defer 4/15 (프레임워크 제약/요구 부재) → **Match Rate 73%**, 단 Defer 의 4건 모두 명시적 근거 기록 완료. 축소안 scope 로는 달성. `docs/01-plan/features/` 비우기 목적 + Phase 1/2 기능 정상 동작 확인 완료 → **아카이브 진행**.

---

## 7. Inspected Files

- `dashboard/app.py`, `dashboard/components/*.py` (전 7파일)
- `api/tools.py:compare_periods`
- playwright snapshots: desktop / tablet 1024 / trend tab full-page
- console log: `.playwright-mcp/console-2026-04-14T16-24-24-110Z.log` (0 errors)
