# review-quickwins-202606 — Plan

> **Cycle**: review-quickwins-202606
> **PDCA Phase**: Plan
> **Date**: 2026-06-10
> **Project**: Production Data Hub API
> **Summary**: 2026-06-10 전체 검토에서 나온 소규모 정리 4건 — 공개경로 SSOT 통일, cache 가드 의도 문서화(검토 결론 정정 포함), 인덱스 도구 통합, chat.py 죽은 코드 제거. 전부 저위험·반나절 분량.

## 1. Background

2026-06-10 전체 프로젝트 검토(code-analyzer + 직접 검증)에서 발견된 Quick wins. 이번 사이클 착수 전 **재검증을 수행해 1건의 결론이 정정**되었다:

| # | 검토 시 결론 | 재검증 결과 (2026-06-10 실측) |
|---|------------|------------------------------|
| QW-1 | `api/main.py:166` rate-limit 스킵 리스트(5개, `/redoc` 누락)가 `shared/auth.py PUBLIC_PATHS`(6개)와 별도 하드코딩 | ✅ 확인 — 이중 정의, `/redoc`만 어긋남 |
| QW-2 | `shared/cache.py:47`의 `id(DB_FILE)` source-guard는 항상 참인 **죽은 안전장치** | ❌ **정정**: `tests/test_cache.py:20-21`이 `@patch("shared.cache.DB_FILE")`로 **모듈 속성을 직접 패치** → 패치 시 `id()`가 변해 1초 TTL 캐시가 무효화됨. 즉 가드는 **테스트 격리용으로 실동작**. 죽은 코드가 아니라 **의도가 미문서화**된 코드 |
| QW-3 | `tools/create_index.py`(2종)와 `create_indexes.py`(4종)가 서로 다른 인덱스 생성 | ✅ 확인 + 보강: 정본 `shared/db_maintenance.REQUIRED_INDEXES`(6종, "single source of truth" 주석 존재)가 이미 있고, 두 스크립트가 이를 **무시하고 부분집합을 각자 하드코딩**(2종+4종=6종으로 상호보완적이나 분열) |
| QW-4 | `api/chat.py:82-83` 주석이 실존하지 않는 `__getattr__/__setattr__` 언급 | ✅ 확인 + 보강: `_get_cleanup_counter`/`_set_cleanup_counter` wrapper(:74-79)는 **호출처 0** (전 코드베이스 grep). 테스트는 `sstore._cleanup_counter`를 직접 사용(`test_session_store.py:18`) |

> QW-2 정정은 [[feedback_agent_verification]](에이전트 주장 재검증 원칙)의 실증 사례 — 코드 변경 전 재검증이 잘못된 삭제를 막았다.

## 2. Goal

1. **QW-1**: `api/main.py` rate-limit 스킵을 `shared.auth.is_public_path()` 재사용으로 전환 — 공개경로 정의를 PUBLIC_PATHS 단일 원천으로. (효과: `/redoc`이 rate-limit 스킵에 포함되는 정책 변화 — 의도적, 문서/공개경로와 정합)
2. **QW-2**: `shared/cache.py` source-guard에 의도 주석 추가(테스트 `@patch` 감지용) — **기능 변경 0**.
3. **QW-3**: `tools/create_index.py` 삭제 + `tools/create_indexes.py`가 `db_maintenance.REQUIRED_INDEXES`를 import해 6종 전체를 SSOT 기반으로 생성하도록 수정.
4. **QW-4**: `api/chat.py` 미사용 wrapper 2개(:74-79) + 거짓 주석(:82-83) 제거. 사용 중인 re-export(`_sessions`, `_get_session_history` 등 :63-71)는 유지.
5. **회귀 0**: 기존 360 테스트 green + CI green ([[project_ci_env_standardization]] — 이번 사이클부터 CI가 강제 장치).

## 3. Non-Goals (defer)

- chat.py re-export(:63-71) 전수 정리 — `_sessions`/`_get_session_history`는 테스트 사용 중. 나머지 미사용 후보(SESSION_TTL 등)의 제거는 별도 검증 필요 → defer.
- `run_stream` 분해, 폴백 정책 헬퍼 통합 — 별도 사이클(검토 Medium 항목).
- create_indexes.py의 dry-run/verify/ANALYZE 기능 재설계 — 인덱스 정의 SSOT 참조로의 최소 수정만.

## 4. Scope

| 구분 | 대상 |
|---|---|
| **수정** | `api/main.py`(스킵 경로 1줄), `shared/cache.py`(주석만), `tools/create_indexes.py`(REQUIRED_INDEXES 참조), `api/chat.py`(삭제만) |
| **삭제** | `tools/create_index.py` |
| **신규 테스트** | `/redoc` rate-limit 스킵 + 공개경로 SSOT 정합 검증 1~2건 |
| **제외** | pyproject, CI 설정, dashboard, webcloring-pdf |

## 5. Acceptance Criteria

| # | Criterion | 측정 |
|---|-----------|---|
| AC1 | `api/main.py`에 공개경로 인라인 리스트 0건 — `is_public_path()` 호출로 대체 | grep + diff |
| AC2 | `/redoc`이 auth·rate-limit 양쪽에서 동일하게 공개경로 취급(신규 테스트) | test |
| AC3 | `cache.py` 가드에 `@patch` 감지 의도 주석 존재, 동작 diff 0 | diff |
| AC4 | `tools/create_index.py` 삭제, `create_indexes.py`가 `REQUIRED_INDEXES` import (자체 인덱스 dict 0건) | grep |
| AC5 | `chat.py` wrapper 2개+거짓 주석 제거, 호출처 0 재확인 | grep |
| AC6 | 기존 360+ 테스트 green (로컬 py3.12 venv) | pytest |
| AC7 | ruff 게이트 클린 + **CI run green** | Actions |
| AC8 | gap match rate ≥ 90% | Check |

## 6. Constraints / Risks

- **QW-1 정책 변화**: `/redoc`이 rate-limit 면제가 됨. FastAPI 기본 redoc은 정적 페이지라 남용 표면 미미 + 이미 auth 면제(PUBLIC_PATHS)와 정합 → 허용. 반대로 통일에 의해 달라지는 다른 경로는 없음(나머지 5개는 양쪽 동일).
- **QW-3 인덱스 보장 변화**: create_indexes.py가 4종→6종 생성하게 됨. `check_and_heal_indexes`가 이미 6종을 치유하므로 운영상 신규 동작 아님(스크립트가 정본을 따라잡는 것).
- **QW-4 안전망**: wrapper 제거 전 전 코드베이스 grep 재확인(Plan §1에서 1차 완료, Do에서 재실행).
- 커밋 분리([[feedback_commit_style]]): QW별 1커밋(4) + 테스트 포함, docs는 별도.

## 7. Out-of-band Notes

- 검토 보고서(대화)의 QW-2 항목은 본 Plan §1에서 공식 정정됨.
- 메모리 참조: [[feedback_agent_verification]], [[project_ci_env_standardization]], [[feedback_commit_style]]
