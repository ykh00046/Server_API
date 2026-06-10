# ci-and-env-standardization Completion Report

> **Summary**: GitHub Actions CI 신설(lint+test+coverage floor 66) + 실행환경 표준화(py3.12 정본 venv, 99핀 lock) — 수동 의존이던 품질 게이트를 자동 강제 장치로 전환
>
> **Project**: Server_API (Production Data Hub)
> **Date**: 2026-06-10
> **Match Rate**: 98% (AC 9/9 PASS)
> **Status**: Completed

---

## 1. 변경 요약

| ID | 변경 | 파일/위치 |
|----|------|----------|
| CI-1 | GitHub Actions 워크플로 신설 — lint(ruff, lock-pinned 버전)/test(pytest+cov) 2-job, push(main)+PR 트리거, concurrency cancel, `permissions: contents: read`, 시크릿 0 | `.github/workflows/ci.yml` |
| CI-2 | coverage floor **66%** CI 전용 적용 (`--cov-fail-under=66`, baseline 71% 실측 −5%p) — pyproject "floor는 CI에서만" 주석의 약속 이행, 로컬 addopts 불변 | `ci.yml` test job |
| CI-3 | 러너 ERP DB 부재 대응 — 빈 `production_records` fixture DB 생성 step (S1 시뮬레이션에서 실DB 의존 테스트 12건 검출 → Design §4 우회 경로 채택) | `ci.yml` test job |
| ENV-1 | 고아 WSL venv(POSIX 레이아웃, WSL 배포판 부재) → **Windows py3.12.12 네이티브 venv** 재구축 — ruff `target-version py312`와 런타임 일치 | `.venv` (로컬) |
| ENV-2 | `requirements.lock.txt` 신설 — pip freeze **99핀**(runtime+dev 통합, UTF-8 no-BOM/LF), CI·로컬 공통 정본. Windows 전용 핀 0건 확인 | `requirements.lock.txt` |
| DOC-1 | README 동기화 — py3.12 명시, lock 설치/재생성 절차, CI 절+배지, 스모크 "선택(Linux/WSL)" 강등 | `README.md` |
| FIX-1 | (구현 중) actions `checkout@v6`/`setup-python@v6` 상향 — Node 20 deprecation(2026-06-16 Node 24 강제) annotation 대응 | `ci.yml` |
| FIX-2 | (구현 중) ci.yml 주석 ASCII-only 통일 — PowerShell 인코딩 roundtrip이 비ASCII 주석을 mojibake로 만들어 워크플로 파싱 실패 1회 발생 → Write 재작성으로 복구 | `ci.yml` |

## 2. 검증 결과

- ✅ AC1~AC9 모두 PASS (9/9), gap match rate **98%**
- ✅ **GitHub Actions run 27261502491 success** — lint 8s, test 1m4s (NFR ≤10분 충족): https://github.com/ykh00046/Server_API/actions/runs/27261502491
- ✅ 신규 py3.12 venv: `pytest tests/ -q` → **360 passed**, `ruff check .` → All checks passed
- ✅ CI 조건 로컬 시뮬레이션(S1+S2: `database/`·`.env` 부재 + 빈 fixture DB): **360 passed**, coverage 70% > floor 66
- ✅ S3: 임시 venv에 lock 단독 설치 성공 (재현성 확인)
- ✅ AC8 불변 검증: `pyproject.toml` diff 0 — addopts에 `--cov-fail-under` 미포함, floor는 ci.yml에만
- 커밋 계층: ① `68ad173` env+lock ② `8f4d250` ci.yml ③ `c801936` README ④ `651118c` PDCA docs (+ `fcaa0f1`/`099cb05` v6 상향·mojibake 복구)

## 3. PDCA 메타데이터

```yaml
cycle: ci-and-env-standardization
phase: completed
match_rate: 98
plan: docs/01-plan/features/ci-and-env-standardization.plan.md
design: docs/02-design/features/ci-and-env-standardization.design.md
analysis: docs/03-analysis/ci-and-env-standardization.analysis.md
report: docs/04-report/ci-and-env-standardization.report.md
duration_h: 1.5
trigger: 프로젝트 전체 검토 (2026-06-10) 개혁 제안 ①CI + ②환경 표준화
```

## 4. 후속 사이클 권장

| Item | 사이클 | 우선순위 |
|------|--------|---------|
| webcloring-pdf submodule 분리 + selenium/google-api 의존성 이관 | webcloring-pdf-separation | Medium (2026-05 결정, 실행 대기) |
| R6 린트 램프 — B나머지+SIM (잔여 159건 중 ~41) — 이제 CI가 강제 장치 | R6-ruff-bugbear-sim-ramp | Medium |
| 2026-06-10 검토 Quick wins: `/redoc` rate-limit SSOT, `cache.py:47` 죽은 가드, `create_index.py` 정리, `chat.py:82` 죽은 주석 | review-quickwins-202606 | Medium (반나절) |
| rate limiter clock 주입 + bulk_retry 순서 의존 flaky 조사 | rate-limiter-clock-injection | Low (CI에서 flaky 실측 시 상향) |
| FastAPI `ORJSONResponse` deprecation 대응 | 다음 의존성 업그레이드 사이클 | Low (lock 고정으로 당장 무영향) |

## 5. Lessons Learned

- **무핀 의존성의 위험을 사이클 중 실증** — 새 venv에 무핀 설치하자 최신 FastAPI가 들어와 deprecation 경고 + 신규 flaky 양상이 즉시 나타남. lock이 바로 이 문제의 해법이며, "언젠가"가 아니라 지금 고정해야 하는 이유 그 자체였음.
- **CI 러너 조건은 push 전에 로컬로 재현 가능** — `database/`·`.env`를 숨긴 시뮬레이션이 실DB 의존 테스트 12건을 사전 검출, 첫 CI run을 한 번에 green으로 만듦. "첫 실행에서 실측"보다 "선검증 후 push"가 싸다.
- **PowerShell 텍스트 roundtrip은 비ASCII를 깨뜨린다** — `(Get-Content -Raw) -replace ... | Set-Content` 패턴이 한국어 주석·em-dash를 mojibake로 만들어 워크플로 파싱 실패. 파일 수정은 Edit/Write 도구로, CI 설정 주석은 ASCII-only로.
- **액션 생태계도 deprecation 시계가 돈다** — 첫 run의 annotation(Node 20, 6일 뒤 강제)을 즉시 처리해 "만들자마자 깨지는 CI"를 회피. CI 신설 시 annotation 확인을 루틴에 포함할 것.
