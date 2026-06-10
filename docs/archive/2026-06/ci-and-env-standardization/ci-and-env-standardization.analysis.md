# ci-and-env-standardization — Gap Analysis

> **Cycle**: ci-and-env-standardization
> **PDCA Phase**: Check
> **Date**: 2026-06-10
> **Design**: [[ci-and-env-standardization.design]]
> **Match Rate**: **98%** (Design 정합 96% + Plan AC 9/9 = 100%)

## 종합 점수

| 범주 | 점수 | 상태 |
|------|:----:|:----:|
| Design 정합 (§1~§6) | 96% | ✅ |
| Plan AC 충족 (AC1~AC9) | 100% (9/9) | ✅ |
| **종합** | **98%** | ✅ |

> 결론: Design과 구현이 매우 잘 일치. 발견된 편차는 모두 **의도적·문서화된** 것으로, 구현이 정본(truth)이며 Design 문서 측 동기화만 필요 → 본 사이클에서 반영 완료(§문서 동기화).

## Design 섹션별 대조 요약

| Design 섹션 | 판정 | 비고 |
|---|:----:|---|
| §1.1 단일 full lock (서브셋 불생성) | ✅ | `requirements.lock.txt` 99핀 단일, CI 서브셋 없음 |
| §1.2 lock 형식/헤더/갱신 절차 | ✅ | 헤더 4줄, runtime+dev 통합, Windows 전용 핀 0 (colorama만 — cross-platform → 수동 마커 불필요) |
| §1.3 floor 66 (실측 −5%p) | ✅ | ci.yml 주석 + `--cov-fail-under=66` |
| §2 ci.yml 구조 | ✅ | 2-job/트리거/concurrency/permissions/py3.12/캐시 전 항목 일치. `tr -d '\r'` CRLF 방어 추가 |
| §3 로컬 정본 venv 재구축 | ✅ | py3.12.12 venv에서 pytest 360 green + ruff clean 실측 |
| §4 시뮬레이션 S1/S2/S3 | ✅ | S1에서 실DB 의존 12건 검출 → §4가 사전 허용한 우회(빈 fixture DB step) 채택. S2/S3 PASS |
| §5 README 변경 | ✅ | py3.12 명시·lock 경로·갱신 4줄·CI 절+배지·스모크 "선택" 강등 전부 반영 |
| §6 커밋 계층 3분리 | ✅ | env+lock / ci.yml / README 분리 커밋 |

## Plan AC 대조 (9/9)

| AC | 기준 | 실측 증거 |
|----|------|----------|
| AC1 | ci.yml 2-job, push(main)+PR, py3.12 | `.github/workflows/ci.yml` |
| AC2 | Actions 실행 green | run **27261502491** success (lint 8s, test 1m4s) — https://github.com/ykh00046/Server_API/actions/runs/27261502491 |
| AC3 | baseline 기록 + floor 설정 | 실측 71% → floor 66, Design §1.3 + ci.yml 주석 + README |
| AC4 | lock 신규 + CI lock 설치 | 99핀, `pip install -r requirements.lock.txt` |
| AC5 | 로컬 py3.12 venv pytest green | **360 passed** (17~19s) 실측 |
| AC6 | venv ruff 클린 | `All checks passed` 실측 |
| AC7 | README 갱신 | 설치/테스트/CI/스모크 절 동기화 |
| AC8 | pyproject 불변 | addopts = `-ra`,`--strict-markers`만 — floor는 ci.yml에만 존재 |
| AC9 | match rate ≥ 90% | 본 분석 98% |

## 발견된 차이

**미구현 (Design O / 구현 X)**: 없음.

**추가 (Design X / 구현 O)** — 모두 정보 등급:
1. 빈 fixture DB 생성 step (`ci.yml`) — Design §4가 "S1 실패 시 우회"로 사전 허용한 분기. S1 시뮬레이션에서 실DB 의존 테스트 12건(test_api_integration 7, test_audit 5) 확인되어 채택.
2. `tr -d '\r'` 파이프 — Windows CRLF lock 대비 방어, 기능 동일.

**변경 (Design ≠ 구현)** — 모두 낮음 등급, 구현이 정본:
1. GitHub Actions 액션 버전: Design `@v4`/`@v5` → 구현 `checkout@v6`/`setup-python@v6`. 첫 run의 Node 20 deprecation annotation(2026-06-16 Node 24 강제) 대응 상향. 상향 후 run green 확인.
2. ci.yml 주석 영문화: PowerShell 인코딩 사고(mojibake로 워크플로 파싱 실패 1회) 후 ASCII-only로 통일.

## 문서 동기화 (본 사이클에서 Design에 반영)

1. §2 YAML 액션 버전 `@v6` 갱신 + Node 20 deprecation 근거 1줄.
2. §2에 fixture DB step 채택 사실 반영(§4 우회 경로 실행됨).
3. §1.3 baseline 각주: py3.13 실측 71% / py3.12 CI 시뮬레이션 70% — floor 66은 양쪽 모두 −4~5%p 마진으로 유효, 결론 불변.
4. §1.2 Windows 전용 핀 검사 결과(0건, colorama만) 기록 — §8 잔존 리스크 클로즈.

## 부수 관찰 (후속 사이클 입력)

- **신규 flaky 관찰**: `tests/test_notifications_bulk_retry.py`의 worker dispatch 계열 2건이 전체 스위트 실행 중 간헐 실패(단독 실행은 항상 green, 재실행 green). 실행 순서 의존 추정 — `rate-limiter-clock-injection` 후속 사이클에 관찰 대상으로 함께 등재 권장.
- **의존성 최신화 부수효과**: 무핀 상태에서 신규 설치된 FastAPI가 `ORJSONResponse` deprecation 경고 발생 — lock 고정으로 당장 영향 없으나, 다음 의존성 업그레이드 사이클에서 대응 필요.
- **GitHub Actions Node 24 강제(2026-06-16)**: v6 상향으로 선제 대응 완료.

## 권장 조치

즉시 조치 없음 — 모든 AC 충족, Actions green. **98% ≥ 90% → `/pdca report` 진행.**
