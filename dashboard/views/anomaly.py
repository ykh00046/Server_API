"""이상탐지 관측 페이지 (anomaly-dashboard-v2).

한 페이지에서 네 가지 질문에 답한다:
① 지금 무엇이 이상인가 (GET /anomaly/scan)
② 최근 30일간 무엇이 발행됐나 (GET /anomaly/findings — anomaly.db 이력)
③ 왜 알림이 안 왔나 = 쿨다운 (GET /anomaly/state)
④ 임계치를 바꾸면 어떻게 되나 = what-if (GET /anomaly/scan?drop_pct=…,
   발행·상태 변경이 물리적으로 불가능한 미리보기 전용 경로)

섹션별 독립 실패: API 오류 시 해당 섹션만 warning, 페이지는 생존.
순수 변환은 components/anomaly_view_helpers.py (streamlit-free).
"""
from __future__ import annotations

import datetime as dt

import httpx
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from components import get_chart_config
from components.anomaly_view_helpers import (
    KIND_LABELS,
    SEVERITY_COLORS,
    findings_to_daily_counts,
    humanize_remaining,
)
from components.layout import empty_state, page_header

from shared.api_client import auth_headers
from shared.config import API_BASE_URL
from shared.ui.theme import get_colors

_SEV_BADGE = {"critical": "red", "warning": "orange", "info": "gray"}


def _headers() -> dict:
    return auth_headers()


@st.cache_data(ttl=60, show_spinner="이상탐지 데이터 조회 중…")
def _fetch(path: str, params: dict | None = None) -> dict:
    with httpx.Client(base_url=API_BASE_URL, timeout=15.0) as c:
        resp = c.get(path, params=params or {}, headers=_headers())
        resp.raise_for_status()
        return resp.json()


def _fetch_fresh(path: str, params: dict | None = None) -> dict:
    """캐시 없는 조회 — what-if 버튼 트리거 전용."""
    with httpx.Client(base_url=API_BASE_URL, timeout=15.0) as c:
        resp = c.get(path, params=params or {}, headers=_headers())
        resp.raise_for_status()
        return resp.json()


def _try_fetch(path: str, params: dict | None = None) -> dict | None:
    try:
        return _fetch(path, params)
    except httpx.HTTPError as e:
        st.warning(f"`{path}` 조회 실패 ({e}). API 서버 상태를 확인하세요.")
        return None


def _render_finding_cards(findings: list[dict]) -> None:
    for f in findings:
        with st.container(border=True):
            head = st.container(horizontal=True, vertical_alignment="center")
            with head:
                st.badge(
                    f["severity"],
                    color=_SEV_BADGE.get(f["severity"], "gray"),
                )
                st.markdown(
                    f"**{KIND_LABELS.get(f['kind'], f['kind'])}** — {f['message']}"
                )
            if f.get("details"):
                with st.expander("상세", expanded=False):
                    st.json(f["details"])


# ==========================================================
# 헤더 + 상태 메트릭
# ==========================================================
page_header(
    "이상탐지",
    caption=f"API: `{API_BASE_URL}/anomaly` · 규칙 기반 v1 · 이력 보존 90일",
    icon=":material/monitor_heart:",
)

state = _try_fetch("/anomaly/state")
scan = _try_fetch("/anomaly/scan")

active_cooldowns = [c for c in (state or {}).get("cooldowns", []) if c["active"]]
last_scan_ts = (state or {}).get("last_scan_ts") or 0
last_scan = (
    dt.datetime.fromtimestamp(last_scan_ts).strftime("%m-%d %H:%M")
    if last_scan_ts else "기록 없음"
)

m1, m2, m3, m4 = st.columns([1, 1, 1, 1])
m1.metric("현재 findings", (scan or {}).get("count", "—"), border=True)
m2.metric("마지막 발행 스캔", last_scan, border=True,
          help="발행 경로(POST/데몬)가 상태를 갱신한 시각")
m3.metric("활성 쿨다운", len(active_cooldowns), border=True)
with m4:
    if st.button("새로고침", icon=":material/refresh:", width="stretch"):
        st.cache_data.clear()
        st.rerun()

# ==========================================================
# ① 현재 스캔 결과
# ==========================================================
st.markdown("**:material/radar: 현재 스캔 결과**")
if scan is None:
    pass  # _try_fetch가 이미 warning 표시
elif not scan.get("enabled", True):
    st.info("이상탐지가 비활성화되어 있습니다 (ANOMALY_ENABLED).")
elif scan.get("findings"):
    _render_finding_cards(scan["findings"])
else:
    st.success("현재 이상 없음")

st.divider()

# ==========================================================
# ② 최근 30일 발행 이력 타임라인
# ==========================================================
st.markdown("**:material/timeline: 최근 30일 발행 이력**")
hist = _try_fetch("/anomaly/findings", {"days": 30, "limit": 500})
if hist is not None:
    rows = hist.get("findings", [])
    if not rows:
        empty_state(
            "아직 발행 이력이 없습니다.",
            hint="이상이 탐지·발행되면 첫 이력부터 여기 누적됩니다.",
        )
    else:
        daily = findings_to_daily_counts(rows)
        fig = go.Figure()
        for sev in ("critical", "warning", "info"):
            sub = daily[daily["severity"] == sev]
            if len(sub):
                fig.add_trace(go.Bar(
                    x=sub["day"], y=sub["count"], name=sev,
                    marker_color=SEVERITY_COLORS[sev],
                ))
        colors = get_colors()
        fig.update_layout(
            barmode="stack", height=260,
            template=colors.get("chart_template", "plotly_white"),
            margin=dict(l=40, r=20, t=10, b=30),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            xaxis_type="category",
        )
        st.plotly_chart(
            fig, width="stretch", config=get_chart_config("anomaly_timeline")
        )

        f1, f2 = st.columns(2)
        with f1:
            kind_f = st.selectbox(
                "종류", ["전체", *KIND_LABELS.values()], index=0
            )
        with f2:
            sev_f = st.selectbox(
                "심각도", ["전체", "critical", "warning", "info"], index=0
            )
        label_to_kind = {v: k for k, v in KIND_LABELS.items()}
        table = pd.DataFrame([
            {
                "발행 시각": r["emitted_at"],
                "종류": KIND_LABELS.get(r["kind"], r["kind"]),
                "심각도": r["severity"],
                "내용": r["message"],
            }
            for r in rows
            if (kind_f == "전체" or r["kind"] == label_to_kind.get(kind_f))
            and (sev_f == "전체" or r["severity"] == sev_f)
        ])
        st.dataframe(table, width="stretch", hide_index=True, height=280)

st.divider()

# ==========================================================
# ③ 쿨다운 현황
# ==========================================================
with st.expander(
    f"쿨다운 현황 ({len(active_cooldowns)}건 활성)", expanded=False
):
    if state is None:
        st.caption("상태를 불러오지 못했습니다.")
    elif not state.get("cooldowns"):
        st.caption("쿨다운 중인 이상이 없습니다.")
    else:
        st.caption(
            "쿨다운 중인 이상은 동일 key로 재탐지돼도 재발행되지 않습니다 "
            f"(쿨다운 {humanize_remaining(state['cooldown_sec'])})."
        )
        cd_table = pd.DataFrame([
            {
                "key": c["key"],
                "남은 시간": humanize_remaining(c["remaining_sec"]),
                "상태": "🔒 억제 중" if c["active"] else "만료",
            }
            for c in state["cooldowns"]
        ])
        st.dataframe(cd_table, width="stretch", hide_index=True)

# ==========================================================
# ④ what-if 임계치 미리보기
# ==========================================================
with st.expander("what-if 임계치 미리보기", expanded=False):
    rules = _try_fetch("/anomaly/rules")
    if rules is not None:
        st.caption(
            "임계치를 바꿔 현재 데이터를 재판정합니다 — "
            "**발행되지 않고 서버 설정도 변하지 않습니다** (.env가 기준)."
        )
        with st.form("whatif_form", border=False):
            c1, c2, c3 = st.columns(3)
            with c1:
                w_drop = st.number_input(
                    "급감 임계 %", min_value=0.1, max_value=100.0,
                    value=float(rules["drop_pct"]), step=5.0,
                )
                w_min = st.number_input(
                    "최소 기준선", min_value=0.0,
                    value=float(rules["min_baseline_qty"]), step=1.0,
                )
            with c2:
                w_spike = st.number_input(
                    "급증 임계 %", min_value=0.1, max_value=1000.0,
                    value=float(rules["spike_pct"]), step=10.0,
                )
                w_base = st.number_input(
                    "기준선 일수", min_value=1, max_value=365,
                    value=int(rules["baseline_days"]),
                )
            with c3:
                w_stale = st.number_input(
                    "미생산 임계 일수", min_value=1, max_value=365,
                    value=int(rules["stale_days"]),
                )
            submitted = st.form_submit_button(
                "미리보기 실행", icon=":material/science:", width="stretch"
            )
        if submitted:
            try:
                with st.spinner("what-if 미리보기 계산 중…"):
                    preview = _fetch_fresh("/anomaly/scan", {
                        "drop_pct": w_drop, "spike_pct": w_spike,
                        "stale_days": w_stale, "min_baseline_qty": w_min,
                        "baseline_days": w_base,
                    })
            except httpx.HTTPError as e:
                st.warning(f"미리보기 실패 ({e}).")
            else:
                st.info(
                    f"미리보기 — 발행되지 않음 · findings {preview['count']}건"
                )
                if preview.get("findings"):
                    _render_finding_cards(preview["findings"])
                else:
                    st.success("이 임계치에서는 이상 없음")
