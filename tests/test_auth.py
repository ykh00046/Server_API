# tests/test_auth.py
"""Unit tests for the pure authentication logic in ``shared.auth``.

These exercise credential extraction, public-path detection, masking and the
``authenticate`` decision table without a running app or TestClient.
"""

from __future__ import annotations

import logging

import pytest

from shared import (
    AuthSettings,
    authenticate,
    extract_credentials,
    is_public_path,
    mask_secret,
)
from shared.api_client import auth_headers


# ----------------------------------------------------------
# Public path detection (SSOT)
# ----------------------------------------------------------
def test_is_public_path_true():
    for path in ("/", "/healthz", "/healthz/ai", "/docs", "/redoc", "/openapi.json"):
        assert is_public_path(path) is True


def test_is_public_path_false():
    for path in ("/records", "/items", "/metrics/performance", "/chat"):
        assert is_public_path(path) is False


# ----------------------------------------------------------
# Credential extraction
# ----------------------------------------------------------
def test_extract_api_key():
    assert extract_credentials({"x-api-key": "k"}) == ("k", None)


def test_extract_api_key_case_insensitive():
    assert extract_credentials({"X-API-Key": "k"}) == ("k", None)


def test_extract_bearer():
    assert extract_credentials({"authorization": "Bearer t"}) == (None, "t")


def test_extract_bearer_case_insensitive_scheme():
    # RFC 7235 auth-scheme is case-insensitive.
    assert extract_credentials({"authorization": "bearer t"}) == (None, "t")


def test_extract_non_bearer_scheme_ignored():
    assert extract_credentials({"authorization": "Basic xx"}) == (None, None)


def test_extract_empty_bearer():
    assert extract_credentials({"authorization": "Bearer "}) == (None, None)


def test_extract_none():
    assert extract_credentials({}) == (None, None)


# ----------------------------------------------------------
# mask_secret
# ----------------------------------------------------------
def test_mask_long():
    assert mask_secret("abcd1234") == "****1234"


def test_mask_short():
    assert mask_secret("abc") == "****"


def test_mask_empty():
    assert mask_secret("") == "****"


def test_mask_never_reveals_full_secret():
    secret = "supersecretvalue"
    assert secret not in mask_secret(secret)


# ----------------------------------------------------------
# authenticate decision table
# ----------------------------------------------------------
def _settings(enabled=True, keys=(), tokens=()):
    return AuthSettings(
        enabled=enabled,
        api_keys=frozenset(keys),
        bearer_tokens=frozenset(tokens),
    )


def test_disabled_grants_all():
    result = authenticate({}, _settings(enabled=False))
    assert result.authenticated is True
    assert result.reason == "auth_disabled"


def test_valid_api_key():
    result = authenticate({"x-api-key": "goodkey9"}, _settings(keys=["goodkey9"]))
    assert result.authenticated is True
    assert result.method == "api_key"
    assert result.principal == "apikey:****key9"


def test_invalid_api_key():
    result = authenticate({"x-api-key": "bad"}, _settings(keys=["good"]))
    assert result.authenticated is False
    assert result.reason == "invalid_credentials"
    assert result.principal is None


def test_valid_bearer():
    result = authenticate(
        {"authorization": "Bearer tok123"}, _settings(tokens=["tok123"])
    )
    assert result.authenticated is True
    assert result.method == "bearer"
    assert result.principal == "bearer:****k123"


def test_invalid_bearer():
    result = authenticate(
        {"authorization": "Bearer nope"}, _settings(tokens=["tok123"])
    )
    assert result.authenticated is False
    assert result.reason == "invalid_credentials"


def test_missing_credentials():
    result = authenticate({}, _settings(keys=["good"]))
    assert result.authenticated is False
    assert result.reason == "missing_credentials"


def test_enabled_but_no_credentials_configured_fails_closed():
    # FR/Design: enabled with empty key/token sets -> nothing can match.
    result = authenticate({"x-api-key": "anything"}, _settings())
    assert result.authenticated is False


def test_api_key_takes_precedence_when_both_present():
    result = authenticate(
        {"x-api-key": "k", "authorization": "Bearer t"},
        _settings(keys=["k"], tokens=["t"]),
    )
    assert result.method == "api_key"


# ==========================================================
# Middleware integration (auth-enable-v2) — client/server contract
# These drive the real FastAPI app via the TestClient. Auth is toggled by
# monkeypatching shared.config (load_auth_settings reads it at call time).
# T9/T11/T12 are covered by tests/test_audit.py; below fill the two gaps:
# T10 (wrong-key → 401 + audit DENY together) and T13 (auth_headers() → 200
# end-to-end, the dashboard helper ↔ server contract).
# ==========================================================
PROTECTED_PATH = "/items"


@pytest.fixture
def _auth_on_with_key(monkeypatch):
    """Enable auth with one accepted API key."""
    monkeypatch.setattr("shared.config.API_AUTH_ENABLED", True)
    monkeypatch.setattr("shared.config.API_KEYS", ["secret-key-1234"])


# T10 — wrong key → 401 AND an [AUDIT] DENY line in the same request.
# test_audit.py asserts DENY only on a *missing*-credential request; this
# fixes the wrong-key (reason=invalid_credentials) path as a single contract.
def test_auth_on_wrong_key_401_and_audit_deny(client, _auth_on_with_key, caplog):
    r = client.get(PROTECTED_PATH, headers={"X-API-Key": "wrong"})
    assert r.status_code == 401
    with caplog.at_level(logging.INFO, logger="audit"):
        client.get(PROTECTED_PATH, headers={"X-API-Key": "wrong-again"})
    audit_lines = [rec.getMessage() for rec in caplog.records if rec.name == "audit"]
    assert any("[AUDIT] DENY" in m and "invalid_credentials" in m for m in audit_lines)


# T13 — auth_headers() output, used verbatim as request headers, reaches the
# protected route through the real middleware and returns 200. This is the
# end-to-end fixation of the dashboard-client ↔ server-auth contract: whatever
# auth_headers() builds is exactly what the server accepts.
def test_auth_headers_grants_access_to_protected_route(
    client, _auth_on_with_key, monkeypatch
):
    monkeypatch.setenv("DASHBOARD_API_KEY", "secret-key-1234")
    headers = auth_headers()
    assert headers == {"X-API-Key": "secret-key-1234"}
    r = client.get(PROTECTED_PATH, headers=headers)
    assert r.status_code == 200
