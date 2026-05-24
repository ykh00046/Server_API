"""Webhook admin UI components (dashboard side).

Public surface:
- `WebhookAdminClient` — HTTP client (the only IO layer).
- `WebhookAdminError` — normalized error.
- `formatters` — pure dict→dict transforms (Streamlit-free, unit-tested).
- `views` — Streamlit render helpers; import lazily to avoid hard
   dependency on st.* when this package is used from tests.
"""
from __future__ import annotations

from .api_client import WebhookAdminClient, WebhookAdminError
from . import formatters

__all__ = ["WebhookAdminClient", "WebhookAdminError", "formatters"]
