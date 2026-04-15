---
template: report
feature: server-api-consistency-and-smoke
date: 2026-04-14
phase: completed
match_rate: 100
status: completed
---

# server-api-consistency-and-smoke — 완료 보고서

> **Plan**: [server-api-consistency-and-smoke.plan.md](../01-plan/features/server-api-consistency-and-smoke.plan.md) (2026-03-31)
> **Analysis**: [server-api-consistency-and-smoke.analysis.md](../03-analysis/server-api-consistency-and-smoke.analysis.md)
> **산출물 리포트**: [server-api-smoke-2026-03-31.report.md](./server-api-smoke-2026-03-31.report.md) *(heartbeat 당시 작성된 검증 리포트, 계획 §3 C5)*
> **Date**: 2026-04-14

---

## 1. Executive Summary

2026-03-31 heartbeat 세션에서 실시한 문서-코드 정합성 교정 + 최소 스모크 경로 고정 작업의 PDCA 완주를 **소급** 문서화. 계획 §3 의 5개 In-Scope 항목(C1~C5) 모두 당시 완료, 이후 보안/관측성 사이클 3건을 거치면서도 유효성 유지.

| 지표 | 결과 |
|---|---|
| Match Rate | **100%** (iteration 0) |
| 테스트 | 134 pass (후속 사이클 누적 상태 유지) |
| 산출물 | C1~C5 5건 모두 존재 |

---

## 2. 구현 결과

| ID | 항목 | 파일 | 상태 |
|---|---|---|---|
| C1 | 루트 실행 문서 보정 | `README.md` | ✅ (스모크 경로 5곳, plan/report 링크) |
| C2 | 운영 문서 경로 정리 | `docs/specs/operations_manual.md` | ✅ (DASHBOARD_PORT=8502 통일, 환경 독립 경로) |
| C3 | 스모크 전용 의존성 분리 | `requirements-smoke.txt` | ✅ (9 LOC, 최소 9 패키지) |
| C4 | 스모크 스크립트 추가 | `tools/smoke_api.sh` | ✅ (74 LOC, 3 phase + optional health) |
| C5 | 검증 결과 기록 | `docs/04-report/server-api-smoke-2026-03-31.report.md` | ✅ (75 LOC, 한계/확인 분리) |

### 2.1 `tools/smoke_api.sh` 동작 흐름

```
python 감지 → .smoke-venv 생성
  → SMOKE_INSTALL=1 이면 pip install -r requirements-smoke.txt
  → 9개 필수 모듈 import 검증 (pytest, fastapi, uvicorn, orjson,
     cachetools, google.genai, dotenv, requests, pydantic)
  → pytest tests -q
  → python -c 'import api.main'
  → SMOKE_RUN_HEALTH=1 이면 uvicorn 기동 + curl /healthz (trap 기반 종료)
```

### 2.2 heartbeat 환경 한계 (C5 리포트 기록)

- `/mnt/c` WSL 마운트 경로에서 venv 설치 정체 — 운영 리스크로 식별
- heartbeat 당시 `fastapi/uvicorn/pytest` 부재 → import/실행 재현 불가
- 후속 로컬 환경에서는 스크립트 자체는 정상 동작 (134 tests pass 확인)

---

## 3. Out of Scope (유지)

- 프로덕션 배포 자동화
- 전체 테스트 suite 의 CI 구성 — 후속 별개 피처로 분리 권장
- Windows 네이티브 실행 경로 완전 재검증

---

## 4. 배운 점

- **환경 제약이 크면 최소 경로를 고정하라** — heartbeat 의 `/mnt/c` venv 정체를 만나고도, 최소 의존성 리스트와 스크립트를 분리해두면 후속 환경에서 즉시 재현 가능한 자산이 된다.
- **산출물 리포트 ↔ PDCA 완주 보고서 분리** — 2026-03-31 리포트는 "검증 결과 기록" 이라는 계획 항목 C5 의 산출물 자체. 본 PDCA 완료 보고서는 그 위에 얹히는 사이클 마감 문서. 두 역할을 섞지 않는 편이 archive 가독성을 높인다.
- **소급 PDCA 마감의 가치** — 코드/문서가 이미 완료된 legacy plan 을 방치하지 않고 소급 Check → Report → Archive 로 닫으면 `docs/01-plan/features/` 가 "아직 할 일" 의 깨끗한 표지가 된다.

---

## 5. 결론

- Match Rate **100%**, 산출물 5건 모두 유효.
- `/pdca archive server-api-consistency-and-smoke` 진행.
- 후속 권장: CI 자동화는 별도 피처(예: `ci-pipeline-setup`) 로 착수.
