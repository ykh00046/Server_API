"""
U7: Filter Preset Manager - Save and load filter configurations.

Allows users to save their filter settings as presets for quick access.
Presets are stored in Streamlit session state.
"""

import streamlit as st
from datetime import date, datetime
from typing import Optional, Dict, Any, List

# Maximum number of presets allowed
MAX_PRESETS = 10


def init_presets() -> None:
    """
    Initialize preset storage in session state.

    Call this once during app initialization.
    """
    if "filter_presets" not in st.session_state:
        st.session_state.filter_presets = {}


def get_preset_names() -> List[str]:
    """
    Get list of saved preset names.

    Returns:
        List of preset names (strings).
    """
    return list(st.session_state.get("filter_presets", {}).keys())


def save_preset(
    name: str,
    item_codes: Optional[List[str]],
    date_from: Optional[date],
    date_to: Optional[date],
    keyword: Optional[str],
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

    # Enforce maximum presets limit
    if len(presets) >= MAX_PRESETS and name not in presets:
        st.warning(f"프리셋은 최대 {MAX_PRESETS}개까지 저장 가능합니다. 기존 프리셋을 삭제해 주세요.")
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


def load_preset(name: str) -> Optional[Dict[str, Any]]:
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


def render_preset_manager(
    current_item_codes: Optional[List[str]],
    current_date_from: Optional[date],
    current_date_to: Optional[date],
    current_keyword: Optional[str],
    current_limit: int
) -> Optional[Dict[str, Any]]:
    """
    Render preset management UI in sidebar.

    Displays:
    - Dropdown to select and load existing presets
    - Apply and Delete buttons for selected preset
    - Input for new preset name
    - Save button for current filter settings

    Args:
        current_item_codes: Currently selected product codes
        current_date_from: Current start date
        current_date_to: Current end date
        current_keyword: Current search keyword
        current_limit: Current row limit

    Returns:
        Loaded preset dict if user clicked Apply, None otherwise.
        The caller should apply these values to the filter controls.
    """
    st.sidebar.divider()
    with st.sidebar.expander("📁 필터 프리셋", expanded=False):
        loaded_preset = None

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
                    if st.button("적용", key="apply_preset", use_container_width=True):
                        loaded_preset = load_preset(selected_preset)

                with col_b:
                    if st.button("삭제", key="delete_preset", use_container_width=True):
                        if delete_preset(selected_preset):
                            st.success(f"'{selected_preset}' 삭제됨")
                            st.rerun()

        # Save preset section
        st.text_input(
            "새 프리셋 이름",
            key="new_preset_name",
            placeholder="예: BW0021 최근 30일",
            help="현재 필터 설정을 저장할 이름을 입력하세요",
        )

        if st.button("현재 필터 저장", key="save_preset", use_container_width=True):
            name = st.session_state.get("new_preset_name", "").strip()
            if name:
                if save_preset(
                    name,
                    current_item_codes,
                    current_date_from,
                    current_date_to,
                    current_keyword,
                    current_limit
                ):
                    st.success(f"프리셋 '{name}' 저장됨!")
                    st.session_state.new_preset_name = ""
                    st.rerun()
            else:
                st.warning("프리셋 이름을 입력하세요")

        # Show preset count
        preset_count = len(get_preset_names())
        st.caption(f"프리셋: {preset_count}/{MAX_PRESETS}")

    return loaded_preset
