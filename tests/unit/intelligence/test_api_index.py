"""Unit tests for trusted runtime API index completions."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from app.intelligence.api_index import (
    DEFAULT_RUNTIME_API_INDEX_PATH,
    DEFAULT_STDLIB_API_INDEX_PATH,
    clear_api_index_cache,
    provide_api_index_member_items,
)
from app.intelligence.completion_models import CompletionKind

pytestmark = pytest.mark.unit


def setup_function() -> None:
    clear_api_index_cache()


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


def test_stdlib_api_index_is_shipped_and_provides_os_members() -> None:
    assert DEFAULT_STDLIB_API_INDEX_PATH.exists()

    items = provide_api_index_member_items(module_name="os", member_prefix="getcwd", limit=20)

    assert any(item.label == "getcwd" for item in items)
    assert items[0].source == "static_api_index"


def test_api_index_json_is_loaded_once_per_file() -> None:
    read_calls = 0
    original_read_text = Path.read_text

    def _counting_read_text(self: Path, *args: object, **kwargs: object) -> str:
        nonlocal read_calls
        if self.name.endswith("_api_index.json"):
            read_calls += 1
        return original_read_text(self, *args, **kwargs)

    with patch.object(Path, "read_text", _counting_read_text):
        clear_api_index_cache()
        provide_api_index_member_items(module_name="os", member_prefix="p", limit=5)
        provide_api_index_member_items(module_name="sys", member_prefix="p", limit=5)

    assert read_calls == 2
