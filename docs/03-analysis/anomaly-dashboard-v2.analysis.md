# anomaly-dashboard-v2 Gap Analysis

> **Design**: docs/02-design/features/anomaly-dashboard-v2.design.md (v0.2 → 본 분석 반영 v0.3)
> **Analyzer**: bkit:gap-detector
> **Date**: 2026-07-08
> **Match Rate**: **96%** (통과 기준 90% 충족)

## 카테고리별 점수

| 카테고리 | 점수 |
|---|:--:|
| 3장 Data Model (스키마/인덱스/함수 계약) | 100% |
| 4장 API Spec (5 엔드포인트·가드·에코) | 100% |
| 5장 UI/UX | 90% |
| 6~8장 에러/보안/테스트 | 100% |
| FR-1~FR-8 | 100% (8/8) |

## Gap 목록 (전부 Low — UI 렌더 세부/문서 문구)

| # | 내용 | 처리 |
|---|---|---|
| G1 | 현재 스캔 "kind별 그룹" 렌더 (설계 O, 구현은 평면 카드) | 설계 v0.3에서 평면 카드로 완화 — 현장 findings 수가 적어(보통 0~3건) 그룹핑이 오히려 과함 |
| G2 | 네비 그룹 라벨: 설계 "관리" ↔ 구현 "운영" (기존 앱의 실제 그룹명) | 설계 v0.3 정정 (구현이 truth) |
| G3 | 쿨다운 "active 배지" ↔ 구현 "🔒 억제 중/만료" 텍스트 | 설계 v0.3 정정 (의미 동일) |
| G4 | 5.3 에러 문구 st.error/warning 혼재 ↔ 구현 st.warning 통일 | 설계 v0.3 정정 |

## 합리적 초과 구현 (조치 불필요)

- `KIND_LABELS`/`SEVERITY_COLORS` 상수 (streamlit-free 유지)
- `_fetch_fresh` 무캐시 헬퍼 (what-if 요구 구현체)
- 인증 회귀에 `/anomaly/state`까지 포함 (설계는 /findings만 명시)
- 가드 정교화: 빈 `RuleOverrides()`+emit 허용 (None 동등, 테스트 고정)

## 결론

기능 계약·데이터 모델·API·보안·테스트 완전 일치. 코드 수정 0건,
설계 문서 소급 정정 4건(v0.3)으로 종결 → Report 단계 진행 가능.
