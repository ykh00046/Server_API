# review-quickwins-202606 — Design

> **Cycle**: review-quickwins-202606
> **PDCA Phase**: Design
> **Date**: 2026-06-10
> **Plan**: [[review-quickwins-202606.plan]]

## 0. 설계 원칙

1. **최소 diff** — 4건 모두 검증된 사실에 대한 정밀 타격. 리팩터링 욕심 금지(Non-Goals 준수).
2. **SSOT 수렴** — 공개경로는 `shared.auth.PUBLIC_PATHS`, 인덱스는 `shared.db_maintenance.REQUIRED_INDEXES`로. 새 정의를 만들지 않고 기존 정본을 참조하게 한다.
3. **기능 변경은 QW-1의 `/redoc` 단 하나** — 나머지는 주석/죽은코드/내부 정의 출처 변경뿐.

## 1. QW-1 — main.py 공개경로 SSOT (`api/main.py`)

**현재** (`main.py:166`):
```python
if request.url.path in ["/", "/healthz", "/healthz/ai", "/docs", "/openapi.json"]:
```

**변경**:
```python
if is_public_path(request.url.path):
```

- import는 기존 `from shared.auth import ...` 라인에 `is_public_path` 추가(이미 auth 미들웨어가 shared.auth를 사용 중).
- 정책 효과: `/redoc`이 rate-limit 스킵에 **추가**됨(auth 면제와 정합). 나머지 5개 경로는 변화 없음.
- 인접 주석 갱신: "공개 경로는 shared.auth.PUBLIC_PATHS가 SSOT" 1줄.

**신규 테스트** (`tests/test_rate_limiter.py` 또는 `test_api_integration.py`):
- `test_public_paths_skip_rate_limit`: `PUBLIC_PATHS` 전체를 순회하며 limiter를 1로 조여도(`monkeypatch max_requests=1`) 공개경로 연속 호출이 429를 받지 않음을 확인 — SSOT 정합을 집합 단위로 고정(개별 경로 하드코딩 재발 방지).

## 2. QW-2 — cache.py 가드 의도 주석 (`shared/cache.py:47`)

기능 변경 0. `current_sources = (id(DB_FILE), id(ARCHIVE_DB_FILE))` 위에 주석 추가:

```python
# NOTE: id() comparison looks like a no-op (module-level Path constants never
# change in production), but tests/test_cache.py @patch("shared.cache.DB_FILE")
# swaps these module attributes — the id() change busts the 1s TTL cache so a
# patched test never sees a version computed from the previous (real) path.
# Do not "simplify" this away. (2026-06-10 review: initially misjudged as dead.)
```

## 3. QW-3 — 인덱스 도구 SSOT 통합 (`tools/`)

1. **`tools/create_index.py` 삭제** — 2종(단일컬럼)만 만드는 print 기반 구버전. 해당 2종은 `REQUIRED_INDEXES`에 포함되어 있어 기능 손실 없음.
2. **`tools/create_indexes.py` 수정** — 로컬 `INDEXES` 리스트(4종, :34-59) 삭제하고:
   ```python
   from shared.db_maintenance import REQUIRED_INDEXES
   ...
   for index_name, sql in REQUIRED_INDEXES.items():
       if index_name in existing and not force: ...
       # sql은 이미 "CREATE INDEX IF NOT EXISTS ..." 완성문 — 그대로 실행
   ```
   - description 필드는 제거(REQUIRED_INDEXES에 없음) — 로그는 인덱스명으로 충분.
   - `--force` 의미 유지: existing 스킵 우회(단, SQL이 `IF NOT EXISTS`라 재생성은 DROP 필요 — 기존 동작도 동일했으므로 불변).
   - dry-run/verify/ANALYZE/양 DB 처리 흐름은 그대로.
3. docstring에 "인덱스 정의 SSOT = shared.db_maintenance.REQUIRED_INDEXES (6종)" 명시.

## 4. QW-4 — chat.py 죽은 코드 제거 (`api/chat.py:74-83`)

삭제 대상(전 코드베이스 호출처 0 — Plan §1 검증, Do에서 재grep):
```python
def _get_cleanup_counter() -> int: ...      # :74-75
def _set_cleanup_counter(v: int) -> None: ... # :78-79
# Test compatibility: ... __getattr__/__setattr__ ...  # :82-83 (거짓 주석)
```
유지: re-export 블록(:62-71) — `_sessions`(테스트 5곳+), `_get_session_history`(test_session_store.py:27) 사용 중.

## 5. 구현 순서 (커밋 계층)

| # | 커밋 | 내용 | AC |
|---|------|------|----|
| 1 | `fix(api): rate-limit 공개경로를 PUBLIC_PATHS SSOT로 통일` | main.py + 신규 테스트 | AC1, AC2 |
| 2 | `docs(cache): id() source-guard 의도 주석 (test @patch 감지)` | cache.py 주석 | AC3 |
| 3 | `refactor(tools): 인덱스 도구 SSOT 통합 — create_index.py 삭제` | create_indexes.py + 삭제 | AC4 |
| 4 | `chore(chat): 미사용 cleanup_counter wrapper + 거짓 주석 제거` | chat.py | AC5 |
| 5 | `docs(pdca): Plan+Design+...` | PDCA 문서 | — |

각 커밋 전 로컬 게이트(pytest+ruff), push 후 CI green 확인(AC7).

> *실제(2026-06-10): `create_index.py` 삭제는 staging 실수로 커밋 #1(92d2139)에 선반영 — 커밋 메시지에 기록된 의도적 편차, 최종 트리는 본 설계와 동일.*

## 6. AC 매핑

AC1·AC2 → §1 / AC3 → §2 / AC4 → §3 / AC5 → §4 / AC6·AC7 → §5 게이트 / AC8 → Check.
