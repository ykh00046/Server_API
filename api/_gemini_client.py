# api/_gemini_client.py
"""Gemini client factory (lazy initialization, monkeypatch seam for tests).

Extracted from api/chat.py (Act-1 of security-and-test-improvement).
"""

from __future__ import annotations

import os

from google import genai

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
    except Exception as e:
        logger.error(f"Failed to initialize GenAI client: {e}")
        _client = None

    _client_initialized = True
    return _client


def reset_for_tests() -> None:
    """Clear cached client so tests can swap `GEMINI_API_KEY`."""
    global _client, _client_initialized
    _client = None
    _client_initialized = False
