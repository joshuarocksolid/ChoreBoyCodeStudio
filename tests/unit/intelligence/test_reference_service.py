"""Unit tests for project reference discovery service."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.intelligence.reference_service import extract_symbol_under_cursor, find_references

pytestmark = pytest.mark.unit


def test_extract_symbol_under_cursor_returns_identifier_token() -> None:
    source = "result = helper_task(value)"
    cursor_position = source.index("helper_task") + 3

    symbol = extract_symbol_under_cursor(source, cursor_position)

    assert symbol == "helper_task"


def test_find_references_collects_definitions_and_usages_across_files(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "a.py").write_text(
        "def helper_task(value):\n"
        "    return value\n\n"
        "helper_task(1)\n",
        encoding="utf-8",
    )
    current_file = project_root / "b.py"
    current_source = "from a import helper_task\nresult = helper_task(2)\n"
    current_file.write_text(current_source, encoding="utf-8")

    result = find_references(
        project_root=str(project_root.resolve()),
        current_file_path=str(current_file.resolve()),
        source_text=current_source,
        cursor_position=current_source.rfind("helper_task") + 2,
    )

    assert result.symbol_name == "helper_task"
    assert len(result.hits) >= 3
    assert any(hit.is_definition for hit in result.hits)
    assert any(hit.file_path.endswith("b.py") and not hit.is_definition for hit in result.hits)


def test_find_references_excludes_comments_and_string_literals(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    current_file = project_root / "main.py"
    current_source = (
        "def helper_task():\n"
        "    return 'helper_task'\n"
        "# helper_task in comment\n"
        "value = helper_task()\n"
    )
    current_file.write_text(current_source, encoding="utf-8")

    result = find_references(
        project_root=str(project_root.resolve()),
        current_file_path=str(current_file.resolve()),
        source_text=current_source,
        cursor_position=current_source.index("helper_task()") + 1,
    )

    assert result.symbol_name == "helper_task"
    assert len(result.hits) == 2
    assert all("comment" not in hit.line_text for hit in result.hits)
    assert all("'helper_task'" not in hit.line_text for hit in result.hits)


def test_find_references_returns_empty_when_no_symbol_at_cursor(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    source = "value = 1 + 2"

    result = find_references(
        project_root=str(project_root.resolve()),
        current_file_path=str((project_root / "main.py").resolve()),
        source_text=source,
        cursor_position=source.index("+"),
    )

    assert result.symbol_name == ""
    assert result.hits == []
