"""Smoke tests: verify every PRODUCTION_TOOL produces a Gemini-valid schema.

Catches drift like the 2026-04-24 regression where `list` without element type
silently shipped to Gemini as `ARRAY` with missing `items` -> 400 INVALID_ARGUMENT.
"""
from __future__ import annotations

import pytest
from google.genai.types import FunctionDeclaration, Type

from api._tool_dispatch import PRODUCTION_TOOLS


class _FakeClient:
    """Minimal stub - FunctionDeclaration.from_callable only reads .vertexai.

    Avoids the real genai.Client dependency on GEMINI_API_KEY, keeping these
    tests offline and deterministic.
    """
    vertexai = False


_FAKE_CLIENT = _FakeClient()


def _declare(tool_fn):
    """Shortcut: generate FunctionDeclaration for a Python tool callable."""
    return FunctionDeclaration.from_callable(client=_FAKE_CLIENT, callable=tool_fn)


# ------------------------------------------------------------------
# Parametrized per-tool smoke
# ------------------------------------------------------------------
@pytest.mark.parametrize(
    "tool_fn", PRODUCTION_TOOLS, ids=lambda f: f.__name__
)
class TestToolSchemaSmoke:
    def test_generates_without_error(self, tool_fn):
        """Schema generation must not raise - catches broken signatures."""
        fd = _declare(tool_fn)
        assert fd is not None

    def test_name_matches_callable(self, tool_fn):
        fd = _declare(tool_fn)
        assert fd.name == tool_fn.__name__

    def test_description_non_empty(self, tool_fn):
        fd = _declare(tool_fn)
        assert fd.description, f"{tool_fn.__name__} missing description (docstring)"

    def test_parameters_have_properties(self, tool_fn):
        """All PRODUCTION_TOOLS take at least one argument."""
        fd = _declare(tool_fn)
        assert fd.parameters is not None
        assert fd.parameters.properties, (
            f"{tool_fn.__name__}: parameters.properties is empty"
        )

    def test_no_array_without_items(self, tool_fn):
        """Core regression guard (2026-04-24): every ARRAY property must have `items`.

        Catches `param: list = None` (element type missing) which Gemini rejects
        with `properties[X].items: missing field`.
        """
        fd = _declare(tool_fn)
        for prop_name, prop in fd.parameters.properties.items():
            if prop.type == Type.ARRAY:
                assert prop.items is not None, (
                    f"{tool_fn.__name__}.{prop_name}: ARRAY property has no items - "
                    f"use list[str] / list[int] / etc. instead of bare list"
                )
                assert prop.items.type != Type.TYPE_UNSPECIFIED, (
                    f"{tool_fn.__name__}.{prop_name}: items.type is TYPE_UNSPECIFIED"
                )

    def test_no_unspecified_types(self, tool_fn):
        """No property should have TYPE_UNSPECIFIED (hidden unknown type hint)."""
        fd = _declare(tool_fn)
        for prop_name, prop in fd.parameters.properties.items():
            assert prop.type != Type.TYPE_UNSPECIFIED, (
                f"{tool_fn.__name__}.{prop_name}: type is TYPE_UNSPECIFIED "
                f"(check Python type hint)"
            )


# ------------------------------------------------------------------
# Global invariants
# ------------------------------------------------------------------
def test_production_tools_not_empty():
    assert len(PRODUCTION_TOOLS) >= 1, "PRODUCTION_TOOLS registry is empty"


def test_tool_names_unique():
    names = [f.__name__ for f in PRODUCTION_TOOLS]
    assert len(names) == len(set(names)), f"duplicate tool names: {names}"
