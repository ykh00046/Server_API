# tests/test_audit.py
"""Middleware + audit integration tests for auth-audit-v1.

Drives the real FastAPI app through the TestClient. Auth is toggled per test by
monkeypatching ``shared.config`` (``load_auth_settings`` reads config at call
time, so the patch takes effect immediately — see [[feedback_default_shadowing]]).
"""

from __future__ import annotations

import logging

import pytest

# A protected (non-public) route with no side effects beyond a read.
PROTECTED_PATH = "/items"


@pytest.fixture
def enable_auth(monkeypatch):
    """Enable auth with one API key and one bearer token."""
    monkeypatch.setattr("shared.config.API_AUTH_ENABLED", True)
    monkeypatch.setattr("shared.config.API_KEYS", ["secret-key-1234"])
    monkeypatch.setattr("shared.config.API_BEARER_TOKENS", ["bearer-tok-abcd"])


# ----------------------------------------------------------
# Default OFF — existing behavior preserved
# ----------------------------------------------------------
def test_auth_off_protected_route_open(client):
    """Default config: protected route is reachable without credentials."""
    r = client.get(PROTECTED_PATH)
    assert r.status_code == 200


# ----------------------------------------------------------
# Auth ON — denial
# ----------------------------------------------------------
def test_auth_on_missing_credentials_401(client, enable_auth):
    r = client.get(PROTECTED_PATH)
    assert r.status_code == 401
    assert r.headers.get("WWW-Authenticate") == "Bearer"
    assert r.json()["detail"] == "Unauthorized"


def test_auth_on_wrong_api_key_401(client, enable_auth):
    r = client.get(PROTECTED_PATH, headers={"X-API-Key": "wrong"})
    assert r.status_code == 401


def test_auth_on_wrong_bearer_401(client, enable_auth):
    r = client.get(PROTECTED_PATH, headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401


# ----------------------------------------------------------
# Auth ON — grant
# ----------------------------------------------------------
def test_auth_on_valid_api_key_200(client, enable_auth):
    r = client.get(PROTECTED_PATH, headers={"X-API-Key": "secret-key-1234"})
    assert r.status_code == 200


def test_auth_on_valid_bearer_200(client, enable_auth):
    r = client.get(PROTECTED_PATH, headers={"Authorization": "Bearer bearer-tok-abcd"})
    assert r.status_code == 200


# ----------------------------------------------------------
# Auth ON — public paths stay open
# ----------------------------------------------------------
@pytest.mark.parametrize("path", ["/healthz", "/", "/openapi.json"])
def test_auth_on_public_paths_open(client, enable_auth, path):
    r = client.get(path)
    assert r.status_code == 200


# ----------------------------------------------------------
# Audit logging
# ----------------------------------------------------------
def test_audit_deny_logged(client, enable_auth, caplog):
    with caplog.at_level(logging.INFO, logger="audit"):
        client.get(PROTECTED_PATH)
    audit_lines = [r.getMessage() for r in caplog.records if r.name == "audit"]
    assert any("[AUDIT] DENY" in m for m in audit_lines)


def test_audit_grant_logged_and_no_raw_secret(client, enable_auth, caplog):
    with caplog.at_level(logging.INFO, logger="audit"):
        client.get(PROTECTED_PATH, headers={"X-API-Key": "secret-key-1234"})
    audit_lines = [r.getMessage() for r in caplog.records if r.name == "audit"]
    assert any("[AUDIT] GRANT" in m for m in audit_lines)
    # The raw secret must never appear; only the masked tail (****1234).
    assert all("secret-key-1234" not in m for m in audit_lines)
    assert any("****1234" in m for m in audit_lines)


def test_audit_off_produces_no_audit_log(client, caplog):
    """With auth disabled the audit logger must stay silent (no noise)."""
    with caplog.at_level(logging.INFO, logger="audit"):
        client.get(PROTECTED_PATH)
    audit_lines = [r for r in caplog.records if r.name == "audit"]
    assert audit_lines == []
