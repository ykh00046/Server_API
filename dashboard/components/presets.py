"""
U7: Filter Preset Manager - Save and load filter configurations.

Allows users to save their filter settings as presets for quick access.
Presets are stored in Streamlit session state.
"""

from datetime import date, datetime
from typing import Any

import streamlit as st

# Maximum number of presets allowed
MAX_PRESETS = 10


def init_presets() -> None:
    """
    Initialize preset storage in session state.

    Call this once during app initialization.
    """
    if "filter_presets" not in st.session_state:
        st.session_state.filter_presets = {}


def get_preset_names() -> list[str]:
    """
    Get list of saved preset names.

    Returns:
        List of preset names (strings).
    """
    return list(st.session_state.get("filter_presets", {}).keys())


def save_preset(
    name: str,
    item_codes: list[str] | None,
    date_from: date | None,
    date_to: date | None,
    keyword: str | None,
    limit: int
) -> bool:
    """
    Save current filter settings as a preset.

    Args:
        name: Preset name (must be non-empty)
        item_codes: List of selected product codes
        date_from: Start date filter
        date_to: End date filter
        keyword: Search keyword
        limit: Row limit

    Returns:
        True if saved successfully, False otherwise.
    """
    if not name or not name.strip():
        return False

    name = name.strip()
    presets = st.session_state.get("filter_presets", {})

    # Enforce maximum presets limit (pure: the caller renders the warning)
    if len(presets) >= MAX_PRESETS and name not in presets:
        return False

    # Store preset
    presets[name] = {
        "item_codes": item_codes,
        "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat() if date_to else None,
        "keyword": keyword,
        "limit": limit,
        "created_at": datetime.now().isoformat()
    }

    st.session_state.filter_presets = presets
    return True


def load_preset(name: str) -> dict[str, Any] | None:
    """
    Load preset by name.

    Args:
        name: Preset name to load

    Returns:
        Preset dict with values, or None if not found.
        Date strings are converted back to date objects.
    """
    presets = st.session_state.get("filter_presets", {})
    preset = presets.get(name)

    if preset:
        # Create a copy to avoid modifying the stored preset
        result = dict(preset)
        # Convert date strings back to date objects
        if result.get("date_from"):
            try:
                result["date_from"] = date.fromisoformat(result["date_from"])
            except ValueError:
                result["date_from"] = None
        if result.get("date_to"):
            try:
                result["date_to"] = date.fromisoformat(result["date_to"])
            except ValueError:
                result["date_to"] = None
        return result

    return None


def delete_preset(name: str) -> bool:
    """
    Delete preset by name.

    Args:
        name: Preset name to delete

    Returns:
        True if deleted, False if not found.
    """
    presets = st.session_state.get("filter_presets", {})
    if name in presets:
        del presets[name]
        st.session_state.filter_presets = presets
        return True
    return False


def apply_pending_preset(label_by_code: dict[str, str]) -> None:
    """Consume the preset queued by the 적용 button into the filter-widget
    session keys (flt_*). Must run BEFORE those widgets are instantiated —
    Streamlit forbids assigning a widget's session key after instantiation.

    Args:
        label_by_code: item_code → multiselect label mapping for the current
            product list; preset codes that no longer exist are dropped.
    """
    pending = st.session_state.pop("_pending_preset", None)
    if not pending:
        return
    st.session_state["flt_limit"] = int(pending.get("limit") or 5000)
    st.session_state["flt_keyword"] = pending.get("keyword") or ""
    if pending.get("date_from") and pending.get("date_to"):
        st.session_state["flt_dates"] = (pending["date_from"], pending["date_to"])
    st.session_state["flt_products"] = [
        label_by_code[c]
        for c in (pending.get("item_codes") or [])
        if c in label_by_code
    ]


def _on_save_click(
    item_codes: list[str] | None,
    date_from: date | None,
    date_to: date | None,
    keyword: str | None,
    limit: int,
) -> None:
    """on_click callback for the save button. Callbacks run before the next
    script run, so clearing the text_input widget key here is legal — the old
    in-script `st.session_state.new_preset_name = ""` raised
    StreamlitAPIException on every save."""
    name = (st.session_state.get("new_preset_name") or "").strip()
    if not name:
        st.session_state["_preset_msg"] = ("warning", "프리셋 이름을 입력하세요")
    elif save_preset(name, item_codes, date_from, date_to, keyword, limit):
        st.session_state["_preset_msg"] = ("success", f"프리셋 '{name}' 저장됨!")
        st.session_state.new_preset_name = ""
    else:
        st.session_state["_preset_msg"] = (
            "warning",
            f"프리셋은 최대 {MAX_PRESETS}개까지 저장 가능합니다. "
            "기존 프리셋을 삭제해 주세요.",
        )


def render_preset_manager(
    current_item_codes: list[str] | None,
    current_date_from: date | None,
    current_date_to: date | None,
    current_keyword: str | None,
    current_limit: int
) -> None:
    """
    Render preset management UI in sidebar.

    Displays:
    - Dropdown to select and load existing presets
    - Apply and Delete buttons for selected preset
    - Input for new preset name
    - Save button for current filter settings

    적용 queues the preset into st.session_state["_pending_preset"] and
    reruns; the app consumes it via apply_pending_preset() before the filter
    widgets are created, so the widgets actually reflect the preset.
    """
    st.sidebar.divider()
    with st.sidebar.expander("필터 프리셋", icon=":material/folder:", expanded=False):
        # Load preset section
        preset_names = get_preset_names()
        if preset_names:
            selected_preset = st.selectbox(
                "프리셋 불러오기",
                options=["-- 선택 --"] + preset_names,
                index=0,
                key="preset_selector",
                help="저장된 필터 프리셋을 선택하세요",
            )

            if selected_preset and selected_preset != "-- 선택 --":
                col_a, col_b = st.columns(2)

                with col_a:
                    if st.button("적용", key="apply_preset", width="stretch"):
                        loaded = load_preset(selected_preset)
                        if loaded:
                            st.session_state["_pending_preset"] = loaded
                            st.session_state["_preset_msg"] = (
                                "success", f"프리셋 '{selected_preset}' 적용됨"
                            )
                            st.rerun()

                with col_b:
                    if st.button(
                        "삭제", key="delete_preset", width="stretch"
                    ) and delete_preset(selected_preset):
                        st.success(f"'{selected_preset}' 삭제됨")
                        st.rerun()

        # Save preset section
        st.text_input(
            "새 프리셋 이름",
            key="new_preset_name",
            placeholder="예: BW0021 최근 30일",
            help="현재 필터 설정을 저장할 이름을 입력하세요",
        )

        st.button(
            "현재 필터 저장",
            key="save_preset",
            width="stretch",
            on_click=_on_save_click,
            args=(
                current_item_codes,
                current_date_from,
                current_date_to,
                current_keyword,
                current_limit,
            ),
        )

        # Deferred feedback from the save callback / apply rerun
        msg = st.session_state.pop("_preset_msg", None)
        if msg:
            level, text = msg
            getattr(st, level)(text)

        # Show preset count
        preset_count = len(get_preset_names())
        st.caption(f"프리셋: {preset_count}/{MAX_PRESETS}")
