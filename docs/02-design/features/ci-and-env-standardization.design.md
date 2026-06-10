# ci-and-env-standardization — Design

> **Cycle**: ci-and-env-standardization
> **PDCA Phase**: Design
> **Date**: 2026-06-10
> **Plan**: [[ci-and-env-standardization.plan]]

## 0. 설계 원칙

1. **코드 로직 diff 0** — 이번 사이클의 산출물은 워크플로 YAML, lock 파일, 문서뿐. `api/`/`shared/`/`dashboard/` 및 `pyproject.toml`은 손대지 않는다(Plan AC8).
2. **단일 정본(SSOT) 환경** — "py3.12 Windows venv에서 freeze한 단일 lock"이 로컬 재구축과 CI 설치의 공통 원천. 환경 정의가 두 곳으로 갈라지지 않게 한다.
3. **게이트는 기존 설정을 그대로 호출** — CI는 `ruff check .`(select는 pyproject가 결정), `pytest`(addopts는 pyproject가 결정)를 호출만 한다. 규칙을 YAML에 중복 정의하지 않는다. 유일한 CI 전용 추가는 `--cov-fail-under`(pyproject 주석의 약속).
4. **첫 실행 리스크는 Do 단계에서 로컬 시뮬레이션으로 선제 검증** — Linux 러너에서만 드러날 조건(DB 파일 부재, .env 부재)을 push 전에 로컬로 재현해 본다.

## 1. 확정된 설계 결정 3건

### 1.1 CI 의존성 서브셋 — **만들지 않는다 (단일 full lock)**

실측 근거: 테스트 스위트는 **의도적으로 streamlit-free**다. `tests/` 전체에서 `streamlit`/`customtkinter`/`pystray`/`plotly`/`selenium` top-level import **0건**(grep 실측). `test_webhook_admin_ui.py:19-23`은 streamlit을 끌어들이지 않으려고 `importlib`로 streamlit-free 서브모듈(`api_client`, `formatters`)만 직접 로드하고, views.py는 소스 텍스트 검사로 대체한다.

그럼에도 서브셋 lock(`requirements-ci.txt`)을 **만들지 않는 이유**:
- lock 이원화는 drift 표면을 하나 더 만든다(테스트가 새 의존성을 쓰면 두 파일 동기화 필요).
- 전체 의존성(streamlit, customtkinter, pystray 포함)은 모두 Linux wheel/순수 파이썬으로 headless 설치 가능 — import만 안 하면 된다.
- 설치 시간은 `actions/setup-python`의 pip 캐시로 흡수(NFR ≤10분 대비 충분).
- 단일 lock = "로컬 venv 재구축"과 "CI 설치"가 같은 파일 → 원칙 2 충족.

### 1.2 Lock 형식과 갱신 절차 — `pip freeze` 단일 파일

```
requirements.txt        ← 사람이 읽는 top-level 선언 (무핀 유지, 불변)
requirements-dev.txt    ← dev 도구 top-level (>= 하한 유지, 불변)
requirements.lock.txt   ← [신규] 정본 venv의 pip freeze 전체 스냅샷 (runtime+dev 통합)
```

- lock은 **runtime + dev를 한 파일에** 담는다(ruff/pytest/pytest-cov 포함). lint job이 같은 ruff 버전을 쓰게 하기 위함.
- 헤더 주석에 생성 커맨드·날짜·파이썬 버전 기록.

**갱신 절차(README에 그대로 수록할 4줄)**:
```powershell
# 의존성 추가/변경 시: requirements*.txt 수정 후
.\.venv\Scripts\python -m pip install -r requirements.txt -r requirements-dev.txt
.\.venv\Scripts\python -m pip freeze > requirements.lock.txt
# requirements*.txt 와 lock 을 같은 커밋으로
```

**플랫폼 마커 리스크**: Windows freeze에 Windows 전용 전이 의존성(예: `colorama`는 cross-platform이라 무해, `pywin32` 계열이 문제)이 박힐 수 있다. 현 의존성 트리에서 pywin32 계열은 없을 것으로 예상하나 **Do 단계에서 freeze 산출물을 육안 검사**하고, 발견 시 해당 라인에 `; sys_platform == "win32"` 마커를 수동 부착한다(이 수동 편집은 lock 헤더 주석에 명시).

### 1.3 `--cov-fail-under` baseline — **66** (실측 71% − 5%p)

2026-06-10 실측(py3.13, 360 passed, branch coverage):
```
TOTAL  2762 stmts  742 miss  616 branch  97 partial  → 71%
```
- floor = **66%** (보수 마진 5%p — 러너/버전 차이에 따른 ±1~2%p 변동 흡수).
- 측정 인터프리터 각주: 위 71%는 py3.13(당시 시스템 환경) 실측. py3.12 정본 venv의 CI 조건 시뮬레이션(빈 fixture DB)에서는 **70%** — 빈 DB로 데이터 경로 분기가 덜 실행된 차이. floor 66은 양쪽 모두 −4~5%p 마진으로 유효, 결론 불변.
- 참고: `shared/ui/*`(theme.py 등 streamlit 헬퍼)가 0%로 전체를 끌어내리고 있음 — coverage `source`에서 빼는 것도 가능하나 **pyproject 불변 원칙**에 따라 이번엔 그대로 두고, floor 상향+source 조정은 커버리지 램프 후속 사이클로.

## 2. `.github/workflows/ci.yml` 상세

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

permissions:
  contents: read

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-python@v6
        with:
          python-version: "3.12"
      - name: Install ruff (lock-pinned version)
        run: pip install "ruff==$(grep -E '^ruff==' requirements.lock.txt | cut -d= -f3)"
      - name: Ruff gate (select inherited from pyproject.toml)
        run: ruff check .

  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-python@v6
        with:
          python-version: "3.12"
          cache: pip
          cache-dependency-path: requirements.lock.txt
      - name: Install dependencies (locked)
        run: pip install -r requirements.lock.txt
      - name: Create empty fixture DB   # §4 S1 우회 경로 — 실제 채택됨 (아래 노트)
        run: ...                        # production_records 빈 스키마 생성 (구현 ci.yml 참조)
      - name: Pytest + coverage floor (CI-only, per pyproject comment)
        run: python -m pytest tests/ -q --cov --cov-report=term --cov-fail-under=66
```

> **구현 중 확정 사항(2026-06-10)**:
> - 액션 버전은 `checkout@v6` / `setup-python@v6` — 첫 run의 Node 20 deprecation annotation(2026-06-16 Node 24 강제) 대응으로 `@v4`/`@v5`에서 상향, 상향 후 run green 확인.
> - §4 S1 시뮬레이션에서 실DB 의존 테스트 12건이 확인되어, 사전 허용해 둔 우회 경로(빈 `production_records` fixture DB step)가 실제 채택됨.
> - lint job의 ruff 버전 추출에 `tr -d '\r'` 추가 — Windows CRLF lock 체크아웃 방어.

설계 노트:
- **lint job은 lock 전체를 설치하지 않는다** — ruff 단일 설치(수 초). 단 버전은 lock에서 추출해 로컬과 동일 보장.
- **test job의 pip 캐시 키 = lock 파일** — lock이 바뀔 때만 캐시 무효화.
- `--cov`/`--cov-fail-under`는 CI 커맨드라인에만 존재. 로컬 `pytest` 동작 불변(원칙 3).
- 환경변수/시크릿 **불설정**: `GEMINI_API_KEY` 부재 시 FakeClient 경로([[feedback_gemini_tool_schema]]), `WEBHOOK_WORKER_ENABLED=0`은 conftest가 자체 설정, `.env` 부재는 `load_dotenv` no-op.
- `tmp_path_retention_policy="all"` + `.pytest_tmp` 프로젝트 내 라우팅(conftest.py:23-26)은 Linux에서도 동일 동작 — 일회용 러너라 누적 무해.

## 3. 로컬 정본 venv 재구축 절차 (Do 체크리스트 §1)

```powershell
# 1) 고아 WSL venv 제거 (POSIX 레이아웃, 이 머신에 WSL 배포판 없음 — 2026-06-10 실측)
Remove-Item -Recurse -Force .venv

# 2) py3.12 Windows venv 생성 (Astral CPython 3.12.12, py launcher 등록 확인됨)
py -V:Astral/CPython3.12.12 -m venv .venv

# 3) 의존성 설치 + lock 생성
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\python -m pip install -r requirements.txt -r requirements-dev.txt
.\.venv\Scripts\python -m pip freeze > requirements.lock.txt

# 4) 게이트 실측 (AC5/AC6)
.\.venv\Scripts\python -m pytest tests/ -q          # 360+ green
.\.venv\Scripts\python -m ruff check .              # All checks passed
```

- `.smoke-venv`/`.smoke-venv2`(WSL smoke용 잔재)는 건드리지 않음 — gitignore 대상이고 smoke 스크립트 경로는 README에서 "선택(Linux/WSL)"로 강등만.

## 4. CI 첫 실행 전 로컬 시뮬레이션 (Do 체크리스트 §2)

Linux 러너에서만 드러날 조건을 push 전에 재현:

| # | 시뮬레이션 | 방법 | 통과 기준 |
|---|-----------|------|----------|
| S1 | **DB 파일 부재** (러너엔 `database/*.db` 없음) | `database/`를 임시 rename 후 `pytest tests/ -q` | 360+ green (테스트는 tmp DB를 자체 생성/monkeypatch — conftest `_close_db_connections`가 전제) |
| S2 | **.env 부재** | `.env` 임시 rename 후 동일 실행 | green (config 기본값 경로) |
| S3 | **freeze lock 재설치 가능성** | 새 임시 venv에 `pip install -r requirements.lock.txt` | 에러 0 |

S1/S2 실패 시: 실패 테스트가 실DB/실env에 암묵 의존하는 것이므로 **이번 사이클에선 ci.yml에 최소 fixture(빈 DB 생성 step)를 추가하는 쪽으로 우회**하고, 테스트 자체 수정은 별도 사이클로 분리(코드 불변 원칙).

## 5. README 변경 설계

| 절 | 변경 |
|----|------|
| 설치 §2 가상환경 | `python -m venv` → py3.12 명시 + lock 설치 경로 추가 (`pip install -r requirements.lock.txt` 권장, top-level 설치는 의존성 변경 시) |
| 테스트 절 | lock 갱신 절차 4줄 추가 (§1.2의 블록 그대로) |
| 신규 "CI" 절 | 워크플로 개요 2줄 + 배지(`![CI](https://github.com/ykh00046/Server_API/actions/workflows/ci.yml/badge.svg)`) |
| 스모크 절 | "Linux/WSL 선택 경로"로 명시 강등(이 머신 WSL 부재 사실 반영) |

## 6. 구현 순서 (커밋 계층 — [[feedback_commit_style]])

| # | 커밋 | 내용 | 검증 |
|---|------|------|------|
| 1 | `chore(env): py3.12 정본 venv + requirements.lock.txt` | venv 재구축(로컬), lock 생성·커밋 | AC5, AC6, S3 |
| 2 | `ci: GitHub Actions lint+test 워크플로 신설` | `.github/workflows/ci.yml` | S1, S2 로컬 선검증 → push → AC2 (Actions green) |
| 3 | `docs: README 환경/테스트/CI 절 동기화` | §5 변경 | AC7 |

## 7. Acceptance Criteria 매핑 (Plan §8 ↔ Design)

| AC | Design 근거 |
|----|------------|
| AC1 (ci.yml 2-job) | §2 — lint/test, push(main)+PR, py3.12 |
| AC2 (Actions green) | §4 선검증 후 push, run URL 확보 |
| AC3 (baseline 기록+floor) | §1.3 — 실측 71%, floor 66 |
| AC4 (lock + CI 설치) | §1.2, §2 test job |
| AC5 (로컬 py3.12 venv green) | §3-4) pytest 실측 |
| AC6 (venv ruff 클린) | §3-4) ruff 실측 |
| AC7 (README 갱신) | §5 |
| AC8 (pyproject 불변) | 원칙 1·3 — diff 검사 |
| AC9 (gap ≥90%) | Check 단계 |

## 8. 리스크 잔여 (Plan §9 대비 갱신)

- ~~커버리지 baseline 미지~~ → **해소**: 71% 실측, floor 66.
- ~~CI 의존성 서브셋 미정~~ → **해소**: 단일 full lock (§1.1).
- ~~Windows 전용 전이 핀~~ → **해소(2026-06-10)**: freeze 산출물 육안 검사 결과 pywin32 계열 0건, colorama(cross-platform)만 — 수동 마커 불필요.
- ~~S1 fixture step 가능성~~ → **확정**: S1에서 실DB 의존 12건 검출, 빈 fixture DB step 채택(§2 노트).
- **잔존**: Linux 러너 타이밍 flaky(`test_rate_limiter.py` sleep 기반) — 1차 관찰, 재발 시 `rate-limiter-clock-injection` 사이클 분리. 추가 관찰 대상: `test_notifications_bulk_retry.py` worker dispatch 계열 간헐 실패(전체 스위트 순서 의존 추정, 단독/재실행 green).
