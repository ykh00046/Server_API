# Plan: Server API Consistency and Smoke Verification

> PDCA Phase: **Plan**
> Feature: `server-api-consistency-and-smoke`
> Created: 2026-03-31
> Status: Draft

---

## 1. Background & Motivation

문서 기준 실행 절차와 실제 코드 시그니처를 비교한 결과, 최소 실행 절차를 다시 고정할 필요가 확인됐다.

- heartbeat 환경에는 `fastapi`, `uvicorn`, `pytest`, `streamlit` 등 핵심 의존성이 없어 런타임 재현이 바로 되지 않았다.
- WSL의 `/mnt/c` 마운트 경로에서 직접 venv를 구성할 경우 설치가 매우 느리거나 장시간 정체될 수 있다.
- 문서 일부는 현재 엔드포인트/파라미터 구조와 어긋나 있었고, 이를 보완한 스모크 전용 산출물이 추가되었다.

이 계획은 문서 정합성 수정과 최소 스모크 경로를 한 묶음으로 관리하기 위한 기준 문서다.

## 2. Goals

| ID | 목표 | 측정 기준 |
|:--:|------|----------|
| G1 | 최소 스모크 절차 고정 | `tools/smoke_api.sh`와 `requirements-smoke.txt` 기준 절차 문서화 |
| G2 | 코드-문서 불일치 축소 | README/운영 문서의 주요 실행 정보가 코드와 일치 |
| G3 | 재검증 포인트 명시 | 현재 heartbeat 한계와 후속 검증 필요 항목이 리포트에 정리됨 |

## 3. Scope

### In Scope

| ID | 항목 | 파일 | 난이도 |
|:--:|------|------|:------:|
| C1 | 루트 실행 문서 보정 | `README.md` | Low |
| C2 | 운영 문서 경로 정리 | `docs/specs/operations_manual.md` | Low |
| C3 | 스모크 전용 의존성 분리 | `requirements-smoke.txt` | Low |
| C4 | 스모크 스크립트 추가 | `tools/smoke_api.sh` | Medium |
| C5 | 검증 결과 기록 | `docs/04-report/server-api-smoke-2026-03-31.report.md` | Low |

### Out of Scope

- 프로덕션 환경 배포 자동화
- 전체 테스트 스위트의 CI 구성
- Windows 네이티브 실행 경로의 완전한 재검증

## 4. Detailed Plan

### C1-C2. 문서 정합성 보정

- 루트 `README.md`의 API 엔드포인트, 파라미터, 스모크 절차를 코드 기준으로 맞춘다
- 운영 매뉴얼에서 개인 고정 경로를 프로젝트 루트 기준 표기로 교체한다
- 문서에서 스모크 결과 리포트로 바로 이동할 수 있는 링크를 유지한다

### C3-C4. 최소 스모크 경로 고정

- `requirements-smoke.txt`에는 import/pytest/헬스체크에 필요한 최소 패키지만 둔다
- `tools/smoke_api.sh`는 다음 순서로 검증한다
  1. pytest 가용성 확인
  2. `api.main` import 검증
  3. 선택적 `/healthz` 요청 확인

### C5. 리포트 작성

- heartbeat 환경의 한계와 확인 가능 범위를 분리 기록한다
- 실제로 확인한 엔드포인트와 미확인 리스크를 문서에 남긴다
- 보드 후속 작업이 필요할 경우 리포트에서 다음 액션을 제안한다

## 5. Modified Files Summary

| 파일 | 변경 유형 | 항목 |
|------|----------|------|
| `README.md` | Modified | C1: 실행/문서 링크 정리 |
| `docs/specs/operations_manual.md` | Modified | C2: 환경 독립 경로 정리 |
| `requirements-smoke.txt` | 신규 생성 | C3: 최소 스모크 의존성 |
| `tools/smoke_api.sh` | 신규 생성 | C4: 최소 스모크 스크립트 |
| `docs/04-report/server-api-smoke-2026-03-31.report.md` | 신규 생성 | C5: 검증 리포트 |

## 6. Verification Plan

1. `python3 -m pytest -q tests` 실행 가능 여부 확인
2. `python3 -c "import api.main"` 성공 여부 확인
3. `SMOKE_INSTALL=1 tools/smoke_api.sh`로 최소 절차 재현 시도
4. 실패 시 환경 제약과 원인을 리포트에 남기고 후속 액션을 분리한다
