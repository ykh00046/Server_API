# tool-schema-smoke-test Design Document

> **Summary**: PRODUCTION_TOOLS 7개에 대해 Gemini schema smoke 검증 pytest 구현
>
> **Project**: Server_API (Production Data Hub)
> **Date**: 2026-04-24
> **Status**: Design

---

## 1. Architecture Decisions

### AD-1: Schema 생성은 `FunctionDeclaration.from_callable`로

- SDK public API이므로 SDK 업그레이드 시 안정성이 비교적 보장됨.
- Python callable + docstring만 있으면 schema 반환. 별도 API 호출 없음 (offline-safe).

### AD-2: API key 회피를 위한 `_FakeClient` stub

- `from_callable`은 `client.vertexai` 속성만 읽음 (확인됨).
- 실제 `genai.Client`는 `GEMINI_API_KEY` 필요 → CI/dev 환경 분산 시 test flaky.
- 최소 stub `class _FakeClient: vertexai = False` 으로 API key 없이 schema 생성 가능.

```python
class _FakeClient:
    """Minimal stub — FunctionDeclaration.from_callable only reads .vertexai."""
    vertexai = False
```

### AD-3: pytest parametrize로 도구별 격리

```python
@pytest.mark.parametrize("tool_fn", PRODUCTION_TOOLS, ids=lambda f: f.__name__)
def test_schema_has_items_for_arrays(tool_fn):
    ...
```

- 실패 시 정확히 어떤 도구가 깨졌는지 test ID로 즉시 식별.
- `PRODUCTION_TOOLS`에 새 도구 추가 시 **자동으로 검증 대상에 포함** — 명시 등록 불필요.

### AD-4: 검증 항목 우선순위

| Check | 이유 |
|-------|------|
| schema 생성 성공 (예외 없음) | 기본 smoke |
| name = `fn.__name__` | 도구 dispatch 일치 보장 |
| `description` non-empty | Gemini가 tool 선택 시 description 사용 → 누락 시 AI 판단 실패 |
| `parameters.properties` non-empty (인자 있는 도구) | 누락 방지 |
| **모든 ARRAY property의 `items` non-None** | **직전 회귀 재발 방지 (핵심)** |
| `items.type` != `TYPE_UNSPECIFIED` | 빈 dict로 우회 차단 |
| 모든 property의 `type` != `TYPE_UNSPECIFIED` | unknown 타입 힌트 감지 |

---

## 2. File-Level Changes

### 2.1 `tests/test_tool_schemas.py` (신규)

```python
"""Smoke tests: verify every PRODUCTION_TOOL produces a Gemini-valid schema.

Catches drift like the 2026-04-24 regression where `list` without element type
silently shipped to Gemini as `ARRAY` with missing `items` → 400 INVALID_ARGUMENT.
"""
from __future__ import annotations

import pytest
from google.genai.types import FunctionDeclaration, Type

from api._tool_dispatch import PRODUCTION_TOOLS


class _FakeClient:
    """Minimal stub — FunctionDeclaration.from_callable only reads .vertexai."""
    vertexai = False


_FAKE_CLIENT = _FakeClient()


@pytest.fixture(scope="module")
def fake_client():
    return _FAKE_CLIENT


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
        """Schema generation must not raise — catches broken signatures."""
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
                    f"{tool_fn.__name__}.{prop_name}: ARRAY property has no items — "
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
```

---

## 3. Test Output Shape

```
tests/test_tool_schemas.py::TestToolSchemaSmoke::test_generates_without_error[search_production_items] PASSED
tests/test_tool_schemas.py::TestToolSchemaSmoke::test_generates_without_error[get_production_summary] PASSED
...
tests/test_tool_schemas.py::TestToolSchemaSmoke::test_no_array_without_items[execute_custom_query] PASSED
tests/test_tool_schemas.py::test_production_tools_not_empty PASSED
tests/test_tool_schemas.py::test_tool_names_unique PASSED
```

예상 테스트 개수: 6 check × 7 tool + 2 global = **44 tests** 추가.

---

## 4. Rollback

단일 신규 파일이므로 revert 시 부작용 없음.

---

## 5. Open Questions

- (해결됨) FakeClient stub 작동 여부 → Bash smoke로 검증 완료 (`items.type=Type.STRING` 정상).
- (해결됨) 도구 순회 방식 → parametrize로 자동 확장.
