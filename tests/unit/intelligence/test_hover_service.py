"""Unit tests for hover metadata resolution service."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.intelligence.hover_service import resolve_hover_info
from app.persistence.sqlite_index import IndexedSymbol, SQLiteSymbolIndex

pytestmark = pytest.mark.unit


def test_resolve_hover_info_from_current_file_function_definition(tmp_path: Path) -> None:
    source = (
        "def build_report(value):\n"
        "    \"\"\"Build report summary.\"\"\"\n"
        "    return value\n\n"
        "result = build_report(1)\n"
    )
    cursor_position = source.rfind("build_report") + 2

    hover = resolve_hover_info(
        source_text=source,
        cursor_position=cursor_position,
        current_file_path=str((tmp_path / "main.py").resolve()),
        project_root=None,
        cache_db_path=None,
    )

    assert hover is not None
    assert hover.symbol_name == "build_report"
    assert hover.symbol_kind == "function"
    assert hover.source == "current_file"
    assert hover.doc_summary == "Build report summary."


def test_resolve_hover_info_falls_back_to_project_index_definition(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    helper_file = project_root / "helper.py"
    helper_file.write_text(
        "def helper_task(name):\n"
        "    \"\"\"Run helper task.\"\"\"\n"
        "    return name\n",
        encoding="utf-8",
    )
    current_file = project_root / "main.py"
    source = "value = helper_task\n"
    current_file.write_text(source, encoding="utf-8")

    cache_path = tmp_path / "state" / "symbols.sqlite3"
    cache = SQLiteSymbolIndex(str(cache_path))
    cache.upsert_symbols_for_files(
        str(project_root.resolve()),
        {
            str(helper_file.resolve()): [
                IndexedSymbol(name="helper_task", file_path=str(helper_file.resolve()), line_number=1)
            ]
        },
    )

    cursor_position = source.rfind("helper_task") + 3
    hover = resolve_hover_info(
        source_text=source,
        cursor_position=cursor_position,
        current_file_path=str(current_file.resolve()),
        project_root=str(project_root.resolve()),
        cache_db_path=str(cache_path),
    )

    assert hover is not None
    assert hover.symbol_name == "helper_task"
    assert hover.source == "project_index"
    assert hover.file_path == str(helper_file.resolve())
    assert hover.line_number == 1


def test_resolve_hover_info_falls_back_to_builtin_symbol() -> None:
    source = "print('hello')"
    hover = resolve_hover_info(
        source_text=source,
        cursor_position=2,
        current_file_path="/tmp/none.py",
        project_root=None,
        cache_db_path=None,
    )

    assert hover is not None
    assert hover.symbol_name == "print"
    assert hover.symbol_kind == "builtin"
    assert hover.source == "builtin"


def test_resolve_hover_info_returns_none_when_cursor_not_on_symbol() -> None:
    hover = resolve_hover_info(
        source_text="value = 1 + 2",
        cursor_position=8,
        current_file_path="/tmp/none.py",
        project_root=None,
        cache_db_path=None,
    )

    assert hover is None
