"""Unit tests for trusted runtime API index completions."""

from __future__ import annotations

import pytest

from app.intelligence.api_index import DEFAULT_RUNTIME_API_INDEX_PATH, provide_api_index_member_items
from app.intelligence.completion_models import CompletionKind

pytestmark = pytest.mark.unit


def test_freecad_api_index_provides_static_members() -> None:
    items = provide_api_index_member_items(module_name="FreeCAD", member_prefix="new", limit=20)

    assert items
    assert items[0].label == "newDocument"
    assert items[0].kind == CompletionKind.FUNCTION
    assert items[0].source == "static_api_index"
    assert items[0].engine == "api_index"


def test_pyside_api_index_handles_submodule_alias() -> None:
    items = provide_api_index_member_items(module_name="PySide2.QtWidgets", member_prefix="QMain", limit=20)

    assert [item.label for item in items] == ["QMainWindow"]
    assert items[0].kind == CompletionKind.CLASS


def test_generated_runtime_api_index_is_shipped_and_used_by_default() -> None:
    assert DEFAULT_RUNTIME_API_INDEX_PATH.exists()

    items = provide_api_index_member_items(module_name="PySide2", member_prefix="QtPrint", limit=20)

    assert [item.label for item in items] == ["QtPrintSupport"]
