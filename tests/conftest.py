# tests/conftest.py
"""Shared pytest fixtures — sys.path, TestClient, rate-limiter reset, DB cleanup."""

from __future__ import annotations

import os
import sqlite3
import sys
import threading
from pathlib import Path

# Ensure project root is importable
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

# webhook-async-dispatch-v2: disable the background dispatch worker for the
# entire test process. Tests that exercise the async path drive worker.tick_once()
# directly via their own WebhookDispatchWorker instance.
os.environ.setdefault("WEBHOOK_WORKER_ENABLED", "0")

# Route pytest tmp_path under the project so it survives system %TEMP%
# permission corruption (Windows: pytest-of-USER can get ACL-locked by stuck
# processes). retention_count in pyproject.toml rotates old runs.
os.environ.setdefault(
    "PYTEST_DEBUG_TEMPROOT", str(_PROJECT_ROOT / ".pytest_tmp")
)
(_PROJECT_ROOT / ".pytest_tmp").mkdir(exist_ok=True)

import contextlib

import pytest
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture(scope="module")
def client():
    """Shared FastAPI TestClient (module-scoped)."""
    return TestClient(app)


# ----------------------------------------------------------
# Seeded production DB fixture (coverage-lift, 2026-06-17)
# ----------------------------------------------------------
# Many AI tools (api/tools/*) and routers query the live DB via
# DBRouter.get_connection, which reads the module-level DB_FILE bound in
# several `shared` submodules. This fixture builds a small temp
# production_records DB (2026 dates -> live-only routing, archive skipped)
# and points every DB_FILE/ARCHIVE_DB_FILE reference at it, so the real
# query path is exercised without depending on the operational database.
_SEED_ROWS = [
    # (production_date, item_code, item_name, good_quantity, lot_number)
    ("2026-03-01", "BW0021", "블루 렌즈", 100, "LT2026A"),
    ("2026-03-15", "BW0021", "블루 렌즈", 200, "LT2026B"),
    ("2026-04-10", "BW0021", "블루 렌즈", 300, "LT2026C"),
    ("2026-04-20", "AA0001", "그린 렌즈", 50, "LT2026D"),
    ("2026-05-05", "AA0001", "그린 렌즈", 150, "LT2026E"),
    ("2026-05-25", "CC0003", "레드 렌즈", 400, "LT2026F"),
]

# Modules that bind DB_FILE / ARCHIVE_DB_FILE at import time and must all be
# redirected for the live query path + cache invalidation to see the temp DB.
_DB_FILE_MODULES = (
    "shared.database",
    "shared._db_connection",
    "shared.cache",
    "api.routers.system",
)
_ARCHIVE_MODULES = (
    "shared.database",
    "shared._db_connection",
    "shared.cache",
    "shared",
    "api.tools.items",
    "api.routers.system",
    "api.routers.records",
)


def _make_production_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute(
        """
        CREATE TABLE production_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            production_date TEXT NOT NULL,
            item_code TEXT NOT NULL,
            item_name TEXT,
            good_quantity INTEGER,
            lot_number TEXT
        )
        """
    )
    conn.executemany(
        "INSERT INTO production_records "
        "(production_date, item_code, item_name, good_quantity, lot_number) "
        "VALUES (?, ?, ?, ?, ?)",
        _SEED_ROWS,
    )
    conn.commit()
    conn.close()


@pytest.fixture
def live_db(tmp_path, monkeypatch):
    """Temp production_records DB wired into all DB_FILE references.

    Yields the Path to the live DB. Archive is pointed at a non-existent
    file so 2026-date queries route live-only (no ATTACH needed).
    """
    import importlib

    from shared.cache import clear_api_cache

    live_path = tmp_path / "test_live.db"
    archive_path = tmp_path / "test_archive_absent.db"  # intentionally not created
    _make_production_db(live_path)

    for mod_name in _DB_FILE_MODULES:
        mod = importlib.import_module(mod_name)
        if hasattr(mod, "DB_FILE"):
            monkeypatch.setattr(mod, "DB_FILE", live_path)
    for mod_name in _ARCHIVE_MODULES:
        mod = importlib.import_module(mod_name)
        if hasattr(mod, "ARCHIVE_DB_FILE"):
            monkeypatch.setattr(mod, "ARCHIVE_DB_FILE", archive_path)

    clear_api_cache()
    _drop_thread_local_conns()
    yield live_path
    clear_api_cache()
    _drop_thread_local_conns()


@pytest.fixture
def live_and_archive_db(tmp_path, monkeypatch):
    """Both live + archive production_records DBs wired in.

    Lets tests exercise the archive-present branches (ATTACH + UNION ALL).
    Archive holds a discontinued item (ZZ9999) not present in live.
    """
    import importlib

    from shared.cache import clear_api_cache

    live_path = tmp_path / "live.db"
    archive_path = tmp_path / "archive.db"
    _make_production_db(live_path)

    conn = sqlite3.connect(str(archive_path))
    conn.execute(
        "CREATE TABLE production_records ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, production_date TEXT, "
        "item_code TEXT, item_name TEXT, good_quantity INTEGER, lot_number TEXT)"
    )
    conn.executemany(
        "INSERT INTO production_records "
        "(production_date, item_code, item_name, good_quantity, lot_number) "
        "VALUES (?, ?, ?, ?, ?)",
        [
            ("2025-06-01", "ZZ9999", "단종 렌즈", 70, "LT2025A"),
            ("2025-07-01", "BW0021", "블루 렌즈", 80, "LT2025B"),
        ],
    )
    conn.commit()
    conn.close()

    for mod_name in _DB_FILE_MODULES:
        mod = importlib.import_module(mod_name)
        if hasattr(mod, "DB_FILE"):
            monkeypatch.setattr(mod, "DB_FILE", live_path)
    for mod_name in _ARCHIVE_MODULES:
        mod = importlib.import_module(mod_name)
        if hasattr(mod, "ARCHIVE_DB_FILE"):
            monkeypatch.setattr(mod, "ARCHIVE_DB_FILE", archive_path)

    # attach_archive_safe validates the path against a whitelist before ATTACH;
    # point both at the temp archive so the ATTACH+UNION path is exercised.
    attach_mod = importlib.import_module("shared._db_attach")
    monkeypatch.setattr(attach_mod, "ARCHIVE_DB_FILE", archive_path)
    monkeypatch.setattr(
        attach_mod, "ARCHIVE_DB_WHITELIST", (archive_path.resolve(),)
    )

    clear_api_cache()
    _drop_thread_local_conns()
    yield live_path, archive_path
    clear_api_cache()
    _drop_thread_local_conns()


def _drop_thread_local_conns() -> None:
    """Close + clear any cached thread-local sqlite connections."""
    try:
        from shared import database as _db
        for attr in list(vars(_db._local)):
            if attr.startswith("conn_"):
                with contextlib.suppress(sqlite3.Error, AttributeError):
                    getattr(_db._local, attr).close()
                setattr(_db._local, attr, None)
            elif attr.startswith("mtime_"):
                setattr(_db._local, attr, None)
    except (ImportError, AttributeError):
        pass


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    """Clear in-memory rate limiter state between tests."""
    from api.chat import chat_rate_limiter
    from shared import api_rate_limiter
    with contextlib.suppress(AttributeError):
        api_rate_limiter._requests.clear()  # type: ignore[attr-defined]
    with contextlib.suppress(AttributeError):
        chat_rate_limiter._requests.clear()  # type: ignore[attr-defined]
    yield


@pytest.fixture(autouse=True)
def _join_leaked_webhook_workers():
    """Drain any still-running WebhookDispatchWorker daemon thread after each test.

    rate-limiter-clock-injection (2026-06-13): a worker started with a slow
    transport can outlive worker.stop() (busy past its join timeout). Because
    the worker resolves NOTIFICATIONS_DB_FILE from global config at write time,
    a leaked thread's trailing record_attempt() can land in the NEXT test's
    monkeypatched isolated_db — flipping a sibling's delivery status. Joining
    here guarantees no worker thread survives into the next test.
    """
    yield
    for t in threading.enumerate():
        if t.name == "WebhookDispatchWorker" and t.is_alive():
            t.join(timeout=5.0)


@pytest.fixture(autouse=True)
def _close_db_connections():
    """Force-close thread-local SQLite connections after each test so that
    Windows can delete the pytest tmp_path without PermissionError.

    The notifications store and shared.database both cache sqlite3.Connection
    objects in threading.local() keyed by db path. When a test monkeypatches
    NOTIFICATIONS_DB_FILE to a tmp file the connection survives the test and
    its open handle blocks rmtree on Windows.
    """
    yield
    try:
        from api.notifications import store as _store
        _store.reset_for_tests()
    except ImportError:
        pass
    try:
        from api.anomaly import store_findings as _findings
        _findings.reset_for_tests()
    except ImportError:
        pass
    try:
        from shared import database as _db
        for attr in list(vars(_db._local)):
            if attr.startswith("conn_"):
                with contextlib.suppress(sqlite3.Error, AttributeError):
                    getattr(_db._local, attr).close()
                setattr(_db._local, attr, None)
    except (ImportError, AttributeError):
        pass
