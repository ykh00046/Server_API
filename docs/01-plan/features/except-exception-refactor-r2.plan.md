# except-exception-refactor-r2 — Plan

> **Cycle**: except-exception-refactor-r2
> **PDCA Phase**: Plan
> **Date**: 2026-05-27
> **Predecessors**: 이전 R1 code-analyzer 보고서(15파일 34곳 → 재측정 결과 본 프로젝트 32파일 78곳)
> **Round**: R2 (2차)

## 1. Background

R1 round의 code-analyzer 보고서는 "except Exception 남용 — 15파일 34곳"으로 추정했지만, R2 round에서 재측정한 결과:

| 측정 범위 | 파일 수 | 발생 횟수 |
|---|---|---|
| 전체 (Server_API + webcloring-pdf submodule) | 56 | 198 |
| **본 프로젝트만 (webcloring-pdf 제외)** | **32** | **~78** |
| tests/ 제외 | 30 | 76 |

`webcloring-pdf/`는 [[project_structure_cleanup_202605]]에서 submodule 분리 결정된 별도 프로젝트이므로 본 사이클 범위에서 제외한다.

**실제 위험 패턴** (즉시 수정 필요):

| 위치 | 패턴 | 위험 |
|---|---|---|
| `api/notifications/store.py:60, 159` | `except Exception: pass` (connection close) | sqlite3 외 OSError 등 silent swallow |
| `api/routers/system.py:111, 117` | `except Exception: pass` (statvfs/shutil fallback) | AttributeError/OSError 외 모두 무음 |
| `api/routers/records.py:44` | `except Exception: return None` (cursor decode) | JSON/base64 외 진짜 버그 은닉 |
| `api/notifications/dispatcher.py:96` | `except Exception` (webhook outbound) | httpx 외부 의존, 너무 광범위 |
| `api/notifications/worker.py:104, 169` | `except Exception` (worker loop) | 의도적이지만 정당화 주석 부재 |

**적절한 패턴** (유지 또는 narrow):

| 위치 | 패턴 | 판단 |
|---|---|---|
| `api/tools/{items,summary,custom}.py` (10곳) | Gemini tool boundary → `return {"status": "error", "message": str(e)}` | 정당 — AI tool 인터페이스 계약. 단 narrow 가능하면 적용 |
| `api/chat.py:280, 301, 333` | provider fallback + top-level | logger.exception 존재 → 유지, 정당화 주석 추가 |
| `api/_chat_stream.py:237` | SSE top-level | 정당 — SSE는 죽이지 말아야 함 |

## 2. Goal

본 프로젝트(`webcloring-pdf` 제외)의 `except Exception` 78곳을 3개 등급으로 분류 후 다음을 달성:

1. **무음 실패 패턴 0개** — `except Exception: pass` / `return None` 류 전부 narrow exception + 로그 (또는 명시적 `contextlib.suppress(...)`)로 치환
2. **catch-all 좁히기** — narrow exception 매핑이 가능한 곳은 좁힌다 (sqlite3.Error, OSError, httpx.HTTPError 등)
3. **정당화 주석** — 의도적 catch-all에는 `# noqa: BLE001` + 1줄 사유 주석 추가
4. **회귀 0건** — 기존 pytest suite green 유지

## 3. Non-Goals (defer to v2+)

- `webcloring-pdf/` submodule 리팩터 (별도 프로젝트, 별도 PR)
- `tests/`의 `except Exception` (테스트 코드는 catch-all이 정당한 경우 多)
- `tools/`, `scripts/`, `manager.py` (운영 유틸리티) — 별도 사이클 R2-2에서
- 새로운 lint 규칙 도입 (`ruff BLE001` 설정 추가 등) — R3 round에서 차단 도입
- catch 후 raise 패턴 변경 (이미 raise되는 곳은 유지)

## 4. Dependencies

| 종류 | 항목 | 상태 |
|------|------|------|
| Python | `httpx` (이미 사용) | ✅ |
| Python | `sqlite3` (stdlib) | ✅ |
| Python | `contextlib.suppress` (stdlib, 명시적 catch-all 표기용) | ✅ |
| Test | pytest 회귀 suite | ✅ (단, tmpdir 권한 이슈 별도 존재 — 무관) |
| 신규 외부 의존성 | — | **0** |

## 5. Scope (대상 파일 범위)

본 PDCA에서 다루는 파일은 다음 7개 영역으로 한정:

| 영역 | 파일 | 위치 수 |
|---|---|---|
| **A. notifications** | `api/notifications/{store,worker,dispatcher,events}.py` | 6 |
| **B. routers** | `api/routers/{system,records}.py` | 5 |
| **C. chat & stream** | `api/{chat,_chat_stream,_gemini_client}.py` | 6 |
| **D. tools (Gemini boundary)** | `api/tools/{items,summary,custom}.py` | 8 |
| **E. shared infra** | `shared/{database,db_maintenance,cache,process_utils}.py` | 10 |
| **F. dashboard core** | `dashboard/data.py`, `dashboard/components/ai_section.py`, `dashboard/components/webhook_admin/{api_client,views}.py`, `dashboard/pages/webhooks.py` | 10 |
| **G. portal & misc** | `portal_settings_dialog.py` | 1 |
| **합계** | | **~46** |

남은 ~32곳(tools/, scripts/, manager.py, tests/)은 R2-2 round로 미룬다.

## 6. Acceptance Criteria

| # | Criterion | 측정 방법 |
|---|-----------|---|
| AC1 | A~G 영역의 `except Exception: pass` 패턴이 0개 | `rg "except Exception:\s*$\n\s*pass" --multiline` 결과 0 |
| AC2 | A~G 영역의 `except Exception:\n    return None` 패턴이 0개 (정당화 주석 없으면) | grep + 시각 검사 |
| AC3 | 무음 패턴을 대체할 때 narrow exception (sqlite3.Error, OSError, httpx.HTTPError, json.JSONDecodeError, binascii.Error, UnicodeDecodeError 등) 사용 | diff 시각 검사 |
| AC4 | 유지되는 catch-all (top-level handler 등)은 `# noqa: BLE001` 또는 1줄 사유 주석 필수 | grep으로 검증 |
| AC5 | A~G 영역 전체 `except Exception` 건수가 **30곳 이하로 감소** (현재 ~46 → 최소 35% 감소) | rg count |
| AC6 | `pytest tests/` 회귀 통과 (tmpdir 권한 이슈는 R2의 별도 항목이므로 제외) | pytest 실행 결과 |
| AC7 | `python -c "import api.notifications.store, api.routers.system, api.routers.records, api.notifications.dispatcher, api.notifications.worker"` 임포트 성공 | shell 실행 |
| AC8 | 수정한 핵심 모듈 한정 smoke test (`/queue/stats`, `/healthz`, `/notifications/webhooks` GET) 200 응답 | 수동 또는 자동 |
| AC9 | gap-detector match rate ≥ 90% (목표 ≥ 95%) | Check phase |

## 7. Constraints / Risks

- **로그 폭증 위험**: 빈번한 catch-all에 `logger.exception`을 무조건 추가하면 정상 동작(예: connection close 시 이미 닫힌 경우)도 로그를 남긴다. → DEBUG 수준 사용 또는 narrow exception로 정상 케이스 분기.
- **동작 변화 위험**: catch-all을 좁히면 기존에 silently 잡히던 진짜 예외가 propagate된다. → 좁히는 범위는 **현재 silently 잡히던 정상 케이스만 포함**하도록 보수적 선택.
- **테스트 환경 격리**: pytest tmpdir 권한 오류(R2 분석 항목 #4)는 본 사이클과 무관 — 수정한 모듈만 부분 실행으로 우회.
- **Gemini tool 인터페이스**: `api/tools/*`의 `return {"status": "error", ...}` 패턴은 LLM 계약이므로 형태 유지 필수. 단 내부 `except Exception`은 narrow 가능.
- **호환성**: 외부 API/스키마 변경 0건. 순수 내부 리팩터.

## 8. Out-of-band Notes

- **lint 규칙 도입 보류**: 향후 R3 round에서 `ruff BLE001` 활성화를 검토하되, 본 R2-1에서는 수동 정리만.
- **연쇄 사이클 예고**:
  - R2-2: `tools/`, `scripts/`, `manager.py`, `portal_*.py` (운영 유틸)
  - R2-3: `webcloring-pdf/` (submodule 분리 후 별도)
- **메모리 참조**: [[feedback_default_shadowing]], [[project_review_fixes_202604]]에서 confirm된 narrowing 패턴 재활용.
