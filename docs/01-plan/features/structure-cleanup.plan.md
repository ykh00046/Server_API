# Plan: structure-cleanup

**Feature**: structure-cleanup
**Author**: PDCA-driven (Opus 4.7)
**Date**: 2026-05-27
**Phase**: Plan

---

## 1. 배경 (Why)

이전 분석(`docs/03-analysis/webhook-admin-ui-v1.analysis.md` 및 code-analyzer 결과)에서
프로젝트 구조 측면의 기술 부채 5건이 보고되었다. 모두 "기능 결함"은 아니지만 다음과 같은
이유로 누적 비용을 발생시킨다.

| 항목 | 발생 비용 |
|------|----------|
| `except Exception` 남용 | 무음 실패(silent failure), 디버깅 시간 증가 |
| `store.py` 577줄 (실측치) | 단일 책임 원칙 위반, 변경 시 회귀 위험 |
| `database.py` 394줄 (실측치) | DBRouter + ATTACH + Connection cache 혼재, 신규 인입 학습 비용 |
| pytest tmpdir Windows PermissionError | 40개 테스트가 실패로 보고 → 진짜 회귀를 가려버림 |
| `pytest.ini`/`pyproject.toml` 부재 | 워닝 필터/마커/testpaths가 사방에 흩어짐 |

> 사용자가 제시한 라인 수(648/489)와 실측치(577/394)에 차이가 있다. 분석 시점 이후
> 일부 리팩토링이 이미 진행되었기 때문이며, **실측 기준**으로 진행한다.

---

## 2. 목표 (What)

### 2.1 In-scope

1. **pytest 설정 통합** — `pyproject.toml`에 `[tool.pytest.ini_options]` 추가
   - `testpaths = ["tests"]`, `tmp_path_retention_policy = "failed"`
   - `filterwarnings` (DeprecationWarning 등) 통합
2. **tmpdir 권한 오류 해결** — `tests/conftest.py`에 `_close_db_connections` autouse fixture
   - `api.notifications.store._local` + `shared.database._local` 양쪽 강제 close
   - pytest cleanup 전에 SQLite handle 해제 → PermissionError 0건
3. **`api/notifications/store.py` 분해** (577 → 100줄대 facade + 4 모듈)
   - `api/notifications/_store_connection.py` — `_get_conn`, `_ensure_schema*`, `reset_for_tests`
   - `api/notifications/_store_models.py` — `WebhookRecord`, `ClaimedDelivery`, `_row_to_*`
   - `api/notifications/webhooks_repo.py` — `create_webhook`, `get_record/public`, `list_*`, `update`, `delete`
   - `api/notifications/deliveries_repo.py` — pending/finalize, enqueue/claim/record_attempt, queue_stats, requeue, list
   - `api/notifications/store.py` — 100% **하위 호환 facade** (re-export only)
4. **`shared/database.py` 분리** (394 → 250줄대)
   - `shared/_db_connection.py` — `_get_db_mtime`, `_apply_pragma_settings`, `_cleanup_all_connections`, thread-local cache
   - `shared/_db_attach.py` — `attach_archive_safe`
   - `shared/database.py` — `DBTargets` + `DBRouter` 만 (위 두 모듈에서 import)
   - `attach_archive_safe`는 기존 import 경로(`from shared.database import attach_archive_safe`) 유지
5. **`except Exception` 좁히기 (보수적)** — **고위험 무음 실패만 타겟**
   - `api/notifications/store.py:60, 159` (cached.close / reset_for_tests close) → `except sqlite3.Error`
   - `api/routers/system.py:111-118` (statvfs fallback) → `except (AttributeError, OSError)`
   - `api/routers/records.py:44` (return None) → `except (ValueError, TypeError)` 명시 + 주석
   - 나머지(top-level handler, AI 호출 등 광범위 catch)는 **그대로 둔다** —
     이미 의도된 광범위 캐치이고 logger.exception이 걸려 있다

### 2.2 Out-of-scope

- 새로운 기능 추가
- `webcloring-pdf/` 서브모듈 내부 (별도 저장소)
- `manager.py` / `dashboard/` 의 `except Exception` (UI 레이어 광범위 캐치는 고의)
- pytest 마커/플러그인 추가 (현재 자연어 collection으로 충분)

---

## 3. 성공 기준 (Acceptance Criteria)

| # | 기준 | 검증 방법 |
|---|------|----------|
| AC1 | `pyproject.toml`에 `[tool.pytest.ini_options]` 존재, `testpaths`/`tmp_path_retention_policy` 설정 | `cat pyproject.toml` |
| AC2 | `pytest tests/` 실행 시 `PermissionError` 0건 (tmpdir cleanup 정상) | `pytest tests/ -q` |
| AC3 | `pytest tests/` **전체 통과** (이전 247 passed → ≥ 285 passed, 0 errors) | `pytest tests/ -q` |
| AC4 | `api/notifications/store.py` ≤ 130줄 (facade only) | `wc -l` |
| AC5 | 신규 5개 모듈(`_store_connection.py`, `_store_models.py`, `webhooks_repo.py`, `deliveries_repo.py`, `_db_connection.py`, `_db_attach.py`) 존재 | `ls` |
| AC6 | `shared/database.py` ≤ 280줄 (DBRouter + DBTargets) | `wc -l` |
| AC7 | 기존 import 경로 모두 유지 — `from api.notifications.store import *` 호출자(events, worker, routers, tests) 무변경 | `grep` + 테스트 |
| AC8 | `from shared.database import attach_archive_safe` 호출자(api/tools/custom.py 등) 무변경 | `grep` + 테스트 |
| AC9 | store/database의 무음 `except Exception: pass` 4곳을 명시적 예외로 좁힘 | `git diff` |
| AC10 | 신규 추가 코드에 회귀 테스트 0건 추가 (기존 288개 테스트로 회귀 감지 충분) | — |

---

## 4. 리스크 & 완화

| 리스크 | 가능성 | 영향 | 완화책 |
|--------|-------|------|--------|
| store.py 분해 시 import cycle | 중 | 중 | facade 패턴 + 단방향 의존 (`models ← connection ← repos ← store`) |
| tmpdir fixture가 prod 코드에 영향 | 낮 | 중 | autouse 범위를 `scope="function"`으로 한정, 테스트 종료 시 close만 호출 |
| pyproject.toml 추가로 기존 도구(black/ruff)와 충돌 | 낮 | 낮 | `[tool.pytest.ini_options]` 섹션만 추가, 기타는 손대지 않음 |
| 광범위 except를 좁히다 진짜 예외 누락 | 중 | 중 | 보수적으로 4곳만 손대고, 다 보존하는 항목은 **명시적으로 유지** |

---

## 5. 일정

1단계 코드 작성 (Do 단계)에서 다음 순서로 진행:

1. **pyproject.toml** 작성 (AC1)
2. **conftest.py** fixture 추가 → 이 시점에서 `pytest` 재실행하여 AC2/AC3 1차 확인
3. **store.py 분해** (AC4/AC5/AC7) → `pytest` 재실행
4. **database.py 분리** (AC5/AC6/AC8) → `pytest` 재실행
5. **except 좁히기** (AC9) → 최종 `pytest`

각 단계마다 별도 커밋 (사용자 메모리: "PDCA commit granularity — split by logical layer per phase").

---

## 6. 참고

- 기존 분석 보고서: `docs/03-analysis/webhook-admin-ui-v1.analysis.md`
- 사용자 메모리:
  - `feedback_commit_style.md` — phase별 layer commit
  - `project_webhook_subsystem.md` — webhook 구조
  - `project_review_fixes_202604_part2.md` — products.py 분해 패턴
