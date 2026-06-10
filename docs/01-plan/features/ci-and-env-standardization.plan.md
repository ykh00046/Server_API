# ci-and-env-standardization — Plan

> **Cycle**: ci-and-env-standardization
> **PDCA Phase**: Plan
> **Date**: 2026-06-10
> **Project**: Production Data Hub API
> **Summary**: 지금까지 사람 손에만 의존하던 품질 게이트(ruff/pytest/coverage)를 **GitHub Actions CI로 강제**하고, 조각난 로컬 실행 환경(고아 WSL venv + 시스템 Python 3.13 혼용, 무핀 의존성)을 **py3.12 정본 venv + 핀 고정 lock**으로 표준화한다.

## 1. Background

2026-06-10 전체 프로젝트 검토에서 확인된 사실(전부 실측):

1. **CI 부재** — `.github/` 없음, pre-commit 없음. ruff 게이트(F/BLE001/I/UP/B904)와 pytest 360개는 전부 수동 실행에 의존한다. `pyproject.toml:46-47` 주석조차 "커버리지 floor는 **CI에서만** 적용"이라 쓰여 있으나 정작 CI가 존재하지 않는다. R6+ 린트 램프, coverage floor, 회귀 방지 모두 강제 장치가 없는 상태.
2. **실행 환경 조각화** —
   - 프로젝트 `.venv`은 POSIX 레이아웃(WSL용)인데 **이 머신에 WSL 배포판이 없어**(`wsl --list` 실패 실측) 사실상 고아 상태.
   - 실제 테스트는 시스템 **Python 3.13**(`C:\...\Python313\python.exe`)에서 실행됨(360 passed, 17.43s 실측). 그러나 ruff `target-version = "py312"`.
   - PATH의 ruff는 무관한 외부 venv(`hermes-agent`) 소속 0.15.10.
   - → "어느 인터프리터가 정본인가"가 코드 어디에도 정의돼 있지 않다.
3. **의존성 무핀** — `requirements.txt` 전 항목 버전 미지정. `pip install` 시점에 따라 동작이 달라질 수 있고, CI 재현성의 전제가 없다. (`requirements-dev.txt`는 `>=` 하한만, `requirements-smoke.txt`도 무핀.)
4. **전제 확인** — origin은 GitHub(`github.com/ykh00046/Server_API`) → GitHub Actions 사용 가능. 테스트는 Gemini 실호출 없이 FakeClient로 오프라인 동작([[feedback_gemini_tool_schema]]) → CI에 시크릿 불필요. 과거 WSL에서 스위트가 돌았으므로 Linux 러너 호환성 전례 있음.

## 2. Goal

1. **GitHub Actions CI 신설** — push(main) + PR 트리거. 2-job 구성:
   - `lint`: `ruff check .` (pyproject 게이트 그대로)
   - `test`: `pytest --cov` + `--cov-fail-under=<baseline>` (floor는 CI에만, addopts 불변 — pyproject 주석의 약속 이행)
2. **커버리지 baseline 실측·문서화** — 현재 api/shared 커버리지를 측정해 floor를 "실측치 − 5%p" 보수값으로 설정(인플레 방지, 점진 상향은 후속 램프).
3. **의존성 핀 고정** — 정본 venv에서 `pip freeze` 기반 lock 파일(`requirements.lock.txt`) 생성. CI는 lock으로 설치, `requirements.txt`는 사람이 읽는 top-level 선언으로 유지.
4. **로컬 정본 환경 재구축** — Windows 네이티브 **Python 3.12** venv(`.venv` 교체. 머신에 Astral CPython 3.12.12 설치 확인됨). ruff target과 런타임 일치.
5. **README 환경/테스트 절 동기화** — 설치 절차를 정본 venv 기준으로 갱신, CI 배지/절차 추가. (WSL smoke 경로 서술은 "선택"으로 강등.)
6. **기존 동작 100% 보존** — 코드 로직 변경 0. 변경은 CI 설정 + lock + 문서 + 로컬 환경뿐.

## 3. Non-Goals (defer)

- **webcloring-pdf 분리·의존성 이관** — `requirements.txt`의 selenium/google-api 계열 분리는 submodule 분리 사이클([[project_structure_cleanup_202605]] 결정사항)에서 함께 수행. 이번엔 핀만 고정.
- **R6 린트 램프(B나머지+SIM, 잔여 159건)** — CI가 생긴 뒤 별도 사이클.
- **rate limiter clock 주입 리팩터** — `test_rate_limiter.py`의 `time.sleep` 기반 테스트가 CI에서 flaky로 판명되면 후속 사이클(`rate-limiter-clock-injection`)로 분리. 이번 사이클에선 관찰만.
- **pre-commit 훅** — CI가 1차 강제 장치. 로컬 훅은 선택 과제로 defer.
- **uv / pip-tools 도입** — 신규 도구 없이 stdlib pip + freeze로 시작. lock 갱신이 고통스러워지면 그때 도구 도입 검토.
- **Windows 러너 CI** — 1차는 ubuntu 단일. Windows 특이 사항(tmproot 등)은 로컬에서 이미 커버.

## 4. Dependencies

| 종류 | 항목 | 상태 |
|------|------|------|
| 인프라 | GitHub Actions (origin = github.com) | ✅ 사용 가능 |
| 로컬 | Astral CPython 3.12.12 (py launcher 등록 확인) | ✅ 설치됨 |
| 시크릿 | 없음 — 테스트는 FakeClient 오프라인 | ✅ 불필요 |
| 코드 변경 | — | **0** (설정/문서/환경만) |
| 신규 외부 런타임 의존성 | — | **0** |

## 5. Scope (대상)

| 구분 | 대상 |
|---|---|
| **신규 파일** | `.github/workflows/ci.yml`, `requirements.lock.txt` |
| **수정 파일** | `README.md`(설치/테스트/CI 절), 필요 시 `requirements-dev.txt`(핀 정합) |
| **로컬 작업(비커밋)** | `.venv` 삭제 후 py3.12 Windows venv 재생성 + 전체 의존성 설치 |
| **제외** | 모든 `api/`/`shared/`/`dashboard/` 코드, `webcloring-pdf/`, pyproject의 ruff select·pytest addopts |

## 6. Functional Requirements

| ID | 요구사항 | 우선순위 |
|----|---------|---------|
| FR-01 | PR 및 main push 시 `ruff check .`이 자동 실행되어 실패 시 머지 차단 신호 제공 | High |
| FR-02 | 동일 트리거로 pytest 전체(360+)가 Linux 러너에서 실행 | High |
| FR-03 | CI test job에 `--cov-fail-under=<baseline>` 적용, 로컬 addopts는 불변 | High |
| FR-04 | CI 의존성 설치는 `requirements.lock.txt` 기반(재현성) | High |
| FR-05 | lock은 정본 py3.12 venv의 freeze 산출물이며 갱신 절차가 README에 1단락으로 문서화 | Medium |
| FR-06 | 로컬 `.venv`이 Windows py3.12로 재구축되어 `python -m pytest` / `python -m ruff` 모두 venv 내부에서 동작 | High |
| FR-07 | CI는 pip 캐시를 사용해 반복 실행 시간을 단축 | Low |

## 7. Non-Functional Requirements

| 범주 | 기준 | 측정 |
|------|------|------|
| 재현성 | 동일 lock → 동일 패키지 셋 (CI/로컬) | `pip freeze` diff |
| 속도 | CI 전체 ≤ 10분 (로컬 17.4s 기준, 설치 포함 여유) | Actions 로그 |
| 호환성 | 기존 360 테스트 Windows 로컬 + Linux CI 양쪽 green | pytest |
| 불변성 | 코드 로직 diff 0 (`git diff --stat`이 설정/문서만) | diff 검사 |

## 8. Acceptance Criteria

| # | Criterion | 측정 |
|---|-----------|---|
| AC1 | `.github/workflows/ci.yml` 신규 — lint/test 2-job, push(main)+PR 트리거, python 3.12 | 파일 |
| AC2 | 실제 GitHub Actions 실행이 **green** (push 후 run 링크 확보) | Actions run |
| AC3 | 커버리지 baseline 실측치가 Plan/Design 문서에 기록되고 floor = 실측−5%p로 CI에 설정 | 문서+yml |
| AC4 | `requirements.lock.txt` 신규 — py3.12 venv freeze, CI가 이것으로 설치 | 파일+yml |
| AC5 | 로컬 `.venv` = Windows py3.12, 그 안에서 pytest 360+ green 재확인 | pytest 실측 |
| AC6 | 그 venv의 ruff로 게이트 클린 (`All checks passed`) | ruff 실측 |
| AC7 | README 설치/테스트 절이 새 환경 기준으로 갱신(고아 WSL 서술 정리) | diff |
| AC8 | pyproject.toml 변경 없음 (addopts/select 불변 약속 검증) | diff |
| AC9 | gap-detector match rate ≥ 90% | Check |

## 9. Constraints / Risks

- **Linux 러너 호환성**: 스위트는 과거 WSL에서 동작했으나 마지막 검증은 2026-03(smoke). `conftest.py`의 `PYTEST_DEBUG_TEMPROOT` 라우팅([[project_pytest_tmproot_strategy]])은 Windows 잠금 회피용 — Linux에서도 무해해야 하나 **첫 CI run에서 실측 확인 필요**. 실패 시 conftest의 OS 분기 추가는 허용 범위(테스트 인프라 코드만).
- **타이밍 flaky**: `test_rate_limiter.py`의 `time.sleep(1.1~1.6)` 기반 테스트는 부하 걸린 공용 러너에서 flaky 가능성. 1차 대응은 관찰(재실행), 구조적 해법(clock 주입)은 Non-Goal로 분리 — CI 도입 사이클에 테스트 리팩터를 섞지 않는다.
- **GUI 의존성의 Linux 설치**: `customtkinter`/`pystray`/`streamlit-shadcn-ui`가 headless Linux에서 import 에러 없이 설치돼야 한다(테스트가 manager.py를 import하지 않으므로 위험 낮음, `test_webhook_admin_ui`는 streamlit AppTest 사용 → streamlit 필수). 설치 실패 시 CI 전용 requirements 서브셋은 Design에서 결정.
- **lock 부패**: freeze-lock은 갱신을 잊으면 requirements.txt와 어긋난다. → README에 갱신 절차 명시 + lock과 top-level의 불일치는 CI 설치 실패로 자연 검출되는 구조 유지.
- **3.13→3.12 다운시프트**: 현재 시스템 3.13에서 green이지만 정본은 3.12로 내려간다. 3.12는 ruff target이자 기존 `.venv`(WSL)의 버전이라 회귀 위험 낮음 — 단 AC5에서 반드시 실측.
- **커밋 분리**([[feedback_commit_style]]): (a) lock+venv 문서, (b) ci.yml, (c) README 동기화 — 계층별 분리 커밋.

## 10. Out-of-band Notes

- **후속 사이클 예고**: `webcloring-pdf-separation`(submodule + 의존성 이관), `R6-ruff-bugbear-sim-ramp`(잔여 159건), 필요 시 `rate-limiter-clock-injection`.
- **이번 검토(2026-06-10)에서 나온 Quick wins**(별도 소사이클 후보): `/redoc` rate-limit 스킵 SSOT 통일(main.py:166 → `is_public_path`), `cache.py:47` id() 죽은 가드 제거, `tools/create_index.py` 정리(정본 = `db_maintenance` 6종 인덱스), `chat.py:82` 죽은 주석 정리.
- **메모리 참조**: [[project_lint_ramp_r3_r4]], [[project_pytest_tmproot_strategy]], [[feedback_gemini_tool_schema]], [[feedback_commit_style]], [[project_structure_cleanup_202605]]
