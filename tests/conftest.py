# tests/conftest.py
"""Shared pytest fixtures — sys.path, TestClient, rate-limiter reset."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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
    from shared import api_rate_limiter
    from api.chat import chat_rate_limiter
    try:
        api_rate_limiter._requests.clear()  # type: ignore[attr-defined]
    except AttributeError:
        pass
    try:
        chat_rate_limiter._requests.clear()  # type: ignore[attr-defined]
    except AttributeError:
        pass
    yield
