# security-hardening-v3 Design Document

> **Summary**: ATTACH helper 추출 + offset deprecation 경고 구현 설계
>
> **Project**: Server_API (Production Data Hub)
> **Date**: 2026-04-23
> **Status**: Design

---

## 1. Architecture Decisions

### AD-1: ATTACH helper 위치

**선택지**

| 옵션 | 장점 | 단점 | 결정 |
|------|------|------|------|
| A. `shared/validators.py`에 `attach_archive_safe` 추가 | validators 일괄 관리 | sqlite3 의존성을 validators에 주입 — 책임 분리 깨짐 | ✗ |
| B. `shared/database.py`에 `_attach_archive_safe` 모듈 함수 추가 (private) | DBRouter와 같은 모듈 — 자연스러움. tools.py가 `from shared.database import _attach_archive_safe`로 import | private prefix지만 cross-module 사용 — 약한 contract | **✓** (private prefix 제거 또는 별도 docstring으로 contract 명시) |
| C. `shared/db_attach.py` 신규 모듈 | 책임 명확 | 모듈 분리가 과한 — 함수 1개에 모듈 1개 | ✗ |

**선택 근거**: B
- DBRouter와 함께 있어야 ATTACH lifecycle 책임이 한 곳에 모인다.
- tools.py는 `attach_archive_safe` (private prefix 제거)로 import하여 명시적 사용.

### AD-2: helper 시그니처

```python
def attach_archive_safe(
    conn: sqlite3.Connection,
    archive_path: Path | str | None = None,
    *,
    alias: str = "archive",
    whitelist: tuple[Path, ...] | None = None,
) -> Path:
    """ATTACH archive DB safely (whitelist + bind-first + ro mode).

    Args:
        conn: Active sqlite3 connection.
        archive_path: Requested archive DB path (default: ARCHIVE_DB_FILE).
        alias: Schema alias (default: "archive").
        whitelist: Allowed paths (default: ARCHIVE_DB_WHITELIST from config).

    Returns:
        Resolved archive Path.

    Raises:
        ValueError: If path not in whitelist.
        FileNotFoundError: If archive file missing.
        sqlite3.OperationalError: If both bind and string ATTACH fail.
    """
```

### AD-3: bind 우선, string fallback의 보안 정당성

```python
try:
    conn.execute(f"ATTACH DATABASE ? AS {alias}", (archive_uri,))
except sqlite3.OperationalError:
    # Some sqlite builds don't accept parameter in ATTACH.
    # Safe because archive_uri came from resolve_archive_db (whitelist-validated)
    # and alias is internal constant ("archive"), not user input.
    conn.execute(f"ATTACH DATABASE '{archive_uri}' AS {alias}")
```

- `archive_uri`: whitelist 통과 + URI form (`file:...?mode=ro`) — single quote 포함 불가.
- `alias`: 호출 측이 hard-code (현재 항상 `"archive"`). 외부 사용자 입력 아님.
- 따라서 string interpolation도 안전. fallback은 sqlite 빌드 차이 흡수용.

### AD-4: offset deprecation 신호

**선택지**

| 옵션 | 장점 | 단점 | 결정 |
|------|------|------|------|
| A. `logger.warning` 만 | 단순 | 외부 클라이언트는 로그 안 봄 | 일부 |
| B. response header `X-Deprecated: offset=true; use=cursor` 추가 | 클라이언트 즉시 알림 | FastAPI Response 객체 변경 필요 → 더 큰 변경 | scope creep |
| C. `logger.warning` + 비율 기반 sampling (예: 10건마다 1번) | 로그 spam 방지 | 복잡도 증가 | over-engineering |

**선택 근거**: A (`logger.warning`)
- 현재 cycle은 가시성 강화가 목표. 이미 deprecated 표기되어 외부 안내 완료.
- header 추가는 별도 사이클 (`api-deprecation-headers-v1` 후보).

---

## 2. File-Level Changes

### 2.1 `shared/database.py`

#### 2.1.1 신규 helper (모듈 함수, DBRouter 외부)

```python
def attach_archive_safe(
    conn: sqlite3.Connection,
    archive_path: Path | str | None = None,
    *,
    alias: str = "archive",
    whitelist: tuple[Path, ...] | None = None,
) -> Path:
    from shared.config import ARCHIVE_DB_FILE, ARCHIVE_DB_WHITELIST
    from shared.validators import resolve_archive_db

    target = archive_path if archive_path is not None else ARCHIVE_DB_FILE
    wl = whitelist if whitelist is not None else ARCHIVE_DB_WHITELIST
    resolved = resolve_archive_db(target, wl)
    archive_uri = f"file:{resolved.as_posix()}?mode=ro"
    try:
        conn.execute(f"ATTACH DATABASE ? AS {alias}", (archive_uri,))
    except sqlite3.OperationalError:
        conn.execute(f"ATTACH DATABASE '{archive_uri}' AS {alias}")
    return resolved
```

#### 2.1.2 `DBRouter.get_connection()` 변경

```diff
- if use_archive and ARCHIVE_DB_FILE.exists():
-     archive_path = str(ARCHIVE_DB_FILE.absolute())
-     try:
-         validate_db_path(archive_path)
-     except ValueError as e:
-         logger.error(f"Invalid archive database path: {e}")
-         raise
-     archive_path_escaped = archive_path.replace("'", "''")
-     conn.execute(f"ATTACH DATABASE '{archive_path_escaped}' AS archive")
-     logger.debug(f"Archive DB attached: {ARCHIVE_DB_FILE}")
+ if use_archive and ARCHIVE_DB_FILE.exists():
+     try:
+         resolved = attach_archive_safe(conn)
+         logger.debug(f"Archive DB attached: {resolved}")
+     except (ValueError, FileNotFoundError) as e:
+         logger.error(f"Invalid archive database path: {e}")
+         raise
```

> Note: `validate_db_path()` import 제거 (다른 사용처 0건이면).

### 2.2 `api/tools.py`

`execute_custom_query()`의 ATTACH 블록(line 629-645)을 helper 호출로 교체:

```diff
  if use_archive:
-     try:
-         archive_resolved = resolve_archive_db(ARCHIVE_DB_FILE, ARCHIVE_DB_WHITELIST)
-     except (ValueError, FileNotFoundError) as e:
-         conn.close()
-         return {"status": "error", "code": "INVALID_ARCHIVE_PATH", "message": f"Invalid archive DB: {e}"}
-     archive_uri = f"file:{archive_resolved.as_posix()}?mode=ro"
-     try:
-         conn.execute("ATTACH DATABASE ? AS archive", (archive_uri,))
-     except sqlite3.OperationalError:
-         conn.execute(f"ATTACH DATABASE '{archive_uri}' AS archive")
+     try:
+         attach_archive_safe(conn)
+     except (ValueError, FileNotFoundError) as e:
+         conn.close()
+         return {"status": "error", "code": "INVALID_ARCHIVE_PATH", "message": f"Invalid archive DB: {e}"}
```

import 정리: `from shared.validators import resolve_archive_db` 제거 (helper 안에서 사용). `from shared.database import attach_archive_safe` 추가.

### 2.3 `api/main.py`

```diff
  else:
      # Legacy offset mode (backward compatibility)
+     logger.warning(
+         f"[Deprecated] /records called with offset={offset} — "
+         f"use cursor pagination instead (cursor=...)"
+     )
      sql, params_doubled = DBRouter.build_union_sql(...)
```

### 2.4 `tests/test_db_attach.py` (신규)

```python
"""Helper tests: attach_archive_safe whitelist enforcement and bind fallback."""
import sqlite3
from pathlib import Path
import pytest
from shared.database import attach_archive_safe


def test_rejects_non_whitelisted_path(tmp_path):
    fake = tmp_path / "fake.db"
    fake.write_bytes(b"")  # exists
    conn = sqlite3.connect(":memory:")
    with pytest.raises(ValueError, match="not in whitelist"):
        attach_archive_safe(conn, archive_path=fake, whitelist=(tmp_path / "other.db",))


def test_rejects_missing_file(tmp_path):
    conn = sqlite3.connect(":memory:")
    missing = tmp_path / "missing.db"
    with pytest.raises(FileNotFoundError):
        attach_archive_safe(conn, archive_path=missing, whitelist=(missing.resolve(),))


def test_attaches_valid_archive(tmp_path):
    archive = tmp_path / "archive.db"
    sqlite3.connect(archive).close()  # create empty db
    conn = sqlite3.connect(":memory:")
    resolved = attach_archive_safe(conn, archive_path=archive, whitelist=(archive.resolve(),))
    assert resolved == archive.resolve()
    # Verify ATTACH succeeded — query main schema list
    rows = list(conn.execute("PRAGMA database_list"))
    aliases = [r[1] for r in rows]
    assert "archive" in aliases
```

---

## 3. Test Plan

| Test | 명령 | 기대 |
|------|------|------|
| 신규 helper 단위 | `pytest tests/test_db_attach.py -q` | 3 passed |
| 회귀 — fallback 테스트 | `pytest tests/test_chat_fallback.py -q` | 7 passed |
| 회귀 — 전체 (소요 시간 허용) | `pytest tests/ -q` | 모두 pass |
| ATTACH 직접 string 잔존 검사 | `grep -RIn 'ATTACH DATABASE.*\\\\$' shared api` | 0건 (helper 내부 fallback 제외) |
| offset warning 로그 검사 | `grep -n '\\[Deprecated\\] /records called with offset' api/main.py` | 1건 |

---

## 4. Rollback

| Commit | Revert 영향 |
|--------|-----------|
| Plan/Design | 기능 영향 없음 |
| S1+S2+S3 (helper + 두 호출 지점) | 이전 string interpolation 패턴 복원 (이미 검증된 경로라 보안 동등) |
| S4 (offset warning) | 로그 출력만 영향 |
| S5 (test) | 테스트 롤백 |

---

## 5. Open Questions

- (해결됨) helper 위치 → AD-1: `shared/database.py` 모듈 함수.
- (해결됨) bind+fallback 정당성 → AD-3: alias 내부 constant + URI whitelist 통과로 안전.
- (해결됨) offset 신호 방식 → AD-4: logger.warning만 (header는 별도 사이클).
