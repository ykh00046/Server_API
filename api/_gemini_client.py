# api/_gemini_client.py
"""Gemini client factory (lazy initialization, monkeypatch seam for tests).

Extracted from api/chat.py (Act-1 of security-and-test-improvement).
"""

from __future__ import annotations

import os

from google import genai
from google.genai.errors import ClientError, ServerError

from shared import get_logger

logger = get_logger(__name__)

_client: genai.Client | None = None
_client_initialized = False


def get_client() -> genai.Client | None:
    """Return a cached Gemini client, or None if `GEMINI_API_KEY` is unset."""
    global _client, _client_initialized

    if _client_initialized:
        return _client

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.warning("GEMINI_API_KEY not found in .env file. AI chat will not work.")
        _client_initialized = True
        return None

    try:
        _client = genai.Client(api_key=api_key)
        logger.info("GenAI client initialized successfully")
    except (ImportError, ValueError, RuntimeError) as e:
        logger.error(f"Failed to initialize GenAI client: {e}")
        _client = None

    _client_initialized = True
    return _client


def reset_for_tests() -> None:
    """Clear cached client so tests can swap `GEMINI_API_KEY`."""
    global _client, _client_initialized
    _client = None
    _client_initialized = False


FALLBACK_STATUS_CODES = {429, 503}

# google-genai APIError.status is a gRPC-style *string*, not an HTTP code.
_STATUS_NAME_TO_HTTP = {
    "RESOURCE_EXHAUSTED": 429,  # quota
    "UNAVAILABLE": 503,  # overload
    "INTERNAL": 500,
}


def extract_http_code(e: Exception) -> int:
    """Best-effort HTTP status code for a google-genai APIError.

    SDK 2.8.0 contract: ``.code`` is the int HTTP code and ``.status`` is a
    string ("RESOURCE_EXHAUSTED"). Reading ``.status`` as if it were the code
    made every real 429/503 unclassifiable — retry and fallback never fired in
    production while the tests (whose fixtures omitted ``status``) stayed green.
    The status-name and message scans below are for malformed responses that
    leave ``.code`` empty (e.g. an HTML 502 from a proxy).
    """
    code = getattr(e, "code", None)
    if isinstance(code, int) and code > 0:
        return code

    status = getattr(e, "status", None)
    if isinstance(status, str):
        mapped = _STATUS_NAME_TO_HTTP.get(status)
        if mapped:
            return mapped

    message = str(e)
    for known in (429, 503, 500):
        if str(known) in message:
            return known
    return 0


def is_fallbackable(e: Exception) -> bool:
    """Check if the error warrants a model fallback (429/503 only)."""
    if not isinstance(e, (ClientError, ServerError)):
        return False
    return extract_http_code(e) in FALLBACK_STATUS_CODES
