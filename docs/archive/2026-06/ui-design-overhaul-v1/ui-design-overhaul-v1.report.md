# ui-design-overhaul-v1 Completion Report

> **Summary**: 대시보드 UI/디자인 대폭 개선 — Pink/Sky 커스텀 CSS 체제(351줄 theme.py + 18곳 HTML 주입)를 산업용 블루/슬레이트 팔레트 + Streamlit 네이티브 테마(config.toml SSOT)로 전면 전환
>
> **Project**: Server_API (Production Data Hub)
> **Date**: 2026-06-11
> **Match Rate**: 100% (AC 10/10 PASS)
> **Status**: Completed

---

## 1. 변경 요약

| ID | 변경 | 파일 | 커밋 |
|----|------|------|------|
| T1 | config.toml 6줄 → 풀 테마: `[theme.light]`+`[theme.dark]`+사이드바 변형, Noto Sans KR, 시맨틱 7색, radius/dataframe — **네이티브 설정 메뉴에 Light/Dark 토글 자동 노출** | `.streamlit/config.toml` | bc0b0c3 |
| T2 | theme.py **351 → 99줄**: CSS 토큰 3모드+`_BASE_RULES` 165줄 제거. plotly 팔레트(블루/틸/앰버)와 스타터카드 CSS 1블록만 잔존. 고대비 모드 제거(팔레트 자체 WCAG AA: light 17:1 / dark 13:1) | `shared/ui/theme.py` | bc0b0c3 |
| T3 | KPI 카드: HTML 문자열+CSS 스파크라인 → `st.metric(border=True, chart_data=...)` 4종 + `st.container(horizontal=True)`(반응형 wrap) | `kpi_cards.py`, `overview.py` | 0e34636 |
| T4 | 내비 5페이지+사이드바 전부 Material 아이콘, 로고 HTML → 네이티브 markdown+caption | `app.py` | 43a725c |
| T5 | 전 페이지/컴포넌트 전파: AI 헤더→title+badge, 상태점→st.badge, zero-state→중앙정렬 컨테이너, 카테고리 KPI→bordered metric, 다운로드/저장/삭제 버튼 icon 파라미터. **unsafe_allow_html=True 18→5곳**, 핑크 hex **37→0곳** | ai_section, products, batches, webhooks, views, notifications, layout, loading, presets, charts | b4cd31b, 757e7f4 |
| T6 | (구현 중 발견) Streamlit 1.58: `showSidebarBorder`/`baseFontSize`/`chartCategoricalColors`는 변형 섹션 무효 → top-level `[theme]` 이동 | config.toml | 757e7f4 |

## 2. 검증 결과

- ✅ AC1~AC10 모두 PASS (10/10, **100%**, gap 0건)
- ✅ `pytest tests/ -q` → **361 passed** (회귀 0 — `test_webhook_admin_ui` 소스 검사 포함)
- ✅ `ruff check .` → All checks passed, **CI run 27349353535 success**
- ✅ **Playwright 시각 검증 10장** (라이트 4 + 다크 6): 핑크 잔재 0, 네이티브 테마 메뉴(System/Light/Dark) 노출, KPI border+스파크라인 렌더, 다크 모드 사이드바/카드/경고배너 정합, Material 아이콘 접근성 트리 전수 확인
- ✅ grep: 핑크/스카이 hex 12패턴 0건, `_BASE_RULES`/`TOKENS_*` 0건, unsafe `=True` 정확히 5곳(전부 사유 명시)

## 3. PDCA 메타데이터

```yaml
cycle: ui-design-overhaul-v1
phase: completed
match_rate: 100
plan: docs/archive/2026-06/ui-design-overhaul-v1/ui-design-overhaul-v1.plan.md
design: docs/archive/2026-06/ui-design-overhaul-v1/ui-design-overhaul-v1.design.md
analysis: docs/archive/2026-06/ui-design-overhaul-v1/ui-design-overhaul-v1.analysis.md
report: docs/archive/2026-06/ui-design-overhaul-v1/ui-design-overhaul-v1.report.md
duration_h: 2.5
trigger: 사용자 요청 "ui 및 디자인 대폭 개선" + AskUserQuestion 방향 확정(블루/슬레이트, 네이티브 우선)
```

## 4. 후속 사이클 권장

| Item | 사이클 | 우선순위 |
|------|--------|---------|
| **O1 콜드 딥링크 라우팅 우회** — 레거시 `pages/` 자동 라우팅이 st.navigation 우회(사이드바 부재 화면). 디렉터리명 변경 등 | nav-routing-fix-v1 | **High** (북마크 사용자 실사용 영향) |
| kpi_cards/ai_section/watcher 순수 로직 단위 테스트 | coverage-blindspots-v1 | Medium |
| bulk_retry 순서 의존 flaky (이번 사이클 중 4번째 관찰) + rate limiter clock | rate-limiter-clock-injection | Medium (빈도 상승) |
| webcloring-pdf 분리, R6 린트 램프 | (기존 예고) | Medium |
| Noto Sans KR 자체 호스팅(fontFaces) — 내부망 CDN 차단 대비 | font-self-hosting | Low |

## 5. Lessons Learned

- **config.toml 변형 섹션은 키별 지원 범위가 다르다** — 1.58에서 3개 키가 `[theme.light/dark]`에서 무효("not a valid config option" 기동 로그). 테마 작업은 **반드시 기동 로그를 확인**하고 시작할 것. 문서 예시가 top-level 기준인 키는 변형에 못 들어갈 수 있다.
- **st.metric의 chart_data가 커스텀 KPI 카드의 존재 이유를 없앴다** — border+sparkline+horizontal container 조합이면 HTML 카드 대비 시각 손실이 거의 없고 다크 모드가 공짜로 따라온다.
- **딥링크 시각 QA가 라우팅 버그를 공짜로 발견** — 콜드 세션 딥링크는 일반 클릭 경로에선 절대 안 보이는 결함(O1)을 드러냈다. 시각 QA 시 "새 세션 + 직접 URL" 경로를 항상 포함할 것.
- **이모지→Material 전환의 예외 기준**: 렌더 컨텍스트가 markdown인 곳만 가능. dataframe 셀(데이터), shadcn 카드 title(서드파티)은 이모지 유지가 옳다 — 일괄 치환 금지.
- **st.expander 등 컴포넌트 모듈 수정은 서버 재시작 필요** — Streamlit hot-reload는 페이지 스크립트만 다시 실행, import된 컴포넌트 모듈은 캐시됨. QA 중 "수정했는데 안 바뀜"의 1순위 원인.
