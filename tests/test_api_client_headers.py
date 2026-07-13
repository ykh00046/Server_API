# tests/test_api_client_headers.py
"""Unit tests for ``shared.api_client.auth_headers`` (auth-enable-v2).

Pure function: returns ``{"X-API-Key": <key>}`` when a dashboard API key is in
the environment, else ``{}``. No Streamlit/FastAPI import — coverage measured.

Precedence: ``DASHBOARD_API_KEY`` (canonical) > ``MATERIALS_API_KEY`` (legacy).
"""
from __future__ import annotations

import pytest

from shared.api_client import auth_headers


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Both keys absent by default — each test sets only what it needs."""
    monkeypatch.delenv("DASHBOARD_API_KEY", raising=False)
    monkeypatch.delenv("MATERIALS_API_KEY", raising=False)
    yield


# T1 — neither key set → empty dict
def test_no_keys_returns_empty_dict():
    assert auth_headers() == {}


# T2 — DASHBOARD_API_KEY set → X-API-Key header
def test_dashboard_api_key_returns_header(monkeypatch):
    monkeypatch.setenv("DASHBOARD_API_KEY", "abc")
    assert auth_headers() == {"X-API-Key": "abc"}


# T3 — only MATERIALS_API_KEY → fallback to legacy key
def test_materials_api_key_fallback(monkeypatch):
    monkeypatch.setenv("MATERIALS_API_KEY", "legacy")
    assert auth_headers() == {"X-API-Key": "legacy"}


# T4 — both set → DASHBOARD_API_KEY wins
def test_dashboard_takes_precedence_over_materials(monkeypatch):
    monkeypatch.setenv("DASHBOARD_API_KEY", "primary")
    monkeypatch.setenv("MATERIALS_API_KEY", "legacy")
    assert auth_headers() == {"X-API-Key": "primary"}


# T5 — surrounding whitespace stripped
def test_key_whitespace_is_stripped(monkeypatch):
    monkeypatch.setenv("DASHBOARD_API_KEY", " abc ")
    assert auth_headers() == {"X-API-Key": "abc"}
