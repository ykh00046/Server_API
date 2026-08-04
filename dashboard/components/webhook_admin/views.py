"""Streamlit render helpers for the webhook admin page.

These helpers wrap api_client calls in try/except so the page itself never
crashes on a backend failure. Errors surface as toast notifications and
the rest of the page continues to render.
"""
from __future__ import annotations

import streamlit as st

from components.kpi_cards import kpi_row
from components.layout import empty_state, section_header

from . import formatters
from .api_client import WebhookAdminClient, WebhookAdminError

# Toast helpers are kept optional — the dashboard already ships a thin
# wrapper around st.toast, but a direct call works just as well.
try:
    from components.notifications import toast_error, toast_info, toast_success
except ImportError:  # pragma: no cover (defensive — toasts are a UX nicety)
    def toast_error(msg: str) -> None: st.error(msg)
    def toast_success(msg: str) -> None: st.success(msg)
    def toast_info(msg: str) -> None: st.info(msg)


_SECRET_KEY = "_webhook_last_secret"

# 표 컬럼 서식 — 영문 키를 한글 헤더로 바꾸고 폭만 준다.
# 값 자체는 formatters 가 만든 문자열 그대로 두므로(다운로드/테스트 계약 불변)
# 타입을 강제하지 않는 generic Column 을 쓴다. LinkColumn/DatetimeColumn 을
# 쓰지 않는 이유는 아래 각 dict 의 주석 참고.
_WEBHOOK_COLUMNS = {
    "id": st.column_config.Column("ID", width="small"),
    # url 은 format_webhook_row 가 60자로 잘라 놓은 표시용 문자열이라
    # LinkColumn 을 걸면 잘린 주소로 링크가 걸린다(깨진 href). 폭만 넓힌다.
    "url": st.column_config.Column("URL", width="large"),
    "events": st.column_config.Column("구독 이벤트", width="medium"),
    "active": st.column_config.Column("활성", width="small"),
    "description": st.column_config.Column("설명", width="medium"),
    # created_at 은 'YYYY-MM-DDTHH:MM:SS' 문자열(object dtype)이라
    # DatetimeColumn 은 타입 불일치가 된다 — 라벨/폭만 준다.
    "created_at": st.column_config.Column("등록 시각", width="medium"),
}

_DELIVERY_COLUMNS = {
    "id": st.column_config.Column("ID", width="small"),
    "event_type": st.column_config.Column("이벤트", width="medium"),
    "status": st.column_config.Column("상태", width="small"),
    "response_status": st.column_config.Column("HTTP", width="small"),
    "duration": st.column_config.Column("소요", width="small"),
    # attempted_at 도 ISO 문자열이라 DatetimeColumn 미적용 (위와 동일 이유).
    "attempted_at": st.column_config.Column("시도 시각", width="medium"),
    "summary": st.column_config.Column("응답/오류", width="large"),
}


# =====================================================================
# Section: queue stats
# =====================================================================
def render_queue_stats_section(client: WebhookAdminClient) -> None:
    section_header("큐 상태", ":material/monitoring:")
    try:
        with st.spinner("큐 상태 조회 중…"):
            stats = client.queue_stats()
    except WebhookAdminError as e:
        # 조회 실패를 0건으로 표시하면 "큐가 비었다"로 오독된다 — 렌더 중단.
        st.error(f"큐 상태를 불러오지 못했습니다: {e}")
        return
    # _hint 는 심각도 토큰(ok/warn/danger)이라 툴팁 문구가 아니다 — 표시하지 않는다.
    cards = formatters.format_queue_stats_cards(stats)
    kpi_row([{"label": label, "value": value} for label, value, _hint in cards])

    try:
        dead_n = int(stats.get("dead", 0) or 0)
    except (TypeError, ValueError):
        dead_n = 0
    if dead_n > 0:
        st.caption(f"포기됨(dead) {dead_n}건이 재시도 큐로 복귀 가능합니다.")
        if st.button(f"dead {dead_n}건 전체 재시도", icon=":material/restart_alt:", key="webhook_bulk_retry_dead"):
            _do_bulk_retry_dead(client)


def _do_bulk_retry_dead(client: WebhookAdminClient) -> None:
    try:
        with st.spinner("재시도 큐로 복귀 중…"):
            out = client.bulk_retry_dead(statuses=["dead"])
    except WebhookAdminError as e:
        toast_error(f"일괄 재시도 실패: {e}")
        return
    n = out.get("requeued", 0)
    toast_success(f"dead delivery {n}건을 재시도 큐로 복귀시켰습니다.")
    st.rerun()


# =====================================================================
# Section: register form
# =====================================================================
def render_register_form(
    client: WebhookAdminClient,
    event_catalog: list[dict],
) -> None:
    section_header("신규 등록", ":material/add_circle:")
    event_names = [e.get("name", "") for e in event_catalog if e.get("name")]
    with st.expander("새 webhook 등록", expanded=False):
        with st.form("webhook_register_form", clear_on_submit=True):
            url = st.text_input("URL", placeholder="https://example.com/webhook")
            chosen = st.multiselect(
                "구독 이벤트 (비우면 모든 이벤트 구독)",
                options=event_names,
                default=[],
            )
            description = st.text_input("설명 (선택)", value="", max_chars=500)
            active = st.checkbox("등록 즉시 활성화", value=True)
            submitted = st.form_submit_button("등록")
        if submitted:
            if not url.strip():
                toast_error("URL은 필수입니다.")
                return
            try:
                created = client.create_webhook(
                    url=url.strip(),
                    event_types=list(chosen),
                    description=description.strip(),
                    active=active,
                )
            except WebhookAdminError as e:
                toast_error(f"등록 실패: {e}")
                return
            st.session_state[_SECRET_KEY] = {
                "id": created["id"],
                "url": created["url"],
                "secret": created.get("secret", ""),
            }
            toast_success(f"webhook #{created['id']} 등록됨")
            st.rerun()


# =====================================================================
# Section: secret one-time disclosure banner
# =====================================================================
def render_secret_banner_if_any() -> None:
    secret_info = st.session_state.get(_SECRET_KEY)
    if not secret_info:
        return
    st.warning(
        "새 webhook secret이 1회 노출되었습니다. **이 페이지를 떠나면 다시 볼 수 없습니다.** "
        "안전한 곳에 복사해 두세요."
    )
    st.code(secret_info["secret"], language="text")
    cols = st.columns([1, 4])
    if cols[0].button("비밀키 확인 완료", key="webhook_secret_ack"):
        st.session_state.pop(_SECRET_KEY, None)
        st.rerun()


# =====================================================================
# Section: webhook list + selection
# =====================================================================
def render_webhook_list_section(client: WebhookAdminClient) -> int | None:
    section_header("등록된 webhook", ":material/webhook:")
    filt_label = st.radio(
        "필터",
        options=["전체", "활성", "비활성"],
        horizontal=True,
        key="webhook_filter_radio",
    )
    active_param: bool | None = None
    if filt_label == "활성":
        active_param = True
    elif filt_label == "비활성":
        active_param = False

    try:
        with st.spinner("webhook 목록 조회 중…"):
            items = client.list_webhooks(active=active_param)
    except WebhookAdminError as e:
        # 조회 실패는 "등록된 webhook 없음"과 다른 상태 — 빈 목록 안내로 덮지 않는다.
        st.error(f"webhook 목록을 불러오지 못했습니다: {e}")
        return None

    if not items:
        empty_state(
            "등록된 webhook이 없습니다.",
            hint="위 ‘신규 등록 › 새 webhook 등록’을 펼쳐 수신 URL을 추가하세요. "
                 "필터가 ‘활성/비활성’이면 ‘전체’로도 확인해 보세요.",
        )
        return None

    rows = [formatters.format_webhook_row(w) for w in items]
    st.dataframe(
        rows, width="stretch", hide_index=True, column_config=_WEBHOOK_COLUMNS
    )

    options = {f"#{w['id']} — {formatters.truncate(str(w.get('url','')), 50)}": w["id"] for w in items}
    label = st.selectbox(
        "관리할 webhook 선택",
        options=["(선택 안 함)"] + list(options.keys()),
        index=0,
        key="webhook_select",
    )
    if label == "(선택 안 함)":
        return None
    return options[label]


# =====================================================================
# Section: webhook detail (edit / rotate / delete / test)
# =====================================================================
def render_webhook_detail(
    client: WebhookAdminClient,
    webhook_id: int,
    event_catalog: list[dict],
) -> None:
    section_header(f"webhook #{webhook_id}", ":material/settings:")
    try:
        wh = client.get_webhook(webhook_id)
    except WebhookAdminError as e:
        toast_error(f"webhook 조회 실패: {e}")
        return

    event_names = [e.get("name", "") for e in event_catalog if e.get("name")]
    current_events = wh.get("event_types") or []

    cols = st.columns([2, 1, 1, 1])
    with cols[0]:
        st.text_input("URL", value=wh.get("url", ""), disabled=True)
    with cols[1]:
        active = st.checkbox("활성", value=bool(wh.get("active")), key=f"wh_active_{webhook_id}")
    with cols[2]:
        if st.button("Test ping", icon=":material/send:", key=f"wh_test_{webhook_id}", help="webhook에 테스트 페이로드를 즉시 1회 발송"):
            _do_test_ping(client, webhook_id)
    with cols[3]:
        if st.button("삭제", icon=":material/delete:", key=f"wh_delete_{webhook_id}", type="secondary"):
            _do_delete(client, webhook_id)

    new_events = st.multiselect(
        "구독 이벤트 (비우면 모든 이벤트)",
        options=sorted(set(event_names) | set(current_events)),
        default=current_events,
        key=f"wh_events_{webhook_id}",
    )
    new_desc = st.text_input(
        "설명",
        value=wh.get("description", ""),
        key=f"wh_desc_{webhook_id}",
        max_chars=500,
    )

    save_col, rotate_col, _ = st.columns([1, 1, 4])
    if save_col.button("저장", icon=":material/save:", key=f"wh_save_{webhook_id}"):
        _do_update(
            client,
            webhook_id,
            event_types=new_events,
            description=new_desc,
            active=active,
        )
    if rotate_col.button("secret 회전", icon=":material/key:", key=f"wh_rotate_{webhook_id}"):
        _do_rotate(client, webhook_id)


def _do_test_ping(client: WebhookAdminClient, webhook_id: int) -> None:
    try:
        with st.spinner("발송 중…"):
            d = client.test_webhook(webhook_id, payload={"ok": True, "source": "dashboard"})
    except WebhookAdminError as e:
        toast_error(f"test 발송 실패: {e}")
        return
    status = d.get("status", "?")
    rs = d.get("response_status")
    dur = d.get("duration_ms")
    if status == "success":
        toast_success(f"성공 · HTTP {rs} · {dur} ms")
    else:
        toast_error(f"{status} · HTTP {rs} · {d.get('error') or ''}")


def _do_update(
    client: WebhookAdminClient,
    webhook_id: int,
    *,
    event_types: list[str],
    description: str,
    active: bool,
) -> None:
    try:
        client.update_webhook(
            webhook_id,
            event_types=event_types,
            description=description,
            active=active,
        )
    except WebhookAdminError as e:
        toast_error(f"수정 실패: {e}")
        return
    toast_success(f"webhook #{webhook_id} 저장됨")
    st.rerun()


def _do_rotate(client: WebhookAdminClient, webhook_id: int) -> None:
    try:
        out = client.update_webhook(webhook_id, rotate_secret=True)
    except WebhookAdminError as e:
        toast_error(f"secret 회전 실패: {e}")
        return
    new_secret = out.get("secret")
    if not new_secret:
        toast_info("회전 응답에 secret이 없습니다 (이미 회전됐을 수 있음).")
        return
    st.session_state[_SECRET_KEY] = {
        "id": webhook_id,
        "url": out.get("url", ""),
        "secret": new_secret,
    }
    toast_success("secret이 회전되었습니다. 상단 배너에서 확인하세요.")
    st.rerun()


def _do_delete(client: WebhookAdminClient, webhook_id: int) -> None:
    try:
        client.delete_webhook(webhook_id)
    except WebhookAdminError as e:
        toast_error(f"삭제 실패: {e}")
        return
    # Clear selection so the detail section disappears.
    st.session_state.pop("webhook_select", None)
    toast_success(f"webhook #{webhook_id} 삭제됨")
    st.rerun()


# =====================================================================
# Section: deliveries
# =====================================================================
_DELIVERY_STATUSES = ("전체", "success", "queued", "in_flight", "retrying", "failed", "dead")


def render_deliveries_section(client: WebhookAdminClient, webhook_id: int) -> None:
    section_header("최근 발송 이력", ":material/outbox:")
    cols = st.columns([1, 1, 4])
    status_choice = cols[0].selectbox(
        "status",
        options=_DELIVERY_STATUSES,
        index=0,
        key=f"deliveries_status_{webhook_id}",
    )
    limit = cols[1].slider("최대 건수", min_value=10, max_value=200, value=50, step=10, key=f"deliveries_limit_{webhook_id}")
    status_param = None if status_choice == "전체" else status_choice

    try:
        items = client.list_deliveries(webhook_id, limit=limit, status=status_param)
    except WebhookAdminError as e:
        toast_error(f"deliveries 조회 실패: {e}")
        return

    if not items:
        empty_state(
            "해당 필터로 발송 이력이 없습니다.",
            hint="status를 ‘전체’로 바꾸거나 최대 건수를 늘려 범위를 넓혀 보세요. "
                 "그래도 비어 있으면 아직 이 webhook으로 발송된 이벤트가 없습니다.",
        )
        return

    rows = [formatters.format_delivery_row(d) for d in items]
    st.dataframe(
        rows, width="stretch", hide_index=True, column_config=_DELIVERY_COLUMNS
    )

    # Retry buttons for the failed/dead subset only.
    retryable = [d for d in items if formatters.is_retryable_status(d.get("status"))]
    if retryable:
        st.caption(f"실패/포기 항목 {len(retryable)}건: 클릭하면 재시도 큐로 복귀합니다.")
        for d in retryable[:10]:  # cap visible buttons to avoid UI sprawl
            did = d.get("id")
            if did is None:
                continue
            if st.button(f"재시도 #{did} ({d.get('status')})", icon=":material/replay:", key=f"retry_{webhook_id}_{did}"):
                _do_retry(client, did)


def _do_retry(client: WebhookAdminClient, delivery_id: int) -> None:
    try:
        out = client.retry_delivery(delivery_id)
    except WebhookAdminError as e:
        toast_error(f"재시도 실패: {e}")
        return
    toast_success(f"delivery #{delivery_id} 재큐잉됨 (status={out.get('status', '?')})")
    st.rerun()


__all__ = [
    "render_queue_stats_section",
    "render_register_form",
    "render_secret_banner_if_any",
    "render_webhook_list_section",
    "render_webhook_detail",
    "render_deliveries_section",
]
