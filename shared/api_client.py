# shared/api_client.py
"""Dashboard-side HTTP auth header helper (auth-enable-v2).

Server auth (shared/auth.py) accepts ``X-API-Key``. When the server runs with
``API_AUTH_ENABLED=false`` (current default) the header is ignored, so it is
always safe to attach. Pure function — no Streamlit/FastAPI import (coverage
측정 대상, coverage omit에 넣지 않는다).
"""
from __future__ import annotations

import os


def auth_headers() -> dict[str, str]:
    """Return ``{"X-API-Key": <key>}`` if a dashboard API key is configured, else ``{}``.

    Key precedence: ``DASHBOARD_API_KEY`` (canonical, dashboard-wide) >
    ``MATERIALS_API_KEY`` (legacy — dataset_page가 먼저 도입한 이름, 봇과 공유).
    """
    api_key = os.getenv("DASHBOARD_API_KEY") or os.getenv("MATERIALS_API_KEY")
    if api_key:
        return {"X-API-Key": api_key.strip()}
    return {}
