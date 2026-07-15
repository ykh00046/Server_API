"""Webhook 관리 페이지 — 운영자가 webhook 등록/조회/편집/삭제/테스트/재시도를
GUI로 수행. 백엔드 라우트는 `api/routers/notifications.py` (webhook-notifications-v1)
+ `webhook-async-dispatch-v2`의 queue/retry 엔드포인트를 그대로 사용한다.

Streamlit 페이지는 IO/렌더링이 한 곳에 모이는 진입점이고, 실제 HTTP/도메인 로직은
`components/webhook_admin/{api_client,formatters,views}`에 위임한다.
"""
from __future__ import annotations

import streamlit as st
from components.layout import page_header
from components.webhook_admin import WebhookAdminClient, views

from shared.config import API_BASE_URL

page_header(
    "Webhook 관리",
    caption=f"API: `{API_BASE_URL}`",
    icon=":material/notifications:",
)


@st.cache_resource(ttl=60, show_spinner=False)
def _event_catalog() -> list[dict]:
    """이벤트 카탈로그는 거의 변하지 않으므로 60초 캐시.

    캐시 키에 API_BASE_URL이 들어가도록 함수 안에서 client를 새로 만들고
    바로 닫는다 (캐시 객체는 list[dict]만 유지).
    """
    with WebhookAdminClient(API_BASE_URL) as c:
        return c.list_event_types()


# 페이지 한 번에 client 1개 — 페이지 rerun 시 새로 만든다 (cheap).
with WebhookAdminClient(API_BASE_URL) as client:
    try:
        event_catalog = _event_catalog()
    except Exception as e:  # noqa: BLE001 (UI safety: catalog는 부수적)
        st.warning(f"이벤트 카탈로그 로드 실패 ({e}). 자유 입력으로 진행합니다.")
        event_catalog = []

    views.render_secret_banner_if_any()
    views.render_queue_stats_section(client)
    st.divider()
    views.render_register_form(client, event_catalog)
    st.divider()
    selected = views.render_webhook_list_section(client)
    if selected is not None:
        st.divider()
        views.render_webhook_detail(client, selected, event_catalog)
        st.divider()
        views.render_deliveries_section(client, selected)
