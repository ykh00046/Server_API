# dashboard-code-quality Planning Document

> **Summary**: 대시보드 코드 품질 개선 — unsafe_allow_html 통합, sys.path 제거, mutable default 수정
>
> **Project**: Server_API (Production Data Hub)
> **Version**: Code Quality Phase 2
> **Author**: interojo
> **Date**: 2026-04-17
> **Status**: Plan

---

## 1. Overview

### 1.1 Purpose

`dashboard-sidebar-redesign` 코드 리뷰(Quality Score 68/100)에서 보류된 Medium/Low 이슈를 해소하여
유지보수성, 보안 일관성, 코드 품질을 개선한다.

### 1.2 Background

- **선행 사이클**: `dashboard-sidebar-redesign` (Match Rate 96%) — Critical 3건, High 6건 이미 해소
- **잔여 이슈**: Medium 5건(M1, M6, M7, M8, M9) 중 실질 개선 가능한 3건 + Low 잔여 2건
- **목표 점수**: Quality Score 68 → 80+

### 1.3 Related Documents

- 코드 리뷰 결과: `docs/archive/2026-04/dashboard-sidebar-redesign/` (report 참조)
- 선행 커밋: `e90c222 feat(dashboard): B3 sidebar UI redesign + code quality fixes`

---

## 2. Scope

### 2.1 In Scope

| ID | Item | Priority | Source | Effort |
|----|------|----------|--------|--------|
| S1 | `unsafe_allow_html` CSS 통합 — 17곳 인라인 HTML을 CSS 클래스로 전환 | Medium | M1 | 1hr |
| S2 | `sys.path.insert` 제거 — `app.py`, `data.py` 2곳, 상대 import 또는 PYTHONPATH 설정으로 전환 | Medium | M6 | 30min |
| S3 | mutable default `api_url` 수정 — `ai_section.py` 3개 함수에서 `None` default + 함수 내 resolve | Low | M7 | 15min |
| S4 | skeleton 함수 미사용 `key` 파라미터 제거 — `loading.py` 3개 함수 | Low | L1 | 10min |
| S5 | UI 문자열 언어 통일 — English → Korean 또는 일관된 규칙 적용 | Low | L5 | 20min |

### 2.2 Out of Scope

| Item | Reason |
|------|--------|
| M8: preset 영속화 (파일/DB 저장) | 현재 설계 의도 (session 한정), 별도 피처 필요 |
| M9: DataFrame hash 캐시 최적화 | 현재 데이터 규모에서 성능 문제 없음 |
| CSS 토큰 시스템 전면 재설계 | S1에서 기존 CSS 토큰 활용으로 충분 |
| `__init__.py` 페이지별 lazy import | 현재 import 시간 이슈 없음 |

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-01 | `unsafe_allow_html=True` 사용 횟수 17 → 5 이하 (불가피한 경우만 허용) | Medium |
| FR-02 | `sys.path.insert` 호출 0건 — import 방식 변경 | Medium |
| FR-03 | 함수 signature에 mutable default 0건 | Low |
| FR-04 | 미사용 파라미터 0건 | Low |
| FR-05 | UI 문자열 Korean 통일 (English 잔류 5건 이하) | Low |

### 3.2 Non-Functional Requirements

| Category | Criteria |
|----------|----------|
| Compatibility | Streamlit 1.54.0 정상 기동 유지 |
| Performance | 페이지 로드 시간 현행 수준 유지 (악화 없음) |
| Testability | 기존 149+ 테스트 전부 통과 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] `unsafe_allow_html=True` 5건 이하
- [ ] `sys.path.insert` 0건
- [ ] mutable default argument 0건 (ai_section.py)
- [ ] 미사용 `key` 파라미터 0건 (loading.py)
- [ ] UI 문자열 혼용 English 잔류 5건 이하
- [ ] Streamlit 서버 정상 기동
- [ ] 기존 테스트 통과

### 4.2 Quality Criteria

- [ ] Quality Score 80+ (code-analyzer 재측정)
- [ ] 브라우저 콘솔 JS 에러 0건
- [ ] 기존 기능 회귀 없음

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| S1: CSS 클래스 전환 시 스타일 깨짐 | High | Medium | 전환 후 Playwright 스크린샷 비교 |
| S2: import 경로 변경 시 ModuleNotFoundError | High | Medium | `dashboard/__init__.py` 없이도 동작하는 상대 import 테스트 |
| S2: start_services 스크립트 PYTHONPATH 누락 | Medium | Low | VBS/bat 스크립트에 env 설정 추가 |
| S5: 한글 전환 시 기존 프리셋 key 호환성 | Low | Low | 프리셋은 session 한정, 영향 없음 |

---

## 6. Architecture Considerations

### 6.1 Project Level

Dynamic (기존 유지)

### 6.2 Key Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| CSS 통합 방식 | 인라인→클래스 / CSS-in-Python / 별도 .css | 인라인→클래스 (기존 `apply_custom_css()` 활용) | theme.py에 이미 CSS 토큰 시스템 있음 |
| import 방식 | sys.path / relative import / PYTHONPATH | PYTHONPATH (start script에서 설정) | Streamlit CWD가 dashboard/이므로 relative import 불안정 |
| api_url default | mutable / None+resolve / module constant | None+resolve | Python best practice, runtime env 변경 대응 |

### 6.3 Implementation Order

```
1. S3: mutable default fix (가장 단순, 리스크 최소)
2. S4: unused key param removal
3. S5: UI string Korean 통일
4. S2: sys.path.insert 제거 + PYTHONPATH 설정
5. S1: unsafe_allow_html CSS 통합 (가장 복잡, 마지막)
```

---

## 7. File Change Summary

| 구분 | 파일 | 변경 내용 |
|------|------|----------|
| MOD | `dashboard/components/ai_section.py` | S3: api_url default → None |
| MOD | `dashboard/components/loading.py` | S4: key param 제거, S5: English→Korean |
| MOD | `dashboard/components/presets.py` | S5: UI label Korean 전환 |
| MOD | `dashboard/app.py` | S2: sys.path.insert 제거 |
| MOD | `dashboard/data.py` | S2: sys.path.insert 제거 |
| MOD | `shared/ui/theme.py` | S1: CSS 클래스 추가 (status, header, hint, spacer 등) |
| MOD | `dashboard/components/ai_section.py` | S1: 인라인 HTML → CSS 클래스 |
| MOD | `dashboard/components/kpi_cards.py` | S1: 인라인 HTML → CSS 클래스 |
| MOD | `dashboard/pages/overview.py` | S1: 인라인 HTML → CSS 클래스 |
| MOD | `dashboard/app.py` | S1: 사이드바 로고 인라인 → CSS |
| MOD | 서비스 시작 스크립트 | S2: PYTHONPATH 환경변수 설정 |

---

## 8. Next Steps

1. [ ] Design document (`/pdca design dashboard-code-quality`)
2. [ ] Implementation
3. [ ] Gap Analysis
4. [ ] Completion Report
5. [ ] Archive

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-04-17 | Initial plan — 보류 이슈 5건 정리 | interojo |
