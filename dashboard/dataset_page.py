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

import httpx
import pandas as pd
import streamlit as st
from components.layout import empty_state, page_header
from data import _cached_excel_bytes

from shared.api_client import auth_headers
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
    return auth_headers()


def _to_excel_frame(
    rows: list[dict], columns: list[tuple[str, str]]
) -> pd.DataFrame:
    """JSON 행들을 기존 Excel과 동일한 한글 헤더·순서의 DataFrame으로 변환."""
    if not rows:
        return pd.DataFrame(columns=[ko for _, ko in columns])
    data = {ko: [r.get(api_field) for r in rows] for api_field, ko in columns}
    return pd.DataFrame(data)


def _fetch_rows(prefix: str, params: dict) -> list[dict]:
    with httpx.Client(base_url=API_BASE_URL, timeout=15.0) as c:
        resp = c.get(prefix, params=params, headers=_headers())
        resp.raise_for_status()
        return resp.json()


def _fetch_runs(prefix: str, limit: int = 20) -> list[dict]:
    with httpx.Client(base_url=API_BASE_URL, timeout=15.0) as c:
        resp = c.get(f"{prefix}/runs", params={"limit": limit}, headers=_headers())
        resp.raise_for_status()
        return resp.json()


def _fetch_tombstones(prefix: str) -> list[dict]:
    with httpx.Client(base_url=API_BASE_URL, timeout=15.0) as c:
        resp = c.get(f"{prefix}/tombstones", headers=_headers())
        resp.raise_for_status()
        return resp.json()


def _json_body_or_empty(resp: httpx.Response) -> dict:
    """응답 본문을 dict로 파싱 — 본문이 없거나 dict가 아니면 {} 로 폴백."""
    try:
        body = resp.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _trigger_run(prefix: str) -> tuple[bool, str]:
    """POST {prefix}/run. Returns (ok, message). 409 → (False, detail)."""
    try:
        with httpx.Client(base_url=API_BASE_URL, timeout=15.0) as c:
            resp = c.post(f"{prefix}/run", headers=_headers())
    except httpx.HTTPError as e:
        # 형제 _fetch들과 동일 계약 — API 다운 시 페이지 크래시 금지
        return False, f"API 연결 실패 ({e}). 서버 상태를 확인하세요."
    body = _json_body_or_empty(resp)
    if resp.status_code == 200:
        return True, body.get("message", "자동화 실행을 시작했습니다.")
    # 409 중복 / 503 비활성 / 500 설정오류 — 서버 detail을 그대로 노출
    detail = body.get("detail")
    return False, detail or f"실행 요청 실패 (HTTP {resp.status_code})"


def _delete(prefix: str, doc_number: str) -> tuple[bool, str]:
    """DELETE {prefix}/{doc_number}. Returns (ok, message). 404 → (False, detail)."""
    try:
        with httpx.Client(base_url=API_BASE_URL, timeout=15.0) as c:
            resp = c.delete(f"{prefix}/{doc_number}", headers=_headers())
    except httpx.HTTPError as e:
        return False, f"API 연결 실패 ({e}). 서버 상태를 확인하세요."
    body = _json_body_or_empty(resp)
    if resp.status_code == 200:
        return True, f"문서 {doc_number} 삭제 완료 (품목 {body.get('deleted', 0)}행)."
    detail = body.get("detail")
    return False, detail or f"삭제 실패 (HTTP {resp.status_code})"


def _restore(prefix: str, doc_number: str) -> tuple[bool, str]:
    """POST {prefix}/{doc_number}/restore. Returns (ok, message). 404 → (False, detail)."""
    try:
        with httpx.Client(base_url=API_BASE_URL, timeout=15.0) as c:
            resp = c.post(f"{prefix}/{doc_number}/restore", headers=_headers())
    except httpx.HTTPError as e:
        return False, f"API 연결 실패 ({e}). 서버 상태를 확인하세요."
    body = _json_body_or_empty(resp)
    if resp.status_code == 200:
        return True, f"문서 {doc_number} 복원 대기 — 다음 백업 때 다시 들어옵니다."
    detail = body.get("detail")
    return False, detail or f"복원 실패 (HTTP {resp.status_code})"


def _render_runs_panel(prefix: str) -> None:
    """실행 상태 / 이력 / 수동 실행 패널. 이력 조회 실패 시 경고만 남긴다."""
    try:
        with st.spinner("실행 이력 조회 중…"):
            run_list = _fetch_runs(prefix, 20)
    except httpx.HTTPError as e:
        st.warning(f"실행 이력을 불러오지 못했습니다 ({e}).")
        return

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
            with st.spinner("자동화 실행 요청 중…"):
                ok, msg = _trigger_run(prefix)
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


def _render_delete_expander(prefix: str) -> None:
    """문서 삭제 (실수 기안·중복 문서 제거) — 목록 유무와 무관하게 항상 노출.

    삭제한 문서는 tombstone으로 막히고, 복원(restore)으로 되돌릴 수 있다.
    tombstone 목록 조회는 페이지를 깨면 안 되므로 실패 시 경고만 남긴다.
    """
    with st.expander("문서 삭제 (실수 기안·중복 문서 제거)", expanded=False):
        st.caption(
            "문서번호로 해당 문서의 모든 품목 행을 서버에서 삭제합니다. "
            "삭제하면 tombstone이 남아 봇이 전체 Excel을 재전송(백업)해도 "
            "제외되어 다시 살아나지 않습니다. 복원하면 다음 백업 때 다시 들어옵니다."
        )
        del_doc = st.text_input(
            "삭제할 문서번호",
            placeholder="예: 20260721P227-0001",
            key=f"del_{prefix}",
        ).strip()
        confirm = st.checkbox("삭제를 확인합니다", key=f"delok_{prefix}")
        if st.button(
            "문서 삭제",
            icon=":material/delete:",
            disabled=not (del_doc and confirm),
            key=f"delbtn_{prefix}",
        ):
            with st.spinner("문서 삭제 중…"):
                ok, msg = _delete(prefix, del_doc)
            (st.success if ok else st.error)(msg)
            if ok:
                st.rerun()

        # ----------------------------------------------------------
        # 삭제된 문서 (복원 가능) — tombstone 목록
        # ----------------------------------------------------------
        st.markdown("##### 삭제된 문서 (복원 가능)")
        try:
            with st.spinner("삭제된 문서 목록 조회 중…"):
                tombstones = _fetch_tombstones(prefix)
        except httpx.HTTPError as e:
            st.caption(f"⚠️ 삭제된 문서 목록을 불러오지 못했습니다 ({e}).")
            return

        if not tombstones:
            st.caption("삭제된 문서가 없습니다.")
            return

        for t in tombstones:
            doc = t.get("doc_number", "")
            when = t.get("deleted_at", "")
            cols = st.columns([4, 3, 1])
            with cols[0]:
                st.markdown(f"`{doc}`" if doc else "—")
            with cols[1]:
                st.caption(f":material/schedule: {when}" if when else "")
            with cols[2]:
                if st.button(
                    "복원",
                    icon=":material/restore:",
                    key=f"rst_{prefix}_{doc}",
                    width="stretch",
                ):
                    with st.spinner("문서 복원 중…"):
                        ok, msg = _restore(prefix, doc)
                    (st.success if ok else st.error)(msg)
                    if ok:
                        st.rerun()


def _render_filters() -> dict:
    """필터 위젯 렌더 + API 쿼리 파라미터 dict 반환."""
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
    return params


def _fetch_and_render_rows(
    prefix: str, title: str, params: dict, columns, sheet_name: str, file_base: str, empty_msg: str
) -> None:
    """데이터 fetch + 표/건수/다운로드 렌더. 데이터 없으면 st.stop()."""
    try:
        with st.spinner(f"{title} 데이터 조회 중…"):
            rows = _fetch_rows(prefix, params)
    except httpx.HTTPError as e:
        st.error(f"{title} 데이터를 불러오지 못했습니다 ({e}). API 서버 상태를 확인하세요.")
        st.stop()

    df = _to_excel_frame(rows, columns)

    st.metric("조회 건수", f"{len(df):,}건")

    if df.empty:
        empty_state(
            empty_msg,
            hint="필터(요청부서·날짜·건수)를 조정하거나 ‘지금 실행’으로 데이터를 수집해 보세요.",
        )
        st.stop()

    st.dataframe(df, width="stretch", hide_index=True)

    # ----------------------------------------------------------
    # Downloads (기존 Excel 레이아웃 그대로)
    # ----------------------------------------------------------
    c1, c2, _ = st.columns([1, 1, 4])
    with c1:
        st.download_button(
            "Excel 다운로드",
            # 캐시 필수: download_button의 data=는 클릭과 무관하게 매 rerun마다
            # 평가되므로 eager 직렬화는 위젯 상호작용마다 전체 시트를 재생성한다
            data=_cached_excel_bytes(df, sheet_name=sheet_name),
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


def render(
    *,
    prefix: str,
    title: str,
    icon: str,
    sheet_name: str,
    file_base: str,
    empty_msg: str,
    columns: list[tuple[str, str]] | None = None,
) -> None:
    """한 데이터셋 페이지를 렌더한다.

    Args:
        prefix: API 경로 prefix (예: "/materials", "/binder").
        title: 페이지 제목 (예: "자재요청").
        icon: material 아이콘 토큰.
        sheet_name: Excel 시트명.
        file_base: 다운로드 파일명 베이스 (예: "material_requests").
        empty_msg: 데이터 없음 안내 문구.
        columns: (api_field, 한글헤더) 목록. 생략 시 자재 레이아웃
            (EXCEL_COLUMNS). 스키마는 데이터셋 공통이지만 헤더 의미가
            다른 데이터셋(예: 바인더 출고)은 여기로 교체한다.
    """
    columns = columns or EXCEL_COLUMNS

    page_header(
        title,
        caption=f"API: `{API_BASE_URL}{prefix}` · 정렬/필터 기준: 문서번호 날짜(doc_date)",
        icon=icon,
    )

    # ----------------------------------------------------------
    # 실행 상태 / 이력 / 수동 실행
    # ----------------------------------------------------------
    _render_runs_panel(prefix)

    # ----------------------------------------------------------
    # 문서 삭제 (실수 기안·중복 문서 제거) — 목록 유무와 무관하게 항상 노출
    # ----------------------------------------------------------
    _render_delete_expander(prefix)

    st.divider()

    # ----------------------------------------------------------
    # Filters
    # ----------------------------------------------------------
    params = _render_filters()

    # ----------------------------------------------------------
    # Fetch + render
    # ----------------------------------------------------------
    _fetch_and_render_rows(
        prefix, title, params, columns, sheet_name, file_base, empty_msg
    )
