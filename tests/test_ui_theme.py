# tests/test_ui_theme.py
"""Unit tests for shared/ui/theme.py and shared/ui/responsive.py.

Streamlit is mocked at the attribute level so the thin render wrappers and the
pure palette/getters can be exercised without a live Streamlit runtime.
"""

import types
from unittest.mock import MagicMock

import pytest

from shared.ui import responsive as resp
from shared.ui import theme as th


def _ctx(base):
    """Build a fake st.context whose .theme.base == base."""
    return types.SimpleNamespace(theme=types.SimpleNamespace(base=base))


# ==========================================================
# theme.get_theme / get_colors
# ==========================================================
class TestThemeDetection:
    def test_dark(self, monkeypatch):
        monkeypatch.setattr(th.st, "context", _ctx("dark"))
        assert th.get_theme() == "dark"
        assert th.get_colors()["chart_template"] == "plotly_dark"

    def test_light(self, monkeypatch):
        monkeypatch.setattr(th.st, "context", _ctx("light"))
        assert th.get_theme() == "light"
        assert th.get_colors()["primary"] == "#2563eb"

    def test_light_on_attribute_error(self, monkeypatch):
        # st.context without a .theme attribute -> AttributeError -> light.
        monkeypatch.setattr(th.st, "context", types.SimpleNamespace())
        assert th.get_theme() == "light"


# ==========================================================
# theme legacy/no-op + CSS hooks
# ==========================================================
class TestThemeHooks:
    def test_init_and_dark_mode_css_are_noops(self):
        # Pure no-ops: must not raise.
        assert th.init_theme() is None
        assert th.apply_dark_mode_css() is None

    def test_render_theme_toggle(self, monkeypatch):
        monkeypatch.setattr(th.st, "context", _ctx("dark"))
        fake_sidebar = MagicMock()
        monkeypatch.setattr(th.st, "sidebar", fake_sidebar)
        assert th.render_theme_toggle() is True
        fake_sidebar.caption.assert_called_once()

    def test_render_theme_toggle_light(self, monkeypatch):
        monkeypatch.setattr(th.st, "context", _ctx("light"))
        monkeypatch.setattr(th.st, "sidebar", MagicMock())
        assert th.render_theme_toggle() is False

    def test_series_colors_constant(self):
        assert th.CHART_SERIES_COLORS[0] == "#2563eb"
        assert len(th.CHART_SERIES_COLORS) == 10

    def test_theme_module_injects_no_html(self):
        # ui-design-overhaul-v1 이후 theme.py는 palette 전용이다. 마지막 CSS
        # 잔재(_STARTER_CARD_CSS)는 1.58 DOM과 셀렉터가 맞지 않아 휴면 상태로
        # 확인돼 제거됐다 — HTML 주입이 다시 생기면 여기서 잡는다.
        import inspect

        src = inspect.getsource(th)
        assert "unsafe_allow_html" not in src
        assert not hasattr(th, "apply_custom_css")


# ==========================================================
# config.toml palette mirror drift guard
# ==========================================================
class TestPaletteMirror:
    def test_categorical_colors_mirror_config_toml(self):
        # CHART_CATEGORICAL_COLORS는 .streamlit/config.toml의
        # chartCategoricalColors를 수동 미러링한다(plotly 수제 figure에는
        # 네이티브 테마 팔레트가 닿지 않으므로). 한쪽만 고치면 차트와
        # 네이티브 요소의 색이 조용히 어긋난다 — 이 테스트가 드리프트를 막는다.
        import tomllib
        from pathlib import Path

        cfg_path = Path(__file__).resolve().parent.parent / ".streamlit" / "config.toml"
        with cfg_path.open("rb") as f:
            cfg = tomllib.load(f)
        assert cfg["theme"]["chartCategoricalColors"] == th.CHART_CATEGORICAL_COLORS


# ==========================================================
# responsive.apply_responsive_css
# ==========================================================
class TestResponsive:
    def test_apply_responsive_css(self, monkeypatch):
        fake_md = MagicMock()
        monkeypatch.setattr(resp.st, "markdown", fake_md)
        resp.apply_responsive_css()
        fake_md.assert_called_once()
        html = fake_md.call_args[0][0]
        assert "@media" in html
        assert fake_md.call_args[1].get("unsafe_allow_html") is True


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
