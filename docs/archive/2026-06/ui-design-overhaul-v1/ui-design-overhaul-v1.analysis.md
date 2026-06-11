# ui-design-overhaul-v1 — Gap Analysis

> **Cycle**: ui-design-overhaul-v1
> **PDCA Phase**: Check
> **Date**: 2026-06-11
> **Design**: [[ui-design-overhaul-v1.design]]
> **Match Rate**: **100%** (AC 10/10, gap 0건)

## 종합 점수

| 항목 | 점수 | 상태 |
|------|:----:|:----:|
| Design 정합 (AC1~AC9) | 100% | ✅ |
| 네이티브 우선 원칙(§0) 준수 | 100% | ✅ |
| **Overall** | **100%** | ✅ |

## AC별 검증

| # | Criterion | 실측 결과 | 판정 |
|---|-----------|-----------|:----:|
| AC1 | config.toml light+dark 풀 정의 | L17~76 양측 + `[theme.*.sidebar]` 완전 정의 | ✅ |
| AC2 | theme.py ≤120줄, 구체제 제거 | **99줄**, `_BASE_RULES`/`TOKENS_*`/high-contrast grep 0건, 잔여 CSS 1블록(6줄) | ✅ |
| AC3 | 핑크/스카이 hex 잔재 0 | 12패턴 grep — dashboard/shared/ui **0건** | ✅ |
| AC4 | unsafe_allow_html=True ≤5곳 | 정확히 **5곳** (loading 3 스켈레톤, theme 1 스타터CSS, responsive 1 미디어쿼리) | ✅ |
| AC5 | KPI = st.metric(border+chart_data) | horizontal container + metric 4종, HTML 빌더 소멸, `_has_signal` 가드 보강 | ✅ |
| AC6 | 내비 5페이지 Material 아이콘 | Design §4 매핑표 9행 1:1 일치, `pages/webhooks.py` 경로 문자열 보존 | ✅ |
| AC7 | pytest green | **361 passed** (py3.12) | ✅ |
| AC8 | ruff + CI green | All checks passed + run **27349353535** success | ✅ |
| AC9 | 10장 스크린샷, 핑크/대비 문제 0 | 라이트 4 + 다크 6 = 10장. 네이티브 토글(System/Light/Dark) 노출, KPI border 렌더, 다크 정합, Material 아이콘 접근성 트리 확인 | ✅ |
| AC10 | match rate ≥90% | 100% | ✅ |

## 문서화된 편차 (의도적 — gap 아님)

| # | 편차 | 근거 |
|---|------|------|
| D1 | `showSidebarBorder`/`baseFontSize`/`chartCategoricalColors` 3키 top-level `[theme]` 배치 | **1.58 실측**: 변형 섹션에서 "not a valid config option" — Design §1 확정 노트 + config 주석 동기화 완료 |
| D2 | STARTER_PROMPTS 이모지 유지 | shadcn 카드 title에 `:material/*:` 미렌더 (기술 제약) |
| D3 | formatters.py 상태 이모지 유지 | dataframe 셀 데이터 + 테스트 단언 대상 (Design §4 "데이터 문자열 불변" 원칙) |

## 부수 관찰 (이번 사이클 비기인)

- **O1 — 콜드 세션 딥링크 라우팅 우회**: 새 브라우저 세션이 `/batches` 등으로 직접 진입하면 레거시 `pages/` 자동 라우팅이 `st.navigation`을 우회해 **사이드바(필터/로고) 없는 화면**이 노출됨(Playwright 재현 2회). 루트 진입 후에는 정상. 기존 동작이며 본 사이클 Scope 밖(IA/라우팅 불변 Non-Goal) — 후속 사이클 후보로 기록(`pages/` 디렉터리명 변경 또는 라우팅 정리).

## 권장 조치

즉시 조치 없음 — **100% → `/pdca report` 진행.** 후속 후보: O1 라우팅 정리, `coverage-blindspots-v1`(kpi_cards/ai_section 순수 로직 테스트), 자체 폰트 호스팅(fontFaces).
