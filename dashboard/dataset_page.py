"""키워드-분할 데이터셋(자재요청·액상바인더출고 …) 공용 페이지 렌더러.

webcloring-pdf가 백업한 데이터를 기존 Excel과 동일한 한글 헤더/컬럼 순서로
표시하고 CSV·Excel로 내려받는다. 데이터셋마다 엔드포인트 prefix(/materials,
/binder …)만 다르고 화면 구성은 동일하므로, 한 `render()`를 prefix로
파라미터화해 각 페이지(views/materials.py, views/binder.py)가 호출한다.

데이터는 `GET {prefix}`(api/routers/materials.py 팩토리)를 HTTP로 호출해
가져온다. 정렬·날짜 필터는 문서번호 날짜(doc_date) 기준이다.
"""
from __future__ import annotations

import datetime as dt
import os

import httpx
import pandas as pd
import streamlit as st
from data import to_excel_bytes

from shared.config import API_BASE_URL

# API 필드 → 기존 Excel 헤더 (순서가 곧 Excel 컬럼 순서). 모든 데이터셋 공통.
EXCEL_COLUMNS: list[tuple[str, str]] = [
    ("seq", "순번"),
    ("material_code", "자재코드"),
    ("material_name", "품명"),
    ("request_qty_g", "요청수량(g단위)"),
    ("reason", "사유"),
    ("request_dept", "요청부서"),
    ("drafter", "기안자"),
    ("doc_number", "문서번호"),
    ("processed_at", "처리일시"),
]

_STATUS_ICON = {"running": "🔄", "success": "✅", "failed": "❌"}
_KIND_LABEL = {"backup": "백업 수신", "automation": "자동 실행"}


def _headers() -> dict:
    headers = {}
    api_key = os.getenv("MATERIALS_API_KEY") or os.getenv("DASHBOARD_API_KEY")
    if api_key:
        headers["X-API-Key"] = api_key
    return headers


def _to_excel_frame(rows: list[dict]) -> pd.DataFrame:
    """JSON 행들을 기존 Excel과 동일한 한글 헤더·순서의 DataFrame으로 변환."""
    if not rows:
        return pd.DataFrame(columns=[ko for _, ko in EXCEL_COLUMNS])
    data = {ko: [r.get(api_field) for r in rows] for api_field, ko in EXCEL_COLUMNS}
    return pd.DataFrame(data)


def render(
    *,
    prefix: str,
    title: str,
    icon: str,
    sheet_name: str,
    file_base: str,
    empty_msg: str,
) -> None:
    """한 데이터셋 페이지를 렌더한다.

    Args:
        prefix: API 경로 prefix (예: "/materials", "/binder").
        title: 페이지 제목 (예: "자재요청").
        icon: material 아이콘 토큰.
        sheet_name: Excel 시트명.
        file_base: 다운로드 파일명 베이스 (예: "material_requests").
        empty_msg: 데이터 없음 안내 문구.
    """

    def _fetch(params: dict) -> list[dict]:
        with httpx.Client(base_url=API_BASE_URL, timeout=15.0) as c:
            resp = c.get(prefix, params=params, headers=_headers())
            resp.raise_for_status()
            return resp.json()

    def _fetch_runs(limit: int = 20) -> list[dict]:
        with httpx.Client(base_url=API_BASE_URL, timeout=15.0) as c:
            resp = c.get(f"{prefix}/runs", params={"limit": limit}, headers=_headers())
            resp.raise_for_status()
            return resp.json()

    def _trigger_run() -> tuple[bool, str]:
        """POST {prefix}/run. Returns (ok, message). 409 → (False, detail)."""
        with httpx.Client(base_url=API_BASE_URL, timeout=15.0) as c:
            resp = c.post(f"{prefix}/run", headers=_headers())
        if resp.status_code == 200:
            return True, resp.json().get("message", "자동화 실행을 시작했습니다.")
        if resp.status_code == 409:
            return False, resp.json().get("detail", "실행할 수 없습니다.")
        return False, f"실행 요청 실패 (HTTP {resp.status_code})"

    st.title(f"{icon} {title}", anchor=False)
    st.caption(f"API: `{API_BASE_URL}{prefix}` · 정렬/필터 기준: 문서번호 날짜(doc_date)")

    # ----------------------------------------------------------
    # 실행 상태 / 이력 / 수동 실행
    # ----------------------------------------------------------
    try:
        run_list = _fetch_runs(20)
    except httpx.HTTPError as e:
        run_list = None
        st.warning(f"실행 이력을 불러오지 못했습니다 ({e}).")

    if run_list is not None:
        last = run_list[0] if run_list else None
        s1, s2, s3 = st.columns([3, 1, 1])
        with s1:
            if last:
                badge = _STATUS_ICON.get(last["status"], "•")
                kind = _KIND_LABEL.get(last["kind"], last["kind"])
                when = last.get("finished_at") or last.get("started_at")
                st.metric("마지막 실행", f"{badge} {kind} · {last['status']}", help=f"{when}")
            else:
                st.metric("마지막 실행", "기록 없음")
        with s2:
            if st.button("지금 실행", icon=":material/play_arrow:", width="stretch"):
                ok, msg = _trigger_run()
                (st.success if ok else st.warning)(msg)
                if ok:
                    st.rerun()
        with s3:
            if st.button("새로고침", icon=":material/refresh:", width="stretch"):
                st.rerun()

        with st.expander("실행 이력", expanded=False):
            if run_list:
                hist = pd.DataFrame([
                    {
                        "종류": _KIND_LABEL.get(r["kind"], r["kind"]),
                        "상태": f"{_STATUS_ICON.get(r['status'], '')} {r['status']}",
                        "시작": r.get("started_at"),
                        "종료": r.get("finished_at"),
                        "건수": r.get("rows"),
                        "신규": r.get("inserted"),
                        "갱신": r.get("updated"),
                        "메시지": (r.get("message") or "")[:120],
                    }
                    for r in run_list
                ])
                st.dataframe(hist, width="stretch", hide_index=True)
            else:
                st.caption("아직 실행 기록이 없습니다.")

    st.divider()

    # ----------------------------------------------------------
    # Filters
    # ----------------------------------------------------------
    f1, f2, f3 = st.columns([2, 2, 1])
    with f1:
        dept = st.text_input("요청부서", placeholder="예: 생산1팀 (비우면 전체)").strip()
    with f2:
        use_date = st.toggle("문서번호 날짜로 필터", value=False)
    with f3:
        limit = st.number_input("최대 건수", min_value=1, max_value=5000, value=1000, step=100)

    date_from = date_to = None
    if use_date:
        d1, d2 = st.columns(2)
        with d1:
            df_in = st.date_input("시작일(문서번호 날짜)", value=None, format="YYYY-MM-DD")
        with d2:
            dt_in = st.date_input("종료일(문서번호 날짜)", value=None, format="YYYY-MM-DD")
        date_from = df_in.isoformat() if isinstance(df_in, dt.date) else None
        date_to = dt_in.isoformat() if isinstance(dt_in, dt.date) else None

    params: dict = {"limit": int(limit)}
    if dept:
        params["request_dept"] = dept
    if date_from:
        params["date_from"] = date_from
    if date_to:
        params["date_to"] = date_to

    # ----------------------------------------------------------
    # Fetch + render
    # ----------------------------------------------------------
    try:
        rows = _fetch(params)
    except httpx.HTTPError as e:
        st.error(f"{title} 데이터를 불러오지 못했습니다 ({e}). API 서버 상태를 확인하세요.")
        st.stop()

    df = _to_excel_frame(rows)

    st.metric("조회 건수", f"{len(df):,}건")

    if df.empty:
        st.info(empty_msg)
        st.stop()

    st.dataframe(df, width="stretch", hide_index=True)

    # ----------------------------------------------------------
    # Downloads (기존 Excel 레이아웃 그대로)
    # ----------------------------------------------------------
    c1, c2, _ = st.columns([1, 1, 4])
    with c1:
        st.download_button(
            "Excel 다운로드",
            data=to_excel_bytes(df, sheet_name=sheet_name),
            file_name=f"{file_base}.xlsx",
            icon=":material/download:",
            width="stretch",
        )
    with c2:
        st.download_button(
            "CSV 다운로드",
            data=df.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"{file_base}.csv",
            mime="text/csv",
            icon=":material/csv:",
            width="stretch",
        )
