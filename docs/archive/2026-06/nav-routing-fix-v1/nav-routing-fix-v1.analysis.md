# nav-routing-fix-v1 — Gap Analysis

> **Cycle**: nav-routing-fix-v1
> **PDCA Phase**: Check
> **Date**: 2026-06-11
> **Design**: [[nav-routing-fix-v1.design]]
> **Match Rate**: **100%** (AC 7/7)
> **검증 방식**: 전 AC가 1차 증거(grep/pytest/CI/Playwright 실측)로 직접 측정 — 본 사이클은 별도 gap-detector 에이전트 없이 직접 검증으로 충분(변경 파일 7개, 내용 변경은 app.py+테스트 2개뿐).

## AC별 검증

| # | Criterion | 실측 결과 | 판정 |
|---|-----------|-----------|:----:|
| AC1 | `dashboard/pages/` 부재, `views/` 5파일 | git mv 5건 + 잔존 `__pycache__` 디렉터리까지 제거(Test-Path False). **빈 pages/도 버그를 재발시키므로 pycache 제거가 필수였음** | ✅ |
| AC2 | app.py `st.Page("views/...")` 5곳, `pages/` 기능 참조 0 | 5곳 전환. grep 잔여 1건은 **재발 방지 경고 주석 자체**("NOT named pages/") — 기능 참조 0 | ✅ |
| AC3 | **콜드 딥링크 첫 요청 풀 사이드바** | 서버 재기동 → 첫 요청 `/batches` 딥링크 → 로고+검색필터+프리셋+내비 전부 렌더(스크린샷). 필터 적용된 0건 표시 = app.py 실행 증거(버그 화면은 필터 없는 5,000건이었음) | ✅ |
| AC4 | 루트+클릭 경로 회귀 | 루트 → 내비 클릭 `/products` 정상, 내비 href 전수(`/trends` `/batches` `/products` `/webhooks`) **URL 불변** 확인 | ✅ |
| AC5 | pytest green | **362 passed** (361 + 신규 `test_no_legacy_pages_directory` 재발 가드) | ✅ |
| AC6 | ruff + CI green | All checks passed + run **27355978686** success | ✅ |
| AC7 | match rate ≥ 90% | 100% | ✅ |

## Design 대조

- §1 변경 목록 4행 — 전부 그대로 실행. `views` 명칭 충돌 없음(webhook_admin/views.py는 import 경로 상이).
- §2 검증 절차 — 수정 전 재현(기확보 2회) + 수정 후 콜드 딥링크 + 클릭 회귀 + URL 보존, 전 단계 수행.
- §3 커밋 — 원자적 1커밋(7ee7514) + docs 커밋. 계획 일치.

## 추가 구현 (Design 범위 내 보강)

- `test_no_legacy_pages_directory` 재발 방지 가드 — Plan §6 리스크("빈 디렉터리도 재발")를 영구 가드로 승격. AC5에 포함 집계.

## 권장 조치

없음 — **100% → Report 진행.** 운영 반영: Manager에서 대시보드 재시작 시 즉시 적용(코드 경로만 변경, 설정·DB 무관).
