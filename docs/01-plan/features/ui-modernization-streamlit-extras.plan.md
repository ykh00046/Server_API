# UI Modernization — Streamlit + Extras (Option 1)

- **Feature ID**: ui-modernization-streamlit-extras
- **작성일**: 2026-04-15
- **작성자**: Claude (with interojo)
- **상태**: Plan
- **선행 사이클**: ui-ux-enhancement (2026-04-15 완료, 11 impl + 4 Defer)

## 1. 배경 (Why)

지난 `ui-ux-enhancement` 사이클은 playwright 검증까지 완료했지만, Streamlit 순정 컴포넌트의 시각적 한계로 "현대적인 느낌"이 부족함.
프레임워크 제약으로 Defer 된 4개(UX-03/DV-05/MA-04/MA-05) 중 일부는 third-party 확장으로 해소 가능.

**현재 프로젝트 규모** (내부 생산 분석 대시보드, 동시 사용자 1~수십)에서
React/Next.js 완전 교체(옵션 3)는 ROI 불리. Streamlit 유지 + 확장이 최적해.

## 2. 목표 (What)

### Primary Goals (반드시 달성)
- **G1**. shadcn 스타일 카드/버튼/탭 적용 → 시각적 현대화
- **G2**. AI 챗 SSE 스트리밍 (신규 `/chat/stream` + Gemini stream=True) + 마크다운 렌더링 품질 개선
- **G3**. 전역 색상 토큰/타이포그래피 시스템 정리 (CSS 변수 통일)
- **G4**. 고대비 접근성 모드 (MA-04 재시도, streamlit-theme 활용)

### Secondary Goals (여유 있으면)
- **S1**. Command Palette 스타일 검색/네비게이션 (streamlit-shortcuts 또는 custom)
- **S2**. 토스트 알림 품질 개선 (streamlit-extras.row / stoggle)
- **S3**. 로딩 스켈레톤 세련화 (현재 st.spinner → skeleton shimmer)

### Non-Goals (이번 사이클에서 안 함)
- React/Next.js 재작성 → 옵션 3 별도 사이클
- PWA/오프라인 (MA-05) → Streamlit 프레임워크 근본 제약
- 실시간 푸시 (DV-05) → polling 유지
- 모바일 네이티브 앱

## 3. 범위 (Scope)

### 적용 대상
- `dashboard/app.py` — 전역 테마/레이아웃
- `dashboard/components/ai_section.py` — 챗 UI + SSE 클라이언트 (최우선)
- `dashboard/components/kpi_cards.py` — 카드 스타일
- `dashboard/components/charts.py` — 차트 컨테이너
- `shared/ui/theme.py` — CSS 토큰 중앙화
- `api/chat.py` 또는 신규 `api/chat_stream.py` — `POST /chat/stream` SSE 엔드포인트
- `api/_gemini_client.py` — `generate_content(stream=True)` 경로 추가
- `tests/test_chat_stream.py` (신규) — SSE 형식/세션 재사용 검증

### 도입 예정 라이브러리 (평가 후 확정)
| 라이브러리 | 용도 | 비고 |
|------------|------|------|
| `streamlit-extras` | 추가 컴포넌트 집합 | ⭐ 사실상 표준 |
| `streamlit-shadcn-ui` | shadcn 스타일 카드/버튼 | 시각 현대화 핵심 |
| `streamlit-antd-components` | 고급 인풋/메뉴 (옵션) | 필요 시만 |
| `streamlit-theme` | 다크/고대비 토글 | MA-04 재시도 |

**평가 기준**: 메인테넌스 활성도, Streamlit 버전 호환, 라이선스, 번들 크기.

## 4. 측정 지표 (Success Criteria)

| 지표 | 목표 | 측정 방법 |
|------|------|-----------|
| playwright 검증 에러 | 0 errors | console + network |
| 페이지 로드 (LCP) | < 2.5s | Chrome DevTools |
| 접근성 (고대비) | WCAG AA 대비율 ≥ 4.5:1 | axe-core |
| 기존 기능 리그레션 | 0건 | 134+ tests 통과 |
| 신규 의존성 | ≤ 3개 | requirements.txt diff |

## 5. 일정 (Timeline)

| 단계 | 기간 | 산출물 |
|------|------|--------|
| Plan | 2026-04-15 | 본 문서 |
| Design | 2026-04-16 | design.md (토큰 시스템, 컴포넌트 매핑, 마이그레이션 표) |
| Do | 2026-04-16~18 | 코드 구현 + playwright 재검증 |
| Check | 2026-04-19 | gap analysis + 스크린샷 |
| Act/Report | 2026-04-19 | 필요 시 iteration + 완료 보고서 |

**예상 총 공수**: 1~2일 (옵션 1 본래 추정 범위).

## 6. 리스크 및 완화

| 리스크 | 완화 |
|--------|------|
| 서드파티 컴포넌트가 Streamlit 1.x 최신 버전과 비호환 | Design 단계에서 각 라이브러리 테스트 POC |
| CSS 충돌 (shadcn vs Streamlit 기본 스타일) | `shared/ui/theme.py` 에 CSS scope 격리 |
| AI 챗 SSE 업그레이드로 `/chat/` 계약 변경 | 신규 `/chat/stream` 추가(기존 엔드포인트 유지), 호환성 보존 |
| 번들 크기 증가로 콜드 스타트 지연 | 의존성 3개 이내로 제한, 사이즈 측정 |

## 7. 의존성

- 이전 사이클(ui-ux-enhancement) playwright MCP 검증 파이프라인 재사용
- `shared/ui/theme.py` 가 이미 분리되어 있어 토큰 중앙화 용이 (2026-04 리팩토링 결과)
- requirements.txt 관리 — 신규 라이브러리 추가 시 smoke 환경도 고려

## 8. Open Questions

1. ~~AI 챗 스트리밍: UI 타협 vs API SSE~~ → **API SSE 업그레이드로 확정 (2026-04-15)**. 신규 `POST /chat/stream` 엔드포인트 추가, 기존 `POST /chat/` 동기 엔드포인트는 호환 유지. Gemini `generate_content(stream=True)` + FastAPI `StreamingResponse` 조합.
2. 다크모드 기본값: 사용자 선호? → 시스템 기본 (`prefers-color-scheme`) 추종 권장.
3. 기존 `render_ai_header_with_animation` 의 그라디언트 텍스트 → shadcn 스타일과 어울리는지 재검토.

---

*다음 단계: `/pdca design ui-modernization-streamlit-extras`*
