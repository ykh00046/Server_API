# tests/test_auth.py
"""Unit tests for the pure authentication logic in ``shared.auth``.

These exercise credential extraction, public-path detection, masking and the
``authenticate`` decision table without a running app or TestClient.
"""

from __future__ import annotations

from shared import (
    AuthSettings,
    authenticate,
    extract_credentials,
    is_public_path,
    mask_secret,
)


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
