"""
Layout Components — shared layout helpers for all pages.

Provides:
- page_header(): 통일 페이지 헤더 (제목 + 한 줄 캡션 + 구분선) — 모든 뷰 공용.
- section_header(): 페이지 안 섹션 제목 (h4 + material 아이콘) — 전 뷰 공용.
- empty_state(): 빈 결과/로딩 대체 안내 (메시지 + 다음 행동 힌트) — 전 뷰 공용.
- download_pair(): Excel + CSV 다운로드 버튼 쌍 — 표를 내려받는 모든 뷰 공용.
- render_page_header(): page_header + AI 패널 토글 (AI 컬럼을 쓰는 뷰 전용).
- get_page_columns() / render_ai_column(): 2-Panel layout
"""

import pandas as pd
import streamlit as st


def init_ai_panel_state() -> None:
    """Initialize AI panel toggle state."""
    if "ai_panel_open" not in st.session_state:
        st.session_state["ai_panel_open"] = False  # 기본: 닫힘 (메인 콘텐츠 우선)


def page_header(title: str, caption: str = "", icon: str | None = None) -> None:
    """통일된 페이지 헤더: 제목(아이콘 옵션) + 한 줄 캡션 + 구분선.

    모든 뷰(overview/trends/batches/products/materials/binder/webhooks/anomaly)가
    동일한 헤더 패턴을 갖도록 한다. 색상·타이포는 config.toml 테마에 맡긴다
    (st.title/st.caption 은 네이티브 테이밍을 따르므로 라이트/다크 모두 깨지지 않는다).

    Args:
        title: 페이지 제목 텍스트 (아이콘은 별도 icon 인자로 전달).
        caption: 제목 아래 한 줄 설명. 빈 문자열이면 캡션 미출력.
        icon: ':material/...:' 토큰. 주면 제목 앞에 붙인다.
    """
    heading = f"{icon} {title}" if icon else title
    st.title(heading, anchor=False)
    if caption:
        st.caption(caption)
    st.divider()


def section_header(title: str, icon: str | None = None) -> None:
    """페이지 안의 섹션 제목 — 모든 뷰의 단일 표기법.

    표준 표기는 h4 마크다운 헤딩 `#### :material/…: 제목` 이다. 이전에는 같은
    역할의 제목이 네 가지(`**볼드**`, `#### 헤딩`, `st.subheader`, `##### 소제목`)
    로 흩어져 있어 한 화면 안에서도 크기·굵기가 달랐다. 그중
    - `st.subheader`(h3)는 page_header(st.title, h1) 바로 아래에 오기엔 크고,
    - `**볼드**`는 본문 텍스트와 같은 크기라 섹션 경계가 눈에 잡히지 않는다.
    h4는 제목(h1) → 섹션(h4) → 본문의 위계를 한 단계로 정리하면서도 2단 컬럼
    안의 차트 제목으로 쓸 만큼 절제돼 있어 이를 정본으로 삼는다.

    색상·타이포는 config.toml 테마에 맡긴다 (unsafe_allow_html 미사용).

    Args:
        title: 섹션 제목 텍스트 (아이콘은 별도 icon 인자로 전달).
        icon: ':material/...:' 토큰. 주면 제목 앞에 붙인다.
    """
    heading = f"{icon} {title}" if icon else title
    st.markdown(f"#### {heading}")


def empty_state(message: str, hint: str | None = None, icon: str = ":material/inbox:") -> None:
    """데이터 없음/빈 결과의 통일 안내 상태.

    st.info 메시지 + (선택) 다음 행동 힌트 캡션을 함께 보여준다.
    단순 st.info("데이터가 없습니다.") 대신 "왜 비었는지 + 무엇을 해볼 수 있는지"를
    주기 위한 공용 헬퍼. unsafe_allow_html 없이 네이티브 위젯만 사용한다.

    Args:
        message: 빈 상태의 핵심 안내 문구.
        hint: 사용자가 시도해볼 다음 행동 제안. None 이면 힌트 줄 생략.
        icon: 안내에 쓸 material 아이콘 토큰 (기본: inbox).
    """
    st.info(message, icon=icon)
    if hint:
        st.caption(f"다음: {hint}")


def download_pair(
    df: pd.DataFrame,
    excel_bytes: bytes,
    file_base: str,
    *,
    excel_label: str = "Excel 다운로드",
    csv_label: str = "CSV 다운로드",
) -> None:
    """표 내려받기 버튼 쌍 (Excel + CSV) — 동일 폭·아이콘·정렬로 통일.

    CSV는 Excel 한글 깨짐 방지를 위해 utf-8-sig 로 인코딩한다.

    excel_bytes 는 호출 측에서 `_cached_excel_bytes(...)` 로 만들어 넘긴다:
    download_button 의 data= 는 클릭 여부와 무관하게 매 rerun 마다 평가되므로,
    여기서 eager 직렬화를 하면 위젯을 건드릴 때마다 전체 시트를 다시 만든다.

    Args:
        df: CSV로 내보낼 DataFrame (표시용으로 이름을 바꾼 프레임일 수 있다).
        excel_bytes: 이미 직렬화(캐시)된 xlsx 바이트.
        file_base: 확장자를 뺀 파일명 베이스 (예: "production_records").
        excel_label: Excel 버튼 라벨.
        csv_label: CSV 버튼 라벨.
    """
    # 고정 비율 컬럼([1,1,4]) 대신 horizontal 컨테이너: 버튼이 내용 폭을
    # 유지하고 좁은 화면(768-1024px)에서도 세로 글자 뭉개짐 없이 줄바꿈된다.
    with st.container(horizontal=True):
        st.download_button(
            excel_label,
            data=excel_bytes,
            file_name=f"{file_base}.xlsx",
            icon=":material/download:",
        )
        st.download_button(
            csv_label,
            data=df.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"{file_base}.csv",
            mime="text/csv",
            icon=":material/csv:",
        )


def render_page_header(title: str, breadcrumb: str = "") -> None:
    """AI 토글이 포함된 페이지 헤더 (AI 컬럼을 사용하는 뷰 전용).

    page_header 의 시각적 패턴(제목+캡션+구분선)을 따르되, AI 패널 토글 버튼을
    제목 행의 별도 컬럼에 함께 렌더한 뒤 구분선으로 마무리한다.
    """
    col_title, col_toggle = st.columns([8, 2])
    with col_title:
        st.title(title, anchor=False)
        if breadcrumb:
            st.caption(breadcrumb)
    with col_toggle:
        is_open = st.session_state.get("ai_panel_open", False)
        btn_label = "AI 닫기" if is_open else "AI 열기"
        if st.button(btn_label, icon=":material/smart_toy:", key=f"ai_toggle_{title}"):
            st.session_state["ai_panel_open"] = not is_open
            st.rerun()
    st.divider()


def get_page_columns():
    """Get main and AI columns based on AI panel state.

    Returns:
        (col_main, col_ai) or (container, None)
    """
    if st.session_state.get("ai_panel_open", False):
        col_main, col_ai = st.columns([7, 3])
        return col_main, col_ai
    else:
        return st.container(), None


def render_ai_column(col_ai) -> None:
    """Render AI panel in the provided column."""
    if col_ai is None:
        return
    with col_ai:
        from components.ai_section import render_ai_section_compact
        render_ai_section_compact()
