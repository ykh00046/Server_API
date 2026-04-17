# dashboard-sidebar-redesign Planning Document

> **Summary**: 탭 기반 UI를 사이드바 네비게이션 + 상시 AI 패널 구조로 전환
>
> **Project**: Server_API (Production Data Hub)
> **Version**: B3 Sidebar UI
> **Author**: interojo
> **Date**: 2026-04-17
> **Status**: Implemented (소급 Plan)

---

## 1. Overview

### 1.1 Purpose

현재 Streamlit 단일 `app.py` + 4개 탭(`AI 분석`, `추세`, `상세내역`, `제품비교`) 구조를
`st.navigation` 기반 멀티페이지 + 사이드바 네비게이션 + 상시 AI 패널 레이아웃으로 전환한다.

### 1.2 Background

- **기존 문제**: 탭 간 전환 시 AI 채팅 컨텍스트가 유지되지 않음, 모든 데이터가 `app.py` 한 파일에 집중
- **목표 UX**: B3 목업 — 좌측 사이드바(필터+네비), 중앙 대시보드 콘텐츠, 우측 AI 비서(토글)
- **색상 전환**: 보라-블루(`#667eea`) → 핑크-스카이(`#ec4899` + `#0ea5e9`)로 전면 교체
- **탐색 과정**: mockup-a(플로팅 채팅) → mockup-b(다크 단일페이지) → mockup-b2(라이트 리파인) → mockup-b3(사이드바+AI 패널) 확정

### 1.3 Related Documents

- 목업 파일: `mockup-b3-sidebar.html`
- 아카이브: `docs/archive/2026-04/ui-modernization-streamlit-extras/` (선행 사이클)

---

## 2. Scope

### 2.1 In Scope

- [x] S1: 데이터 레이어 분리 (`data.py` 추출)
- [x] S2: `st.navigation` + `st.Page` 멀티페이지 전환
- [x] S3: 사이드바 필터 + session_state 공유
- [x] S4: AI 패널 토글 (열기/닫기, `st.columns([7,3])`)
- [x] S5: AI compact 패널 (`render_ai_section_compact`)
- [x] S6: 공통 레이아웃 컴포넌트 (`layout.py`)
- [x] S7: 핑크/스카이 차트 색상 (차트 내 `#ec4899` / `#0ea5e9`)
- [x] S8: `st.segmented_control` 집계 단위 (추세/제품)
- [x] S9: X축 category 타입 강제 (Plotly 날짜 파싱 방지)
- [x] S10: 부동소수점 표시 정수 포맷팅

### 2.2 Out of Scope

- CSS 토큰 시스템(theme.py) 핑크/스카이 전면 교체 (Phase 2 예정)
- `config.toml` primaryColor 변경 (Phase 2 예정)
- KPI 카드 HTML 커스텀 리디자인 (현재 `st.metric` 유지)
- CORS 미들웨어 추가 (별도 작업)
- reports.py / settings.py 페이지 (불필요 판정)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `st.navigation` 기반 4페이지 라우팅 (종합현황/추세/배치/제품) | High | ✅ Done |
| FR-02 | 사이드바에 필터(날짜, 키워드, 제품, 레코드 수) 유지 | High | ✅ Done |
| FR-03 | 필터 상태 `session_state["_filters"]`로 전페이지 공유 | High | ✅ Done |
| FR-04 | AI 패널 토글 (기본 닫힘, 열면 7:3 비율) | High | ✅ Done |
| FR-05 | AI compact 패널: Quick chips + 채팅 + 엑셀 다운로드 | Medium | ✅ Done |
| FR-06 | 데이터 로딩 함수 `data.py`로 분리 (캐시 유지) | High | ✅ Done |
| FR-07 | 차트 색상 핑크/스카이 적용 | Medium | ✅ Done |
| FR-08 | 집계 단위 segmented_control (일/주/월) | Medium | ✅ Done |

### 3.2 Non-Functional Requirements

| Category | Criteria | Status |
|----------|----------|--------|
| Performance | 페이지 전환 시 캐시 유지 (`@st.cache_data` TTL 보존) | ✅ |
| Compatibility | Streamlit 1.54.0 API (`st.navigation`, `st.segmented_control`) | ✅ |
| Maintainability | 페이지당 1파일, 공통 레이아웃 재사용 | ✅ |
| UX | AI 패널 기본 닫힘 (메인 콘텐츠 우선) | ✅ |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [x] 4개 페이지 정상 라우팅 (/, /trends, /batches, /products)
- [x] AI 패널 토글 동작 (열기/닫기)
- [x] 필터 변경 시 모든 페이지 데이터 반영
- [x] 차트 X축 정상 표시 (category 타입)
- [x] 부동소수점 정수 포맷
- [x] 기존 기능 (Excel 다운로드, 프리셋, 테마 토글) 유지

### 4.2 Quality Criteria

- [x] Streamlit 서버 에러 없이 기동
- [x] 브라우저 콘솔 JS 에러 0건
- [x] 4개 페이지 스크린샷 시각 검증 통과

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| `st.navigation` 페이지 간 상태 유실 | High | Low | `session_state["_filters"]` dict로 공유, entrypoint에서 선언 |
| AI 패널 열면 차트 영역 축소 | Medium | High | 기본 닫힘 + 토글로 사용자 선택 |
| `data.py` import 경로 문제 | High | Medium | Streamlit CWD가 `dashboard/`이므로 `from data import ...` 정상 동작 확인 |
| 기존 테스트 깨짐 | Medium | Low | 테스트는 API 레이어 대상, 대시보드 UI 테스트 없음 |

---

## 6. Architecture Considerations

### 6.1 Project Level Selection

| Level | Characteristics | Selected |
|-------|-----------------|:--------:|
| **Starter** | Simple structure | ☐ |
| **Dynamic** | Feature-based modules, services layer | ☑ |
| **Enterprise** | Strict layer separation, DI | ☐ |

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| UI Framework | Streamlit | Streamlit 1.54.0 | 기존 스택 유지, `st.navigation` 지원 |
| 페이지 구조 | 탭 / 멀티페이지 | `st.navigation` 멀티페이지 | URL 라우팅, 코드 분리 |
| AI 패널 | 플로팅 / 인라인 / 고정 우측 | 토글 가능 우측 패널 | 화면 공간 효율 + 상시 접근 |
| 데이터 레이어 | app.py 내장 / 분리 | `data.py` 분리 | 멀티페이지 공유 필요 |
| 색상 | 보라-블루 / 핑크-스카이 | 핑크-스카이 | B3 목업 확정 |

### 6.3 Structure

```
dashboard/
├── app.py              # 엔트리포인트 (nav + sidebar filters)
├── data.py             # 데이터 로딩 레이어 (캐시 함수)
├── pages/
│   ├── overview.py     # 종합 현황 (KPI + 차트 + AI)
│   ├── trends.py       # 생산 추세 (일/주/월)
│   ├── batches.py      # 배치 내역 (테이블 + Excel/CSV)
│   └── products.py     # 제품 비교 (Top10 + 분포 + 추세)
└── components/
    ├── __init__.py     # 통합 export
    ├── layout.py       # [NEW] 공통 레이아웃 (헤더, AI 토글, columns)
    ├── ai_section.py   # [MOD] + render_ai_section_compact
    ├── charts.py       # [MOD] 핑크/스카이 색상
    ├── kpi_cards.py    # (유지)
    ├── presets.py       # (유지)
    ├── loading.py       # (유지)
    └── notifications.py # (유지)
```

---

## 7. File Change Summary

| 구분 | 파일 | 변경 내용 |
|------|------|----------|
| NEW | `dashboard/data.py` | app.py에서 데이터 로딩 함수 추출 (331줄) |
| NEW | `dashboard/pages/overview.py` | 종합 현황 페이지 |
| NEW | `dashboard/pages/trends.py` | 생산 추세 페이지 |
| NEW | `dashboard/pages/batches.py` | 배치 상세 페이지 |
| NEW | `dashboard/pages/products.py` | 제품 비교 페이지 |
| NEW | `dashboard/components/layout.py` | 공통 레이아웃 헬퍼 |
| REWRITE | `dashboard/app.py` | 536줄 → 149줄 (엔트리포인트) |
| MOD | `dashboard/components/ai_section.py` | + `render_ai_section_compact` (160줄) |
| MOD | `dashboard/components/charts.py` | 색상 `#ec4899`, 정수 포맷 |
| MOD | `dashboard/components/__init__.py` | layout.py export 추가 |

---

## 8. Next Steps

1. [x] ~~Write design document~~ (소급 — 구현 완료 후 Plan 작성)
2. [ ] Gap Analysis (`/pdca analyze dashboard-sidebar-redesign`)
3. [ ] Completion Report
4. [ ] Archive

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-04-17 | 소급 Plan — 구현 완료 후 문서화 | interojo |
