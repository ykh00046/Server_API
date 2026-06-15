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
        from shared import database as _db
        for attr in list(vars(_db._local)):
            if attr.startswith("conn_"):
                with contextlib.suppress(sqlite3.Error, AttributeError):
                    getattr(_db._local, attr).close()
                setattr(_db._local, attr, None)
    except (ImportError, AttributeError):
        pass
