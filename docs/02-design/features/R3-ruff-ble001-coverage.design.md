# R3-ruff-ble001-coverage — Design

> **Cycle**: R3-ruff-ble001-coverage
> **PDCA Phase**: Design
> **Date**: 2026-05-28
> **Plan**: [[R3-ruff-ble001-coverage.plan]]

## 1. Architecture / 변경 지점 개요

순수 **툴링/설정 + 잠복 버그 수정** 사이클. 런타임 아키텍처 변경 없음.

```
pyproject.toml
 ├─ [tool.ruff]              ← 신규: target, line-length, exclude
 ├─ [tool.ruff.lint]         ← 신규: select=F,BLE001
 ├─ [tool.ruff.lint.per-file-ignores]  ← 신규: tests
 ├─ [tool.coverage.run]      ← 신규
 ├─ [tool.coverage.report]   ← 신규
 └─ [tool.pytest.ini_options] ← 기존 유지(변경 없음)

requirements-dev.txt          ← 신규: ruff, pytest, pytest-cov

소스 수정(잠복 버그/F):
 ├─ api/tools/items.py        ← import sqlite3 추가 (F821 ×2)
 ├─ api/tools/summary.py      ← import sqlite3 추가 (F821 ×2)
 ├─ shared/validators.py      ← Path 참조 수정 (F821 ×1)
 ├─ scripts/perf_smoke.py     ← import requests 추가/정리 (F821 ×1)
 ├─ tools/db_watcher.py       ← import sqlite3 추가 (F821 ×1)
 ├─ (F401 unused) 다수 파일    ← ruff --fix 자동 제거
 ├─ dashboard/components/charts.py, manager.py ← F841 수동 제거
 ├─ tools/watcher.py          ← F811 중복 정의 정리
 └─ manager.py, tools/{check_models,watcher}.py ← BLE001 narrow/noqa
```

## 2. ruff 설정 (pyproject.toml)

```toml
[tool.ruff]
target-version = "py312"
line-length = 100
extend-exclude = [
    "webcloring-pdf",
    ".venv", ".smoke-venv", ".smoke-venv2",
    "dist", "build",
    "docs", "logs",
    ".pytest_tmp", "__pycache__",
]

[tool.ruff.lint]
# R3 baseline gate — high-signal only. 향후 ramp(R4): I, UP, B904, SIM.
select = ["F", "BLE001"]

[tool.ruff.lint.per-file-ignores]
# 테스트 코드: 미사용 import(픽스처/등록 목적)·광범위 catch는 정당한 경우 多.
# 단 F821/F841/F811(실버그)은 계속 enforce.
"tests/**" = ["F401", "BLE001"]
```

**근거**:
- `select=["F","BLE001"]` — F는 실오류(undefined/unused/redefined), BLE001은 본 사이클 핵심. E501(226)·I(52)·UP(126)·SIM(19)·B(13)는 거대 diff·노이즈라 baseline 측정만 하고 enforce 보류.
- `line-length=100` — 설정만(E501 미select이므로 에러 미발생). 향후 ramp 대비 기준값.
- `extend-exclude` — webcloring-pdf(submodule 예정), 가상환경, 빌드/문서/로그 산출물.

## 3. coverage 설정 (pyproject.toml)

```toml
[tool.coverage.run]
source = ["api", "shared"]
branch = true
omit = ["*/__pycache__/*", "tests/*"]

[tool.coverage.report]
show_missing = true
skip_covered = false
exclude_lines = [
    "pragma: no cover",
    "if TYPE_CHECKING:",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
]
```

**베이스라인 측정 명령**: `python -m pytest --cov --cov-report=term-missing`
**회귀 방지(권장, opt-in)**: 측정된 baseline에서 안전 여유를 둔 floor를 `--cov-fail-under=<floor>`로 CI에서만 적용. **기본 addopts에는 넣지 않음** — 전체 suite의 알려진 flaky(tmpdir race, rate-limit 60s timing)가 일반 `pytest` 실행을 깨지 않도록.

## 4. F821 잠복 버그 수정 상세

| 파일:라인 | 현재 | 수정 |
|---|---|---|
| `api/tools/items.py` | `except (sqlite3.Error, KeyError)` 인데 import 없음 | 파일 상단에 `import sqlite3` 추가 |
| `api/tools/summary.py` | 동일 | `import sqlite3` 추가 |
| `tools/db_watcher.py:56` | `sqlite3.Error` 참조, import 없음 | `import sqlite3` 추가 |
| `shared/validators.py:167` | bare `Path` 참조(함수 내 별칭 `_P`만 존재) | 해당 라인을 `_P`로 교정(또는 모듈 상단 `from pathlib import Path`) — 코드 확인 후 최소 변경 |
| `scripts/perf_smoke.py:43` | `requests` 참조, import 없음 | `import requests` 추가(또는 기존 조건부 import 정리) |

→ 수정 후 `python -c "import api.tools.items, api.tools.summary, shared.validators, tools.db_watcher"` 임포트·로드 성공 확인.

## 5. F401/F541 (autofix) 및 F841/F811 (수동)

- **F401(unused-import) 소스 24건 + F541 2건**: `ruff check <소스dirs> --select F401,F541 --fix` 자동 제거. tests의 F401은 per-file-ignore로 미적용.
- **F841(3건, unsafe-fix)** 수동:
  - `dashboard/components/charts.py:104` `total` — 사용처 없으면 라인 제거
  - `manager.py:104,105` `center`,`radius` — 죽은 계산이면 제거
- **F811(1건)** `tools/watcher.py:103` `get_file_state` 중복 정의 — 의도 확인 후 잘못된 중복 제거(또는 첫 정의가 죽은 코드면 그쪽 제거).

## 6. BLE001 8건 처리 정책 (tools/scripts/manager.py)

R3는 **게이트 통과**가 목표이므로 narrow가 trivial하지 않으면 `# noqa: BLE001`+1줄 사유. 위치:

| 파일:라인 | 처리(예정, 코드 확인 후 확정) |
|---|---|
| `manager.py:52,504,506,511,622,651` (6) | CLI/GUI 최상위 핸들러 추정 → noqa+사유 (R2-2에서 narrow) |
| `tools/check_models.py:23` | 모델 점검 스크립트 최상위 → noqa+사유 |
| `tools/watcher.py:220` | watcher 루프 최상위 → noqa+사유 |

각 noqa는 `# noqa: BLE001 — <사유>` 형식. R2-2에서 narrow로 대체 예정임을 보고서에 명시.

## 7. requirements-dev.txt (신규)

```
# Dev / lint / test tooling (R3-ruff-ble001-coverage)
ruff>=0.15
pytest>=7.0
pytest-cov>=4.0
```

## 8. 게이트 실행 방식 (확정)

| 용도 | 명령 |
|---|---|
| Lint 게이트 | `python -m ruff check .` (설정이 select/exclude 포함하므로 인자 불필요) |
| Lint 자동수정 | `python -m ruff check . --fix` |
| 커버리지 베이스라인 | `python -m pytest --cov --cov-report=term-missing` |
| 회귀 | `python -m pytest` |

## 9. 구현 순서 (Do)

1. `pyproject.toml`에 ruff + coverage 설정 추가
2. F821 5파일 미import 수정(잠복 버그)
3. `ruff --select F401,F541 --fix`로 소스 unused 제거
4. F841/F811 수동 정리
5. BLE001 8건 narrow/noqa
6. `requirements-dev.txt` 생성
7. `ruff check .` → 0 errors 확인 (게이트 green)
8. `pytest --cov` → 베이스라인 % 측정·기록
9. `pytest` 회귀 확인

## 10. Test / 검증 전략

- **게이트**: `ruff check .` exit 0
- **F821 수정**: 대상 모듈 import 성공 + `ruff --select F821` 0
- **회귀**: 핵심 영역 테스트 green (test_tool_schemas, test_db_router, test_notifications 등), 알려진 flaky 제외
- **커버리지**: api/shared 베이스라인 % 기록 + term-missing 상위 갭 보고서 기재
- **베이스라인 통계**: `ruff check . --select E,W,I,UP,B,SIM --statistics`로 미적용 부채 기록(AC9)
