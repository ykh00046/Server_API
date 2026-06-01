# shared/auth.py
"""
Production Data Hub - API Authentication (auth-audit-v1)

Pure, framework-independent authentication logic. The middleware in
``api/main.py`` is a thin adapter over these functions; everything here
operates on a plain header ``Mapping`` so it can be unit-tested without a
running app or TestClient.

Design highlights (see docs/02-design/features/auth-audit-v1.design.md):
- opt-in: when ``API_AUTH_ENABLED`` is False, ``authenticate`` grants every
  request so existing open-access behavior is preserved.
- single source of truth for public (unauthenticated) paths: ``PUBLIC_PATHS``.
- constant-time credential comparison via ``secrets.compare_digest`` to avoid
  timing side channels.
- never logs raw secrets: principals are masked (``apikey:****1a2b``).
- runtime settings lookup (``load_auth_settings``) instead of capturing config
  constants as default args, so monkeypatching config takes effect immediately.
"""

from __future__ import annotations

import secrets
from collections.abc import Mapping
from dataclasses import dataclass

# ==========================================================
# Public (unauthenticated) paths — single source of truth
# ==========================================================
PUBLIC_PATHS: frozenset[str] = frozenset(
    {
        "/",
        "/healthz",
        "/healthz/ai",
        "/docs",
        "/redoc",
        "/openapi.json",
    }
)


def is_public_path(path: str) -> bool:
    """True if ``path`` is exempt from authentication."""
    return path in PUBLIC_PATHS


# ==========================================================
# Data structures
# ==========================================================
@dataclass(frozen=True)
class AuthSettings:
    """Immutable snapshot of auth configuration for one request."""

    enabled: bool
    api_keys: frozenset[str]
    bearer_tokens: frozenset[str]


@dataclass(frozen=True)
class AuthResult:
    """Outcome of an authentication attempt.

    ``principal`` is a masked identifier safe to log. ``reason`` is for audit
    logs / debugging only and is never returned to the client.
    """

    authenticated: bool
    principal: str | None
    method: str | None  # "api_key" | "bearer" | None
    reason: str | None


# ==========================================================
# Helpers
# ==========================================================
def mask_secret(secret: str) -> str:
    """Mask a secret for safe logging — only the last 4 chars are revealed."""
    if not secret:
        return "****"
    if len(secret) > 4:
        return "****" + secret[-4:]
    return "****"


def _get(headers: Mapping[str, str], name: str) -> str | None:
    """Case-insensitive header lookup that also works on a plain dict.

    Starlette's ``request.headers`` is already case-insensitive, but accepting
    a plain dict keeps the pure functions easy to unit-test.
    """
    if name in headers:
        return headers[name]
    lname = name.lower()
    for key, value in headers.items():
        if key.lower() == lname:
            return value
    return None


def extract_credentials(
    headers: Mapping[str, str],
) -> tuple[str | None, str | None]:
    """Return ``(api_key, bearer_token)`` extracted from request headers.

    - ``X-API-Key: <key>`` -> api_key
    - ``Authorization: Bearer <token>`` -> bearer_token
    Anything else yields ``None`` for that slot.
    """
    api_key = _get(headers, "x-api-key")
    api_key = api_key.strip() if api_key else None

    bearer: str | None = None
    authz = _get(headers, "authorization")
    if authz and authz.lower().startswith("bearer "):
        bearer = authz[7:].strip() or None

    return api_key, bearer


def _matches_any(candidate: str, allowed: frozenset[str]) -> bool:
    """Constant-time membership test.

    Compares against every allowed value without early return so the time
    taken does not leak how many leading characters matched.
    """
    matched = False
    for value in allowed:
        if secrets.compare_digest(candidate, value):
            matched = True
    return matched


# ==========================================================
# Core
# ==========================================================
def authenticate(headers: Mapping[str, str], settings: AuthSettings) -> AuthResult:
    """Authenticate a request from its headers against ``settings``.

    Returns an :class:`AuthResult`. When auth is disabled, every request is
    granted with ``reason="auth_disabled"``.
    """
    if not settings.enabled:
        return AuthResult(True, None, None, "auth_disabled")

    api_key, bearer = extract_credentials(headers)

    if api_key and _matches_any(api_key, settings.api_keys):
        return AuthResult(True, f"apikey:{mask_secret(api_key)}", "api_key", None)

    if bearer and _matches_any(bearer, settings.bearer_tokens):
        return AuthResult(True, f"bearer:{mask_secret(bearer)}", "bearer", None)

    if api_key or bearer:
        return AuthResult(False, None, None, "invalid_credentials")

    return AuthResult(False, None, None, "missing_credentials")


def load_auth_settings() -> AuthSettings:
    """Build an :class:`AuthSettings` from current config at call time.

    Reads ``shared.config`` on every call (rather than capturing the constants
    as defaults) so that monkeypatching config in tests / runtime reloads is
    reflected immediately. See [[feedback_default_shadowing]].
    """
    from shared import config

    return AuthSettings(
        enabled=config.API_AUTH_ENABLED,
        api_keys=frozenset(config.API_KEYS),
        bearer_tokens=frozenset(config.API_BEARER_TOKENS),
    )
