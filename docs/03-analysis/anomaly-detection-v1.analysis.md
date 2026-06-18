# anomaly-detection-v1 Gap Analysis

> **Phase**: Check (+ Act 보정 반영)
> **Date**: 2026-06-19
> **Analyst**: bkit:gap-detector (독립 분석) + Claude
> **Match Rate**: 96% → **100% (Act 후)**

---

## 1. 종합

| 영역 | Match | 비고 |
|------|:-----:|------|
| 기능 요구사항 FR-1~7 | 100% | 전부 구현·테스트 |
| 비기능 NFR-1~5 | 100% | read-only/idempotent/예외 비전파/OFF 스위치 |
| 3종 규칙 | 100% | 경계값 테스트 포함 |
| 컴포넌트 구조 (design §9) | 100% | 의존 방향 준수, rules 순수 |
| API 스펙 (design §4) | 100% | scan/rules 구현 |
| 데이터 모델 (design §3) | 100% | Finding + 상태파일 |
| 테스트 계획 (design §8) | 100% | 계획 초과(state 독립 파일, dry-run 케이스) |
| 부수 산출물(gitignore/env) | 100% | **Act에서 보정** |

검증: `pytest` 567 passed (anomaly 29 신규 포함), `ruff check .` All checks passed.

## 2. 발견된 갭과 조치 (Act)

| # | 갭 | 심각도 | 조치 | 상태 |
|---|----|:------:|------|:----:|
| 1 | `.gitignore`에 `database/.anomaly_state.json` 누락 (상태파일 git 추적 위험) | 중 | `.gitignore`에 항목 추가 | ✅ 완료 |
| 2 | `.env.example`에 `ANOMALY_*` 9개 노브 미반영 | 경미 | 기본값과 함께 추가 | ✅ 완료 |
| 3 | design §4.2 `/anomaly/scan` 응답 예시가 실제(`enabled`,`emitted_count`)와 불일치 | 무시가능 | 문서를 코드에 맞춤(Code-is-truth) | ✅ 완료 |

## 3. 설계 의도를 강화한 추가 구현 (긍정적 차이)

- `store_state.prune`: 쿨다운 항목 만료 정리 → 상태파일 무한 증가 억제.
- severity 자동 등급화: `drop_pct+25`/`stale_days*2` 초과 시 critical.
- stale 결과 idle 내림차순 정렬, `EVENT_TYPE_DESCRIPTIONS`(관리 UI 노출).
- `test_anomaly_state.py` 독립 분리.

## 4. 잔여 리스크 / 후속 (v2 후보)

- 통계/계절성 기반 이상탐지(현재는 단순 후행 평균 규칙) — `anomaly-detection-v2`.
- 품목별 개별 임계치 / 대시보드 시각화 — 별도 기능.
- 운영 데이터 기반 임계치 튜닝(현 기본값은 보수적 시작점).

## 5. 결론

설계-구현 일치도 96% → Act 보정 후 실질 100%. 핵심 가치(pull→push 능동 알림, webhook 인프라 재사용)를 신규 코드 최소화로 달성. Report 진행 가능.
