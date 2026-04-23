# security-hardening-v3 Analysis Document

> **Summary**: Cycle 4 갭 분석 — 7/7 AC PASS (실측 포함 일치율 100%)
>
> **Project**: Server_API (Production Data Hub)
> **Date**: 2026-04-23
> **Status**: Analysis (passed)

---

## 1. AC 검증 결과

| AC | 항목 | 결과 | 근거 |
|----|------|:----:|------|
| AC1 | `attach_archive_safe` 정의 존재 | PASS | `shared/database.py:45` |
| AC2 | `DBRouter.get_connection()` string interpolation 제거 | PASS | helper만 호출 (`shared/database.py:299-305`); 외부 string ATTACH 0건. helper 내부 fallback 1건만 잔존 (설계상 허용, AD-3) |
| AC3 | `tools.py:execute_custom_query`도 helper 호출 | PASS | `api/tools.py:30` import, `:628` 호출 |
| AC4 | helper 시그니처 + URI form + bind 우선 | PASS | `shared/database.py:45-82` |
| AC5 | `api/main.py` legacy offset `logger.warning` ("Deprecated"+"cursor") | PASS | `api/main.py:514-518` |
| AC6 | `pytest tests/test_db_attach.py -q` 4/4 | PASS | 4 passed (실측) |
| AC7 | 전체 pytest 회귀 무손상 | PASS | 163 passed (실측, 0 failed) |

**일치율: 7/7 = 100%**

## 2. 추가 검증

- `validate_db_path` import: `shared/database.py`/`api/tools.py`에서 제거됨. 함수 자체는 `tests/test_archive_whitelist.py`가 의존하여 `shared/validators.py`에 유지.
- helper public API: `attach_archive_safe` (private prefix 제거됨, cross-module 사용 명시).
- `ATTACH DATABASE` 직접 string interpolation 위치: `shared/database.py:81`(helper fallback) 1건만. `api/`, `dashboard/`에서 0건.
- offset deprecation warning은 `if offset > 0` 가드 안에서만 발생 — cursor mode에는 영향 없음.

## 3. Iteration 필요 여부

불필요 (100%).

## 4. Lessons Learned

- **공통 보안 패턴은 helper로 추출하면 정합성·검증성·테스트성이 모두 개선된다**: 두 곳에 동일 ATTACH 패턴이 있던 상태에서, 한 곳을 더 강화해도 다른 곳이 약점으로 남는 비대칭이 있었다. helper 추출로 단일 검증 지점 확보.
- **테스트의 production parity를 명시적으로 보장**: `sqlite3.connect(":memory:")`(uri=False)로 시작했더니 production의 `uri=True` connection이 지원하는 ATTACH URI form이 실패. `uri=True`로 수정한 후 4/4 통과. helper 같은 cross-cutting 코드는 **production-equivalent 환경에서 테스트**해야 진짜 동작 검증.
- **legacy 경로 가시성은 logger.warning으로 충분**: 클라이언트 마이그레이션이 목표라면 response header가 더 강력하지만, 본 목표는 운영 추적성. logger.warning으로 분석 가능.
